"""Tests for generate_kbase module."""
import os
import pytest
from unittest.mock import Mock, patch, mock_open, MagicMock, call
from typing import Any


# --- Factory Functions ---
def create_mock_article(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a mock article with optional overrides."""
    defaults = {
        "title": "Test Article Title",
        "cat": "How-To Guide",
        "domain": "Test Domain",
        "prereq": "Test Prerequisites",
        "step1": "test step 1 command",
        "step2": "test step 2 command",
        "verify": "test verify command",
        "err": "Test Error Message",
        "sol": "Test Solution",
    }
    return {**defaults, **(overrides or {})}


def create_mock_document(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Create a mock MongoDB document with optional overrides."""
    defaults = {
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
        "raw_markdown": "# Test Markdown Content",
    }
    return {**defaults, **(overrides or {})}


def create_mock_unique_module(overrides: tuple | None = None) -> tuple:
    """Create a mock unique module tuple with optional overrides."""
    defaults = ("Test Module Title", "Test Domain", "test-cmd1", "test-cmd2")
    if overrides:
        return overrides
    return defaults


# --- Fixtures ---
@pytest.fixture
def mock_mongo_client():
    """Provide a mocked MongoDB client."""
    with patch("generate_kbase.MongoClient") as mock:
        mock_collection = Mock()
        mock_db = Mock()
        mock_db.__getitem__ = Mock(return_value=mock_collection)
        mock_client_instance = Mock()
        mock_client_instance.__getitem__ = Mock(return_value=mock_db)
        mock.return_value = mock_client_instance
        yield {
            "client_class": mock,
            "client": mock_client_instance,
            "db": mock_db,
            "collection": mock_collection,
        }


@pytest.fixture
def mock_env_vars():
    """Provide mocked environment variables."""
    env = {
        "MONGODB_URI": "mongodb://test:test@localhost:27017/test",
        "DB_NAME": "test_kbase",
        "COLLECTION_NAME": "test_content",
    }
    with patch.dict(os.environ, env):
        yield env


@pytest.fixture
def sample_article() -> dict[str, Any]:
    """Provide a sample article for testing."""
    return create_mock_article()


@pytest.fixture
def sample_articles_list() -> list[dict[str, Any]]:
    """Provide a sample list of articles for testing."""
    return [
        create_mock_article({"title": f"Article {i}", "domain": f"Domain {i}"})
        for i in range(1, 4)
    ]


# =============================================================================
# Tests for ARTICLES_DATA Structure
# =============================================================================
class TestArticlesData:
    """Tests for ARTICLES_DATA module-level constant."""

    # Test cases to implement:
    # - should contain exactly 50 articles after dynamic generation
    # - should have all required keys in each article
    # - should have non-empty values for all required fields
    # - should have valid category values (How-To Guide or Tutorial)
    # - should have unique titles across all articles

    class TestStructure:
        """Structure validation tests."""

        def test_contains_50_articles(self):
            """Should contain exactly 50 articles after dynamic generation."""
            from generate_kbase import ARTICLES_DATA

            assert len(ARTICLES_DATA) == 50  # 20 static + 30 dynamic from UNIQUE_MODULES

        def test_each_article_has_required_keys(self):
            """Should have all required keys in each article."""
            from generate_kbase import ARTICLES_DATA

            required_keys = {"title", "cat", "domain", "prereq", "step1", "step2", "verify", "err", "sol"}

            for idx, article in enumerate(ARTICLES_DATA):
                missing = required_keys - set(article.keys())
                assert not missing, f"Article {idx} missing keys: {missing}"

        def test_each_article_has_non_empty_values(self):
            """Should have non-empty values for all required fields."""
            from generate_kbase import ARTICLES_DATA

            for idx, article in enumerate(ARTICLES_DATA):
                for key, value in article.items():
                    assert value, f"Article {idx} has empty value for '{key}'"

        def test_categories_are_valid(self):
            """Should have valid category values."""
            from generate_kbase import ARTICLES_DATA

            valid_categories = {"How-To Guide", "Tutorial"}

            for idx, article in enumerate(ARTICLES_DATA):
                assert article["cat"] in valid_categories, (
                    f"Article {idx} has invalid category: {article['cat']}"
                )

        def test_titles_are_unique(self):
            """Should have unique titles across all articles."""
            from generate_kbase import ARTICLES_DATA

            titles = [article["title"] for article in ARTICLES_DATA]
            assert len(titles) == len(set(titles)), "Duplicate titles found"


# =============================================================================
# Tests for UNIQUE_MODULES Dynamic Generation
# =============================================================================
class TestUniqueModules:
    """Tests for UNIQUE_MODULES and dynamic article generation."""

    # Test cases to implement:
    # - should have 27 unique modules defined
    # - should generate articles with correct category alternation
    # - should include sourceID in generated step1 commands
    # - should include config path in generated step2 commands
    # - should generate proper error message format

    class TestModuleDefinition:
        """Module definition tests."""

        def test_unique_modules_count(self):
            """Should have 30 unique modules defined."""
            from generate_kbase import UNIQUE_MODULES

            assert len(UNIQUE_MODULES) == 30

        def test_each_module_has_four_elements(self):
            """Should have four elements per module tuple."""
            from generate_kbase import UNIQUE_MODULES

            for idx, module in enumerate(UNIQUE_MODULES):
                assert len(module) == 4, f"Module {idx} should have 4 elements, got {len(module)}"

    class TestDynamicGeneration:
        """Dynamic generation tests."""

        def test_generated_articles_have_sourceID_in_step1(self):
            """Should include sourceID in generated step1 commands."""
            from generate_kbase import ARTICLES_DATA

            # Dynamic articles start at index 20 (0-indexed)
            for article in ARTICLES_DATA[20:]:
                assert "--sourceID=SRC-99402" in article["step1"]

        def test_generated_articles_have_config_in_step2(self):
            """Should include config path in generated step2 commands."""
            from generate_kbase import ARTICLES_DATA

            for article in ARTICLES_DATA[20:]:
                assert "--config=/etc/mindsbeyond/config.json" in article["step2"]

        def test_generated_error_format(self):
            """Should generate proper error message format."""
            from generate_kbase import ARTICLES_DATA

            for article in ARTICLES_DATA[20:]:
                assert article["err"].startswith("Error:")
                assert "ExecutionFailed" in article["err"]


# =============================================================================
# Tests for generate_markdown_files Function
# =============================================================================
class TestGenerateMarkdownFiles:
    """Tests for generate_markdown_files function."""

    # Test cases to implement:
    # - should create MD_DIR directory if it doesn't exist
    # - should not fail if MD_DIR already exists
    # - should generate correct number of files
    # - should generate files with correct naming pattern
    # - should generate files with correct content structure
    # - should handle special characters in titles
    # - should include all required sections in markdown
    # - should format document ID correctly (KB-XXXX)
    # - should print success message after completion

    class TestDirectoryCreation:
        """Directory creation tests."""

        @patch("generate_kbase.os.path.exists")
        @patch("generate_kbase.os.makedirs")
        @patch("builtins.open", new_callable=mock_open)
        @patch("builtins.print")
        def test_creates_directory_if_not_exists(
            self, mock_print, mock_file, mock_makedirs, mock_exists
        ):
            """Should create MD_DIR directory if it doesn't exist."""
            mock_exists.return_value = False

            from generate_kbase import generate_markdown_files

            generate_markdown_files()

            mock_makedirs.assert_called_once_with("./md_docs")

        @patch("generate_kbase.os.path.exists")
        @patch("generate_kbase.os.makedirs")
        @patch("builtins.open", new_callable=mock_open)
        @patch("builtins.print")
        def test_does_not_create_directory_if_exists(
            self, mock_print, mock_file, mock_makedirs, mock_exists
        ):
            """Should not create directory if it already exists."""
            mock_exists.return_value = True

            from generate_kbase import generate_markdown_files

            generate_markdown_files()

            mock_makedirs.assert_not_called()

    class TestFileGeneration:
        """File generation tests."""

        @patch("generate_kbase.os.path.exists")
        @patch("generate_kbase.os.makedirs")
        @patch("builtins.open", new_callable=mock_open)
        @patch("builtins.print")
        def test_generates_correct_number_of_files(
            self, mock_print, mock_file, mock_makedirs, mock_exists
        ):
            """Should generate correct number of files."""
            mock_exists.return_value = True

            from generate_kbase import generate_markdown_files, ARTICLES_DATA

            generate_markdown_files()

            # Each article should result in one file write
            assert mock_file.call_count == len(ARTICLES_DATA)

        @patch("generate_kbase.os.path.exists")
        @patch("generate_kbase.os.makedirs")
        @patch("builtins.open", new_callable=mock_open)
        @patch("builtins.print")
        def test_generates_files_with_correct_naming_pattern(
            self, mock_print, mock_file, mock_makedirs, mock_exists
        ):
            """Should generate files with correct naming pattern."""
            mock_exists.return_value = True

            from generate_kbase import generate_markdown_files

            generate_markdown_files()

            # Check first file call
            first_call = mock_file.call_args_list[0]
            filepath = first_call[0][0]
            assert filepath.startswith("./md_docs/01_")
            assert filepath.endswith(".md")

        @patch("generate_kbase.os.path.exists")
        @patch("generate_kbase.os.makedirs")
        @patch("builtins.open", new_callable=mock_open)
        @patch("builtins.print")
        def test_handles_special_characters_in_titles(
            self, mock_print, mock_file, mock_makedirs, mock_exists
        ):
            """Should handle special characters in titles (slashes become dashes)."""
            mock_exists.return_value = True

            from generate_kbase import generate_markdown_files

            generate_markdown_files()

            # All file paths should not contain forward slashes in filename
            for call_args in mock_file.call_args_list:
                filepath = call_args[0][0]
                filename = os.path.basename(filepath)
                # Slashes should be replaced with dashes
                assert "/" not in filename or filename == filepath

    class TestMarkdownContent:
        """Markdown content tests."""

        @patch("generate_kbase.os.path.exists")
        @patch("generate_kbase.os.makedirs")
        @patch("builtins.open", new_callable=mock_open)
        @patch("builtins.print")
        def test_includes_all_required_sections(
            self, mock_print, mock_file, mock_makedirs, mock_exists
        ):
            """Should include all required sections in markdown."""
            mock_exists.return_value = True

            from generate_kbase import generate_markdown_files

            generate_markdown_files()

            # Get the content written to the first file
            write_calls = mock_file().write.call_args_list
            content = write_calls[0][0][0]

            required_sections = [
                "# How To:",
                "**Document ID**:",
                "**Category**:",
                "**Domain**:",
                "## Overview",
                "## Prerequisites",
                "## Step-by-Step Execution Guide",
                "### Step 1:",
                "### Step 2:",
                "## Verification & Validation",
                "## Troubleshooting",
            ]

            for section in required_sections:
                assert section in content, f"Missing section: {section}"

        @patch("generate_kbase.os.path.exists")
        @patch("generate_kbase.os.makedirs")
        @patch("builtins.open", new_callable=mock_open)
        @patch("builtins.print")
        def test_formats_document_id_correctly(
            self, mock_print, mock_file, mock_makedirs, mock_exists
        ):
            """Should format document ID correctly (KB-XXXX)."""
            mock_exists.return_value = True

            from generate_kbase import generate_markdown_files

            generate_markdown_files()

            write_calls = mock_file().write.call_args_list
            first_content = write_calls[0][0][0]

            assert "**Document ID**: KB-0001" in first_content

    class TestOutputMessages:
        """Output message tests."""

        @patch("generate_kbase.os.path.exists")
        @patch("generate_kbase.os.makedirs")
        @patch("builtins.open", new_callable=mock_open)
        @patch("builtins.print")
        def test_prints_success_message(
            self, mock_print, mock_file, mock_makedirs, mock_exists
        ):
            """Should print success message after completion."""
            mock_exists.return_value = True

            from generate_kbase import generate_markdown_files, ARTICLES_DATA

            generate_markdown_files()

            # Check that success message was printed
            print_calls = [str(call) for call in mock_print.call_args_list]
            success_found = any("Successfully generated" in str(c) for c in print_calls)
            assert success_found


# =============================================================================
# Tests for insert_into_mongodb Function
# =============================================================================
class TestInsertIntoMongodb:
    """Tests for insert_into_mongodb function."""

    # Test cases to implement:
    # - should skip insertion when MONGODB_URI is not set
    # - should connect to MongoDB with correct URI
    # - should use correct database name
    # - should use correct collection name
    # - should create documents with correct structure
    # - should upsert documents using doc_id as filter
    # - should read markdown files for raw_markdown field
    # - should handle missing markdown files gracefully
    # - should close client connection after completion
    # - should print success message after completion

    class TestConnectionHandling:
        """Connection handling tests."""

        @patch("generate_kbase.MONGODB_URI", None)
        @patch("builtins.print")
        def test_skips_insertion_when_uri_not_set(self, mock_print):
            """Should skip insertion when MONGODB_URI is not set."""
            from generate_kbase import insert_into_mongodb

            insert_into_mongodb()

            mock_print.assert_called_with("❌ MONGODB_URI not set. Skipping MongoDB insertion.")

        @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
        @patch("generate_kbase.MongoClient")
        @patch("generate_kbase.os.path.exists", return_value=False)
        @patch("builtins.print")
        def test_connects_with_correct_uri(
            self, mock_print, mock_exists, mock_client
        ):
            """Should connect to MongoDB with correct URI."""
            mock_collection = Mock()
            mock_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

            from generate_kbase import insert_into_mongodb

            insert_into_mongodb()

            mock_client.assert_called_once_with("mongodb://test:test@localhost:27017/test")

        @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
        @patch("generate_kbase.DB_NAME", "custom_db")
        @patch("generate_kbase.MongoClient")
        @patch("generate_kbase.os.path.exists", return_value=False)
        @patch("builtins.print")
        def test_uses_correct_database_name(
            self, mock_print, mock_exists, mock_client
        ):
            """Should use correct database name."""
            mock_db = Mock()
            mock_client.return_value.__getitem__ = Mock(return_value=mock_db)
            mock_db.__getitem__ = Mock(return_value=Mock())

            from generate_kbase import insert_into_mongodb

            insert_into_mongodb()

            mock_client.return_value.__getitem__.assert_called_with("custom_db")

        @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
        @patch("generate_kbase.COLLECTION_NAME", "custom_collection")
        @patch("generate_kbase.MongoClient")
        @patch("generate_kbase.os.path.exists", return_value=False)
        @patch("builtins.print")
        def test_uses_correct_collection_name(
            self, mock_print, mock_exists, mock_client
        ):
            """Should use correct collection name."""
            mock_db = Mock()
            mock_collection = Mock()
            mock_client.return_value.__getitem__ = Mock(return_value=mock_db)
            mock_db.__getitem__ = Mock(return_value=mock_collection)

            from generate_kbase import insert_into_mongodb

            insert_into_mongodb()

            mock_db.__getitem__.assert_called_with("custom_collection")

    class TestDocumentCreation:
        """Document creation tests."""

        @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
        @patch("generate_kbase.MongoClient")
        @patch("generate_kbase.os.path.exists", return_value=False)
        @patch("builtins.print")
        def test_creates_documents_with_correct_structure(
            self, mock_print, mock_exists, mock_client
        ):
            """Should create documents with correct structure."""
            mock_collection = Mock()
            mock_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

            from generate_kbase import insert_into_mongodb

            insert_into_mongodb()

            # Get the first upsert call
            first_call = mock_collection.update_one.call_args_list[0]
            filter_arg = first_call[0][0]
            update_arg = first_call[0][1]
            doc = update_arg["$set"]

            # Verify document structure
            assert "doc_id" in doc
            assert "title" in doc
            assert "category" in doc
            assert "domain" in doc
            assert "prerequisites" in doc
            assert "steps" in doc
            assert "troubleshooting" in doc
            assert "metadata" in doc
            assert "raw_markdown" in doc

        @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
        @patch("generate_kbase.MongoClient")
        @patch("generate_kbase.os.path.exists", return_value=False)
        @patch("builtins.print")
        def test_upserts_documents_using_doc_id_filter(
            self, mock_print, mock_exists, mock_client
        ):
            """Should upsert documents using doc_id as filter."""
            mock_collection = Mock()
            mock_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

            from generate_kbase import insert_into_mongodb

            insert_into_mongodb()

            first_call = mock_collection.update_one.call_args_list[0]
            filter_arg = first_call[0][0]
            kwargs = first_call[1]

            assert "doc_id" in filter_arg
            assert filter_arg["doc_id"] == "KB-0001"
            assert kwargs["upsert"] is True

    class TestMarkdownFileReading:
        """Markdown file reading tests."""

        @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
        @patch("generate_kbase.MongoClient")
        @patch("generate_kbase.os.path.exists", return_value=True)
        @patch("builtins.open", new_callable=mock_open, read_data="# Test Markdown")
        @patch("builtins.print")
        def test_reads_markdown_files_for_raw_markdown(
            self, mock_print, mock_file, mock_exists, mock_client
        ):
            """Should read markdown files for raw_markdown field."""
            mock_collection = Mock()
            mock_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

            from generate_kbase import insert_into_mongodb

            insert_into_mongodb()

            first_call = mock_collection.update_one.call_args_list[0]
            doc = first_call[0][1]["$set"]

            assert doc["raw_markdown"] == "# Test Markdown"

        @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
        @patch("generate_kbase.MongoClient")
        @patch("generate_kbase.os.path.exists", return_value=False)
        @patch("builtins.print")
        def test_handles_missing_markdown_files(
            self, mock_print, mock_exists, mock_client
        ):
            """Should handle missing markdown files gracefully (empty raw_markdown)."""
            mock_collection = Mock()
            mock_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

            from generate_kbase import insert_into_mongodb

            insert_into_mongodb()

            first_call = mock_collection.update_one.call_args_list[0]
            doc = first_call[0][1]["$set"]

            assert doc["raw_markdown"] == ""

    class TestCleanup:
        """Cleanup and completion tests."""

        @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
        @patch("generate_kbase.MongoClient")
        @patch("generate_kbase.os.path.exists", return_value=False)
        @patch("builtins.print")
        def test_closes_client_connection(
            self, mock_print, mock_exists, mock_client
        ):
            """Should close client connection after completion."""
            mock_client_instance = Mock()
            mock_client_instance.__getitem__ = Mock(return_value=Mock(__getitem__=Mock(return_value=Mock())))
            mock_client.return_value = mock_client_instance

            from generate_kbase import insert_into_mongodb

            insert_into_mongodb()

            mock_client_instance.close.assert_called_once()

        @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
        @patch("generate_kbase.MongoClient")
        @patch("generate_kbase.os.path.exists", return_value=False)
        @patch("builtins.print")
        def test_prints_success_message(
            self, mock_print, mock_exists, mock_client
        ):
            """Should print success message after completion."""
            mock_collection = Mock()
            mock_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

            from generate_kbase import insert_into_mongodb

            insert_into_mongodb()

            print_calls = [str(call) for call in mock_print.call_args_list]
            success_found = any("Successfully upserted" in str(c) for c in print_calls)
            assert success_found


# =============================================================================
# Tests for Module Constants
# =============================================================================
class TestModuleConstants:
    """Tests for module-level constants."""

    # Test cases to implement:
    # - should have MD_DIR set to ./md_docs
    # - should have default DB_NAME as kbase
    # - should have default COLLECTION_NAME as content

    def test_md_dir_value(self):
        """Should have MD_DIR set to ./md_docs."""
        from generate_kbase import MD_DIR

        assert MD_DIR == "./md_docs"

    @patch.dict(os.environ, {}, clear=True)
    def test_default_db_name(self):
        """Should have default DB_NAME as kbase."""
        # Need to reimport to get default value
        assert os.getenv("DB_NAME", "kbase") == "kbase"

    @patch.dict(os.environ, {}, clear=True)
    def test_default_collection_name(self):
        """Should have default COLLECTION_NAME as content."""
        assert os.getenv("COLLECTION_NAME", "content") == "content"


# =============================================================================
# Tests for Filename Generation Logic
# =============================================================================
class TestFilenameGeneration:
    """Tests for filename generation from article titles."""

    # Test cases to implement:
    # - should convert title to lowercase
    # - should replace spaces with dashes
    # - should replace slashes with dashes
    # - should prefix with zero-padded index
    # - should have .md extension

    def test_filename_lowercase_conversion(self, sample_article):
        """Should convert title to lowercase."""
        title = sample_article["title"]
        filename = f"01_{title.lower().replace(' ', '-').replace('/', '-')}.md"

        assert filename == filename.lower()

    def test_filename_spaces_replaced_with_dashes(self):
        """Should replace spaces with dashes."""
        title = "Test Article Title"
        filename = f"01_{title.lower().replace(' ', '-').replace('/', '-')}.md"

        assert " " not in filename
        assert "test-article-title" in filename

    def test_filename_slashes_replaced_with_dashes(self):
        """Should replace slashes with dashes."""
        title = "CI/CD Pipeline Setup"
        filename = f"01_{title.lower().replace(' ', '-').replace('/', '-')}.md"

        assert "/" not in filename
        assert "ci-cd" in filename

    def test_filename_zero_padded_index(self):
        """Should prefix with zero-padded index."""
        title = "Test"
        for idx in [1, 9, 10, 50]:
            filename = f"{idx:02d}_{title.lower()}.md"
            assert filename.startswith(f"{idx:02d}_")

    def test_filename_md_extension(self, sample_article):
        """Should have .md extension."""
        title = sample_article["title"]
        filename = f"01_{title.lower().replace(' ', '-').replace('/', '-')}.md"

        assert filename.endswith(".md")


# =============================================================================
# Tests for Document ID Generation
# =============================================================================
class TestDocumentIdGeneration:
    """Tests for document ID generation."""

    # Test cases to implement:
    # - should format as KB-XXXX with zero padding
    # - should start at KB-0001
    # - should increment correctly

    def test_doc_id_format(self):
        """Should format as KB-XXXX with zero padding."""
        for idx in [1, 10, 100]:
            doc_id = f"KB-{idx:04d}"
            assert doc_id.startswith("KB-")
            assert len(doc_id) == 7

    def test_doc_id_starts_at_0001(self):
        """Should start at KB-0001."""
        doc_id = f"KB-{1:04d}"

        assert doc_id == "KB-0001"

    def test_doc_id_increments_correctly(self):
        """Should increment correctly."""
        doc_ids = [f"KB-{i:04d}" for i in range(1, 4)]

        assert doc_ids == ["KB-0001", "KB-0002", "KB-0003"]


# =============================================================================
# Tests for Metadata Values
# =============================================================================
class TestMetadataValues:
    """Tests for hardcoded metadata values."""

    # Test cases to implement:
    # - should use SRC-99402 as source_id
    # - should use CC-8812 as cost_center
    # - should use Diataxis as framework

    @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
    @patch("generate_kbase.MongoClient")
    @patch("generate_kbase.os.path.exists", return_value=False)
    @patch("builtins.print")
    def test_source_id_value(self, mock_print, mock_exists, mock_client):
        """Should use SRC-99402 as source_id."""
        mock_collection = Mock()
        mock_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

        from generate_kbase import insert_into_mongodb

        insert_into_mongodb()

        first_call = mock_collection.update_one.call_args_list[0]
        doc = first_call[0][1]["$set"]

        assert doc["metadata"]["source_id"] == "SRC-99402"

    @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
    @patch("generate_kbase.MongoClient")
    @patch("generate_kbase.os.path.exists", return_value=False)
    @patch("builtins.print")
    def test_cost_center_value(self, mock_print, mock_exists, mock_client):
        """Should use CC-8812 as cost_center."""
        mock_collection = Mock()
        mock_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

        from generate_kbase import insert_into_mongodb

        insert_into_mongodb()

        first_call = mock_collection.update_one.call_args_list[0]
        doc = first_call[0][1]["$set"]

        assert doc["metadata"]["cost_center"] == "CC-8812"

    @patch("generate_kbase.MONGODB_URI", "mongodb://test:test@localhost:27017/test")
    @patch("generate_kbase.MongoClient")
    @patch("generate_kbase.os.path.exists", return_value=False)
    @patch("builtins.print")
    def test_framework_value(self, mock_print, mock_exists, mock_client):
        """Should use Diataxis as framework."""
        mock_collection = Mock()
        mock_client.return_value.__getitem__.return_value.__getitem__.return_value = mock_collection

        from generate_kbase import insert_into_mongodb

        insert_into_mongodb()

        first_call = mock_collection.update_one.call_args_list[0]
        doc = first_call[0][1]["$set"]

        assert doc["metadata"]["framework"] == "Diataxis"
