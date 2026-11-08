"""Shared fixtures for the v2 tests."""
import pytest

from kbase.search.docs import load_articles
from kbase.search.offline import OfflineSearchService
from kbase.search.pipelines import IndexConfig


@pytest.fixture(scope="session")
def articles():
    return load_articles("md_docs")


@pytest.fixture
def offline_kb(articles):
    return OfflineSearchService(articles, IndexConfig(), default_query_model="voyage-4-lite",
                                default_rerank_model="rerank-2.5-lite")
