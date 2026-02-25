"""Pilot-based tests for QAScreen TUI widget — focus cycling and answer scrolling."""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.containers import ScrollableContainer
from textual.widgets import DataTable, Input, Markdown

from emdx.ui.qa.qa_screen import QAScreen

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MOCK_BASE = "emdx.ui.qa.qa_screen"
_PRESENTER_BASE = "emdx.ui.qa.qa_presenter"


def _long_markdown(n: int = 80) -> str:
    """Generate markdown content long enough to require scrolling."""
    lines = [f"**Line {i}:** Some answer content here." for i in range(n)]
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Test app
# ---------------------------------------------------------------------------


class QATestApp(App[None]):
    """Minimal app that mounts a single QAScreen."""

    DEFAULT_CSS = """
    QATestApp { height: 100%; }
    """

    def compose(self) -> ComposeResult:
        yield QAScreen(id="qa-screen")


# ---------------------------------------------------------------------------
# Fixture: mock presenter so no DB/embedding calls happen
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_qa_deps() -> Generator[dict[str, MagicMock], None, None]:
    """Patch QAPresenter methods to avoid DB/embedding calls."""
    with (
        patch(f"{_PRESENTER_BASE}.QAPresenter.initialize_sync") as m_init,
        patch(
            f"{_PRESENTER_BASE}.QAPresenter.preload_embeddings",
            return_value=None,
        ) as m_preload,
    ):
        yield {
            "initialize_sync": m_init,
            "preload_embeddings": m_preload,
        }


# ===================================================================
# A. Focus Cycling (Tab / Shift+Tab)
# ===================================================================


class TestFocusCycling:
    """Tests for 3-way focus cycling: input -> table -> answer panel."""

    @pytest.mark.asyncio
    async def test_initial_focus_on_table(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """On mount, focus should be on the history table."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#qa-history-table", DataTable)
            assert table.has_focus

    @pytest.mark.asyncio
    async def test_tab_from_table_focuses_answer_panel(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """Tab from history table should focus the answer panel."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            # Table has focus initially
            table = app.query_one("#qa-history-table", DataTable)
            assert table.has_focus

            await pilot.press("tab")
            await pilot.pause()

            # Answer panel (stream scroll is visible by default) should have focus
            stream_scroll = app.query_one(
                "#qa-answer-stream-scroll", ScrollableContainer
            )
            assert stream_scroll.has_focus

    @pytest.mark.asyncio
    async def test_tab_from_answer_panel_focuses_input(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """Tab from answer panel should focus the input."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            # Tab twice: table -> answer -> input
            await pilot.press("tab")
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()

            inp = app.query_one("#qa-input", Input)
            assert inp.has_focus

    @pytest.mark.asyncio
    async def test_tab_full_cycle(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """Tab 3 times should cycle back to the table."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#qa-history-table", DataTable)
            assert table.has_focus

            # Tab 3x: table -> answer -> input -> table
            for _ in range(3):
                await pilot.press("tab")
                await pilot.pause()

            assert table.has_focus

    @pytest.mark.asyncio
    async def test_shift_tab_from_table_focuses_input(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """Shift+Tab from table should focus input (reverse cycle)."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#qa-history-table", DataTable)
            assert table.has_focus

            await pilot.press("shift+tab")
            await pilot.pause()

            inp = app.query_one("#qa-input", Input)
            assert inp.has_focus

    @pytest.mark.asyncio
    async def test_tab_focuses_md_scroll_when_visible(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """Tab should focus md-scroll when it's the visible answer panel."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()

            # Switch to md-scroll view (simulating answer completion)
            qa = app.query_one("#qa-screen", QAScreen)
            qa._show_md_scroll()
            await pilot.pause()

            # Tab from table -> should focus md-scroll
            await pilot.press("tab")
            await pilot.pause()

            md_scroll = app.query_one(
                "#qa-answer-md-scroll", ScrollableContainer
            )
            assert md_scroll.has_focus


# ===================================================================
# B. Answer Panel Scrolling
# ===================================================================


class TestAnswerScrolling:
    """Tests for answer panel scroll bindings."""

    @pytest.mark.asyncio
    async def test_space_scrolls_answer_down(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """Space should scroll the answer panel down."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()

            # Switch to md-scroll and add long content
            qa = app.query_one("#qa-screen", QAScreen)
            qa._show_md_scroll()
            md = app.query_one("#qa-answer-md", Markdown)
            await md.update(_long_markdown())
            await pilot.pause()
            await pilot.pause()

            scroll = app.query_one(
                "#qa-answer-md-scroll", ScrollableContainer
            )
            assert scroll.scroll_y == 0

            # Press space to scroll down
            await pilot.press("space")
            await pilot.pause()

            assert scroll.scroll_y > 0

    @pytest.mark.asyncio
    async def test_shift_space_scrolls_answer_up(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """Shift+Space should scroll the answer panel up."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()

            # Switch to md-scroll and add long content
            qa = app.query_one("#qa-screen", QAScreen)
            qa._show_md_scroll()
            md = app.query_one("#qa-answer-md", Markdown)
            await md.update(_long_markdown())
            await pilot.pause()
            await pilot.pause()

            scroll = app.query_one(
                "#qa-answer-md-scroll", ScrollableContainer
            )

            # Scroll down first
            await pilot.press("space")
            await pilot.pause()
            scrolled_pos = scroll.scroll_y
            assert scrolled_pos > 0

            # Now scroll up
            await pilot.press("shift+space")
            await pilot.pause()

            assert scroll.scroll_y < scrolled_pos

    @pytest.mark.asyncio
    async def test_scroll_to_top_on_new_answer(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """Rendering a new answer should reset scroll to top."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()

            # Show md-scroll and add content
            qa = app.query_one("#qa-screen", QAScreen)
            qa._show_md_scroll()
            md = app.query_one("#qa-answer-md", Markdown)
            await md.update(_long_markdown())
            await pilot.pause()
            await pilot.pause()

            scroll = app.query_one(
                "#qa-answer-md-scroll", ScrollableContainer
            )

            # Scroll down without animation to avoid timing issues
            scroll.scroll_end(animate=False)
            await pilot.pause()
            assert scroll.scroll_y > 0

            # Show a new answer (calls _show_md_scroll which resets)
            qa._show_md_scroll()
            await pilot.pause()

            assert scroll.scroll_y == 0

    @pytest.mark.asyncio
    async def test_click_answer_panel_gives_focus(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """Clicking on the answer panel should focus it."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()

            # Show md-scroll with content
            qa = app.query_one("#qa-screen", QAScreen)
            qa._show_md_scroll()
            md = app.query_one("#qa-answer-md", Markdown)
            await md.update(_long_markdown())
            await pilot.pause()
            await pilot.pause()

            # Verify table has initial focus
            table = app.query_one("#qa-history-table", DataTable)
            assert table.has_focus

            # Click on the md-scroll container
            md_scroll = app.query_one(
                "#qa-answer-md-scroll", ScrollableContainer
            )
            await pilot.click(md_scroll, offset=(5, 5))
            await pilot.pause()

            assert md_scroll.has_focus

    @pytest.mark.asyncio
    async def test_keyboard_scroll_after_focus(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """After focusing answer panel, keyboard scrolling should work."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()

            # Show md-scroll with long content
            qa = app.query_one("#qa-screen", QAScreen)
            qa._show_md_scroll()
            md = app.query_one("#qa-answer-md", Markdown)
            await md.update(_long_markdown())
            await pilot.pause()
            await pilot.pause()

            scroll = app.query_one(
                "#qa-answer-md-scroll", ScrollableContainer
            )

            # Tab to answer panel
            await pilot.press("tab")
            await pilot.pause()
            assert scroll.has_focus

            # Press pagedown (should work now that panel is focused)
            await pilot.press("pagedown")
            await pilot.pause()

            assert scroll.scroll_y > 0


# ===================================================================
# C. History Navigation with Answer Panel Focus
# ===================================================================


class TestHistoryWithFocus:
    """Tests for j/k history navigation when answer panel is focused."""

    @pytest.mark.asyncio
    async def test_jk_works_from_table(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """j/k should navigate history when table has focus."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#qa-history-table", DataTable)
            assert table.has_focus

            # j/k should work (no crash, moves cursor)
            await pilot.press("j")
            await pilot.pause()
            await pilot.press("k")
            await pilot.pause()
            # No assertion needed — just verify no crash


# ===================================================================
# D. Zoom Integration
# ===================================================================


class TestZoomWithScrolling:
    """Tests for zoom mode interaction with scrolling."""

    @pytest.mark.asyncio
    async def test_zoom_hides_history(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """Pressing z should hide history and expand answer panel."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()

            await pilot.press("z")
            await pilot.pause()

            history = app.query_one("#qa-history-panel")
            answer = app.query_one("#qa-answer-panel")
            assert "zoom-hidden" in history.classes
            assert "zoom-full" in answer.classes

    @pytest.mark.asyncio
    async def test_scroll_works_in_zoom_mode(
        self, mock_qa_deps: dict[str, MagicMock]
    ) -> None:
        """Space should scroll answer even in zoom mode."""
        app = QATestApp()
        async with app.run_test(size=(80, 40)) as pilot:
            await pilot.pause()

            # Show md-scroll with content
            qa = app.query_one("#qa-screen", QAScreen)
            qa._show_md_scroll()
            md = app.query_one("#qa-answer-md", Markdown)
            await md.update(_long_markdown())
            await pilot.pause()
            await pilot.pause()

            # Enter zoom mode — should auto-focus answer panel
            await pilot.press("z")
            await pilot.pause()

            scroll = app.query_one(
                "#qa-answer-md-scroll", ScrollableContainer
            )
            assert scroll.has_focus
            assert scroll.scroll_y == 0

            # Space should scroll
            await pilot.press("space")
            await pilot.pause()

            assert scroll.scroll_y > 0
