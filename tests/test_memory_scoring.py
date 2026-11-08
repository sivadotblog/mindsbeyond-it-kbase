"""Tests for memory models and scoring."""
from datetime import datetime, timedelta, timezone

import pytest

from kbase.memory.models import MemoryHit, MemoryRecord, RecallResult, label_key
from kbase.memory.scoring import combine, explain, recency, score_records

NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)


def rec(**kw):
    base = {"type": "semantic", "user_id": "u1", "content": "cluster = kbase-prod", "label": "cluster",
            "updated_at": NOW, "created_at": NOW}
    base.update(kw)
    return MemoryRecord(**base)


class TestModels:
    @pytest.mark.parametrize("raw,key", [("Cluster Name", "cluster name"), ("cluster_name", "cluster name"),
                                         ("KB-0016:step-2", "kb 0016:step 2"), ("", None), (None, None), ("--", None)])
    def test_label_key(self, raw, key):
        assert label_key(raw) == key

    @pytest.mark.parametrize("kw,msg", [({"type": "x"}, "memory type"), ({"visibility": "public"}, "visibility"),
                                        ({"user_id": " "}, "user_id"), ({"content": ""}, "content")])
    def test_validation(self, kw, msg):
        with pytest.raises(ValueError, match=msg):
            rec(**kw)

    def test_importance_clamped(self):
        assert rec(importance=3).importance == 1.0 and rec(importance=-1).importance == 0.0

    def test_naive_and_string_dates_become_utc(self):
        r = rec(created_at="2026-11-08T10:00:00Z", updated_at=datetime(2026, 11, 8, 11), expires_at="2026-11-09T00:00:00")
        assert r.created_at.tzinfo and r.updated_at.tzinfo and r.expires_at.tzinfo

    def test_doc_round_trip(self):
        r = rec()
        doc = r.to_doc()
        assert doc["_id"] == r.id and doc["label_key"] == "cluster"
        back = MemoryRecord.from_doc({**doc, "score": 1, "score_parts": {}})
        assert back.id == r.id and back.content == r.content

    def test_to_api(self):
        r = rec(history=[{"content": "old", "at": NOW}])
        assert r.to_api()["versions"] == 2
        assert r.to_api(with_history=True)["history"][0]["at"] == NOW.isoformat()

    def test_hit_and_result_to_api(self):
        hit = MemoryHit(record=rec(), score=0.123456, relevance=1, recency=0.5, importance=0.7, why="x")
        out = RecallResult(backend="b", strategy="s", hits=[hit]).to_api()
        assert out["hits"][0]["score"] == 0.1235 and out["hits"][0]["score_parts"]["recency"] == 0.5


class TestScoring:
    def test_recency_halves_each_half_life(self):
        assert recency(NOW - timedelta(hours=24), 24, NOW) == pytest.approx(0.5)
        assert recency(NOW, 24, NOW) == 1.0

    def test_future_and_zero_half_life(self):
        assert recency(NOW + timedelta(hours=5), 24, NOW) == 1.0
        assert recency(NOW - timedelta(days=9), 0, NOW) == 1.0

    def test_combine_weights(self):
        assert combine(1, 0, 0, (0.6, 0.2, 0.2)) == pytest.approx(0.6)
        assert combine(1, 1, 1, (0, 0, 0)) == 0.0

    def test_explain(self):
        assert explain(0.9, 0.9, 0.9) == "strong match, recent, marked important"
        assert explain(0.1, 0.1, 0.1) == "weak match, old"
        assert explain(0.5, 0.5, 0.5) == "partial match, older"

    def test_score_records_normalizes_and_sorts(self):
        old = rec(content="older", updated_at=NOW - timedelta(days=30))
        new = rec(content="newer")
        hits = score_records([(old, 2.0), (new, 1.0)], weights=(0.6, 0.2, 0.2), half_life_hours=168, now=NOW)
        assert {h.record.content: h.relevance for h in hits} == {"older": 1.0, "newer": 0.5}

    def test_score_records_zero_relevance(self):
        hits = score_records([(rec(), 0.0)], weights=(1, 0, 0), half_life_hours=1, now=NOW)
        assert hits[0].relevance == 0.0
