"""Tests for the trace and the agent engine."""
from unittest.mock import MagicMock

import pytest

from kbase.agent.engine import AgentEngine, Tool, command_variables, explain_command
from kbase.agent.trace import Trace, scrub
from kbase.memory.consolidate import MemoryManager
from kbase.memory.inmemory import InMemoryStore


class TestTrace:
    def test_add_numbers_and_redacts(self):
        t = Trace()
        t.add("tool", "token=abc123", {"note": "password=x", "n": [1, "Bearer abcdefghijk"]})
        e = t.to_list()[0]
        assert e["seq"] == 1 and "abc123" not in e["title"] and "password=x" not in e["detail"]["note"]
        assert "abcdefghijk" not in e["detail"]["n"][1]

    def test_unknown_kind(self):
        with pytest.raises(ValueError):
            Trace().add("nope", "x")

    def test_timed(self):
        t = Trace()
        with t.timed("tool", "work") as d:
            d["x"] = 1
        assert t.events[0]["detail"] == {"x": 1} and t.events[0]["ms"] is not None

    def test_scrub_passthrough(self):
        assert scrub(5) == 5 and scrub(("a",)) == ["a"]


class TestExplain:
    def test_reads_and_changes(self):
        assert "reads state" in explain_command("az network nsg rule list -g rg")
        assert "changes state" in explain_command("terraform apply -auto-approve")
        assert "netcat" in explain_command("nc -zv host 10260") and "reads state" in explain_command("nc -zv h 1")

    def test_unknown_tool(self):
        assert "the foo command" in explain_command("foo --bar")

    def test_curl_defaults_to_read(self):
        assert "reads state" in explain_command("curl https://x/clusters/$C")
        assert "not obvious" in explain_command("curl -H a https://x --data-raw y")

    def test_variables(self):
        out = explain_command('curl -u "$ATLAS_PUBLIC_KEY:$ATLAS_PRIVATE_KEY" https://x/$ORG_ID')
        assert "$ORG_ID set in your shell" in out and "never sees or fills" in out
        assert command_variables("echo ${CLUSTER} $CLUSTER") == ["CLUSTER"]

    def test_empty(self):
        assert explain_command("") == ""


@pytest.fixture
def engine(offline_kb):
    return AgentEngine(offline_kb, memory=MemoryManager(InMemoryStore()))


class TestEngine:
    def test_only_read_only_tools(self, engine):
        with pytest.raises(ValueError, match="read only"):
            engine.register(Tool("run_shell", "x", False, lambda: None))

    def test_unknown_tool(self, engine):
        with pytest.raises(ValueError):
            engine.call(Trace(), "nope")

    def test_search_uses_first_working_method(self, engine):
        t = Trace()
        out = engine.call(t, "search_kb", query="private endpoint timeout")
        assert out["method"] == "hybrid_rrf" and out["reranked"] is True
        assert t.events[0]["kind"] == "search" and t.events[0]["detail"]["top"][0]["doc_id"] == "KB-0016"

    def test_search_chain_falls_through(self):
        kb = MagicMock()
        kb.run.side_effect = [
            {"status": "unsupported", "results": [], "reason": "no rerank"},
            {"status": "ok", "results": []},
            {"status": "ok", "results": [{"doc_id": "KB-1", "title": "t", "score": 1}], "method": "vector_ann",
             "reranked": False, "pipeline": []},
        ]
        out = AgentEngine(kb).call(Trace(), "search_kb", query="x")
        assert out["method"] == "vector_ann" and len(out["tried"]) == 3

    def test_search_all_fail(self):
        kb = MagicMock()
        kb.run.return_value = {"status": "error", "results": [], "reason": "down"}
        assert AgentEngine(kb).call(Trace(), "search_kb", query="x")["status"] == "empty"

    def test_tool_detail_shapes(self, engine):
        t = Trace()
        engine.call(t, "get_article", doc_id="KB-0016")
        engine.call(t, "related_articles", domain="Troubleshooting")
        engine.call(t, "explain_command", command="az login")
        assert t.events[0]["detail"]["result"]["doc_id"] == "KB-0016"
        assert isinstance(t.events[1]["detail"]["result"], list)
        assert "Azure CLI" in t.events[2]["detail"]["result"]

    def test_recall_without_memory_warns(self, offline_kb):
        t = Trace()
        assert AgentEngine(offline_kb, memory_error="off").recall(t, "q", "u") is None
        assert t.events[0]["kind"] == "warning" and t.events[0]["detail"]["reason"] == "off"

    def test_recall_failure_is_contained(self, offline_kb):
        memory = MagicMock()
        memory.recall.side_effect = RuntimeError("boom")
        t = Trace()
        assert AgentEngine(offline_kb, memory=memory).recall(t, "q", "u") is None
        assert t.events[0]["kind"] == "warning"

    def test_recall_and_remember(self, engine):
        t = Trace()
        engine.remember(t, lambda m: m.remember_fact("u", "cluster", "kbase-prod"), "fact")
        out = engine.recall(t, "cluster", "u")
        assert out.hits and [e["kind"] for e in t.events] == ["memory_write", "memory_recall"]
        assert engine.memory_backend == "inmemory"

    def test_remember_without_memory(self, offline_kb):
        assert AgentEngine(offline_kb).remember(Trace(), lambda m: None, "x") is None

    def test_remember_failure_is_contained(self, engine):
        t = Trace()
        assert engine.remember(t, lambda m: (_ for _ in ()).throw(RuntimeError("x")), "fact") is None
        assert t.events[0]["kind"] == "warning"

    def test_think_json_offline(self, engine):
        assert engine.think_json(Trace(), "p", "s", "x") is None

    def test_think_json_llm(self, offline_kb):
        llm = MagicMock(enabled=True, last_error="bad")
        llm.name = "fake"
        llm.complete_json.side_effect = [{"a": 1}, None]
        e = AgentEngine(offline_kb, llm=llm)
        t = Trace()
        assert e.think_json(t, "p", "s", "x") == {"a": 1}
        assert e.think_json(t, "p", "s", "x") is None
        assert [ev["kind"] for ev in t.events] == ["llm", "llm_fallback"]
