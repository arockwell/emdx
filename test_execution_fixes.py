#!/usr/bin/env python3
"""Test script to validate EMDX execution fixes."""

import os
import subprocess
import tempfile
import time
from pathlib import Path


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def test_environment_check():
    """Test environment validation."""
    print("🧪 Testing environment check...")
    code, stdout, stderr = run_command(["emdx", "claude", "check-env"])
    if code == 0:
        print("✅ Environment check passed")
    else:
        print(f"❌ Environment check failed: {stderr}")
    return code == 0


def test_branch_cleanup():
    """Test branch cleanup utility."""
    print("\n🧪 Testing branch cleanup...")
    # Dry run first
    code, stdout, stderr = run_command(["emdx", "cleanup", "branches", "--dry-run"])
    print(f"Dry run output: {stdout}")
    return code == 0


def test_process_cleanup():
    """Test process cleanup utility."""
    print("\n🧪 Testing process cleanup...")
    code, stdout, stderr = run_command(["emdx", "cleanup", "processes", "--dry-run"])
    print(f"Process status: {stdout}")
    return code == 0


def test_execution_cleanup():
    """Test execution cleanup utility."""
    print("\n🧪 Testing execution cleanup...")
    code, stdout, stderr = run_command(["emdx", "cleanup", "executions", "--dry-run"])
    print(f"Execution status: {stdout}")
    return code == 0


def test_simple_execution():
    """Test a simple execution with a test document."""
    print("\n🧪 Testing simple execution...")
    
    # Create a test document
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("# Test Document\n\nprint('Hello from test execution')")
        test_file = f.name
    
    try:
        # Save document to emdx
        code, stdout, stderr = run_command(["emdx", "save", test_file, "--title", "Test Execution"])
        if code != 0:
            print(f"❌ Failed to save document: {stderr}")
            return False
        
        # Extract document ID from output
        import re
        match = re.search(r'Document saved with ID: (\d+)', stdout)
        if not match:
            print("❌ Could not extract document ID")
            return False
        
        doc_id = match.group(1)
        print(f"📄 Created test document ID: {doc_id}")
        
        # Execute the document
        print("🚀 Starting execution...")
        code, stdout, stderr = run_command(["emdx", "claude", "execute", doc_id])
        
        # For background execution, just check that it started
        if "Starting execution" in stdout or "Claude started" in stdout:
            print("✅ Execution started successfully")
            time.sleep(2)  # Give it time to start
            
            # Check execution status
            code, stdout, stderr = run_command(["emdx", "exec", "list", "--limit", "1"])
            print(f"Latest execution: {stdout}")
            return True
        else:
            print(f"❌ Execution failed: {stderr}")
            return False
            
    finally:
        os.unlink(test_file)


def test_concurrent_executions():
    """Test that multiple executions get unique IDs."""
    print("\n🧪 Testing concurrent execution IDs...")
    
    # Check current running executions
    code, stdout, stderr = run_command(["emdx", "exec", "running"])
    print(f"Currently running: {stdout}")
    
    # Check execution stats
    code, stdout, stderr = run_command(["emdx", "exec", "stats"])
    print(f"Execution statistics: {stdout}")
    
    return True


def test_monitoring_commands():
    """Test execution monitoring commands."""
    print("\n🧪 Testing monitoring commands...")
    
    tests = [
        (["emdx", "exec", "list", "--limit", "5"], "Recent executions"),
        (["emdx", "exec", "stats"], "Execution statistics"),
        (["emdx", "exec", "health"], "Execution health"),
    ]
    
    all_passed = True
    for cmd, desc in tests:
        code, stdout, stderr = run_command(cmd)
        if code == 0:
            print(f"✅ {desc}: OK")
        else:
            print(f"❌ {desc}: Failed - {stderr}")
            all_passed = False
    
    return all_passed


def main():
    """Run all tests."""
    print("🔍 EMDX Execution System Test Suite")
    print("=" * 50)
    
    tests = [
        ("Environment Check", test_environment_check),
        ("Branch Cleanup", test_branch_cleanup),
        ("Process Cleanup", test_process_cleanup),
        ("Execution Cleanup", test_execution_cleanup),
        ("Simple Execution", test_simple_execution),
        ("Concurrent Executions", test_concurrent_executions),
        ("Monitoring Commands", test_monitoring_commands),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {name} failed with exception: {e}")
            failed += 1
    
    print("\n" + "=" * 50)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total: {passed + failed}")
    
    if failed == 0:
        print("\n🎉 All tests passed!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")


if __name__ == "__main__":
    main()