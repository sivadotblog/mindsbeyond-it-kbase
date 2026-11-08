"""Builds the services from settings, once, and hands them to the API."""
from __future__ import annotations

import threading
from typing import Any

from kbase.agent.engine import AgentEngine
from kbase.agent.llm import LLM, make_llm
from kbase.agent.runs import InMemoryRunStore, MongoRunStore
from kbase.agent.sop_agent import SOPAgent
from kbase.config import Settings
from kbase.memory.agent_engine import AgentEngineMemoryStore, TokenProvider
from kbase.memory.atlas import AtlasMemoryStore
from kbase.memory.base import MemoryUnavailable
from kbase.memory.consolidate import MemoryManager
from kbase.memory.inmemory import InMemoryStore
from kbase.search.docs import load_articles
from kbase.search.offline import OfflineSearchService
from kbase.search.pipelines import IndexConfig
from kbase.search.service import SearchService


class Container:
    def __init__(self, settings: Settings | None = None, *, client: Any = None, llm: LLM | None = None,
                 docs: list[dict[str, Any]] | None = None, agent_engine_factory: Any = None):
        self.settings = settings or Settings.from_env()
        s = self.settings
        self.index = IndexConfig(s.text_index, s.vector_index, s.vector_path, s.query_format)
        self._client = client
        self._lock = threading.Lock()
        self._stores: dict[str, Any] = {}
        self._managers: dict[str, MemoryManager] = {}
        self.memory_errors: dict[str, str] = {}
        self._agent_engine_factory = agent_engine_factory
        common = {"default_query_model": s.query_model, "default_rerank_model": s.rerank_model}
        if s.offline:
            self.kb = OfflineSearchService(docs if docs is not None else load_articles(s.md_dir), self.index, **common)
            self.runs: Any = InMemoryRunStore()
        else:
            self.kb = SearchService(self.db[s.collection_name], self.index, **common)
            self.runs = MongoRunStore(self.db[s.runs_collection])
        self.llm = llm or make_llm(s)
        self.agent = SOPAgent(self.engine_for, self.runs, min_confidence=s.sop_min_score,
                              default_backend=self.default_memory_backend)

    # -- database -------------------------------------------------------------------
    @property
    def client(self) -> Any:
        if self._client is None:
            from pymongo import MongoClient
            self._client = MongoClient(self.settings.mongodb_uri, appname="mindsbeyond-kb-lab",
                                       serverSelectionTimeoutMS=8000)
        return self._client

    @property
    def db(self) -> Any:
        return self.client[self.settings.db_name]

    # -- memory ---------------------------------------------------------------------
    @property
    def memory_backends(self) -> list[str]:
        names = ["inmemory"]
        if not self.settings.offline:
            names.insert(0, "atlas")
        if self.settings.agent_engine_configured:
            names.append("agent_engine")
        return names

    @property
    def default_memory_backend(self) -> str:
        wanted = self.settings.memory_backend
        if wanted == "auto":
            return "inmemory" if self.settings.offline else "atlas"
        return wanted if wanted in self.memory_backends else "inmemory"

    def store(self, name: str | None = None) -> Any:
        name = name or self.default_memory_backend
        if name not in self.memory_backends:
            raise MemoryUnavailable(f"memory backend {name!r} is not configured; available: "
                                    f"{', '.join(self.memory_backends)}")
        with self._lock:
            if name not in self._stores:
                self._stores[name] = self._build_store(name)
            return self._stores[name]

    def _build_store(self, name: str) -> Any:
        s = self.settings
        common = {"weights": s.memory_weights, "half_life_hours": s.memory_half_life_hours}
        if name == "inmemory":
            return InMemoryStore(**common)
        if name == "atlas":
            return AtlasMemoryStore(self.db[s.memory_collection], vector_index=s.memory_vector_index,
                                    text_index=s.memory_text_index, model=s.memory_model, **common)
        tokens = TokenProvider(token=s.agentic_memory_token, client_id=s.mdb_client,
                               client_secret=s.mdb_secret, token_url=s.agent_engine_token_url)
        kwargs: dict[str, Any] = {"project_id": s.agentic_memory_project_id, "token_provider": tokens,
                                  "base_url": s.agentic_memory_base_url, **common}
        if self._agent_engine_factory is not None:
            kwargs["memory_factory"] = self._agent_engine_factory
        return AgentEngineMemoryStore(**kwargs)

    def manager(self, name: str | None = None) -> MemoryManager:
        name = name or self.default_memory_backend
        if name not in self._managers:
            self._managers[name] = MemoryManager(self.store(name), stm_ttl_hours=self.settings.stm_ttl_hours)
        return self._managers[name]

    def engine_for(self, name: str | None = None) -> AgentEngine:
        try:
            memory = self.manager(name)
            error = None
        except MemoryUnavailable as exc:
            memory, error = None, str(exc)
            self.memory_errors[name or self.default_memory_backend] = error
        return AgentEngine(self.kb, memory=memory, llm=self.llm, memory_error=error)

    # -- report ---------------------------------------------------------------------
    def health(self) -> dict[str, Any]:
        return {
            "mode": self.settings.mode,
            "llm": self.llm.describe(),
            "memory_backends": self.memory_backends,
            "default_memory_backend": self.default_memory_backend,
            "memory_errors": self.memory_errors,
            "memory_weights": list(self.settings.memory_weights),
            "runs_store": self.runs.name,
            "index": {"text": self.index.text_index, "vector": self.index.vector_index,
                      "path": self.index.vector_path, "query_format": self.index.query_format,
                      "index_model": self.settings.index_model, "query_model": self.settings.query_model,
                      "rerank_model": self.settings.rerank_model},
        }
