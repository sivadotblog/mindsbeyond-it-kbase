"""Tests for search agreement metrics."""
from kbase.search.compare import agreement, jaccard


def result(ids, status="ok"):
    return {"status": status, "results": [{"doc_id": d, "title": d, "rank": i} for i, d in enumerate(ids, 1)]}


def test_jaccard_basic():
    assert jaccard(["a", "b"], ["b", "c"]) == 1 / 3


def test_jaccard_both_empty_is_one():
    assert jaccard([], []) == 1.0


def test_pairs_are_sorted_and_counted():
    out = agreement({"x": result(["a", "b"]), "w": result(["b", "c"])})
    assert out["pairs"] == [{"a": "w", "b": "x", "jaccard": 0.333, "common": ["b"]}]


def test_failed_methods_are_ignored():
    out = agreement({"x": result(["a"]), "y": result([], status="unsupported")})
    assert out["pairs"] == []


def test_consensus_orders_by_coverage_then_rank():
    out = agreement({"m1": result(["a", "b", "c"]), "m2": result(["b", "a"]), "m3": result(["b"])})
    assert [c["doc_id"] for c in out["consensus"]] == ["b", "a"]
    assert out["consensus"][0]["methods"] == ["m1", "m2", "m3"]


def test_ann_recall_when_both_vector_methods_ran():
    out = agreement({"vector_ann": result(["a", "b", "x"]), "vector_enn": result(["a", "b", "c"])})
    assert out["ann_recall"] == 0.667


def test_ann_recall_none_when_enn_empty():
    out = agreement({"vector_ann": result(["a"]), "vector_enn": result([])})
    assert out["ann_recall"] is None


def test_no_ann_recall_without_both():
    assert "ann_recall" not in agreement({"vector_ann": result(["a"])})
