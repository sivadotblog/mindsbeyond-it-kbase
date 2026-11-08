"""Tests for the /api/v2 blueprint and the service container."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pymongo.errors import PyMongoError

from kbase import api as api_module
from kbase.config import Settings
from kbase.container import Container
from kbase.memory.base import MemoryUnavailable

TASK = "private endpoint connection keeps timing out"


@pytest.fixture
def container(articles):
    c = Container(Settings.from_env({"KBASE_MODE": "offline"}), docs=articles)
    api_module.set_container(c)
    yield c
    api_module.set_container(None)


@pytest.fixture
def client(container):
    from app import create_app
    return create_app(testing=True).test_client()


class TestStatus:
    def test_health(self, client):
        body = client.get("/api/v2/health").json
        assert body["mode"] == "offline" and body["memory_backends"] == ["inmemory"]
        assert body["llm"]["provider"] == "offline"

    def test_capabilities_and_facets(self, client):
        assert client.get("/api/v2/capabilities?refresh=true").json["mode"] == "offline"
        assert "Tutorial" in client.get("/api/v2/facets").json["category"]

    def test_methods(self, client):
        assert len(client.get("/api/v2/search/methods").json["methods"]) == 6


class TestSearch:
    def test_search(self, client):
        body = client.post("/api/v2/search", json={"query": "port 10260", "method": "fulltext", "limit": 3}).json
        assert body["status"] == "ok" and body["results"][0]["doc_id"] == "KB-0016"

    def test_default_method_and_options(self, client):
        body = client.post("/api/v2/search", json={
            "query": "private endpoint", "rerank": True, "filters": {"domain": "Networking"},
            "weights": {"vector": 2, "text": 1}, "query_model": "voyage-4", "num_candidates": 200}).json
        assert body["method"] == "hybrid_rrf" and body["reranked"] is True

    @pytest.mark.parametrize("payload,msg", [
        ({"query": ""}, "query is required"),
        ({"query": "x", "limit": "ten"}, "limit must be an integer"),
        ({"query": "x", "weights": {"vector": "heavy"}}, "weights.vector"),
        ({"query": "x", "filters": "Networking"}, "objects"),
        ({"query": "x", "method": "bm99"}, "unknown method"),
    ])
    def test_bad_requests(self, client, payload, msg):
        resp = client.post("/api/v2/search", json=payload)
        assert resp.status_code == 400 and msg in resp.json["error"]

    def test_body_must_be_object(self, client):
        assert client.post("/api/v2/search", json=[1, 2]).status_code == 400

    def test_compare(self, client):
        body = client.post("/api/v2/search/compare", json={"query": "rotate service account keys",
                                                           "methods": ["fulltext", "vector_ann", "vector_enn"]}).json
        assert set(body["results"]) == {"fulltext", "vector_ann", "vector_enn"} and "agreement" in body

    def test_compare_bad_methods(self, client):
        assert client.post("/api/v2/search/compare", json={"query": "x", "methods": "fulltext"}).status_code == 400


class TestAgent:
    def test_full_run(self, client):
        resp = client.post("/api/v2/agent/runs", json={"task": TASK, "user_id": "siva"})
        assert resp.status_code == 201
        run = resp.json
        rid = run["id"]
        assert client.get(f"/api/v2/agent/runs/{rid}").json["id"] == rid
        client.post(f"/api/v2/agent/runs/{rid}/messages", json={"content": "our cluster is kbase-prod"})
        run = client.post(f"/api/v2/agent/runs/{rid}/steps/step-2", json={"status": "failed", "note": "port"}).json
        assert next(s for s in run["checklist"] if s["id"] == "step-2")["guidance"]
        run = client.post(f"/api/v2/agent/runs/{rid}/finish").json
        assert run["status"] == "abandoned" and run["memory_writes"]
        runs = client.get("/api/v2/agent/runs?user_id=siva").json["runs"]
        assert runs[0]["id"] == rid and "trace" not in runs[0]

    def test_choose(self, client):
        rid = client.post("/api/v2/agent/runs", json={"task": "bake a chocolate cake", "user_id": "siva"}).json["id"]
        assert client.post(f"/api/v2/agent/runs/{rid}/choose", json={}).status_code == 400
        assert client.post(f"/api/v2/agent/runs/{rid}/choose", json={"doc_id": "KB-0002"}).json["status"] == "in_progress"

    def test_errors(self, client):
        assert client.get("/api/v2/agent/runs").status_code == 400
        assert client.get("/api/v2/agent/runs/missing").status_code == 404
        assert client.post("/api/v2/agent/runs", json={"task": "x", "user_id": "u"}).status_code == 400


class TestMemory:
    def test_write_list_search_delete(self, client):
        resp = client.post("/api/v2/memory", json={"type": "semantic", "label": "cluster",
                                                   "content": "cluster = kbase-prod", "user_id": "siva",
                                                   "importance": 0.9})
        assert resp.status_code == 201 and resp.json["op"] == "ADD"
        mid = resp.json["id"]
        items = client.get("/api/v2/memory?user_id=siva&type=semantic").json["items"]
        assert items[0]["id"] == mid and items[0]["history"] == []
        hits = client.post("/api/v2/memory/search", json={"query": "cluster", "user_id": "siva"}).json["hits"]
        assert hits[0]["record"]["id"] == mid and set(hits[0]["score_parts"]) == {"relevance", "recency", "importance"}
        assert client.delete(f"/api/v2/memory/{mid}?user_id=siva").json["deleted"] is True
        assert client.delete(f"/api/v2/memory/{mid}?user_id=siva").status_code == 404

    @pytest.mark.parametrize("method,url,payload", [
        ("get", "/api/v2/memory?user_id=siva&type=bogus", None),
        ("get", "/api/v2/memory", None),
        ("post", "/api/v2/memory", {"type": "bogus", "content": "x", "user_id": "u"}),
        ("post", "/api/v2/memory", {"type": "semantic", "content": "x" * 4001, "user_id": "u"}),
        ("post", "/api/v2/memory/search", {"query": "", "user_id": "u"}),
        ("post", "/api/v2/memory/search", {"query": "x", "user_id": "u", "types": ["dreams"]}),
    ])
    def test_bad_requests(self, client, method, url, payload):
        resp = getattr(client, method)(url, json=payload) if payload is not None else getattr(client, method)(url)
        assert resp.status_code == 400

    def test_unknown_backend(self, client):
        resp = client.get("/api/v2/memory?user_id=u&backend=atlas")
        assert resp.status_code == 503 and resp.json["code"] == "memory_unavailable"

    def test_backends_and_setup(self, client):
        backends = client.get("/api/v2/memory/backends").json["backends"]
        assert backends[0]["name"] == "inmemory" and backends[0]["default"] is True
        assert client.post("/api/v2/memory/setup").json["steps"]


class TestErrorMapping:
    def test_unsupported_and_database(self, client, container):
        store = MagicMock()
        store.delete.side_effect = __import__("kbase.memory.base", fromlist=["MemoryUnsupported"]).MemoryUnsupported("no")
        container._stores["inmemory"] = store
        assert client.delete("/api/v2/memory/x?user_id=u").status_code == 501
        store.list.side_effect = PyMongoError("down")
        assert client.get("/api/v2/memory?user_id=u").status_code == 503

    def test_backend_listing_reports_errors(self, client, container):
        container._stores["inmemory"] = MagicMock(describe=MagicMock(side_effect=RuntimeError("x")))
        assert client.get("/api/v2/memory/backends").json["backends"][0]["error"] == "x"


class TestContainer:
    def test_atlas_mode_wires_mongo(self):
        client = MagicMock()
        c = Container(Settings.from_env({"MONGODB_URI": "mongodb+srv://h"}), client=client)
        assert c.memory_backends == ["atlas", "inmemory"] and c.default_memory_backend == "atlas"
        assert c.runs.name == "atlas" and c.store("atlas").name == "atlas"
        assert c.health()["runs_store"] == "atlas"

    def test_default_backend_falls_back(self, articles):
        c = Container(Settings.from_env({"KBASE_MODE": "offline", "MEMORY_BACKEND": "atlas"}), docs=articles)
        assert c.default_memory_backend == "inmemory"

    def test_agent_engine_backend(self, articles):
        memory = MagicMock()
        memory.bind.return_value.save_semantic.return_value = SimpleNamespace(id="s1")
        c = Container(Settings.from_env({"KBASE_MODE": "offline", "AGENTIC_MEMORY_PROJECT_ID": "p",
                                         "AGENTIC_MEMORY_SERVICE_ACCOUNT_TOKEN": "t",
                                         "MEMORY_BACKEND": "agent_engine"}),
                      docs=articles, agent_engine_factory=lambda token, project, base: memory)
        assert c.default_memory_backend == "agent_engine"
        assert c.manager().remember_fact("u", "a", "b").op in ("ADD", "UPDATE", "NOOP")

    def test_engine_without_memory(self, articles):
        c = Container(Settings.from_env({"KBASE_MODE": "offline"}), docs=articles)
        engine = c.engine_for("atlas")
        assert engine.memory is None and "not configured" in engine.memory_error
        assert "atlas" in c.memory_errors
        with pytest.raises(MemoryUnavailable):
            c.store("agent_engine")

    def test_lazy_client(self, monkeypatch):
        created = {}

        class FakeClient(dict):
            def __init__(self, uri, **kw):
                created["uri"] = uri
                super().__init__()

            def __getitem__(self, name):
                return MagicMock()

        monkeypatch.setattr("pymongo.MongoClient", FakeClient)
        c = Container(Settings.from_env({"MONGODB_URI": "mongodb+srv://h"}))
        assert created["uri"] == "mongodb+srv://h" and c.kb is not None

    def test_get_container_builds_once(self, monkeypatch, articles):
        api_module.set_container(None)
        monkeypatch.setenv("KBASE_MODE", "offline")
        a = api_module.get_container()
        assert api_module.get_container() is a
        api_module.set_container(None)
