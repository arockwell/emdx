"""Tests for emdx/database/documents.py -- the core document CRUD module.

Tests use the session-scoped isolate_test_database fixture from conftest.py
which provides a real SQLite database with migrations applied. Each test
class cleans up the documents table to avoid cross-test interference.
"""

import time

import pytest


@pytest.fixture(autouse=True)
def clean_documents_tables(isolate_test_database):
    """Clean up documents and related tables before each test."""
    from emdx.database.connection import db_connection

    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM document_cascade_metadata")
        conn.execute("DELETE FROM document_sources")
        conn.execute("DELETE FROM document_tags")
        conn.execute("DELETE FROM documents")
        conn.commit()

    yield

    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM document_cascade_metadata")
        conn.execute("DELETE FROM document_sources")
        conn.execute("DELETE FROM document_tags")
        conn.execute("DELETE FROM documents")
        conn.commit()


# =========================================================================
# CRUD Lifecycle
# =========================================================================


class TestSaveDocument:
    """Test save_document()."""

    def test_save_returns_positive_id(self):
        from emdx.database.documents import save_document

        doc_id = save_document("My Title", "Some content")
        assert isinstance(doc_id, int)
        assert doc_id > 0

    def test_save_with_project(self):
        from emdx.database.documents import save_document, get_document

        doc_id = save_document("Proj Doc", "Content", project="my-project")
        doc = get_document(doc_id)
        assert doc["project"] == "my-project"

    def test_save_with_parent_id(self):
        from emdx.database.documents import save_document, get_document

        parent_id = save_document("Parent", "Parent content")
        child_id = save_document("Child", "Child content", parent_id=parent_id)
        child = get_document(child_id)
        assert child["parent_id"] == parent_id

    def test_save_with_tags(self):
        from emdx.database.documents import save_document
        from emdx.database.connection import db_connection

        doc_id = save_document("Tagged", "Content", tags=["alpha", "beta"])
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                """SELECT t.name FROM tags t
                   JOIN document_tags dt ON t.id = dt.tag_id
                   WHERE dt.document_id = ?
                   ORDER BY t.name""",
                (doc_id,),
            )
            tag_names = [row[0] for row in cursor.fetchall()]
        assert "alpha" in tag_names
        assert "beta" in tag_names

    def test_save_minimal(self):
        from emdx.database.documents import save_document, get_document

        doc_id = save_document("Title Only", "")
        doc = get_document(doc_id)
        assert doc is not None
        assert doc["title"] == "Title Only"
        assert doc["content"] == ""

    def test_save_special_characters_in_title(self):
        from emdx.database.documents import save_document, get_document

        title = "Test's \"special\" <chars> & more: 日本語"
        doc_id = save_document(title, "Content")
        doc = get_document(doc_id)
        assert doc["title"] == title

    def test_save_special_characters_in_content(self):
        from emdx.database.documents import save_document, get_document

        content = "Line 1\nLine 2\n\tTabbed\n```python\nprint('hello')\n```"
        doc_id = save_document("Code Doc", content)
        doc = get_document(doc_id)
        assert doc["content"] == content

    def test_save_very_long_content(self):
        from emdx.database.documents import save_document, get_document

        long_content = "x" * 100_000
        doc_id = save_document("Long Doc", long_content)
        doc = get_document(doc_id)
        assert len(doc["content"]) == 100_000


class TestGetDocument:
    """Test get_document()."""

    def test_get_by_id(self):
        from emdx.database.documents import save_document, get_document

        doc_id = save_document("Test Doc", "Content here")
        doc = get_document(doc_id)
        assert doc is not None
        assert doc["id"] == doc_id
        assert doc["title"] == "Test Doc"
        assert doc["content"] == "Content here"

    def test_get_by_string_id(self):
        from emdx.database.documents import save_document, get_document

        doc_id = save_document("String ID", "Content")
        doc = get_document(str(doc_id))
        assert doc is not None
        assert doc["id"] == doc_id

    def test_get_by_title(self):
        from emdx.database.documents import save_document, get_document

        save_document("Unique Title XYZ", "Some content")
        doc = get_document("Unique Title XYZ")
        assert doc is not None
        assert doc["title"] == "Unique Title XYZ"

    def test_get_by_title_case_insensitive(self):
        from emdx.database.documents import save_document, get_document

        save_document("Case Test Doc", "Content")
        doc = get_document("case test doc")
        assert doc is not None
        assert doc["title"] == "Case Test Doc"

    def test_get_nonexistent_returns_none(self):
        from emdx.database.documents import get_document

        assert get_document(999999) is None

    def test_get_deleted_returns_none(self):
        from emdx.database.documents import save_document, get_document, delete_document

        doc_id = save_document("To Delete", "Content")
        delete_document(doc_id)
        assert get_document(doc_id) is None

    def test_get_increments_access_count(self):
        from emdx.database.documents import save_document, get_document

        doc_id = save_document("Access Test", "Content")
        # First access
        doc1 = get_document(doc_id)
        count1 = doc1["access_count"]
        # Second access
        doc2 = get_document(doc_id)
        count2 = doc2["access_count"]
        assert count2 == count1 + 1

    def test_get_updates_accessed_at(self):
        from emdx.database.documents import save_document, get_document

        doc_id = save_document("Accessed At Test", "Content")
        doc1 = get_document(doc_id)
        time.sleep(0.05)
        doc2 = get_document(doc_id)
        # accessed_at should be updated (or at least not earlier)
        assert doc2["accessed_at"] >= doc1["accessed_at"]

    def test_get_returns_all_fields(self):
        from emdx.database.documents import save_document, get_document

        doc_id = save_document("Full Fields", "Content", project="proj")
        doc = get_document(doc_id)
        # Verify all expected fields exist
        for field in ["id", "title", "content", "project", "created_at",
                       "updated_at", "accessed_at", "access_count",
                       "is_deleted", "deleted_at"]:
            assert field in doc, f"Missing field: {field}"


class TestUpdateDocument:
    """Test update_document()."""

    def test_update_title_and_content(self):
        from emdx.database.documents import save_document, get_document, update_document

        doc_id = save_document("Original", "Original content")
        result = update_document(doc_id, "Updated", "Updated content")
        assert result is True

        doc = get_document(doc_id)
        assert doc["title"] == "Updated"
        assert doc["content"] == "Updated content"

    def test_update_nonexistent_returns_false(self):
        from emdx.database.documents import update_document

        result = update_document(999999, "X", "Y")
        assert result is False

    def test_update_sets_updated_at(self):
        from emdx.database.documents import save_document, get_document, update_document

        doc_id = save_document("Timestamp Test", "Content")
        doc_before = get_document(doc_id)
        time.sleep(0.05)
        update_document(doc_id, "Timestamp Test v2", "New Content")
        doc_after = get_document(doc_id)
        assert doc_after["updated_at"] >= doc_before["updated_at"]


class TestDeleteDocument:
    """Test delete_document() (soft and hard delete)."""

    def test_soft_delete_by_id(self):
        from emdx.database.documents import save_document, get_document, delete_document

        doc_id = save_document("Soft Del", "Content")
        result = delete_document(doc_id)
        assert result is True
        # Soft-deleted doc not visible via get_document
        assert get_document(doc_id) is None

    def test_soft_delete_by_title(self):
        from emdx.database.documents import save_document, get_document, delete_document

        save_document("Delete By Title", "Content")
        result = delete_document("Delete By Title")
        assert result is True
        assert get_document("Delete By Title") is None

    def test_soft_delete_by_title_case_insensitive(self):
        from emdx.database.documents import save_document, get_document, delete_document

        save_document("Case Del Test", "Content")
        result = delete_document("case del test")
        assert result is True
        assert get_document("Case Del Test") is None

    def test_hard_delete_by_id(self):
        from emdx.database.documents import save_document, delete_document
        from emdx.database.connection import db_connection

        doc_id = save_document("Hard Del", "Content")
        result = delete_document(doc_id, hard_delete=True)
        assert result is True
        # Hard-deleted doc gone from DB entirely
        with db_connection.get_connection() as conn:
            cursor = conn.execute("SELECT id FROM documents WHERE id = ?", (doc_id,))
            assert cursor.fetchone() is None

    def test_hard_delete_by_title(self):
        from emdx.database.documents import save_document, delete_document
        from emdx.database.connection import db_connection

        save_document("Hard Del Title", "Content")
        result = delete_document("Hard Del Title", hard_delete=True)
        assert result is True
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id FROM documents WHERE title = ?", ("Hard Del Title",)
            )
            assert cursor.fetchone() is None

    def test_delete_nonexistent_returns_false(self):
        from emdx.database.documents import delete_document

        assert delete_document(999999) is False

    def test_double_soft_delete_returns_false(self):
        from emdx.database.documents import save_document, delete_document

        doc_id = save_document("Double Del", "Content")
        assert delete_document(doc_id) is True
        assert delete_document(doc_id) is False

    def test_soft_delete_preserves_data(self):
        from emdx.database.documents import save_document, delete_document
        from emdx.database.connection import db_connection

        doc_id = save_document("Preserved", "Important content")
        delete_document(doc_id)
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT title, content, is_deleted, deleted_at FROM documents WHERE id = ?",
                (doc_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "Preserved"
            assert row[1] == "Important content"
            assert row[2] == 1  # is_deleted = TRUE
            assert row[3] is not None  # deleted_at set


class TestRestoreDocument:
    """Test restore_document()."""

    def test_restore_by_id(self):
        from emdx.database.documents import save_document, get_document, delete_document, restore_document

        doc_id = save_document("Restorable", "Content")
        delete_document(doc_id)
        assert get_document(doc_id) is None

        result = restore_document(doc_id)
        assert result is True
        doc = get_document(doc_id)
        assert doc is not None
        assert doc["title"] == "Restorable"

    def test_restore_by_title(self):
        from emdx.database.documents import save_document, get_document, delete_document, restore_document

        save_document("Restore Title", "Content")
        delete_document("Restore Title")
        result = restore_document("Restore Title")
        assert result is True
        assert get_document("Restore Title") is not None

    def test_restore_clears_deleted_at(self):
        from emdx.database.documents import save_document, get_document, delete_document, restore_document

        doc_id = save_document("Clear Deleted At", "Content")
        delete_document(doc_id)
        restore_document(doc_id)
        doc = get_document(doc_id)
        assert doc["deleted_at"] is None
        assert doc["is_deleted"] == 0

    def test_restore_non_deleted_returns_false(self):
        from emdx.database.documents import save_document, restore_document

        doc_id = save_document("Not Deleted", "Content")
        assert restore_document(doc_id) is False

    def test_restore_nonexistent_returns_false(self):
        from emdx.database.documents import restore_document

        assert restore_document(999999) is False


# =========================================================================
# Listing & Counting
# =========================================================================


class TestListDocuments:
    """Test list_documents()."""

    def test_list_returns_top_level_by_default(self):
        from emdx.database.documents import save_document, list_documents

        save_document("Top 1", "Content")
        save_document("Top 2", "Content")
        parent = save_document("Parent", "Content")
        save_document("Child", "Content", parent_id=parent)

        docs = list_documents()
        titles = [d["title"] for d in docs]
        assert "Top 1" in titles
        assert "Top 2" in titles
        assert "Parent" in titles
        assert "Child" not in titles

    def test_list_with_parent_id_minus_one_returns_all(self):
        from emdx.database.documents import save_document, list_documents

        parent = save_document("Parent", "Content")
        save_document("Child", "Content", parent_id=parent)
        save_document("Top", "Content")

        docs = list_documents(parent_id=-1)
        titles = [d["title"] for d in docs]
        assert "Parent" in titles
        assert "Child" in titles
        assert "Top" in titles

    def test_list_children_of_parent(self):
        from emdx.database.documents import save_document, list_documents

        parent = save_document("Parent", "Content")
        save_document("Child A", "Content", parent_id=parent)
        save_document("Child B", "Content", parent_id=parent)
        save_document("Unrelated", "Content")

        docs = list_documents(parent_id=parent)
        titles = [d["title"] for d in docs]
        assert len(docs) == 2
        assert "Child A" in titles
        assert "Child B" in titles

    def test_list_filter_by_project(self):
        from emdx.database.documents import save_document, list_documents

        save_document("Proj A", "Content", project="alpha")
        save_document("Proj B", "Content", project="beta")

        docs = list_documents(project="alpha", parent_id=-1)
        assert len(docs) == 1
        assert docs[0]["title"] == "Proj A"

    def test_list_excludes_archived_by_default(self):
        from emdx.database.documents import save_document, list_documents, archive_document

        doc_id = save_document("Archived", "Content")
        save_document("Active", "Content")
        archive_document(doc_id)

        docs = list_documents(parent_id=-1)
        titles = [d["title"] for d in docs]
        assert "Active" in titles
        assert "Archived" not in titles

    def test_list_includes_archived_when_requested(self):
        from emdx.database.documents import save_document, list_documents, archive_document

        doc_id = save_document("Archived", "Content")
        save_document("Active", "Content")
        archive_document(doc_id)

        docs = list_documents(parent_id=-1, include_archived=True)
        titles = [d["title"] for d in docs]
        assert "Active" in titles
        assert "Archived" in titles

    def test_list_excludes_deleted(self):
        from emdx.database.documents import save_document, list_documents, delete_document

        doc_id = save_document("Deleted", "Content")
        save_document("Visible", "Content")
        delete_document(doc_id)

        docs = list_documents(parent_id=-1)
        titles = [d["title"] for d in docs]
        assert "Visible" in titles
        assert "Deleted" not in titles

    def test_list_pagination_limit(self):
        from emdx.database.documents import save_document, list_documents

        for i in range(5):
            save_document(f"Doc {i}", "Content")

        docs = list_documents(limit=3, parent_id=-1)
        assert len(docs) == 3

    def test_list_pagination_offset(self):
        from emdx.database.documents import save_document, list_documents

        for i in range(5):
            save_document(f"Offset Doc {i}", "Content")

        all_docs = list_documents(parent_id=-1)
        offset_docs = list_documents(offset=2, parent_id=-1)
        assert len(offset_docs) == len(all_docs) - 2

    def test_list_ordered_by_id_desc(self):
        from emdx.database.documents import save_document, list_documents

        id1 = save_document("First", "Content")
        id2 = save_document("Second", "Content")
        id3 = save_document("Third", "Content")

        docs = list_documents(parent_id=-1)
        ids = [d["id"] for d in docs]
        assert ids == sorted(ids, reverse=True)


class TestCountDocuments:
    """Test count_documents()."""

    def test_count_basic(self):
        from emdx.database.documents import save_document, count_documents

        save_document("A", "Content")
        save_document("B", "Content")
        save_document("C", "Content")
        assert count_documents(parent_id=-1) == 3

    def test_count_excludes_deleted(self):
        from emdx.database.documents import save_document, count_documents, delete_document

        save_document("A", "Content")
        doc_id = save_document("B", "Content")
        delete_document(doc_id)
        assert count_documents(parent_id=-1) == 1

    def test_count_by_project(self):
        from emdx.database.documents import save_document, count_documents

        save_document("A", "Content", project="x")
        save_document("B", "Content", project="x")
        save_document("C", "Content", project="y")
        assert count_documents(project="x", parent_id=-1) == 2

    def test_count_excludes_archived_by_default(self):
        from emdx.database.documents import save_document, count_documents, archive_document

        doc_id = save_document("A", "Content")
        save_document("B", "Content")
        archive_document(doc_id)
        assert count_documents(parent_id=-1) == 1

    def test_count_includes_archived_when_requested(self):
        from emdx.database.documents import save_document, count_documents, archive_document

        doc_id = save_document("A", "Content")
        save_document("B", "Content")
        archive_document(doc_id)
        assert count_documents(parent_id=-1, include_archived=True) == 2


class TestGetRecentDocuments:
    """Test get_recent_documents()."""

    def test_recent_returns_most_recent_first(self):
        from emdx.database.documents import save_document, get_document, get_recent_documents

        id1 = save_document("Old", "Content")
        id2 = save_document("New", "Content")
        # Access old one so its accessed_at is more recent
        get_document(id1)
        time.sleep(0.05)
        get_document(id1)

        docs = get_recent_documents(limit=10)
        # id1 was accessed most recently
        assert docs[0]["id"] == id1

    def test_recent_respects_limit(self):
        from emdx.database.documents import save_document, get_recent_documents

        for i in range(5):
            save_document(f"Recent {i}", "Content")
        docs = get_recent_documents(limit=3)
        assert len(docs) == 3

    def test_recent_excludes_deleted(self):
        from emdx.database.documents import save_document, get_recent_documents, delete_document

        doc_id = save_document("Deleted Recent", "Content")
        save_document("Visible Recent", "Content")
        delete_document(doc_id)

        docs = get_recent_documents()
        titles = [d["title"] for d in docs]
        assert "Deleted Recent" not in titles
        assert "Visible Recent" in titles


class TestListDeletedDocuments:
    """Test list_deleted_documents()."""

    def test_lists_soft_deleted(self):
        from emdx.database.documents import save_document, delete_document, list_deleted_documents

        doc_id = save_document("Trashed", "Content")
        delete_document(doc_id)
        deleted = list_deleted_documents()
        assert len(deleted) == 1
        assert deleted[0]["title"] == "Trashed"

    def test_excludes_non_deleted(self):
        from emdx.database.documents import save_document, list_deleted_documents

        save_document("Active", "Content")
        deleted = list_deleted_documents()
        assert len(deleted) == 0

    def test_limit_parameter(self):
        from emdx.database.documents import save_document, delete_document, list_deleted_documents

        for i in range(5):
            doc_id = save_document(f"Del {i}", "Content")
            delete_document(doc_id)
        deleted = list_deleted_documents(limit=3)
        assert len(deleted) == 3


class TestPurgeDeletedDocuments:
    """Test purge_deleted_documents()."""

    def test_purge_all(self):
        from emdx.database.documents import (
            save_document, delete_document, purge_deleted_documents, list_deleted_documents,
        )

        for i in range(3):
            doc_id = save_document(f"Purge {i}", "Content")
            delete_document(doc_id)

        count = purge_deleted_documents()
        assert count == 3
        assert len(list_deleted_documents()) == 0

    def test_purge_does_not_affect_active(self):
        from emdx.database.documents import (
            save_document, delete_document, purge_deleted_documents, get_document,
        )

        active_id = save_document("Active", "Content")
        del_id = save_document("Deleted", "Content")
        delete_document(del_id)

        purge_deleted_documents()
        assert get_document(active_id) is not None


# =========================================================================
# Access Tracking
# =========================================================================


class TestAccessTracking:
    """Test access_count increment and accessed_at update."""

    def test_initial_access_count_is_zero(self):
        from emdx.database.documents import save_document
        from emdx.database.connection import db_connection

        doc_id = save_document("Zero Access", "Content")
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT access_count FROM documents WHERE id = ?", (doc_id,)
            )
            assert cursor.fetchone()[0] == 0

    def test_each_get_increments_count(self):
        from emdx.database.documents import save_document, get_document

        doc_id = save_document("Count Test", "Content")
        for i in range(5):
            get_document(doc_id)

        # access_count should be 5 (each get increments, including the last one)
        # The last get_document also incremented, so we query the raw value
        from emdx.database.connection import db_connection
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT access_count FROM documents WHERE id = ?", (doc_id,)
            )
            assert cursor.fetchone()[0] == 5

    def test_get_by_title_also_increments(self):
        from emdx.database.documents import save_document, get_document
        from emdx.database.connection import db_connection

        save_document("Title Access", "Content")
        get_document("Title Access")
        get_document("Title Access")

        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT access_count FROM documents WHERE title = ?", ("Title Access",)
            )
            assert cursor.fetchone()[0] == 2


# =========================================================================
# FTS5 Sync
# =========================================================================


class TestFTSSync:
    """Test that FTS5 index stays in sync with document operations."""

    def _fts_search(self, query):
        """Helper to search FTS directly."""
        from emdx.database.connection import db_connection
        from emdx.database.search import escape_fts5_query

        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                """SELECT d.id, d.title FROM documents d
                   JOIN documents_fts ON d.id = documents_fts.rowid
                   WHERE documents_fts MATCH ? AND d.is_deleted = FALSE""",
                (escape_fts5_query(query),),
            )
            return [dict(row) for row in cursor.fetchall()]

    def test_save_indexes_in_fts(self):
        from emdx.database.documents import save_document

        save_document("Quantum Computing Primer", "Introduction to qubits and entanglement")
        results = self._fts_search("quantum")
        assert len(results) == 1
        assert results[0]["title"] == "Quantum Computing Primer"

    def test_save_indexes_content_in_fts(self):
        from emdx.database.documents import save_document

        save_document("Generic Title", "The mitochondria is the powerhouse of the cell")
        results = self._fts_search("mitochondria")
        assert len(results) == 1

    def test_update_reflects_in_fts(self):
        from emdx.database.documents import save_document, update_document

        doc_id = save_document("Old FTS Title", "Old content about zebras")
        update_document(doc_id, "New FTS Title", "New content about penguins")

        # New content is searchable
        results = self._fts_search("penguins")
        assert len(results) == 1
        assert results[0]["title"] == "New FTS Title"

    def test_hard_delete_removes_from_fts(self):
        from emdx.database.documents import save_document, delete_document

        doc_id = save_document("FTS Hard Delete", "Unique xyzzy content")
        delete_document(doc_id, hard_delete=True)
        results = self._fts_search("xyzzy")
        assert len(results) == 0

    def test_soft_delete_hides_from_search(self):
        from emdx.database.documents import save_document, delete_document

        doc_id = save_document("FTS Soft Delete", "Unique plugh content")
        delete_document(doc_id)
        # The FTS row still exists (triggers fire on UPDATE too) but
        # our search query filters is_deleted = FALSE
        results = self._fts_search("plugh")
        assert len(results) == 0

    def test_project_indexed_in_fts(self):
        from emdx.database.documents import save_document

        save_document("Proj FTS", "Content", project="my-unique-project-xyz")
        results = self._fts_search("my-unique-project-xyz")
        assert len(results) == 1


# =========================================================================
# Document Hierarchy (Parent/Child)
# =========================================================================


class TestSetParent:
    """Test set_parent()."""

    def test_set_parent_basic(self):
        from emdx.database.documents import save_document, get_document, set_parent

        parent = save_document("Parent", "Content")
        child = save_document("Child", "Content")
        result = set_parent(child, parent)
        assert result is True

        doc = get_document(child)
        assert doc["parent_id"] == parent
        assert doc["relationship"] == "supersedes"

    def test_set_parent_custom_relationship(self):
        from emdx.database.documents import save_document, get_document, set_parent

        parent = save_document("Parent", "Content")
        child = save_document("Child", "Content")
        set_parent(child, parent, relationship="exploration")

        doc = get_document(child)
        assert doc["relationship"] == "exploration"

    def test_set_parent_nonexistent_child(self):
        from emdx.database.documents import save_document, set_parent

        parent = save_document("Parent", "Content")
        result = set_parent(999999, parent)
        assert result is False


class TestGetChildren:
    """Test get_children() and has_children()."""

    def test_get_children_basic(self):
        from emdx.database.documents import save_document, get_children

        parent = save_document("Parent", "Content")
        save_document("Child 1", "Content", parent_id=parent)
        save_document("Child 2", "Content", parent_id=parent)

        children = get_children(parent)
        assert len(children) == 2
        titles = {c["title"] for c in children}
        assert titles == {"Child 1", "Child 2"}

    def test_get_children_excludes_archived(self):
        from emdx.database.documents import save_document, get_children, archive_document

        parent = save_document("Parent", "Content")
        child1 = save_document("Active Child", "Content", parent_id=parent)
        child2 = save_document("Archived Child", "Content", parent_id=parent)
        archive_document(child2)

        children = get_children(parent)
        assert len(children) == 1
        assert children[0]["title"] == "Active Child"

    def test_get_children_includes_archived(self):
        from emdx.database.documents import save_document, get_children, archive_document

        parent = save_document("Parent", "Content")
        save_document("Active", "Content", parent_id=parent)
        child2 = save_document("Archived", "Content", parent_id=parent)
        archive_document(child2)

        children = get_children(parent, include_archived=True)
        assert len(children) == 2

    def test_has_children(self):
        from emdx.database.documents import save_document, has_children

        parent = save_document("Parent", "Content")
        assert has_children(parent) is False

        save_document("Child", "Content", parent_id=parent)
        assert has_children(parent) is True

    def test_has_children_ignores_archived(self):
        from emdx.database.documents import save_document, has_children, archive_document

        parent = save_document("Parent", "Content")
        child = save_document("Child", "Content", parent_id=parent)
        archive_document(child)

        assert has_children(parent) is False
        assert has_children(parent, include_archived=True) is True


class TestGetChildrenCount:
    """Test get_children_count()."""

    def test_children_count_basic(self):
        from emdx.database.documents import save_document, get_children_count

        p1 = save_document("P1", "Content")
        p2 = save_document("P2", "Content")
        save_document("C1", "Content", parent_id=p1)
        save_document("C2", "Content", parent_id=p1)
        save_document("C3", "Content", parent_id=p2)

        counts = get_children_count([p1, p2])
        assert counts[p1] == 2
        assert counts[p2] == 1

    def test_children_count_empty_list(self):
        from emdx.database.documents import get_children_count

        assert get_children_count([]) == {}

    def test_children_count_zero_children(self):
        from emdx.database.documents import save_document, get_children_count

        p1 = save_document("No Kids", "Content")
        counts = get_children_count([p1])
        assert counts[p1] == 0


class TestGetDescendants:
    """Test get_descendants()."""

    def test_descendants_multi_level(self):
        from emdx.database.documents import save_document, get_descendants

        root = save_document("Root", "Content")
        child = save_document("Child", "Content", parent_id=root)
        grandchild = save_document("Grandchild", "Content", parent_id=child)

        descendants = get_descendants(root)
        ids = {d["id"] for d in descendants}
        assert child in ids
        assert grandchild in ids
        assert root not in ids

    def test_descendants_empty(self):
        from emdx.database.documents import save_document, get_descendants

        leaf = save_document("Leaf", "Content")
        assert get_descendants(leaf) == []


class TestArchiveDescendants:
    """Test archive_descendants()."""

    def test_archive_descendants(self):
        from emdx.database.documents import (
            save_document, archive_descendants, get_document,
        )

        root = save_document("Root", "Content")
        child = save_document("Child", "Content", parent_id=root)
        grandchild = save_document("Grandchild", "Content", parent_id=child)

        count = archive_descendants(root)
        assert count == 2

        # Root itself should NOT be archived
        root_doc = get_document(root)
        assert root_doc["archived_at"] is None

        # Children should be archived
        child_doc = get_document(child)
        assert child_doc["archived_at"] is not None
        grandchild_doc = get_document(grandchild)
        assert grandchild_doc["archived_at"] is not None


# =========================================================================
# Archive / Unarchive
# =========================================================================


class TestArchiveUnarchive:
    """Test archive_document() and unarchive_document()."""

    def test_archive_document(self):
        from emdx.database.documents import save_document, get_document, archive_document

        doc_id = save_document("To Archive", "Content")
        result = archive_document(doc_id)
        assert result is True

        doc = get_document(doc_id)
        assert doc["archived_at"] is not None

    def test_archive_already_archived_returns_false(self):
        from emdx.database.documents import save_document, archive_document

        doc_id = save_document("Double Archive", "Content")
        archive_document(doc_id)
        assert archive_document(doc_id) is False

    def test_unarchive_document(self):
        from emdx.database.documents import save_document, get_document, archive_document, unarchive_document

        doc_id = save_document("To Unarchive", "Content")
        archive_document(doc_id)
        result = unarchive_document(doc_id)
        assert result is True

        doc = get_document(doc_id)
        assert doc["archived_at"] is None

    def test_unarchive_non_archived_returns_false(self):
        from emdx.database.documents import save_document, unarchive_document

        doc_id = save_document("Not Archived", "Content")
        assert unarchive_document(doc_id) is False

    def test_archive_deleted_returns_false(self):
        from emdx.database.documents import save_document, delete_document, archive_document

        doc_id = save_document("Deleted", "Content")
        delete_document(doc_id)
        assert archive_document(doc_id) is False


# =========================================================================
# Statistics
# =========================================================================


class TestGetStats:
    """Test get_stats()."""

    def test_stats_overall(self):
        from emdx.database.documents import save_document, get_document, get_stats

        save_document("Stats 1", "Content", project="proj-a")
        save_document("Stats 2", "Content", project="proj-b")
        doc3 = save_document("Stats 3", "Content", project="proj-a")
        # Access doc3 to give it views
        get_document(doc3)
        get_document(doc3)

        stats = get_stats()
        assert stats["total_documents"] == 3
        assert stats["total_projects"] == 2
        assert stats["total_views"] >= 2
        assert "table_size" in stats
        assert "most_viewed" in stats

    def test_stats_by_project(self):
        from emdx.database.documents import save_document, get_stats

        save_document("PA1", "Content", project="proj-a")
        save_document("PA2", "Content", project="proj-a")
        save_document("PB1", "Content", project="proj-b")

        stats = get_stats(project="proj-a")
        assert stats["total_documents"] == 2


# =========================================================================
# Document Sources (Workflow Provenance)
# =========================================================================


class TestDocumentSources:
    """Test record_document_source, get_document_source, get_workflow_document_ids."""

    _wf_counter = 0

    def _create_workflow_infrastructure(self):
        """Create workflow tables needed for document sources."""
        from emdx.database.connection import db_connection

        TestDocumentSources._wf_counter += 1
        name = f"test-wf-{TestDocumentSources._wf_counter}"

        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO workflows (name, display_name, definition_json)
                   VALUES (?, ?, '{}')""",
                (name, name),
            )
            workflow_id = cursor.lastrowid
            cursor = conn.execute(
                """INSERT INTO workflow_runs (workflow_id, status) VALUES (?, 'completed')""",
                (workflow_id,),
            )
            workflow_run_id = cursor.lastrowid
            conn.commit()
            return workflow_run_id

    def test_record_and_get_source(self):
        from emdx.database.documents import save_document, record_document_source, get_document_source

        doc_id = save_document("Sourced", "Content")
        wf_run_id = self._create_workflow_infrastructure()

        result = record_document_source(doc_id, workflow_run_id=wf_run_id)
        assert result is True

        source = get_document_source(doc_id)
        assert source is not None
        assert source["workflow_run_id"] == wf_run_id
        assert source["source_type"] == "individual_output"

    def test_get_source_none(self):
        from emdx.database.documents import get_document_source

        assert get_document_source(999999) is None

    def test_get_workflow_document_ids(self):
        from emdx.database.documents import (
            save_document, record_document_source, get_workflow_document_ids,
        )

        wf_run_id = self._create_workflow_infrastructure()
        d1 = save_document("WF Doc 1", "Content")
        d2 = save_document("WF Doc 2", "Content")
        save_document("Non-WF Doc", "Content")

        record_document_source(d1, workflow_run_id=wf_run_id)
        record_document_source(d2, workflow_run_id=wf_run_id)

        ids = get_workflow_document_ids()
        assert d1 in ids
        assert d2 in ids

    def test_get_workflow_document_ids_filtered(self):
        from emdx.database.documents import (
            save_document, record_document_source, get_workflow_document_ids,
        )

        wf_run_id = self._create_workflow_infrastructure()
        d1 = save_document("WF Run Doc", "Content")
        record_document_source(d1, workflow_run_id=wf_run_id)

        ids = get_workflow_document_ids(workflow_run_id=wf_run_id)
        assert d1 in ids

        ids_other = get_workflow_document_ids(workflow_run_id=999999)
        assert len(ids_other) == 0


class TestListNonWorkflowDocuments:
    """Test list_non_workflow_documents()."""

    def test_excludes_workflow_documents(self):
        from emdx.database.documents import (
            save_document, record_document_source, list_non_workflow_documents,
        )
        from emdx.database.connection import db_connection

        # Create workflow infrastructure
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                """INSERT INTO workflows (name, display_name, definition_json)
                   VALUES ('test', 'Test', '{}')"""
            )
            wf_id = cursor.lastrowid
            cursor = conn.execute(
                "INSERT INTO workflow_runs (workflow_id, status) VALUES (?, 'completed')",
                (wf_id,),
            )
            wf_run_id = cursor.lastrowid
            conn.commit()

        wf_doc = save_document("Workflow Doc", "Content")
        record_document_source(wf_doc, workflow_run_id=wf_run_id)
        manual_doc = save_document("Manual Doc", "Content")

        docs = list_non_workflow_documents(days=1)
        titles = [d["title"] for d in docs]
        assert "Manual Doc" in titles
        assert "Workflow Doc" not in titles


# =========================================================================
# Cascade Stage Operations
# =========================================================================


class TestCascadeStageOperations:
    """Test cascade-related functions in documents.py."""

    def test_update_document_stage(self):
        from emdx.database.documents import save_document, update_document_stage
        from emdx.database.connection import db_connection

        doc_id = save_document("Stage Test", "Content")
        result = update_document_stage(doc_id, "idea")
        assert result is True

        # Verify in documents table
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT stage FROM documents WHERE id = ?", (doc_id,)
            )
            assert cursor.fetchone()[0] == "idea"

    def test_update_document_stage_progression(self):
        from emdx.database.documents import save_document, update_document_stage
        from emdx.database.connection import db_connection

        doc_id = save_document("Stage Prog", "Content")
        for stage in ["idea", "prompt", "analyzed", "planned", "done"]:
            update_document_stage(doc_id, stage)

        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT stage FROM documents WHERE id = ?", (doc_id,)
            )
            assert cursor.fetchone()[0] == "done"

    def test_update_document_stage_to_none(self):
        from emdx.database.documents import save_document, update_document_stage
        from emdx.database.connection import db_connection

        doc_id = save_document("Remove Stage", "Content")
        update_document_stage(doc_id, "idea")
        update_document_stage(doc_id, None)

        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT stage FROM documents WHERE id = ?", (doc_id,)
            )
            assert cursor.fetchone()[0] is None

    def test_update_document_stage_nonexistent(self):
        from emdx.database.documents import update_document_stage

        result = update_document_stage(999999, "idea")
        assert result is False

    def test_update_document_stage_dual_writes(self):
        from emdx.database.documents import save_document, update_document_stage
        from emdx.database.connection import db_connection

        doc_id = save_document("Dual Write", "Content")
        update_document_stage(doc_id, "prompt")

        # Check cascade metadata table
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT stage FROM document_cascade_metadata WHERE document_id = ?",
                (doc_id,),
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] == "prompt"

    def test_update_document_pr_url(self):
        from emdx.database.documents import save_document, update_document_pr_url
        from emdx.database.connection import db_connection

        doc_id = save_document("PR URL Test", "Content")
        pr_url = "https://github.com/user/repo/pull/42"
        result = update_document_pr_url(doc_id, pr_url)
        assert result is True

        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT pr_url FROM documents WHERE id = ?", (doc_id,)
            )
            assert cursor.fetchone()[0] == pr_url

    def test_get_cascade_stats(self):
        from emdx.database.documents import save_document, update_document_stage, get_cascade_stats

        save_document("Idea 1", "Content")
        d1 = save_document("Idea 2", "Content")
        d2 = save_document("Prompt 1", "Content")
        update_document_stage(d1, "idea")
        update_document_stage(d2, "prompt")

        stats = get_cascade_stats()
        assert stats["idea"] >= 1
        assert stats["prompt"] >= 1

    def test_save_document_to_cascade(self):
        from emdx.database.documents import save_document_to_cascade, get_document
        from emdx.database.connection import db_connection

        doc_id = save_document_to_cascade(
            title="Cascade Doc",
            content="Cascade content",
            stage="idea",
            project="cascade-proj",
        )

        doc = get_document(doc_id)
        assert doc is not None
        assert doc["title"] == "Cascade Doc"

        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT stage FROM documents WHERE id = ?", (doc_id,)
            )
            assert cursor.fetchone()[0] == "idea"


# =========================================================================
# Edge Cases
# =========================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_save_empty_title(self):
        from emdx.database.documents import save_document, get_document

        doc_id = save_document("", "Some content")
        doc = get_document(doc_id)
        assert doc["title"] == ""

    def test_save_empty_content(self):
        from emdx.database.documents import save_document, get_document

        doc_id = save_document("Empty Content", "")
        doc = get_document(doc_id)
        assert doc["content"] == ""

    def test_save_none_project(self):
        from emdx.database.documents import save_document, get_document

        doc_id = save_document("No Project", "Content", project=None)
        doc = get_document(doc_id)
        assert doc["project"] is None

    def test_multiple_docs_same_title(self):
        from emdx.database.documents import save_document, get_document

        id1 = save_document("Duplicate Title", "Content 1")
        id2 = save_document("Duplicate Title", "Content 2")
        assert id1 != id2

        # get_document by title returns one of them (behavior is deterministic per query)
        doc = get_document("Duplicate Title")
        assert doc is not None

    def test_unicode_content(self):
        from emdx.database.documents import save_document, get_document

        content = "Unicode: \u2603 \U0001f600 \u00e9\u00e8\u00ea \u4e16\u754c \ud55c\uad6d\uc5b4"
        doc_id = save_document("Unicode Test", content)
        doc = get_document(doc_id)
        assert doc["content"] == content

    def test_newlines_in_title(self):
        from emdx.database.documents import save_document, get_document

        title = "Line1\nLine2\nLine3"
        doc_id = save_document(title, "Content")
        doc = get_document(doc_id)
        assert doc["title"] == title

    def test_sql_injection_in_title(self):
        from emdx.database.documents import save_document, get_document

        title = "'; DROP TABLE documents; --"
        doc_id = save_document(title, "Content")
        doc = get_document(doc_id)
        assert doc["title"] == title

    def test_rapid_saves(self):
        from emdx.database.documents import save_document, count_documents

        ids = []
        for i in range(50):
            ids.append(save_document(f"Rapid {i}", f"Content {i}"))
        assert len(set(ids)) == 50
        assert count_documents(parent_id=-1) == 50

    def test_delete_by_string_id(self):
        from emdx.database.documents import save_document, get_document, delete_document

        doc_id = save_document("String ID Delete", "Content")
        result = delete_document(str(doc_id))
        assert result is True
        assert get_document(doc_id) is None

    def test_restore_by_string_id(self):
        from emdx.database.documents import save_document, get_document, delete_document, restore_document

        doc_id = save_document("String ID Restore", "Content")
        delete_document(doc_id)
        result = restore_document(str(doc_id))
        assert result is True
        assert get_document(doc_id) is not None
