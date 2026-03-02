"""Tests for the db management commands (db status, db path, db copy-from-prod)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from unittest.mock import patch

from typer.testing import CliRunner

from emdx.main import app as main_app

runner = CliRunner()


def _out(result: Any) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# db status command
# ---------------------------------------------------------------------------
class TestDbStatus:
    """Tests for the db status command."""

    def test_db_status_shows_active_path(self) -> None:
        """db status displays the active database path."""
        result = runner.invoke(main_app, ["db", "status"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Active DB:" in out
        assert "Reason:" in out

    def test_db_status_shows_production_path(self) -> None:
        """db status displays the production database path."""
        result = runner.invoke(main_app, ["db", "status"])
        assert result.exit_code == 0
        out = _out(result)
        assert "Production:" in out

    @patch.dict("os.environ", {"EMDX_TEST_DB": "/tmp/test.db"})
    def test_db_status_test_env_reason(self) -> None:
        """db status shows EMDX_TEST_DB reason when env var is set."""
        result = runner.invoke(main_app, ["db", "status"])
        assert result.exit_code == 0
        out = _out(result)
        assert "EMDX_TEST_DB" in out


# ---------------------------------------------------------------------------
# db path command
# ---------------------------------------------------------------------------
class TestDbPath:
    """Tests for the db path command."""

    def test_db_path_prints_path(self) -> None:
        """db path prints just the database path."""
        result = runner.invoke(main_app, ["db", "path"])
        assert result.exit_code == 0
        out = _out(result).strip()
        # Should be a path (contains / or \)
        assert "/" in out or "\\" in out


# ---------------------------------------------------------------------------
# db copy-from-prod command
# ---------------------------------------------------------------------------
class TestDbCopyFromProd:
    """Tests for the db copy-from-prod command."""

    @patch("emdx.commands.db_manage.get_db_path")
    @patch("emdx.commands.db_manage.EMDX_CONFIG_DIR", new_callable=lambda: type(Path()))
    def test_copy_from_prod_same_path_errors(
        self, mock_config_dir: Any, mock_get_path: Any
    ) -> None:
        """copy-from-prod errors when already using production database."""
        prod_path = Path("/home/user/.config/emdx/knowledge.db")
        mock_get_path.return_value = prod_path

        with patch("emdx.commands.db_manage.EMDX_CONFIG_DIR", Path("/home/user/.config/emdx")):
            result = runner.invoke(main_app, ["db", "copy-from-prod"])
            # Should exit with error code
            assert result.exit_code != 0 or "Already using" in result.output

    @patch("emdx.commands.db_manage.shutil.copy2")
    @patch("emdx.commands.db_manage.get_db_path")
    def test_copy_from_prod_no_prod_db(
        self, mock_get_path: Any, mock_copy: Any, tmp_path: Path
    ) -> None:
        """copy-from-prod errors when production database doesn't exist."""
        mock_get_path.return_value = tmp_path / "dev.db"

        with patch(
            "emdx.commands.db_manage.EMDX_CONFIG_DIR",
            tmp_path / "nonexistent_config",
        ):
            result = runner.invoke(main_app, ["db", "copy-from-prod"])
            assert result.exit_code != 0 or "not found" in result.output


# ---------------------------------------------------------------------------
# db --help
# ---------------------------------------------------------------------------
class TestDbHelp:
    """Tests for the db help output."""

    def test_db_help(self) -> None:
        """db --help shows available subcommands."""
        result = runner.invoke(main_app, ["db", "--help"])
        assert result.exit_code == 0
        out = _out(result)
        assert "status" in out
        assert "path" in out
        assert "copy-from-prod" in out
