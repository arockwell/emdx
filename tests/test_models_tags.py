"""Tests for emdx/models/tags.py -- the tag management Python API.

Unlike tests/test_tags.py which tests raw SQL operations, these tests exercise
all public functions in emdx.models.tags through the actual Python API,
including emoji alias expansion, batch operations, and tag search modes.

Tests use the session-scoped isolate_test_database fixture from conftest.py
which provides a real SQLite database with migrations applied. A function-scoped
autouse fixture cleans up tags and related tables before/after each test.
"""

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def clean_tags_tables(isolate_test_database: object) -> Generator[None, None, None]:
    """Clean up tags-related tables before and after each test."""
    from emdx.database.connection import db_connection

    def _clean() -> None:
        with db_connection.get_connection() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM document_tags")
            conn.execute("DELETE FROM tags")
            conn.execute("DELETE FROM documents")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    _clean()
    yield
    _clean()


def _create_document(
    title: str = "Test Doc", content: str = "Test content", project: str | None = None
) -> int:
    """Helper to create a document via the database module."""
    from emdx.database.documents import save_document

    return save_document(title=title, content=content, project=project)


# =========================================================================
# get_or_create_tag
# =========================================================================


class TestGetOrCreateTag:
    """Test get_or_create_tag() which takes a raw connection."""

    def test_creates_new_tag(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.models.tags import get_or_create_tag

        with db_connection.get_connection() as conn:
            tag_id = get_or_create_tag(conn, "python")
            assert isinstance(tag_id, int)
            assert tag_id > 0

    def test_returns_existing_tag(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.models.tags import get_or_create_tag

        with db_connection.get_connection() as conn:
            tag_id_1 = get_or_create_tag(conn, "python")
            tag_id_2 = get_or_create_tag(conn, "python")
            assert tag_id_1 == tag_id_2

    def test_normalizes_case_and_whitespace(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.models.tags import get_or_create_tag

        with db_connection.get_connection() as conn:
            tag_id_1 = get_or_create_tag(conn, "Python")
            tag_id_2 = get_or_create_tag(conn, "  python  ")
            tag_id_3 = get_or_create_tag(conn, "PYTHON")
            assert tag_id_1 == tag_id_2 == tag_id_3

    def test_different_tags_get_different_ids(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.models.tags import get_or_create_tag

        with db_connection.get_connection() as conn:
            id_a = get_or_create_tag(conn, "python")
            id_b = get_or_create_tag(conn, "javascript")
            assert id_a != id_b


# =========================================================================
# add_tags_to_document
# =========================================================================


class TestAddTagsToDocument:
    """Test add_tags_to_document() including emoji alias expansion."""

    def test_add_simple_tags(self) -> None:
        from emdx.models.tags import add_tags_to_document

        doc_id = _create_document()
        added = add_tags_to_document(doc_id, ["python", "rust"])
        assert sorted(added) == ["python", "rust"]

    def test_returns_only_newly_added_tags(self) -> None:
        from emdx.models.tags import add_tags_to_document

        doc_id = _create_document()
        added_first = add_tags_to_document(doc_id, ["python", "testing"])
        assert len(added_first) == 2

        # Adding same tags again returns empty since they already exist
        added_second = add_tags_to_document(doc_id, ["python", "testing"])
        assert added_second == []

    def test_partially_new_tags(self) -> None:
        from emdx.models.tags import add_tags_to_document

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["python"])
        added = add_tags_to_document(doc_id, ["python", "javascript"])
        assert added == ["javascript"]

    def test_text_tags_stored_as_is(self) -> None:
        """Text tags should be stored and retrieved as-is (no emoji conversion)."""
        from emdx.models.tags import add_tags_to_document, get_document_tags

        doc_id = _create_document()
        added = add_tags_to_document(doc_id, ["gameplan", "active"])
        assert "gameplan" in added
        assert "active" in added

        tags = get_document_tags(doc_id)
        assert "gameplan" in tags
        assert "active" in tags

    def test_mixed_tags(self) -> None:
        """Mix of known and custom tags."""
        from emdx.models.tags import add_tags_to_document, get_document_tags

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["gameplan", "custom-tag"])

        tags = get_document_tags(doc_id)
        assert "gameplan" in tags
        assert "custom-tag" in tags

    def test_empty_and_whitespace_tags_ignored(self) -> None:
        from emdx.models.tags import add_tags_to_document

        doc_id = _create_document()
        added = add_tags_to_document(doc_id, ["python", "", "  ", "rust"])
        # Empty/whitespace-only tags should be skipped
        assert "python" in added
        assert "rust" in added
        assert "" not in added
        # Only 2 real tags should be added (empty and whitespace skipped)
        assert len(added) == 2

    def test_updates_usage_count(self) -> None:
        """Adding tags should increment usage_count on the tags table."""
        from emdx.database.connection import db_connection
        from emdx.models.tags import add_tags_to_document

        doc1 = _create_document(title="Doc 1")
        doc2 = _create_document(title="Doc 2")
        add_tags_to_document(doc1, ["python"])
        add_tags_to_document(doc2, ["python"])

        with db_connection.get_connection() as conn:
            cursor = conn.execute("SELECT usage_count FROM tags WHERE name = ?", ("python",))
            count = cursor.fetchone()[0]
            assert count == 2

    def test_duplicate_add_does_not_increment_usage(self) -> None:
        """Re-adding a tag to the same doc should NOT increment usage_count."""
        from emdx.database.connection import db_connection
        from emdx.models.tags import add_tags_to_document

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["python"])
        add_tags_to_document(doc_id, ["python"])

        with db_connection.get_connection() as conn:
            cursor = conn.execute("SELECT usage_count FROM tags WHERE name = ?", ("python",))
            count = cursor.fetchone()[0]
            assert count == 1


# =========================================================================
# remove_tags_from_document
# =========================================================================


class TestRemoveTagsFromDocument:
    """Test remove_tags_from_document()."""

    def test_remove_existing_tag(self) -> None:
        from emdx.models.tags import (
            add_tags_to_document,
            get_document_tags,
            remove_tags_from_document,
        )

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["python", "testing"])
        removed = remove_tags_from_document(doc_id, ["python"])
        assert removed == ["python"]

        remaining = get_document_tags(doc_id)
        assert "python" not in remaining
        assert "testing" in remaining

    def test_remove_nonexistent_tag_returns_empty(self) -> None:
        from emdx.models.tags import add_tags_to_document, remove_tags_from_document

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["python"])
        removed = remove_tags_from_document(doc_id, ["nonexistent"])
        assert removed == []

    def test_remove_text_tags(self) -> None:
        """Removing text tags should work directly."""
        from emdx.models.tags import (
            add_tags_to_document,
            get_document_tags,
            remove_tags_from_document,
        )

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["gameplan", "active"])
        assert "gameplan" in get_document_tags(doc_id)

        removed = remove_tags_from_document(doc_id, ["gameplan"])
        assert "gameplan" in removed

        tags = get_document_tags(doc_id)
        assert "gameplan" not in tags

    def test_remove_decrements_usage_count(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.models.tags import add_tags_to_document, remove_tags_from_document

        doc1 = _create_document(title="Doc 1")
        doc2 = _create_document(title="Doc 2")
        add_tags_to_document(doc1, ["python"])
        add_tags_to_document(doc2, ["python"])

        # usage_count should be 2
        with db_connection.get_connection() as conn:
            cursor = conn.execute("SELECT usage_count FROM tags WHERE name = ?", ("python",))
            assert cursor.fetchone()[0] == 2

        remove_tags_from_document(doc1, ["python"])

        with db_connection.get_connection() as conn:
            cursor = conn.execute("SELECT usage_count FROM tags WHERE name = ?", ("python",))
            assert cursor.fetchone()[0] == 1

    def test_remove_multiple_tags_at_once(self) -> None:
        from emdx.models.tags import (
            add_tags_to_document,
            get_document_tags,
            remove_tags_from_document,
        )

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["python", "javascript", "rust"])
        removed = remove_tags_from_document(doc_id, ["python", "rust"])
        assert sorted(removed) == ["python", "rust"]

        remaining = get_document_tags(doc_id)
        assert len(remaining) == 1
        assert "javascript" in remaining


# =========================================================================
# get_document_tags
# =========================================================================


class TestGetDocumentTags:
    """Test get_document_tags()."""

    def test_returns_tags_for_document(self) -> None:
        from emdx.models.tags import add_tags_to_document, get_document_tags

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["alpha", "beta", "gamma"])
        tags = get_document_tags(doc_id)
        assert sorted(tags) == ["alpha", "beta", "gamma"]

    def test_empty_list_for_untagged_document(self) -> None:
        from emdx.models.tags import get_document_tags

        doc_id = _create_document()
        tags = get_document_tags(doc_id)
        assert tags == []

    def test_returns_text_tags_as_stored(self) -> None:
        """Tags stored as text should be returned as text (no emoji conversion)."""
        from emdx.database.connection import db_connection
        from emdx.models.tags import get_document_tags

        doc_id = _create_document()

        # Insert a tag with a text name directly via SQL
        with db_connection.get_connection() as conn:
            conn.execute("INSERT INTO tags (name, usage_count) VALUES ('gameplan', 1)")
            cursor = conn.execute("SELECT id FROM tags WHERE name = 'gameplan'")
            tag_id = cursor.fetchone()[0]
            conn.execute(
                "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
                (doc_id, tag_id),
            )
            conn.commit()

        tags = get_document_tags(doc_id)
        assert "gameplan" in tags

    def test_returns_tags_sorted_by_name(self) -> None:
        from emdx.models.tags import add_tags_to_document, get_document_tags

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["zebra", "alpha", "middle"])
        tags = get_document_tags(doc_id)
        assert tags == sorted(tags)


# =========================================================================
# get_tags_for_documents (batch operation)
# =========================================================================


class TestGetTagsForDocuments:
    """Test get_tags_for_documents() batch operation."""

    def test_returns_tags_for_multiple_documents(self) -> None:
        from emdx.models.tags import add_tags_to_document, get_tags_for_documents

        doc1 = _create_document(title="Doc 1")
        doc2 = _create_document(title="Doc 2")
        # Use non-alias tags to avoid emoji expansion in assertions
        add_tags_to_document(doc1, ["python", "rust"])
        add_tags_to_document(doc2, ["javascript"])

        result = get_tags_for_documents([doc1, doc2])
        assert doc1 in result
        assert doc2 in result
        assert sorted(result[doc1]) == ["python", "rust"]
        assert result[doc2] == ["javascript"]

    def test_empty_input_returns_empty_dict(self) -> None:
        from emdx.models.tags import get_tags_for_documents

        result = get_tags_for_documents([])
        assert result == {}

    def test_untagged_documents_have_empty_lists(self) -> None:
        from emdx.models.tags import get_tags_for_documents

        doc1 = _create_document(title="Untagged 1")
        doc2 = _create_document(title="Untagged 2")

        result = get_tags_for_documents([doc1, doc2])
        assert result[doc1] == []
        assert result[doc2] == []

    def test_returns_text_tags_as_stored(self) -> None:
        from emdx.models.tags import add_tags_to_document, get_tags_for_documents

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["gameplan", "active"])

        result = get_tags_for_documents([doc_id])
        assert "gameplan" in result[doc_id]
        assert "active" in result[doc_id]

    def test_handles_mixed_tagged_and_untagged(self) -> None:
        from emdx.models.tags import add_tags_to_document, get_tags_for_documents

        doc1 = _create_document(title="Tagged")
        doc2 = _create_document(title="Untagged")
        add_tags_to_document(doc1, ["python"])

        result = get_tags_for_documents([doc1, doc2])
        assert result[doc1] == ["python"]
        assert result[doc2] == []

    def test_returns_distinct_tags(self) -> None:
        """Batch operation should return tags without duplication."""
        from emdx.models.tags import add_tags_to_document, get_tags_for_documents

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["gameplan", "active"])

        result = get_tags_for_documents([doc_id])
        assert result[doc_id].count("gameplan") == 1
        assert result[doc_id].count("active") == 1


# =========================================================================
# list_all_tags
# =========================================================================


class TestListAllTags:
    """Test list_all_tags() with various sort orders."""

    def test_lists_tags_with_usage_stats(self) -> None:
        from emdx.models.tags import add_tags_to_document, list_all_tags

        doc1 = _create_document(title="Doc 1")
        doc2 = _create_document(title="Doc 2")
        add_tags_to_document(doc1, ["python", "javascript"])
        add_tags_to_document(doc2, ["python"])

        tags = list_all_tags()
        assert len(tags) >= 2

        tag_names = [t["name"] for t in tags]
        assert "python" in tag_names
        assert "javascript" in tag_names

    def test_sort_by_usage_default(self) -> None:
        from emdx.models.tags import add_tags_to_document, list_all_tags

        doc1 = _create_document(title="Doc 1")
        doc2 = _create_document(title="Doc 2")
        doc3 = _create_document(title="Doc 3")

        add_tags_to_document(doc1, ["rare"])
        add_tags_to_document(doc1, ["popular"])
        add_tags_to_document(doc2, ["popular"])
        add_tags_to_document(doc3, ["popular"])

        tags = list_all_tags(sort_by="usage")
        tag_names = [t["name"] for t in tags]
        # "popular" has 3 usages, "rare" has 1
        assert tag_names.index("popular") < tag_names.index("rare")

    def test_sort_by_name(self) -> None:
        from emdx.models.tags import add_tags_to_document, list_all_tags

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["zebra", "alpha", "middle"])

        tags = list_all_tags(sort_by="name")
        tag_names = [t["name"] for t in tags]
        assert tag_names == sorted(tag_names)

    def test_sort_by_created_raises_due_to_ambiguous_column(self) -> None:
        """sort_by='created' currently triggers an ambiguous column error.

        The SQL query joins tags and document_tags, both of which have a
        created_at column. The ORDER BY clause uses 'created_at DESC' without
        qualifying which table, causing sqlite3.OperationalError. This test
        documents the current behavior as a known bug.
        """
        import sqlite3

        from emdx.models.tags import add_tags_to_document, list_all_tags

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["first", "second"])

        with pytest.raises(sqlite3.OperationalError, match="ambiguous"):
            list_all_tags(sort_by="created")

    def test_tag_dict_structure(self) -> None:
        """Each tag dict should have the expected keys."""
        from emdx.models.tags import add_tags_to_document, list_all_tags

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["python"])

        tags = list_all_tags()
        assert len(tags) > 0
        tag = tags[0]
        assert "id" in tag
        assert "name" in tag
        assert "count" in tag
        assert "created_at" in tag
        assert "last_used" in tag

    def test_empty_database_returns_empty_list(self) -> None:
        from emdx.models.tags import list_all_tags

        tags = list_all_tags()
        assert tags == []

    def test_returns_text_tag_names(self) -> None:
        """Tags stored as text should be returned as text."""
        from emdx.database.connection import db_connection
        from emdx.models.tags import list_all_tags

        with db_connection.get_connection() as conn:
            conn.execute("INSERT INTO tags (name, usage_count) VALUES ('gameplan', 3)")
            conn.commit()

        tags = list_all_tags()
        tag_names = [t["name"] for t in tags]
        assert "gameplan" in tag_names

    def test_unknown_sort_falls_back_to_usage(self) -> None:
        """An unrecognized sort_by value should fall back to usage order."""
        from emdx.models.tags import add_tags_to_document, list_all_tags

        doc1 = _create_document(title="Doc 1")
        doc2 = _create_document(title="Doc 2")
        add_tags_to_document(doc1, ["rare"])
        add_tags_to_document(doc1, ["popular"])
        add_tags_to_document(doc2, ["popular"])

        tags = list_all_tags(sort_by="nonexistent")
        tag_names = [t["name"] for t in tags]
        assert tag_names.index("popular") < tag_names.index("rare")


# =========================================================================
# search_by_tags
# =========================================================================


class TestSearchByTags:
    """Test search_by_tags() with different modes and options."""

    def test_search_any_mode(self) -> None:
        from emdx.models.tags import add_tags_to_document, search_by_tags

        doc1 = _create_document(title="Python Doc")
        doc2 = _create_document(title="JavaScript Doc")
        doc3 = _create_document(title="No Tags Doc")
        add_tags_to_document(doc1, ["python"])
        add_tags_to_document(doc2, ["javascript"])

        results = search_by_tags(["python", "javascript"], mode="any", prefix_match=False)
        result_ids = [r["id"] for r in results]
        assert doc1 in result_ids
        assert doc2 in result_ids
        assert doc3 not in result_ids

    def test_search_all_mode_exact(self) -> None:
        from emdx.models.tags import add_tags_to_document, search_by_tags

        doc1 = _create_document(title="Has Both")
        doc2 = _create_document(title="Has One")
        add_tags_to_document(doc1, ["python", "testing"])
        add_tags_to_document(doc2, ["python"])

        results = search_by_tags(["python", "testing"], mode="all", prefix_match=False)
        result_ids = [r["id"] for r in results]
        assert doc1 in result_ids
        assert doc2 not in result_ids

    def test_prefix_match_on(self) -> None:
        """prefix_match=True should match 'work' against 'workflow', etc."""
        from emdx.models.tags import add_tags_to_document, search_by_tags

        doc1 = _create_document(title="Workflow Doc")
        doc2 = _create_document(title="Worker Doc")
        add_tags_to_document(doc1, ["workflow"])
        add_tags_to_document(doc2, ["worker"])

        results = search_by_tags(["work"], prefix_match=True)
        result_ids = [r["id"] for r in results]
        assert doc1 in result_ids
        assert doc2 in result_ids

    def test_prefix_match_off(self) -> None:
        """prefix_match=False should only match exact tags."""
        from emdx.models.tags import add_tags_to_document, search_by_tags

        doc1 = _create_document(title="Workflow Doc")
        add_tags_to_document(doc1, ["workflow"])

        results = search_by_tags(["work"], prefix_match=False)
        result_ids = [r["id"] for r in results]
        assert doc1 not in result_ids

    def test_search_text_tags(self) -> None:
        """Text tags should be searchable as-is."""
        from emdx.models.tags import add_tags_to_document, search_by_tags

        doc_id = _create_document(title="Gameplan Doc")
        add_tags_to_document(doc_id, ["gameplan"])

        results = search_by_tags(["gameplan"], prefix_match=False)
        result_ids = [r["id"] for r in results]
        assert doc_id in result_ids

    def test_search_with_project_filter(self) -> None:
        from emdx.models.tags import add_tags_to_document, search_by_tags

        doc1 = _create_document(title="Proj A Doc", project="project-a")
        doc2 = _create_document(title="Proj B Doc", project="project-b")
        add_tags_to_document(doc1, ["python"])
        add_tags_to_document(doc2, ["python"])

        results = search_by_tags(["python"], project="project-a", prefix_match=False)
        result_ids = [r["id"] for r in results]
        assert doc1 in result_ids
        assert doc2 not in result_ids

    def test_search_respects_limit(self) -> None:
        from emdx.models.tags import add_tags_to_document, search_by_tags

        for i in range(5):
            doc_id = _create_document(title=f"Doc {i}")
            add_tags_to_document(doc_id, ["common"])

        results = search_by_tags(["common"], limit=3, prefix_match=False)
        assert len(results) <= 3

    def test_search_excludes_deleted_documents(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.models.tags import add_tags_to_document, search_by_tags

        doc_id = _create_document(title="Deleted Doc")
        add_tags_to_document(doc_id, ["python"])

        # Soft-delete the document
        with db_connection.get_connection() as conn:
            conn.execute("UPDATE documents SET is_deleted = TRUE WHERE id = ?", (doc_id,))
            conn.commit()

        results = search_by_tags(["python"], prefix_match=False)
        result_ids = [r["id"] for r in results]
        assert doc_id not in result_ids

    def test_search_returns_expected_fields(self) -> None:
        from emdx.models.tags import add_tags_to_document, search_by_tags

        doc_id = _create_document(title="Test Doc")
        add_tags_to_document(doc_id, ["python"])

        results = search_by_tags(["python"], prefix_match=False)
        assert len(results) > 0
        result = results[0]
        assert "id" in result
        assert "title" in result
        assert "project" in result
        assert "tags" in result

    def test_search_no_results(self) -> None:
        from emdx.models.tags import search_by_tags

        results = search_by_tags(["nonexistent"], prefix_match=False)
        assert results == []

    def test_all_mode_with_prefix_match_uses_any_logic(self) -> None:
        """When mode='all' but prefix_match=True, it falls back to 'any' logic."""
        from emdx.models.tags import add_tags_to_document, search_by_tags

        doc1 = _create_document(title="Has Workflow")
        doc2 = _create_document(title="Has Worker")
        add_tags_to_document(doc1, ["workflow"])
        add_tags_to_document(doc2, ["worker"])

        # mode="all" + prefix_match=True uses the 'any' branch
        results = search_by_tags(["workflow", "worker"], mode="all", prefix_match=True)
        result_ids = [r["id"] for r in results]
        # Both should match since prefix_match forces 'any' behavior
        assert doc1 in result_ids
        assert doc2 in result_ids


# =========================================================================
# rename_tag
# =========================================================================


class TestRenameTag:
    """Test rename_tag()."""

    def test_rename_existing_tag(self) -> None:
        from emdx.models.tags import add_tags_to_document, get_document_tags, rename_tag

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["oldname"])

        success = rename_tag("oldname", "newname")
        assert success is True

        tags = get_document_tags(doc_id)
        assert "newname" in tags
        assert "oldname" not in tags

    def test_rename_nonexistent_tag(self) -> None:
        from emdx.models.tags import rename_tag

        success = rename_tag("nonexistent", "newname")
        assert success is False

    def test_rename_to_existing_name_fails(self) -> None:
        from emdx.models.tags import add_tags_to_document, rename_tag

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["tag-a", "tag-b"])

        success = rename_tag("tag-a", "tag-b")
        assert success is False

    def test_rename_normalizes_case(self) -> None:
        from emdx.database.connection import db_connection
        from emdx.models.tags import add_tags_to_document, rename_tag

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["oldname"])

        success = rename_tag("OldName", "  NewName  ")
        assert success is True

        # Should be stored as lowercase trimmed
        with db_connection.get_connection() as conn:
            cursor = conn.execute("SELECT name FROM tags WHERE name = 'newname'")
            result = cursor.fetchone()
            assert result is not None


# =========================================================================
# merge_tags
# =========================================================================


class TestMergeTags:
    """Test merge_tags()."""

    def test_merge_source_into_target(self) -> None:
        from emdx.models.tags import (
            add_tags_to_document,
            get_document_tags,
            merge_tags,
        )

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["source-tag"])

        merged_count = merge_tags(["source-tag"], "target-tag")
        assert merged_count > 0

        tags = get_document_tags(doc_id)
        assert "target-tag" in tags
        assert "source-tag" not in tags

    def test_merge_multiple_sources(self) -> None:
        from emdx.models.tags import (
            add_tags_to_document,
            get_document_tags,
            merge_tags,
        )

        doc1 = _create_document(title="Doc 1")
        doc2 = _create_document(title="Doc 2")
        add_tags_to_document(doc1, ["tag-a"])
        add_tags_to_document(doc2, ["tag-b"])

        merged_count = merge_tags(["tag-a", "tag-b"], "unified")
        assert merged_count >= 2

        tags1 = get_document_tags(doc1)
        tags2 = get_document_tags(doc2)
        assert "unified" in tags1
        assert "unified" in tags2
        assert "tag-a" not in tags1
        assert "tag-b" not in tags2

    def test_merge_skips_nonexistent_sources(self) -> None:
        from emdx.models.tags import add_tags_to_document, merge_tags

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["real-tag"])

        merged_count = merge_tags(["real-tag", "fake-tag"], "target")
        # Should process real-tag and skip fake-tag without error
        assert merged_count >= 1

    def test_merge_skips_self_reference(self) -> None:
        """Merging a tag into itself should be a no-op for that source."""
        from emdx.models.tags import add_tags_to_document, merge_tags

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["same-tag"])

        merged_count = merge_tags(["same-tag"], "same-tag")
        assert merged_count == 0

    def test_merge_deletes_source_tags(self) -> None:
        """Source tags should be deleted from the tags table after merge."""
        from emdx.database.connection import db_connection
        from emdx.models.tags import add_tags_to_document, merge_tags

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["obsolete"])

        merge_tags(["obsolete"], "current")

        with db_connection.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM tags WHERE name = 'obsolete'")
            assert cursor.fetchone()[0] == 0

    def test_merge_updates_target_usage_count(self) -> None:
        """Target tag usage_count should reflect actual unique document count."""
        from emdx.database.connection import db_connection
        from emdx.models.tags import add_tags_to_document, merge_tags

        doc1 = _create_document(title="Doc 1")
        doc2 = _create_document(title="Doc 2")
        add_tags_to_document(doc1, ["tag-a"])
        add_tags_to_document(doc2, ["tag-b"])

        merge_tags(["tag-a", "tag-b"], "merged")

        with db_connection.get_connection() as conn:
            cursor = conn.execute("SELECT usage_count FROM tags WHERE name = 'merged'")
            count = cursor.fetchone()[0]
            assert count == 2

    def test_merge_handles_overlap(self) -> None:
        """If a document already has the target tag, merge should not create a duplicate."""
        from emdx.models.tags import (
            add_tags_to_document,
            get_document_tags,
            merge_tags,
        )

        doc_id = _create_document()
        add_tags_to_document(doc_id, ["source", "target"])

        merge_tags(["source"], "target")
        # The document_tags entry for source->doc should be replaced by target->doc
        # but since target->doc already exists, UPDATE OR IGNORE skips it

        tags = get_document_tags(doc_id)
        assert tags.count("target") == 1
        assert "source" not in tags
