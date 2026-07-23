"""Tests for emdx config module.

get_db_path's priority chain is the only guard keeping dev/agent
processes off the production ~/.config/emdx/knowledge.db:

    1. EMDX_TEST_DB  — test isolation
    2. EMDX_DB       — explicit override (creates parent dir)
    3. Dev checkout  — <project-root>/.emdx/dev.db
    4. Production    — ~/.config/emdx/knowledge.db

Every branch and the precedence order are covered here. All tests use
tmp_path/monkeypatch and never touch the real ~/.config/emdx.
"""

from pathlib import Path

import pytest

from emdx.config import settings
from emdx.config.settings import _is_dev_checkout, get_db_path


@pytest.fixture()
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Clear DB env vars and redirect the production dir to tmp_path.

    Guarantees no branch of get_db_path can reach the real
    ~/.config/emdx, no matter which branch a test exercises.
    """
    monkeypatch.delenv("EMDX_TEST_DB", raising=False)
    monkeypatch.delenv("EMDX_DB", raising=False)
    fake_prod_dir = tmp_path / "prod-config"
    monkeypatch.setattr(settings, "EMDX_CONFIG_DIR", fake_prod_dir)
    return fake_prod_dir


def _fake_checkout(tmp_path: Path, with_pyproject: bool) -> Path:
    """Build <root>/emdx/config/settings.py layout; return the fake settings.py path."""
    root = tmp_path / "checkout"
    config_dir = root / "emdx" / "config"
    config_dir.mkdir(parents=True)
    fake_settings = config_dir / "settings.py"
    fake_settings.write_text("# fake\n")
    if with_pyproject:
        (root / "pyproject.toml").write_text('[tool.poetry]\nname = "emdx"\n')
    return fake_settings


# ---------------------------------------------------------------------------
# Branch 1: EMDX_TEST_DB
# ---------------------------------------------------------------------------


def test_test_db_env_returns_exact_path(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    test_db = tmp_path / "test.db"
    monkeypatch.setenv("EMDX_TEST_DB", str(test_db))
    assert get_db_path() == test_db


def test_test_db_env_does_not_create_parent(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """EMDX_TEST_DB is returned as-is — no mkdir side effects."""
    test_db = tmp_path / "nested" / "dirs" / "test.db"
    monkeypatch.setenv("EMDX_TEST_DB", str(test_db))
    assert get_db_path() == test_db
    assert not test_db.parent.exists()


def test_empty_test_db_env_falls_through(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Empty EMDX_TEST_DB is falsy and must not shadow EMDX_DB."""
    explicit_db = tmp_path / "explicit.db"
    monkeypatch.setenv("EMDX_TEST_DB", "")
    monkeypatch.setenv("EMDX_DB", str(explicit_db))
    assert get_db_path() == explicit_db


# ---------------------------------------------------------------------------
# Branch 2: EMDX_DB (explicit override)
# ---------------------------------------------------------------------------


def test_explicit_db_env_returns_exact_path(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    explicit_db = tmp_path / "explicit.db"
    monkeypatch.setenv("EMDX_DB", str(explicit_db))
    assert get_db_path() == explicit_db


def test_explicit_db_env_creates_missing_nested_parent(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """EMDX_DB pointing at a non-existent nested dir creates the parents."""
    explicit_db = tmp_path / "a" / "b" / "c" / "explicit.db"
    assert not explicit_db.parent.exists()
    monkeypatch.setenv("EMDX_DB", str(explicit_db))
    assert get_db_path() == explicit_db
    assert explicit_db.parent.is_dir()
    # The db file itself is not created — only the parent dir.
    assert not explicit_db.exists()


def test_explicit_db_env_existing_parent_ok(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """mkdir(exist_ok=True): an existing parent must not raise."""
    explicit_db = tmp_path / "explicit.db"
    monkeypatch.setenv("EMDX_DB", str(explicit_db))
    assert get_db_path() == explicit_db
    assert get_db_path() == explicit_db  # second call, parent already exists


# ---------------------------------------------------------------------------
# Branch 3: dev checkout detection
# ---------------------------------------------------------------------------


def test_is_dev_checkout_true_in_this_repo() -> None:
    """Regression guard: running from the repo MUST be detected as a dev
    checkout. This was broken (parent.parent stopped at the emdx package
    dir instead of the project root), silently routing all dev writes to
    the production database.
    """
    assert _is_dev_checkout() is True


def test_is_dev_checkout_true_when_pyproject_at_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_settings = _fake_checkout(tmp_path, with_pyproject=True)
    monkeypatch.setattr(settings, "__file__", str(fake_settings))
    assert _is_dev_checkout() is True


def test_is_dev_checkout_false_without_pyproject(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_settings = _fake_checkout(tmp_path, with_pyproject=False)
    monkeypatch.setattr(settings, "__file__", str(fake_settings))
    assert _is_dev_checkout() is False


def test_is_dev_checkout_false_for_site_packages_layout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Installed layout: site-packages/emdx/config/settings.py with a
    pyproject.toml further up (e.g. a project using emdx as a dependency)
    must NOT be treated as a dev checkout."""
    site = tmp_path / "proj" / ".venv" / "lib" / "python3.11" / "site-packages"
    config_dir = site / "emdx" / "config"
    config_dir.mkdir(parents=True)
    fake_settings = config_dir / "settings.py"
    fake_settings.write_text("# fake\n")
    (tmp_path / "proj" / "pyproject.toml").write_text('[project]\nname = "other"\n')
    monkeypatch.setattr(settings, "__file__", str(fake_settings))
    assert _is_dev_checkout() is False


def test_dev_checkout_returns_local_dev_db(
    clean_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_settings = _fake_checkout(tmp_path, with_pyproject=True)
    monkeypatch.setattr(settings, "__file__", str(fake_settings))

    db_path = get_db_path()

    root = fake_settings.parent.parent.parent
    assert db_path == root / ".emdx" / "dev.db"
    assert db_path.parent.is_dir()
    # First run announces the dev DB on stderr.
    assert "Using dev database" in capsys.readouterr().err


def test_dev_checkout_existing_dev_db_is_quiet(
    clean_env: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake_settings = _fake_checkout(tmp_path, with_pyproject=True)
    monkeypatch.setattr(settings, "__file__", str(fake_settings))
    root = fake_settings.parent.parent.parent
    dev_db = root / ".emdx" / "dev.db"
    dev_db.parent.mkdir(parents=True)
    dev_db.touch()

    assert get_db_path() == dev_db
    assert capsys.readouterr().err == ""


# ---------------------------------------------------------------------------
# Branch 4: production default
# ---------------------------------------------------------------------------


def test_production_default_when_nothing_else_applies(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "_is_dev_checkout", lambda: False)
    db_path = get_db_path()
    assert db_path == clean_env / "knowledge.db"
    assert db_path.parent.is_dir()  # config dir is created


# ---------------------------------------------------------------------------
# Precedence order
# ---------------------------------------------------------------------------


def test_test_db_beats_explicit_db_and_dev_checkout(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    test_db = tmp_path / "test.db"
    explicit_db = tmp_path / "explicit.db"
    monkeypatch.setenv("EMDX_TEST_DB", str(test_db))
    monkeypatch.setenv("EMDX_DB", str(explicit_db))
    monkeypatch.setattr(settings, "_is_dev_checkout", lambda: True)
    assert get_db_path() == test_db


def test_explicit_db_beats_dev_checkout(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    explicit_db = tmp_path / "explicit.db"
    monkeypatch.setenv("EMDX_DB", str(explicit_db))

    def _boom() -> bool:
        raise AssertionError("_is_dev_checkout must not be consulted when EMDX_DB is set")

    monkeypatch.setattr(settings, "_is_dev_checkout", _boom)
    assert get_db_path() == explicit_db


def test_dev_checkout_beats_production_default(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_settings = _fake_checkout(tmp_path, with_pyproject=True)
    monkeypatch.setattr(settings, "__file__", str(fake_settings))
    db_path = get_db_path()
    assert db_path.name == "dev.db"
    assert db_path != clean_env / "knowledge.db"


def test_full_priority_chain_order(
    clean_env: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Peel the chain one layer at a time and assert each winner."""
    test_db = tmp_path / "test.db"
    explicit_db = tmp_path / "explicit.db"
    fake_settings = _fake_checkout(tmp_path, with_pyproject=True)
    monkeypatch.setattr(settings, "__file__", str(fake_settings))
    root = fake_settings.parent.parent.parent

    monkeypatch.setenv("EMDX_TEST_DB", str(test_db))
    monkeypatch.setenv("EMDX_DB", str(explicit_db))
    assert get_db_path() == test_db

    monkeypatch.delenv("EMDX_TEST_DB")
    assert get_db_path() == explicit_db

    monkeypatch.delenv("EMDX_DB")
    assert get_db_path() == root / ".emdx" / "dev.db"

    (root / "pyproject.toml").unlink()
    assert get_db_path() == clean_env / "knowledge.db"


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def test_get_db_path_returns_consistent_path() -> None:
    """Same result across calls (under the session's EMDX_TEST_DB fixture)."""
    assert get_db_path() == get_db_path()
