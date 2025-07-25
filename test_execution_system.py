#!/usr/bin/env python3
"""Test script for EMDX execution system improvements."""

import subprocess
import time
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

def run_test(name: str, command: list, expected_success: bool = True) -> bool:
    """Run a test command and report results."""
    console.print(f"\n[bold cyan]Testing: {name}[/bold cyan]")
    console.print(f"[dim]Command: {' '.join(command)}[/dim]")
    
    try:
        result = subprocess.run(command, capture_output=True, text=True)
        success = (result.returncode == 0) == expected_success
        
        if success:
            console.print("[green]✅ PASSED[/green]")
        else:
            console.print("[red]❌ FAILED[/red]")
            console.print(f"[red]stdout: {result.stdout}[/red]")
            console.print(f"[red]stderr: {result.stderr}[/red]")
            
        return success
    except Exception as e:
        console.print(f"[red]❌ ERROR: {e}[/red]")
        return False

def main():
    """Run all tests."""
    console.print(Panel("[bold]EMDX Execution System Test Suite[/bold]", expand=False))
    
    # Track results
    tests = []
    
    # Test 1: Environment check
    tests.append((
        "Environment validation",
        run_test("Environment check", ["emdx", "claude", "check-env"])
    ))
    
    # Test 2: Branch cleanup (dry run)
    tests.append((
        "Branch cleanup (dry run)",
        run_test("Branch cleanup", ["emdx", "maintain", "cleanup", "--branches"])
    ))
    
    # Test 3: Process cleanup (dry run)
    tests.append((
        "Process cleanup (dry run)",
        run_test("Process cleanup", ["emdx", "maintain", "cleanup", "--processes"])
    ))
    
    # Test 4: Execution cleanup (dry run)
    tests.append((
        "Execution cleanup (dry run)",
        run_test("Execution cleanup", ["emdx", "maintain", "cleanup", "--executions"])
    ))
    
    # Test 5: Create test document
    console.print("\n[bold cyan]Creating test document...[/bold cyan]")
    test_content = "print('Hello from EMDX execution test!')"
    result = subprocess.run(
        ["echo", test_content],
        capture_output=True,
        text=True
    )
    
    save_result = subprocess.run(
        ["emdx", "save", "--title", "Execution Test Script"],
        input=result.stdout,
        capture_output=True,
        text=True
    )
    
    if save_result.returncode == 0:
        # Extract document ID
        output_lines = save_result.stdout.strip().split('\n')
        doc_id = None
        for line in output_lines:
            if "Document saved with ID" in line:
                doc_id = line.split()[-1]
                break
        
        if doc_id:
            console.print(f"[green]✅ Created test document: #{doc_id}[/green]")
            tests.append(("Document creation", True))
            
            # Test 6: Execute document (background)
            tests.append((
                "Document execution (background)",
                run_test(
                    "Execute in background",
                    ["emdx", "claude", "execute", doc_id, "--background", "--no-smart"]
                )
            ))
            
            # Wait a bit for execution to start
            time.sleep(2)
            
            # Test 7: List executions
            tests.append((
                "List executions",
                run_test("List executions", ["emdx", "exec", "list"])
            ))
            
            # Test 8: Show running executions
            tests.append((
                "Show running executions",
                run_test("Show running", ["emdx", "exec", "running"])
            ))
            
            # Test 9: Execution stats
            tests.append((
                "Execution statistics",
                run_test("Show stats", ["emdx", "exec", "stats"])
            ))
            
            # Test 10: Health check
            tests.append((
                "Execution health check",
                run_test("Health check", ["emdx", "exec", "health"])
            ))
            
            # Clean up test document
            subprocess.run(["emdx", "delete", doc_id], capture_output=True)
        else:
            tests.append(("Document creation", False))
    else:
        tests.append(("Document creation", False))
        console.print(f"[red]Failed to create test document: {save_result.stderr}[/red]")
    
    # Test 11: Directory cleanup
    tests.append((
        "Temp directory cleanup",
        run_test("Directory cleanup", ["emdx", "maintain", "cleanup-dirs"])
    ))
    
    # Summary
    console.print("\n" + "="*50)
    table = Table(title="Test Results Summary")
    table.add_column("Test", style="cyan")
    table.add_column("Result", style="bold")
    
    passed = 0
    for test_name, result in tests:
        table.add_row(
            test_name,
            "[green]PASSED[/green]" if result else "[red]FAILED[/red]"
        )
        if result:
            passed += 1
    
    console.print(table)
    
    total = len(tests)
    console.print(f"\n[bold]Total: {passed}/{total} tests passed ({passed/total*100:.0f}%)[/bold]")
    
    if passed == total:
        console.print("[bold green]✅ All tests passed![/bold green]")
        return 0
    else:
        console.print(f"[bold red]❌ {total - passed} tests failed[/bold red]")
        return 1

if __name__ == "__main__":
    sys.exit(main())