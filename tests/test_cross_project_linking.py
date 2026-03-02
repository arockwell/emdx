"""Tests for cross-project auto-linking (title-match and entity-match)."""

from __future__ import annotations

import sqlite3
from typing import Any

from emdx.database.document_links import link_exists
from emdx.services.entity_service import (
    entity_match_wikify,
    entity_wikify_all,
    extract_and_save_entities,
)
from emdx.services.wikify_service import title_match_wikify, wikify_all


def _create_doc(
    conn: sqlite3.Connection,
    doc_id: int,
    title: str,
    content: str,
    project: str | None = None,
) -> None:
    """Insert a test document with an optional project."""
    conn.execute(
        "INSERT INTO documents (id, title, content, project, is_deleted) VALUES (?, ?, ?, ?, 0)",
        (doc_id, title, content, project),
    )
    conn.commit()


class TestTitleMatchCrossProject:
    """Test cross-project title-match wikification."""

    def test_same_project_only_by_default(self, isolate_test_database: Any) -> None:
        """Default behavior: only match titles within same project."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                8001,
                "Quantum Flux Refactor",
                "Details about the quantum flux refactor.",
                project="project-alpha",
            )
            _create_doc(
                conn,
                8002,
                "Session Bug Report",
                "The quantum flux refactor broke sessions.",
                project="project-beta",
            )

        # Default: cross_project=False — different projects, no link
        result = title_match_wikify(8002)
        assert result.links_created == 0

    def test_cross_project_finds_matches(self, isolate_test_database: Any) -> None:
        """cross_project=True finds titles across projects."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                8011,
                "Nebula Processor Design",
                "Design of the nebula processor.",
                project="project-alpha",
            )
            _create_doc(
                conn,
                8012,
                "Integration Report",
                "The nebula processor design needs review.",
                project="project-beta",
            )

        result = title_match_wikify(8012, cross_project=True)
        assert result.links_created == 1
        assert 8011 in result.linked_doc_ids

    def test_same_project_links_normally(self, isolate_test_database: Any) -> None:
        """Same project docs still link with default settings."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                8021,
                "Prism Allocator",
                "The prism allocator handles memory.",
                project="project-gamma",
            )
            _create_doc(
                conn,
                8022,
                "Prism Bug Report",
                "The prism allocator has a bug.",
                project="project-gamma",
            )

        result = title_match_wikify(8022)
        assert result.links_created == 1
        assert 8021 in result.linked_doc_ids

    def test_null_project_matches_all_when_not_cross(self, isolate_test_database: Any) -> None:
        """Docs with NULL project match all docs (no project filter)."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                8031,
                "Zephyr Blaster Module",
                "The zephyr blaster module handles events.",
                project=None,
            )
            _create_doc(
                conn,
                8032,
                "Zephyr Bug Report",
                "The zephyr blaster module has issues.",
                project="project-delta",
            )

        # Doc 8032 has project="project-delta", so it looks for
        # candidates in "project-delta" only — doc 8031 is NULL
        result = title_match_wikify(8032)
        assert result.links_created == 0

        # With cross_project, it finds across all projects
        result = title_match_wikify(8032, cross_project=True)
        assert result.links_created >= 1
        assert 8031 in result.linked_doc_ids


class TestWikifyAllCrossProject:
    """Test batch title-match wikification with cross-project."""

    def test_wikify_all_respects_cross_project(self, isolate_test_database: Any) -> None:
        """wikify_all with cross_project=True links across projects."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                8101,
                "Aurora Pipeline",
                "The aurora pipeline processes data.",
                project="proj-x",
            )
            _create_doc(
                conn,
                8102,
                "Aurora Bug Fix",
                "Fixed the aurora pipeline crash.",
                project="proj-y",
            )

        # Default: no cross-project links
        total, docs = wikify_all()
        cross_link = link_exists(8101, 8102)
        if not cross_link:
            # Now try with cross_project
            total_cross, _ = wikify_all(cross_project=True)
            assert total_cross >= 1
            assert link_exists(8101, 8102) or link_exists(8102, 8101)


class TestEntityMatchCrossProject:
    """Test cross-project entity-match wikification."""

    def test_same_project_only_by_default(self, isolate_test_database: Any) -> None:
        """Default: entity-match only within same project."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                8201,
                "Xenon Scheduler Design",
                "## Xenon Pipeline\n\n"
                "The `xenon_event_loop` processes xenon events "
                "using the `xenon_scheduler` for coordination.",
                project="proj-a",
            )
            _create_doc(
                conn,
                8202,
                "Xenon Performance Report",
                "## Xenon Bottleneck\n\n"
                "The `xenon_event_loop` is slow and the "
                "`xenon_scheduler` needs optimization.",
                project="proj-b",
            )

        extract_and_save_entities(8201)
        result = entity_match_wikify(8202)
        # Different projects, default cross_project=False
        assert result.links_created == 0

    def test_cross_project_entity_match(self, isolate_test_database: Any) -> None:
        """cross_project=True enables entity-match across projects."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                8211,
                "Zircon Cache Design",
                "## Zircon Architecture\n\n"
                "The `zircon_pool` manages connections "
                "via `zircon_layer` proxy.",
                project="proj-a",
            )
            _create_doc(
                conn,
                8212,
                "Zircon Cache Performance",
                "## Zircon Analysis\n\nThe `zircon_pool` and `zircon_layer` are bottlenecks.",
                project="proj-b",
            )

        extract_and_save_entities(8211)
        result = entity_match_wikify(8212, cross_project=True)
        assert result.links_created >= 1
        assert 8211 in result.linked_doc_ids

    def test_same_project_entities_link_normally(self, isolate_test_database: Any) -> None:
        """Same project entity-match works with default settings."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                8221,
                "Yttrium Queue Core",
                "The `yttrium_queue` and `yttrium_dispatch` handle events.",
                project="proj-c",
            )
            _create_doc(
                conn,
                8222,
                "Yttrium Queue Bug",
                "The `yttrium_queue` and `yttrium_dispatch` have a bug.",
                project="proj-c",
            )

        extract_and_save_entities(8221)
        result = entity_match_wikify(8222)
        assert result.links_created >= 1
        assert 8221 in result.linked_doc_ids


class TestEntityWikifyAllCrossProject:
    """Test batch entity wikification with cross-project."""

    def test_entity_wikify_all_cross_project(self, isolate_test_database: Any) -> None:
        """entity_wikify_all with cross_project=True links across."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                8301,
                "Tungsten Router Core",
                "The `tungsten_router` and `tungsten_stack` handle requests.",
                project="proj-m",
            )
            _create_doc(
                conn,
                8302,
                "Tungsten Router Tests",
                "The `tungsten_router` and `tungsten_stack` need testing.",
                project="proj-n",
            )

        # Default: no cross-project links
        _, links_default, _ = entity_wikify_all()
        has_link = link_exists(8301, 8302) or link_exists(8302, 8301)
        if not has_link:
            # Rebuild with cross-project
            _, links_cross, _ = entity_wikify_all(rebuild=True, cross_project=True)
            assert links_cross >= 1
            assert link_exists(8301, 8302) or link_exists(8302, 8301)

    def test_entity_wikify_all_default_respects_project(self, isolate_test_database: Any) -> None:
        """entity_wikify_all default does NOT link across projects."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                8311,
                "Hafnium Queue Design",
                "The `hafnium_runner` and `hafnium_queue` process background tasks.",
                project="proj-p",
            )
            _create_doc(
                conn,
                8312,
                "Hafnium Queue Report",
                "The `hafnium_runner` and `hafnium_queue` are slow.",
                project="proj-q",
            )

        _, links, _ = entity_wikify_all()
        has_link = link_exists(8311, 8312) or link_exists(8312, 8311)
        assert not has_link


class TestCrossProjectConfig:
    """Test that the DEFAULT_CROSS_PROJECT_LINKING constant exists."""

    def test_constant_exists(self) -> None:
        from emdx.config.constants import DEFAULT_CROSS_PROJECT_LINKING

        assert DEFAULT_CROSS_PROJECT_LINKING is False
