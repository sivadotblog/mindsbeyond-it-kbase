"""The SOP agent: find a procedure, build a checklist, walk it with a person, remember what happened.

Lifecycle of a run::

    start(task)  -> recall memory, search KB, choose a procedure, build the checklist
    message()    -> person tells the agent something; facts are noted for later
    confirm()    -> person marks a human step done, failed or skipped; failures get guidance
    choose()     -> person overrides the chosen procedure
    finish()     -> summary, then memory: episode, facts, step notes
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from kbase.agent.engine import AgentEngine
from kbase.agent.sop import build_checklist, failure_guidance, match_confidence
from kbase.agent.trace import Trace
from kbase.memory.extract import heuristic_facts, llm_facts
from kbase.memory.models import MemoryHit, MemoryRecord
from kbase.redact import contains_secret, redact

STATUSES = ("no_match", "in_progress", "completed", "abandoned")
STEP_STATUSES = ("done", "failed", "skipped")
MAX_TEXT = 2000

CHOOSE_SYSTEM = (
    "You pick the standard operating procedure (SOP) that best fits an engineer's task. You only "
    "choose from the candidates given. You never ask for or handle credentials. JSON keys: "
    '"doc_id" (one of the candidate ids, or null if none fits), "reason" (one or two plain sentences).'
)
SUMMARY_SYSTEM = (
    "You write a short, plain summary of an SOP run for the team's records: what was attempted, "
    "what happened at each failed or skipped step, and what to remember next time. No secrets. "
    'JSON keys: "summary" (under 120 words).'
)


class RunNotFound(KeyError):
    pass


class RunError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hits_from_run(run: dict[str, Any]) -> list[MemoryHit]:
    hits = []
    for item in run.get("recalled") or []:
        rec = item["record"]
        try:
            record = MemoryRecord(type=rec["type"], user_id=rec["user_id"], content=rec["content"],
                                  label=rec.get("label"), source=rec.get("source"),
                                  importance=rec.get("importance", 0.5), id=rec["id"],
                                  created_at=rec["created_at"], updated_at=rec["updated_at"])
        except (KeyError, ValueError):
            continue
        parts = item.get("score_parts", {})
        hits.append(MemoryHit(record=record, score=item.get("score", 0.0), relevance=parts.get("relevance", 0.0),
                              recency=parts.get("recency", 0.0), importance=parts.get("importance", 0.0),
                              why=item.get("why", "")))
    return hits


class SOPAgent:
    def __init__(self, engine_for: Callable[[str | None], AgentEngine], runs: Any, *,
                 min_confidence: float = 0.3, default_backend: str | None = None):
        self.engine_for = engine_for
        self.runs = runs
        self.min_confidence = min_confidence
        self.default_backend = default_backend

    # -- helpers ----------------------------------------------------------------
    def _load(self, run_id: str) -> tuple[dict[str, Any], Trace, AgentEngine]:
        run = self.runs.get(run_id)
        if run is None:
            raise RunNotFound(run_id)
        return run, Trace(run.get("trace")), self.engine_for(run.get("memory_backend"))

    def _save(self, run: dict[str, Any], trace: Trace) -> dict[str, Any]:
        run["trace"] = trace.to_list()
        run["updated_at"] = _now()
        self.runs.save(run)
        return run

    @staticmethod
    def _clean(text: str | None, field: str, *, min_len: int = 0) -> str:
        text = (text or "").strip()
        if len(text) < min_len:
            raise RunError(f"{field} must be at least {min_len} characters")
        if len(text) > MAX_TEXT:
            raise RunError(f"{field} must be at most {MAX_TEXT} characters")
        return redact(text)

    # -- start ------------------------------------------------------------------
    def start(self, task: str, user_id: str, *, memory_backend: str | None = None) -> dict[str, Any]:
        task = self._clean(task, "task", min_len=3)
        user_id = (user_id or "").strip()
        if not user_id:
            raise RunError("user_id is required")
        backend = memory_backend or self.default_backend
        engine = self.engine_for(backend)
        trace = Trace()
        now = _now()
        run: dict[str, Any] = {
            "id": uuid.uuid4().hex, "user_id": user_id, "task": task, "status": "in_progress",
            "created_at": now, "updated_at": now, "memory_backend": engine.memory_backend,
            "llm": engine.llm.name, "search": None, "procedure": None, "recalled": [], "checklist": [],
            "messages": [], "learned": [], "summary": None, "memory_writes": [],
        }

        recall = engine.recall(trace, task, user_id)
        hits = recall.hits if recall else []
        run["recalled"] = [h.to_api() for h in hits]
        if recall:
            run["recall_pipeline"] = recall.pipeline
            run["recall_strategy"] = recall.strategy
        engine.remember(trace, lambda m: m.add_turn(user_id, run["id"], "user", task), "task turn")

        search = engine.call(trace, "search_kb", query=task, limit=5)
        candidates = []
        for item in search.get("results", []):
            article = engine.call(trace, "get_article", doc_id=item["doc_id"]) or {}
            candidates.append({**item, "confidence": match_confidence(task, article),
                               "known_error": (article.get("troubleshooting") or {}).get("error", "")})
        for cand in candidates:
            if search.get("reranked") and cand.get("score", 0) > cand["confidence"]:
                cand["confidence"] = round(min(float(cand["score"]), 1.0), 3)
        run["search"] = {"method": search.get("method"), "reranked": search.get("reranked"),
                         "tried": search.get("tried"), "pipeline": search.get("pipeline"),
                         "offline": search.get("offline", False), "candidates": candidates}

        how = f"{search.get('method') or 'search'}{' + rerank' if search.get('reranked') else ''}"
        choice = self._choose(engine, trace, task, candidates, hits, how)
        if choice is None:
            run["status"] = "no_match"
            trace.add("decision", "No procedure fits well enough; showing candidates instead", {
                "threshold": self.min_confidence,
                "best": candidates[0]["confidence"] if candidates else None,
            })
            return self._save(run, trace)
        doc_id, reason, chosen_by = choice
        self._plan(run, engine, trace, doc_id, reason, chosen_by, hits)
        return self._save(run, trace)

    def _choose(self, engine: AgentEngine, trace: Trace, task: str, candidates: list[dict[str, Any]],
                hits: list[MemoryHit], how: str = "search") -> tuple[str, str, str] | None:
        if not candidates:
            return None
        past = {(h.record.source or {}).get("doc_id") for h in hits} - {None}
        ids = {c["doc_id"] for c in candidates}
        if engine.llm.enabled:
            prompt = "Task: " + task + "\nCandidates:\n" + "\n".join(
                f"- {c['doc_id']}: {c['title']} (domain {c['domain']}; known error {c['known_error']}; "
                f"match {c['confidence']})" for c in candidates)
            if hits:
                prompt += "\nMemories:\n" + "\n".join(f"- {h.record.content}" for h in hits[:5])
            data = engine.think_json(trace, "choose a procedure", CHOOSE_SYSTEM, prompt)
            if data is not None:
                chosen = data.get("doc_id")
                if chosen is None:
                    return None
                if chosen in ids:
                    reason = str(data.get("reason") or "Chosen by the LLM.")[:500]
                    trace.add("decision", f"Chose {chosen}", {"by": "llm", "reason": reason})
                    return chosen, reason, "agent"
                trace.add("llm_fallback", "LLM picked an id that is not a candidate", {"doc_id": chosen})
        best = candidates[0]
        if best["confidence"] < self.min_confidence:
            return None
        reason = (f"Top result of {how} out of {len(candidates)} candidates; "
                  f"{round(best['confidence'] * 100)}% match with the task's words.")
        if best["doc_id"] in past:
            reason += " You have run this procedure before; notes from that run are attached."
        trace.add("decision", f"Chose {best['doc_id']}", {"by": "rules", "reason": reason,
                                                          "confidence": best["confidence"]})
        return best["doc_id"], reason, "agent"

    def _plan(self, run: dict[str, Any], engine: AgentEngine, trace: Trace, doc_id: str, reason: str,
              chosen_by: str, hits: list[MemoryHit]) -> None:
        article = engine.call(trace, "get_article", doc_id=doc_id)
        if not article:
            raise RunError(f"article {doc_id} not found")
        related = engine.call(trace, "related_articles", domain=article.get("domain", ""), exclude=doc_id)
        run["procedure"] = {"doc_id": doc_id, "title": article.get("title", ""), "domain": article.get("domain", ""),
                            "reason": reason, "chosen_by": chosen_by,
                            "troubleshooting": article.get("troubleshooting") or {}}
        run["checklist"] = build_checklist(article, hits=hits, related=related,
                                           memory_on=engine.memory is not None)
        run["status"] = "in_progress"
        human = sum(1 for s in run["checklist"] if s["actor"] == "human")
        trace.add("decision", f"Built a checklist of {len(run['checklist'])} steps ({human} for you)",
                  {"doc_id": doc_id, "steps": [{"id": s["id"], "actor": s["actor"], "title": s["title"]}
                                               for s in run["checklist"]]})

    # -- during the run -----------------------------------------------------------
    def choose(self, run_id: str, doc_id: str) -> dict[str, Any]:
        run, trace, engine = self._load(run_id)
        if run["status"] in ("completed", "abandoned"):
            raise RunError("the run is finished")
        ids = {c["doc_id"] for c in (run.get("search") or {}).get("candidates", [])}
        if doc_id not in ids and engine.kb.get_article(doc_id) is None:
            raise RunError(f"article {doc_id} not found")
        trace.add("decision", f"You chose {doc_id}", {"by": "user"})
        self._plan(run, engine, trace, doc_id, "Chosen by you.", "user", _hits_from_run(run))
        return self._save(run, trace)

    def confirm(self, run_id: str, step_id: str, status: str, note: str | None = None) -> dict[str, Any]:
        run, trace, engine = self._load(run_id)
        if run["status"] != "in_progress":
            raise RunError(f"the run is {run['status']}")
        if status not in STEP_STATUSES:
            raise RunError(f"status must be one of {', '.join(STEP_STATUSES)}")
        step = next((s for s in run["checklist"] if s["id"] == step_id), None)
        if step is None:
            raise RunNotFound(step_id)
        if step["actor"] != "human":
            raise RunError("agent steps complete on their own")
        clean = self._clean(note, "note") if note else None
        step["status"], step["note"] = status, clean
        trace.add("confirm", f"{step['title']}: {status}", {"step": step_id, "note": clean})
        if clean:
            engine.remember(trace, lambda m: m.add_turn(run["user_id"], run["id"], "user",
                                                        f"{step['title']} ({status}): {clean}"), "step note turn")
            self._learn(run, engine, trace, clean)
        if status == "failed":
            article = engine.call(trace, "get_article", doc_id=run["procedure"]["doc_id"]) or {}
            query = " ".join(filter(None, [clean, (article.get("troubleshooting") or {}).get("error")]))
            related = []
            if query:
                search = engine.call(trace, "search_kb", query=query, limit=3)
                related = [{"doc_id": r["doc_id"], "title": r["title"]} for r in search.get("results", [])
                           if r["doc_id"] != run["procedure"]["doc_id"]][:2]
            step["guidance"] = failure_guidance(article, step, related=related, hits=_hits_from_run(run))
            trace.add("decision", "Added troubleshooting guidance", {"step": step_id, "guidance": step["guidance"]})
        return self._save(run, trace)

    def _learn(self, run: dict[str, Any], engine: AgentEngine, trace: Trace, text: str) -> list[dict[str, str]]:
        facts = llm_facts(engine.llm, text) if engine.llm.enabled else None
        if facts is None:
            facts = heuristic_facts(text)
        learned = {f["label"].lower(): f for f in run.get("learned", [])}
        new = []
        for fact in facts:
            item = {"label": fact.label, "value": fact.value}
            if learned.get(fact.label.lower()) != item:
                learned[fact.label.lower()] = item
                new.append(item)
        run["learned"] = list(learned.values())
        if new:
            trace.add("decision", f"Noted {len(new)} fact(s) to save when the run finishes", {"facts": new})
        return new

    def message(self, run_id: str, content: str) -> dict[str, Any]:
        run, trace, engine = self._load(run_id)
        raw = (content or "").strip()
        had_secret = contains_secret(raw)
        text = self._clean(raw, "message", min_len=1)
        run["messages"].append({"role": "user", "content": text, "at": _now()})
        trace.add("message", "You said", {"content": text})
        engine.remember(trace, lambda m: m.add_turn(run["user_id"], run["id"], "user", text), "message turn")
        new = self._learn(run, engine, trace, text)

        reply = []
        if had_secret:
            reply.append("That looked like a secret, so I removed it before saving anything. "
                         "I never need secrets; type them into your own terminal.")
        if new:
            reply.append("Noted: " + "; ".join(f"{f['label']} = {f['value']}" for f in new)
                         + ". I will save this to memory when the run finishes.")
        if text.endswith("?"):
            search = engine.call(trace, "search_kb", query=text, limit=3)
            titles = [f"{r['doc_id']} {r['title']}" for r in search.get("results", [])]
            reply.append(("These articles may help: " + "; ".join(titles) + ".") if titles
                         else "I could not find an article for that.")
        if not reply:
            reply.append("Noted. It is in short term memory for this run.")
        answer = " ".join(reply)
        run["messages"].append({"role": "agent", "content": answer, "at": _now()})
        trace.add("message", "Agent replied", {"content": answer})
        engine.remember(trace, lambda m: m.add_turn(run["user_id"], run["id"], "assistant", answer), "reply turn")
        return self._save(run, trace)

    # -- finish -------------------------------------------------------------------
    def finish(self, run_id: str) -> dict[str, Any]:
        run, trace, engine = self._load(run_id)
        if run["status"] in ("completed", "abandoned"):
            raise RunError(f"the run is already {run['status']}")
        human = [s for s in run["checklist"] if s["actor"] == "human"]
        pending = [s for s in human if s["status"] == "pending"]
        run["status"] = "abandoned" if (pending or run["status"] == "no_match") else "completed"
        run["summary"] = self._summary(run, engine, trace)
        trace.add("decision", f"Run {run['status']}", {"summary": run["summary"]})

        writes = []
        user, rid = run["user_id"], run["id"]
        proc = run.get("procedure") or {}
        title = proc.get("title") or run["task"][:60]
        outcome = engine.remember(trace, lambda m: m.remember_episode(user, rid, title, run["summary"],
                                                                      proc.get("doc_id")), "episode")
        writes.append(outcome)
        for fact in run.get("learned", []):
            writes.append(engine.remember(trace, lambda m, f=fact: m.remember_fact(user, f["label"], f["value"],
                                                                                    run_id=rid), "fact"))
        for step in human:
            if step.get("note") and proc.get("doc_id"):
                writes.append(engine.remember(trace, lambda m, s=step: m.remember_step_note(
                    user, proc["doc_id"], s["id"], s["title"], s["note"], failed=s["status"] == "failed",
                    run_id=rid), "step note"))
        run["memory_writes"] = [w.to_api() for w in writes if w is not None]
        return self._save(run, trace)

    def _summary(self, run: dict[str, Any], engine: AgentEngine, trace: Trace) -> str:
        proc = run.get("procedure") or {}
        human = [s for s in run["checklist"] if s["actor"] == "human"]
        counts = {k: sum(1 for s in human if s["status"] == k) for k in ("done", "failed", "skipped", "pending")}
        lines = [f"Task: {run['task']}."]
        if proc:
            lines.append(f"Procedure {proc['doc_id']} {proc['title']}.")
        else:
            lines.append("No procedure was chosen.")
        lines.append(f"Outcome: {run['status']}. Steps: {counts['done']} done, {counts['failed']} failed, "
                     f"{counts['skipped']} skipped, {counts['pending']} pending.")
        for s in human:
            if s["status"] in ("failed", "skipped") or s.get("note"):
                lines.append(f"{s['title']} {s['status']}" + (f": {s['note']}" if s.get("note") else "") + ".")
        if run.get("learned"):
            lines.append("Learned: " + "; ".join(f"{f['label']} = {f['value']}" for f in run["learned"]) + ".")
        template = " ".join(lines)
        if engine.llm.enabled:
            data = engine.think_json(trace, "summarize the run", SUMMARY_SYSTEM, template, max_tokens=400)
            if data and isinstance(data.get("summary"), str) and data["summary"].strip():
                return redact(data["summary"].strip())[:1500]
        return template

    # -- reads ----------------------------------------------------------------------
    def get(self, run_id: str) -> dict[str, Any]:
        run = self.runs.get(run_id)
        if run is None:
            raise RunNotFound(run_id)
        return run

    def list(self, user_id: str) -> list[dict[str, Any]]:
        return self.runs.list(user_id)

