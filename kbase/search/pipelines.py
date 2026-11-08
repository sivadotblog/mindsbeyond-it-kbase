"""Pure builders for the Atlas aggregation pipelines behind each search method.

Nothing here talks to a database. Every builder returns plain dicts so tests can assert the exact
shape and the API can return the pipeline that ran. Request shapes for preview features (autoEmbed
query, $rerank, $scoreFusion) live only in this file.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

RESULT_FIELDS = {"_id": 0, "doc_id": 1, "title": 1, "category": 1, "domain": 1}
TEXT_PATHS = ("title", "raw_markdown")
RERANK_PATHS = ["title", "raw_markdown"]
MAX_CANDIDATES = 10_000
MAX_RERANK_DOCS = 1_000


@dataclass(frozen=True)
class IndexConfig:
    """Names and models of the indexes the pipelines target."""

    text_index: str = "fulltext_index"
    vector_index: str = "auto_embedding_index"
    vector_path: str = "raw_markdown"
    query_format: str = "object"


@dataclass(frozen=True)
class SearchParams:
    """User facing knobs for one search. Validated by :func:`validate_params`."""

    query: str
    limit: int = 10
    num_candidates: int | None = None
    query_model: str | None = None
    category: str | None = None
    domain: str | None = None
    vector_weight: float = 1.0
    text_weight: float = 1.0
    normalization: str = "sigmoid"
    rerank: bool = False
    rerank_model: str | None = None
    fuzzy: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def filters(self) -> dict[str, str]:
        return {k: v for k, v in (("category", self.category), ("domain", self.domain)) if v}


NORMALIZATIONS = ("none", "sigmoid", "minMaxScaler")
QUERY_MODELS = ("voyage-4-lite", "voyage-4", "voyage-4-large")
MAX_QUERY_CHARS = 1000


def validate_params(params: SearchParams) -> SearchParams:
    """Raise ``ValueError`` for bad input; clamp numbers into range."""
    query = (params.query or "").strip()
    if not query:
        raise ValueError("query is required")
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"query is longer than {MAX_QUERY_CHARS} characters")
    if params.normalization not in NORMALIZATIONS:
        raise ValueError(f"normalization must be one of {', '.join(NORMALIZATIONS)}")
    if params.query_model and params.query_model not in QUERY_MODELS:
        raise ValueError(f"query_model must be one of {', '.join(QUERY_MODELS)}")
    if params.vector_weight < 0 or params.text_weight < 0:
        raise ValueError("weights must be non negative")
    limit = min(max(int(params.limit), 1), 50)
    num_candidates = params.num_candidates
    if num_candidates is not None:
        num_candidates = min(max(int(num_candidates), limit), MAX_CANDIDATES)
    return SearchParams(
        query=query,
        limit=limit,
        num_candidates=num_candidates,
        query_model=params.query_model,
        category=(params.category or None),
        domain=(params.domain or None),
        vector_weight=float(params.vector_weight),
        text_weight=float(params.text_weight),
        normalization=params.normalization,
        rerank=bool(params.rerank),
        rerank_model=params.rerank_model,
        fuzzy=bool(params.fuzzy),
        extra=dict(params.extra),
    )


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def vector_filter(filters: dict[str, str]) -> dict[str, Any] | None:
    """MQL pre filter for ``$vectorSearch`` on fields indexed as ``filter``."""
    clauses = [{key: {"$eq": value}} for key, value in sorted(filters.items())]
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def vector_search_stage(
    *,
    index: str,
    path: str,
    query: str,
    limit: int,
    num_candidates: int | None = None,
    exact: bool = False,
    model: str | None = None,
    filters: dict[str, str] | None = None,
    query_format: str = "object",
) -> dict[str, Any]:
    """``$vectorSearch`` against an ``autoEmbed`` field.

    ``query_format="object"`` sends ``{"text": query}`` as the stage reference documents.
    ``"string"`` sends the bare string that older examples use.
    """
    stage: dict[str, Any] = {
        "index": index,
        "path": path,
        "query": {"text": query} if query_format == "object" else query,
        "limit": limit,
    }
    if exact:
        stage["exact"] = True
    else:
        candidates = num_candidates if num_candidates is not None else limit * 20
        stage["numCandidates"] = min(max(candidates, limit), MAX_CANDIDATES)
    if model:
        stage["model"] = model
    flt = vector_filter(filters or {})
    if flt:
        stage["filter"] = flt
    return {"$vectorSearch": stage}


def search_stage(
    *,
    index: str,
    query: str,
    paths: tuple[str, ...] = TEXT_PATHS,
    fuzzy: bool = False,
    filters: dict[str, str] | None = None,
) -> dict[str, Any]:
    """``$search`` with the ``text`` operator, wrapped in ``compound`` when filters are given.

    ``category`` is indexed with ``lucene.keyword`` so a ``text`` clause is an exact match there.
    ``domain`` is analyzed, so it uses ``phrase``.
    """
    text: dict[str, Any] = {"query": query, "path": list(paths)}
    if fuzzy:
        text["fuzzy"] = {"maxEdits": 1}
    filters = filters or {}
    if not filters:
        return {"$search": {"index": index, "text": text}}
    filter_clauses = []
    if filters.get("category"):
        filter_clauses.append({"text": {"query": filters["category"], "path": "category"}})
    if filters.get("domain"):
        filter_clauses.append({"phrase": {"query": filters["domain"], "path": "domain"}})
    return {
        "$search": {
            "index": index,
            "compound": {"must": [{"text": text}], "filter": filter_clauses},
        }
    }


def project_stage(score_meta: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    fields: dict[str, Any] = dict(RESULT_FIELDS)
    fields["score"] = {"$meta": score_meta}
    if extra:
        fields.update(extra)
    return {"$project": fields}


def rerank_tail(
    *,
    query: str,
    limit: int,
    pool: int,
    score_meta: str,
    model: str | None,
) -> list[dict[str, Any]]:
    """Stages appended after any retrieval pipeline to rerank with Voyage AI.

    The pre rerank score and rank are saved first because ``$rerank`` replaces ``$meta: score``.
    """
    num_docs = min(max(pool, limit), MAX_RERANK_DOCS)
    rerank: dict[str, Any] = {
        "query": {"text": query},
        "path": list(RERANK_PATHS),
        "numDocsToRerank": num_docs,
    }
    if model:
        rerank["model"] = model
    return [
        {"$addFields": {"preRerankScore": {"$meta": score_meta}}},
        {
            "$setWindowFields": {
                "sortBy": {"preRerankScore": -1},
                "output": {"preRerankRank": {"$documentNumber": {}}},
            }
        },
        {"$rerank": rerank},
        {"$limit": limit},
        project_stage("score", extra={"preRerankScore": 1, "preRerankRank": 1}),
    ]


def rerank_pool(limit: int) -> int:
    """How many candidates to hand to the reranker for ``limit`` results."""
    return min(max(limit * 3, 20), 100)


# ---------------------------------------------------------------------------
# Methods
# ---------------------------------------------------------------------------

def _finish(retrieval: list[dict[str, Any]], *, params: SearchParams, score_meta: str,
            needs_limit: bool) -> list[dict[str, Any]]:
    if params.rerank:
        pool = rerank_pool(params.limit)
        stages = list(retrieval)
        if needs_limit:
            stages.append({"$limit": pool})
        return stages + rerank_tail(
            query=params.query, limit=params.limit, pool=pool,
            score_meta=score_meta, model=params.rerank_model,
        )
    stages = list(retrieval)
    if needs_limit:
        stages.append({"$limit": params.limit})
    extra = {"scoreDetails": {"$meta": "scoreDetails"}} if score_meta == "score" else None
    stages.append(project_stage(score_meta, extra=extra))
    return stages


def _retrieval_limit(params: SearchParams) -> int:
    return rerank_pool(params.limit) if params.rerank else params.limit


def fulltext_pipeline(params: SearchParams, idx: IndexConfig) -> list[dict[str, Any]]:
    stage = search_stage(index=idx.text_index, query=params.query, fuzzy=params.fuzzy,
                         filters=params.filters)
    return _finish([stage], params=params, score_meta="searchScore", needs_limit=True)


def _vector(params: SearchParams, idx: IndexConfig, *, exact: bool, use_filters: bool,
            limit: int | None = None) -> dict[str, Any]:
    lim = limit if limit is not None else _retrieval_limit(params)
    return vector_search_stage(
        index=idx.vector_index,
        path=idx.vector_path,
        query=params.query,
        limit=lim,
        num_candidates=None if exact else (params.num_candidates or lim * 20),
        exact=exact,
        model=params.query_model,
        filters=params.filters if use_filters else None,
        query_format=idx.query_format,
    )


def vector_ann_pipeline(params: SearchParams, idx: IndexConfig) -> list[dict[str, Any]]:
    return _finish([_vector(params, idx, exact=False, use_filters=False)], params=params,
                   score_meta="vectorSearchScore", needs_limit=False)


def vector_enn_pipeline(params: SearchParams, idx: IndexConfig) -> list[dict[str, Any]]:
    return _finish([_vector(params, idx, exact=True, use_filters=False)], params=params,
                   score_meta="vectorSearchScore", needs_limit=False)


def vector_filtered_pipeline(params: SearchParams, idx: IndexConfig) -> list[dict[str, Any]]:
    if not params.filters:
        raise ValueError("filtered vector search needs a category or domain filter")
    return _finish([_vector(params, idx, exact=False, use_filters=True)], params=params,
                   score_meta="vectorSearchScore", needs_limit=False)


def _fusion_inputs(params: SearchParams, idx: IndexConfig) -> dict[str, list[dict[str, Any]]]:
    per_leg = max(_retrieval_limit(params) * 2, 20)
    return {
        "vector": [_vector(params, idx, exact=False, use_filters=True, limit=per_leg)],
        "text": [
            search_stage(index=idx.text_index, query=params.query, fuzzy=params.fuzzy,
                         filters=params.filters),
            {"$limit": per_leg},
        ],
    }


def hybrid_rrf_pipeline(params: SearchParams, idx: IndexConfig) -> list[dict[str, Any]]:
    stage = {
        "$rankFusion": {
            "input": {"pipelines": _fusion_inputs(params, idx)},
            "combination": {"weights": {"vector": params.vector_weight, "text": params.text_weight}},
            "scoreDetails": True,
        }
    }
    return _finish([stage], params=params, score_meta="score", needs_limit=True)


def hybrid_score_pipeline(params: SearchParams, idx: IndexConfig) -> list[dict[str, Any]]:
    stage = {
        "$scoreFusion": {
            "input": {
                "pipelines": _fusion_inputs(params, idx),
                "normalization": params.normalization,
            },
            "combination": {
                "weights": {"vector": params.vector_weight, "text": params.text_weight},
                "method": "avg",
            },
            "scoreDetails": True,
        }
    }
    return _finish([stage], params=params, score_meta="score", needs_limit=True)
