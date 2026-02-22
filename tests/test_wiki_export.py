"""Tests for wiki export to MkDocs (FEAT-41, FEAT-42, FEAT-44)."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml  # type: ignore[import-untyped]
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app
from emdx.services.wiki_export_service import (
    ExportedArticle,
    _generate_mkdocs_yml,
    _render_article_md,
    _render_index_md,
    _slugify,
    export_mkdocs,
)

runner = CliRunner()


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def clean_wiki_db(isolate_test_database: Any) -> Any:
    """Ensure clean wiki tables for each test."""

    def cleanup() -> None:
        with db.get_connection() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM wiki_article_sources")
            conn.execute("DELETE FROM wiki_articles")
            conn.execute("DELETE FROM wiki_topic_members")
            conn.execute("DELETE FROM wiki_topics")
            conn.execute("DELETE FROM document_entities")
            conn.execute("DELETE FROM documents")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    cleanup()
    db.ensure_schema()
    yield
    cleanup()


def _insert_topic(
    conn: sqlite3.Connection,
    topic_id: int,
    slug: str,
    label: str,
    status: str = "active",
) -> None:
    conn.execute(
        "INSERT INTO wiki_topics (id, topic_slug, topic_label, status) VALUES (?, ?, ?, ?)",
        (topic_id, slug, label, status),
    )
    conn.commit()


def _insert_doc(conn: sqlite3.Connection, doc_id: int, title: str, content: str) -> None:
    conn.execute(
        "INSERT INTO documents (id, title, content, is_deleted, doc_type) "
        "VALUES (?, ?, ?, 0, 'wiki')",
        (doc_id, title, content),
    )
    conn.commit()


def _insert_article(
    conn: sqlite3.Connection,
    topic_id: int,
    doc_id: int,
    version: int = 1,
    model: str = "test-model",
    rating: int | None = None,
) -> int:
    conn.execute(
        "INSERT INTO wiki_articles "
        "(topic_id, document_id, source_hash, model, version, rating, "
        "generated_at) "
        "VALUES (?, ?, 'hash', ?, ?, ?, CURRENT_TIMESTAMP)",
        (topic_id, doc_id, model, version, rating),
    )
    conn.commit()
    row = conn.execute("SELECT last_insert_rowid()").fetchone()
    assert row is not None
    article_id: int = row[0]
    return article_id


def _insert_member(conn: sqlite3.Connection, topic_id: int, doc_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO wiki_topic_members (topic_id, document_id) VALUES (?, ?)",
        (topic_id, doc_id),
    )
    conn.commit()


def _setup_full_article(
    conn: sqlite3.Connection,
    topic_id: int,
    slug: str,
    label: str,
    content: str,
    source_doc_ids: list[int] | None = None,
    rating: int | None = None,
) -> None:
    """Set up a complete topic + document + article + members."""
    _insert_topic(conn, topic_id, slug, label)
    doc_id = 5000 + topic_id
    _insert_doc(conn, doc_id, label, content)
    article_id = _insert_article(conn, topic_id, doc_id, rating=rating)

    # Add source docs as members
    if source_doc_ids:
        for src_id in source_doc_ids:
            _insert_member(conn, topic_id, src_id)
            conn.execute(
                "INSERT OR IGNORE INTO wiki_article_sources "
                "(article_id, document_id, content_hash) VALUES (?, ?, 'h')",
                (article_id, src_id),
            )
        conn.commit()


# ── Unit tests: _slugify ─────────────────────────────────────────────


class TestSlugify:
    def test_basic(self) -> None:
        assert _slugify("Hello World") == "hello-world"

    def test_special_chars(self) -> None:
        assert _slugify("Auth / OAuth / JWT") == "auth-oauth-jwt"

    def test_max_length(self) -> None:
        long = "a" * 100
        assert len(_slugify(long)) <= 80


# ── Unit tests: rendering ───────────────────────────────────────────


class TestRenderArticleMd:
    def test_includes_front_matter(self) -> None:
        article = ExportedArticle(
            topic_id=1,
            topic_slug="auth",
            topic_label="Authentication",
            content="# Authentication\n\nArticle content.",
            version=2,
            generated_at="2026-01-01",
            model="test-model",
            rating=4,
            member_count=5,
        )
        md = _render_article_md(article)
        assert md.startswith("---\n")
        assert "title: Authentication" in md
        assert "version: 2" in md
        assert "rating: 4" in md
        assert "# Authentication" in md

    def test_no_rating_omitted(self) -> None:
        article = ExportedArticle(
            topic_id=1,
            topic_slug="auth",
            topic_label="Auth",
            content="# Auth",
            version=1,
            generated_at="",
            model="m",
            rating=None,
            member_count=3,
        )
        md = _render_article_md(article)
        assert "rating" not in md

    def test_source_footer(self) -> None:
        article = ExportedArticle(
            topic_id=1,
            topic_slug="auth",
            topic_label="Auth",
            content="# Auth",
            version=1,
            generated_at="",
            model="m",
            rating=None,
            member_count=3,
            source_titles=["Doc A", "Doc B", "Doc C"],
        )
        md = _render_article_md(article)
        assert "Generated from 3 source documents" in md


class TestRenderIndexMd:
    def test_index_content(self) -> None:
        articles = [
            ExportedArticle(
                topic_id=1,
                topic_slug="auth",
                topic_label="Authentication",
                content="",
                version=1,
                generated_at="",
                model="m",
                rating=None,
                member_count=5,
            ),
        ]
        md = _render_index_md(articles, entity_count=3)
        assert "1 articles" in md
        assert "3 entity pages" in md
        assert "[Authentication](articles/auth.md)" in md
        assert "5 sources" in md

    def test_empty(self) -> None:
        md = _render_index_md([], entity_count=0)
        assert "0 articles" in md


# ── Unit tests: mkdocs.yml generation ───────────────────────────────


class TestGenerateMkdocsYml:
    def test_basic_structure(self) -> None:
        articles = [
            ExportedArticle(
                topic_id=1,
                topic_slug="auth",
                topic_label="Authentication",
                content="",
                version=1,
                generated_at="",
                model="m",
                rating=None,
                member_count=3,
            ),
        ]
        yml_str = _generate_mkdocs_yml(articles, [], site_name="Test Wiki")
        config = yaml.safe_load(yml_str)

        assert config["site_name"] == "Test Wiki"
        assert config["theme"]["name"] == "material"
        assert "search" in config["plugins"]

    def test_nav_structure(self) -> None:
        from emdx.services.wiki_entity_service import EntityPage

        articles = [
            ExportedArticle(
                topic_id=1,
                topic_slug="auth",
                topic_label="Authentication",
                content="",
                version=1,
                generated_at="",
                model="m",
                rating=None,
                member_count=3,
            ),
        ]
        entities = [
            EntityPage(
                entity="OAuth",
                entity_type="tech_term",
                doc_frequency=5,
                page_score=40.0,
                tier="A",
            ),
        ]
        yml_str = _generate_mkdocs_yml(articles, entities)
        config = yaml.safe_load(yml_str)

        nav = config["nav"]
        assert nav[0] == {"Home": "index.md"}
        assert "Articles" in nav[1]
        assert "Glossary" in nav[2]

    def test_empty_nav(self) -> None:
        yml_str = _generate_mkdocs_yml([], [])
        config = yaml.safe_load(yml_str)
        assert len(config["nav"]) == 1  # Just Home


# ── Integration tests: export_mkdocs ────────────────────────────────


class TestExportMkdocs:
    def test_export_creates_structure(self, clean_wiki_db: Any, tmp_path: Path) -> None:
        """Export creates the expected directory structure."""
        with db.get_connection() as conn:
            # Source docs
            _insert_doc(conn, 1, "Source A", "content A")
            _insert_doc(conn, 2, "Source B", "content B")
            _setup_full_article(
                conn,
                1,
                "auth",
                "Authentication",
                "# Authentication\n\nAll about auth.",
                source_doc_ids=[1, 2],
                rating=4,
            )

        out = tmp_path / "wiki-site"
        result = export_mkdocs(out)

        assert result.articles_exported == 1
        assert result.mkdocs_yml_generated
        assert (out / "mkdocs.yml").exists()
        assert (out / "docs" / "index.md").exists()
        assert (out / "docs" / "articles" / "auth.md").exists()

    def test_export_article_content(self, clean_wiki_db: Any, tmp_path: Path) -> None:
        """Exported article has front matter and content."""
        with db.get_connection() as conn:
            _setup_full_article(
                conn,
                1,
                "auth",
                "Auth",
                "# Authentication\n\nDetailed content.",
            )

        out = tmp_path / "wiki-site"
        export_mkdocs(out)

        article_md = (out / "docs" / "articles" / "auth.md").read_text()
        assert "---" in article_md
        assert "title: Auth" in article_md
        assert "# Authentication" in article_md

    def test_export_mkdocs_yml_valid(self, clean_wiki_db: Any, tmp_path: Path) -> None:
        """Generated mkdocs.yml is valid YAML with expected keys."""
        with db.get_connection() as conn:
            _setup_full_article(
                conn,
                1,
                "auth",
                "Auth",
                "# Auth\n\nContent.",
            )

        out = tmp_path / "wiki-site"
        export_mkdocs(out)

        config = yaml.safe_load((out / "mkdocs.yml").read_text())
        assert config["site_name"] == "Knowledge Base Wiki"
        assert config["theme"]["name"] == "material"
        assert any("Articles" in item for item in config["nav"] if isinstance(item, dict))

    def test_export_skips_skipped_topics(self, clean_wiki_db: Any, tmp_path: Path) -> None:
        """Skipped topics are excluded from export."""
        with db.get_connection() as conn:
            _insert_topic(conn, 1, "auth", "Auth", status="skipped")
            _insert_doc(conn, 5001, "Auth", "# Auth\n\nContent.")
            _insert_article(conn, 1, 5001)

        out = tmp_path / "wiki-site"
        result = export_mkdocs(out)
        assert result.articles_exported == 0

    def test_export_empty_db(self, clean_wiki_db: Any, tmp_path: Path) -> None:
        """Empty database produces valid structure with 0 articles."""
        out = tmp_path / "wiki-site"
        result = export_mkdocs(out)

        assert result.articles_exported == 0
        assert result.mkdocs_yml_generated
        assert (out / "mkdocs.yml").exists()
        assert (out / "docs" / "index.md").exists()

    def test_export_multiple_articles(self, clean_wiki_db: Any, tmp_path: Path) -> None:
        """Multiple articles are exported correctly."""
        with db.get_connection() as conn:
            _setup_full_article(conn, 1, "auth", "Auth", "# Auth")
            _setup_full_article(conn, 2, "database", "Database", "# Database")
            _setup_full_article(conn, 3, "testing", "Testing", "# Testing")

        out = tmp_path / "wiki-site"
        result = export_mkdocs(out)

        assert result.articles_exported == 3
        assert (out / "docs" / "articles" / "auth.md").exists()
        assert (out / "docs" / "articles" / "database.md").exists()
        assert (out / "docs" / "articles" / "testing.md").exists()

    def test_export_custom_site_name(self, clean_wiki_db: Any, tmp_path: Path) -> None:
        """Custom site name appears in mkdocs.yml."""
        out = tmp_path / "wiki-site"
        export_mkdocs(out, site_name="My Custom Wiki")

        config = yaml.safe_load((out / "mkdocs.yml").read_text())
        assert config["site_name"] == "My Custom Wiki"

    def test_index_lists_all_articles(self, clean_wiki_db: Any, tmp_path: Path) -> None:
        """Index page links to all articles."""
        with db.get_connection() as conn:
            _setup_full_article(conn, 1, "auth", "Auth", "# Auth")
            _setup_full_article(conn, 2, "db", "Database", "# Database")

        out = tmp_path / "wiki-site"
        export_mkdocs(out)

        index_md = (out / "docs" / "index.md").read_text()
        assert "[Auth](articles/auth.md)" in index_md
        assert "[Database](articles/db.md)" in index_md


# ── CLI tests ────────────────────────────────────────────────────────


class TestWikiExportCli:
    def test_export_command_basic(self, clean_wiki_db: Any, tmp_path: Path) -> None:
        """CLI export command runs successfully."""
        with db.get_connection() as conn:
            _setup_full_article(conn, 1, "auth", "Auth", "# Auth")

        out = str(tmp_path / "wiki-site")
        result = runner.invoke(app, ["maintain", "wiki", "export", out])
        assert result.exit_code == 0
        assert "Articles:     1" in result.output
        assert "mkdocs.yml:   yes" in result.output

    def test_export_command_custom_name(self, clean_wiki_db: Any, tmp_path: Path) -> None:
        """CLI export with custom site name."""
        out = str(tmp_path / "wiki-site")
        result = runner.invoke(app, ["maintain", "wiki", "export", out, "-n", "Test Wiki"])
        assert result.exit_code == 0
        config = yaml.safe_load((tmp_path / "wiki-site" / "mkdocs.yml").read_text())
        assert config["site_name"] == "Test Wiki"

    def test_export_help(self) -> None:
        """Help text shows expected content."""
        result = runner.invoke(app, ["maintain", "wiki", "export", "--help"])
        assert result.exit_code == 0
        assert "mkdocs" in result.output.lower()
        assert "--build" in result.output
        assert "--deploy" in result.output

    def test_export_build_no_mkdocs(self, clean_wiki_db: Any, tmp_path: Path) -> None:
        """--build fails gracefully when mkdocs is not installed."""
        out = str(tmp_path / "wiki-site")
        with patch("shutil.which", return_value=None):
            result = runner.invoke(app, ["maintain", "wiki", "export", out, "--build"])
        assert result.exit_code == 1
        assert "mkdocs not found" in result.output
