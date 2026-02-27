"""Tests for TUI layout configuration (ui_config.py layout support)."""

import json

from emdx.config.ui_config import (
    DEFAULT_LAYOUT,
    LayoutConfig,
    get_layout,
    load_ui_config,
    save_ui_config,
    set_layout,
)


def test_default_layout_values():
    """Default layout has sensible percentages."""
    assert DEFAULT_LAYOUT["list_height_pct"] == 40
    assert DEFAULT_LAYOUT["sidebar_width_pct"] == 30
    assert DEFAULT_LAYOUT["sidebar_threshold"] == 120


def test_get_layout_returns_defaults(tmp_path, monkeypatch):
    """get_layout returns defaults when no config file exists."""
    monkeypatch.setattr(
        "emdx.config.ui_config.get_ui_config_path",
        lambda: tmp_path / "ui_config.json",
    )
    layout = get_layout()
    assert layout["list_height_pct"] == 40
    assert layout["sidebar_width_pct"] == 30
    assert layout["sidebar_threshold"] == 120


def test_set_layout_persists(tmp_path, monkeypatch):
    """set_layout writes to config and get_layout reads it back."""
    config_path = tmp_path / "ui_config.json"
    monkeypatch.setattr(
        "emdx.config.ui_config.get_ui_config_path",
        lambda: config_path,
    )
    custom: LayoutConfig = {
        "list_height_pct": 60,
        "sidebar_width_pct": 25,
        "sidebar_threshold": 100,
    }
    set_layout(custom)

    # Read back
    layout = get_layout()
    assert layout["list_height_pct"] == 60
    assert layout["sidebar_width_pct"] == 25
    assert layout["sidebar_threshold"] == 100


def test_get_layout_merges_partial_config(tmp_path, monkeypatch):
    """Missing keys in persisted config are filled from defaults."""
    config_path = tmp_path / "ui_config.json"
    config_path.write_text(json.dumps({"layout": {"list_height_pct": 55}}) + "\n")
    monkeypatch.setattr(
        "emdx.config.ui_config.get_ui_config_path",
        lambda: config_path,
    )
    layout = get_layout()
    assert layout["list_height_pct"] == 55
    # Defaults for missing keys
    assert layout["sidebar_width_pct"] == 30
    assert layout["sidebar_threshold"] == 120


def test_get_layout_handles_corrupt_layout(tmp_path, monkeypatch):
    """Non-dict layout value in config falls back to defaults."""
    config_path = tmp_path / "ui_config.json"
    config_path.write_text(json.dumps({"layout": "bad"}) + "\n")
    monkeypatch.setattr(
        "emdx.config.ui_config.get_ui_config_path",
        lambda: config_path,
    )
    layout = get_layout()
    assert layout == DEFAULT_LAYOUT


def test_set_layout_preserves_other_config(tmp_path, monkeypatch):
    """set_layout does not clobber other config keys like theme."""
    config_path = tmp_path / "ui_config.json"
    monkeypatch.setattr(
        "emdx.config.ui_config.get_ui_config_path",
        lambda: config_path,
    )
    # Save theme first
    save_ui_config({"theme": "my-theme", "code_theme": "monokai"})

    set_layout(DEFAULT_LAYOUT)

    config = load_ui_config()
    assert config["theme"] == "my-theme"
    assert config["code_theme"] == "monokai"
    assert config["layout"]["list_height_pct"] == 40


def test_default_config_includes_layout(tmp_path, monkeypatch):
    """load_ui_config includes layout in defaults."""
    monkeypatch.setattr(
        "emdx.config.ui_config.get_ui_config_path",
        lambda: tmp_path / "ui_config.json",
    )
    config = load_ui_config()
    assert "layout" in config
    assert config["layout"]["list_height_pct"] == 40
