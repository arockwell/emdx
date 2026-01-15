"""Integration tests for the workflow executor.

Tests the WorkflowExecutor class which orchestrates multi-stage agent runs
with different execution modes (single, parallel, iterative, adversarial, dynamic).

NOTE: Many tests were removed during the Phase 1 cleanup because they tested
the strategies/ module which was never integrated. Tests should be added back
that test the executor methods directly.
"""

import pytest
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

from emdx.workflows.base import (
    ExecutionMode,
    StageConfig,
    StageResult,
    WorkflowConfig,
)
from emdx.workflows.executor import WorkflowExecutor
from emdx.workflows.output_parser import extract_output_doc_id, extract_token_usage_detailed


class TestWorkflowExecutorInit:
    """Test WorkflowExecutor initialization."""

    def test_default_max_concurrent(self):
        """Default max_concurrent is 10."""
        executor = WorkflowExecutor()
        assert executor.max_concurrent == 10

    def test_custom_max_concurrent(self):
        """Custom max_concurrent is respected."""
        executor = WorkflowExecutor(max_concurrent=5)
        assert executor.max_concurrent == 5


class TestOutputDocIdExtraction:
    """Test extraction of output document IDs from logs."""

    def test_extract_saved_as_pattern(self, tmp_path):
        """Extract ID from 'Saved as #123' pattern."""
        log_file = tmp_path / "test.log"
        log_file.write_text("Starting...\n✅ Saved as #456\nDone.")

        doc_id = extract_output_doc_id(log_file)
        assert doc_id == 456

    def test_extract_created_document_pattern(self, tmp_path):
        """Extract ID from 'Created document #123' pattern."""
        log_file = tmp_path / "test.log"
        log_file.write_text("Starting...\nCreated document #789\nDone.")

        doc_id = extract_output_doc_id(log_file)
        assert doc_id == 789

    def test_extract_last_match(self, tmp_path):
        """Extract the LAST document ID if multiple are found."""
        log_file = tmp_path / "test.log"
        log_file.write_text("Saved as #100\nSaved as #200\nSaved as #300")

        doc_id = extract_output_doc_id(log_file)
        assert doc_id == 300

    def test_no_doc_id_in_log(self, tmp_path):
        """Return None if no document ID found."""
        log_file = tmp_path / "test.log"
        log_file.write_text("No document was created here.")

        doc_id = extract_output_doc_id(log_file)
        assert doc_id is None

    def test_missing_log_file(self, tmp_path):
        """Return None if log file doesn't exist."""
        log_file = tmp_path / "nonexistent.log"

        doc_id = extract_output_doc_id(log_file)
        assert doc_id is None

    def test_strip_ansi_codes(self, tmp_path):
        """ANSI codes are stripped before matching."""
        log_file = tmp_path / "test.log"
        # Simulate Rich/ANSI formatted output
        log_file.write_text("\x1b[32m✅ Saved as #123\x1b[0m")

        doc_id = extract_output_doc_id(log_file)
        assert doc_id == 123


class TestTokenUsageExtraction:
    """Test extraction of token usage from logs."""

    def test_extract_from_raw_result_json(self, tmp_path):
        """Extract tokens from __RAW_RESULT_JSON__ marker."""
        log_file = tmp_path / "test.log"
        log_file.write_text(
            'Starting...\n'
            '__RAW_RESULT_JSON__:{"type":"result","usage":{"input_tokens":100,"output_tokens":50,"cache_creation_input_tokens":10,"cache_read_input_tokens":5},"total_cost_usd":0.05}\n'
            'Done.'
        )

        usage = extract_token_usage_detailed(log_file)

        assert usage['input'] == 105  # 100 + 5 cache_read
        assert usage['output'] == 50
        assert usage['cache_in'] == 5
        assert usage['cache_create'] == 10
        assert usage['total'] == 165  # 100 + 50 + 10 + 5
        assert usage['cost_usd'] == 0.05

    def test_missing_log_returns_empty(self, tmp_path):
        """Missing log file returns zeros."""
        log_file = tmp_path / "nonexistent.log"

        usage = extract_token_usage_detailed(log_file)

        assert usage == {'input': 0, 'output': 0, 'cache_in': 0, 'cache_create': 0, 'total': 0, 'cost_usd': 0.0}

    def test_no_json_marker_returns_empty(self, tmp_path):
        """Log without JSON marker returns zeros."""
        log_file = tmp_path / "test.log"
        log_file.write_text("Just some log output without the marker")

        usage = extract_token_usage_detailed(log_file)

        assert usage['total'] == 0


class TestTaskExpansion:
    """Test expansion of tasks into prompts."""

    def test_no_tasks_no_expansion(self):
        """Without tasks in context, prompts unchanged."""
        executor = WorkflowExecutor()
        stage = StageConfig(
            name="test",
            mode=ExecutionMode.PARALLEL,
            prompt="Do {{task}}",
        )
        context = {}  # No tasks

        executor._expand_tasks_to_prompts(stage, context)

        # prompts should not be set (or remain None)
        assert stage.prompts is None

    def test_no_prompt_no_expansion(self):
        """Without prompt template, no expansion happens."""
        executor = WorkflowExecutor()
        stage = StageConfig(
            name="test",
            mode=ExecutionMode.PARALLEL,
            prompt=None,  # No prompt
        )
        context = {"tasks": ["task1", "task2"]}

        executor._expand_tasks_to_prompts(stage, context)

        assert stage.prompts is None
