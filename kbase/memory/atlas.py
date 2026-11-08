"""Agent memory on Atlas collections built by this repo.

Recall is one ``$rankFusion`` with three inputs:

* ``semantic``: ``$vectorSearch`` on an ``autoEmbed`` index over ``content``
* ``lexical``: ``$search`` over ``content`` and ``label``
* ``recent``: ``$match`` plus ``$sort`` on importance and update time, which also covers memories
  written seconds ago that the search indexes have not caught up with yet

After fusion the pipeline normalizes the fused score, computes recency and importance, and sorts by
the weighted score, so the whole score is visible in the pipeline. If ``$rankFusion`` is not
available it falls back to vector only, then to recent only.
"""
from __future__ import annotations

import time
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.errors import OperationFailure, PyMongoError
from pymongo.operations import SearchIndexModel

from kbase.memory.models import MemoryHit, MemoryRecord, RecallResult, label_key
from kbase.memory.scoring import explain

FILTER_FIELDS = ("user_id", "type", "visibility", "agent_id")


def vector_index_definition(model: str) -> dict[str, Any]:
    return {
        "fields": [
            {"type": "autoEmbed", "modality": "text", "path": "content", "model": model},
            *({"type": "filter", "path": f} for f in FILTER_FIELDS),
        ]
    }


def text_index_definition() -> dict[str, Any]:
    return {
        "mappings": {
            "dynamic": False,
            "fields": {
                "content": {"type": "string", "analyzer": "lucene.standard"},
                "label": {"type": "string", "analyzer": "lucene.standard"},
                **{f: {"type": "token"} for f in FILTER_FIELDS},
            },
        }
    }


def visibility_match(user_id: str) -> dict[str, Any]:
    return {"$or": [{"user_id": user_id}, {"visibility": "org"}]}


def mql_filter(user_id: str, types: tuple[str, ...]) -> dict[str, Any]:
    return {"$and": [visibility_match(user_id), {"type": {"$in": list(types)}}]}


def search_filter(user_id: str, types: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {"in": {"path": "type", "value": list(types)}},
        {"compound": {"should": [{"equals": {"path": "user_id", "value": user_id}},
                                 {"equals": {"path": "visibility", "value": "org"}}],
                      "minimumShouldMatch": 1}},
    ]


def score_tail(*, weights: tuple[float, float, float], half_life_hours: float, limit: int,
               score_meta: str) -> list[dict[str, Any]]:
    """Stages that turn a retrieval score into relevance, recency, importance and a final score."""
    w_rel, w_rec, w_imp = weights
    total = (w_rel + w_rec + w_imp) or 1.0
    age_hours = {"$divide": [{"$subtract": ["$$NOW", "$updated_at"]}, 3_600_000]}
    rel = {"$cond": [{"$gt": ["$_maxRaw", 0]}, {"$divide": ["$_raw", "$_maxRaw"]}, 0]}
    return [
        {"$addFields": {"_raw": {"$meta": score_meta} if score_meta else {"$literal": 0.0}}},
        {"$setWindowFields": {"output": {"_maxRaw": {"$max": "$_raw",
                                                     "window": {"documents": ["unbounded", "unbounded"]}}}}},
        {"$addFields": {
            "score_parts": {
                "relevance": rel,
                "recency": {"$pow": [0.5, {"$divide": [{"$max": [age_hours, 0]}, half_life_hours]}]},
                "importance": {"$ifNull": ["$importance", 0.5]},
            }
        }},
        {"$addFields": {"score": {"$divide": [{"$add": [
            {"$multiply": [w_rel, "$score_parts.relevance"]},
            {"$multiply": [w_rec, "$score_parts.recency"]},
            {"$multiply": [w_imp, "$score_parts.importance"]},
        ]}, total]}}},
        {"$sort": {"score": -1}},
        {"$limit": limit},
        {"$project": {"_raw": 0, "_maxRaw": 0, "history": 0}},
    ]


def recall_pipeline(query: str, user_id: str, types: tuple[str, ...], *, limit: int,
                    vector_index: str, text_index: str, model: str | None,
                    weights: tuple[float, float, float], half_life_hours: float,
                    strategy: str = "fusion") -> list[dict[str, Any]]:
    per_leg = max(limit * 3, 10)
    vector = {"$vectorSearch": {
        "index": vector_index, "path": "content", "query": {"text": query},
        "numCandidates": per_leg * 20, "limit": per_leg, "filter": mql_filter(user_id, types),
        **({"model": model} if model else {}),
    }}
    recent = [{"$match": mql_filter(user_id, types)},
              {"$sort": {"importance": -1, "updated_at": -1}}, {"$limit": per_leg}]
    tail = dict(weights=weights, half_life_hours=half_life_hours, limit=limit)
    if strategy == "vector":
        return [vector, *score_tail(score_meta="vectorSearchScore", **tail)]
    if strategy == "recent":
        return [*recent, *score_tail(score_meta="", **tail)]
    lexical = [{"$search": {"index": text_index, "compound": {
        "must": [{"text": {"query": query, "path": ["content", "label"]}}],
        "filter": search_filter(user_id, types)}}}, {"$limit": per_leg}]
    fusion = {"$rankFusion": {
        "input": {"pipelines": {"semantic": [vector], "lexical": lexical, "recent": recent}},
        "combination": {"weights": {"semantic": 1.0, "lexical": 1.0, "recent": 0.5}},
    }}
    return [fusion, *score_tail(score_meta="score", **tail)]


class AtlasMemoryStore:
    name = "atlas"
    capabilities = {"delete": True, "update": True, "list": True}

    def __init__(self, collection: Any, *, vector_index: str = "memory_vector_index",
                 text_index: str = "memory_text_index", model: str = "voyage-4",
                 weights: tuple[float, float, float] = (0.6, 0.2, 0.2), half_life_hours: float = 168.0):
        self.collection = collection
        self.vector_index = vector_index
        self.text_index = text_index
        self.model = model
        self.weights = weights
        self.half_life_hours = half_life_hours
        self._strategy = "fusion"

    def write(self, record: MemoryRecord) -> MemoryRecord:
        self.collection.insert_one(record.to_doc())
        return record

    def update(self, record: MemoryRecord) -> MemoryRecord:
        doc = record.to_doc()
        doc_id = doc.pop("_id")
        self.collection.update_one({"_id": doc_id, "user_id": record.user_id}, {"$set": doc})
        return record

    def find_by_label(self, user_id: str, type_: str, label: str) -> MemoryRecord | None:
        doc = self.collection.find_one({"user_id": user_id, "type": type_, "label_key": label_key(label)})
        return MemoryRecord.from_doc(doc) if doc else None

    def list(self, user_id: str, type_: str | None = None, limit: int = 50) -> list[MemoryRecord]:
        query: dict[str, Any] = visibility_match(user_id)
        if type_:
            query = {"$and": [query, {"type": type_}]}
        cursor = self.collection.find(query).sort("updated_at", DESCENDING).limit(limit)
        return [MemoryRecord.from_doc(d) for d in cursor]

    def recall(self, query: str, user_id: str, types: tuple[str, ...], limit: int = 8) -> RecallResult:
        start = time.perf_counter()
        warnings: list[str] = []
        order = ["fusion", "vector", "recent"]
        for strategy in order[order.index(self._strategy):]:
            pipeline = recall_pipeline(
                query, user_id, types, limit=limit, vector_index=self.vector_index,
                text_index=self.text_index, model=self.model, weights=self.weights,
                half_life_hours=self.half_life_hours, strategy=strategy)
            try:
                docs = list(self.collection.aggregate(pipeline))
            except OperationFailure as exc:
                warnings.append(f"{strategy} recall failed, falling back: {exc}")
                continue
            if strategy != self._strategy:
                self._strategy = strategy
            hits = []
            for d in docs:
                parts = d.get("score_parts") or {}
                rel, rec, imp = (float(parts.get(k, 0.0)) for k in ("relevance", "recency", "importance"))
                hits.append(MemoryHit(record=MemoryRecord.from_doc(d), score=float(d.get("score", 0.0)),
                                      relevance=rel, recency=rec, importance=imp, why=explain(rel, rec, imp)))
            labels = {"fusion": "$rankFusion of vector, text and recent",
                      "vector": "$vectorSearch only", "recent": "recent and important only"}
            return RecallResult(backend=self.name, strategy=labels[strategy], hits=hits, pipeline=pipeline,
                                ms=round((time.perf_counter() - start) * 1000, 1), warnings=warnings)
        return RecallResult(backend=self.name, strategy="none", hits=[], pipeline=None,
                            ms=round((time.perf_counter() - start) * 1000, 1), warnings=warnings)

    def delete(self, memory_id: str, user_id: str) -> bool:
        return self.collection.delete_one({"_id": memory_id, "user_id": user_id}).deleted_count == 1

    def setup(self) -> list[str]:
        steps = []
        self.collection.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0, name="stm_ttl")
        steps.append("TTL index stm_ttl on expires_at")
        self.collection.create_index([("user_id", ASCENDING), ("type", ASCENDING), ("label_key", ASCENDING)],
                                     name="user_type_label")
        steps.append("lookup index user_type_label")
        for model in (
            SearchIndexModel(definition=vector_index_definition(self.model), name=self.vector_index,
                             type="vectorSearch"),
            SearchIndexModel(definition=text_index_definition(), name=self.text_index, type="search"),
        ):
            name = model.document["name"]
            try:
                self.collection.create_search_index(model=model)
                steps.append(f"search index {name} created (builds in the background)")
            except OperationFailure as exc:
                if "already exists" in str(exc).lower():
                    steps.append(f"search index {name} already exists")
                else:
                    steps.append(f"search index {name} failed: {exc}")
        return steps

    def index_status(self) -> list[dict[str, Any]]:
        try:
            return [{"name": ix.get("name"), "status": ix.get("status"), "queryable": bool(ix.get("queryable"))}
                    for ix in self.collection.list_search_indexes()]
        except PyMongoError as exc:
            return [{"name": "error", "status": str(exc), "queryable": False}]

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "capabilities": self.capabilities, "persistent": True,
                "collection": getattr(self.collection, "name", None), "indexes": self.index_status(),
                "strategy": self._strategy}
