#!/usr/bin/env python3
"""Format verification tests for EMDX documents"""

import subprocess
import json
import sys


def test_document_retrieval(doc_id):
    """Test retrieving and verifying document content"""
    print(f"\n=== Testing Document #{doc_id} ===")
    
    # Get raw document content using emdx CLI
    result = subprocess.run(
        ["emdx", "view", str(doc_id), "--raw"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        # Try without --raw flag
        result = subprocess.run(
            ["emdx", "view", str(doc_id)],
            capture_output=True,
            text=True
        )
    
    content = result.stdout
    
    # Check various formatting elements
    tests = {
        "Bold text": "**bold text**" in content or "bold text" in content,
        "Italic text": "*italic text*" in content or "italic text" in content,
        "Code blocks": "```python" in content or "def test_formatting():" in content,
        "Unicode Chinese": "你好" in content,
        "Unicode Japanese": "こんにちは" in content,
        "Emojis": "🎯" in content and "🚀" in content,
        "Special chars": "<>&" in content,
        "Tables": "| Feature |" in content,
        "Lists": "- First item" in content or "• First item" in content,
        "Headers": "## Basic Text Formatting" in content or "Basic Text Formatting" in content,
    }
    
    print("\nFormatting preservation tests:")
    all_passed = True
    for test_name, passed in tests.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    return all_passed


def test_cli_rendering():
    """Test how documents render in CLI view"""
    print("\n=== Testing CLI Rendering ===")
    
    # Test viewing document 935 (complex formatting)
    result = subprocess.run(
        ["emdx", "view", "935"],
        capture_output=True,
        text=True
    )
    
    if result.returncode == 0:
        print("✅ Document renders successfully in CLI")
        
        # Check for specific rendering features
        output = result.stdout
        checks = {
            "Headers rendered": "Basic Text Formatting" in output,
            "Lists formatted": "• First item" in output or "- First item" in output,
            "Code blocks shown": "def test_formatting():" in output,
            "Unicode preserved": "你好" in output,
            "Emojis displayed": "🎯" in output,
        }
        
        print("\nRendering checks:")
        for check, passed in checks.items():
            status = "✅" if passed else "❌"
            print(f"  {status} {check}")
    else:
        print("❌ Failed to render document")
        print(f"Error: {result.stderr}")


def test_search_functionality():
    """Test searching for formatted content"""
    print("\n=== Testing Search with Formatted Content ===")
    
    # Search for various content types
    searches = [
        ("formatting test", "Basic search"),
        ("你好", "Unicode search"),
        ("🎯", "Emoji search"),
        ("test_formatting", "Code search"),
    ]
    
    for query, description in searches:
        result = subprocess.run(
            ["emdx", "find", query],
            capture_output=True,
            text=True
        )
        
        if "EMDX Formatting Test Document" in result.stdout or "#935" in result.stdout:
            print(f"✅ {description}: Found document")
        else:
            print(f"❌ {description}: Document not found")


def main():
    """Run all format verification tests"""
    print("EMDX Format Verification Tests")
    print("=" * 50)
    
    # Test document IDs
    test_docs = [935, 936]  # Complex and simple test documents
    
    # Run retrieval tests
    for doc_id in test_docs:
        test_document_retrieval(doc_id)
    
    # Test CLI rendering
    test_cli_rendering()
    
    # Test search
    test_search_functionality()
    
    print("\n" + "=" * 50)
    print("Format verification complete!")


if __name__ == "__main__":
    main()