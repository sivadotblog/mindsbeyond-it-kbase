"""Turn a knowledge base article into an SOP checklist.

Following SOP-Agent, each node allows a small set of actions. Here that is simple: steps with a
command are human steps (the agent explains, the person runs and confirms), and the agent's own
steps only read.
"""
from __future__ import annotations

import re
from typing import Any

from kbase.agent.engine import command_variables, explain_command
from kbase.memory.models import MemoryHit, label_key
from kbase.redact import is_secret_name
from kbase.search.offline import tokenize


def match_confidence(task: str, article: dict[str, Any]) -> float:
    """Share of the task's content words that appear in the article (title words count double)."""
    words = tokenize(task)
    if not words or not article:
        return 0.0
    title = set(tokenize(article.get("title", "")))
    body = set(tokenize(" ".join([
        article.get("raw_markdown", ""), article.get("domain", ""),
        (article.get("troubleshooting") or {}).get("error", ""),
        (article.get("troubleshooting") or {}).get("solution", ""),
    ])))
    stems_body = {w[:6] for w in body | title}
    score = 0.0
    for w in words:
        if w in title:
            score += 1.0
        elif w in body or w[:6] in stems_body:
            score += 0.6
    return round(min(score / len(words), 1.0), 3)


def _step(id_: str, kind: str, actor: str, title: str, *, command: str | None = None,
          explain: str = "", hints: list[str] | None = None, output: str | None = None,
          status: str = "pending") -> dict[str, Any]:
    return {"id": id_, "kind": kind, "actor": actor, "title": title, "command": command,
            "explain": explain, "hints": hints or [], "status": status, "note": None,
            "guidance": [], "output": output}


def _var_key(name: str) -> str:
    return label_key(name.replace("_", " ")) or ""


def memory_hints(step_id: str, command: str | None, doc_id: str, hits: list[MemoryHit]) -> list[str]:
    """Hints for one step from recalled procedural notes and semantic facts."""
    hints = []
    for hit in hits:
        rec = hit.record
        src = rec.source or {}
        if rec.type == "procedural" and src.get("doc_id") == doc_id and src.get("step_id") == step_id:
            hints.append(f"From a past run: {rec.content}")
    for var in command_variables(command or ""):
        if is_secret_name(var):
            hints.append(f"${var} is a secret. Supply it from your own secret store; the agent never fills it.")
            continue
        vkey = _var_key(var)
        for hit in hits:
            rec = hit.record
            lkey = rec.label_key or ""
            if rec.type != "semantic" or not lkey or not vkey:
                continue
            if lkey == vkey or vkey.endswith(" " + lkey) or lkey.endswith(" " + vkey):
                value = rec.content.split("=", 1)[-1].strip()
                hints.append(f"Known value for ${var} from memory: {value}")
                break
    return hints


def build_checklist(article: dict[str, Any], *, hits: list[MemoryHit] | None = None,
                    related: list[dict[str, Any]] | None = None,
                    explanations: dict[str, str] | None = None,
                    memory_on: bool = True) -> list[dict[str, Any]]:
    hits = hits or []
    explanations = explanations or {}
    doc_id = article.get("doc_id", "")
    steps: list[dict[str, Any]] = []

    rel = related or []
    steps.append(_step(
        "agent-review", "agent", "agent", "Read the procedure and find related articles",
        output=("Related: " + "; ".join(f"{r['doc_id']} {r['title']}" for r in rel)) if rel
        else "No related articles in the same domain.",
        status="done",
    ))
    if memory_on:
        notes = [h for h in hits if h.record.type == "procedural" and (h.record.source or {}).get("doc_id") == doc_id]
        facts = [h for h in hits if h.record.type == "semantic"]
        episodes = [h for h in hits if h.record.type == "episodic"]
        steps.append(_step(
            "agent-memory", "agent", "agent", "Check memory for notes, facts and past runs",
            output=f"{len(notes)} notes on this procedure, {len(facts)} facts, {len(episodes)} past runs.",
            status="done",
        ))

    items = article.get("prerequisite_items") or []
    tooling = article.get("prerequisites") or ""
    if not items:
        items = [f"Tooling & Access: {tooling}"] if tooling else []
        items += ["Environment Tags: set MINDSBEYOND_SOURCE_ID and MINDSBEYOND_COST_CENTER",
                  "IAM Permissions: active service account permissions"]
    for n, item in enumerate(items, start=1):
        text = re.sub(r"`", "", item).rstrip(".")
        steps.append(_step(f"pre-{n}", "prerequisite", "human", f"Confirm: {text}",
                           explain="You confirm this. Credentials stay with you; the agent never asks for them."))

    commands = article.get("steps") or {}
    for key, kind, title in (("step1", "step", "Step 1: environment and context setup"),
                             ("step2", "step", "Step 2: primary operation"),
                             ("verify", "verify", "Verify the result")):
        command = commands.get(key) or ""
        if not command:
            continue
        sid = "verify" if key == "verify" else f"step-{key[-1]}"
        steps.append(_step(
            sid, kind, "human", title, command=command,
            explain=explanations.get(sid) or explain_command(command),
            hints=memory_hints(sid, command, doc_id, hits),
        ))
    return steps


def failure_guidance(article: dict[str, Any], step: dict[str, Any], *, related: list[dict[str, Any]],
                     hits: list[MemoryHit]) -> list[str]:
    trouble = article.get("troubleshooting") or {}
    out = []
    if trouble.get("error"):
        out.append(f"Known error for this procedure: {trouble['error']}. Fix: {trouble.get('solution', '')}".strip())
    for hit in hits:
        rec = hit.record
        if rec.type == "procedural" and (rec.source or {}).get("doc_id") == article.get("doc_id"):
            out.append(f"From a past run: {rec.content}")
    for r in related:
        out.append(f"Related article: {r['doc_id']} {r['title']}")
    if not out:
        out.append("No troubleshooting guidance found. Check the step output and escalate in #data-platform-support.")
    return out
