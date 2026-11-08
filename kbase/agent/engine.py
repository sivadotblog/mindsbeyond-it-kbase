"""A small agent engine: read only tools, memory hooks, an optional LLM and a trace.

The engine never runs shell commands. Every tool here only reads (search, read an article,
recall memory, explain a command). Writing memory goes through :meth:`remember`, which records the
consolidation decision in the trace.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any, Callable

from kbase.agent.llm import LLM, OfflineLLM
from kbase.agent.trace import Trace
from kbase.memory.consolidate import MemoryManager, WriteOutcome
from kbase.memory.models import LONG_TERM_TYPES, RecallResult
from kbase.redact import is_secret_name
from kbase.search.pipelines import SearchParams

SEARCH_CHAIN: tuple[tuple[str, bool], ...] = (
    ("hybrid_rrf", True),
    ("hybrid_rrf", False),
    ("vector_ann", False),
    ("fulltext", False),
)

TOOL_NAMES = {
    "az": "Azure CLI", "terraform": "Terraform", "curl": "an HTTP request with curl",
    "mongosh": "the MongoDB Shell", "gh": "the GitHub CLI", "kubectl": "kubectl",
    "databricks": "the Databricks CLI", "python": "a Python script", "nc": "a netcat port check",
    "nslookup": "a DNS lookup", "dig": "a DNS lookup", "cypher-shell": "the Neo4j shell",
    "datadog-cli": "the Datadog CLI", "atlas": "the Atlas CLI", "npx": "a Node.js tool",
    "node": "a Node.js script", "spark-submit": "a Spark job", "echo": "a shell echo",
    "pytest": "a pytest run", "mongodump": "mongodump", "mongorestore": "mongorestore",
    "snowflake-cli": "the Snowflake CLI", "openapi-diff": "an OpenAPI diff",
}
_CHANGES = re.compile(r"\b(apply|create|update|delete|destroy|install|register|set|upload|submit|"
                      r"rotate|restore|import|enable|patch|post|put)\b|-auto-approve|-X\s+(POST|PATCH|PUT|DELETE)",
                      re.I)
_READS = re.compile(r"\b(show|list|get|status|plan|view|test|check|verify|tail|describe|stats|eval)\b|-X\s+GET",
                    re.I)
_CURL_WRITE = re.compile(r"\s(-d|-F|-T|--data\S*|--form|--upload-file)\b")
READ_TOOLS = frozenset({"nc", "nslookup", "dig", "echo", "cat", "ls", "ping"})
_VAR = re.compile(r"\$\{?([A-Z][A-Z0-9_]*)\}?")


def command_variables(command: str) -> list[str]:
    return sorted(set(_VAR.findall(command or "")))


def explain_command(command: str) -> str:
    """Plain words for what a command does. Deterministic, no model needed."""
    if not command:
        return ""
    parts = []
    for line in command.splitlines():
        tool = line.strip().split()[0] if line.strip() else ""
        tool = tool.split("/")[-1]
        name = TOOL_NAMES.get(tool, f"the {tool} command" if tool else "a command")
        if _CHANGES.search(line):
            effect = "changes state"
        elif tool in READ_TOOLS or _READS.search(line) or (tool == "curl" and not _CURL_WRITE.search(line)):
            effect = "reads state"
        else:
            effect = "effect not obvious, read it before running"
        parts.append(f"Runs {name} ({effect}).")
    variables = command_variables(command)
    if variables:
        secret = [v for v in variables if is_secret_name(v)]
        plain = [v for v in variables if v not in secret]
        if plain:
            parts.append("Needs " + ", ".join(f"${v}" for v in plain) + " set in your shell.")
        if secret:
            parts.append("Needs " + ", ".join(f"${v}" for v in secret)
                         + " from your secret store. The agent never sees or fills these.")
    return " ".join(parts)


def _tool_title(name: str, args: dict[str, Any], result: Any) -> str:
    if name == "search_kb":
        how = result.get("method") or "no method worked"
        if result.get("reranked"):
            how += " + rerank"
        return f"Searched the knowledge base ({how}) for: {str(args.get('query', ''))[:80]}"
    if name == "get_article":
        return f"Read article {args.get('doc_id')}"
    if name == "related_articles":
        return f"Looked up related articles in {args.get('domain')}"
    return f"Ran {name}"


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    read_only: bool
    fn: Callable[..., Any]


class AgentEngine:
    def __init__(self, kb: Any, *, memory: MemoryManager | None = None, llm: LLM | None = None,
                 memory_error: str | None = None):
        self.kb = kb
        self.memory = memory
        self.memory_error = memory_error
        self.llm = llm or OfflineLLM()
        self.tools: dict[str, Tool] = {}
        for tool in (
            Tool("search_kb", "Search the knowledge base with the best available method", True, self._search_kb),
            Tool("get_article", "Read one knowledge base article", True, self.kb.get_article),
            Tool("related_articles", "Articles in the same domain", True, self._related),
            Tool("explain_command", "Explain what a command does without running it", True, explain_command),
        ):
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if not tool.read_only:
            raise ValueError("the engine only accepts read only tools; state changes are human steps")
        self.tools[tool.name] = tool

    # -- tools -----------------------------------------------------------------
    def _search_kb(self, query: str, limit: int = 5, category: str | None = None) -> dict[str, Any]:
        tried = []
        for method, rerank in SEARCH_CHAIN:
            result = self.kb.run(method, SearchParams(query=query, limit=limit, rerank=rerank, category=category))
            tried.append({"method": method, "rerank": rerank, "status": result["status"],
                          "reason": result.get("reason")})
            if result["status"] == "ok" and result["results"]:
                result["tried"] = tried
                return result
        return {"status": "empty", "results": [], "tried": tried, "pipeline": [], "method": None,
                "reranked": False}

    def _related(self, domain: str, exclude: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
        return self.kb.related(domain, exclude=exclude, limit=limit)

    def call(self, trace: Trace, name: str, **args: Any) -> Any:
        tool = self.tools.get(name)
        if tool is None:
            raise ValueError(f"unknown tool {name!r}")
        start = time.perf_counter()
        result = tool.fn(**args)
        ms = round((time.perf_counter() - start) * 1000, 1)
        kind = "search" if name == "search_kb" else "tool"
        detail: dict[str, Any] = {"tool": name, "args": args, "read_only": True}
        if name == "search_kb":
            detail.update({"method": result.get("method"), "reranked": result.get("reranked"),
                           "tried": result.get("tried"), "pipeline": result.get("pipeline"),
                           "top": [{"doc_id": r["doc_id"], "title": r["title"], "score": r["score"]}
                                   for r in result.get("results", [])[:5]]})
        elif isinstance(result, dict):
            detail["result"] = {k: result.get(k) for k in ("doc_id", "title") if k in result}
        elif isinstance(result, list):
            detail["result"] = result[:5]
        else:
            detail["result"] = result
        trace.add(kind, _tool_title(name, args, result), detail, ms=ms)
        return result

    # -- memory ----------------------------------------------------------------
    @property
    def memory_backend(self) -> str | None:
        return getattr(getattr(self.memory, "store", None), "name", None)

    def recall(self, trace: Trace, query: str, user_id: str,
               types: tuple[str, ...] = LONG_TERM_TYPES, limit: int = 8) -> RecallResult | None:
        if self.memory is None:
            trace.add("warning", "No long term memory for this run",
                      {"reason": self.memory_error or "memory backend not configured"})
            return None
        try:
            result = self.memory.recall(query, user_id, types, limit)
        except Exception as exc:  # noqa: BLE001 - memory must not break runs
            trace.add("warning", "Memory recall failed, continuing without it",
                      {"backend": self.memory_backend, "error": str(exc)})
            return None
        trace.add("memory_recall", f"Recalled {len(result.hits)} memories", {
            "backend": result.backend, "strategy": result.strategy, "pipeline": result.pipeline,
            "warnings": result.warnings,
            "hits": [{"type": h.record.type, "label": h.record.label, "content": h.record.content,
                      "score": round(h.score, 3), "why": h.why} for h in result.hits],
        }, ms=result.ms)
        return result

    def remember(self, trace: Trace, write: Callable[[MemoryManager], WriteOutcome],
                 what: str) -> WriteOutcome | None:
        if self.memory is None:
            return None
        try:
            outcome = write(self.memory)
        except Exception as exc:  # noqa: BLE001 - memory must not break runs
            trace.add("warning", f"Could not save {what}", {"backend": self.memory_backend, "error": str(exc)})
            return None
        trace.add("memory_write", f"{outcome.op} {outcome.record.type}: {outcome.record.label or what}",
                  {"backend": self.memory_backend, **outcome.to_api()})
        return outcome

    # -- LLM -------------------------------------------------------------------
    def think_json(self, trace: Trace, purpose: str, system: str, prompt: str,
                   max_tokens: int = 800) -> dict[str, Any] | None:
        if not self.llm.enabled:
            return None
        start = time.perf_counter()
        data = self.llm.complete_json(system, prompt, max_tokens=max_tokens)
        ms = round((time.perf_counter() - start) * 1000, 1)
        if data is None:
            trace.add("llm_fallback", f"LLM unusable for {purpose}, using deterministic logic",
                      {"provider": self.llm.name, "error": self.llm.last_error}, ms=ms)
            return None
        trace.add("llm", f"LLM {purpose}", {"provider": self.llm.name, "reply": data}, ms=ms)
        return data
