"""In process memory backend for offline mode and tests."""
from __future__ import annotations

import math
import threading
import time
from datetime import datetime
from typing import Any, Callable

from kbase.memory.models import MemoryRecord, RecallResult, label_key, utcnow
from kbase.memory.scoring import score_records
from kbase.search.offline import tokenize


RECENT_FLOOR = 0.25


def lexical_relevance(query: str, record: MemoryRecord) -> float:
    q = set(tokenize(query))
    d = set(tokenize(f"{record.label or ''} {record.content}"))
    if not q or not d:
        return 0.0
    return len(q & d) / math.sqrt(len(q) * len(d))


class InMemoryStore:
    name = "inmemory"
    capabilities = {"delete": True, "update": True, "list": True}

    def __init__(self, *, weights: tuple[float, float, float] = (0.6, 0.2, 0.2),
                 half_life_hours: float = 168.0, now: Callable[[], datetime] = utcnow):
        self._items: dict[str, MemoryRecord] = {}
        self._lock = threading.Lock()
        self.weights = weights
        self.half_life_hours = half_life_hours
        self.now = now

    def _alive(self, rec: MemoryRecord) -> bool:
        return rec.expires_at is None or rec.expires_at > self.now()

    def _visible(self, rec: MemoryRecord, user_id: str) -> bool:
        return self._alive(rec) and (rec.user_id == user_id or rec.visibility == "org")

    def write(self, record: MemoryRecord) -> MemoryRecord:
        with self._lock:
            self._items[record.id] = record
        return record

    def update(self, record: MemoryRecord) -> MemoryRecord:
        return self.write(record)

    def find_by_label(self, user_id: str, type_: str, label: str) -> MemoryRecord | None:
        key = label_key(label)
        for rec in self._items.values():
            if rec.user_id == user_id and rec.type == type_ and rec.label_key == key and self._alive(rec):
                return rec
        return None

    def list(self, user_id: str, type_: str | None = None, limit: int = 50) -> list[MemoryRecord]:
        items = [r for r in self._items.values() if self._visible(r, user_id) and (type_ is None or r.type == type_)]
        items.sort(key=lambda r: r.updated_at, reverse=True)
        return items[:limit]

    def recall(self, query: str, user_id: str, types: tuple[str, ...], limit: int = 8) -> RecallResult:
        """Token overlap, plus a "recent and important" leg like the Atlas backend's third
        ``$rankFusion`` input: the top records by importance and recency get a small relevance
        floor, so facts and notes still reach the agent when the wording differs."""
        start = time.perf_counter()
        visible = [r for r in self._items.values() if r.type in types and self._visible(r, user_id)]
        lexical = {r.id: lexical_relevance(query, r) for r in visible}
        top = max(lexical.values(), default=0.0) or 1.0
        lexical = {k: v / top for k, v in lexical.items()}
        recent = sorted(visible, key=lambda r: (r.importance, r.updated_at), reverse=True)[: max(limit * 3, 10)]
        floor = {r.id: RECENT_FLOOR for r in recent}
        scored = []
        for rec in visible:
            rel = max(lexical[rec.id], floor.get(rec.id, 0.0))
            if rel > 0:
                scored.append((rec, rel))
        hits = score_records(scored, weights=self.weights, half_life_hours=self.half_life_hours,
                             now=self.now(), normalize=False)[:limit]
        return RecallResult(backend=self.name, strategy="in process token overlap + recent and important", hits=hits,
                            ms=round((time.perf_counter() - start) * 1000, 2))

    def delete(self, memory_id: str, user_id: str) -> bool:
        with self._lock:
            rec = self._items.get(memory_id)
            if rec is None or rec.user_id != user_id:
                return False
            del self._items[memory_id]
            return True

    def setup(self) -> list[str]:
        return ["In process memory needs no setup. It is cleared when the app restarts."]

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "capabilities": self.capabilities, "persistent": False,
                "count": len(self._items)}
