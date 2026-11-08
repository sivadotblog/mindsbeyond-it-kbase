"""MemoryManager: the write path. Decides ADD, UPDATE or NOOP and keeps history.

No automatic DELETE. People delete memories in the explorer. This follows the lesson in the
research notes: automatic deletes are where memory systems make destructive mistakes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from kbase.memory.base import MemoryStore
from kbase.memory.inmemory import lexical_relevance
from kbase.memory.models import DEFAULT_IMPORTANCE, LONG_TERM_TYPES, MemoryRecord, RecallResult, label_key, utcnow
from kbase.redact import redact

NEAR_DUPLICATE = 0.9


@dataclass
class WriteOutcome:
    op: str  # ADD | UPDATE | NOOP
    record: MemoryRecord
    reason: str

    def to_api(self) -> dict[str, Any]:
        return {"op": self.op, "type": self.record.type, "label": self.record.label,
                "id": self.record.id, "reason": self.reason, "content": self.record.content}


class MemoryManager:
    def __init__(self, store: MemoryStore, *, stm_ttl_hours: float = 24.0,
                 agent_id: str = "sop-agent", now: Callable = utcnow):
        self.store = store
        self.stm_ttl_hours = stm_ttl_hours
        self.agent_id = agent_id
        self.now = now

    # -- generic -------------------------------------------------------------
    def remember(self, *, type_: str, user_id: str, content: str, label: str | None = None,
                 importance: float | None = None, visibility: str = "private",
                 source: dict[str, Any] | None = None) -> WriteOutcome:
        content = redact(content).strip()
        if type_ == "stm":
            rec = self._record(type_, user_id, content, label, importance, visibility, source)
            rec.expires_at = self.now() + timedelta(hours=self.stm_ttl_hours)
            return WriteOutcome("ADD", self.store.write(rec), "short term turn, expires automatically")

        if label_key(label):
            existing = self.store.find_by_label(user_id, type_, label)
            if existing is not None:
                if existing.content.strip().lower() == content.lower():
                    return WriteOutcome("NOOP", existing, "same label and same content already stored")
                existing.history.append({"content": existing.content, "at": existing.updated_at})
                existing.content = content
                existing.updated_at = self.now()
                if importance is not None:
                    existing.importance = max(existing.importance, importance)
                if source:
                    existing.source = source
                return WriteOutcome("UPDATE", self.store.update(existing),
                                    "same label with new content; previous value kept in history")

        dup = self._near_duplicate(type_, user_id, content)
        if dup is not None:
            return WriteOutcome("NOOP", dup, "near duplicate of an existing memory")
        rec = self._record(type_, user_id, content, label, importance, visibility, source)
        return WriteOutcome("ADD", self.store.write(rec), "new memory")

    def _record(self, type_, user_id, content, label, importance, visibility, source) -> MemoryRecord:
        now = self.now()
        return MemoryRecord(
            type=type_, user_id=user_id, content=content, label=label, agent_id=self.agent_id,
            visibility=visibility,
            importance=DEFAULT_IMPORTANCE[type_] if importance is None else importance,
            source=source, created_at=now, updated_at=now,
        )

    def _near_duplicate(self, type_: str, user_id: str, content: str) -> MemoryRecord | None:
        if type_ not in LONG_TERM_TYPES:
            return None
        for rec in self.store.list(user_id, type_, limit=200):
            if rec.user_id == user_id and lexical_relevance(content, rec) >= NEAR_DUPLICATE:
                return rec
        return None

    # -- typed helpers used by the agent ---------------------------------------
    def add_turn(self, user_id: str, run_id: str, role: str, content: str) -> WriteOutcome:
        return self.remember(type_="stm", user_id=user_id, content=content,
                             source={"run_id": run_id, "role": role})

    def remember_fact(self, user_id: str, label: str, value: str, *, run_id: str | None = None) -> WriteOutcome:
        return self.remember(type_="semantic", user_id=user_id, label=label, content=f"{label} = {value}",
                             source={"run_id": run_id} if run_id else None)

    def remember_step_note(self, user_id: str, doc_id: str, step_id: str, step_title: str, note: str,
                           *, failed: bool, run_id: str | None = None) -> WriteOutcome:
        status = "failed" if failed else "note"
        return self.remember(
            type_="procedural", user_id=user_id, label=f"{doc_id}:{step_id}",
            content=f"{doc_id} {step_title} ({status}): {note}",
            importance=0.9 if failed else 0.7,
            source={"run_id": run_id, "doc_id": doc_id, "step_id": step_id},
        )

    def remember_episode(self, user_id: str, run_id: str, title: str, summary: str,
                         doc_id: str | None) -> WriteOutcome:
        return self.remember(type_="episodic", user_id=user_id, label=f"run {run_id[:8]}: {title}",
                             content=summary, source={"run_id": run_id, "doc_id": doc_id})

    def recall(self, query: str, user_id: str, types: tuple[str, ...] = LONG_TERM_TYPES,
               limit: int = 8) -> RecallResult:
        return self.store.recall(query, user_id, types, limit)
