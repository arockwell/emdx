"""Exercise selection before imports in a real CLI process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture()
def cli_env(tmp_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("EMDX_TEST_DB", "EMDX_DB", "EMDX_KB"):
        env.pop(key, None)
    env["HOME"] = str(tmp_path)
    env["EMDX_CONFIG_FILE"] = str(tmp_path / "config.json")
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    return env


def run_cli(tmp_path: Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "from emdx.main import run; run()", *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize("source", ["env", "default", "mapping"])
@pytest.mark.parametrize("name", ["missing", "INVALID"])
def test_broken_selection_can_be_overridden_and_repaired(
    tmp_path: Path, cli_env: dict[str, str], source: str, name: str
) -> None:
    config: dict[str, str] = {}
    if source == "env":
        cli_env["EMDX_KB"] = name
    elif source == "default":
        config["kb.default"] = name
    else:
        config[f"kb.dirs.{name}"] = str(tmp_path)
    Path(cli_env["EMDX_CONFIG_FILE"]).write_text(json.dumps(config))

    failed = run_cli(tmp_path, cli_env, "db", "path")
    assert failed.returncode == 1
    assert "Error:" in failed.stderr
    assert "Traceback" not in failed.stderr
    assert not (tmp_path / ".config/emdx/kb" / f"{name}.db").exists()

    overridden = run_cli(tmp_path, cli_env, "--kb", "default", "db", "path")
    assert overridden.returncode == 0, overridden.stderr
    assert str(tmp_path / ".config/emdx/knowledge.db") in overridden.stdout

    repair = run_cli(tmp_path, cli_env, "kb", "use", "--clear")
    assert repair.returncode == 0, repair.stderr
    created = run_cli(tmp_path, cli_env, "kb", "create", "recovered")
    assert created.returncode == 0, created.stderr
    fixed = run_cli(tmp_path, cli_env, "config", "unset", "kb.default")
    assert fixed.returncode == 0, fixed.stderr


@pytest.mark.parametrize("variable", ["EMDX_DB", "EMDX_TEST_DB"])
def test_effective_override_reporting(
    tmp_path: Path, cli_env: dict[str, str], variable: str
) -> None:
    cli_env["EMDX_KB"] = "INVALID"
    cli_env[variable] = str(tmp_path / "override.db")
    result = run_cli(tmp_path, cli_env, "kb", "current", "--json")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["name"] is None
    assert data["path"] == cli_env[variable]
    assert variable in data["reason"]
    assert not Path(cli_env[variable]).exists()
    result = run_cli(tmp_path, cli_env, "kb", "list", "--json")
    assert result.returncode == 0, result.stderr
    assert not any(row["active"] for row in json.loads(result.stdout))


def test_development_destination_reporting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from typer.testing import CliRunner

    from emdx.config import settings
    from emdx.main import app

    monkeypatch.delenv("EMDX_TEST_DB", raising=False)
    monkeypatch.delenv("EMDX_DB", raising=False)
    monkeypatch.setenv("EMDX_KB", "INVALID")
    monkeypatch.setattr(settings, "_is_dev_checkout", lambda: True)
    monkeypatch.setattr(settings, "_project_root", lambda: tmp_path)
    result = CliRunner().invoke(app, ["kb", "current", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["name"] is None
    assert data["path"] == str(tmp_path / ".emdx/dev.db")
    assert "dev checkout" in data["reason"]
    assert not (tmp_path / ".emdx").exists()
