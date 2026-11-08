"""Tests for the live smoke checks with fakes."""
from unittest.mock import MagicMock

import pytest

from kbase.config import Settings
from kbase.container import Container
from kbase.smoke import (
    Check,
    agent_checks,
    cleanup_memory,
    main,
    memory_checks,
    render,
    search_checks,
    wait_for_connection,
    wait_for_indexes,
)


def fake_kb(status_for=None):
    status_for = status_for or {}

    def run(method, params):
        key = f"{method}{'+r' if params.rerank else ''}"
        status = status_for.get(key, "ok")
        if status == "ok":
            return {"status": "ok", "results": [{"doc_id": "KB-0016"}], "ms": 5, "warnings": []}
        if status == "miss":
            return {"status": "ok", "results": [{"doc_id": "KB-0001"}], "ms": 5, "warnings": ["w"]}
        return {"status": status, "reason": "needs 8.3", "results": [], "ms": 1}
    kb = MagicMock()
    kb.run.side_effect = run
    return kb


def test_search_checks_statuses():
    checks = search_checks(fake_kb({"hybrid_score": "unsupported", "fulltext": "error", "vector_ann+r": "miss"}))
    by = {c.name: c for c in checks}
    assert by["hybrid_score"].status == "unsupported" and by["fulltext"].status == "fail"
    assert by["vector_ann + rerank"].status == "fail" and "not in top 5" in by["vector_ann + rerank"].detail
    assert by["hybrid_rrf"].status == "pass" and len(checks) == 8


@pytest.fixture
def container(articles):
    return Container(Settings.from_env({"KBASE_MODE": "offline"}), docs=articles)


def test_memory_and_agent_checks(container):
    checks = memory_checks(container, wait_seconds=0, sleep=lambda s: None)
    assert [c.status for c in checks] == ["pass", "pass"]
    assert container.store().list("live-smoke") == []
    checks = agent_checks(container)
    assert checks[0].status == "pass" and checks[1].status == "pass"
    assert cleanup_memory(container.manager()) >= 1


def test_memory_checks_unavailable_backend(container):
    assert memory_checks(container, backend="atlas")[0].status == "skipped"


def test_memory_write_failure(container):
    container._managers["inmemory"] = MagicMock(remember_fact=MagicMock(side_effect=RuntimeError("down")))
    assert memory_checks(container)[0].status == "fail"


def test_memory_recall_miss(container):
    manager = MagicMock()
    manager.recall.return_value = MagicMock(hits=[], strategy="s", ms=1)
    container._managers["inmemory"] = manager
    assert memory_checks(container, wait_seconds=0)[-1].status == "fail"


def test_agent_failures():
    c = MagicMock()
    c.agent.start.side_effect = RuntimeError("x")
    assert agent_checks(c)[0].status == "fail"
    c.agent.start.side_effect = None
    c.agent.start.return_value = {"id": "r", "status": "no_match", "procedure": None, "search": {"method": None}}
    c.agent.finish.side_effect = RuntimeError("y")
    out = agent_checks(c)
    assert out[0].status == "fail" and out[1].status == "fail"


def test_cleanup_tolerates_errors():
    manager = MagicMock()
    manager.store.list.side_effect = RuntimeError("no list")
    assert cleanup_memory(manager) == 0


def test_render():
    caps = {"mode": "atlas", "server_version": "8.3.1", "query_format": "object",
            "indexes": [{"name": "fulltext_index", "type": "search", "status": "READY", "queryable": True}]}
    text = render(caps, [Check("a", "pass", "x|y", 3.0), Check("b", "unsupported"), Check("c", "skipped")])
    assert "| a | PASS | x/y | 3.0 |" in text and "1 passed, 0 failed, 1 unsupported, 1 skipped." in text


def test_wait_for_indexes():
    coll = MagicMock()
    coll.name = "content"
    coll.list_search_indexes.side_effect = [[{"name": "i", "queryable": False, "status": "BUILDING"}],
                                            [{"name": "i", "queryable": True}]]
    assert wait_for_indexes([coll], 100, sleep=lambda s: None) == []
    coll.list_search_indexes.side_effect = None
    coll.list_search_indexes.return_value = [{"name": "i", "queryable": False, "status": "BUILDING"}]
    ticks = iter([0, 200])
    assert wait_for_indexes([coll], 100, sleep=lambda s: None, clock=lambda: next(ticks)) == ["content.i (BUILDING)"]


def test_wait_for_connection():
    client = MagicMock()
    client.admin.command.side_effect = [RuntimeError("not yet"), {"ok": 1}]
    wait_for_connection(client, sleep=lambda s: None)
    client.admin.command.side_effect = RuntimeError("never")
    ticks = iter([0, 500])
    with pytest.raises(RuntimeError):
        wait_for_connection(client, timeout=10, sleep=lambda s: None, clock=lambda: next(ticks))


def test_main_refuses_offline(container):
    assert main(["run"], container_factory=lambda: container) == 2


def test_main_run_writes_report(tmp_path):
    c = MagicMock()
    c.settings.offline = False
    c.kb = fake_kb()
    c.kb.capabilities.return_value = {"mode": "atlas"}
    c.memory_backends = ["atlas", "inmemory"]
    c.manager.return_value.recall.return_value = MagicMock(hits=[1], strategy="s", ms=1)
    c.agent.start.return_value = {"id": "r", "status": "in_progress", "procedure": {"doc_id": "KB-0016"},
                                  "search": {"method": "hybrid_rrf"}}
    c.agent.finish.return_value = {"memory_writes": [1]}
    report = tmp_path / "r.md"
    assert main(["run", "--report", str(report)], container_factory=lambda: c) == 0
    assert "Live smoke report" in report.read_text()


def test_main_setup_skip_seed():
    c = MagicMock()
    c.settings.offline = False
    c.store.return_value.setup.return_value = ["ok"]
    c.db.__getitem__.return_value.list_search_indexes.return_value = []
    assert main(["setup", "--skip-seed", "--wait", "0"], container_factory=lambda: c) == 0
