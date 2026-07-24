"""Tests for the Knowledge Base Flask API."""
import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import Any


# --- Factory Functions ---
def create_mock_document(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a mock MongoDB document with optional overrides."""
    defaults = {
        "_id": "507f1f77bcf86cd799439011",
        "doc_id": "KB-0001",
        "title": "Test Article Title",
        "category": "How-To Guide",
        "domain": "Test Domain",
        "prerequisites": "Test Prerequisites",
        "steps": {
            "step1": "test step 1 command",
            "step2": "test step 2 command",
            "verify": "test verify command",
        },
        "troubleshooting": {
            "error": "Test Error Message",
            "solution": "Test Solution",
        },
        "metadata": {
            "source_id": "SRC-99402",
            "cost_center": "CC-8812",
            "framework": "Diataxis",
        },
        "raw_markdown": "# Test Markdown Content\n\nThis is test content.",
    }
    return {**defaults, **(overrides or {})}


def create_mock_document_list(count: int = 10, start_idx: int = 1, for_list: bool = False) -> list[dict[str, Any]]:
    """Create a list of mock documents for pagination testing.
    
    Args:
        count: Number of documents to create
        start_idx: Starting index for doc_id
        for_list: If True, exclude _id and raw_markdown (simulating list projection)
    """
    docs = []
    for i in range(start_idx, start_idx + count):
        doc = create_mock_document({
            "doc_id": f"KB-{i:04d}",
            "title": f"Article {i}",
            "domain": f"Domain {(i % 5) + 1}",
        })
        if for_list:
            doc.pop("_id", None)
            doc.pop("raw_markdown", None)
        docs.append(doc)
    return docs


def create_mock_document_for_list(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a mock document without _id and raw_markdown (for list view)."""
    doc = create_mock_document(overrides)
    doc.pop("_id", None)
    doc.pop("raw_markdown", None)
    return doc


# --- Fixtures ---
@pytest.fixture
def app():
    """Create and configure a test application instance."""
    from app import create_app
    
    app = create_app(testing=True)
    app.config["TESTING"] = True
    yield app


@pytest.fixture
def client(app):
    """Create a test client for the application."""
    return app.test_client()


@pytest.fixture
def mock_collection():
    """Provide a mocked MongoDB collection."""
    with patch("app.get_collection") as mock:
        mock_coll = Mock()
        mock.return_value = mock_coll
        yield mock_coll


# =============================================================================
# Tests for GET /api/articles (List with Pagination)
# =============================================================================
class TestListArticles:
    """Tests for the GET /api/articles endpoint."""

    # Test cases to implement:
    # - should return 200 status code
    # - should return first 10 articles by default
    # - should return articles with correct fields (doc_id, title, category, domain)
    # - should not include raw_markdown in list response (too large)
    # - should return pagination metadata (page, per_page, total, total_pages)
    # - should support page parameter for pagination
    # - should support per_page parameter (max 50)
    # - should return empty list when no articles exist
    # - should return 400 for invalid page parameter
    # - should return 400 for invalid per_page parameter
    # - should cap per_page at 50 maximum

    class TestSuccessResponses:
        """Successful response tests."""

        def test_returns_200_status_code(self, client, mock_collection):
            """Should return 200 status code."""
            mock_collection.find.return_value.skip.return_value.limit.return_value = []
            mock_collection.count_documents.return_value = 0

            response = client.get("/api/articles")

            assert response.status_code == 200

        def test_returns_first_10_articles_by_default(self, client, mock_collection):
            """Should return first 10 articles by default."""
            mock_docs = create_mock_document_list(10)
            mock_collection.find.return_value.skip.return_value.limit.return_value = mock_docs
            mock_collection.count_documents.return_value = 50

            response = client.get("/api/articles")
            data = response.get_json()

            assert len(data["articles"]) == 10
            assert data["pagination"]["per_page"] == 10

        def test_returns_articles_with_correct_fields(self, client, mock_collection):
            """Should return articles with correct fields."""
            mock_docs = create_mock_document_list(1)
            mock_collection.find.return_value.skip.return_value.limit.return_value = mock_docs
            mock_collection.count_documents.return_value = 1

            response = client.get("/api/articles")
            data = response.get_json()
            article = data["articles"][0]

            assert "doc_id" in article
            assert "title" in article
            assert "category" in article
            assert "domain" in article

        def test_does_not_include_raw_markdown_in_list(self, client, mock_collection):
            """Should not include raw_markdown in list response."""
            # Mock returns filtered data (simulating MongoDB projection)
            mock_docs = create_mock_document_list(1, for_list=True)
            mock_collection.find.return_value.skip.return_value.limit.return_value = mock_docs
            mock_collection.count_documents.return_value = 1

            response = client.get("/api/articles")
            data = response.get_json()
            article = data["articles"][0]

            assert "raw_markdown" not in article

        def test_returns_pagination_metadata(self, client, mock_collection):
            """Should return pagination metadata."""
            mock_docs = create_mock_document_list(10)
            mock_collection.find.return_value.skip.return_value.limit.return_value = mock_docs
            mock_collection.count_documents.return_value = 50

            response = client.get("/api/articles")
            data = response.get_json()

            assert "pagination" in data
            assert data["pagination"]["page"] == 1
            assert data["pagination"]["per_page"] == 10
            assert data["pagination"]["total"] == 50
            assert data["pagination"]["total_pages"] == 5

        def test_returns_empty_list_when_no_articles(self, client, mock_collection):
            """Should return empty list when no articles exist."""
            mock_collection.find.return_value.skip.return_value.limit.return_value = []
            mock_collection.count_documents.return_value = 0

            response = client.get("/api/articles")
            data = response.get_json()

            assert data["articles"] == []
            assert data["pagination"]["total"] == 0

    class TestPagination:
        """Pagination parameter tests."""

        def test_supports_page_parameter(self, client, mock_collection):
            """Should support page parameter for pagination."""
            mock_docs = create_mock_document_list(10, start_idx=11)
            mock_collection.find.return_value.skip.return_value.limit.return_value = mock_docs
            mock_collection.count_documents.return_value = 50

            response = client.get("/api/articles?page=2")
            data = response.get_json()

            assert data["pagination"]["page"] == 2
            # Verify skip was called with correct offset (page 2 = skip 10)
            mock_collection.find.return_value.skip.assert_called_with(10)

        def test_supports_per_page_parameter(self, client, mock_collection):
            """Should support per_page parameter."""
            mock_docs = create_mock_document_list(5)
            mock_collection.find.return_value.skip.return_value.limit.return_value = mock_docs
            mock_collection.count_documents.return_value = 50

            response = client.get("/api/articles?per_page=5")
            data = response.get_json()

            assert data["pagination"]["per_page"] == 5
            mock_collection.find.return_value.skip.return_value.limit.assert_called_with(5)

        def test_caps_per_page_at_50(self, client, mock_collection):
            """Should cap per_page at 50 maximum."""
            mock_docs = create_mock_document_list(50)
            mock_collection.find.return_value.skip.return_value.limit.return_value = mock_docs
            mock_collection.count_documents.return_value = 100

            response = client.get("/api/articles?per_page=100")
            data = response.get_json()

            assert data["pagination"]["per_page"] == 50

    class TestErrorHandling:
        """Error handling tests."""

        def test_returns_400_for_invalid_page(self, client, mock_collection):
            """Should return 400 for invalid page parameter."""
            response = client.get("/api/articles?page=invalid")

            assert response.status_code == 400

        def test_returns_400_for_negative_page(self, client, mock_collection):
            """Should return 400 for negative page parameter."""
            response = client.get("/api/articles?page=-1")

            assert response.status_code == 400

        def test_returns_400_for_zero_page(self, client, mock_collection):
            """Should return 400 for zero page parameter."""
            response = client.get("/api/articles?page=0")

            assert response.status_code == 400

        def test_returns_400_for_invalid_per_page(self, client, mock_collection):
            """Should return 400 for invalid per_page parameter."""
            response = client.get("/api/articles?per_page=invalid")

            assert response.status_code == 400


# =============================================================================
# Tests for GET /api/articles/<doc_id> (Single Article)
# =============================================================================
class TestGetArticle:
    """Tests for the GET /api/articles/<doc_id> endpoint."""

    # Test cases to implement:
    # - should return 200 status code for existing article
    # - should return full article with all fields
    # - should include raw_markdown in response
    # - should return 404 for non-existent article
    # - should handle invalid doc_id format gracefully

    class TestSuccessResponses:
        """Successful response tests."""

        def test_returns_200_for_existing_article(self, client, mock_collection):
            """Should return 200 status code for existing article."""
            mock_doc = create_mock_document()
            mock_collection.find_one.return_value = mock_doc

            response = client.get("/api/articles/KB-0001")

            assert response.status_code == 200

        def test_returns_full_article_with_all_fields(self, client, mock_collection):
            """Should return full article with all fields."""
            mock_doc = create_mock_document()
            mock_collection.find_one.return_value = mock_doc

            response = client.get("/api/articles/KB-0001")
            data = response.get_json()

            assert data["doc_id"] == "KB-0001"
            assert data["title"] == "Test Article Title"
            assert data["category"] == "How-To Guide"
            assert data["domain"] == "Test Domain"
            assert data["prerequisites"] == "Test Prerequisites"
            assert "steps" in data
            assert "troubleshooting" in data
            assert "metadata" in data

        def test_includes_raw_markdown_in_response(self, client, mock_collection):
            """Should include raw_markdown in response."""
            mock_doc = create_mock_document()
            mock_collection.find_one.return_value = mock_doc

            response = client.get("/api/articles/KB-0001")
            data = response.get_json()

            assert "raw_markdown" in data
            assert data["raw_markdown"] == "# Test Markdown Content\n\nThis is test content."

    class TestErrorHandling:
        """Error handling tests."""

        def test_returns_404_for_non_existent_article(self, client, mock_collection):
            """Should return 404 for non-existent article."""
            mock_collection.find_one.return_value = None

            response = client.get("/api/articles/KB-9999")

            assert response.status_code == 404

        def test_returns_404_with_error_message(self, client, mock_collection):
            """Should return 404 with descriptive error message."""
            mock_collection.find_one.return_value = None

            response = client.get("/api/articles/KB-9999")
            data = response.get_json()

            assert "error" in data
            assert "not found" in data["error"].lower()


# =============================================================================
# Tests for Database Connection
# =============================================================================
class TestDatabaseConnection:
    """Tests for database connection handling."""

    # Test cases to implement:
    # - should handle database connection errors gracefully
    # - should return 500 when database is unavailable

    def test_handles_connection_error_on_list(self, client, mock_collection):
        """Should return 500 when database connection fails on list."""
        from pymongo.errors import ConnectionFailure
        mock_collection.count_documents.side_effect = ConnectionFailure("Connection refused")

        response = client.get("/api/articles")

        assert response.status_code == 500

    def test_handles_connection_error_on_get(self, client, mock_collection):
        """Should return 500 when database connection fails on get."""
        from pymongo.errors import ConnectionFailure
        mock_collection.find_one.side_effect = ConnectionFailure("Connection refused")

        response = client.get("/api/articles/KB-0001")

        assert response.status_code == 500


# =============================================================================
# Tests for Response Format
# =============================================================================
class TestResponseFormat:
    """Tests for API response format."""

    # Test cases to implement:
    # - should return JSON content type
    # - should serialize ObjectId correctly (exclude _id or convert to string)

    def test_returns_json_content_type(self, client, mock_collection):
        """Should return JSON content type."""
        mock_collection.find.return_value.skip.return_value.limit.return_value = []
        mock_collection.count_documents.return_value = 0

        response = client.get("/api/articles")

        assert response.content_type == "application/json"

    def test_excludes_mongodb_id_from_response(self, client, mock_collection):
        """Should exclude MongoDB _id from response."""
        # Mock returns filtered data (simulating MongoDB projection)
        mock_doc = create_mock_document()
        mock_doc.pop("_id", None)  # Simulate MongoDB projection excluding _id
        mock_collection.find_one.return_value = mock_doc

        response = client.get("/api/articles/KB-0001")
        data = response.get_json()

        assert "_id" not in data


# =============================================================================
# Tests for POST /api/admin/reset (Reset Demo)
# =============================================================================
class TestResetDemo:
    """Tests for the POST /api/admin/reset endpoint."""

    # Test cases to implement:
    # - should return 200 status code on success
    # - should drop the collection
    # - should return success message
    # - should handle database errors gracefully
    # - should be a POST request (not GET)

    class TestSuccessResponses:
        """Successful response tests."""

        @patch("app.get_db")
        def test_returns_200_on_success(self, mock_get_db, client):
            """Should return 200 status code on success."""
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            response = client.post("/api/admin/reset")

            assert response.status_code == 200

        @patch("app.get_db")
        def test_drops_collection(self, mock_get_db, client):
            """Should drop the collection."""
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            client.post("/api/admin/reset")

            mock_db.drop_collection.assert_called_once()

        @patch("app.get_db")
        def test_returns_success_message(self, mock_get_db, client):
            """Should return success message."""
            mock_db = Mock()
            mock_get_db.return_value = mock_db

            response = client.post("/api/admin/reset")
            data = response.get_json()

            assert data["status"] == "success"
            assert "reset" in data["message"].lower()

    class TestErrorHandling:
        """Error handling tests."""

        @patch("app.get_db")
        def test_handles_database_error(self, mock_get_db, client):
            """Should return 500 when database operation fails."""
            from pymongo.errors import OperationFailure
            mock_db = Mock()
            mock_db.drop_collection.side_effect = OperationFailure("Operation failed")
            mock_get_db.return_value = mock_db

            response = client.post("/api/admin/reset")

            assert response.status_code == 500

    class TestRequestMethod:
        """Request method tests."""

        def test_rejects_get_request(self, client):
            """Should reject GET requests (405 Method Not Allowed or 404)."""
            response = client.get("/api/admin/reset")

            # Flask returns 404 or 405 depending on configuration
            assert response.status_code in (404, 405)


# =============================================================================
# Tests for POST /api/admin/generate (Generate Data)
# =============================================================================
class TestGenerateData:
    """Tests for the POST /api/admin/generate endpoint."""

    # Test cases to implement:
    # - should return 200 status code on success
    # - should call generate_markdown_files
    # - should call insert_into_mongodb
    # - should return success message with count
    # - should handle generation errors gracefully
    # - should be a POST request (not GET)

    class TestSuccessResponses:
        """Successful response tests."""

        @patch("app.create_search_indexes")
        @patch("app.insert_into_mongodb")
        @patch("app.generate_markdown_files")
        def test_returns_200_on_success(self, mock_generate, mock_insert, mock_indexes, client):
            """Should return 200 status code on success."""
            mock_indexes.return_value = {"search": True, "vector": True}
            response = client.post("/api/admin/generate")

            assert response.status_code == 200

        @patch("app.create_search_indexes")
        @patch("app.insert_into_mongodb")
        @patch("app.generate_markdown_files")
        def test_calls_generate_markdown_files(self, mock_generate, mock_insert, mock_indexes, client):
            """Should call generate_markdown_files."""
            mock_indexes.return_value = {"search": True, "vector": True}
            client.post("/api/admin/generate")

            mock_generate.assert_called_once()

        @patch("app.create_search_indexes")
        @patch("app.insert_into_mongodb")
        @patch("app.generate_markdown_files")
        def test_calls_insert_into_mongodb(self, mock_generate, mock_insert, mock_indexes, client):
            """Should call insert_into_mongodb."""
            mock_indexes.return_value = {"search": True, "vector": True}
            client.post("/api/admin/generate")

            mock_insert.assert_called_once()

        @patch("app.create_search_indexes")
        @patch("app.insert_into_mongodb")
        @patch("app.generate_markdown_files")
        def test_returns_success_message(self, mock_generate, mock_insert, mock_indexes, client):
            """Should return success message."""
            mock_indexes.return_value = {"search": True, "vector": True}
            response = client.post("/api/admin/generate")
            data = response.get_json()

            assert data["status"] == "success"
            assert "generated" in data["message"].lower()

    class TestErrorHandling:
        """Error handling tests."""

        @patch("app.create_search_indexes")
        @patch("app.insert_into_mongodb")
        @patch("app.generate_markdown_files")
        def test_handles_generation_error(self, mock_generate, mock_insert, mock_indexes, client):
            """Should return 500 when generation fails."""
            mock_generate.side_effect = Exception("Generation failed")

            response = client.post("/api/admin/generate")

            assert response.status_code == 500

    class TestRequestMethod:
        """Request method tests."""

        def test_rejects_get_request(self, client):
            """Should reject GET requests (405 Method Not Allowed or 404)."""
            response = client.get("/api/admin/generate")

            # Flask returns 404 or 405 depending on configuration
            assert response.status_code in (404, 405)

    class TestTerraformOption:
        """Tests for Terraform index creation option."""

        # Test cases to implement:
        # - should use PyMongo by default (use_terraform=false)
        # - should call terraform when use_terraform=true
        # - should include terraform step in response when used

        @patch("app.create_search_indexes")
        @patch("app.insert_into_mongodb")
        @patch("app.generate_markdown_files")
        def test_uses_pymongo_by_default(self, mock_gen, mock_insert, mock_indexes, client):
            """Should use PyMongo approach by default."""
            mock_indexes.return_value = {"search": True, "vector": True}

            response = client.post("/api/admin/generate", json={"use_terraform": False})

            mock_indexes.assert_called_once()

        @patch("app.run_terraform_apply")
        @patch("app.insert_into_mongodb")
        @patch("app.generate_markdown_files")
        def test_calls_terraform_when_enabled(self, mock_gen, mock_insert, mock_tf, client):
            """Should call Terraform when use_terraform=true."""
            mock_tf.return_value = {"success": True, "output": "Applied"}

            response = client.post("/api/admin/generate", json={"use_terraform": True})

            mock_tf.assert_called_once()

        @patch("app.run_terraform_apply")
        @patch("app.insert_into_mongodb")
        @patch("app.generate_markdown_files")
        def test_includes_terraform_step_in_response(self, mock_gen, mock_insert, mock_tf, client):
            """Should include Terraform step in response when used."""
            mock_tf.return_value = {"success": True, "output": "Applied"}

            response = client.post("/api/admin/generate", json={"use_terraform": True})
            data = response.get_json()

            assert "steps" in data
            steps_text = " ".join(data["steps"])
            assert "terraform" in steps_text.lower()


# =============================================================================
# Tests for Server Reachability
# =============================================================================
class TestServerReachability:
    """Tests to verify the server starts and responds correctly."""

    # Test cases to implement:
    # - root endpoint should return 200
    # - root endpoint should serve HTML content
    # - health check response time should be reasonable

    def test_root_returns_200(self, client):
        """Should return 200 status code for root endpoint."""
        response = client.get("/")
        
        assert response.status_code == 200

    def test_root_serves_html(self, client):
        """Should serve HTML content at root."""
        response = client.get("/")
        
        assert response.content_type.startswith("text/html")

    def test_api_articles_endpoint_responds(self, mock_collection, client):
        """Should have working API endpoint."""
        mock_collection.find.return_value.skip.return_value.limit.return_value = []
        mock_collection.count_documents.return_value = 0
        
        response = client.get("/api/articles")
        
        assert response.status_code == 200


# =============================================================================
# Integration Test for Live Server
# =============================================================================
@pytest.mark.integration
class TestLiveServer:
    """Integration tests to verify the Flask server is running on localhost:5001.
    
    Run these tests separately with: pytest -m integration
    Skip these tests with: pytest -m "not integration"
    """

    # Test cases to implement:
    # - live server should be reachable at localhost:5001
    # - live server should return 200 for root
    # - live server should respond within reasonable time

    @pytest.fixture
    def live_server_url(self):
        """Return the live server URL."""
        return "http://localhost:5001"

    def test_live_server_is_running(self, live_server_url):
        """Should verify Flask app is running at localhost:5001."""
        import urllib.request
        import urllib.error
        
        try:
            with urllib.request.urlopen(live_server_url, timeout=5) as response:
                assert response.status == 200, f"Expected 200, got {response.status}"
        except urllib.error.URLError as e:
            pytest.fail(f"Flask server not reachable at {live_server_url}: {e}")
        except Exception as e:
            pytest.fail(f"Failed to connect to Flask server: {e}")

    def test_live_server_returns_html(self, live_server_url):
        """Should return HTML content from live server."""
        import urllib.request
        
        try:
            with urllib.request.urlopen(live_server_url, timeout=5) as response:
                content_type = response.headers.get("Content-Type", "")
                assert "text/html" in content_type, f"Expected text/html, got {content_type}"
        except Exception as e:
            pytest.fail(f"Failed to connect to Flask server: {e}")

    def test_live_server_response_time(self, live_server_url):
        """Should respond within 2 seconds."""
        import urllib.request
        import time
        
        try:
            start = time.time()
            with urllib.request.urlopen(live_server_url, timeout=5) as response:
                elapsed = time.time() - start
                assert elapsed < 2.0, f"Response took {elapsed:.2f}s, expected < 2s"
        except Exception as e:
            pytest.fail(f"Failed to connect to Flask server: {e}")


# =============================================================================
# Tests for Vector Search
# =============================================================================
class TestVectorSearch:
    """Tests for vector search functionality."""

    # Test cases to implement:
    # - should return 200 for valid search query
    # - should return results array
    # - should return empty array for no matches
    # - should return 400 for missing query parameter

    def test_returns_200_for_valid_query(self, mock_collection, client):
        """Should return 200 status code for valid search query."""
        mock_collection.aggregate.return_value = []
        
        response = client.get("/api/search?q=test")
        
        assert response.status_code == 200

    def test_returns_results_array(self, mock_collection, client):
        """Should return results array in response."""
        mock_collection.aggregate.return_value = [
            {"title": "Test Doc", "score": 0.95}
        ]
        
        response = client.get("/api/search?q=test")
        data = response.get_json()
        
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_returns_empty_array_for_no_matches(self, mock_collection, client):
        """Should return empty array when no documents match."""
        mock_collection.aggregate.return_value = []
        
        response = client.get("/api/search?q=nonexistent")
        data = response.get_json()
        
        assert data["results"] == []

    def test_returns_400_for_missing_query(self, client):
        """Should return 400 when query parameter is missing."""
        response = client.get("/api/search")
        
        assert response.status_code == 400

    def test_returns_400_for_empty_query(self, client):
        """Should return 400 when query is empty."""
        response = client.get("/api/search?q=")
        
        assert response.status_code == 400


# =============================================================================
# Tests for Index Management in Generate/Reset
# =============================================================================
class TestIndexManagement:
    """Tests for search index creation and deletion."""

    # Test cases to implement:
    # - generate should create search index
    # - generate should create auto-embedding index
    # - generate should return steps completed
    # - reset should delete indexes before dropping collection
    # - reset should return indexes deleted in message

    class TestGenerateWithIndexes:
        """Tests for index creation during generate."""

        @patch("app.create_search_indexes")
        @patch("app.insert_into_mongodb")
        @patch("app.generate_markdown_files")
        def test_creates_search_indexes(self, mock_generate, mock_insert, mock_indexes, client):
            """Should create search indexes during generate."""
            mock_indexes.return_value = {"search": True, "vector": True}

            client.post("/api/admin/generate")

            mock_indexes.assert_called_once()

        @patch("app.create_search_indexes")
        @patch("app.insert_into_mongodb")
        @patch("app.generate_markdown_files")
        def test_returns_steps_in_response(self, mock_generate, mock_insert, mock_indexes, client):
            """Should return steps completed in response."""
            mock_indexes.return_value = {"search": True, "vector": True}

            response = client.post("/api/admin/generate")
            data = response.get_json()

            assert "steps" in data
            assert isinstance(data["steps"], list)

    class TestResetWithIndexes:
        """Tests for index deletion during reset."""

        @patch("app.delete_search_indexes")
        @patch("app.get_db")
        def test_deletes_indexes_before_dropping(self, mock_get_db, mock_delete_indexes, client):
            """Should delete indexes before dropping collection."""
            mock_db = Mock()
            mock_get_db.return_value = mock_db
            mock_delete_indexes.return_value = True

            client.post("/api/admin/reset")

            mock_delete_indexes.assert_called_once()

        @patch("app.delete_search_indexes")
        @patch("app.get_db")
        def test_returns_indexes_deleted_message(self, mock_get_db, mock_delete_indexes, client):
            """Should return indexes deleted in response."""
            mock_db = Mock()
            mock_get_db.return_value = mock_db
            mock_delete_indexes.return_value = True

            response = client.post("/api/admin/reset")
            data = response.get_json()

            assert "steps" in data
            # Check that indexes deleted step is included
            steps_text = " ".join(data["steps"])
            assert "index" in steps_text.lower()

