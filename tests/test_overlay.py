#!/usr/bin/env python3
"""
Test script to verify the refactored overlay architecture.
"""

import sys
from emdx.ui.agent_execution_overlay import AgentExecutionOverlay, StageType

def test_simplified_data_storage():
    """Test that data dict works correctly."""
    print("Testing simplified data storage...")

    overlay = AgentExecutionOverlay(initial_document_id=42)

    # Verify initial state
    assert overlay.data['document_id'] == 42
    assert overlay.data['agent_id'] is None
    assert overlay.data['config'] == {}

    # Test set methods
    overlay.set_agent_selection(7)
    assert overlay.data['agent_id'] == 7

    overlay.set_project_selection(0, "/path/to/project", [])
    assert overlay.data['project_path'] == "/path/to/project"
    assert overlay.data['project_worktrees'] == []

    overlay.set_worktree_selection(3)
    assert overlay.data['worktree_index'] == 3

    overlay.set_execution_config({"background": True})
    assert overlay.data['config']['background'] == True

    # Test get_selection_summary
    summary = overlay.get_selection_summary()
    assert summary['document_id'] == 42
    assert summary['agent_id'] == 7
    assert summary['worktree_index'] == 3
    assert 'current_stage' in summary

    print("✅ Simplified data storage tests passed!")

def test_stage_setup():
    """Test that stage enum and setup is correct."""
    print("\nTesting stage setup...")

    overlay = AgentExecutionOverlay()

    # Verify stages list
    assert len(overlay.stages) == 5
    assert StageType.DOCUMENT in overlay.stages
    assert StageType.AGENT in overlay.stages
    assert StageType.PROJECT in overlay.stages
    assert StageType.WORKTREE in overlay.stages
    assert StageType.CONFIG in overlay.stages

    # Verify stage navigation
    assert overlay.get_current_stage() == StageType.DOCUMENT
    overlay.current_stage_index = 1
    assert overlay.get_current_stage() == StageType.AGENT

    print("✅ Stage setup tests passed!")

def test_stage_completed_tracking():
    """Test that stage completion is tracked correctly."""
    print("\nTesting stage completion tracking...")

    overlay = AgentExecutionOverlay()

    # Initially all stages should be incomplete
    assert not overlay.stage_completed[StageType.DOCUMENT]
    assert not overlay.stage_completed[StageType.AGENT]

    # Marking stages complete should work
    overlay.set_document_selection(1)
    assert overlay.stage_completed[StageType.DOCUMENT]

    overlay.set_agent_selection(2)
    assert overlay.stage_completed[StageType.AGENT]

    print("✅ Stage completion tracking tests passed!")

def main():
    """Run all tests."""
    print("=" * 60)
    print("REFACTORED OVERLAY ARCHITECTURE TEST SUITE")
    print("=" * 60)

    tests = [
        test_simplified_data_storage,
        test_stage_setup,
        test_stage_completed_tracking,
    ]

    failed = 0
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 60)
    if failed == 0:
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        return 0
    else:
        print(f"❌ {failed} test(s) failed")
        print("=" * 60)
        return 1

if __name__ == "__main__":
    sys.exit(main())
