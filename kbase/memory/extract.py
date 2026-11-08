"""Pull durable facts out of what a person tells the agent.

Heuristics by default. When an LLM is configured the agent can call :func:`llm_facts` instead,
and falls back to the heuristics on any problem.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from kbase.redact import contains_secret, is_secret_name, redact
from kbase.search.offline import tokenize

_OUR_X_IS_Y = re.compile(
    r"\b(?:our|my|the)\s+(?P<label>[a-z][a-z0-9 _-]{1,40}?)(?:\s+(?:is|are)\s+|\s*[=:]\s*)[`'\"]?(?P<value>[A-Za-z0-9][\w./:@-]{1,80})",
    re.I,
)
_ENV_ASSIGN = re.compile(r"\b(?P<label>[A-Z][A-Z0-9_]{2,40})\s*=\s*[`'\"]?(?P<value>[^\s`'\",;]{1,120})")
_REMEMBER = re.compile(r"\bremember(?:\s+that)?[:,]?\s+(?P<value>.{4,300})", re.I)
_TRAILING = re.compile(r"[.,;:!?)\]]+$")


@dataclass(frozen=True)
class Fact:
    label: str
    value: str

    @property
    def text(self) -> str:
        return f"{self.label} = {self.value}"


def _clean(value: str) -> str:
    return _TRAILING.sub("", value.strip())


def _ok(label: str, value: str) -> bool:
    return bool(label) and bool(value) and not is_secret_name(label) and not contains_secret(f"{label}={value}") \
        and not contains_secret(value)


def heuristic_facts(text: str) -> list[Fact]:
    """Facts such as "our cluster is kbase-prod" or "CLUSTER=kbase-prod". Secrets are skipped."""
    if not text:
        return []
    facts: dict[str, Fact] = {}
    for m in _OUR_X_IS_Y.finditer(text):
        label, value = m.group("label").strip().lower(), _clean(m.group("value"))
        if _ok(label, value):
            facts[label] = Fact(label, value)
    for m in _ENV_ASSIGN.finditer(text):
        label, value = m.group("label"), _clean(m.group("value"))
        if _ok(label, value):
            facts[label.lower()] = Fact(label, value)
    for m in _REMEMBER.finditer(text):
        value = _clean(redact(m.group("value")))
        words = tokenize(value)[:4]
        if words and not contains_secret(m.group("value")):
            label = "note " + " ".join(words)
            facts[label] = Fact(label, value)
    return list(facts.values())


FACT_PROMPT = (
    "Extract durable facts the user stated about their environment (names of clusters, projects, "
    "regions, teams, hosts, ports). Never include passwords, keys, tokens or other secrets. Reply "
    'with JSON only: {"facts": [{"label": "<short noun>", "value": "<value>"}]}. Use an empty list '
    "when there are none."
)


def llm_facts(llm: Any, text: str) -> list[Fact] | None:
    """Ask the LLM for facts. Returns ``None`` when the LLM is off or the reply is unusable."""
    if llm is None or not getattr(llm, "enabled", False):
        return None
    data = llm.complete_json(FACT_PROMPT, redact(text))
    if not isinstance(data, dict) or not isinstance(data.get("facts"), list):
        return None
    out = []
    for item in data["facts"]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()[:60]
        value = _clean(str(item.get("value", "")))[:200]
        if _ok(label, value):
            out.append(Fact(label, value))
    return out
