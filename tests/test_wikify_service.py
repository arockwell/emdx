"""Tests for the wikify service (title-match wikification)."""

from __future__ import annotations

import sqlite3
from typing import Any

import pytest

from emdx.database.document_links import (
    get_link_count,
    get_links_for_document,
    link_exists,
)
from emdx.services.wikify_service import (
    _build_title_pattern,
    _normalize_title,
    title_match_wikify,
    wikify_all,
)


def _create_doc(conn: sqlite3.Connection, doc_id: int, title: str, content: str) -> None:
    """Insert a test document."""
    conn.execute(
        "INSERT INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 0)",
        (doc_id, title, content),
    )
    conn.commit()


class TestNormalizeTitle:
    """Test title normalization."""

    def test_lowercase(self) -> None:
        assert _normalize_title("Auth Module") == "auth module"

    def test_strip_whitespace(self) -> None:
        assert _normalize_title("  hello  ") == "hello"

    def test_strip_leading_punctuation(self) -> None:
        assert _normalize_title("## Auth Module") == "auth module"

    def test_strip_trailing_punctuation(self) -> None:
        assert _normalize_title("Auth Module...") == "auth module"

    def test_keep_internal_punctuation(self) -> None:
        assert _normalize_title("Auth-Module") == "auth-module"

    def test_keep_internal_apostrophe(self) -> None:
        assert _normalize_title("User's Guide") == "user's guide"


class TestBuildTitlePattern:
    """Test word-boundary pattern building."""

    def test_matches_exact(self) -> None:
        pattern = _build_title_pattern("auth module")
        assert pattern.search("auth module")

    def test_matches_in_sentence(self) -> None:
        pattern = _build_title_pattern("auth module")
        assert pattern.search("the auth module broke yesterday")

    def test_no_match_partial_word(self) -> None:
        pattern = _build_title_pattern("auth")
        assert not pattern.search("authorization failed")

    def test_matches_at_start(self) -> None:
        pattern = _build_title_pattern("auth module")
        assert pattern.search("auth module is broken")

    def test_matches_at_end(self) -> None:
        pattern = _build_title_pattern("auth module")
        assert pattern.search("we fixed the auth module")

    def test_case_insensitive(self) -> None:
        pattern = _build_title_pattern("auth module")
        assert pattern.search("The Auth Module works")

    def test_special_regex_chars_escaped(self) -> None:
        pattern = _build_title_pattern("c++ guide")
        assert pattern.search("read the c++ guide")
        assert not pattern.search("cppp guide")

    def test_hyphenated_title(self) -> None:
        pattern = _build_title_pattern("session-handling")
        assert pattern.search("the session-handling code")

    def test_no_match_different_word(self) -> None:
        pattern = _build_title_pattern("auth module")
        assert not pattern.search("authentication module")


class TestTitleMatchWikify:
    """Test the main wikification function."""

    def test_creates_link_for_title_mention(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                5001,
                "Quantum Flux Refactor",
                "Details about the quantum flux refactor.",
            )
            _create_doc(
                conn,
                5002,
                "Session Bug Report",
                "The quantum flux refactor broke session handling.",
            )

        result = title_match_wikify(5002)
        assert result.links_created == 1
        assert 5001 in result.linked_doc_ids
        assert link_exists(5002, 5001)

    def test_no_self_links(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(
                conn,
                5010,
                "Vortex Handler",
                "The vortex handler manages vortex events.",
            )

        result = title_match_wikify(5010)
        assert result.links_created == 0
        assert not link_exists(5010, 5010)

    def test_skips_short_titles(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(conn, 5020, "API", "Short title doc.")
            _create_doc(conn, 5021, "Uses the API extensively", "Content about API usage.")

        result = title_match_wikify(5021)
        assert result.links_created == 0

    def test_skips_stopword_titles(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(conn, 5030, "Notes", "Some notes.")
            _create_doc(conn, 5031, "My meeting notes from today", "Content.")

        result = title_match_wikify(5031)
        assert result.links_created == 0

    def test_skips_already_linked(self, isolate_test_database: Any) -> None:
        from emdx.database import db
        from emdx.database.document_links import create_link

        with db.get_connection() as conn:
            _create_doc(
                conn,
                5040,
                "Zebra Migration Plan",
                "Details about zebra migrations.",
            )
            _create_doc(
                conn,
                5041,
                "Bug Report",
                "The zebra migration plan has a bug.",
            )

        # Pre-create the link
        create_link(5041, 5040, similarity_score=0.8, method="auto")

        result = title_match_wikify(5041)
        assert result.links_created == 0
        assert result.skipped_existing == 1

    def test_nonexistent_document(self, isolate_test_database: Any) -> None:
        result = title_match_wikify(99999)
        assert result.links_created == 0

    def test_multiple_title_matches(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(conn, 5050, "Flamingo Renderer", "Flamingo rendering engine.")
            _create_doc(conn, 5051, "Pelican Pipeline", "Pelican pipeline stuff.")
            _create_doc(
                conn,
                5052,
                "Integration Report",
                "The flamingo renderer and pelican pipeline both need work.",
            )

        result = title_match_wikify(5052)
        assert result.links_created == 2
        assert set(result.linked_doc_ids) == {5050, 5051}

    def test_word_boundary_prevents_substring_match(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(conn, 5060, "xray", "About xray scanning.")
            _create_doc(
                conn,
                5061,
                "Xray Report",
                "The xrayscanner module failed.",
            )

        # "xray" is exactly MIN_TITLE_LENGTH so it passes the filter,
        # but word boundary check prevents matching "xrayscanner"
        result = title_match_wikify(5061)
        assert result.links_created == 0

    def test_dry_run_reports_matches(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(conn, 5070, "Narwhal Processor", "Narwhal stuff.")
            _create_doc(
                conn,
                5071,
                "Narwhal Bug Report",
                "The narwhal processor has a bug.",
            )

        result = title_match_wikify(5071, dry_run=True)
        assert result.links_created == 0
        assert len(result.dry_run_matches) == 1
        assert result.dry_run_matches[0] == (5070, "Narwhal Processor")
        # Verify no actual link was created
        assert not link_exists(5071, 5070)

    def test_idempotent(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(conn, 5080, "Osprey Controller", "Osprey stuff.")
            _create_doc(
                conn,
                5081,
                "Osprey Bug Report",
                "The osprey controller has a bug.",
            )

        result1 = title_match_wikify(5081)
        assert result1.links_created == 1

        result2 = title_match_wikify(5081)
        assert result2.links_created == 0
        assert result2.skipped_existing == 1

        # Only one link exists
        assert get_link_count(5081) == 1

    def test_deleted_docs_excluded(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 1)",
                (5090, "Platypus Engine", "Deleted platypus doc."),
            )
            _create_doc(
                conn,
                5091,
                "Platypus Bug Report",
                "The platypus engine has a bug.",
            )
            conn.commit()

        result = title_match_wikify(5091)
        assert result.links_created == 0

    def test_title_with_special_regex_chars(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(conn, 5100, "C++ Performance Guide", "C++ perf tips.")
            _create_doc(
                conn,
                5101,
                "Compiler Review Notes",
                "Read the C++ Performance Guide before the review.",
            )

        result = title_match_wikify(5101)
        assert result.links_created == 1
        assert 5100 in result.linked_doc_ids

    def test_link_method_is_title_match(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(conn, 5110, "Iguana Scheduler", "Iguana stuff.")
            _create_doc(
                conn,
                5111,
                "Iguana Bug Report",
                "The iguana scheduler has a bug.",
            )

        title_match_wikify(5111)

        links = get_links_for_document(5111)
        assert len(links) >= 1
        title_match_links = [lnk for lnk in links if lnk["link_type"] == "title_match"]
        assert len(title_match_links) == 1
        assert title_match_links[0]["similarity_score"] == pytest.approx(1.0)

    def test_multiple_occurrences_single_link(self, isolate_test_database: Any) -> None:
        """Title appearing multiple times in content should create only one link."""
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(conn, 5120, "Toucan Allocator", "Toucan stuff.")
            _create_doc(
                conn,
                5121,
                "Toucan Report",
                "The toucan allocator is broken. We need to fix toucan allocator soon. "
                "The toucan allocator team agrees.",
            )

        result = title_match_wikify(5121)
        assert result.links_created == 1


class TestWikifyAll:
    """Test batch wikification."""

    def test_wikify_all_creates_links(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(conn, 5200, "Walrus Orchestrator", "Walrus details.")
            _create_doc(
                conn,
                5201,
                "Yak Pipeline Bug",
                "The walrus orchestrator has a yak pipeline bug.",
            )

        total_created, docs_processed = wikify_all()
        assert docs_processed >= 2
        # At least one new link: 5201 -> 5200
        assert total_created >= 1

    def test_wikify_all_dry_run(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            _create_doc(conn, 5210, "Axolotl Validator", "Axolotl details.")
            _create_doc(
                conn,
                5211,
                "Axolotl Bug Report",
                "The axolotl validator has bugs.",
            )

        before_5210 = get_link_count(5210)
        before_5211 = get_link_count(5211)

        total_would_create, docs_processed = wikify_all(dry_run=True)
        assert docs_processed >= 2
        # Dry run reports matches that would be created
        assert total_would_create >= 1
        # But no actual links should have been created
        assert get_link_count(5210) == before_5210
        assert get_link_count(5211) == before_5211
