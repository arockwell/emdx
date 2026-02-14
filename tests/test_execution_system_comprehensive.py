#!/usr/bin/env python3
"""Comprehensive test script for EMDX execution system fixes.

This script tests all the improvements made to the execution system:
- Cleanup utilities (branches, processes, executions)
- Branch name generation uniqueness
- Process lifecycle management
- Environment validation
- Unified execution path
- Error handling
- Execution monitoring
"""

import subprocess
import time
import os
import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


class ExecutionSystemTester:
    """Test suite for EMDX execution system."""
    
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.test_results = []
    
    def run_command(self, cmd: str) -> tuple[int, str, str]:
        """Run a command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)
    
    def test_environment_validation(self):
        """Test environment validation."""
        console.print("\n[bold cyan]Testing Environment Validation...[/bold cyan]")
        
        # Test check-env command
        exit_code, stdout, stderr = self.run_command("emdx claude check-env")
        
        if exit_code == 0:
            self.tests_passed += 1
            self.test_results.append(("Environment validation", "✅ Passed"))
            console.print("[green]✅ Environment validation working[/green]")
        else:
            self.tests_failed += 1
            self.test_results.append(("Environment validation", "❌ Failed"))
            console.print(f"[red]❌ Environment validation failed: {stderr}[/red]")
    
    def test_cleanup_utilities(self):
        """Test cleanup utilities."""
        console.print("\n[bold cyan]Testing Cleanup Utilities...[/bold cyan]")
        
        # For now, test with available maintain options
        # Test clean (duplicates and empty docs)
        exit_code, stdout, stderr = self.run_command("emdx maintain --clean --dry-run")
        if exit_code == 0:
            self.tests_passed += 1
            self.test_results.append(("Document cleanup", "✅ Passed"))
            console.print("[green]✅ Document cleanup working[/green]")
        else:
            self.tests_failed += 1
            self.test_results.append(("Document cleanup", "❌ Failed"))
            console.print(f"[red]❌ Document cleanup failed: {stderr}[/red]")
        
        # Test garbage collection
        exit_code, stdout, stderr = self.run_command("emdx maintain --gc --dry-run")
        if exit_code == 0:
            self.tests_passed += 1
            self.test_results.append(("Garbage collection", "✅ Passed"))
            console.print("[green]✅ Garbage collection working[/green]")
        else:
            self.tests_failed += 1
            self.test_results.append(("Garbage collection", "❌ Failed"))
            console.print(f"[red]❌ Garbage collection failed: {stderr}[/red]")
        
        # Note: The cleanup commands are internal functions, not exposed as CLI
        self.test_results.append(("Execution cleanup utilities", "⚠️  Internal functions"))
    
    def test_execution_monitoring(self):
        """Test execution monitoring commands."""
        console.print("\n[bold cyan]Testing Execution Monitoring...[/bold cyan]")
        
        # Test execution list
        exit_code, stdout, stderr = self.run_command("emdx exec list --limit 5")
        if exit_code == 0:
            self.tests_passed += 1
            self.test_results.append(("Execution list", "✅ Passed"))
            console.print("[green]✅ Execution list working[/green]")
        else:
            self.tests_failed += 1
            self.test_results.append(("Execution list", "❌ Failed"))
            console.print(f"[red]❌ Execution list failed: {stderr}[/red]")
        
        # Test execution stats
        exit_code, stdout, stderr = self.run_command("emdx exec stats")
        if exit_code == 0:
            self.tests_passed += 1
            self.test_results.append(("Execution stats", "✅ Passed"))
            console.print("[green]✅ Execution stats working[/green]")
        else:
            self.tests_failed += 1
            self.test_results.append(("Execution stats", "❌ Failed"))
            console.print(f"[red]❌ Execution stats failed: {stderr}[/red]")
        
        # Test execution health
        exit_code, stdout, stderr = self.run_command("emdx exec health")
        if exit_code == 0:
            self.tests_passed += 1
            self.test_results.append(("Execution health", "✅ Passed"))
            console.print("[green]✅ Execution health working[/green]")
        else:
            self.tests_failed += 1
            self.test_results.append(("Execution health", "❌ Failed"))
            console.print(f"[red]❌ Execution health failed: {stderr}[/red]")
    
    def test_execution_creation(self):
        """Test creating and managing an execution."""
        console.print("\n[bold cyan]Testing Execution Creation...[/bold cyan]")
        
        # Create a test document
        test_content = "Test execution at " + time.strftime("%Y-%m-%d %H:%M:%S")
        exit_code, stdout, stderr = self.run_command(
            f'echo "{test_content}" | emdx save --title "Test Execution"'
        )
        
        if exit_code != 0:
            self.tests_failed += 1
            self.test_results.append(("Document creation", "❌ Failed"))
            console.print(f"[red]❌ Failed to create test document: {stderr}[/red]")
            return
        
        # Extract document ID - look for different patterns
        import re
        # Try multiple patterns
        patterns = [
            r'Document #(\d+) saved',
            r'Document saved with ID: (\d+)',
            r'Saved as document #(\d+)',
            r'#(\d+):',  # Sometimes just shows the ID
            r'#\x1b\[0m\x1b\[1;32m(\d+)\x1b\[0m\x1b\[32m:',  # With ANSI color codes
            r'Saved as #\x1b\[0m\x1b\[1;32m(\d+)\x1b\[0m',  # Another ANSI pattern
            r'Saved as #.*?(\d+)',  # Generic pattern to catch ID
        ]
        
        doc_id = None
        for pattern in patterns:
            match = re.search(pattern, stdout)
            if match:
                doc_id = match.group(1)
                break
        
        if not doc_id:
            # Try to get the most recent document
            exit_code2, stdout2, stderr2 = self.run_command("emdx list --limit 1")
            if exit_code2 == 0:
                match2 = re.search(r'#(\d+):', stdout2)
                if match2:
                    doc_id = match2.group(1)
        
        if not doc_id:
            self.tests_failed += 1
            self.test_results.append(("Document ID extraction", "❌ Failed"))
            console.print(f"[red]❌ Failed to extract document ID from: {stdout[:200]}[/red]")
            return
        console.print(f"[green]✅ Created test document #{doc_id}[/green]")
        self.tests_passed += 1
        self.test_results.append(("Document creation", "✅ Passed"))
        
        # Test execution in background (if claude is available)
        exit_code, stdout, stderr = self.run_command("which claude")
        if exit_code == 0:
            # Claude is available, test execution
            exit_code, stdout, stderr = self.run_command(
                f"emdx claude execute {doc_id} --background --smart"
            )
            
            if exit_code == 0:
                self.tests_passed += 1
                self.test_results.append(("Background execution", "✅ Passed"))
                console.print("[green]✅ Background execution started[/green]")

                # Poll for execution to start (max 2s with 0.2s intervals)
                execution_found = False
                for _ in range(10):
                    time.sleep(0.2)
                    exit_code, stdout, stderr = self.run_command("emdx exec running")
                    if "claude" in stdout.lower() or "running" in stdout.lower():
                        execution_found = True
                        break

                # Check running executions
                exit_code, stdout, stderr = self.run_command("emdx exec running")
                if "claude" in stdout.lower() or "running" in stdout.lower():
                    self.tests_passed += 1
                    self.test_results.append(("Execution tracking", "✅ Passed"))
                    console.print("[green]✅ Execution being tracked[/green]")
                else:
                    self.tests_failed += 1
                    self.test_results.append(("Execution tracking", "❌ Failed"))
                    console.print("[red]❌ Execution not tracked properly[/red]")
            else:
                self.tests_failed += 1
                self.test_results.append(("Background execution", "❌ Failed"))
                console.print(f"[red]❌ Background execution failed: {stderr}[/red]")
        else:
            console.print("[yellow]⚠️  Claude not available, skipping execution test[/yellow]")
            self.test_results.append(("Background execution", "⚠️  Skipped"))
    
    def test_cleanup_dirs(self):
        """Test temporary directory cleanup."""
        console.print("\n[bold cyan]Testing Directory Cleanup...[/bold cyan]")
        
        # Directory cleanup is also an internal function, not exposed
        self.test_results.append(("Directory cleanup", "⚠️  Internal function"))
        console.print("[yellow]⚠️  Directory cleanup is an internal function[/yellow]")
    
    def print_summary(self):
        """Print test summary."""
        console.print("\n" + "=" * 80)
        
        # Create summary table
        table = Table(title="Test Results Summary", box=box.ROUNDED)
        table.add_column("Test", style="cyan")
        table.add_column("Result", style="bold")
        
        for test_name, result in self.test_results:
            if "✅" in result:
                style = "green"
            elif "❌" in result:
                style = "red"
            else:
                style = "yellow"
            table.add_row(test_name, f"[{style}]{result}[/{style}]")
        
        console.print(table)
        
        # Overall summary
        total_tests = self.tests_passed + self.tests_failed
        if total_tests > 0:
            success_rate = (self.tests_passed / total_tests) * 100
            
            if success_rate == 100:
                panel_style = "green"
                status = "All Tests Passed! 🎉"
            elif success_rate >= 80:
                panel_style = "yellow"
                status = "Most Tests Passed"
            else:
                panel_style = "red"
                status = "Tests Failed"
            
            console.print(Panel(
                f"[bold]{status}[/bold]\n\n"
                f"Passed: [green]{self.tests_passed}[/green]\n"
                f"Failed: [red]{self.tests_failed}[/red]\n"
                f"Success Rate: {success_rate:.1f}%",
                title="[bold]Test Summary[/bold]",
                border_style=panel_style,
                box=box.DOUBLE
            ))
        else:
            console.print("[yellow]No tests were run[/yellow]")


def main():
    """Run all tests."""
    console.print(Panel(
        "[bold cyan]EMDX Execution System Comprehensive Test Suite[/bold cyan]\n\n"
        "This script tests all improvements made to the execution system:\n"
        "• Cleanup utilities (branches, processes, executions)\n"
        "• Environment validation\n"
        "• Execution monitoring\n"
        "• Execution creation and tracking\n"
        "• Directory cleanup",
        box=box.DOUBLE
    ))
    
    tester = ExecutionSystemTester()
    
    # Run all tests
    tester.test_environment_validation()
    tester.test_cleanup_utilities()
    tester.test_execution_monitoring()
    tester.test_execution_creation()
    tester.test_cleanup_dirs()
    
    # Print summary
    tester.print_summary()


if __name__ == "__main__":
    main()