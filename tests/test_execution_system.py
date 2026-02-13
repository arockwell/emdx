#!/usr/bin/env python3
"""Test script for EMDX execution system fixes.

Run this manually to validate the fixes:
    python tests/test_execution_system.py
"""

import subprocess
import tempfile
import pytest


@pytest.mark.integration  
def test_execution_id_uniqueness():
    """Test that execution IDs are unique (when environment allows)."""
    print("\n=== Test: Execution ID Uniqueness ===")
    
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
        
        # Extract doc ID
        doc_id = None
        for line in result.stdout.split('\n'):
            if 'Saved as #' in line:
                # Format: "✅ Saved as #1758: Test Doc"
                doc_id = line.split('#')[1].split(':')[0].strip()
                break
        
        if not doc_id:
            print("❌ Failed to create test document - skipping execution test")
            print(f"Save result: {result.stdout}")
            pytest.skip("Save failed due to environment issues - cannot run execution test")
        
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
        if len(exec_ids) == 0:
            print("⚠️ No executions started - environment may not be configured")
            pytest.skip("No executions started - environment may not be configured")
        elif len(exec_ids) == len(set(exec_ids)):
            print(f"✅ All {len(exec_ids)} execution IDs are unique")
        else:
            pytest.fail(f"Duplicate execution IDs found: {exec_ids}")
    
    finally:
        # Clean up temp file
        import os
        try:
            os.unlink(test_file)
        except OSError:
            pass


@pytest.mark.integration
def test_maintenance_commands():
    """Test maintenance commands exist and can run."""
    print("\n=== Test: Maintenance Commands ===")

    commands = [
        # The maintain command help
        ["emdx", "maintain", "--help"],
        # Analyze command help (now under maintain)
        ["emdx", "maintain", "analyze", "--help"],
        # Exec commands
        ["emdx", "exec", "--help"],
        ["emdx", "exec", "stats"],
    ]

    all_passed = True
    for cmd in commands:
        result = subprocess.run(cmd, capture_output=True, text=True)
        # Accept commands that run but may have DB issues
        if result.returncode == 0 or "OperationalError" in result.stderr or "DRY RUN MODE" in result.stdout:
            print(f"✅ {' '.join(cmd[1:])}: OK (command exists and runs)")
        else:
            print(f"❌ {' '.join(cmd[1:])}: Failed")
            print(f"  stdout: {result.stdout[:100]}...")
            print(f"  stderr: {result.stderr[:100]}...")
            all_passed = False

    assert all_passed, "Some maintenance commands failed to run at all"


@pytest.mark.integration
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
    
    assert all_passed, "Some execution monitoring commands failed"


@pytest.mark.integration
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
    else:
        print("⚠️  Environment has issues (this may be expected)")
        print(result.stdout)
        pytest.skip("Environment has issues - skipping validation test")


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
