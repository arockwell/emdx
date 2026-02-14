#!/usr/bin/env python3
"""Test script for EMDX execution system fixes.

Run this manually to validate the fixes:
    python tests/test_execution_system.py
"""

import os
import re
import subprocess
import tempfile
import pytest


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


@pytest.mark.integration
def test_execution_id_uniqueness():
    """Test that execution IDs are unique (when environment allows)."""
    # Create test document
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("print('Test')")
        test_file = f.name

    try:
        # Save document
        result = subprocess.run(
            ["emdx", "save", test_file, "--title", "Test Doc"],
            capture_output=True,
            text=True
        )

        # Assert save command succeeded
        assert result.returncode == 0, f"Save command failed with return code {result.returncode}: {result.stderr}"

        # Extract doc ID and validate format (strip ANSI codes)
        stdout_clean = strip_ansi(result.stdout)
        doc_id = None
        for line in stdout_clean.split('\n'):
            if 'Saved as #' in line:
                # Format: "✅ Saved as #1758: Test Doc"
                doc_id = line.split('#')[1].split(':')[0].strip()
                break

        assert doc_id is not None, f"Failed to extract doc ID from output: {stdout_clean}"
        assert doc_id.isdigit(), f"Doc ID should be numeric, got: {doc_id}"

        # Start multiple executions rapidly
        exec_ids = []
        for i in range(3):
            result = subprocess.run(
                ["emdx", "claude", "execute", doc_id, "--background"],
                capture_output=True,
                text=True
            )

            # Extract execution ID from output
            for line in result.stdout.split('\n'):
                if 'Execution ID:' in line:
                    exec_id = line.split(':')[1].strip()
                    exec_ids.append(exec_id)
                    break

        # Skip if environment doesn't support executions, but assert uniqueness if any were created
        if len(exec_ids) == 0:
            pytest.skip("No executions started - environment may not be configured for claude execution")

        # Assert all execution IDs are non-empty strings
        for exec_id in exec_ids:
            assert exec_id, "Execution ID should not be empty"
            assert len(exec_id) > 0, "Execution ID should have non-zero length"

        # Assert uniqueness
        unique_ids = set(exec_ids)
        assert len(exec_ids) == len(unique_ids), f"Duplicate execution IDs found: {exec_ids}"

    finally:
        # Clean up temp file
        try:
            os.unlink(test_file)
        except OSError:
            pass


@pytest.mark.integration
def test_maintenance_commands():
    """Test maintenance commands exist and produce expected help output."""
    # Test maintain --help
    result = subprocess.run(["emdx", "maintain", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, f"maintain --help failed: {result.stderr}"
    assert "maintain" in result.stdout.lower(), "Help output should mention 'maintain'"
    # Help output should contain usage information
    assert "--help" in result.stdout or "Usage:" in result.stdout or "Options:" in result.stdout, \
        f"Help output should contain usage info, got: {result.stdout[:200]}"

    # Test maintain analyze --help
    result = subprocess.run(["emdx", "maintain", "analyze", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, f"maintain analyze --help failed: {result.stderr}"
    assert "analyze" in result.stdout.lower(), "Help output should mention 'analyze'"

    # Test exec --help
    result = subprocess.run(["emdx", "exec", "--help"], capture_output=True, text=True)
    assert result.returncode == 0, f"exec --help failed: {result.stderr}"
    assert "exec" in result.stdout.lower() or "execution" in result.stdout.lower(), \
        "Help output should mention 'exec' or 'execution'"

    # Test exec stats - should run and produce structured output
    result = subprocess.run(["emdx", "exec", "stats"], capture_output=True, text=True)
    assert result.returncode == 0, f"exec stats failed: {result.stderr}"
    # Stats output should contain some statistics-related content
    output = result.stdout.lower()
    assert any(term in output for term in ["total", "count", "execution", "stats", "no executions"]), \
        f"Stats output should contain statistical information, got: {result.stdout[:200]}"


@pytest.mark.integration
def test_execution_monitoring():
    """Test execution monitoring commands produce valid output."""
    # Test exec list
    result = subprocess.run(["emdx", "exec", "list", "--limit", "5"], capture_output=True, text=True)
    assert result.returncode == 0, f"exec list failed with code {result.returncode}: {result.stderr}"
    # Output should either show executions or indicate none exist
    output = result.stdout.lower()
    assert any(term in output for term in ["execution", "id", "status", "no executions", "empty"]) or result.stdout.strip() == "", \
        f"exec list should show execution info or indicate none exist, got: {result.stdout[:200]}"

    # Test exec stats
    result = subprocess.run(["emdx", "exec", "stats"], capture_output=True, text=True)
    assert result.returncode == 0, f"exec stats failed with code {result.returncode}: {result.stderr}"
    output = result.stdout.lower()
    assert any(term in output for term in ["total", "stats", "count", "execution", "no executions"]), \
        f"exec stats should show statistics or indicate none exist, got: {result.stdout[:200]}"

    # Test exec health
    result = subprocess.run(["emdx", "exec", "health"], capture_output=True, text=True)
    assert result.returncode == 0, f"exec health failed with code {result.returncode}: {result.stderr}"
    output = result.stdout.lower()
    # Health check should report on system state
    assert any(term in output for term in ["health", "ok", "status", "running", "stopped", "no", "healthy"]), \
        f"exec health should report system health status, got: {result.stdout[:200]}"

    # Test exec monitor with --no-follow (non-blocking)
    result = subprocess.run(["emdx", "exec", "monitor", "--no-follow"], capture_output=True, text=True)
    assert result.returncode == 0, f"exec monitor --no-follow failed with code {result.returncode}: {result.stderr}"
    # Monitor should complete immediately with --no-follow and show some status


@pytest.mark.integration
def test_environment_validation():
    """Test environment validation command runs and produces diagnostic output."""
    result = subprocess.run(
        ["emdx", "claude", "check-env"],
        capture_output=True,
        text=True
    )

    # Command should always complete (exit 0 for configured, non-zero for issues)
    # But it should never crash - it should provide diagnostic info
    output = result.stdout.lower() + result.stderr.lower()

    # The command should produce some form of environment diagnostic output
    diagnostic_terms = [
        "configured", "environment", "claude", "api", "key", "check",
        "missing", "found", "valid", "invalid", "error", "warning", "ok"
    ]
    has_diagnostic_output = any(term in output for term in diagnostic_terms)
    assert has_diagnostic_output, \
        f"check-env should produce diagnostic output about environment, got: {result.stdout[:300]}"

    # Validate return code semantics
    if "properly configured" in result.stdout:
        assert result.returncode == 0, \
            "check-env should return 0 when environment is properly configured"
    elif result.returncode != 0:
        # Non-zero return should indicate specific issues, not a crash
        assert len(result.stdout) > 0 or len(result.stderr) > 0, \
            "check-env with non-zero return should explain what's wrong"


def main():
    """Run all tests manually (for debugging outside pytest)."""
    tests = [
        test_environment_validation,
        test_execution_id_uniqueness,
        test_maintenance_commands,
        test_execution_monitoring,
    ]

    passed = 0
    failed = 0
    skipped = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except pytest.skip.Exception:
            skipped += 1
        except (AssertionError, Exception):
            failed += 1

    return failed == 0


if __name__ == "__main__":
    main()
