"""Tests for the SOP agent: choose, plan, confirm, message, finish and memory across runs."""
import json
from unittest.mock import MagicMock

import pytest

from kbase.agent.engine import AgentEngine
from kbase.agent.runs import InMemoryRunStore
from kbase.agent.sop_agent import RunError, RunNotFound, SOPAgent
from kbase.memory.consolidate import MemoryManager
from kbase.memory.inmemory import InMemoryStore

TASK = "private endpoint connection keeps timing out"


@pytest.fixture
def memory():
    return MemoryManager(InMemoryStore())


@pytest.fixture
def agent(offline_kb, memory):
    engine = AgentEngine(offline_kb, memory=memory)
    return SOPAgent(lambda name: engine, InMemoryRunStore(), min_confidence=0.3)


def fake_llm(*replies):
    llm = MagicMock(enabled=True, last_error=None)
    llm.name = "fake"
    llm.complete_json.side_effect = list(replies)
    return llm


def finish_all(agent, run):
    for step in run["checklist"]:
        if step["actor"] == "human" and step["status"] == "pending":
            run = agent.confirm(run["id"], step["id"], "done")
    return agent.finish(run["id"])


class TestStart:
    def test_chooses_and_plans(self, agent):
        run = agent.start(TASK, "siva")
        assert run["status"] == "in_progress" and run["procedure"]["doc_id"] == "KB-0016"
        assert run["search"]["candidates"][0]["confidence"] >= 0.3
        assert run["memory_backend"] == "inmemory"
        kinds = [e["kind"] for e in run["trace"]]
        assert kinds[0] == "memory_recall" and "search" in kinds and "decision" in kinds

    def test_no_match(self, agent):
        run = agent.start("bake a chocolate cake", "siva")
        assert run["status"] == "no_match" and run["checklist"] == []

    def test_no_candidates(self, memory):
        kb = MagicMock()
        kb.run.return_value = {"status": "ok", "results": []}
        a = SOPAgent(lambda n: AgentEngine(kb, memory=memory), InMemoryRunStore())
        assert a.start("anything at all", "u")["status"] == "no_match"

    @pytest.mark.parametrize("task,user,msg", [("hi", "u", "at least"), ("x" * 2001, "u", "at most"),
                                               ("valid task", " ", "user_id")])
    def test_validation(self, agent, task, user, msg):
        with pytest.raises(RunError, match=msg):
            agent.start(task, user)

    def test_task_is_redacted(self, agent):
        run = agent.start(TASK + " password=hunter2", "siva")
        assert "hunter2" not in json.dumps(run)

    def test_llm_choice(self, offline_kb, memory):
        llm = fake_llm({"doc_id": "KB-0002", "reason": "Private endpoints."})
        engine = AgentEngine(offline_kb, memory=memory, llm=llm)
        run = SOPAgent(lambda n: engine, InMemoryRunStore()).start(TASK, "siva")
        assert run["procedure"]["doc_id"] == "KB-0002" and run["procedure"]["reason"] == "Private endpoints."

    def test_llm_says_none(self, offline_kb, memory):
        engine = AgentEngine(offline_kb, memory=memory, llm=fake_llm({"doc_id": None}))
        assert SOPAgent(lambda n: engine, InMemoryRunStore()).start(TASK, "siva")["status"] == "no_match"

    def test_llm_bad_id_falls_back(self, offline_kb, memory):
        engine = AgentEngine(offline_kb, memory=memory, llm=fake_llm({"doc_id": "KB-9999"}))
        run = SOPAgent(lambda n: engine, InMemoryRunStore()).start(TASK, "siva")
        assert run["procedure"]["doc_id"] == "KB-0016"
        assert any(e["kind"] == "llm_fallback" for e in run["trace"])

    def test_runs_without_memory(self, offline_kb):
        engine = AgentEngine(offline_kb, memory_error="not configured")
        run = SOPAgent(lambda n: engine, InMemoryRunStore()).start(TASK, "siva")
        assert run["status"] == "in_progress" and run["memory_backend"] is None
        assert all(s["id"] != "agent-memory" for s in run["checklist"])


class TestDuringRun:
    def test_choose_override(self, agent):
        run = agent.start("bake a chocolate cake", "siva")
        run = agent.choose(run["id"], "KB-0002")
        assert run["status"] == "in_progress" and run["procedure"]["chosen_by"] == "user"

    def test_choose_unknown(self, agent):
        run = agent.start(TASK, "siva")
        with pytest.raises(RunError, match="not found"):
            agent.choose(run["id"], "KB-9999")

    def test_confirm_failed_adds_guidance(self, agent):
        run = agent.start(TASK, "siva")
        run = agent.confirm(run["id"], "step-2", "failed", "needed port 10260 open on the NSG")
        step = next(s for s in run["checklist"] if s["id"] == "step-2")
        assert step["status"] == "failed" and step["guidance"][0].startswith("Known error")

    def test_confirm_rules(self, agent):
        run = agent.start(TASK, "siva")
        with pytest.raises(RunError, match="status"):
            agent.confirm(run["id"], "step-1", "maybe")
        with pytest.raises(RunError, match="agent steps"):
            agent.confirm(run["id"], "agent-review", "done")
        with pytest.raises(RunNotFound):
            agent.confirm(run["id"], "nope", "done")
        with pytest.raises(RunNotFound):
            agent.confirm("missing", "step-1", "done")

    def test_message_learns_fact_and_warns_on_secret(self, agent):
        run = agent.start(TASK, "siva")
        run = agent.message(run["id"], "our cluster is kbase-prod, token: abcdef123456")
        reply = run["messages"][-1]["content"]
        assert "looked like a secret" in reply and "cluster = kbase-prod" in reply
        assert run["learned"] == [{"label": "cluster", "value": "kbase-prod"}]
        assert "abcdef123456" not in json.dumps(run)

    def test_message_question_searches(self, agent):
        run = agent.start(TASK, "siva")
        run = agent.message(run["id"], "how do I configure private DNS zones?")
        assert "articles may help" in run["messages"][-1]["content"]

    def test_message_plain(self, agent):
        run = agent.start(TASK, "siva")
        assert "short term memory" in agent.message(run["id"], "ok")["messages"][-1]["content"]

    def test_message_question_without_hits(self, offline_kb, memory):
        engine = AgentEngine(offline_kb, memory=memory)
        a = SOPAgent(lambda n: engine, InMemoryRunStore())
        run = a.start(TASK, "siva")
        engine.kb = MagicMock(run=MagicMock(return_value={"status": "ok", "results": []}))
        assert "could not find" in a.message(run["id"], "zzzz?")["messages"][-1]["content"]

    def test_llm_fact_extraction(self, offline_kb, memory):
        llm = fake_llm({"doc_id": "KB-0016", "reason": "r"}, {"facts": [{"label": "region", "value": "eastus2"}]})
        engine = AgentEngine(offline_kb, memory=memory, llm=llm)
        a = SOPAgent(lambda n: engine, InMemoryRunStore())
        run = a.message(a.start(TASK, "siva")["id"], "we deploy in East US 2")
        assert run["learned"] == [{"label": "region", "value": "eastus2"}]


class TestFinishAndMemory:
    def test_finish_writes_memory_and_second_run_recalls_it(self, agent, memory):
        run = agent.start(TASK, "siva")
        agent.message(run["id"], "our cluster is kbase-prod")
        run = agent.confirm(run["id"], "step-2", "failed", "needed port 10260 open on the NSG")
        run = finish_all(agent, run)
        assert run["status"] == "completed" and "Learned: cluster = kbase-prod" in run["summary"]
        ops = {(w["type"], w["op"]) for w in run["memory_writes"]}
        assert ops == {("episodic", "ADD"), ("semantic", "ADD"), ("procedural", "ADD")}

        second = agent.start("nc to the private endpoint fails on 10260", "siva")
        recalled = {h["record"]["type"] for h in second["recalled"]}
        assert {"episodic", "semantic", "procedural"} <= recalled
        step2 = next(s for s in second["checklist"] if s["id"] == "step-2")
        assert any("10260" in h for h in step2["hints"])
        assert "run this procedure before" in second["procedure"]["reason"]

        other = agent.start(TASK, "someone-else")
        assert other["recalled"] == []

    def test_fact_update_on_second_run(self, agent):
        r1 = agent.start(TASK, "siva")
        agent.message(r1["id"], "our cluster is kbase-prod")
        finish_all(agent, agent.get(r1["id"]))
        r2 = agent.start(TASK, "siva")
        agent.message(r2["id"], "our cluster is kbase-dr")
        r2 = finish_all(agent, agent.get(r2["id"]))
        assert ("semantic", "UPDATE") in {(w["type"], w["op"]) for w in r2["memory_writes"]}

    def test_abandoned_when_steps_pending(self, agent):
        run = agent.finish(agent.start(TASK, "siva")["id"])
        assert run["status"] == "abandoned"
        with pytest.raises(RunError, match="already"):
            agent.finish(run["id"])
        with pytest.raises(RunError, match="abandoned"):
            agent.confirm(run["id"], "step-1", "done")
        with pytest.raises(RunError, match="finished"):
            agent.choose(run["id"], "KB-0016")

    def test_no_match_finish(self, agent):
        run = agent.finish(agent.start("bake a chocolate cake", "siva")["id"])
        assert run["status"] == "abandoned" and "No procedure" in run["summary"]

    def test_llm_summary(self, offline_kb, memory):
        llm = fake_llm({"doc_id": "KB-0016", "reason": "r"}, {"summary": "All good, password=x"})
        engine = AgentEngine(offline_kb, memory=memory, llm=llm)
        a = SOPAgent(lambda n: engine, InMemoryRunStore())
        run = a.finish(a.start(TASK, "siva")["id"])
        assert run["summary"].startswith("All good") and "password=x" not in run["summary"]

    def test_get_and_list(self, agent):
        run = agent.start(TASK, "siva")
        assert agent.get(run["id"])["id"] == run["id"]
        assert [r["id"] for r in agent.list("siva")] == [run["id"]]
        with pytest.raises(RunNotFound):
            agent.get("missing")
