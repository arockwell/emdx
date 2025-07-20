#!/usr/bin/env python3
"""Manual testing script for auto-tagger functionality."""

import sys
sys.path.insert(0, '.')

from emdx.services.auto_tagger import AutoTagger

def test_basic_patterns():
    """Test basic pattern matching."""
    tagger = AutoTagger()
    
    test_cases = [
        ("Gameplan: Implement new feature", "## Goals\n- Build feature\n## Success Criteria\n- Tests pass"),
        ("Bug: Login fails", "Error: TypeError when clicking login button"),
        ("Test: Authentication tests", "def test_login():\n    assert user.is_authenticated"),
        ("Feature: Add dark mode", "Implement theme switching functionality"),
        ("Urgent: Fix payment system", "Critical error in payment processing")
    ]
    
    for title, content in test_cases:
        print(f"\n{'='*60}")
        print(f"Title: {title}")
        print(f"Content: {content[:50]}...")
        print("-" * 60)
        
        suggestions = tagger.analyze_document(title, content)
        
        if suggestions:
            print("Suggested tags:")
            for tag, confidence in suggestions:
                print(f"  • {tag} ({confidence:.0%})")
        else:
            print("No tags suggested")

def test_custom_patterns():
    """Test adding custom patterns."""
    tagger = AutoTagger()
    
    # Add custom pattern
    tagger.add_custom_pattern(
        "standup",
        title_patterns=[r"standup:", r"daily standup"],
        content_patterns=[r"yesterday:", r"today:", r"blockers:"],
        tags=["meeting", "standup"],
        confidence=0.9
    )
    
    title = "Standup: 2024-01-15"
    content = "Yesterday: Fixed bug\nToday: Working on feature\nBlockers: None"
    
    print(f"\n{'='*60}")
    print("Testing custom pattern:")
    print(f"Title: {title}")
    
    suggestions = tagger.analyze_document(title, content)
    print("\nSuggested tags:")
    for tag, confidence in suggestions:
        print(f"  • {tag} ({confidence:.0%})")

if __name__ == "__main__":
    print("Testing AutoTagger patterns...\n")
    
    try:
        test_basic_patterns()
        test_custom_patterns()
        print("\n✅ All manual tests passed!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()