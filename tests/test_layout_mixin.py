"""Tests for the LayoutMixin shared by all TUI views."""

from unittest.mock import MagicMock

from emdx.config.ui_config import DEFAULT_LAYOUT
from emdx.ui.layout_mixin import (
    ADJUST_STEP,
    MAX_LIST_HEIGHT_PCT,
    MIN_LIST_HEIGHT_PCT,
    LayoutMixin,
)


def _make_mixin():
    """Create a minimal LayoutMixin instance that fakes Widget.query_one."""
    mixin = LayoutMixin()
    mixin._layout_list_panel_id = "#list"
    mixin._layout_detail_panel_id = "#detail"
    mixin._layout_list_section_id = ""
    mixin._layout_sidebar_section_id = ""
    return mixin


def test_adjust_list_height_increases(tmp_path, monkeypatch):
    """action_grow_list increases the persisted list_height_pct."""
    config_path = tmp_path / "ui_config.json"
    monkeypatch.setattr(
        "emdx.config.ui_config.get_ui_config_path",
        lambda: config_path,
    )

    mixin = _make_mixin()
    # Stub _apply_layout so it doesn't call query_one
    mixin._apply_layout = MagicMock()  # type: ignore[method-assign]

    mixin._adjust_list_height(ADJUST_STEP)

    assert mixin._layout is not None
    assert mixin._layout["list_height_pct"] == DEFAULT_LAYOUT["list_height_pct"] + ADJUST_STEP


def test_adjust_list_height_decreases(tmp_path, monkeypatch):
    """action_shrink_list decreases the persisted list_height_pct."""
    config_path = tmp_path / "ui_config.json"
    monkeypatch.setattr(
        "emdx.config.ui_config.get_ui_config_path",
        lambda: config_path,
    )

    mixin = _make_mixin()
    mixin._apply_layout = MagicMock()  # type: ignore[method-assign]

    mixin._adjust_list_height(-ADJUST_STEP)

    assert mixin._layout is not None
    assert mixin._layout["list_height_pct"] == DEFAULT_LAYOUT["list_height_pct"] - ADJUST_STEP


def test_adjust_respects_min_bound(tmp_path, monkeypatch):
    """Cannot shrink below MIN_LIST_HEIGHT_PCT."""
    config_path = tmp_path / "ui_config.json"
    monkeypatch.setattr(
        "emdx.config.ui_config.get_ui_config_path",
        lambda: config_path,
    )

    mixin = _make_mixin()
    mixin._apply_layout = MagicMock()  # type: ignore[method-assign]

    # Try to shrink way below minimum
    mixin._adjust_list_height(-200)

    assert mixin._layout is not None
    assert mixin._layout["list_height_pct"] == MIN_LIST_HEIGHT_PCT


def test_adjust_respects_max_bound(tmp_path, monkeypatch):
    """Cannot grow above MAX_LIST_HEIGHT_PCT."""
    config_path = tmp_path / "ui_config.json"
    monkeypatch.setattr(
        "emdx.config.ui_config.get_ui_config_path",
        lambda: config_path,
    )

    mixin = _make_mixin()
    mixin._apply_layout = MagicMock()  # type: ignore[method-assign]

    # Try to grow way above maximum
    mixin._adjust_list_height(200)

    assert mixin._layout is not None
    assert mixin._layout["list_height_pct"] == MAX_LIST_HEIGHT_PCT


def test_no_change_when_already_at_bound(tmp_path, monkeypatch):
    """_adjust_list_height is a no-op when already at the limit."""
    config_path = tmp_path / "ui_config.json"
    monkeypatch.setattr(
        "emdx.config.ui_config.get_ui_config_path",
        lambda: config_path,
    )

    mixin = _make_mixin()
    mixin._apply_layout = MagicMock()  # type: ignore[method-assign]

    # First push to min
    mixin._adjust_list_height(-200)
    mixin._apply_layout.reset_mock()

    # Try to shrink further — should be a no-op
    mixin._adjust_list_height(-ADJUST_STEP)
    mixin._apply_layout.assert_not_called()
