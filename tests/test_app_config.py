"""Tests for the app config store and `emdx config` commands (#1038)."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from emdx.commands.config_cmd import app as config_app
from emdx.commands.core import app as core_app
from emdx.config.app_config import (
    get_config_value,
    load_config,
    parse_config_value,
    set_config_value,
    unset_config_value,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """Point EMDX_CONFIG_FILE at a per-test temp file."""
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("EMDX_CONFIG_FILE", str(config_file))
    yield config_file


class TestConfigStore:
    def test_missing_file_loads_empty(self) -> None:
        assert load_config() == {}

    def test_set_then_get_roundtrip(self) -> None:
        set_config_value("maintain.auto_link_on_save", False)
        assert get_config_value("maintain.auto_link_on_save") is False

    def test_known_default_when_unset(self) -> None:
        assert get_config_value("maintain.auto_link_on_save") is True

    def test_explicit_default_wins_for_unknown_key(self) -> None:
        assert get_config_value("no.such.key", default="fallback") == "fallback"

    def test_unset_reverts_to_default(self) -> None:
        set_config_value("maintain.auto_link_on_save", False)
        assert unset_config_value("maintain.auto_link_on_save") is True
        assert get_config_value("maintain.auto_link_on_save") is True

    def test_unset_missing_key_returns_false(self) -> None:
        assert unset_config_value("never.set") is False

    def test_corrupt_file_loads_empty(self, isolated_config: Path) -> None:
        isolated_config.write_text("{not json")
        assert load_config() == {}
        # And setting still works afterwards (config never breaks a command)
        set_config_value("maintain.auto_link_on_save", False)
        assert get_config_value("maintain.auto_link_on_save") is False


class TestParseConfigValue:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("true", True),
            ("TRUE", True),
            ("false", False),
            ("null", None),
            ("42", 42),
            ("2.5", 2.5),
            ("hello", "hello"),
            ("/some/path", "/some/path"),
        ],
    )
    def test_parses(self, raw: str, expected: object) -> None:
        assert parse_config_value(raw) == expected


class TestConfigCli:
    def test_set_and_get(self) -> None:
        result = runner.invoke(config_app, ["set", "maintain.auto_link_on_save", "false"])
        assert result.exit_code == 0
        assert "maintain.auto_link_on_save = false" in result.output

        result = runner.invoke(config_app, ["get", "maintain.auto_link_on_save"])
        assert result.exit_code == 0
        assert result.output.strip() == "false"

    def test_get_default_when_unset(self) -> None:
        result = runner.invoke(config_app, ["get", "maintain.auto_link_on_save"])
        assert result.exit_code == 0
        assert result.output.strip() == "true"

    def test_get_unknown_key_errors(self) -> None:
        result = runner.invoke(config_app, ["get", "no.such.key"])
        assert result.exit_code == 1

    def test_unset(self) -> None:
        runner.invoke(config_app, ["set", "maintain.auto_link_on_save", "false"])
        result = runner.invoke(config_app, ["unset", "maintain.auto_link_on_save"])
        assert result.exit_code == 0
        assert "unset" in result.output

        result = runner.invoke(config_app, ["get", "maintain.auto_link_on_save"])
        assert result.output.strip() == "true"

    def test_list_shows_defaults_and_set_values(self) -> None:
        runner.invoke(config_app, ["set", "custom.key", "7"])
        result = runner.invoke(config_app, ["list"])
        assert result.exit_code == 0
        assert "maintain.auto_link_on_save = true (default)" in result.output
        assert "custom.key = 7" in result.output


class TestSaveHonorsAutoLinkSetting:
    """`emdx save` reads maintain.auto_link_on_save when no flag is given (#1038)."""

    def _save(self, *extra_args: str) -> object:
        with (
            patch("emdx.commands.core.display_save_result"),
            patch("emdx.commands.core.apply_tags", return_value=[]),
            patch("emdx.commands.core.create_document", return_value=42),
            patch("emdx.commands.core.detect_project", return_value=None),
            patch("emdx.services.link_service.auto_link_document") as mock_link,
        ):
            result = runner.invoke(core_app, ["save", "some content", *extra_args])
            assert result.exit_code == 0, result.output
        return mock_link

    def test_auto_links_by_default(self) -> None:
        mock_link = self._save()
        mock_link.assert_called_once()

    def test_setting_false_skips_auto_link(self) -> None:
        set_config_value("maintain.auto_link_on_save", False)
        mock_link = self._save()
        mock_link.assert_not_called()

    def test_explicit_flag_overrides_setting(self) -> None:
        set_config_value("maintain.auto_link_on_save", False)
        mock_link = self._save("--auto-link")
        mock_link.assert_called_once()

    def test_no_auto_link_flag_still_works(self) -> None:
        mock_link = self._save("--no-auto-link")
        mock_link.assert_not_called()
