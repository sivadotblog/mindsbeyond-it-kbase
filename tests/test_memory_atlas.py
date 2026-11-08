"""Tests for the Atlas memory store with a mocked collection."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from pymongo.errors import OperationFailure, PyMongoError

from kbase.memory.atlas import (
    AtlasMemoryStore,
    mql_filter,
    recall_pipeline,
    search_filter,
    text_index_definition,
    vector_index_definition,
)
from kbase.memory.models import MemoryRecord

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def rec(**kw):
    base = {"type": "semantic", "user_id": "u1", "content": "cluster = kbase-prod", "label": "cluster",
            "created_at": NOW, "updated_at": NOW}
    base.update(kw)
    return MemoryRecord(**base)


def args(strategy="fusion"):
    return dict(limit=5, vector_index="mv", text_index="mt", model="voyage-4", weights=(0.6, 0.2, 0.2),
                half_life_hours=168, strategy=strategy)


@pytest.fixture
def coll():
    return MagicMock()


@pytest.fixture
def store(coll):
    return AtlasMemoryStore(coll, vector_index="mv", text_index="mt")


class TestDefinitions:
    def test_vector_index(self):
        fields = vector_index_definition("voyage-4")["fields"]
        assert fields[0] == {"type": "autoEmbed", "modality": "text", "path": "content", "model": "voyage-4"}
        assert {f["path"] for f in fields[1:]} == {"user_id", "type", "visibility", "agent_id"}

    def test_text_index(self):
        fields = text_index_definition()["mappings"]["fields"]
        assert fields["user_id"] == {"type": "token"} and fields["content"]["type"] == "string"

    def test_filters(self):
        assert mql_filter("u1", ("semantic",)) == {"$and": [
            {"$or": [{"user_id": "u1"}, {"visibility": "org"}]}, {"type": {"$in": ["semantic"]}}]}
        assert search_filter("u1", ("semantic",))[1]["compound"]["minimumShouldMatch"] == 1


class TestRecallPipeline:
    def test_fusion_has_three_legs(self):
        pipe = recall_pipeline("port", "u1", ("semantic", "procedural"), **args())
        legs = pipe[0]["$rankFusion"]["input"]["pipelines"]
        assert set(legs) == {"semantic", "lexical", "recent"}
        vs = legs["semantic"][0]["$vectorSearch"]
        assert vs["query"] == {"text": "port"} and vs["model"] == "voyage-4" and vs["limit"] == 15
        assert legs["recent"][1] == {"$sort": {"importance": -1, "updated_at": -1}}
        assert pipe[1] == {"$addFields": {"_raw": {"$meta": "score"}}}

    def test_score_tail(self):
        pipe = recall_pipeline("port", "u1", ("semantic",), **args())
        stages = [next(iter(s)) for s in pipe]
        assert stages == ["$rankFusion", "$addFields", "$setWindowFields", "$addFields", "$addFields",
                          "$sort", "$limit", "$project"]
        parts = pipe[3]["$addFields"]["score_parts"]
        assert set(parts) == {"relevance", "recency", "importance"}
        assert pipe[6] == {"$limit": 5}

    def test_vector_strategy(self):
        pipe = recall_pipeline("port", "u1", ("semantic",), **args("vector"))
        assert "$vectorSearch" in pipe[0] and pipe[1] == {"$addFields": {"_raw": {"$meta": "vectorSearchScore"}}}

    def test_recent_strategy(self):
        pipe = recall_pipeline("port", "u1", ("semantic",), **args("recent"))
        assert "$match" in pipe[0] and pipe[3] == {"$addFields": {"_raw": {"$literal": 0.0}}}

    def test_no_model(self):
        a = args()
        a["model"] = None
        pipe = recall_pipeline("q", "u1", ("semantic",), **a)
        assert "model" not in pipe[0]["$rankFusion"]["input"]["pipelines"]["semantic"][0]["$vectorSearch"]


class TestStore:
    def test_write(self, store, coll):
        r = store.write(rec())
        assert coll.insert_one.call_args[0][0]["_id"] == r.id

    def test_update_scopes_by_user(self, store, coll):
        r = rec()
        store.update(r)
        filt, change = coll.update_one.call_args[0]
        assert filt == {"_id": r.id, "user_id": "u1"} and "_id" not in change["$set"]

    def test_find_by_label(self, store, coll):
        coll.find_one.return_value = rec().to_doc()
        assert store.find_by_label("u1", "semantic", "Cluster").label == "cluster"
        assert coll.find_one.call_args[0][0] == {"user_id": "u1", "type": "semantic", "label_key": "cluster"}
        coll.find_one.return_value = None
        assert store.find_by_label("u1", "semantic", "x") is None

    def test_list(self, store, coll):
        coll.find.return_value.sort.return_value.limit.return_value = [rec().to_doc()]
        assert len(store.list("u1", "semantic")) == 1
        assert coll.find.call_args[0][0]["$and"][1] == {"type": "semantic"}

    def test_recall_maps_hits(self, store, coll):
        doc = {**rec().to_doc(), "score": 0.8, "score_parts": {"relevance": 1, "recency": 0.5, "importance": 0.7}}
        coll.aggregate.return_value = iter([doc])
        out = store.recall("cluster", "u1", ("semantic",))
        assert out.hits[0].score == 0.8 and out.hits[0].relevance == 1.0
        assert out.strategy.startswith("$rankFusion") and out.pipeline

    def test_recall_falls_back(self, store, coll):
        coll.aggregate.side_effect = [OperationFailure("Unrecognized pipeline stage name: '$rankFusion'"),
                                      iter([])]
        out = store.recall("cluster", "u1", ("semantic",))
        assert out.strategy == "$vectorSearch only" and out.warnings
        assert store._strategy == "vector"

    def test_recall_all_fail(self, store, coll):
        coll.aggregate.side_effect = OperationFailure("nope")
        assert store.recall("cluster", "u1", ("semantic",)).strategy == "none"

    def test_delete(self, store, coll):
        coll.delete_one.return_value.deleted_count = 1
        assert store.delete("id1", "u1") is True
        assert coll.delete_one.call_args[0][0] == {"_id": "id1", "user_id": "u1"}

    def test_setup(self, store, coll):
        coll.create_search_index.side_effect = [None, OperationFailure("Index already exists")]
        steps = store.setup()
        assert coll.create_index.call_args_list[0][1] == {"expireAfterSeconds": 0, "name": "stm_ttl"}
        assert "created" in steps[2] and "already exists" in steps[3]

    def test_setup_failure_reported(self, store, coll):
        coll.create_search_index.side_effect = OperationFailure("not allowed")
        assert "failed" in store.setup()[2]

    def test_describe(self, store, coll):
        coll.list_search_indexes.return_value = [{"name": "mv", "status": "READY", "queryable": True}]
        assert store.describe()["indexes"][0]["queryable"] is True
        coll.list_search_indexes.side_effect = PyMongoError("x")
        assert store.describe()["indexes"][0]["name"] == "error"
