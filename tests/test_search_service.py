"""Tests for the Atlas SearchService with a mocked collection."""
from unittest.mock import MagicMock

import pytest
from pymongo.errors import OperationFailure, PyMongoError

from kbase.search import pipelines as P
from kbase.search.methods import METHODS
from kbase.search.service import (
    RERANK_REQUIREMENT,
    SearchService,
    classify_failure,
    format_results,
    parse_version,
    rerank_warnings,
)


def make_doc(i, **extra):
    return {"doc_id": f"KB-{i:04d}", "title": f"T{i}", "category": "How-To Guide", "domain": "D",
            "score": 1.0 / i, **extra}


def make_service(docs=None, side_effect=None, version="8.3.1", indexes=None):
    coll = MagicMock()
    if side_effect is not None:
        coll.aggregate.side_effect = side_effect
    else:
        coll.aggregate.return_value = iter(docs or [])
    coll.database.command.return_value = {"version": version}
    coll.list_search_indexes.return_value = indexes if indexes is not None else [
        {"name": "fulltext_index", "type": "search", "status": "READY", "queryable": True},
        {"name": "auto_embedding_index", "type": "vectorSearch", "status": "READY", "queryable": True},
    ]
    svc = SearchService(coll, P.IndexConfig(), default_query_model="voyage-4-lite",
                        default_rerank_model="rerank-2.5-lite")
    return svc, coll


def sp(**kw):
    base = {"query": "private endpoint", "limit": 3}
    base.update(kw)
    return P.SearchParams(**base)


class TestHelpers:
    @pytest.mark.parametrize("text,expected", [("8.3.1", (8, 3)), ("9", (9, 0)), (None, None), ("x.y", None)])
    def test_parse_version(self, text, expected):
        assert parse_version(text) == expected

    def test_format_results_reranked(self):
        out = format_results([make_doc(1, preRerankRank=3, preRerankScore=0.5)], reranked=True)
        assert out[0]["rank_change"] == 2 and out[0]["pre_rerank_rank"] == 3

    def test_format_results_missing_pre_rank(self):
        out = format_results([make_doc(1)], reranked=True)
        assert out[0]["rank_change"] is None and out[0]["pre_rerank_score"] is None

    def test_format_results_keeps_score_details(self):
        out = format_results([make_doc(1, scoreDetails={"value": 1})], reranked=False)
        assert out[0]["score_details"] == {"value": 1}

    def test_constant_rerank_scores_warn(self):
        assert rerank_warnings([{"score": 0.5}, {"score": 0.5}])
        assert rerank_warnings([{"score": 0.5}, {"score": 0.4}]) == []

    def test_classify_unknown_stage(self):
        reason = classify_failure(METHODS["hybrid_score"], sp(), "Unrecognized pipeline stage name: '$scoreFusion'")
        assert reason == "$scoreFusion needs MongoDB 8.3+"

    def test_classify_rerank(self):
        assert classify_failure(METHODS["vector_ann"], sp(rerank=True), "Unrecognized pipeline stage name: '$rerank'") == RERANK_REQUIREMENT

    def test_classify_rerank_disabled(self):
        assert classify_failure(METHODS["fulltext"], sp(), "native reranking is disabled") == RERANK_REQUIREMENT

    def test_classify_other_unknown_stage(self):
        assert "does not recognize" in classify_failure(METHODS["fulltext"], sp(), "Unrecognized pipeline stage name: '$foo'")

    def test_classify_unknown_stage_while_reranking(self):
        assert classify_failure(METHODS["fulltext"], sp(rerank=True), "Unrecognized pipeline stage name: '$x'") == RERANK_REQUIREMENT

    def test_classify_autoembed(self):
        assert "automated embedding" in classify_failure(METHODS["vector_ann"], sp(), "autoEmbed not enabled")

    def test_classify_other(self):
        assert classify_failure(METHODS["fulltext"], sp(), "boom") is None


class TestRun:
    def test_ok_result(self):
        svc, coll = make_service([make_doc(1), make_doc(2)])
        out = svc.run("vector_ann", sp())
        assert out["status"] == "ok" and [r["rank"] for r in out["results"]] == [1, 2]
        sent = coll.aggregate.call_args[0][0]
        assert sent[0]["$vectorSearch"]["model"] == "voyage-4-lite"
        assert out["pipeline"] == sent

    def test_default_rerank_model_applied(self):
        svc, coll = make_service([make_doc(1, preRerankRank=2), make_doc(2, preRerankRank=1)])
        out = svc.run("fulltext", sp(rerank=True))
        rerank = [s for s in coll.aggregate.call_args[0][0] if "$rerank" in s][0]["$rerank"]
        assert rerank["model"] == "rerank-2.5-lite"
        assert [r["rank_change"] for r in out["results"]] == [1, -1]

    def test_unsupported_stage(self):
        svc, _ = make_service(side_effect=OperationFailure("Unrecognized pipeline stage name: '$scoreFusion'"))
        out = svc.run("hybrid_score", sp())
        assert out["status"] == "unsupported" and "8.3" in out["reason"]

    def test_generic_error(self):
        svc, _ = make_service(side_effect=OperationFailure("something broke"))
        out = svc.run("fulltext", sp())
        assert out["status"] == "error" and "something broke" in out["reason"]

    def test_connection_error(self):
        svc, _ = make_service(side_effect=PyMongoError("down"))
        assert svc.run("fulltext", sp())["status"] == "error"

    def test_query_shape_fallback(self):
        good = [make_doc(1)]
        svc, coll = make_service(side_effect=[OperationFailure("\"query\" must be a string"), iter(good)])
        out = svc.run("vector_ann", sp())
        assert out["status"] == "ok"
        assert coll.aggregate.call_args_list[1][0][0][0]["$vectorSearch"]["query"] == "private endpoint"
        assert "string form" in out["warnings"][0]
        assert svc._query_format == "string"

    def test_query_shape_fallback_fails_twice(self):
        svc, _ = make_service(side_effect=[OperationFailure("query must be an object"),
                                           OperationFailure("query must be an object")])
        assert svc.run("vector_ann", sp())["status"] == "error"

    def test_precheck_blocks_old_server(self):
        svc, coll = make_service([make_doc(1)], version="8.0.4")
        svc.capabilities()
        out = svc.run("hybrid_score", sp())
        assert out["status"] == "unsupported" and "8.0.4" in out["reason"]
        coll.aggregate.assert_not_called()

    def test_empty_results_warn_about_missing_index(self):
        svc, _ = make_service([], indexes=[])
        svc.capabilities()
        out = svc.run("fulltext", sp())
        assert "fulltext_index does not exist" in out["warnings"][0]

    def test_bad_method_raises(self):
        svc, _ = make_service([])
        with pytest.raises(ValueError):
            svc.run("nope", sp())

    def test_filtered_without_filter_raises(self):
        svc, _ = make_service([])
        with pytest.raises(ValueError):
            svc.run("vector_filtered", sp())


class TestCompare:
    def test_runs_each_method(self):
        svc, coll = make_service()
        coll.aggregate.side_effect = lambda pipe: iter([make_doc(1), make_doc(2)])
        out = svc.compare(["fulltext", "vector_ann", "vector_enn"], sp())
        assert set(out["results"]) == {"fulltext", "vector_ann", "vector_enn"}
        assert out["agreement"]["ann_recall"] == 1.0

    def test_default_methods(self):
        svc, coll = make_service()
        coll.aggregate.side_effect = lambda pipe: iter([])
        assert len(svc.compare(None, sp())["results"]) == 5

    def test_value_error_becomes_error_column(self):
        svc, coll = make_service()
        coll.aggregate.side_effect = lambda pipe: iter([])
        out = svc.compare(["vector_filtered"], sp())
        assert out["results"]["vector_filtered"]["status"] == "error"

    def test_rejects_too_many(self):
        svc, _ = make_service()
        with pytest.raises(ValueError, match="between 1 and 8"):
            svc.compare(["fulltext"] * 9, sp())

    def test_rejects_unknown(self):
        svc, _ = make_service()
        with pytest.raises(ValueError):
            svc.compare(["fulltext", "zzz"], sp())


class TestCapabilities:
    def test_reports_methods(self):
        svc, _ = make_service(version="8.0.1")
        caps = svc.capabilities()
        assert caps["server_version"] == "8.0.1"
        assert caps["methods"]["hybrid_rrf"]["available"] is True
        assert caps["methods"]["hybrid_score"]["available"] is False

    def test_index_not_queryable(self):
        svc, _ = make_service(indexes=[{"name": "fulltext_index", "status": "BUILDING", "queryable": False}])
        caps = svc.capabilities()
        assert "BUILDING" in caps["methods"]["fulltext"]["reason"]
        assert "does not exist" in caps["methods"]["vector_ann"]["reason"]

    def test_cached(self):
        svc, coll = make_service()
        svc.capabilities()
        svc.capabilities()
        assert coll.database.command.call_count == 1
        svc.capabilities(refresh=True)
        assert coll.database.command.call_count == 2

    def test_errors_recorded(self):
        svc, coll = make_service()
        coll.database.command.side_effect = PyMongoError("no")
        coll.list_search_indexes.side_effect = PyMongoError("no")
        caps = svc.capabilities()
        assert len(caps["errors"]) == 2


class TestArticles:
    def test_get_article(self):
        svc, coll = make_service()
        coll.find_one.return_value = {"doc_id": "KB-0001"}
        assert svc.get_article("KB-0001") == {"doc_id": "KB-0001"}
        coll.find_one.assert_called_with({"doc_id": "KB-0001"}, {"_id": 0})

    def test_related_excludes(self):
        svc, coll = make_service()
        coll.find.return_value.limit.return_value = [{"doc_id": "KB-0002"}]
        assert svc.related("D", exclude="KB-0001") == [{"doc_id": "KB-0002"}]
        assert coll.find.call_args[0][0] == {"domain": "D", "doc_id": {"$ne": "KB-0001"}}

    def test_facets(self):
        svc, coll = make_service()
        coll.distinct.side_effect = [["B", "A", None], ["Z"]]
        assert svc.facets() == {"category": ["A", "B"], "domain": ["Z"]}
