"""Tests for fact extraction and the ADD / UPDATE / NOOP write path."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from kbase.memory.consolidate import MemoryManager
from kbase.memory.extract import Fact, heuristic_facts, llm_facts
from kbase.memory.inmemory import InMemoryStore

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


@pytest.fixture
def manager():
    return MemoryManager(InMemoryStore(now=lambda: NOW), stm_ttl_hours=2, now=lambda: NOW)


class TestHeuristicFacts:
    @pytest.mark.parametrize("text,expected", [
        ("our cluster is kbase-prod", [Fact("cluster", "kbase-prod")]),
        ("The project id is 6a664fdf970411d2b8aad08b.", [Fact("project id", "6a664fdf970411d2b8aad08b")]),
        ("set CLUSTER=kbase-prod please", [Fact("CLUSTER", "kbase-prod")]),
        ("my region: eastus2", [Fact("region", "eastus2")]),
    ])
    def test_extracts(self, text, expected):
        assert heuristic_facts(text) == expected

    def test_remember_that(self):
        facts = heuristic_facts("remember that the NSG blocks 10260 by default")
        assert facts[0].label == "note nsg block 10260 default"

    @pytest.mark.parametrize("text", ["my password is hunter2", "DB_PASS=abc123", "our api key is sk-ant-abcdefghijkl",
                                      "remember that password=hunter2", "", "nothing to see"])
    def test_skips_secrets_and_noise(self, text):
        assert heuristic_facts(text) == []

    def test_fact_text(self):
        assert Fact("a", "b").text == "a = b"


class TestLlmFacts:
    def test_off(self):
        assert llm_facts(None, "x") is None
        assert llm_facts(MagicMock(enabled=False), "x") is None

    def test_parses_and_filters(self):
        llm = MagicMock(enabled=True)
        llm.complete_json.return_value = {"facts": [{"label": "cluster", "value": "kbase-prod."},
                                                    {"label": "password", "value": "x"}, "junk"]}
        assert llm_facts(llm, "our cluster is kbase-prod") == [Fact("cluster", "kbase-prod")]

    def test_bad_reply(self):
        llm = MagicMock(enabled=True)
        llm.complete_json.return_value = {"nope": 1}
        assert llm_facts(llm, "x") is None


class TestManager:
    def test_add_then_noop_then_update(self, manager):
        first = manager.remember_fact("u1", "cluster", "kbase-prod")
        same = manager.remember_fact("u1", "Cluster", "kbase-prod")
        changed = manager.remember_fact("u1", "cluster", "kbase-dev")
        assert (first.op, same.op, changed.op) == ("ADD", "NOOP", "UPDATE")
        assert changed.record.content == "cluster = kbase-dev"
        assert changed.record.history[0]["content"] == "cluster = kbase-prod"
        assert len(manager.store.list("u1", "semantic")) == 1

    def test_update_keeps_higher_importance_and_source(self, manager):
        manager.remember(type_="semantic", user_id="u1", label="x", content="x = 1", importance=0.9)
        out = manager.remember(type_="semantic", user_id="u1", label="x", content="x = 2", importance=0.2,
                               source={"run_id": "r"})
        assert out.record.importance == 0.9 and out.record.source == {"run_id": "r"}

    def test_near_duplicate_without_label(self, manager):
        manager.remember(type_="taxonomic", user_id="u1", content="SourceID tags every resource for chargeback")
        out = manager.remember(type_="taxonomic", user_id="u1", content="SourceID tags every resource for chargeback.")
        assert out.op == "NOOP"

    def test_turns_expire(self, manager):
        out = manager.add_turn("u1", "run1", "user", "hello")
        assert out.op == "ADD" and out.record.expires_at == NOW + timedelta(hours=2)
        assert out.record.source == {"run_id": "run1", "role": "user"}

    def test_redacts_content(self, manager):
        out = manager.remember(type_="semantic", user_id="u1", label="conn",
                               content="uri mongodb://a:hunter2@h")
        assert "hunter2" not in out.record.content

    def test_step_note_and_episode(self, manager):
        note = manager.remember_step_note("u1", "KB-0016", "step-2", "Step 2", "port 10260", failed=True, run_id="r")
        assert note.record.label == "KB-0016:step-2" and note.record.importance == 0.9
        assert "(failed)" in note.record.content
        ok = manager.remember_step_note("u1", "KB-0016", "verify", "Verify", "worked", failed=False)
        assert ok.record.importance == 0.7
        ep = manager.remember_episode("u1", "abcdef123456", "Title", "Summary text", "KB-0016")
        assert ep.record.label.startswith("run abcdef12") and ep.record.source["doc_id"] == "KB-0016"

    def test_recall_delegates(self, manager):
        manager.remember_fact("u1", "cluster", "kbase-prod")
        assert manager.recall("cluster", "u1").hits

    def test_outcome_to_api(self, manager):
        assert manager.remember_fact("u1", "a", "b").to_api()["op"] == "ADD"
