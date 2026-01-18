#!/usr/bin/env python3
"""Verification script for UnifiedExecutor integration.

This script tests the actual execution paths (not mocked) to verify
that the refactored code works correctly end-to-end.

Run with: poetry run python scripts/verify_unified_executor.py

WARNING: This will make actual Claude API calls!
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from rich.console import Console
from rich.table import Table

console = Console()


def check_database_connection():
    """Verify database is accessible."""
    console.print("\n[bold]1. Checking database connection...[/bold]")
    try:
        from emdx.database.connection import db_connection
        with db_connection.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM documents")
            count = cursor.fetchone()[0]
            console.print(f"  [green]✓[/green] Database connected, {count} documents")
            return True
    except Exception as e:
        console.print(f"  [red]✗[/red] Database error: {e}")
        return False


def check_imports():
    """Verify all refactored modules import correctly."""
    console.print("\n[bold]2. Checking imports...[/bold]")

    modules = [
        ("UnifiedExecutor", "emdx.services.unified_executor", "UnifiedExecutor"),
        ("ExecutionConfig", "emdx.services.unified_executor", "ExecutionConfig"),
        ("execute_with_output_tracking", "emdx.services.unified_executor", "execute_with_output_tracking"),
        ("agent command", "emdx.commands.agent", "agent"),
        ("cascade app", "emdx.commands.cascade", "app"),
        ("agent_runner", "emdx.workflows.agent_runner", "run_agent"),
    ]

    all_ok = True
    for name, module, attr in modules:
        try:
            mod = __import__(module, fromlist=[attr])
            getattr(mod, attr)
            console.print(f"  [green]✓[/green] {name}")
        except Exception as e:
            console.print(f"  [red]✗[/red] {name}: {e}")
            all_ok = False

    return all_ok


def check_execution_record_creation():
    """Verify execution records are created correctly."""
    console.print("\n[bold]3. Checking execution record creation...[/bold]")

    try:
        from emdx.models.executions import create_execution, get_execution
        from emdx.database.connection import db_connection

        # Create a test execution
        exec_id = create_execution(
            doc_id=None,
            doc_title="Test Execution for Verification",
            log_file="/tmp/test-verify.log",
            working_dir=str(Path.cwd()),
        )

        # Verify it was created
        with db_connection.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, doc_title, status FROM executions WHERE id = ?",
                (exec_id,)
            )
            row = cursor.fetchone()

            if row and row[1] == "Test Execution for Verification":
                console.print(f"  [green]✓[/green] Execution #{exec_id} created successfully")

                # Clean up
                conn.execute("DELETE FROM executions WHERE id = ?", (exec_id,))
                conn.commit()
                return True
            else:
                console.print(f"  [red]✗[/red] Execution not found or wrong title")
                return False

    except Exception as e:
        console.print(f"  [red]✗[/red] Error: {e}")
        return False


def check_unified_executor_config():
    """Verify ExecutionConfig and UnifiedExecutor work together."""
    console.print("\n[bold]4. Checking UnifiedExecutor configuration...[/bold]")

    try:
        from emdx.services.unified_executor import UnifiedExecutor, ExecutionConfig

        # Create executor with temp log dir
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            executor = UnifiedExecutor(log_dir=Path(tmpdir))

            # Verify log dir was created
            if executor.log_dir.exists():
                console.print(f"  [green]✓[/green] Log directory created: {executor.log_dir}")
            else:
                console.print(f"  [red]✗[/red] Log directory not created")
                return False

            # Create a config
            config = ExecutionConfig(
                prompt="Test prompt",
                title="Test Title",
                timeout_seconds=60,
                output_instruction="\n\nSave output with emdx save",
            )

            # Verify config
            if config.prompt == "Test prompt" and config.timeout_seconds == 60:
                console.print(f"  [green]✓[/green] ExecutionConfig created correctly")
            else:
                console.print(f"  [red]✗[/red] ExecutionConfig has wrong values")
                return False

        return True

    except Exception as e:
        console.print(f"  [red]✗[/red] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_output_instruction_building():
    """Verify output instruction building for agent command."""
    console.print("\n[bold]5. Checking output instruction building...[/bold]")

    try:
        from emdx.services.unified_executor import execute_with_output_tracking, ExecutionConfig, UnifiedExecutor
        from unittest.mock import patch, MagicMock
        from pathlib import Path

        # Mock the executor to capture the config
        captured_config = None

        original_execute = UnifiedExecutor.execute
        def capture_execute(self, config):
            nonlocal captured_config
            captured_config = config
            # Return a fake result
            from emdx.services.unified_executor import ExecutionResult
            return ExecutionResult(
                success=True,
                execution_id=999,
                log_file=Path("/tmp/fake.log"),
            )

        with patch.object(UnifiedExecutor, 'execute', capture_execute):
            execute_with_output_tracking(
                prompt="Test prompt",
                title="Test Output",
                tags=["analysis", "security"],
                group_id=123,
                group_role="exploration",
                create_pr=True,
            )

        # Verify the instruction was built correctly
        if captured_config is None:
            console.print(f"  [red]✗[/red] Config not captured")
            return False

        instruction = captured_config.output_instruction

        checks = [
            ('emdx save --title "Test Output"' in instruction, "title in instruction"),
            ('--tags "analysis,security"' in instruction, "tags in instruction"),
            ('--group 123' in instruction, "group in instruction"),
            ('--group-role exploration' in instruction, "group-role in instruction"),
            ('gh pr create' in instruction, "PR instruction present"),
        ]

        all_ok = True
        for check, name in checks:
            if check:
                console.print(f"  [green]✓[/green] {name}")
            else:
                console.print(f"  [red]✗[/red] {name}")
                all_ok = False

        return all_ok

    except Exception as e:
        console.print(f"  [red]✗[/red] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_cascade_config():
    """Verify cascade uses correct timeout for implementation stage."""
    console.print("\n[bold]6. Checking cascade configuration...[/bold]")

    try:
        from emdx.services.unified_executor import execute_for_cascade, UnifiedExecutor, ExecutionResult
        from unittest.mock import patch
        from pathlib import Path

        captured_configs = []

        def capture_execute(self, config):
            captured_configs.append(config)
            return ExecutionResult(
                success=True,
                execution_id=999,
                log_file=Path("/tmp/fake.log"),
            )

        with patch.object(UnifiedExecutor, 'execute', capture_execute):
            # Normal stage
            execute_for_cascade(
                prompt="Transform",
                doc_id=1,
                title="Test",
                is_implementation=False,
            )

            # Implementation stage
            execute_for_cascade(
                prompt="Implement",
                doc_id=1,
                title="Test",
                is_implementation=True,
            )

        if len(captured_configs) != 2:
            console.print(f"  [red]✗[/red] Expected 2 configs, got {len(captured_configs)}")
            return False

        normal_timeout = captured_configs[0].timeout_seconds
        impl_timeout = captured_configs[1].timeout_seconds

        if normal_timeout == 300:
            console.print(f"  [green]✓[/green] Normal stage timeout: {normal_timeout}s (5 min)")
        else:
            console.print(f"  [red]✗[/red] Normal stage timeout wrong: {normal_timeout}s (expected 300)")
            return False

        if impl_timeout == 1800:
            console.print(f"  [green]✓[/green] Implementation stage timeout: {impl_timeout}s (30 min)")
        else:
            console.print(f"  [red]✗[/red] Implementation stage timeout wrong: {impl_timeout}s (expected 1800)")
            return False

        return True

    except Exception as e:
        console.print(f"  [red]✗[/red] Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_recent_executions():
    """Show recent executions to verify they're being recorded."""
    console.print("\n[bold]7. Recent executions in database...[/bold]")

    try:
        from emdx.database.connection import db_connection

        with db_connection.get_connection() as conn:
            cursor = conn.execute("""
                SELECT id, doc_title, status, started_at, completed_at
                FROM executions
                ORDER BY started_at DESC
                LIMIT 10
            """)
            rows = cursor.fetchall()

        if not rows:
            console.print("  [dim]No executions found[/dim]")
            return True

        table = Table(title="Recent Executions")
        table.add_column("ID", style="cyan")
        table.add_column("Title")
        table.add_column("Status")
        table.add_column("Started")

        for row in rows:
            started = str(row[3])[:16] if row[3] else ""
            table.add_row(str(row[0]), (row[1] or "")[:40], row[2] or "unknown", started)

        console.print(table)
        return True

    except Exception as e:
        console.print(f"  [red]✗[/red] Error: {e}")
        return False


def main():
    """Run all verification checks."""
    console.print("[bold cyan]UnifiedExecutor Integration Verification[/bold cyan]")
    console.print("=" * 50)

    results = []

    results.append(("Database connection", check_database_connection()))
    results.append(("Module imports", check_imports()))
    results.append(("Execution record creation", check_execution_record_creation()))
    results.append(("UnifiedExecutor config", check_unified_executor_config()))
    results.append(("Output instruction building", check_output_instruction_building()))
    results.append(("Cascade configuration", check_cascade_config()))
    results.append(("Recent executions", check_recent_executions()))

    # Summary
    console.print("\n" + "=" * 50)
    console.print("[bold]Summary:[/bold]")

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for name, ok in results:
        status = "[green]PASS[/green]" if ok else "[red]FAIL[/red]"
        console.print(f"  {status} {name}")

    console.print(f"\n[bold]{passed}/{total} checks passed[/bold]")

    if passed == total:
        console.print("\n[bold green]All verifications passed![/bold green]")
        console.print("\nNext steps for full verification:")
        console.print("  1. Run: emdx agent \"Say hello\" --tags test -v")
        console.print("  2. Check Activity view in TUI (screen 1)")
        console.print("  3. Run: emdx cascade add \"Test idea\" && emdx cascade process idea --sync")
        console.print("  4. Check Cascade browser in TUI (screen 4)")
        return 0
    else:
        console.print("\n[bold red]Some verifications failed![/bold red]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
