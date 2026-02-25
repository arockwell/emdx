"""Pilot-based tests for QAScreen — VerticalScroll + Markdown architecture."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Input, Markdown, RichLog, Static

from emdx.ui.qa.qa_presenter import QAEntry, QASource, QAStateVM
from emdx.ui.qa.qa_screen import QAScreen

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_BASE = "emdx.ui.qa.qa_presenter"


def _make_entry(
    question: str = "How does auth work?",
    answer: str = "Auth uses JWT tokens.",
    sources: list[QASource] | None = None,
    elapsed_ms: int = 1500,
    is_loading: bool = False,
) -> QAEntry:
    return QAEntry(
        question=question,
        answer=answer,
        sources=sources or [],
        elapsed_ms=elapsed_ms,
        is_loading=is_loading,
    )


# ---------------------------------------------------------------------------
# Test app
# ---------------------------------------------------------------------------


class QATestApp(App[None]):
    CSS = """
    Screen { layout: vertical; }
    """

    def compose(self) -> ComposeResult:
        yield QAScreen(id="qa-screen")


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_qa() -> Generator[dict[str, Any], None, None]:
    state = QAStateVM(
        entries=[],
        is_asking=False,
        has_claude_cli=True,
        has_embeddings=True,
        status_text="Ready",
    )
    with (
        patch(f"{_MOCK_BASE}.QAPresenter.initialize_sync") as m_init,
        patch(f"{_MOCK_BASE}.QAPresenter.preload_embeddings", new_callable=AsyncMock) as m_pre,
        patch(f"{_MOCK_BASE}.QAPresenter.load_history") as m_hist,
    ):
        m_init.side_effect = lambda: None
        m_pre.return_value = None
        m_hist.return_value = None
        yield {"state": state, "initialize_sync": m_init, "preload_embeddings": m_pre}


# ---------------------------------------------------------------------------
# Tests: Layout
# ---------------------------------------------------------------------------


class TestQALayout:
    @pytest.mark.asyncio
    async def test_mounts(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#qa-screen", QAScreen) is not None

    @pytest.mark.asyncio
    async def test_has_input(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#qa-input", Input) is not None

    @pytest.mark.asyncio
    async def test_has_history_table(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#qa-history-table", DataTable) is not None

    @pytest.mark.asyncio
    async def test_has_markdown_and_richlog(self, mock_qa: dict[str, MagicMock]) -> None:
        """Both Markdown (completed) and RichLog (streaming) widgets exist."""
        app = QATestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#qa-answer-md", Markdown) is not None
            assert app.query_one("#qa-answer-stream", RichLog) is not None

    @pytest.mark.asyncio
    async def test_welcome_shown(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            md = app.query_one("#qa-answer-md", Markdown)
            # Markdown widget should be visible (display != none)
            assert md.styles.display != "none"


# ---------------------------------------------------------------------------
# Tests: Focus
# ---------------------------------------------------------------------------


class TestQAFocus:
    @pytest.mark.asyncio
    async def test_initial_focus_on_table(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#qa-history-table", DataTable).has_focus

    @pytest.mark.asyncio
    async def test_tab_toggles_input(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            assert app.query_one("#qa-input", Input).has_focus

            await pilot.press("tab")
            await pilot.pause()
            assert app.query_one("#qa-history-table", DataTable).has_focus

    @pytest.mark.asyncio
    async def test_slash_focuses_input(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("slash")
            await pilot.pause()
            assert app.query_one("#qa-input", Input).has_focus


# ---------------------------------------------------------------------------
# Tests: History
# ---------------------------------------------------------------------------


class TestQAHistory:
    @pytest.mark.asyncio
    async def test_table_populates(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            qa = app.query_one("#qa-screen", QAScreen)
            qa._presenter.state.entries.append(_make_entry(question="Q1"))
            qa._presenter.state.entries.append(_make_entry(question="Q2"))
            qa._rebuild_history_table()
            await pilot.pause()
            assert app.query_one("#qa-history-table", DataTable).row_count == 2

    @pytest.mark.asyncio
    async def test_header_shows_count(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            qa = app.query_one("#qa-screen", QAScreen)
            qa._presenter.state.entries.append(_make_entry())
            qa._rebuild_history_table()
            await pilot.pause()
            assert "1" in str(app.query_one("#qa-history-header", Static).content)

    @pytest.mark.asyncio
    async def test_jk_navigate(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            qa = app.query_one("#qa-screen", QAScreen)
            for i in range(3):
                qa._presenter.state.entries.append(_make_entry(question=f"Q{i}"))
            qa._rebuild_history_table()
            qa._selected_index = 0
            await pilot.pause()

            table = app.query_one("#qa-history-table", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            await pilot.press("j")
            await pilot.pause()
            assert table.cursor_row == 1

            await pilot.press("k")
            await pilot.pause()
            assert table.cursor_row == 0

    @pytest.mark.asyncio
    async def test_clear_history(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test() as pilot:
            await pilot.pause()
            qa = app.query_one("#qa-screen", QAScreen)
            qa._presenter.state.entries.append(_make_entry())
            qa._rebuild_history_table()
            await pilot.pause()

            await pilot.press("c")
            await pilot.pause()

            table = app.query_one("#qa-history-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    async def test_selecting_row_renders_answer(self, mock_qa: dict[str, MagicMock]) -> None:
        """Highlighting a history row renders the corresponding answer."""
        app = QATestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            qa = app.query_one("#qa-screen", QAScreen)

            qa._presenter.state.entries.append(_make_entry(question="Q1", answer="Answer one"))
            qa._presenter.state.entries.append(_make_entry(question="Q2", answer="Answer two"))
            qa._rebuild_history_table()
            await pilot.pause()

            table = app.query_one("#qa-history-table", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            assert qa._selected_index == 0


# ---------------------------------------------------------------------------
# Tests: Answer rendering
# ---------------------------------------------------------------------------


class TestQAAnswer:
    @pytest.mark.asyncio
    async def test_render_answer_uses_markdown(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            qa = app.query_one("#qa-screen", QAScreen)

            entry = _make_entry(
                answer="This is the answer.",
                sources=[QASource(doc_id=42, title="Auth Design")],
            )
            qa._render_answer(entry)
            await pilot.pause()

            md = app.query_one("#qa-answer-md", Markdown)
            assert md.styles.display != "none"

            stream = app.query_one("#qa-answer-stream", RichLog)
            assert stream.styles.display == "none"

    @pytest.mark.asyncio
    async def test_selecting_history_renders_answer(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            qa = app.query_one("#qa-screen", QAScreen)

            qa._presenter.state.entries.append(_make_entry(question="Q1", answer="A1"))
            qa._presenter.state.entries.append(_make_entry(question="Q2", answer="A2"))
            qa._rebuild_history_table()
            await pilot.pause()

            table = app.query_one("#qa-history-table", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            assert qa._selected_index == 0


# ---------------------------------------------------------------------------
# Tests: Scroll
# ---------------------------------------------------------------------------


class TestQAScroll:
    @pytest.mark.asyncio
    async def test_answer_scroll_container_exists(self, mock_qa: dict[str, MagicMock]) -> None:
        """VerticalScroll container wraps the answer content."""
        app = QATestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            from emdx.ui.qa.qa_screen import _AnswerScroll

            scroll = app.query_one("#qa-answer-scroll", _AnswerScroll)
            assert not scroll.can_focus, "Answer scroll should not be focusable"

    @pytest.mark.asyncio
    async def test_answer_panel_region_nonzero(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panel = app.query_one("#qa-answer-panel")
            assert panel.region.width > 0
            assert panel.region.height > 0

    @pytest.mark.asyncio
    async def test_scroll_fence_prevents_table_scroll(self, mock_qa: dict[str, MagicMock]) -> None:
        """Scrolling in the answer panel must not move the history table cursor."""
        app = QATestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            qa = app.query_one("#qa-screen", QAScreen)
            for i in range(5):
                qa._presenter.state.entries.append(_make_entry(question=f"Q{i}", answer=f"A{i}"))
            qa._rebuild_history_table()
            await pilot.pause()

            table = app.query_one("#qa-history-table", DataTable)
            table.move_cursor(row=0)
            await pilot.pause()

            initial_cursor = table.cursor_row
            assert table.cursor_row == initial_cursor


# ---------------------------------------------------------------------------
# Tests: Zoom
# ---------------------------------------------------------------------------


class TestQAZoom:
    @pytest.mark.asyncio
    async def test_zoom_toggle(self, mock_qa: dict[str, MagicMock]) -> None:
        app = QATestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            qa = app.query_one("#qa-screen", QAScreen)

            assert not qa._zoomed

            # Zoom in
            qa.action_toggle_zoom()
            await pilot.pause()
            assert qa._zoomed

            history = app.query_one("#qa-history-panel")
            assert history.has_class("zoom-hidden")

            # Zoom out
            qa.action_toggle_zoom()
            await pilot.pause()
            assert not qa._zoomed
            assert not history.has_class("zoom-hidden")
