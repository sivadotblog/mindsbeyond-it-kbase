"""Ordered record of what an agent read, decided and did."""
from __future__ import annotations

import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from kbase.redact import redact

KINDS = ("memory_recall", "search", "decision", "tool", "confirm", "message", "memory_write",
         "llm", "llm_fallback", "warning")


def scrub(value: Any) -> Any:
    """Redact every string inside ``value``."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return value


class Trace:
    def __init__(self, events: list[dict[str, Any]] | None = None):
        self.events: list[dict[str, Any]] = list(events or [])

    def add(self, kind: str, title: str, detail: dict[str, Any] | None = None,
            ms: float | None = None) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError(f"unknown trace kind {kind!r}")
        event = {
            "seq": len(self.events) + 1,
            "at": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "title": redact(title),
            "detail": scrub(detail or {}),
            "ms": ms,
        }
        self.events.append(event)
        return event

    @contextmanager
    def timed(self, kind: str, title: str, detail: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        start = time.perf_counter()
        holder: dict[str, Any] = dict(detail or {})
        try:
            yield holder
        finally:
            self.add(kind, title, holder, ms=round((time.perf_counter() - start) * 1000, 1))

    def to_list(self) -> list[dict[str, Any]]:
        return list(self.events)
