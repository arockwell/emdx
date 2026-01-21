"""Tests for database module refactoring.

Tests the following improvements:
- Phase 1: Path resolution consolidation (get_db_path)
- Phase 2: Standardized error handling (exceptions module)
- Phase 3: N+1 query optimization (recursive CTE for get_descendants)
- Phase 4: Validation layer (cycle detection, stage validation)
- Phase 5: Tag handling simplification (database/tags.py)
"""

import pytest


class TestPathResolution:
    """Test that get_db_path is consolidated and respects EMDX_TEST_DB."""

    def test_path_module_exports_get_db_path(self):
        """Test that get_db_path can be imported from database.path."""
        from emdx.database.path import get_db_path
        path = get_db_path()
        assert path is not None
        assert str(path).endswith(".db")

    def test_settings_reexports_get_db_path(self):
        """Test that settings module re-exports get_db_path."""
        from emdx.config.settings import get_db_path
        path = get_db_path()
        assert path is not None

    def test_database_package_exports_get_db_path(self):
        """Test that database package exports get_db_path."""
        from emdx.database import get_db_path
        path = get_db_path()
        assert path is not None

    def test_migrations_uses_same_path(self, isolate_test_database):
        """Test that migrations module uses the same path function."""
        from emdx.database.migrations import get_db_path as migrations_get_db_path
        from emdx.database.path import get_db_path as path_get_db_path

        # Both should return the same path
        assert str(migrations_get_db_path()) == str(path_get_db_path())


class TestExceptions:
    """Test the new exceptions module."""

    def test_exceptions_importable(self):
        """Test that all exceptions can be imported from database package."""
        from emdx.database import (
            DatabaseError,
            DocumentNotFoundError,
            DuplicateDocumentError,
            GroupNotFoundError,
            CycleDetectedError,
            IntegrityError,
            InvalidStageError,
        )

        # Test that they're proper exceptions
        assert issubclass(DocumentNotFoundError, DatabaseError)
        assert issubclass(CycleDetectedError, DatabaseError)
        assert issubclass(InvalidStageError, DatabaseError)

    def test_document_not_found_error_message(self):
        """Test DocumentNotFoundError has proper message."""
        from emdx.database.exceptions import DocumentNotFoundError

        err = DocumentNotFoundError(42)
        assert "42" in str(err)
        assert err.identifier == 42

    def test_cycle_detected_error_message(self):
        """Test CycleDetectedError has proper message."""
        from emdx.database.exceptions import CycleDetectedError

        err = CycleDetectedError("Custom message")
        assert "Custom message" in str(err)

    def test_invalid_stage_error_message(self):
        """Test InvalidStageError includes valid stages."""
        from emdx.database.exceptions import InvalidStageError

        err = InvalidStageError("bad_stage", {"idea", "done"})
        assert "bad_stage" in str(err)
        assert "idea" in str(err)


class TestDocumentHierarchy:
    """Test document hierarchy operations."""

    def test_set_parent_success(self, isolate_test_database):
        """Test setting a document's parent successfully."""
        from emdx.database.documents import save_document, set_parent, get_document

        parent_id = save_document(
            title="Parent Doc",
            content="Parent content",
            project="test",
        )
        child_id = save_document(
            title="Child Doc",
            content="Child content",
            project="test",
        )

        result = set_parent(child_id, parent_id)
        assert result is True

        child = get_document(child_id)
        assert child["parent_id"] == parent_id

    def test_set_parent_raises_on_cycle(self, isolate_test_database):
        """Test that set_parent raises CycleDetectedError for cycles."""
        from emdx.database.documents import save_document, set_parent
        from emdx.database.exceptions import CycleDetectedError

        # Create a chain: A -> B -> C
        a_id = save_document(title="A", content="Content", project="test")
        b_id = save_document(title="B", content="Content", project="test")
        c_id = save_document(title="C", content="Content", project="test")

        set_parent(b_id, a_id)
        set_parent(c_id, b_id)

        # Trying to make A a child of C should fail (C -> A -> B -> C)
        with pytest.raises(CycleDetectedError):
            set_parent(a_id, c_id)

    def test_set_parent_raises_on_self_reference(self, isolate_test_database):
        """Test that set_parent raises for self-reference."""
        from emdx.database.documents import save_document, set_parent
        from emdx.database.exceptions import CycleDetectedError

        doc_id = save_document(title="Self", content="Content", project="test")

        with pytest.raises(CycleDetectedError):
            set_parent(doc_id, doc_id)

    def test_set_parent_raises_on_nonexistent_document(self, isolate_test_database):
        """Test that set_parent raises DocumentNotFoundError."""
        from emdx.database.documents import save_document, set_parent
        from emdx.database.exceptions import DocumentNotFoundError

        doc_id = save_document(title="Doc", content="Content", project="test")

        with pytest.raises(DocumentNotFoundError):
            set_parent(doc_id, 99999)

        with pytest.raises(DocumentNotFoundError):
            set_parent(99999, doc_id)


class TestGetDescendants:
    """Test the optimized get_descendants function."""

    def test_get_descendants_empty(self, isolate_test_database):
        """Test get_descendants returns empty list for doc with no children."""
        from emdx.database.documents import save_document, get_descendants

        doc_id = save_document(title="Leaf Doc", content="Content", project="test")
        descendants = get_descendants(doc_id)
        assert descendants == []

    def test_get_descendants_single_level(self, isolate_test_database):
        """Test get_descendants with direct children only."""
        from emdx.database.documents import save_document, set_parent, get_descendants

        parent_id = save_document(title="Parent", content="Content", project="test")
        child1_id = save_document(title="Child1", content="Content", project="test")
        child2_id = save_document(title="Child2", content="Content", project="test")

        set_parent(child1_id, parent_id)
        set_parent(child2_id, parent_id)

        descendants = get_descendants(parent_id)
        assert len(descendants) == 2
        descendant_ids = {d["id"] for d in descendants}
        assert child1_id in descendant_ids
        assert child2_id in descendant_ids

    def test_get_descendants_multi_level(self, isolate_test_database):
        """Test get_descendants with multiple levels of nesting."""
        from emdx.database.documents import save_document, set_parent, get_descendants

        # Create a three-level hierarchy: Root -> Level1 -> Level2
        root_id = save_document(title="Root", content="Content", project="test")
        level1_id = save_document(title="Level1", content="Content", project="test")
        level2_id = save_document(title="Level2", content="Content", project="test")

        set_parent(level1_id, root_id)
        set_parent(level2_id, level1_id)

        descendants = get_descendants(root_id)
        assert len(descendants) == 2
        descendant_ids = {d["id"] for d in descendants}
        assert level1_id in descendant_ids
        assert level2_id in descendant_ids

    def test_get_descendants_includes_depth(self, isolate_test_database):
        """Test that get_descendants returns depth information."""
        from emdx.database.documents import save_document, set_parent, get_descendants

        root_id = save_document(title="Root", content="Content", project="test")
        level1_id = save_document(title="Level1", content="Content", project="test")
        level2_id = save_document(title="Level2", content="Content", project="test")

        set_parent(level1_id, root_id)
        set_parent(level2_id, level1_id)

        descendants = get_descendants(root_id)

        # Each descendant should have a depth field
        for d in descendants:
            assert "depth" in d

        # Level1 should be depth 1, Level2 should be depth 2
        depths = {d["title"]: d["depth"] for d in descendants}
        assert depths["Level1"] == 1
        assert depths["Level2"] == 2


class TestArchiveDescendants:
    """Test the optimized archive_descendants function."""

    def test_archive_descendants(self, isolate_test_database):
        """Test archiving all descendants in one batch."""
        from emdx.database.documents import (
            save_document,
            set_parent,
            get_document,
            archive_descendants,
        )

        root_id = save_document(title="Root", content="Content", project="test")
        child1_id = save_document(title="Child1", content="Content", project="test")
        child2_id = save_document(title="Child2", content="Content", project="test")
        grandchild_id = save_document(title="Grandchild", content="Content", project="test")

        set_parent(child1_id, root_id)
        set_parent(child2_id, root_id)
        set_parent(grandchild_id, child1_id)

        # Archive all descendants
        count = archive_descendants(root_id)
        assert count == 3

        # Root should not be archived
        root = get_document(root_id)
        assert root["archived_at"] is None

        # All descendants should be archived
        child1 = get_document(child1_id)
        child2 = get_document(child2_id)
        grandchild = get_document(grandchild_id)

        assert child1["archived_at"] is not None
        assert child2["archived_at"] is not None
        assert grandchild["archived_at"] is not None

    def test_archive_descendants_skips_already_archived(self, isolate_test_database):
        """Test that archive_descendants skips already archived docs."""
        from emdx.database.documents import (
            save_document,
            set_parent,
            archive_document,
            archive_descendants,
        )

        root_id = save_document(title="Root", content="Content", project="test")
        child1_id = save_document(title="Child1", content="Content", project="test")
        child2_id = save_document(title="Child2", content="Content", project="test")

        set_parent(child1_id, root_id)
        set_parent(child2_id, root_id)

        # Archive one child first
        archive_document(child1_id)

        # Now archive all descendants
        count = archive_descendants(root_id)
        assert count == 1  # Only child2 was newly archived


class TestCascadeStageValidation:
    """Test cascade stage validation."""

    def test_update_stage_valid(self, isolate_test_database):
        """Test updating to a valid cascade stage."""
        from emdx.database.documents import save_document, update_document_stage, get_document

        doc_id = save_document(title="Test", content="Content", project="test")

        # Test all valid default cascade stages
        for stage in ["idea", "prompt", "analyzed", "planned", "done"]:
            result = update_document_stage(doc_id, stage)
            assert result is True

            doc = get_document(doc_id)
            assert doc.get("stage") == stage

    def test_update_stage_none_removes_from_cascade(self, isolate_test_database):
        """Test that setting stage to None removes from cascade."""
        from emdx.database.documents import save_document, update_document_stage, get_document

        doc_id = save_document(title="Test", content="Content", project="test")

        update_document_stage(doc_id, "idea")
        update_document_stage(doc_id, None)

        doc = get_document(doc_id)
        assert doc.get("stage") is None

    def test_update_stage_invalid_raises(self, isolate_test_database):
        """Test that invalid stages raise InvalidStageError."""
        from emdx.database.documents import save_document, update_document_stage
        from emdx.database.exceptions import InvalidStageError

        doc_id = save_document(title="Test", content="Content", project="test")

        with pytest.raises(InvalidStageError) as exc_info:
            update_document_stage(doc_id, "invalid_stage")

        assert "invalid_stage" in str(exc_info.value)


class TestDatabaseTags:
    """Test the new database/tags.py module."""

    def test_add_tags_with_conn(self, isolate_test_database):
        """Test adding tags using connection-based API."""
        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document
        from emdx.database.tags import add_tags_with_conn, get_document_tags_with_conn

        doc_id = save_document(title="Test", content="Content", project="test")

        with db_connection.get_connection() as conn:
            added = add_tags_with_conn(conn, doc_id, ["tag1", "tag2", "tag3"])
            conn.commit()

        assert len(added) == 3

        with db_connection.get_connection() as conn:
            tags = get_document_tags_with_conn(conn, doc_id)

        assert "tag1" in tags
        assert "tag2" in tags
        assert "tag3" in tags

    def test_add_duplicate_tags_ignored(self, isolate_test_database):
        """Test that duplicate tags are silently ignored."""
        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document
        from emdx.database.tags import add_tags_with_conn, get_document_tags_with_conn

        doc_id = save_document(title="Test", content="Content", project="test")

        with db_connection.get_connection() as conn:
            added1 = add_tags_with_conn(conn, doc_id, ["tag1", "tag2"])
            conn.commit()
            added2 = add_tags_with_conn(conn, doc_id, ["tag2", "tag3"])
            conn.commit()

        assert len(added1) == 2
        assert len(added2) == 1  # tag2 was already there

        with db_connection.get_connection() as conn:
            tags = get_document_tags_with_conn(conn, doc_id)

        assert len(tags) == 3

    def test_remove_tags_with_conn(self, isolate_test_database):
        """Test removing tags using connection-based API."""
        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document
        from emdx.database.tags import add_tags_with_conn, remove_tags_with_conn, get_document_tags_with_conn

        doc_id = save_document(title="Test", content="Content", project="test")

        with db_connection.get_connection() as conn:
            add_tags_with_conn(conn, doc_id, ["tag1", "tag2", "tag3"])
            conn.commit()
            removed = remove_tags_with_conn(conn, doc_id, ["tag2"])
            conn.commit()

        assert "tag2" in removed

        with db_connection.get_connection() as conn:
            tags = get_document_tags_with_conn(conn, doc_id)

        assert "tag2" not in tags
        assert "tag1" in tags
        assert "tag3" in tags

    def test_get_all_tags_with_conn(self, isolate_test_database):
        """Test getting all tags with usage counts."""
        from emdx.database.connection import db_connection
        from emdx.database.documents import save_document
        from emdx.database.tags import add_tags_with_conn, get_all_tags_with_conn

        doc1_id = save_document(title="Doc1", content="Content", project="test")
        doc2_id = save_document(title="Doc2", content="Content", project="test")

        with db_connection.get_connection() as conn:
            add_tags_with_conn(conn, doc1_id, ["common", "unique1"])
            add_tags_with_conn(conn, doc2_id, ["common", "unique2"])
            conn.commit()

        with db_connection.get_connection() as conn:
            all_tags = get_all_tags_with_conn(conn)

        tag_dict = {t["name"]: t for t in all_tags}
        assert "common" in tag_dict
        assert "unique1" in tag_dict
        assert "unique2" in tag_dict


class TestGroupCycleDetection:
    """Test that CycleDetectedError is raised for group cycles."""

    def test_group_cycle_detection_raises_custom_error(self, isolate_test_database):
        """Test that group cycle detection raises CycleDetectedError."""
        from emdx.database import groups as groups_db
        from emdx.database.exceptions import CycleDetectedError
        from emdx.database.connection import db_connection

        # Clean up any existing test groups
        with db_connection.get_connection() as conn:
            conn.execute("DELETE FROM document_group_members")
            conn.execute("DELETE FROM document_groups")
            conn.commit()

        group_id = groups_db.create_group(name="Self")

        with pytest.raises(CycleDetectedError):
            groups_db.update_group(group_id, parent_group_id=group_id)
