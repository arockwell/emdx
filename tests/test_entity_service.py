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

    # --- Stopword filtering tests ---

    def test_skips_heading_stopwords(self) -> None:
        """Generic structural headings should be filtered out."""
        content = (
            "## Summary\n\n## Overview\n\n## Conclusion\n\n"
            "## Recommendations\n\n## Executive Summary\n"
        )
        entities = extract_entities(content)
        names = {e.normalized for e in entities}
        assert "summary" not in names
        assert "overview" not in names
        assert "conclusion" not in names
        assert "recommendations" not in names
        assert "executive summary" not in names

    def test_keeps_specific_headings(self) -> None:
        """Non-generic headings should still be extracted."""
        content = "## Falcon Scheduler Architecture\n\n## Redis Connection Pool\n"
        entities = extract_entities(content)
        names = {e.normalized for e in entities}
        assert "falcon scheduler architecture" in names
        assert "redis connection pool" in names

    def test_skips_concept_stopwords(self) -> None:
        """Noisy bold label patterns should be filtered."""
        content = "The **file:** is located at /tmp. The **issue:** is critical."
        entities = extract_entities(content)
        names = {e.normalized for e in entities}
        assert "file:" not in names
        assert "issue:" not in names

    def test_strips_proper_noun_suffix_noise(self) -> None:
        """Trailing noise words on proper nouns should be stripped."""
        content = "The Summary Successfully completed. Conclusion The end."
        entities = extract_entities(content)
        names = {e.normalized for e in entities}
        # "Summary Successfully" should be stripped to just "Summary"
        # which is too short or a stopword, so it won't appear
        assert "summary successfully" not in names
        assert "conclusion the" not in names


class TestEntityWikify:
    """Test entity-match wikification."""

    def test_creates_link_for_shared_entities(self, isolate_test_database: Any) -> None:
        """Two docs sharing ≥2 entities should be linked."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7001,
                "Falcon Scheduler Design",
                "## Falcon Pipeline\n\nThe `event_loop` processes falcon events "
                "using the `task_scheduler` for coordination.",
            )
            _create_doc(
                conn,
                7002,
                "Falcon Performance Report",
                "## Falcon Bottleneck\n\nThe `event_loop` is slow and the "
                "`task_scheduler` needs optimization.",
            )

        extract_and_save_entities(7001)
        result = entity_match_wikify(7002)
        assert result.entities_extracted > 0
        assert result.links_created >= 1
        assert 7001 in result.linked_doc_ids

    def test_no_link_for_single_shared_entity(self, isolate_test_database: Any) -> None:
        """Docs sharing only 1 entity should NOT be linked (MIN_SHARED_ENTITIES=2)."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7003,
                "Osprey Cache Design",
                "The `redis_pool` manages connections.",
            )
            _create_doc(
                conn,
                7004,
                "Pelican Queue Design",
                "The `redis_pool` is the bottleneck.",
            )

        extract_and_save_entities(7003)
        result = entity_match_wikify(7004)
        assert result.links_created == 0

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
                "The `redis_pool` manages connections via `cache_layer` proxy.",
            )
            _create_doc(
                conn,
                7021,
                "Heron Cache Performance",
                "The `redis_pool` and `cache_layer` are bottlenecks.",
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
                "## Ibis Message Layer\n\nThe `message_queue` and "
                "`event_dispatcher` handle events.",
            )
            _create_doc(
                conn,
                7031,
                "Ibis Queue Bug",
                "## Ibis Event Layer\n\nThe `message_queue` and `event_dispatcher` have a bug.",
            )

        extract_and_save_entities(7030)
        entity_match_wikify(7031)

        links = get_links_for_document(7031)
        entity_links = [lnk for lnk in links if lnk["link_type"] == "entity_match"]
        assert len(entity_links) >= 1

    def test_score_uses_idf_jaccard(self, isolate_test_database: Any) -> None:
        """IDF-weighted Jaccard scores should be between 0 and 1."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7040,
                "Jackal Engine Core",
                "## Jackal Internals\n\nThe `task_scheduler` and `event_loop` "
                "and `thread_pool` coordinate via **Jackal Bus**.",
            )
            _create_doc(
                conn,
                7041,
                "Jackal Engine Performance",
                "## Jackal Metrics\n\nThe `task_scheduler` and `event_loop` "
                "and `thread_pool` and **Jackal Bus** are all slow.",
            )

        extract_and_save_entities(7040)
        result = entity_match_wikify(7041)
        assert result.links_created >= 1

        links = get_links_for_document(7041)
        entity_links = [lnk for lnk in links if lnk["link_type"] == "entity_match"]
        assert len(entity_links) >= 1
        score = entity_links[0]["similarity_score"]
        assert 0.0 < score <= 1.0

    def test_idempotent(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7050,
                "Kiwi Validator Core",
                "The `schema_check` validates inputs via `rule_engine`.",
            )
            _create_doc(
                conn,
                7051,
                "Kiwi Validator Tests",
                "The `schema_check` and `rule_engine` need more tests.",
            )

        extract_and_save_entities(7050)
        result1 = entity_match_wikify(7051)
        result2 = entity_match_wikify(7051)

        assert result2.links_created == 0
        assert get_link_count(7051) == result1.links_created

    def test_top_k_cap(self, isolate_test_database: Any) -> None:
        """Entity links should be capped at MAX_ENTITY_LINKS per doc."""
        from emdx.database import db
        from emdx.services.entity_service import MAX_ENTITY_LINKS

        # Create 15 docs all sharing the same 3 entities with the source
        shared_content = (
            "The `quasar_engine` and `photon_beam` and `neutron_flux` are critical components."
        )
        with db.get_connection() as conn:
            for i in range(15):
                _create_doc(
                    conn,
                    7060 + i,
                    f"Quasar Module {i}",
                    shared_content,
                )

        # Extract entities for all 15 docs
        for i in range(15):
            extract_and_save_entities(7060 + i)

        # Wikify the last doc — should be capped
        result = entity_match_wikify(7074)
        assert result.links_created <= MAX_ENTITY_LINKS


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
                "The `memory_pool` allocates buffers via `arena_alloc`.",
            )
            _create_doc(
                conn,
                7201,
                "Manta Allocator Bug",
                "The `memory_pool` and `arena_alloc` leak memory.",
            )

        total_entities, total_links, docs = entity_wikify_all()
        assert docs >= 2
        assert total_entities >= 2
        assert total_links >= 1

    def test_rebuild_clears_existing_links(self, isolate_test_database: Any) -> None:
        """--rebuild should delete entity_match links before regenerating."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                7210,
                "Narwhal Parser Core",
                "The `token_stream` feeds the `syntax_tree` builder.",
            )
            _create_doc(
                conn,
                7211,
                "Narwhal Parser Tests",
                "The `token_stream` and `syntax_tree` need tests.",
            )

        # First pass creates links
        _, links1, _ = entity_wikify_all()
        assert links1 >= 1

        # Count entity_match links before rebuild
        with db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM document_links WHERE link_type = 'entity_match'"
            )
            count_before = cursor.fetchone()[0]

        # Rebuild should clear and recreate — not double
        _, links2, _ = entity_wikify_all(rebuild=True)
        assert links2 >= 1

        with db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM document_links WHERE link_type = 'entity_match'"
            )
            count_after = cursor.fetchone()[0]

        # Should be roughly same count, not doubled
        assert count_after <= count_before + 2  # allow small variance from IDF
        assert count_after >= 1  # links were recreated
