"""Tests for wiki topic merge and split commands (Issue #1244)."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app

runner = CliRunner()


def _setup_wiki_topic(
    conn: sqlite3.Connection,
    topic_id: int,
    label: str = "Test Topic",
    slug: str | None = None,
    with_article: bool = False,
    members: list[int] | None = None,
) -> None:
    """Insert a wiki topic with optional article and members."""
    if slug is None:
        slug = f"test-topic-{topic_id}"
    conn.execute(
        "INSERT INTO wiki_topics (id, topic_slug, topic_label, entity_fingerprint, status) "
        "VALUES (?, ?, ?, 'fp', 'active')",
        (topic_id, slug, label),
    )
    if with_article:
        doc_id = topic_id + 1000
        conn.execute(
            "INSERT INTO documents (id, title, content, is_deleted) "
            "VALUES (?, ?, 'Article body', 0)",
            (doc_id, f"Wiki: {label}"),
        )
        conn.execute(
            "INSERT INTO wiki_articles (topic_id, document_id, source_hash) VALUES (?, ?, 'hash')",
            (topic_id, doc_id),
        )
    if members:
        for mid in members:
            # Ensure the member document exists
            existing = conn.execute("SELECT id FROM documents WHERE id = ?", (mid,)).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO documents (id, title, content, is_deleted) "
                    "VALUES (?, ?, 'content', 0)",
                    (mid, f"Doc {mid}"),
                )
            conn.execute(
                "INSERT INTO wiki_topic_members "
                "(topic_id, document_id, relevance_score, is_primary) "
                "VALUES (?, ?, 1.0, 1)",
                (topic_id, mid),
            )
    conn.commit()


def _cleanup_topics(conn: sqlite3.Connection, topic_ids: list[int]) -> None:
    """Remove wiki topics and related rows."""
    for tid in topic_ids:
        doc_id = tid + 1000
        conn.execute(
            "DELETE FROM wiki_article_sources WHERE article_id IN "
            "(SELECT id FROM wiki_articles WHERE topic_id = ?)",
            (tid,),
        )
        conn.execute("DELETE FROM wiki_articles WHERE topic_id = ?", (tid,))
        conn.execute("DELETE FROM wiki_topic_members WHERE topic_id = ?", (tid,))
        conn.execute("DELETE FROM wiki_topics WHERE id = ?", (tid,))
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    conn.commit()


def _cleanup_docs(conn: sqlite3.Connection, doc_ids: list[int]) -> None:
    """Remove documents by IDs."""
    for did in doc_ids:
        conn.execute("DELETE FROM documents WHERE id = ?", (did,))
    conn.commit()


# --- Merge Tests ---


class TestWikiMergeCommand:
    """Test 'emdx maintain wiki merge' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=80, label="Auth", slug="auth", members=[801, 802])
            _setup_wiki_topic(
                conn, topic_id=81, label="Security", slug="security", members=[803, 804]
            )
        yield
        with db.get_connection() as conn:
            _cleanup_topics(conn, [80, 81])
            _cleanup_docs(conn, [801, 802, 803, 804])

    def test_merge_combines_members(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "merge", "80", "81"])
        assert result.exit_code == 0
        assert "Merged topic 81" in result.output
        assert "Auth" in result.output
        assert "Security" in result.output

        with db.get_connection() as conn:
            members = conn.execute(
                "SELECT document_id FROM wiki_topic_members WHERE topic_id = 80 "
                "ORDER BY document_id"
            ).fetchall()
            doc_ids = [r[0] for r in members]
            assert doc_ids == [801, 802, 803, 804]

    def test_merge_updates_label_and_slug(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "merge", "80", "81"])
        assert result.exit_code == 0

        with db.get_connection() as conn:
            row = conn.execute(
                "SELECT topic_label, topic_slug FROM wiki_topics WHERE id = 80"
            ).fetchone()
            assert row[0] == "Auth & Security"
            assert row[1] == "auth-security"

    def test_merge_deletes_source_topic(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "merge", "80", "81"])
        assert result.exit_code == 0

        with db.get_connection() as conn:
            row = conn.execute("SELECT id FROM wiki_topics WHERE id = 81").fetchone()
            assert row is None

    def test_merge_shows_member_counts(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "merge", "80", "81"])
        assert result.exit_code == 0
        assert "Members moved: 2" in result.output
        assert "Total members: 4" in result.output

    def test_merge_nonexistent_target(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "merge", "999", "81"])
        assert result.exit_code == 1
        assert "999 not found" in result.output

    def test_merge_nonexistent_source(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "merge", "80", "999"])
        assert result.exit_code == 1
        assert "999 not found" in result.output

    def test_merge_self(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "merge", "80", "80"])
        assert result.exit_code == 1
        assert "cannot merge a topic with itself" in result.output


class TestWikiMergeWithOverlap:
    """Test merge when both topics share a member document."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(conn, topic_id=82, label="A", slug="overlap-a", members=[810, 811])
            _setup_wiki_topic(conn, topic_id=83, label="B", slug="overlap-b", members=[811, 812])
        yield
        with db.get_connection() as conn:
            _cleanup_topics(conn, [82, 83])
            _cleanup_docs(conn, [810, 811, 812])

    def test_merge_skips_duplicate_members(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "merge", "82", "83"])
        assert result.exit_code == 0
        # Doc 811 was in both — only 812 should be moved
        assert "Members moved: 1" in result.output
        assert "Total members: 3" in result.output


class TestWikiMergeWithArticle:
    """Test merge deletes the source topic's wiki article."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            _setup_wiki_topic(
                conn,
                topic_id=84,
                label="Target",
                slug="merge-target",
                members=[820],
                with_article=True,
            )
            _setup_wiki_topic(
                conn,
                topic_id=85,
                label="Source",
                slug="merge-source",
                members=[821],
                with_article=True,
            )
        yield
        with db.get_connection() as conn:
            _cleanup_topics(conn, [84, 85])
            _cleanup_docs(conn, [820, 821])

    def test_merge_deletes_source_article(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "merge", "84", "85"])
        assert result.exit_code == 0
        assert "Deleted wiki article" in result.output

        with db.get_connection() as conn:
            # Source article should be gone
            article = conn.execute("SELECT id FROM wiki_articles WHERE topic_id = 85").fetchone()
            assert article is None

            # Source article's document should be soft-deleted
            doc = conn.execute("SELECT is_deleted FROM documents WHERE id = 1085").fetchone()
            assert doc[0] == 1

    def test_merge_marks_target_article_stale(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "merge", "84", "85"])
        assert result.exit_code == 0

        with db.get_connection() as conn:
            article = conn.execute(
                "SELECT is_stale, stale_reason FROM wiki_articles WHERE topic_id = 84"
            ).fetchone()
            assert article[0] == 1
            assert article[1] == "topic merged"


# --- Split Tests ---


class TestWikiSplitCommand:
    """Test 'emdx maintain wiki split' CLI command."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            # Create docs with specific content for entity matching
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (830, 'OAuth Setup Guide', 'How to configure OAuth for your app', 0)"
            )
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (831, 'JWT Tokens', 'JWT token validation and refresh', 0)"
            )
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (832, 'OAuth Scopes', 'Managing OAuth permission scopes', 0)"
            )
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (833, 'Session Management', 'Handling user sessions securely', 0)"
            )
            _setup_wiki_topic(
                conn,
                topic_id=86,
                label="Auth / Security",
                slug="auth-security",
                members=[830, 831, 832, 833],
            )
        yield
        with db.get_connection() as conn:
            # Clean up new topic created by split (find it dynamically)
            new_topics = conn.execute("SELECT id FROM wiki_topics WHERE id != 86").fetchall()
            all_topic_ids = [86] + [r[0] for r in new_topics]
            _cleanup_topics(conn, all_topic_ids)
            _cleanup_docs(conn, [830, 831, 832, 833])

    def test_split_moves_matching_docs(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "split", "86", "--entity", "OAuth"])
        assert result.exit_code == 0
        assert "Split topic 86" in result.output
        assert "Moved 2 doc(s)" in result.output
        assert "830" in result.output
        assert "832" in result.output
        assert "Remaining in original: 2" in result.output

    def test_split_creates_new_topic(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "split", "86", "--entity", "OAuth"])
        assert result.exit_code == 0

        with db.get_connection() as conn:
            new_topic = conn.execute(
                "SELECT id, topic_label, topic_slug FROM wiki_topics WHERE topic_label = 'OAuth'"
            ).fetchone()
            assert new_topic is not None
            assert new_topic[2] == "oauth"

    def test_split_moves_members_correctly(self) -> None:
        runner.invoke(app, ["maintain", "wiki", "split", "86", "--entity", "OAuth"])

        with db.get_connection() as conn:
            # Original topic should retain non-OAuth docs
            original_members = conn.execute(
                "SELECT document_id FROM wiki_topic_members WHERE topic_id = 86 "
                "ORDER BY document_id"
            ).fetchall()
            original_doc_ids = [r[0] for r in original_members]
            assert original_doc_ids == [831, 833]

            # New topic should have OAuth docs
            new_topic = conn.execute(
                "SELECT id FROM wiki_topics WHERE topic_label = 'OAuth'"
            ).fetchone()
            new_members = conn.execute(
                "SELECT document_id FROM wiki_topic_members WHERE topic_id = ? "
                "ORDER BY document_id",
                (new_topic[0],),
            ).fetchall()
            new_doc_ids = [r[0] for r in new_members]
            assert new_doc_ids == [830, 832]

    def test_split_case_insensitive(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "split", "86", "--entity", "oauth"])
        assert result.exit_code == 0
        assert "Moved 2 doc(s)" in result.output

    def test_split_nonexistent_topic(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "split", "999", "--entity", "OAuth"])
        assert result.exit_code == 1
        assert "999 not found" in result.output

    def test_split_no_matching_docs(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "split", "86", "--entity", "GraphQL"])
        assert result.exit_code == 1
        assert "No documents" in result.output

    def test_split_all_docs_match(self) -> None:
        """When all docs match the entity, refuse to split (use rename instead)."""
        # Add OAuth to all docs' content by using a topic where every doc has it
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (840, 'OAuth Intro', 'OAuth basics', 0)"
            )
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (841, 'OAuth Advanced', 'Advanced OAuth', 0)"
            )
            _setup_wiki_topic(
                conn,
                topic_id=87,
                label="All OAuth",
                slug="all-oauth",
                members=[840, 841],
            )

        try:
            result = runner.invoke(app, ["maintain", "wiki", "split", "87", "--entity", "OAuth"])
            assert result.exit_code == 1
            assert "nothing would remain" in result.output
        finally:
            with db.get_connection() as conn:
                _cleanup_topics(conn, [87])
                _cleanup_docs(conn, [840, 841])


class TestWikiSplitMarksArticleStale:
    """Test that split marks the original topic's article as stale."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (850, 'OAuth Doc', 'OAuth content', 0)"
            )
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (851, 'Other Doc', 'Other content', 0)"
            )
            _setup_wiki_topic(
                conn,
                topic_id=88,
                label="Mixed Topic",
                slug="mixed-topic",
                members=[850, 851],
                with_article=True,
            )
        yield
        with db.get_connection() as conn:
            new_topics = conn.execute("SELECT id FROM wiki_topics WHERE id != 88").fetchall()
            all_topic_ids = [88] + [r[0] for r in new_topics]
            _cleanup_topics(conn, all_topic_ids)
            _cleanup_docs(conn, [850, 851])

    def test_split_marks_original_article_stale(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "split", "88", "--entity", "OAuth"])
        assert result.exit_code == 0

        with db.get_connection() as conn:
            article = conn.execute(
                "SELECT is_stale, stale_reason FROM wiki_articles WHERE topic_id = 88"
            ).fetchone()
            assert article[0] == 1
            assert article[1] == "topic split"


class TestWikiSplitSlugUniqueness:
    """Test that split handles slug conflicts by appending suffix."""

    @pytest.fixture(autouse=True)
    def _setup(self) -> Generator[None, None, None]:
        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (860, 'OAuth Doc', 'OAuth content here', 0)"
            )
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) "
                "VALUES (861, 'Other Doc', 'Other content here', 0)"
            )
            _setup_wiki_topic(
                conn,
                topic_id=89,
                label="Auth Stuff",
                slug="auth-stuff",
                members=[860, 861],
            )
            # Pre-create a topic with the slug that would be generated
            _setup_wiki_topic(conn, topic_id=90, label="OAuth", slug="oauth")
        yield
        with db.get_connection() as conn:
            new_topics = conn.execute(
                "SELECT id FROM wiki_topics WHERE id NOT IN (89, 90)"
            ).fetchall()
            all_topic_ids = [89, 90] + [r[0] for r in new_topics]
            _cleanup_topics(conn, all_topic_ids)
            _cleanup_docs(conn, [860, 861])

    def test_split_appends_suffix_on_slug_conflict(self) -> None:
        result = runner.invoke(app, ["maintain", "wiki", "split", "89", "--entity", "OAuth"])
        assert result.exit_code == 0

        with db.get_connection() as conn:
            new_topic = conn.execute(
                "SELECT topic_slug FROM wiki_topics WHERE topic_label = 'OAuth' AND id != 90"
            ).fetchone()
            assert new_topic is not None
            assert new_topic[0] == "oauth-1"
