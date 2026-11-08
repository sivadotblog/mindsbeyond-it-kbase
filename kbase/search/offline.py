"""Offline stand ins for the Atlas methods, over the markdown files in ``md_docs``.

These are approximations so the UI and the agent work with no cluster. Results are labeled
``offline`` and every response still carries the Atlas pipeline the method would run.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from kbase.search import pipelines as P
from kbase.search.methods import METHODS, Method
from kbase.search.service import BaseSearchService

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and are as at be by for from how i in is it of on or the this to with via your you "
    "my our we can do does what when why which use using into".split()
)

OFFLINE_NOTE = {
    "fulltext": "Offline approximation: BM25 in Python over title and body.",
    "vector_ann": "Offline approximation: TF-IDF cosine in Python. No embeddings are used offline.",
    "vector_enn": "Offline approximation: TF-IDF cosine in Python (ANN and ENN are identical offline).",
    "vector_filtered": "Offline approximation: TF-IDF cosine in Python with the filter applied first.",
    "hybrid_rrf": "Offline approximation: reciprocal rank fusion (k=60) of the BM25 and TF-IDF lists.",
    "hybrid_score": "Offline approximation: normalized, weighted average of BM25 and TF-IDF scores.",
}
RERANK_NOTE = "Offline approximation of $rerank: cosine against title, domain and troubleshooting text."


def _stem(word: str) -> str:
    """Very light plural folding so "timeouts" matches "timeout" and "keys" matches "key"."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall((text or "").lower()) if t not in _STOP]


def _terms(text: str) -> list[str]:
    toks = tokenize(text)
    return toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]


def _doc_text(doc: dict[str, Any]) -> str:
    steps = doc.get("steps") or {}
    trouble = doc.get("troubleshooting") or {}
    title = doc.get("title", "")
    return " ".join([
        title, title, title, doc.get("domain", ""), doc.get("prerequisites", ""),
        steps.get("step1", ""), steps.get("step2", ""), steps.get("verify", ""),
        trouble.get("error", ""), trouble.get("solution", ""),
    ])


class _Index:
    def __init__(self, docs: list[dict[str, Any]]):
        self.docs = docs
        self.bm25_tf = [Counter(tokenize(" ".join([d.get("title", ""), d.get("raw_markdown", ""),
                                                   _doc_text(d)]))) for d in docs]
        self.lengths = [sum(tf.values()) for tf in self.bm25_tf]
        self.avg_len = (sum(self.lengths) / len(self.lengths)) if docs else 0.0
        df: Counter[str] = Counter()
        for tf in self.bm25_tf:
            df.update(tf.keys())
        n = len(docs)
        self.bm25_idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

        tfidf_tf = [Counter(_terms(_doc_text(d))) for d in docs]
        tdf: Counter[str] = Counter()
        for tf in tfidf_tf:
            tdf.update(tf.keys())
        self.tfidf_idf = {t: math.log((1 + n) / (1 + f)) + 1 for t, f in tdf.items()}
        self.vectors = [self._weigh(tf) for tf in tfidf_tf]

    def _weigh(self, tf: Counter[str]) -> dict[str, float]:
        vec = {t: (1 + math.log(c)) * self.tfidf_idf.get(t, 0.0) for t, c in tf.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def bm25(self, query: str, ids: list[int], k1: float = 1.5, b: float = 0.75) -> list[tuple[int, float]]:
        q = tokenize(query)
        out = []
        for i in ids:
            tf, dl = self.bm25_tf[i], self.lengths[i]
            score = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    score += self.bm25_idf.get(t, 0.0) * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / (self.avg_len or 1)))
            if score > 0:
                out.append((i, score))
        return sorted(out, key=lambda x: -x[1])

    def cosine(self, query: str, ids: list[int]) -> list[tuple[int, float]]:
        qv = self._weigh(Counter(_terms(query)))
        out = []
        for i in ids:
            v = self.vectors[i]
            score = sum(w * v.get(t, 0.0) for t, w in qv.items())
            if score > 0:
                out.append((i, score))
        return sorted(out, key=lambda x: -x[1])


def rrf(lists: dict[str, list[tuple[int, float]]], weights: dict[str, float], k: int = 60) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for name, ranked in lists.items():
        w = weights.get(name, 1.0)
        for rank, (i, _) in enumerate(ranked, start=1):
            scores[i] = scores.get(i, 0.0) + w * (1.0 / (k + rank))
    return sorted(scores.items(), key=lambda x: -x[1])


def _normalize(ranked: list[tuple[int, float]], how: str) -> dict[int, float]:
    if how == "none":
        return dict(ranked)
    if how == "sigmoid":
        return {i: 1 / (1 + math.exp(-s)) for i, s in ranked}
    if not ranked:
        return {}
    lo, hi = min(s for _, s in ranked), max(s for _, s in ranked)
    span = (hi - lo) or 1.0
    return {i: (s - lo) / span for i, s in ranked}


def score_fusion(lists: dict[str, list[tuple[int, float]]], weights: dict[str, float],
                 normalization: str) -> list[tuple[int, float]]:
    normed = {name: _normalize(ranked, normalization) for name, ranked in lists.items()}
    ids = set().union(*[set(n) for n in normed.values()]) if normed else set()
    n = len(lists) or 1
    out = {i: sum(weights.get(name, 1.0) * normed[name].get(i, 0.0) for name in lists) / n for i in ids}
    return sorted(out.items(), key=lambda x: -x[1])


class OfflineSearchService(BaseSearchService):
    """Search over parsed markdown articles with Python scoring."""

    offline = True

    def __init__(self, docs: list[dict[str, Any]], index: P.IndexConfig, **kwargs: Any):
        super().__init__(index, **kwargs)
        self.docs = docs
        self._ix = _Index(docs)
        self._by_id = {d["doc_id"]: d for d in docs}

    def capabilities(self, *, refresh: bool = False) -> dict[str, Any]:
        return {
            "mode": "offline",
            "server_version": None,
            "indexes": [],
            "errors": [],
            "query_format": self.index.query_format,
            "documents": len(self.docs),
            "methods": {name: {"available": True, "reason": "offline approximation"} for name in METHODS},
        }

    def _candidates(self, params: P.SearchParams, use_filters: bool) -> list[int]:
        ids = list(range(len(self.docs)))
        if not use_filters:
            return ids
        cat, dom = params.category, params.domain
        out = []
        for i in ids:
            d = self.docs[i]
            if cat and d.get("category") != cat:
                continue
            if dom and dom.lower() not in d.get("domain", "").lower():
                continue
            out.append(i)
        return out

    def _execute(self, method: Method, params: P.SearchParams, pipeline):
        name = method.name
        filtered = name in ("vector_filtered", "hybrid_rrf", "hybrid_score", "fulltext")
        ids = self._candidates(params, filtered and bool(params.filters))
        pool = P.rerank_pool(params.limit) if params.rerank else params.limit
        if name == "fulltext":
            ranked = self._ix.bm25(params.query, ids)
        elif name.startswith("vector"):
            ranked = self._ix.cosine(params.query, ids)
        else:
            legs = {"vector": self._ix.cosine(params.query, ids)[: pool * 2 or 20],
                    "text": self._ix.bm25(params.query, ids)[: pool * 2 or 20]}
            weights = {"vector": params.vector_weight, "text": params.text_weight}
            ranked = rrf(legs, weights) if name == "hybrid_rrf" else score_fusion(
                legs, weights, params.normalization)
        ranked = ranked[:pool]
        warnings = [OFFLINE_NOTE[name]]
        if params.rerank:
            ranked = self._rerank(params.query, ranked, params.limit)
            warnings.append(RERANK_NOTE)
        docs = []
        for item in ranked[: params.limit]:
            i, score = item[0], item[1]
            d = self.docs[i]
            row = {k: d.get(k) for k in ("doc_id", "title", "category", "domain")}
            row["score"] = score
            if params.rerank:
                row["preRerankRank"], row["preRerankScore"] = item[2], item[3]
            docs.append(row)
        return docs, pipeline, warnings

    def _rerank(self, query: str, ranked: list[tuple[int, float]], limit: int) -> list[tuple]:
        if not ranked:
            return []
        top = max(s for _, s in ranked) or 1.0
        qv = self._ix._weigh(Counter(_terms(query)))
        out = []
        for pre_rank, (i, s) in enumerate(ranked, start=1):
            d = self.docs[i]
            focus = self._ix._weigh(Counter(_terms(" ".join([
                d.get("title", ""), d.get("domain", ""),
                (d.get("troubleshooting") or {}).get("error", ""),
                (d.get("troubleshooting") or {}).get("solution", ""),
            ]))))
            cos = sum(w * focus.get(t, 0.0) for t, w in qv.items())
            out.append((i, round(0.7 * cos + 0.3 * (s / top), 6), pre_rank, s))
        return sorted(out, key=lambda x: -x[1])[:limit]

    def get_article(self, doc_id: str) -> dict[str, Any] | None:
        doc = self._by_id.get(doc_id)
        return dict(doc) if doc else None

    def related(self, domain: str, *, exclude: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
        out = [{"doc_id": d["doc_id"], "title": d["title"]} for d in self.docs
               if d.get("domain") == domain and d["doc_id"] != exclude]
        return out[:limit]

    def facets(self) -> dict[str, list[str]]:
        return {
            "category": sorted({d["category"] for d in self.docs if d.get("category")}),
            "domain": sorted({d["domain"] for d in self.docs if d.get("domain")}),
        }
