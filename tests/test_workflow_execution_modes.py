"""Tests for workflow execution modes — imports, templates, and base classes.

Strategy-specific tests live in test_strategies.py.
"""

import pytest
from emdx.workflows.base import ExecutionMode, StageConfig, StageResult
from emdx.workflows.executor import WorkflowExecutor
from emdx.workflows.template import resolve_template


class TestExecutorImports:
    """Verify executor and base classes can be imported."""

    def test_executor_import(self):
        """WorkflowExecutor can be instantiated."""
        executor = WorkflowExecutor(max_concurrent=5)
        assert executor.max_concurrent == 5

    def test_stage_result_import(self):
        """StageResult can be created."""
        result = StageResult(success=True, output_doc_id=123)
        assert result.success is True
        assert result.output_doc_id == 123

    def test_execution_modes_exist(self):
        """All execution modes are defined."""
        assert ExecutionMode.SINGLE.value == "single"
        assert ExecutionMode.PARALLEL.value == "parallel"
        assert ExecutionMode.ITERATIVE.value == "iterative"
        assert ExecutionMode.ADVERSARIAL.value == "adversarial"
        assert ExecutionMode.DYNAMIC.value == "dynamic"


class TestTemplateResolution:
    """Test template resolution (now in template.py module)."""

    def test_simple_variable(self):
        """Simple {{variable}} substitution works."""
        result = resolve_template("Hello {{name}}", {"name": "World"})
        assert result == "Hello World"

    def test_dotted_variable(self):
        """Dotted {{stage.output}} substitution works."""
        result = resolve_template(
            "Previous: {{stage1.output}}",
            {"stage1.output": "test output"}
        )
        assert result == "Previous: test output"

    def test_indexed_variable(self):
        """Indexed {{array[0]}} substitution works."""
        result = resolve_template(
            "First: {{items[0]}}, Second: {{items[1]}}",
            {"items": ["a", "b", "c"]}
        )
        assert result == "First: a, Second: b"

    def test_missing_variable(self):
        """Missing variables become empty strings."""
        result = resolve_template("Hello {{missing}}", {})
        assert result == "Hello "

    def test_index_out_of_bounds(self):
        """Out of bounds index becomes empty string."""
        result = resolve_template("{{items[99]}}", {"items": ["a"]})
        assert result == ""
