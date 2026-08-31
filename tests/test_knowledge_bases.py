"""Tests for named knowledge bases (config/knowledge_bases.py, `emdx kb`, --kb).

All tests redirect EMDX_CONFIG_DIR and EMDX_CONFIG_FILE into tmp_path and
clear the DB env vars, so nothing touches the real ~/.config/emdx.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from emdx.config import constants, knowledge_bases, settings
from emdx.config.knowledge_bases import (
    InvalidKnowledgeBaseName,
    UnknownKnowledgeBase,
    kb_db_path,
    kb_for_directory,
    require_kb,
    resolve_kb,
)
from emdx.main import app as main_app

runner = CliRunner()


def _out(result: Any) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


@pytest.fixture()
def kb_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Isolated config dir + config file, no DB env vars, not a dev checkout."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    monkeypatch.setattr(constants, "EMDX_CONFIG_DIR", config_dir)
    monkeypatch.setattr(settings, "EMDX_CONFIG_DIR", config_dir)
    monkeypatch.setenv("EMDX_CONFIG_FILE", str(config_dir / "config.json"))
    for var in ("EMDX_TEST_DB", "EMDX_DB", "EMDX_KB"):
        # setenv-then-delenv so monkeypatch records the original absence and
        # undoes anything the CLI callback exports (os.environ["EMDX_KB"] = ...)
        monkeypatch.setenv(var, "")
        monkeypatch.delenv(var)
    monkeypatch.setattr(settings, "_is_dev_checkout", lambda: False)
    # --kb re-points the process-wide connection; restore it for later tests
    from emdx.database import connection

    monkeypatch.setattr(connection.db_connection, "db_path", connection.db_connection.db_path)
    monkeypatch.chdir(tmp_path)
    return config_dir


def _create(name: str) -> Path:
    path = kb_db_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------
class TestResolution:
    def test_default_when_nothing_configured(self, kb_env: Path) -> None:
        sel = resolve_kb()
        assert sel.name == "default"
        assert sel.path == kb_env / "knowledge.db"
        assert sel.reason == "default"

    def test_env_var_wins(self, kb_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMDX_KB", "propolis")
        sel = resolve_kb()
        assert sel.name == "propolis"
        assert sel.path == kb_env / "kb" / "propolis.db"

    def test_kb_default_setting(self, kb_env: Path) -> None:
        from emdx.config.app_config import set_config_value

        set_config_value("kb.default", "notes")
        assert resolve_kb().name == "notes"
        assert resolve_kb().reason == "kb.default setting"

    def test_directory_mapping_deepest_wins(
        self, kb_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from emdx.config.app_config import set_config_value

        outer = tmp_path / "work"
        inner = outer / "client"
        inner.mkdir(parents=True)
        set_config_value("kb.dirs.work", str(outer))
        set_config_value("kb.dirs.client", f"{tmp_path / 'elsewhere'}:{inner}")
        assert kb_for_directory(outer) == "work"
        assert kb_for_directory(inner) == "client"
        assert kb_for_directory(tmp_path) is None
        monkeypatch.chdir(inner)
        assert resolve_kb().name == "client"

    def test_env_beats_mapping_and_setting(
        self, kb_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from emdx.config.app_config import set_config_value

        set_config_value("kb.dirs.mapped", str(tmp_path))
        set_config_value("kb.default", "configured")
        monkeypatch.setenv("EMDX_KB", "explicit")
        assert resolve_kb().name == "explicit"

    def test_invalid_name_rejected(self, kb_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMDX_KB", "../evil")
        with pytest.raises(InvalidKnowledgeBaseName):
            resolve_kb()

    def test_require_kb_unknown(self, kb_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMDX_KB", "nope")
        with pytest.raises(UnknownKnowledgeBase):
            require_kb()

    def test_require_kb_default_never_fails(self, kb_env: Path) -> None:
        assert require_kb().name == "default"


class TestGetDbPath:
    def test_named_kb_path(self, kb_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _create("propolis")
        monkeypatch.setenv("EMDX_KB", "propolis")
        assert settings.get_db_path() == kb_env / "kb" / "propolis.db"

    def test_default_kb_is_production_db(self, kb_env: Path) -> None:
        assert settings.get_db_path() == kb_env / "knowledge.db"

    def test_emdx_db_overrides_kb(
        self, kb_env: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EMDX_KB", "propolis")
        monkeypatch.setenv("EMDX_DB", str(tmp_path / "explicit.db"))
        assert settings.get_db_path() == tmp_path / "explicit.db"

    def test_unknown_kb_raises(self, kb_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMDX_KB", "ghost")
        with pytest.raises(UnknownKnowledgeBase):
            settings.get_db_path()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
class TestKbCli:
    def test_create_list_current(self, kb_env: Path) -> None:
        result = runner.invoke(main_app, ["kb", "create", "propolis"])
        assert result.exit_code == 0, result.output
        assert (kb_env / "kb" / "propolis.db").exists()
        # migrations ran: documents table exists
        import sqlite3

        conn = sqlite3.connect(kb_env / "kb" / "propolis.db")
        assert conn.execute("select name from sqlite_master where name='documents'").fetchone()
        conn.close()

        result = runner.invoke(main_app, ["kb", "list"])
        assert result.exit_code == 0
        out = _out(result)
        assert "* default" in out
        assert "propolis" in out

        result = runner.invoke(main_app, ["--kb", "propolis", "kb", "current"])
        assert result.exit_code == 0
        assert "Knowledge base: propolis" in _out(result)

    def test_create_rejects_duplicate_and_bad_name(self, kb_env: Path) -> None:
        _create("dupe")
        result = runner.invoke(main_app, ["kb", "create", "dupe"])
        assert result.exit_code == 1
        result = runner.invoke(main_app, ["kb", "create", "Bad Name"])
        assert result.exit_code == 1

    def test_use_sets_default(self, kb_env: Path) -> None:
        _create("notes")
        result = runner.invoke(main_app, ["kb", "use", "notes"])
        assert result.exit_code == 0, result.output
        assert resolve_kb().name == "notes"
        result = runner.invoke(main_app, ["kb", "use", "--clear"])
        assert result.exit_code == 0
        assert resolve_kb().name == "default"

    def test_use_unknown_fails(self, kb_env: Path) -> None:
        result = runner.invoke(main_app, ["kb", "use", "missing"])
        assert result.exit_code == 1

    def test_map_and_remove(self, kb_env: Path, tmp_path: Path) -> None:
        _create("client")
        d = tmp_path / "proj"
        d.mkdir()
        result = runner.invoke(main_app, ["kb", "map", "client", str(d)])
        assert result.exit_code == 0, result.output
        assert kb_for_directory(d) == "client"
        result = runner.invoke(main_app, ["kb", "map", "--remove", "client", str(d)])
        assert result.exit_code == 0, result.output
        assert kb_for_directory(d) is None

    def test_unknown_kb_on_normal_command_is_friendly(
        self, kb_env: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = runner.invoke(main_app, ["--kb", "ghost", "db", "path"])
        assert result.exit_code == 1
        assert "does not exist" in result.output
        assert "emdx kb create ghost" in result.output

    def test_db_status_reports_kb(self, kb_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _create("propolis")
        monkeypatch.setenv("EMDX_KB", "propolis")
        result = runner.invoke(main_app, ["db", "status"])
        assert result.exit_code == 0, result.output
        assert "knowledge base 'propolis'" in _out(result)

    def test_kb_flag_scopes_documents(self, kb_env: Path) -> None:
        """A doc saved into one KB is invisible from another."""
        runner.invoke(main_app, ["kb", "create", "a"])
        runner.invoke(main_app, ["kb", "create", "b"])
        result = runner.invoke(
            main_app, ["--kb", "a", "save", "--title", "Only in A"], input="hello\n"
        )
        assert result.exit_code == 0, result.output
        assert "Only in A" in _out(runner.invoke(main_app, ["--kb", "a", "find", "--all"]))
        assert "Only in A" not in _out(runner.invoke(main_app, ["--kb", "b", "find", "--all"]))


def test_list_kbs_ignores_stray_files(kb_env: Path) -> None:
    (kb_env / "kb").mkdir()
    (kb_env / "kb" / "good.db").touch()
    (kb_env / "kb" / "Bad Name.db").touch()
    (kb_env / "kb" / "notes.txt").touch()
    assert knowledge_bases.list_kbs() == ["default", "good"]
