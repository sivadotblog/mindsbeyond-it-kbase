"""Tests for the Atlas Agent Engine memory adapter with a fake SDK."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from kbase.memory.agent_engine import AgentEngineMemoryStore, TokenProvider
from kbase.memory.base import MemoryUnavailable, MemoryUnsupported
from kbase.memory.models import MemoryRecord

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def rec(**kw):
    base = {"type": "semantic", "user_id": "u1", "content": "cluster = kbase-prod", "label": "cluster",
            "source": {"run_id": "run1", "doc_id": "KB-0016"}}
    base.update(kw)
    return MemoryRecord(**base)


@pytest.fixture
def sdk():
    bound = MagicMock()
    bound.record_turn.return_value = SimpleNamespace(id="t1")
    bound.save_semantic.return_value = SimpleNamespace(id="s1")
    bound.save_episode.return_value = SimpleNamespace(id="e1")
    bound.save_procedure.return_value = SimpleNamespace(id="p1")
    bound.save_taxonomic.return_value = {"id": "x1"}
    memory = MagicMock()
    memory.bind.return_value = bound
    return memory, bound


@pytest.fixture
def store(sdk):
    memory, _ = sdk
    factory = MagicMock(return_value=memory)
    s = AgentEngineMemoryStore(project_id="proj", token_provider=lambda: "tok", memory_factory=factory,
                               context_factory=lambda u, sess, a: {"user_id": u, "session_id": sess, "agent_id": a})
    s._factory_mock = factory
    return s


class TestTokenProvider:
    def test_static(self):
        assert TokenProvider(token="t")() == "t"

    def test_needs_credentials(self):
        with pytest.raises(MemoryUnavailable):
            TokenProvider()

    def test_mints_and_caches(self):
        session = MagicMock()
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {"access_token": "abc", "expires_in": 3600}
        clock = MagicMock(return_value=1000.0)
        tp = TokenProvider(client_id="id", client_secret="sec", token_url="https://ae/token", session=session, clock=clock)
        assert tp() == "abc" and tp() == "abc"
        assert session.post.call_count == 1
        assert session.post.call_args[1]["auth"] == ("id", "sec")
        assert session.post.call_args[1]["data"] == {"grant_type": "client_credentials"}
        clock.return_value = 1000.0 + 3600
        tp()
        assert session.post.call_count == 2

    def test_failure(self):
        session = MagicMock()
        session.post.return_value.status_code = 401
        tp = TokenProvider(client_id="id", client_secret="sec", token_url="u", session=session)
        with pytest.raises(MemoryUnavailable, match="401"):
            tp()


class TestWrites:
    def test_semantic(self, store, sdk):
        _, bound = sdk
        out = store.write(rec())
        assert out.id == "s1"
        kw = bound.save_semantic.call_args[1]
        assert kw["label"] == "cluster" and kw["metadata"]["importance"] == 0.5
        store._factory_mock.assert_called_once_with("tok", "proj", None)

    def test_stm_uses_session(self, store, sdk):
        _, bound = sdk
        store.write(rec(type="stm", label=None, source={"run_id": "run1", "role": "assistant"}))
        assert bound.record_turn.call_args[1]["role"] == "assistant"
        assert bound.record_turn.call_args[1]["session_id"] == "run1"

    def test_episode_procedure_taxonomy(self, store, sdk):
        _, bound = sdk
        store.write(rec(type="episodic", label="run 1"))
        assert bound.save_episode.call_args[1]["tags"] == ["KB-0016"]
        store.write(rec(type="procedural", label="KB-0016:step-2"))
        assert bound.save_procedure.call_args[1]["procedure"] == "KB-0016:step-2"
        out = store.write(rec(type="taxonomic", label="SourceID", source=None))
        assert out.id == "x1" and bound.save_taxonomic.call_args[1]["term"] == "SourceID"

    def test_update_resaves(self, store, sdk):
        _, bound = sdk
        store.update(rec())
        assert bound.save_semantic.called

    def test_client_rebuilt_on_new_token(self, sdk):
        memory, _ = sdk
        tokens = iter(["a", "a", "b"])
        factory = MagicMock(return_value=memory)
        s = AgentEngineMemoryStore(project_id="p", token_provider=lambda: next(tokens), memory_factory=factory,
                                   context_factory=lambda *a: {})
        s.write(rec())
        s.write(rec())
        s.write(rec())
        assert factory.call_count == 2


class TestReads:
    def test_find_by_label(self, store, sdk):
        _, bound = sdk
        bound.get_semantic.return_value = {"id": "s1", "text": "cluster = kbase-prod"}
        found = store.find_by_label("u1", "semantic", "cluster")
        assert found.content == "cluster = kbase-prod" and found.id == "s1"
        bound.get_procedure.return_value = None
        assert store.find_by_label("u1", "procedural", "KB-0016:step-2") is None
        bound.get_semantic.return_value = {"id": "s1"}
        assert store.find_by_label("u1", "semantic", "cluster") is None
        assert store.find_by_label("u1", "episodic", "x") is None

    def test_recall_scores_chunks(self, store, sdk):
        _, bound = sdk
        bound.search.return_value = [
            SimpleNamespace(id="c1", content="cluster = kbase-prod", source=SimpleNamespace(value="semantic"),
                            timestamp=NOW, similarity_score=0.9,
                            metadata={"label": "cluster", "metadata": {"importance": 0.7}}),
            {"id": "c2", "content": "old run", "source": "episodic", "timestamp": "2026-11-01T00:00:00Z",
             "similarity_score": 0.45, "metadata": {}},
        ]
        out = store.recall("cluster", "u1", ("semantic", "episodic", "stm"), limit=4)
        assert bound.search.call_args[1]["sources"] == ["semantic", "episodic"]
        assert out.hits[0].record.label == "cluster" and out.hits[0].relevance == 1.0
        assert out.hits[1].relevance == pytest.approx(0.5)
        assert out.pipeline[0]["sdk"] == "Memory.search"

    def test_recall_only_stm_defaults(self, store, sdk):
        _, bound = sdk
        bound.search.return_value = []
        store.recall("q", "u1", ("stm",))
        assert bound.search.call_args[1]["sources"] == ["semantic", "episodic"]

    def test_list(self, store, sdk):
        _, bound = sdk
        bound.list_episodes.return_value = [{"id": "e1", "title": "Run", "content": "did things",
                                             "created_at": "2026-11-08T00:00:00Z"}]
        bound.search.return_value = [{"id": "c1", "content": "fact", "source": "semantic", "metadata": {}}]
        items = store.list("u1")
        assert [i.type for i in items] == ["episodic", "semantic"]
        assert [i.type for i in store.list("u1", "episodic")] == ["episodic"]
        store.list("u1", "procedural")
        assert bound.search.call_args[1]["sources"] == ["procedural"]

    def test_unknown_source_maps_to_semantic(self, store):
        chunk = {"id": "c", "content": "x", "source": "weird", "metadata": None}
        assert store._chunk_to_record(chunk, "u1").type == "semantic"


def test_delete_not_supported(store):
    with pytest.raises(MemoryUnsupported):
        store.delete("x", "u1")


def test_setup_and_describe(store):
    assert "agentengine memory" in store.setup()[0]
    assert store.describe()["project_id"] == "proj"
