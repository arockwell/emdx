"""Tests for configurable TUI panel sizes (#891)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from emdx.config.app_config import set_config_value
from emdx.ui.layout_config import (
    DEFAULT_LIST_HEIGHT,
    DEFAULT_SIDEBAR_WIDTH,
    apply_panel_sizes,
    get_list_height,
    get_sidebar_width,
)


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("EMDX_CONFIG_FILE", str(tmp_path / "config.json"))
    yield


class TestPanelSizeSettings:
    def test_defaults(self) -> None:
        assert get_list_height() == DEFAULT_LIST_HEIGHT == 40
        assert get_sidebar_width() == DEFAULT_SIDEBAR_WIDTH == 30

    def test_configured_values(self) -> None:
        set_config_value("ui.list_height", 55)
        set_config_value("ui.sidebar_width", 20)
        assert get_list_height() == 55
        assert get_sidebar_width() == 20

    def test_clamped_to_bounds(self) -> None:
        set_config_value("ui.list_height", 5)
        set_config_value("ui.sidebar_width", 95)
        assert get_list_height() == 10
        assert get_sidebar_width() == 90

    def test_invalid_value_falls_back_to_default(self) -> None:
        set_config_value("ui.list_height", "huge")
        assert get_list_height() == DEFAULT_LIST_HEIGHT


class TestApplyPanelSizes:
    TEMPLATE = (
        "a { height: __LIST_HEIGHT__; } b { height: __PREVIEW_HEIGHT__; } "
        "c { width: __LIST_WIDTH__; } d { width: __SIDEBAR_WIDTH__; }"
    )

    def test_default_substitution(self) -> None:
        css = apply_panel_sizes(self.TEMPLATE)
        assert "height: 40%" in css
        assert "height: 60%" in css
        assert "width: 70%" in css
        assert "width: 30%" in css
        assert "__" not in css

    def test_configured_substitution_is_complementary(self) -> None:
        set_config_value("ui.list_height", 25)
        set_config_value("ui.sidebar_width", 45)
        css = apply_panel_sizes(self.TEMPLATE)
        assert "height: 25%" in css
        assert "height: 75%" in css
        assert "width: 55%" in css
        assert "width: 45%" in css


class TestViewCssIsSubstituted:
    """The real views must carry resolved values, not raw tokens."""

    def test_activity_view_css(self) -> None:
        from emdx.ui.activity.activity_view import ActivityView

        assert "__LIST_HEIGHT__" not in ActivityView.DEFAULT_CSS
        assert "__" not in ActivityView.DEFAULT_CSS.replace("──", "")
        assert "#activity-panel" in ActivityView.DEFAULT_CSS

    def test_task_view_css(self) -> None:
        from emdx.ui.task_view import TaskView

        assert "__LIST_HEIGHT__" not in TaskView.DEFAULT_CSS
        assert "__" not in TaskView.DEFAULT_CSS.replace("──", "")
        assert "#task-list-panel" in TaskView.DEFAULT_CSS
