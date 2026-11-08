"""Run search methods against Atlas, compare them and report what the cluster supports."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from pymongo.errors import OperationFailure, PyMongoError

from kbase.search import pipelines as P
from kbase.search.compare import agreement
from kbase.search.methods import DEFAULT_COMPARE, METHODS, Method, get_method

RERANK_REQUIREMENT = (
    "$rerank needs Atlas with a recent server (8.3+, 9.0+ per the current reference) and "
    "Native Reranking enabled in Project Settings"
)


class Unsupported(Exception):
    """The cluster cannot run this method. ``reason`` says what it needs."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def parse_version(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    parts = text.split(".")
    try:
        return int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except ValueError:
        return None


def _is_query_shape_error(message: str) -> bool:
    msg = message.lower()
    return "query" in msg and any(w in msg for w in ("object", "string", "query.text", "type"))


def classify_failure(method: Method, params: P.SearchParams, message: str) -> str | None:
    """Return an "unsupported" reason for known feature gaps, else ``None``."""
    msg = message.lower()
    if "$rerank" in msg or ("rerank" in msg and ("not enabled" in msg or "disabled" in msg)):
        return RERANK_REQUIREMENT
    if "unrecognized pipeline stage" in msg:
        if method.stage and method.stage.lower() in msg:
            need = ".".join(map(str, method.min_version)) + "+" if method.min_version else "a newer server"
            return f"{method.stage} needs MongoDB {need}"
        if params.rerank:
            return RERANK_REQUIREMENT
        return f"the server does not recognize a stage: {message}"
    if "autoembed" in msg or "auto-embed" in msg or "automated embedding" in msg:
        return f"automated embedding is not available: {message}"
    return None


def format_results(docs: list[dict[str, Any]], *, reranked: bool) -> list[dict[str, Any]]:
    out = []
    for rank, doc in enumerate(docs, start=1):
        item: dict[str, Any] = {
            "rank": rank,
            "doc_id": doc.get("doc_id", ""),
            "title": doc.get("title", ""),
            "category": doc.get("category", ""),
            "domain": doc.get("domain", ""),
            "score": round(float(doc.get("score") or 0.0), 6),
        }
        if doc.get("scoreDetails") is not None:
            item["score_details"] = doc["scoreDetails"]
        if reranked:
            pre = doc.get("preRerankRank")
            item["pre_rerank_rank"] = int(pre) if pre is not None else None
            item["pre_rerank_score"] = (
                round(float(doc["preRerankScore"]), 6) if doc.get("preRerankScore") is not None else None
            )
            item["rank_change"] = (int(pre) - rank) if pre is not None else None
        out.append(item)
    return out


def rerank_warnings(results: list[dict[str, Any]]) -> list[str]:
    scores = {r["score"] for r in results}
    if len(results) > 1 and len(scores) == 1:
        return [
            "Every rerank score is the same value. Atlas returns a constant score when Native "
            "Reranking is not enabled for the project."
        ]
    return []


class BaseSearchService:
    """Shared run and compare logic. Subclasses implement :meth:`_execute`."""

    offline = False

    def __init__(self, index: P.IndexConfig, *, default_query_model: str | None = None,
                 default_rerank_model: str | None = None,
                 clock: Callable[[], float] = time.perf_counter):
        self.index = index
        self.default_query_model = default_query_model
        self.default_rerank_model = default_rerank_model
        self.clock = clock

    # -- hooks ---------------------------------------------------------------
    def _execute(self, method: Method, params: P.SearchParams,
                 pipeline: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        """Return (raw docs, pipeline that ran, warnings)."""
        raise NotImplementedError

    def _precheck(self, method: Method, params: P.SearchParams) -> None:
        """Raise :class:`Unsupported` before running when the gap is known."""

    # -- public --------------------------------------------------------------
    def methods(self) -> list[dict[str, Any]]:
        return [m.describe() for m in METHODS.values()]

    def with_defaults(self, params: P.SearchParams) -> P.SearchParams:
        params = P.validate_params(params)
        changes: dict[str, Any] = {}
        if not params.query_model and self.default_query_model:
            changes["query_model"] = self.default_query_model
        if params.rerank and not params.rerank_model and self.default_rerank_model:
            changes["rerank_model"] = self.default_rerank_model
        if not changes:
            return params
        data = {**params.__dict__, **changes}
        return P.SearchParams(**data)

    def run(self, method_name: str, params: P.SearchParams) -> dict[str, Any]:
        method = get_method(method_name)
        params = self.with_defaults(params)
        pipeline = method.builder(params, self.index)
        base = {
            "method": method.name,
            "label": method.label,
            "offline": self.offline,
            "reranked": params.rerank,
            "pipeline": pipeline,
            "results": [],
            "warnings": [],
            "reason": None,
        }
        start = self.clock()
        try:
            self._precheck(method, params)
            docs, ran, warnings = self._execute(method, params, pipeline)
        except Unsupported as exc:
            return {**base, "status": "unsupported", "reason": exc.reason,
                    "ms": round((self.clock() - start) * 1000, 1)}
        except (OperationFailure, PyMongoError) as exc:
            return {**base, "status": "error", "reason": str(exc),
                    "ms": round((self.clock() - start) * 1000, 1)}
        results = format_results(docs, reranked=params.rerank)
        if params.rerank:
            warnings = warnings + rerank_warnings(results)
        return {**base, "status": "ok", "pipeline": ran, "results": results, "warnings": warnings,
                "ms": round((self.clock() - start) * 1000, 1)}

    def compare(self, method_names: list[str] | tuple[str, ...] | None,
                params: P.SearchParams) -> dict[str, Any]:
        names = list(method_names or DEFAULT_COMPARE)
        if not names or len(names) > 8:
            raise ValueError("pick between 1 and 8 methods")
        for name in names:
            get_method(name)
        params = self.with_defaults(params)

        def one(name: str) -> dict[str, Any]:
            try:
                return self.run(name, params)
            except ValueError as exc:
                method = get_method(name)
                return {"method": name, "label": method.label, "status": "error", "reason": str(exc),
                        "offline": self.offline, "results": [], "pipeline": [], "warnings": [],
                        "ms": 0.0, "reranked": params.rerank}

        start = self.clock()
        with ThreadPoolExecutor(max_workers=min(4, len(names))) as pool:
            results = dict(zip(names, pool.map(one, names)))
        return {
            "query": params.query,
            "results": results,
            "agreement": agreement(results),
            "offline": self.offline,
            "ms": round((self.clock() - start) * 1000, 1),
        }


class SearchService(BaseSearchService):
    """Runs pipelines on an Atlas collection."""

    CAPABILITY_TTL = 60.0

    def __init__(self, collection: Any, index: P.IndexConfig, **kwargs: Any):
        super().__init__(index, **kwargs)
        self.collection = collection
        self._query_format = index.query_format
        self._caps: dict[str, Any] | None = None
        self._caps_at = 0.0

    # -- capability report ---------------------------------------------------
    def capabilities(self, *, refresh: bool = False) -> dict[str, Any]:
        now = time.monotonic()
        if self._caps is not None and not refresh and now - self._caps_at < self.CAPABILITY_TTL:
            return self._caps
        report: dict[str, Any] = {"mode": "atlas", "server_version": None, "indexes": [],
                                  "methods": {}, "errors": [], "query_format": self._query_format}
        try:
            info = self.collection.database.command("buildInfo")
            report["server_version"] = info.get("version")
        except PyMongoError as exc:
            report["errors"].append(f"buildInfo failed: {exc}")
        try:
            for ix in self.collection.list_search_indexes():
                report["indexes"].append({
                    "name": ix.get("name"),
                    "type": ix.get("type", "search"),
                    "status": ix.get("status"),
                    "queryable": bool(ix.get("queryable")),
                })
        except PyMongoError as exc:
            report["errors"].append(f"list_search_indexes failed: {exc}")

        version = parse_version(report["server_version"])
        names = {ix["name"]: ix for ix in report["indexes"]}
        for method in METHODS.values():
            report["methods"][method.name] = self._availability(method, version, names)
        self._caps, self._caps_at = report, now
        return report

    def _availability(self, method: Method, version: tuple[int, int] | None,
                      indexes: dict[str, dict[str, Any]]) -> dict[str, Any]:
        reasons = []
        if method.min_version and version and version < method.min_version:
            reasons.append(f"{method.stage} needs MongoDB {'.'.join(map(str, method.min_version))}+")
        for needed, name in ((method.needs_vector_index, self.index.vector_index),
                             (method.needs_text_index, self.index.text_index)):
            if not needed:
                continue
            ix = indexes.get(name)
            if ix is None:
                reasons.append(f"index {name} does not exist")
            elif not ix.get("queryable"):
                reasons.append(f"index {name} is {ix.get('status') or 'not queryable'}")
        return {"available": not reasons, "reason": "; ".join(reasons) or None}

    def _precheck(self, method: Method, params: P.SearchParams) -> None:
        if self._caps is None:
            return
        version = parse_version(self._caps.get("server_version"))
        if method.min_version and version and version < method.min_version:
            raise Unsupported(f"{method.stage} needs MongoDB {'.'.join(map(str, method.min_version))}+ "
                              f"(cluster runs {self._caps.get('server_version')})")

    # -- execution -----------------------------------------------------------
    def _build(self, method: Method, params: P.SearchParams, query_format: str) -> list[dict[str, Any]]:
        idx = P.IndexConfig(self.index.text_index, self.index.vector_index, self.index.vector_path,
                            query_format)
        return method.builder(params, idx)

    def _execute(self, method, params, pipeline):
        warnings: list[str] = []
        pipeline = self._build(method, params, self._query_format)
        try:
            docs = list(self.collection.aggregate(pipeline))
        except OperationFailure as exc:
            message = str(exc)
            if method.needs_vector_index and _is_query_shape_error(message):
                other = "string" if self._query_format == "object" else "object"
                retry = self._build(method, params, other)
                try:
                    docs = list(self.collection.aggregate(retry))
                except OperationFailure:
                    pass
                else:
                    self._query_format = other
                    warnings.append(f"autoEmbed query sent as {other} form after the server rejected "
                                    f"the other form")
                    return docs, retry, warnings
            reason = classify_failure(method, params, message)
            if reason:
                raise Unsupported(reason) from exc
            raise
        if not docs:
            warnings.extend(self._index_warnings(method))
        return docs, pipeline, warnings

    def _index_warnings(self, method: Method) -> list[str]:
        caps = self._caps
        if caps is None:
            return []
        avail = caps.get("methods", {}).get(method.name, {})
        if avail.get("reason"):
            return [f"No results. {avail['reason']}."]
        return []

    # -- article access used by the agent ------------------------------------
    def get_article(self, doc_id: str) -> dict[str, Any] | None:
        return self.collection.find_one({"doc_id": doc_id}, {"_id": 0})

    def related(self, domain: str, *, exclude: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"domain": domain}
        if exclude:
            query["doc_id"] = {"$ne": exclude}
        cursor = self.collection.find(query, {"_id": 0, "doc_id": 1, "title": 1}).limit(limit)
        return list(cursor)

    def facets(self) -> dict[str, list[str]]:
        return {
            "category": sorted(v for v in self.collection.distinct("category") if v),
            "domain": sorted(v for v in self.collection.distinct("domain") if v),
        }
