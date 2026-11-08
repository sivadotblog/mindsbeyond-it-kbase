"""Tests for Settings.from_env."""
import pytest

from kbase.config import Settings


def test_defaults_are_offline():
    s = Settings.from_env({})
    assert s.mode == "offline" and s.offline and s.llm_provider == "offline"
    assert s.text_index == "fulltext_index" and s.query_format == "object"


def test_auto_mode_uses_atlas_with_uri():
    assert Settings.from_env({"MONGODB_URI": "mongodb+srv://x"}).mode == "atlas"


def test_explicit_offline_wins_over_uri():
    assert Settings.from_env({"MONGODB_URI": "mongodb+srv://x", "KBASE_MODE": "offline"}).mode == "offline"


def test_atlas_mode_needs_uri():
    with pytest.raises(ValueError, match="MONGODB_URI"):
        Settings.from_env({"KBASE_MODE": "atlas"})


def test_invalid_choice():
    with pytest.raises(ValueError, match="LLM_PROVIDER"):
        Settings.from_env({"LLM_PROVIDER": "gpt"})


def test_bad_number():
    with pytest.raises(ValueError, match="STM_TTL_HOURS"):
        Settings.from_env({"STM_TTL_HOURS": "soon"})


def test_bad_weights():
    with pytest.raises(ValueError, match="weights"):
        Settings.from_env({"MEMORY_WEIGHT_RELEVANCE": "0", "MEMORY_WEIGHT_RECENCY": "0",
                           "MEMORY_WEIGHT_IMPORTANCE": "0"})


def test_llm_enabled_needs_key():
    assert not Settings.from_env({"LLM_PROVIDER": "anthropic"}).llm_enabled
    assert Settings.from_env({"LLM_PROVIDER": "anthropic", "LLM_API_KEY": "k"}).llm_enabled


def test_agent_engine_configured():
    assert not Settings.from_env({"AGENTIC_MEMORY_PROJECT_ID": "p"}).agent_engine_configured
    assert Settings.from_env({"AGENTIC_MEMORY_PROJECT_ID": "p", "MDB_CLIENT": "c",
                              "MDB_SECRET": "s"}).agent_engine_configured
    assert Settings.from_env({"AGENTIC_MEMORY_PROJECT_ID": "p",
                              "AGENTIC_MEMORY_SERVICE_ACCOUNT_TOKEN": "t"}).agent_engine_configured


def test_secrets_not_in_repr():
    s = Settings.from_env({"MDB_SECRET": "mdb_sa_sk_123", "LLM_API_KEY": "sk-ant-xyz"})
    assert "mdb_sa_sk_123" not in repr(s) and "sk-ant-xyz" not in repr(s)
