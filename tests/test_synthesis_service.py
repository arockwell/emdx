"""Tests for synthesis service prompt execution.

Regression tests for argv exposure: document contents must be passed
to the ``claude`` CLI via stdin, never as a positional argument —
process arguments are world-readable via ps/procfs and can exceed
ARG_MAX for large documents.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from emdx.services.synthesis_service import SYNTHESIS_TIMEOUT, _execute_prompt


def _success_run(returncode: int = 0, stdout: str = "synthesized") -> MagicMock:
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = ""
    return result


class TestExecutePromptStdin:
    @patch("emdx.services.synthesis_service.subprocess.run")
    def test_prompt_passed_via_stdin_not_argv(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _success_run()
        secret_content = "password=hunter2 and sk-ant-secret-key-material"

        result = _execute_prompt("You are a synthesizer", secret_content, "title")

        assert result.success
        cmd = mock_run.call_args[0][0]
        assert cmd == ["claude", "--print"]
        # No part of the prompt appears in argv
        assert all(secret_content not in arg for arg in cmd)
        # Full prompt (system + user) goes through stdin
        stdin = mock_run.call_args.kwargs["input"]
        assert secret_content in stdin
        assert "You are a synthesizer" in stdin

    @patch("emdx.services.synthesis_service.subprocess.run")
    def test_model_flag_still_on_argv(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _success_run()

        _execute_prompt("system", "user message", "title", model="claude-fable-5")

        cmd = mock_run.call_args[0][0]
        assert cmd == ["claude", "--print", "--model", "claude-fable-5"]
        assert "user message" in mock_run.call_args.kwargs["input"]

    @patch("emdx.services.synthesis_service.subprocess.run")
    def test_large_prompt_never_hits_argv(self, mock_run: MagicMock) -> None:
        """Prompts larger than ARG_MAX must not be argv arguments."""
        mock_run.return_value = _success_run()
        huge = "x" * 300_000  # > Linux MAX_ARG_STRLEN (128 KiB)

        _execute_prompt("system", huge, "title")

        cmd = mock_run.call_args[0][0]
        assert max(len(arg) for arg in cmd) < 1024
        assert huge in mock_run.call_args.kwargs["input"]

    @patch("emdx.services.synthesis_service.subprocess.run")
    def test_nonzero_exit_raises_runtime_error(self, mock_run: MagicMock) -> None:
        mock_run.return_value = _success_run(returncode=1)
        mock_run.return_value.stderr = "boom"

        with pytest.raises(RuntimeError, match="boom"):
            _execute_prompt("system", "user", "title")

    @patch("emdx.services.synthesis_service.subprocess.run")
    def test_timeout_raises_runtime_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["claude", "--print"], timeout=SYNTHESIS_TIMEOUT
        )

        with pytest.raises(RuntimeError, match="timed out"):
            _execute_prompt("system", "user", "title")
