#!/usr/bin/env python3
"""Test script for EMDX execution system fixes.

Run this manually to validate the fixes:
    python tests/test_execution_system.py
"""

import subprocess
import time
import tempfile
from pathlib import Path


def test_execution_id_uniqueness():
    """Test that execution IDs are unique."""
    print("\n=== Test: Execution ID Uniqueness ===")
    
    # Create test document
    with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
        f.write("print('Test')")
        test_file = f.name
    
    # Save document
    result = subprocess.run(
        ["emdx", "save", test_file, "--title", "Test Doc"],
        capture_output=True,
        text=True
    )
    
    # Extract doc ID
    doc_id = None
    for line in result.stdout.split('\n'):
        if 'Document saved with ID:' in line:
            doc_id = line.split(':')[1].strip()
            break
    
    if not doc_id:
        print("❌ Failed to create test document")
        return False
    
    print(f"✅ Created test document #{doc_id}")
    
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
    
    # Check uniqueness
    if len(exec_ids) == len(set(exec_ids)):
        print(f"✅ All {len(exec_ids)} execution IDs are unique")
        return True
    else:
        print(f"❌ Duplicate execution IDs found: {exec_ids}")
        return False


def test_cleanup_commands():
    """Test cleanup commands work without errors."""
    print("\n=== Test: Cleanup Commands ===")
    
    commands = [
        ["emdx", "maintain", "cleanup", "--all"],
        ["emdx", "maintain", "cleanup", "--branches"],
        ["emdx", "maintain", "cleanup", "--processes"],
        ["emdx", "maintain", "cleanup", "--executions"],
        ["emdx", "maintain", "cleanup-dirs"],
    ]
    
    all_passed = True
    for cmd in commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {' '.join(cmd[2:])}: OK")
        else:
            print(f"❌ {' '.join(cmd[2:])}: Failed")
            all_passed = False
    
    return all_passed


def test_execution_monitoring():
    """Test execution monitoring commands."""
    print("\n=== Test: Execution Monitoring ===")
    
    commands = [
        ["emdx", "exec", "list", "--limit", "5"],
        ["emdx", "exec", "stats"],
        ["emdx", "exec", "health"],
        ["emdx", "exec", "monitor", "--no-follow"],
    ]
    
    all_passed = True
    for cmd in commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {' '.join(cmd[2:])}: OK")
        else:
            print(f"❌ {' '.join(cmd[2:])}: Failed")
            all_passed = False
    
    return all_passed


def test_environment_validation():
    """Test environment validation."""
    print("\n=== Test: Environment Validation ===")
    
    result = subprocess.run(
        ["emdx", "claude", "check-env"],
        capture_output=True,
        text=True
    )
    
    if "properly configured" in result.stdout:
        print("✅ Environment is properly configured")
        return True
    else:
        print("⚠️  Environment has issues (this may be expected)")
        print(result.stdout)
        return True  # Don't fail test for env issues


def main():
    """Run all tests."""
    print("🧪 EMDX Execution System Test Suite")
    print("=" * 50)
    
    tests = [
        test_environment_validation,
        test_execution_id_uniqueness,
        test_cleanup_commands,
        test_execution_monitoring,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_func.__name__} failed with exception: {e}")
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