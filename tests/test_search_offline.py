"""Tests for the markdown parser and the offline search service."""
import pytest

from kbase.search import pipelines as P
from kbase.search.docs import load_articles, parse_article
from kbase.search.offline import OfflineSearchService, rrf, score_fusion, tokenize

SAMPLE = """# How To: Fixing Things Fast

**Document ID**: KB-0099
**Category**: Tutorial
**Domain**: Networking

## Prerequisites
1. **Tooling & Access**: Azure CLI, Owner role.
2. **Environment Tags**: Set tags.

## Step-by-Step Execution Guide

### Step 1: Setup
```bash
# comment
export MINDSBEYOND_SOURCE_ID="SRC-99402"
az login
```

### Step 2: Run
```bash
az network fix --now
```

## Verification & Validation

```bash
nc -zv host 443
```

## Troubleshooting

**Error Message**: `Connection Refused`

**Resolution**: Open port 443.
"""


@pytest.fixture(scope="module")
def docs():
    return load_articles("md_docs")


@pytest.fixture(scope="module")
def svc(docs):
    return OfflineSearchService(docs, P.IndexConfig(), default_query_model="voyage-4-lite")


class TestParser:
    def test_fields(self):
        doc = parse_article(SAMPLE)
        assert doc["doc_id"] == "KB-0099" and doc["title"] == "Fixing Things Fast"
        assert doc["category"] == "Tutorial" and doc["domain"] == "Networking"
        assert doc["prerequisites"] == "Azure CLI, Owner role"

    def test_steps_skip_comments_and_exports(self):
        steps = parse_article(SAMPLE)["steps"]
        assert steps == {"step1": "az login", "step2": "az network fix --now", "verify": "nc -zv host 443"}

    def test_troubleshooting(self):
        assert parse_article(SAMPLE)["troubleshooting"] == {"error": "Connection Refused", "solution": "Open port 443."}

    def test_empty_markdown(self):
        doc = parse_article("")
        assert doc["doc_id"] == "" and doc["steps"]["step1"] == ""

    def test_load_all_generated(self, docs):
        assert len(docs) == 50 and all(all(d["steps"].values()) for d in docs)

    def test_load_missing_dir(self, tmp_path):
        assert load_articles(str(tmp_path / "nope")) == []

    def test_load_skips_other_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("x")
        (tmp_path / "b.md").write_text("no id here")
        assert load_articles(str(tmp_path)) == []


class TestScoringHelpers:
    def test_tokenize_drops_stopwords(self):
        assert tokenize("How to fix the Port 10260") == ["fix", "port", "10260"]

    def test_tokenize_folds_plurals(self):
        assert tokenize("timeouts keys policies access status") == ["timeout", "key", "policy", "access", "status"]

    def test_rrf(self):
        out = rrf({"a": [(1, 9.0), (2, 1.0)], "b": [(2, 5.0)]}, {"a": 1, "b": 1})
        assert out[0][0] == 2

    @pytest.mark.parametrize("norm", ["none", "sigmoid", "minMaxScaler"])
    def test_score_fusion(self, norm):
        out = score_fusion({"a": [(1, 3.0), (2, 1.0)], "b": [(1, 0.9)]}, {"a": 1, "b": 1}, norm)
        assert out[0][0] == 1

    def test_score_fusion_empty(self):
        assert score_fusion({"a": []}, {}, "minMaxScaler") == []


class TestOfflineService:
    def test_capabilities(self, svc):
        caps = svc.capabilities()
        assert caps["mode"] == "offline" and caps["documents"] == 50
        assert all(m["available"] for m in caps["methods"].values())

    @pytest.mark.parametrize("method", ["fulltext", "vector_ann", "vector_enn", "hybrid_rrf", "hybrid_score"])
    def test_finds_the_private_endpoint_article(self, svc, method):
        out = svc.run(method, P.SearchParams(query="private endpoint connection timeout", limit=5))
        assert out["status"] == "ok" and out["offline"] is True
        assert out["results"][0]["doc_id"] == "KB-0016"
        assert out["warnings"][0].startswith("Offline approximation")
        assert out["pipeline"]

    def test_filtered(self, svc):
        out = svc.run("vector_filtered", P.SearchParams(query="search", limit=10, domain="AI"))
        assert out["results"] and all("AI" in r["domain"] for r in out["results"])

    def test_category_filter(self, svc):
        out = svc.run("fulltext", P.SearchParams(query="setup", limit=10, category="Tutorial"))
        assert all(r["category"] == "Tutorial" for r in out["results"])

    def test_rerank_reports_rank_change(self, svc):
        out = svc.run("hybrid_rrf", P.SearchParams(query="port 10260 refused", limit=3, rerank=True))
        assert all(r["pre_rerank_rank"] is not None for r in out["results"])
        assert any("$rerank" in w for w in out["warnings"])

    def test_rerank_with_no_hits(self, svc):
        out = svc.run("fulltext", P.SearchParams(query="zzzqqq", limit=3, rerank=True))
        assert out["results"] == []

    def test_compare(self, svc):
        out = svc.compare(None, P.SearchParams(query="rotate service account keys", limit=5))
        assert out["offline"] and out["agreement"]["ann_recall"] == 1.0

    def test_article_access(self, svc):
        assert svc.get_article("KB-0016")["title"].startswith("Troubleshooting")
        assert svc.get_article("KB-9999") is None
        related = svc.related("AI & Search", exclude="KB-0003")
        assert all(r["doc_id"] != "KB-0003" for r in related)

    def test_facets(self, svc):
        facets = svc.facets()
        assert "Tutorial" in facets["category"] and "Networking" in facets["domain"]
