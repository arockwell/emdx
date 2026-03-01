"""Tests for the entities command --json output mode."""

from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from emdx.database import db
from emdx.main import app

runner = CliRunner()


@pytest.fixture
def clean_entity_db(isolate_test_database: Any) -> Any:
    """Ensure clean database for entity tests."""

    def cleanup() -> None:
        with db.get_connection() as conn:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("DELETE FROM document_entities")
            conn.execute("DELETE FROM document_links")
            conn.execute("DELETE FROM documents")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()

    cleanup()
    yield
    cleanup()


def _create_doc(doc_id: int, title: str, content: str) -> None:
    """Create a test document."""
    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 0)",
            (doc_id, title, content),
        )
        conn.commit()


class TestEntitiesJsonSingleDoc:
    """Tests for --json with a single document."""

    def test_json_extract_and_link(self, clean_entity_db: Any) -> None:
        """Single doc entity extraction with --json outputs expected fields."""
        _create_doc(
            1,
            "Auth Module",
            "## Authentication\n\nThe `auth_handler` manages tokens.\n",
        )

        result = runner.invoke(app, ["maintain", "entities", "--json", "1"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["action"] == "extract_and_link"
        assert data["doc_id"] == 1
        assert "entities_extracted" in data
        assert "links_created" in data
        assert "linked_doc_ids" in data
        assert isinstance(data["linked_doc_ids"], list)

    def test_json_extract_only(self, clean_entity_db: Any) -> None:
        """Single doc entity extraction with --no-wikify --json."""
        _create_doc(
            1,
            "Test Doc",
            "## Important Concept\n\nUse `some_function` here.\n",
        )

        result = runner.invoke(app, ["maintain", "entities", "--no-wikify", "--json", "1"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["action"] == "extract_only"
        assert data["doc_id"] == 1
        assert "entities_extracted" in data
        assert data["entities_extracted"] >= 0


class TestEntitiesJsonAllDocs:
    """Tests for --json with --all."""

    def test_json_all_extract_and_link(self, clean_entity_db: Any) -> None:
        """--all --json outputs total entities and links."""
        _create_doc(
            1,
            "Auth Module",
            "## Authentication\n\nThe `auth_handler` manages tokens.\n",
        )
        _create_doc(
            2,
            "Session Handler",
            "## Session Management\n\nUses `auth_handler` for auth.\n",
        )

        result = runner.invoke(app, ["maintain", "entities", "--all", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["action"] == "extract_and_link"
        assert "entities_extracted" in data
        assert "links_created" in data
        assert "docs_processed" in data
        assert data["docs_processed"] >= 2

    def test_json_all_extract_only(self, clean_entity_db: Any) -> None:
        """--all --no-wikify --json outputs extraction counts."""
        _create_doc(
            1,
            "Test Doc",
            "## Some Heading\n\nContent with `code_term`.\n",
        )

        result = runner.invoke(app, ["maintain", "entities", "--all", "--no-wikify", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["action"] == "extract_only"
        assert "entities_extracted" in data
        assert "docs_processed" in data


class TestEntitiesJsonErrors:
    """Tests for --json error cases."""

    def test_json_no_doc_id_no_all(self, clean_entity_db: Any) -> None:
        """Missing doc ID and --all with --json outputs error JSON."""
        result = runner.invoke(app, ["maintain", "entities", "--json"])

        data = json.loads(result.output)
        assert "error" in data
