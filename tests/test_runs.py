"""Tests for the run stores."""
from unittest.mock import MagicMock

from kbase.agent.runs import InMemoryRunStore, MongoRunStore


def run(i="r1", user="u1", updated="2026-11-08T10:00:00"):
    return {"id": i, "user_id": user, "updated_at": updated, "trace": []}


def test_inmemory_round_trip_is_a_copy():
    store = InMemoryRunStore()
    r = run()
    store.save(r)
    got = store.get("r1")
    got["user_id"] = "changed"
    assert store.get("r1")["user_id"] == "u1"
    assert store.get("nope") is None


def test_inmemory_list_sorted_and_scoped():
    store = InMemoryRunStore()
    store.save(run("a", updated="2026-11-08T09:00:00"))
    store.save(run("b", updated="2026-11-08T11:00:00"))
    store.save(run("c", user="u2"))
    assert [r["id"] for r in store.list("u1")] == ["b", "a"]


def test_mongo_save_get_list():
    coll = MagicMock()
    store = MongoRunStore(coll)
    store.save(run())
    store.save(run())
    assert coll.create_index.call_count == 1
    filt, doc = coll.replace_one.call_args[0]
    assert filt == {"_id": "r1"} and doc["_id"] == "r1" and "id" not in doc
    assert coll.replace_one.call_args[1] == {"upsert": True}
    coll.find_one.return_value = {"_id": "r1", "user_id": "u1"}
    assert store.get("r1") == {"id": "r1", "user_id": "u1"}
    coll.find_one.return_value = None
    assert store.get("x") is None
    coll.find.return_value.sort.return_value.limit.return_value = [{"_id": "r1"}]
    assert store.list("u1") == [{"id": "r1"}]
    assert coll.find.call_args[0] == ({"user_id": "u1"}, {"trace": 0})
