"""Settings read from environment variables.

Every setting has a default so the app starts with no configuration at all (offline mode).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping

VALID_MODES = ("auto", "atlas", "offline")
VALID_LLM_PROVIDERS = ("offline", "anthropic", "openai")
VALID_MEMORY_BACKENDS = ("auto", "atlas", "agent_engine", "inmemory")
VALID_QUERY_FORMATS = ("object", "string")


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a number, got {raw!r}") from exc


def _choice(env: Mapping[str, str], key: str, default: str, valid: tuple[str, ...]) -> str:
    value = (env.get(key) or default).strip().lower()
    if value not in valid:
        raise ValueError(f"{key} must be one of {', '.join(valid)}, got {value!r}")
    return value


@dataclass(frozen=True)
class Settings:
    """Runtime configuration. Build with :meth:`from_env`."""

    mongodb_uri: str | None = None
    mode: str = "offline"
    db_name: str = "kbase"
    collection_name: str = "content"
    md_dir: str = "md_docs"

    text_index: str = "fulltext_index"
    vector_index: str = "auto_embedding_index"
    vector_path: str = "raw_markdown"
    index_model: str = "voyage-4"
    query_model: str = "voyage-4-lite"
    query_format: str = "object"
    rerank_model: str = "rerank-2.5-lite"

    llm_provider: str = "offline"
    llm_model: str = "claude-sonnet-5-5"
    llm_api_key: str | None = field(default=None, repr=False)
    llm_base_url: str | None = None
    llm_auth_header: str = "Authorization"
    llm_timeout: float = 30.0

    memory_backend: str = "auto"
    memory_collection: str = "agent_memory"
    runs_collection: str = "agent_runs"
    memory_vector_index: str = "memory_vector_index"
    memory_text_index: str = "memory_text_index"
    memory_model: str = "voyage-4"
    stm_ttl_hours: float = 24.0
    memory_half_life_hours: float = 168.0
    memory_weights: tuple[float, float, float] = (0.6, 0.2, 0.2)

    agentic_memory_project_id: str | None = None
    agentic_memory_token: str | None = field(default=None, repr=False)
    agentic_memory_base_url: str | None = None
    agent_engine_token_url: str = "https://agentengine.mongodb.com/api/v1/oauth/token"
    mdb_client: str | None = None
    mdb_secret: str | None = field(default=None, repr=False)

    sop_min_score: float = 0.3

    @property
    def offline(self) -> bool:
        return self.mode == "offline"

    @property
    def llm_enabled(self) -> bool:
        return self.llm_provider != "offline" and bool(self.llm_api_key)

    @property
    def agent_engine_configured(self) -> bool:
        has_auth = bool(self.agentic_memory_token) or bool(self.mdb_client and self.mdb_secret)
        return bool(self.agentic_memory_project_id) and has_auth

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        uri = (env.get("MONGODB_URI") or "").strip() or None
        mode = _choice(env, "KBASE_MODE", "auto", VALID_MODES)
        if mode == "auto":
            mode = "atlas" if uri else "offline"
        if mode == "atlas" and not uri:
            raise ValueError("KBASE_MODE=atlas needs MONGODB_URI")

        weights = (
            _float(env, "MEMORY_WEIGHT_RELEVANCE", 0.6),
            _float(env, "MEMORY_WEIGHT_RECENCY", 0.2),
            _float(env, "MEMORY_WEIGHT_IMPORTANCE", 0.2),
        )
        if any(w < 0 for w in weights) or sum(weights) == 0:
            raise ValueError("memory weights must be non negative and not all zero")

        return cls(
            mongodb_uri=uri,
            mode=mode,
            db_name=env.get("DB_NAME", "kbase"),
            collection_name=env.get("COLLECTION_NAME", "content"),
            md_dir=env.get("KBASE_MD_DIR", "md_docs"),
            text_index=env.get("KBASE_TEXT_INDEX", "fulltext_index"),
            vector_index=env.get("KBASE_VECTOR_INDEX", "auto_embedding_index"),
            vector_path=env.get("KBASE_VECTOR_PATH", "raw_markdown"),
            index_model=env.get("KBASE_INDEX_MODEL", "voyage-4"),
            query_model=env.get("KBASE_QUERY_MODEL", "voyage-4-lite"),
            query_format=_choice(env, "KBASE_QUERY_FORMAT", "object", VALID_QUERY_FORMATS),
            rerank_model=env.get("KBASE_RERANK_MODEL", "rerank-2.5-lite"),
            llm_provider=_choice(env, "LLM_PROVIDER", "offline", VALID_LLM_PROVIDERS),
            llm_model=env.get("LLM_MODEL", "claude-sonnet-5-5"),
            llm_api_key=(env.get("LLM_API_KEY") or "").strip() or None,
            llm_base_url=(env.get("LLM_BASE_URL") or "").strip() or None,
            llm_auth_header=env.get("LLM_AUTH_HEADER", "Authorization"),
            llm_timeout=_float(env, "LLM_TIMEOUT", 30.0),
            memory_backend=_choice(env, "MEMORY_BACKEND", "auto", VALID_MEMORY_BACKENDS),
            memory_collection=env.get("MEMORY_COLLECTION", "agent_memory"),
            runs_collection=env.get("RUNS_COLLECTION", "agent_runs"),
            memory_vector_index=env.get("MEMORY_VECTOR_INDEX", "memory_vector_index"),
            memory_text_index=env.get("MEMORY_TEXT_INDEX", "memory_text_index"),
            memory_model=env.get("MEMORY_MODEL", "voyage-4"),
            stm_ttl_hours=_float(env, "STM_TTL_HOURS", 24.0),
            memory_half_life_hours=_float(env, "MEMORY_HALF_LIFE_HOURS", 168.0),
            memory_weights=weights,
            agentic_memory_project_id=(env.get("AGENTIC_MEMORY_PROJECT_ID") or "").strip() or None,
            agentic_memory_token=(env.get("AGENTIC_MEMORY_SERVICE_ACCOUNT_TOKEN") or "").strip() or None,
            agentic_memory_base_url=(env.get("AGENTIC_MEMORY_BASE_URL") or "").strip() or None,
            agent_engine_token_url=env.get(
                "AGENT_ENGINE_TOKEN_URL", "https://agentengine.mongodb.com/api/v1/oauth/token"
            ),
            mdb_client=(env.get("MDB_CLIENT") or "").strip() or None,
            mdb_secret=(env.get("MDB_SECRET") or "").strip() or None,
            sop_min_score=_float(env, "SOP_MIN_SCORE", 0.3),
        )
