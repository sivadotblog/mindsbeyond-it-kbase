"""Relevance, recency and importance: the three parts of a memory score.

Recency halves every ``half_life_hours``, as in the Generative Agents retrieval function.
"""
from __future__ import annotations

from datetime import datetime

from kbase.memory.models import MemoryHit, MemoryRecord, utcnow


def recency(updated_at: datetime, half_life_hours: float, now: datetime | None = None) -> float:
    now = now or utcnow()
    age_hours = max((now - updated_at).total_seconds() / 3600.0, 0.0)
    if half_life_hours <= 0:
        return 1.0
    return 0.5 ** (age_hours / half_life_hours)


def combine(relevance: float, recency_value: float, importance: float,
            weights: tuple[float, float, float]) -> float:
    w_rel, w_rec, w_imp = weights
    total = (w_rel + w_rec + w_imp) or 1.0
    return (w_rel * relevance + w_rec * recency_value + w_imp * importance) / total


def explain(relevance: float, recency_value: float, importance: float) -> str:
    parts = []
    parts.append("strong match" if relevance >= 0.7 else "partial match" if relevance >= 0.3 else "weak match")
    parts.append("recent" if recency_value >= 0.7 else "older" if recency_value >= 0.3 else "old")
    if importance >= 0.7:
        parts.append("marked important")
    return ", ".join(parts)


def score_records(scored: list[tuple[MemoryRecord, float]], *, weights: tuple[float, float, float],
                  half_life_hours: float, now: datetime | None = None, normalize: bool = True) -> list[MemoryHit]:
    """Turn (record, raw relevance) pairs into hits. Relevance is normalized to the best match unless
    ``normalize`` is false, in which case the given values must already be in 0..1."""
    top = max((s for _, s in scored), default=0.0) if normalize else 1.0
    hits = []
    for record, raw in scored:
        rel = (raw / top) if top > 0 else 0.0
        rec = recency(record.updated_at, half_life_hours, now)
        imp = record.importance
        hits.append(MemoryHit(record=record, score=combine(rel, rec, imp, weights), relevance=rel,
                              recency=rec, importance=imp, why=explain(rel, rec, imp)))
    hits.sort(key=lambda h: -h.score)
    return hits
