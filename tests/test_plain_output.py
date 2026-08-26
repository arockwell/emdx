"""Tests for the TTY/non-TTY output styling split.

emdx is piped by agents far more often than it's read by a human on a
real terminal. Rich's Console must not force ANSI styling on a pipe:
stray escape sequences fragment tokens (e.g. a task ID) that a piped
consumer needs to parse cleanly.
"""

from __future__ import annotations

import os
import subprocess
import sys
from unittest.mock import patch

from emdx.utils.output import Table, use_styling

ESC = "\x1b["


# ---------------------------------------------------------------------------
# use_styling() unit tests
# ---------------------------------------------------------------------------
class TestUseStyling:
    """Unit tests for the use_styling() decision function."""

    def test_plain_when_stdout_not_a_tty(self) -> None:
        with patch("sys.stdout.isatty", return_value=False), patch.dict(os.environ, {}, clear=True):
            assert use_styling() is False

    def test_styled_when_stdout_is_a_tty(self) -> None:
        with patch("sys.stdout.isatty", return_value=True), patch.dict(os.environ, {}, clear=True):
            assert use_styling() is True

    def test_no_color_forces_plain_even_on_a_tty(self) -> None:
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch.dict(os.environ, {"NO_COLOR": "1"}, clear=True),
        ):
            assert use_styling() is False

    def test_force_color_forces_styled_even_when_piped(self) -> None:
        with (
            patch("sys.stdout.isatty", return_value=False),
            patch.dict(os.environ, {"FORCE_COLOR": "1"}, clear=True),
        ):
            assert use_styling() is True

    def test_force_color_wins_over_no_color(self) -> None:
        with (
            patch("sys.stdout.isatty", return_value=False),
            patch.dict(os.environ, {"FORCE_COLOR": "1", "NO_COLOR": "1"}, clear=True),
        ):
            assert use_styling() is True


# ---------------------------------------------------------------------------
# Table degradation
# ---------------------------------------------------------------------------
class TestPlainTable:
    """Table should drop box-drawing when output isn't styled."""

    def test_box_none_when_not_styled(self) -> None:
        with patch("sys.stdout.isatty", return_value=False), patch.dict(os.environ, {}, clear=True):
            table = Table(title="t")
            assert table.box is None

    def test_box_kept_when_styled(self) -> None:
        with patch("sys.stdout.isatty", return_value=True), patch.dict(os.environ, {}, clear=True):
            table = Table(title="t")
            assert table.box is not None


# ---------------------------------------------------------------------------
# Real subprocess: stdout as an actual pipe, no TTY.
# ---------------------------------------------------------------------------
def _run_emdx(args: list[str], extra_env: dict[str, str] | None = None) -> str:
    # EMDX_TEST_DB is already set in os.environ by the autouse
    # isolate_test_database fixture, so this inherits the isolated DB.
    env = dict(os.environ)
    env.pop("FORCE_COLOR", None)
    env.pop("NO_COLOR", None)
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        [sys.executable, "-m", "emdx.main", *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(__file__)),
        timeout=30,
    )
    return result.stdout


class TestSubprocessPipedOutput:
    """End-to-end: stdout is a real OS pipe (subprocess.PIPE), not a TTY."""

    def test_task_add_has_no_escape_sequences_when_piped(self) -> None:
        out = _run_emdx(["task", "add", "plain output subprocess test"])
        assert ESC not in out
        assert "Task #" in out or "Task TOOL" in out

    def test_task_ready_table_has_no_escape_sequences_when_piped(self) -> None:
        _run_emdx(["task", "add", "ready list plain test"])
        out = _run_emdx(["task", "ready"])
        assert ESC not in out

    def test_force_color_still_styles_when_piped(self) -> None:
        out = _run_emdx(
            ["task", "add", "force color subprocess test"], extra_env={"FORCE_COLOR": "1"}
        )
        assert ESC in out
