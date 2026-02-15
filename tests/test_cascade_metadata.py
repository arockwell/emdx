"""Tests for cascade metadata extraction and the new cascade database module."""

import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="function")
def test_db_path():
    """Create a temporary database path for testing.

    Using function scope to ensure each test gets a fresh database.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    # Cleanup
    if db_path.exists():
        db_path.unlink()


@pytest.fixture(scope="function")
def setup_test_db(test_db_path, monkeypatch):
    """Set up a test database with migrations run.

    Using function scope to ensure each test gets a fresh database.
    """
    # Set the test database environment variable
    monkeypatch.setenv("EMDX_TEST_DB", str(test_db_path))

    # Import and run migrations
    from emdx.database.connection import DatabaseConnection
    from emdx.database.migrations import run_migrations

    run_migrations(test_db_path)

    # Create a new connection instance for the test db
    conn_instance = DatabaseConnection(test_db_path)

    # Patch the global db_connection in all relevant modules
    import emdx.database.cascade as cascade_module
    import emdx.database.connection as conn_module
    import emdx.database.documents as docs_module

    original_conn = conn_module.db_connection

    # Patch in all modules that use db_connection
    conn_module.db_connection = conn_instance
    docs_module.db_connection = conn_instance
    cascade_module.db_connection = conn_instance

    yield conn_instance

    # Restore original
    conn_module.db_connection = original_conn
    docs_module.db_connection = original_conn
    cascade_module.db_connection = original_conn


class TestMigrationCreatesTable:
    """Test that the migration creates the cascade metadata table correctly."""

    def test_table_exists(self, setup_test_db):
        """Test that document_cascade_metadata table is created."""
        with setup_test_db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='document_cascade_metadata'"
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "document_cascade_metadata"

    def test_table_schema(self, setup_test_db):
        """Test the table has correct columns."""
        with setup_test_db.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(document_cascade_metadata)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}

            assert "id" in columns
            assert "document_id" in columns
            assert "stage" in columns
            assert "pr_url" in columns
            assert "created_at" in columns
            assert "updated_at" in columns

    def test_indexes_exist(self, setup_test_db):
        """Test that partial indexes are created."""
        with setup_test_db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='document_cascade_metadata'"
            )
            indexes = {row[0] for row in cursor.fetchall()}

            assert "idx_cascade_meta_stage" in indexes
            assert "idx_cascade_meta_pr_url" in indexes
            assert "idx_cascade_meta_document_id" in indexes


class TestCascadeMetadataBackfill:
    """Test that existing cascade data is backfilled correctly."""

    def test_backfill_stage_data(self, setup_test_db):
        """Test that documents with stage are backfilled."""
        # First create a document with stage directly in documents table
        with setup_test_db.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO documents (title, content, stage) VALUES (?, ?, ?)",
                ("Test Doc", "Content", "idea"),
            )
            doc_id = cursor.lastrowid
            conn.commit()

            # Manually insert into cascade metadata (simulating what migration does)
            conn.execute(
                "INSERT OR IGNORE INTO document_cascade_metadata (document_id, stage) VALUES (?, ?)",
                (doc_id, "idea"),
            )
            conn.commit()

            # Verify it's in the new table
            cursor = conn.execute(
                "SELECT stage FROM document_cascade_metadata WHERE document_id = ?",
                (doc_id,),
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "idea"

    def test_backfill_pr_url_data(self, setup_test_db):
        """Test that documents with pr_url are backfilled."""
        with setup_test_db.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO documents (title, content, pr_url) VALUES (?, ?, ?)",
                ("Test Doc", "Content", "https://github.com/test/repo/pull/1"),
            )
            doc_id = cursor.lastrowid
            conn.commit()

            # Manually insert
            conn.execute(
                "INSERT OR IGNORE INTO document_cascade_metadata (document_id, pr_url) VALUES (?, ?)",
                (doc_id, "https://github.com/test/repo/pull/1"),
            )
            conn.commit()

            cursor = conn.execute(
                "SELECT pr_url FROM document_cascade_metadata WHERE document_id = ?",
                (doc_id,),
            )
            result = cursor.fetchone()
            assert result is not None
            assert result[0] == "https://github.com/test/repo/pull/1"


class TestCascadeModuleCRUD:
    """Test CRUD operations in the cascade module."""

    def test_get_cascade_metadata_empty(self, setup_test_db):
        """Test getting metadata for document not in cascade."""
        from emdx.database import cascade as cascade_db

        result = cascade_db.get_cascade_metadata(99999)
        assert result is None

    def test_update_cascade_stage_insert(self, setup_test_db):
        """Test adding a document to cascade via stage update."""
        from emdx.database import cascade as cascade_db
        from emdx.database.documents import save_document

        doc_id = save_document("Test", "Content")

        result = cascade_db.update_cascade_stage(doc_id, "idea")
        assert result is True

        metadata = cascade_db.get_cascade_metadata(doc_id)
        assert metadata is not None
        assert metadata["stage"] == "idea"

    def test_update_cascade_stage_update(self, setup_test_db):
        """Test updating an existing cascade stage."""
        from emdx.database import cascade as cascade_db
        from emdx.database.documents import save_document

        doc_id = save_document("Test", "Content")
        cascade_db.update_cascade_stage(doc_id, "idea")

        result = cascade_db.update_cascade_stage(doc_id, "prompt")
        assert result is True

        metadata = cascade_db.get_cascade_metadata(doc_id)
        assert metadata["stage"] == "prompt"

    def test_update_cascade_stage_remove(self, setup_test_db):
        """Test removing a document from cascade."""
        from emdx.database import cascade as cascade_db
        from emdx.database.documents import save_document

        doc_id = save_document("Test", "Content")
        cascade_db.update_cascade_stage(doc_id, "idea")

        result = cascade_db.update_cascade_stage(doc_id, None)
        assert result is True

        metadata = cascade_db.get_cascade_metadata(doc_id)
        assert metadata is None

    def test_update_cascade_pr_url(self, setup_test_db):
        """Test updating PR URL."""
        from emdx.database import cascade as cascade_db
        from emdx.database.documents import save_document

        doc_id = save_document("Test", "Content")
        cascade_db.update_cascade_stage(doc_id, "done")

        pr_url = "https://github.com/test/repo/pull/123"
        result = cascade_db.update_cascade_pr_url(doc_id, pr_url)
        assert result is True

        retrieved = cascade_db.get_cascade_pr_url(doc_id)
        assert retrieved == pr_url

    def test_remove_from_cascade(self, setup_test_db):
        """Test removing cascade metadata."""
        from emdx.database import cascade as cascade_db
        from emdx.database.documents import save_document

        doc_id = save_document("Test", "Content")
        cascade_db.update_cascade_stage(doc_id, "idea")

        result = cascade_db.remove_from_cascade(doc_id)
        assert result is True

        metadata = cascade_db.get_cascade_metadata(doc_id)
        assert metadata is None


class TestCascadeStageQueries:
    """Test stage-based query operations."""

    def test_get_oldest_at_stage(self, setup_test_db):
        """Test getting oldest document at stage."""
        import time

        from emdx.database import cascade as cascade_db
        from emdx.database.documents import save_document

        # Create documents with slight time difference
        doc1 = save_document("First", "Content 1")
        cascade_db.update_cascade_stage(doc1, "idea")

        time.sleep(0.01)  # Small delay to ensure different timestamps

        doc2 = save_document("Second", "Content 2")
        cascade_db.update_cascade_stage(doc2, "idea")

        oldest = cascade_db.get_oldest_at_stage("idea")
        assert oldest is not None
        assert oldest["id"] == doc1

    def test_get_oldest_at_stage_empty(self, setup_test_db):
        """Test getting oldest when stage is empty."""
        from emdx.database import cascade as cascade_db

        oldest = cascade_db.get_oldest_at_stage("idea")
        assert oldest is None

    def test_list_documents_at_stage(self, setup_test_db):
        """Test listing documents at a stage."""
        from emdx.database import cascade as cascade_db
        from emdx.database.documents import save_document

        doc1 = save_document("Doc 1", "Content 1")
        cascade_db.update_cascade_stage(doc1, "idea")

        doc2 = save_document("Doc 2", "Content 2")
        cascade_db.update_cascade_stage(doc2, "idea")

        doc3 = save_document("Doc 3", "Content 3")
        cascade_db.update_cascade_stage(doc3, "prompt")  # Different stage

        docs = cascade_db.list_documents_at_stage("idea")
        assert len(docs) == 2
        assert all(d["stage"] == "idea" for d in docs)

    def test_count_documents_at_stage(self, setup_test_db):
        """Test counting documents at a stage."""
        from emdx.database import cascade as cascade_db
        from emdx.database.documents import save_document

        doc1 = save_document("Doc 1", "Content")
        cascade_db.update_cascade_stage(doc1, "analyzed")

        doc2 = save_document("Doc 2", "Content")
        cascade_db.update_cascade_stage(doc2, "analyzed")

        count = cascade_db.count_documents_at_stage("analyzed")
        assert count == 2

        count_empty = cascade_db.count_documents_at_stage("planned")
        assert count_empty == 0

    def test_get_cascade_stats(self, setup_test_db):
        """Test getting cascade statistics."""
        from emdx.database import cascade as cascade_db
        from emdx.database.documents import save_document

        # Create documents at various stages
        for stage, count in [("idea", 3), ("prompt", 2), ("analyzed", 1)]:
            for i in range(count):
                doc_id = save_document(f"{stage} doc {i}", "Content")
                cascade_db.update_cascade_stage(doc_id, stage)

        stats = cascade_db.get_cascade_stats()

        assert stats["idea"] == 3
        assert stats["prompt"] == 2
        assert stats["analyzed"] == 1
        assert stats["planned"] == 0
        assert stats["done"] == 0


class TestForeignKeyCascadeDelete:
    """Test that foreign key ON DELETE CASCADE works."""

    def test_cascade_delete_removes_metadata(self, setup_test_db):
        """Test that deleting a document removes its cascade metadata."""
        from emdx.database import cascade as cascade_db
        from emdx.database.documents import save_document

        doc_id = save_document("Test", "Content")
        cascade_db.update_cascade_stage(doc_id, "idea")

        # Verify metadata exists
        metadata = cascade_db.get_cascade_metadata(doc_id)
        assert metadata is not None

        # Hard delete the document
        with setup_test_db.get_connection() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            conn.commit()

        # Metadata should be gone due to ON DELETE CASCADE
        metadata = cascade_db.get_cascade_metadata(doc_id)
        assert metadata is None


class TestSaveDocumentToCascade:
    """Test the save_document_to_cascade function."""

    def test_save_to_cascade_creates_both_records(self, setup_test_db):
        """Test that save_document_to_cascade creates document and metadata."""
        from emdx.database import cascade as cascade_db
        from emdx.database.documents import get_document

        doc_id = cascade_db.save_document_to_cascade(
            title="Cascade Test",
            content="Test content",
            stage="idea",
            project="test-project",
        )

        # Check document exists
        doc = get_document(doc_id)
        assert doc is not None
        assert doc["title"] == "Cascade Test"
        assert doc["project"] == "test-project"

        # Check cascade metadata exists
        metadata = cascade_db.get_cascade_metadata(doc_id)
        assert metadata is not None
        assert metadata["stage"] == "idea"

    def test_save_to_cascade_with_parent(self, setup_test_db):
        """Test saving cascade document with parent."""
        from emdx.database import cascade as cascade_db
        from emdx.database.documents import get_document, save_document

        parent_id = save_document("Parent", "Parent content")

        child_id = cascade_db.save_document_to_cascade(
            title="Child",
            content="Child content",
            stage="prompt",
            parent_id=parent_id,
        )

        child = get_document(child_id)
        assert child["parent_id"] == parent_id


