"""Tests for the entity extraction and entity-match wikification service."""

from __future__ import annotations

import sqlite3
from typing import Any

from emdx.database.document_links import get_link_count, get_links_for_document, link_exists
from emdx.services.entity_service import (
    _normalize_entity,
    entity_match_wikify,
    entity_wikify_all,
    extract_and_save_entities,
    extract_entities,
)


def _create_doc(conn: sqlite3.Connection, doc_id: int, title: str, content: str) -> None:
    """Insert a test document."""
    conn.execute(
        "INSERT INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 0)",
        (doc_id, title, content),
    )
    conn.commit()


class TestNormalizeEntity:
    """Test entity normalization."""

    def test_lowercase(self) -> None:
        assert _normalize_entity("Auth Module") == "auth module"

    def test_strip_whitespace(self) -> None:
        assert _normalize_entity("  hello world  ") == "hello world"

    def test_collapse_whitespace(self) -> None:
        assert _normalize_entity("auth   module") == "auth module"


class TestExtractEntities:
    """Test heuristic entity extraction."""

    def test_extracts_headings(self) -> None:
        content = "## Authentication Module\n\nSome text.\n\n### Rate Limiter\n"
        entities = extract_entities(content)
        names = {e.normalized for e in entities}
        assert "authentication module" in names
        assert "rate limiter" in names

    def test_heading_type_is_heading(self) -> None:
        content = "## Cosmic Decoder\n\nDetails here."
        entities = extract_entities(content)
        heading_entities = [e for e in entities if e.entity_type == "heading"]
        assert len(heading_entities) >= 1
        assert heading_entities[0].normalized == "cosmic decoder"

    def test_extracts_backtick_terms(self) -> None:
        content = "Use `session_handler` to manage `auth_token` storage."
        entities = extract_entities(content)
        names = {e.normalized for e in entities}
        assert "session_handler" in names
        assert "auth_token" in names

    def test_backtick_type_is_tech_term(self) -> None:
        content = "The `widget_factory` creates widgets."
        entities = extract_entities(content)
        tech = [e for e in entities if e.entity_type == "tech_term"]
        assert len(tech) >= 1
        assert tech[0].normalized == "widget_factory"

    def test_extracts_bold_text(self) -> None:
        content = "The **Quantum Processor** handles all **flux routing**."
        entities = extract_entities(content)
        names = {e.normalized for e in entities}
        assert "quantum processor" in names
        assert "flux routing" in names

    def test_bold_type_is_concept(self) -> None:
        content = "This is **important concept** to understand."
        entities = extract_entities(content)
        concepts = [e for e in entities if e.entity_type == "concept"]
        assert len(concepts) >= 1

    def test_extracts_capitalized_phrases(self) -> None:
        content = "The Session Handler and Auth Module need work."
        entities = extract_entities(content)
        names = {e.normalized for e in entities}
        assert "session handler" in names
        assert "auth module" in names

    def test_capitalized_type_is_proper_noun(self) -> None:
        content = "The Zebra Engine processes data."
        entities = extract_entities(content)
        proper = [e for e in entities if e.entity_type == "proper_noun"]
        assert len(proper) >= 1
        assert proper[0].normalized == "zebra engine"

    def test_skips_short_entities(self) -> None:
        content = "## API\n\nUse `db` for data."
        entities = extract_entities(content)
        names = {e.normalized for e in entities}
        assert "api" not in names
        assert "db" not in names

    def test_skips_stopword_entities(self) -> None:
        content = "## Examples\n\nSome **example** text."
        entities = extract_entities(content)
        names = {e.normalized for e in entities}
        assert "examples" not in names
        assert "example" not in names

    def test_skips_own_title(self) -> None:
        content = "## Architecture Overview\n\nDetails here."
        entities = extract_entities(content, title="Architecture Overview")
        names = {e.normalized for e in entities}
        assert "architecture overview" not in names

    def test_deduplicates(self) -> None:
        content = "## Rate Limiter\n\nThe **Rate Limiter** is important."
        entities = extract_entities(content)
        names = [e.normalized for e in entities]
        assert names.count("rate limiter") == 1

    def test_skips_shell_commands_in_backticks(self) -> None:
        content = "Run `ls /tmp | grep foo` to check."
        entities = extract_entities(content)
        names = {e.normalized for e in entities}
        assert "ls /tmp | grep foo" not in names

    def test_heading_confidence_high(self) -> None:
        content = "## Meteor Scheduler\n\nDetails."
        entities = extract_entities(content)
        heading = next(e for e in entities if e.normalized == "meteor scheduler")
        assert heading.confidence >= 0.9

    def test_capitalized_confidence_lower(self) -> None:
        content = "The Meteor Scheduler runs daily."
        entities = extract_entities(content)
        proper = next(e for e in entities if e.normalized == "meteor scheduler")
        assert proper.confidence < 0.9


class TestEntityWikify:
    """Test entity-match wikification."""

    def test_creates_link_for_shared_entity(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7001,
                "Falcon Scheduler Design",
                "## Architecture\n\nThe `event_loop` processes falcon events.",
            )
            _create_doc(
                conn,
                7002,
                "Falcon Performance Report",
                "The `event_loop` is the bottleneck in falcon processing.",
            )

        # Extract entities for doc 7001 first so they exist in the DB
        extract_and_save_entities(7001)

        # Now wikify doc 7002 — should find shared `event_loop` entity
        result = entity_match_wikify(7002)
        assert result.entities_extracted > 0
        assert result.links_created >= 1
        assert 7001 in result.linked_doc_ids

    def test_no_self_links(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7010,
                "Gecko Router",
                "## Gecko Router\n\nThe `gecko_router` handles routing.",
            )

        entity_match_wikify(7010)
        assert not link_exists(7010, 7010)

    def test_skips_already_linked(self, isolate_test_database: Any) -> None:
        from emdx.database import db
        from emdx.database.document_links import create_link

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7020,
                "Heron Cache Design",
                "The `redis_pool` manages connections.",
            )
            _create_doc(
                conn,
                7021,
                "Heron Cache Performance",
                "The `redis_pool` is the bottleneck.",
            )

        extract_and_save_entities(7020)
        create_link(7021, 7020, similarity_score=0.8, method="auto")

        result = entity_match_wikify(7021)
        assert result.links_created == 0
        assert result.skipped_existing > 0

    def test_nonexistent_document(self, isolate_test_database: Any) -> None:
        result = entity_match_wikify(99998)
        assert result.links_created == 0
        assert result.entities_extracted == 0

    def test_link_method_is_entity_match(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7030,
                "Ibis Queue Design",
                "## Message Processing\n\nThe `message_queue` handles events.",
            )
            _create_doc(
                conn,
                7031,
                "Ibis Queue Bug",
                "## Message Processing\n\nThe `message_queue` has a bug.",
            )

        extract_and_save_entities(7030)
        entity_match_wikify(7031)

        links = get_links_for_document(7031)
        entity_links = [lnk for lnk in links if lnk["method"] == "entity_match"]
        assert len(entity_links) >= 1

    def test_score_reflects_shared_count(self, isolate_test_database: Any) -> None:
        """Documents sharing more entities should have higher scores."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7040,
                "Jackal Engine Core",
                "## Event Loop\n\nThe `task_scheduler` and `event_loop` "
                "coordinate via **Message Bus**.",
            )
            _create_doc(
                conn,
                7041,
                "Jackal Engine Performance",
                "## Event Loop\n\nThe `task_scheduler` and `event_loop` "
                "and **Message Bus** are all slow.",
            )

        extract_and_save_entities(7040)
        result = entity_match_wikify(7041)
        assert result.links_created >= 1

        links = get_links_for_document(7041)
        entity_links = [lnk for lnk in links if lnk["method"] == "entity_match"]
        if entity_links:
            # Score should be > 0.5 since we share multiple entities
            assert entity_links[0]["similarity_score"] > 0.5

    def test_idempotent(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7050,
                "Kiwi Validator Core",
                "The `schema_check` validates inputs.",
            )
            _create_doc(
                conn,
                7051,
                "Kiwi Validator Tests",
                "The `schema_check` needs more tests.",
            )

        extract_and_save_entities(7050)
        result1 = entity_match_wikify(7051)
        result2 = entity_match_wikify(7051)

        assert result2.links_created == 0
        assert get_link_count(7051) == result1.links_created


class TestExtractAndSave:
    """Test entity persistence."""

    def test_saves_entities_to_db(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7100,
                "Lemur Proxy Design",
                "## Connection Pool\n\nThe `http_client` connects to upstream.",
            )

        count = extract_and_save_entities(7100)
        assert count >= 2  # At least heading + backtick term

        with db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT entity, entity_type FROM document_entities WHERE document_id = ?",
                (7100,),
            )
            rows = cursor.fetchall()

        entity_names = {row[0] for row in rows}
        assert "connection pool" in entity_names
        assert "http_client" in entity_names

    def test_nonexistent_doc_returns_zero(self, isolate_test_database: Any) -> None:
        count = extract_and_save_entities(99997)
        assert count == 0


class TestEntityWikifyAll:
    """Test batch entity wikification."""

    def test_processes_all_docs(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7200,
                "Manta Allocator Core",
                "The `memory_pool` allocates buffers.",
            )
            _create_doc(
                conn,
                7201,
                "Manta Allocator Bug",
                "The `memory_pool` leaks memory.",
            )

        total_entities, total_links, docs = entity_wikify_all()
        assert docs >= 2
        assert total_entities >= 2
        assert total_links >= 1
