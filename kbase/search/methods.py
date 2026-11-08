"""Registry of search methods: what each one is, what it needs and how to build it."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from kbase.search import pipelines as P

Builder = Callable[[P.SearchParams, P.IndexConfig], list[dict[str, Any]]]


@dataclass(frozen=True)
class Method:
    name: str
    label: str
    summary: str
    builder: Builder
    score_meta: str
    needs_vector_index: bool
    needs_text_index: bool
    min_version: tuple[int, int] | None = None
    stage: str | None = None
    params: tuple[str, ...] = ()

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "label": self.label,
            "summary": self.summary,
            "score": self.score_meta,
            "requires": {
                "vector_index": self.needs_vector_index,
                "text_index": self.needs_text_index,
                "min_version": ".".join(map(str, self.min_version)) if self.min_version else None,
                "stage": self.stage,
            },
            "params": list(self.params),
        }


METHODS: dict[str, Method] = {
    m.name: m
    for m in (
        Method(
            name="fulltext",
            label="Full text (BM25)",
            summary="Lucene $search text operator over title and body. Strong on exact terms, codes and ports.",
            builder=P.fulltext_pipeline,
            score_meta="searchScore",
            needs_vector_index=False,
            needs_text_index=True,
            stage="$search",
            params=("limit", "fuzzy", "category", "domain"),
        ),
        Method(
            name="vector_ann",
            label="Vector ANN",
            summary="$vectorSearch with autoEmbed, approximate HNSW search over numCandidates.",
            builder=P.vector_ann_pipeline,
            score_meta="vectorSearchScore",
            needs_vector_index=True,
            needs_text_index=False,
            stage="$vectorSearch",
            params=("limit", "num_candidates", "query_model"),
        ),
        Method(
            name="vector_enn",
            label="Vector ENN (exact)",
            summary="$vectorSearch with exact: true. Scans every vector. The ground truth for ANN recall.",
            builder=P.vector_enn_pipeline,
            score_meta="vectorSearchScore",
            needs_vector_index=True,
            needs_text_index=False,
            stage="$vectorSearch",
            params=("limit", "query_model"),
        ),
        Method(
            name="vector_filtered",
            label="Vector with pre filter",
            summary="ANN restricted to a category or domain with the $vectorSearch filter option.",
            builder=P.vector_filtered_pipeline,
            score_meta="vectorSearchScore",
            needs_vector_index=True,
            needs_text_index=False,
            stage="$vectorSearch",
            params=("limit", "num_candidates", "query_model", "category", "domain"),
        ),
        Method(
            name="hybrid_rrf",
            label="Hybrid, rank fusion",
            summary="$rankFusion: reciprocal rank fusion of vector and text, weight / (60 + rank).",
            builder=P.hybrid_rrf_pipeline,
            score_meta="score",
            needs_vector_index=True,
            needs_text_index=True,
            min_version=(8, 0),
            stage="$rankFusion",
            params=("limit", "query_model", "vector_weight", "text_weight", "category", "domain"),
        ),
        Method(
            name="hybrid_score",
            label="Hybrid, score fusion",
            summary="$scoreFusion: normalize each leg's scores, then a weighted average.",
            builder=P.hybrid_score_pipeline,
            score_meta="score",
            needs_vector_index=True,
            needs_text_index=True,
            min_version=(8, 3),
            stage="$scoreFusion",
            params=("limit", "query_model", "vector_weight", "text_weight", "normalization",
                    "category", "domain"),
        ),
    )
}

DEFAULT_COMPARE = ("fulltext", "vector_ann", "vector_enn", "hybrid_rrf", "hybrid_score")


def get_method(name: str) -> Method:
    try:
        return METHODS[name]
    except KeyError:
        raise ValueError(f"unknown method {name!r}; choose from {', '.join(METHODS)}") from None
