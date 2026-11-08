"""Shape tests for the Atlas pipeline builders."""
import pytest

from kbase.search import pipelines as P
from kbase.search.methods import DEFAULT_COMPARE, METHODS, get_method

IDX = P.IndexConfig()


def params(**overrides):
    base = {"query": "private endpoint timeout", "limit": 5}
    base.update(overrides)
    return P.validate_params(P.SearchParams(**base))


class TestValidateParams:
    def test_strips_query(self):
        assert params(query="  hi  ").query == "hi"

    def test_rejects_empty_query(self):
        with pytest.raises(ValueError, match="query is required"):
            params(query="   ")

    def test_rejects_long_query(self):
        with pytest.raises(ValueError, match="longer than"):
            params(query="x" * 1001)

    @pytest.mark.parametrize("given,expected", [(0, 1), (-3, 1), (7, 7), (99, 50)])
    def test_clamps_limit(self, given, expected):
        assert params(limit=given).limit == expected

    def test_clamps_num_candidates_between_limit_and_max(self):
        assert params(limit=10, num_candidates=3).num_candidates == 10
        assert params(num_candidates=99999).num_candidates == P.MAX_CANDIDATES

    def test_rejects_bad_normalization(self):
        with pytest.raises(ValueError, match="normalization"):
            params(normalization="zscore")

    def test_rejects_unknown_query_model(self):
        with pytest.raises(ValueError, match="query_model"):
            params(query_model="text-embedding-3")

    def test_rejects_negative_weight(self):
        with pytest.raises(ValueError, match="weights"):
            params(vector_weight=-1)

    def test_blank_filters_become_none(self):
        assert params(category="", domain="").filters == {}


class TestVectorSearchStage:
    def test_object_query_shape_by_default(self):
        stage = P.vector_search_stage(index="i", path="p", query="q", limit=5)["$vectorSearch"]
        assert stage["query"] == {"text": "q"}

    def test_string_query_shape(self):
        stage = P.vector_search_stage(index="i", path="p", query="q", limit=5,
                                      query_format="string")["$vectorSearch"]
        assert stage["query"] == "q"

    def test_ann_defaults_to_twenty_times_limit(self):
        stage = P.vector_search_stage(index="i", path="p", query="q", limit=5)["$vectorSearch"]
        assert stage["numCandidates"] == 100 and "exact" not in stage

    def test_enn_sets_exact_and_drops_candidates(self):
        stage = P.vector_search_stage(index="i", path="p", query="q", limit=5,
                                      exact=True)["$vectorSearch"]
        assert stage["exact"] is True and "numCandidates" not in stage

    def test_candidates_capped(self):
        stage = P.vector_search_stage(index="i", path="p", query="q", limit=5,
                                      num_candidates=50000)["$vectorSearch"]
        assert stage["numCandidates"] == P.MAX_CANDIDATES

    def test_model_and_filter(self):
        stage = P.vector_search_stage(index="i", path="p", query="q", limit=5, model="voyage-4-lite",
                                      filters={"category": "Tutorial"})["$vectorSearch"]
        assert stage["model"] == "voyage-4-lite"
        assert stage["filter"] == {"category": {"$eq": "Tutorial"}}

    def test_two_filters_use_and(self):
        assert P.vector_filter({"domain": "B", "category": "A"}) == {
            "$and": [{"category": {"$eq": "A"}}, {"domain": {"$eq": "B"}}]
        }

    def test_no_filter(self):
        assert P.vector_filter({}) is None


class TestSearchStage:
    def test_plain_text(self):
        stage = P.search_stage(index="ft", query="q")
        assert stage == {"$search": {"index": "ft", "text": {"query": "q", "path": ["title", "raw_markdown"]}}}

    def test_fuzzy(self):
        stage = P.search_stage(index="ft", query="q", fuzzy=True)
        assert stage["$search"]["text"]["fuzzy"] == {"maxEdits": 1}

    def test_filters_use_compound(self):
        stage = P.search_stage(index="ft", query="q", filters={"category": "Tutorial", "domain": "AI Search"})
        compound = stage["$search"]["compound"]
        assert compound["filter"] == [
            {"text": {"query": "Tutorial", "path": "category"}},
            {"phrase": {"query": "AI Search", "path": "domain"}},
        ]


class TestMethodPipelines:
    def test_fulltext_limits_and_projects_search_score(self):
        pipe = P.fulltext_pipeline(params(), IDX)
        assert pipe[0]["$search"]["index"] == "fulltext_index"
        assert pipe[1] == {"$limit": 5}
        assert pipe[2]["$project"]["score"] == {"$meta": "searchScore"}

    def test_vector_ann_uses_vector_index(self):
        pipe = P.vector_ann_pipeline(params(query_model="voyage-4"), IDX)
        vs = pipe[0]["$vectorSearch"]
        assert vs["index"] == "auto_embedding_index" and vs["path"] == "raw_markdown"
        assert vs["model"] == "voyage-4"
        assert pipe[-1]["$project"]["score"] == {"$meta": "vectorSearchScore"}

    def test_vector_enn_is_exact(self):
        assert P.vector_enn_pipeline(params(), IDX)[0]["$vectorSearch"]["exact"] is True

    def test_filtered_requires_filter(self):
        with pytest.raises(ValueError, match="filter"):
            P.vector_filtered_pipeline(params(), IDX)

    def test_filtered_sets_filter(self):
        pipe = P.vector_filtered_pipeline(params(domain="Networking"), IDX)
        assert pipe[0]["$vectorSearch"]["filter"] == {"domain": {"$eq": "Networking"}}

    def test_rrf_shape(self):
        pipe = P.hybrid_rrf_pipeline(params(vector_weight=2, text_weight=1), IDX)
        rf = pipe[0]["$rankFusion"]
        assert set(rf["input"]["pipelines"]) == {"vector", "text"}
        assert rf["combination"]["weights"] == {"vector": 2.0, "text": 1.0}
        assert rf["scoreDetails"] is True
        assert rf["input"]["pipelines"]["text"][0]["$search"]["index"] == "fulltext_index"
        assert pipe[1] == {"$limit": 5}
        assert pipe[2]["$project"]["scoreDetails"] == {"$meta": "scoreDetails"}

    def test_score_fusion_shape(self):
        pipe = P.hybrid_score_pipeline(params(normalization="minMaxScaler"), IDX)
        sf = pipe[0]["$scoreFusion"]
        assert sf["input"]["normalization"] == "minMaxScaler"
        assert sf["combination"]["method"] == "avg"

    def test_fusion_legs_overfetch(self):
        pipe = P.hybrid_rrf_pipeline(params(limit=5), IDX)
        legs = pipe[0]["$rankFusion"]["input"]["pipelines"]
        assert legs["vector"][0]["$vectorSearch"]["limit"] == 20
        assert legs["text"][1] == {"$limit": 20}


class TestRerankTail:
    def test_vector_rerank_tail(self):
        pipe = P.vector_ann_pipeline(params(rerank=True, rerank_model="rerank-2.5"), IDX)
        assert pipe[0]["$vectorSearch"]["limit"] == 20
        assert pipe[1] == {"$addFields": {"preRerankScore": {"$meta": "vectorSearchScore"}}}
        assert "$setWindowFields" in pipe[2]
        rr = pipe[3]["$rerank"]
        assert rr == {"query": {"text": "private endpoint timeout"}, "path": ["title", "raw_markdown"],
                      "numDocsToRerank": 20, "model": "rerank-2.5"}
        assert pipe[4] == {"$limit": 5}
        assert pipe[5]["$project"]["preRerankRank"] == 1

    def test_rerank_after_fusion_comes_after_limit(self):
        pipe = P.hybrid_rrf_pipeline(params(rerank=True), IDX)
        stages = [next(iter(s)) for s in pipe]
        assert stages == ["$rankFusion", "$limit", "$addFields", "$setWindowFields", "$rerank",
                          "$limit", "$project"]

    def test_rerank_without_model_omits_it(self):
        tail = P.rerank_tail(query="q", limit=5, pool=20, score_meta="score", model=None)
        assert "model" not in tail[2]["$rerank"]

    def test_rerank_pool_bounds(self):
        assert P.rerank_pool(1) == 20
        assert P.rerank_pool(50) == 100


class TestRegistry:
    def test_every_method_builds(self):
        for method in METHODS.values():
            extra = {"domain": "Networking"} if method.name == "vector_filtered" else {}
            assert method.builder(params(**extra), IDX)

    def test_describe_has_requirements(self):
        assert METHODS["hybrid_score"].describe()["requires"]["min_version"] == "8.3"
        assert METHODS["fulltext"].describe()["requires"]["min_version"] is None

    def test_default_compare_names_exist(self):
        assert all(name in METHODS for name in DEFAULT_COMPARE)

    def test_unknown_method(self):
        with pytest.raises(ValueError, match="unknown method"):
            get_method("bm42")
