"""Tests for the KnowledgeGraphPanel widget."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import RichLog

from emdx.ui.knowledge_graph_panel import _NOT_LOADED, KnowledgeGraphPanel

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _richlog_text(widget: RichLog) -> str:
    """Extract plain text from a RichLog widget."""
    return "\n".join(line.text for line in widget.lines)


def _get_panel_log(app: App[None]) -> RichLog:
    """Get the RichLog inside the KnowledgeGraphPanel."""
    panel = app.query_one(KnowledgeGraphPanel)
    logs = panel.query(RichLog)
    assert len(logs) == 1, f"Expected 1 RichLog, found {len(logs)}"
    return logs.first()


# ---------------------------------------------------------------------------
# Test App
# ---------------------------------------------------------------------------


class GraphTestApp(App[None]):
    """Minimal app for testing KnowledgeGraphPanel."""

    def compose(self) -> ComposeResult:
        yield KnowledgeGraphPanel(id="test-kg-panel")


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

_MOCK_LINKS = [
    {
        "id": 1,
        "source_doc_id": 10,
        "source_title": "Source Doc",
        "target_doc_id": 20,
        "target_title": "Related Architecture Notes",
        "similarity_score": 0.85,
        "created_at": "2025-01-01",
        "method": "semantic",
    },
    {
        "id": 2,
        "source_doc_id": 30,
        "source_title": "Reverse Linked Doc",
        "target_doc_id": 10,
        "target_title": "Source Doc",
        "similarity_score": 0.72,
        "created_at": "2025-01-02",
        "method": "entity",
    },
]

_PATCH_LINKS = "emdx.database.document_links.get_links_for_document"


def _mock_entity_rows() -> list[tuple[str, str, float]]:
    return [
        ("Python", "language", 0.95),
        ("SQLite", "database", 0.90),
        ("FastAPI", "framework", 0.85),
        ("Textual", "framework", 0.80),
        ("emdx", "project", 0.99),
    ]


def _mock_wiki_topic_rows() -> list[tuple[int, str, float]]:
    return [
        (1, "Database Architecture", 0.92),
        (2, "CLI Design Patterns", 0.78),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestKnowledgeGraphPanelPlaceholder:
    """Test initial placeholder state."""

    @pytest.mark.asyncio
    async def test_initial_placeholder(self) -> None:
        """Panel shows placeholder text when no document is selected."""
        async with GraphTestApp().run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panel = pilot.app.query_one(KnowledgeGraphPanel)
            panel.load_for_document(None)
            await pilot.pause()
            log = _get_panel_log(pilot.app)
            text = _richlog_text(log)
            assert "Select a document" in text


class TestLinkedDocuments:
    """Test linked documents section rendering."""

    @pytest.mark.asyncio
    async def test_linked_docs_display(self) -> None:
        """Linked documents are shown with IDs and titles."""
        with patch(_PATCH_LINKS, return_value=_MOCK_LINKS):
            async with GraphTestApp().run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = pilot.app.query_one(KnowledgeGraphPanel)
                panel.load_for_document(10)
                await pilot.pause()
                log = _get_panel_log(pilot.app)
                text = _richlog_text(log)
                assert "Linked Documents" in text
                assert "#20" in text
                assert "Related Architecture Notes" in text

    @pytest.mark.asyncio
    async def test_linked_docs_empty(self) -> None:
        """Empty state message when no linked documents."""
        with patch(_PATCH_LINKS, return_value=[]):
            async with GraphTestApp().run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = pilot.app.query_one(KnowledgeGraphPanel)
                panel.load_for_document(10)
                await pilot.pause()
                log = _get_panel_log(pilot.app)
                text = _richlog_text(log)
                assert "No linked documents" in text

    @pytest.mark.asyncio
    async def test_bidirectional_links(self) -> None:
        """Both forward and reverse links are displayed."""
        with patch(_PATCH_LINKS, return_value=_MOCK_LINKS):
            async with GraphTestApp().run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = pilot.app.query_one(KnowledgeGraphPanel)
                panel.load_for_document(10)
                await pilot.pause()
                log = _get_panel_log(pilot.app)
                text = _richlog_text(log)
                # Forward link: doc 10 -> doc 20
                assert "#20" in text
                # Reverse link: doc 30 -> doc 10, shows #30
                assert "#30" in text


class TestEntities:
    """Test entities section rendering."""

    @pytest.mark.asyncio
    async def test_entities_display(self) -> None:
        """Entities are shown grouped by type."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = _mock_entity_rows()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value = mock_cursor

        with (
            patch(_PATCH_LINKS, return_value=[]),
            patch(
                "emdx.database.connection.db_connection.get_connection",
                return_value=mock_conn,
            ),
        ):
            async with GraphTestApp().run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = pilot.app.query_one(KnowledgeGraphPanel)
                panel.load_for_document(42)
                await pilot.pause()
                log = _get_panel_log(pilot.app)
                text = _richlog_text(log)
                assert "Entities" in text
                assert "Python" in text


class TestWikiTopics:
    """Test wiki topics section rendering."""

    @pytest.mark.asyncio
    async def test_wiki_topics_display(self) -> None:
        """Wiki topics are shown with labels and relevance."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = _mock_wiki_topic_rows()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value = mock_cursor

        with (
            patch(_PATCH_LINKS, return_value=[]),
            patch(
                "emdx.database.connection.db_connection.get_connection",
                return_value=mock_conn,
            ),
        ):
            async with GraphTestApp().run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = pilot.app.query_one(KnowledgeGraphPanel)
                panel.load_for_document(42)
                await pilot.pause()
                log = _get_panel_log(pilot.app)
                text = _richlog_text(log)
                assert "Wiki Topics" in text


class TestCaching:
    """Test doc ID caching behavior."""

    @pytest.mark.asyncio
    async def test_doc_id_caching(self) -> None:
        """Calling load_for_document with same ID skips reload."""
        call_count = 0
        original_links: list[dict[str, Any]] = []

        def counting_get_links(doc_id: int) -> list[dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            return original_links

        with patch(_PATCH_LINKS, side_effect=counting_get_links):
            async with GraphTestApp().run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = pilot.app.query_one(KnowledgeGraphPanel)
                panel.load_for_document(10)
                assert call_count == 1
                # Same doc_id — cached, no reload
                panel.load_for_document(10)
                assert call_count == 1
                # Different doc_id — reload
                panel.load_for_document(20)
                assert call_count == 2

    @pytest.mark.asyncio
    async def test_clear_resets_cache(self) -> None:
        """clear_panel resets the cached doc_id."""
        with patch(_PATCH_LINKS, return_value=[]):
            async with GraphTestApp().run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panel = pilot.app.query_one(KnowledgeGraphPanel)
                panel.load_for_document(10)
                assert panel._current_doc_id == 10
                panel.clear_panel()
                assert panel._current_doc_id == _NOT_LOADED
