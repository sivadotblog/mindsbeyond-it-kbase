"""Adapter for the Atlas Agent Engine memory service (public preview).

Uses the ``agent-engine-sdk-memory`` package (``pip install -e ".[agent-engine]"``). The SDK is
imported lazily so the rest of the app works without it.

Auth: a service account access token. Either set ``AGENTIC_MEMORY_SERVICE_ACCOUNT_TOKEN`` or give
``MDB_CLIENT`` and ``MDB_SECRET``, which are exchanged for a one hour token at the Agent Engine
OAuth endpoint and refreshed before they expire.

Mapping to the five memory types:

==========  ==============================================
stm         ``record_turn`` (short term memory)
semantic    ``save_semantic`` / ``get_semantic``
episodic    ``save_episode`` / ``list_episodes``
procedural  ``save_procedure`` / ``get_procedure``
taxonomic   ``save_taxonomic`` / ``get_taxonomic_term``
==========  ==============================================

Agent Engine runs its own extraction in the background, so facts may also appear that this app
never wrote. The SDK has no delete, so delete raises :class:`MemoryUnsupported`.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any, Callable

import requests

from kbase.memory.base import MemoryUnavailable, MemoryUnsupported
from kbase.memory.models import MemoryRecord, RecallResult, utcnow
from kbase.memory.scoring import score_records

TAXONOMY_DOMAIN = "mindsbeyond-kbase"


class TokenProvider:
    """Returns a valid bearer token, minting one from client credentials when needed."""

    def __init__(self, *, token: str | None = None, client_id: str | None = None,
                 client_secret: str | None = None, token_url: str = "",
                 session: Any = None, clock: Callable[[], float] = time.time):
        if not token and not (client_id and client_secret):
            raise MemoryUnavailable("Agent Engine needs a token or MDB_CLIENT and MDB_SECRET")
        self._static = token
        self._client_id = client_id
        self._client_secret = client_secret
        self._url = token_url
        self._session = session or requests.Session()
        self._clock = clock
        self._token: str | None = None
        self._expires = 0.0
        self._lock = threading.Lock()

    def __call__(self) -> str:
        if self._static:
            return self._static
        with self._lock:
            if self._token and self._clock() < self._expires - 60:
                return self._token
            resp = self._session.post(self._url, auth=(self._client_id, self._client_secret),
                                      data={"grant_type": "client_credentials"}, timeout=20)
            if resp.status_code != 200:
                raise MemoryUnavailable(f"Agent Engine token request failed with HTTP {resp.status_code}")
            body = resp.json()
            self._token = body["access_token"]
            self._expires = self._clock() + float(body.get("expires_in", 3600))
            return self._token


def _default_factory(token: str, project_id: str, base_url: str | None) -> Any:
    try:
        from agent_engine_sdk_memory import Memory  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise MemoryUnavailable(
            'agent-engine-sdk-memory is not installed; run pip install -e ".[agent-engine]"'
        ) from exc
    kwargs: dict[str, Any] = {"service_account_token": token, "project_id": project_id}
    if base_url:
        kwargs["base_url"] = base_url
    return Memory(**kwargs)


def _context(user_id: str, session_id: str | None, agent_id: str | None) -> Any:
    try:
        from agent_engine_sdk_memory import MemoryRequestContext  # type: ignore[import-not-found]
    except ImportError:  # the fake SDK in tests accepts a plain dict
        return {"user_id": user_id, "session_id": session_id, "agent_id": agent_id}
    return MemoryRequestContext(user_id=user_id, session_id=session_id, agent_id=agent_id)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class AgentEngineMemoryStore:
    name = "agent_engine"
    capabilities = {"delete": False, "update": True, "list": True}

    def __init__(self, *, project_id: str, token_provider: Callable[[], str], base_url: str | None = None,
                 memory_factory: Callable[[str, str, str | None], Any] = _default_factory,
                 context_factory: Callable[[str, str | None, str | None], Any] = _context,
                 agent_id: str = "sop-agent", weights: tuple[float, float, float] = (0.6, 0.2, 0.2),
                 half_life_hours: float = 168.0):
        self.project_id = project_id
        self._token = token_provider
        self._base_url = base_url
        self._factory = memory_factory
        self._context = context_factory
        self.agent_id = agent_id
        self.weights = weights
        self.half_life_hours = half_life_hours
        self._memory: Any = None
        self._memory_token: str | None = None

    def _client(self) -> Any:
        token = self._token()
        if self._memory is None or token != self._memory_token:
            self._memory = self._factory(token, self.project_id, self._base_url)
            self._memory_token = token
        return self._memory

    def _bound(self, user_id: str, session_id: str | None = None) -> Any:
        return self._client().bind(self._context(user_id, session_id, self.agent_id))

    # -- writes ----------------------------------------------------------------
    def write(self, record: MemoryRecord) -> MemoryRecord:
        source = record.source or {}
        session_id = source.get("run_id")
        mem = self._bound(record.user_id, session_id)
        meta = {"importance": record.importance, "app_id": record.id}
        if record.type == "stm":
            result = mem.record_turn(role=source.get("role", "user"), content=record.content,
                                     session_id=session_id, metadata=meta)
        elif record.type == "semantic":
            result = mem.save_semantic(text=record.content, label=record.label or record.content[:60],
                                       visibility=record.visibility, metadata=meta)
        elif record.type == "episodic":
            result = mem.save_episode(title=record.label or "SOP run", content=record.content,
                                      summary=record.content[:500], session_id=session_id or record.id,
                                      tags=[t for t in (source.get("doc_id"),) if t],
                                      visibility=record.visibility, metadata=meta)
        elif record.type == "procedural":
            result = mem.save_procedure(procedure=record.label or record.id, description=record.content[:200],
                                        content=record.content, tags=[t for t in (source.get("doc_id"),) if t],
                                        visibility=record.visibility, metadata=meta)
        else:
            result = mem.save_taxonomic(domain=TAXONOMY_DOMAIN, term=record.label or record.content[:40],
                                        definition=record.content, visibility=record.visibility)
        remote_id = _get(result, "id")
        if remote_id:
            record.id = str(remote_id)
        return record

    def update(self, record: MemoryRecord) -> MemoryRecord:
        """The hosted API is create only, so an update saves a new version under the same label."""
        return self.write(record)

    # -- reads -----------------------------------------------------------------
    def find_by_label(self, user_id: str, type_: str, label: str) -> MemoryRecord | None:
        mem = self._bound(user_id)
        if type_ == "semantic":
            item = mem.get_semantic(label)
        elif type_ == "procedural":
            item = mem.get_procedure(label)
        else:
            return None
        if not item:
            return None
        content = _get(item, "text") or _get(item, "content") or ""
        if not content:
            return None
        return MemoryRecord(type=type_, user_id=user_id, content=content, label=label,
                            id=str(_get(item, "id") or _get(item, "_id") or label))

    def _chunk_to_record(self, chunk: Any, user_id: str) -> MemoryRecord:
        source = _get(chunk, "source")
        type_ = getattr(source, "value", source) or "semantic"
        meta = _get(chunk, "metadata") or {}
        user_meta = meta.get("metadata", {}) if isinstance(meta, dict) else {}
        ts = _get(chunk, "timestamp") or utcnow()
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        label = meta.get("label") or meta.get("title") or meta.get("procedure") or meta.get("term") \
            if isinstance(meta, dict) else None
        return MemoryRecord(
            type=type_ if type_ in ("stm", "episodic", "semantic", "procedural", "taxonomic") else "semantic",
            user_id=user_id, content=_get(chunk, "content") or "(empty)", label=label,
            importance=float(user_meta.get("importance", 0.5)), id=str(_get(chunk, "id") or ""),
            created_at=ts, updated_at=ts,
        )

    def list(self, user_id: str, type_: str | None = None, limit: int = 50) -> list[MemoryRecord]:
        mem = self._bound(user_id)
        records: list[MemoryRecord] = []
        if type_ in (None, "episodic"):
            for ep in mem.list_episodes(limit=limit) or []:
                ts = _get(ep, "created_at") or _get(ep, "timestamp") or utcnow()
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                records.append(MemoryRecord(
                    type="episodic", user_id=user_id,
                    content=_get(ep, "content") or _get(ep, "summary_text") or _get(ep, "title") or "(episode)",
                    label=_get(ep, "title"), id=str(_get(ep, "id") or _get(ep, "_id") or ""),
                    created_at=ts, updated_at=ts))
        if type_ != "episodic":
            sources = [type_] if type_ and type_ != "stm" else ["semantic", "procedural", "taxonomic"]
            for chunk in mem.search("memory", sources=sources, top_k=limit) or []:
                records.append(self._chunk_to_record(chunk, user_id))
        return records[:limit]

    def recall(self, query: str, user_id: str, types: tuple[str, ...], limit: int = 8) -> RecallResult:
        start = time.perf_counter()
        sources = [t for t in types if t != "stm"] or ["semantic", "episodic"]
        chunks = self._bound(user_id).search(query, sources=sources, top_k=limit * 2) or []
        scored = [(self._chunk_to_record(c, user_id), float(_get(c, "similarity_score") or 0.0)) for c in chunks]
        hits = score_records(scored, weights=self.weights, half_life_hours=self.half_life_hours)[:limit]
        return RecallResult(
            backend=self.name, strategy="Agent Engine Memory.search (server side hybrid retrieval)",
            hits=hits, pipeline=[{"sdk": "Memory.search", "query": query, "sources": sources,
                                  "top_k": limit * 2}],
            ms=round((time.perf_counter() - start) * 1000, 1),
        )

    def delete(self, memory_id: str, user_id: str) -> bool:
        raise MemoryUnsupported("The Atlas Agent Engine memory SDK has no delete operation")

    def setup(self) -> list[str]:
        return ["Agent Engine manages its own memory indexes. Configure extraction with "
                "`agentengine memory configure` and `agentengine memory apply --wait`."]

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "capabilities": self.capabilities, "persistent": True,
                "project_id": self.project_id, "note": "Atlas Agent Engine memory, public preview"}

