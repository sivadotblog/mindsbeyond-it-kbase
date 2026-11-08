"""Tests for the in process memory store."""
from datetime import datetime, timedelta, timezone

import pytest

from kbase.memory.inmemory import InMemoryStore, lexical_relevance
from kbase.memory.models import MemoryRecord

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def rec(**kw):
    base = {"type": "semantic", "user_id": "u1", "content": "cluster = kbase-prod", "label": "cluster",
            "created_at": NOW, "updated_at": NOW}
    base.update(kw)
    return MemoryRecord(**base)


@pytest.fixture
def store():
    return InMemoryStore(now=lambda: NOW)


def test_write_and_find_by_label(store):
    r = store.write(rec())
    assert store.find_by_label("u1", "semantic", "Cluster") is r
    assert store.find_by_label("u2", "semantic", "cluster") is None


def test_update_replaces(store):
    r = store.write(rec())
    r.content = "cluster = other"
    store.update(r)
    assert store.list("u1")[0].content == "cluster = other"


def test_private_memories_stay_private(store):
    store.write(rec(user_id="u2"))
    store.write(rec(user_id="u2", visibility="org", content="shared term", label="term"))
    assert [r.content for r in store.list("u1")] == ["shared term"]


def test_expired_are_hidden(store):
    store.write(rec(type="stm", expires_at=NOW - timedelta(seconds=1)))
    store.write(rec(type="stm", content="fresh", label=None, expires_at=NOW + timedelta(hours=1)))
    assert [r.content for r in store.list("u1", "stm")] == ["fresh"]
    assert store.find_by_label("u1", "stm", "cluster") is None


def test_list_newest_first_and_limit(store):
    store.write(rec(content="a", label="a", updated_at=NOW - timedelta(hours=2)))
    store.write(rec(content="b", label="b"))
    assert [r.content for r in store.list("u1", limit=1)] == ["b"]


def test_recall_ranks_matches_and_respects_types(store):
    store.write(rec(type="procedural", label="KB-0016:step-2", content="port 10260 needed on the NSG",
                    importance=0.9))
    store.write(rec(type="episodic", label="run", content="baked bread", importance=0.1))
    out = store.recall("port 10260 refused", "u1", ("procedural", "semantic"), limit=5)
    assert out.hits[0].record.type == "procedural" and out.hits[0].relevance == 1.0
    assert all(h.record.type != "episodic" for h in out.hits)


def test_recall_includes_important_facts_with_floor(store):
    store.write(rec())
    out = store.recall("nc to endpoint fails", "u1", ("semantic",))
    assert out.hits and out.hits[0].relevance == pytest.approx(0.25)


def test_recall_empty(store):
    assert store.recall("anything", "u1", ("semantic",)).hits == []


def test_delete_only_own(store):
    r = store.write(rec())
    assert store.delete(r.id, "u2") is False
    assert store.delete(r.id, "u1") is True
    assert store.delete(r.id, "u1") is False


def test_setup_and_describe(store):
    assert store.setup() and store.describe()["persistent"] is False


def test_lexical_relevance_empty():
    assert lexical_relevance("", rec()) == 0.0
