#!/usr/bin/env python3
"""Example demonstrating how to integrate emoji_aliases with EMDX tagging system.

This example shows how to use the emoji_aliases module to enhance tag input
processing in the EMDX command-line interface.
"""

from typing import List
import sys
import os

# Add the parent directory to the path to import emdx modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from emdx.emoji_aliases import (
    expand_aliases,
    normalize_tags,
    suggest_aliases,
    is_valid_tag,
    print_alias_summary,
    get_aliases_for_emoji,
)


def enhanced_tag_input(user_input: str) -> List[str]:
    """Enhanced tag input processing with alias support.
    
    This function demonstrates how to integrate emoji aliases into tag input
    processing for EMDX commands.
    
    Args:
        user_input: Space or comma-separated tag input from user
        
    Returns:
        List of normalized emoji tags
    """
    # Parse user input (handle both space and comma separation)
    raw_tags = []
    for part in user_input.replace(',', ' ').split():
        if part.strip():
            raw_tags.append(part.strip())
    
    # Expand aliases to emojis
    normalized_tags = normalize_tags(raw_tags)
    
    return normalized_tags


def interactive_tag_suggestion(partial_input: str) -> None:
    """Interactive tag suggestion based on partial input.
    
    This demonstrates how to provide auto-completion/suggestions
    for users typing tag aliases.
    """
    suggestions = suggest_aliases(partial_input, limit=10)
    
    if suggestions:
        print(f"\nSuggestions for '{partial_input}':")
        for alias, emoji in suggestions:
            print(f"  {alias} → {emoji}")
    else:
        print(f"No suggestions found for '{partial_input}'")


def validate_user_tags(tags: List[str]) -> tuple[List[str], List[str]]:
    """Validate user-provided tags and separate valid from invalid.
    
    Args:
        tags: List of user-provided tags (mix of aliases, emojis, and custom)
        
    Returns:
        Tuple of (valid_emoji_tags, custom_tags)
    """
    valid_emoji_tags = []
    custom_tags = []
    
    for tag in tags:
        if is_valid_tag(tag):
            # This is a valid emoji or alias - expand it
            expanded = normalize_tags([tag])
            valid_emoji_tags.extend(expanded)
        else:
            # This is a custom tag - preserve it
            custom_tags.append(tag)
    
    return valid_emoji_tags, custom_tags


def demonstrate_tag_workflows():
    """Demonstrate various tag workflow scenarios."""
    print("=== EMDX Emoji Aliases Integration Examples ===\n")
    
    # 1. Basic alias expansion
    print("1. Basic alias expansion:")
    user_inputs = [
        "gameplan active",
        "bug, urgent, test",
        "docs refactor done success",
        "custom-tag gameplan unknown-alias bug"
    ]
    
    for user_input in user_inputs:
        expanded = enhanced_tag_input(user_input)
        print(f"  Input: '{user_input}'")
        print(f"  Output: {expanded}")
        print()
    
    # 2. Tag validation and separation
    print("2. Tag validation and separation:")
    mixed_tags = ["gameplan", "🚀", "my-custom-tag", "bug", "project-specific"]
    emoji_tags, custom_tags = validate_user_tags(mixed_tags)
    print(f"  Input tags: {mixed_tags}")
    print(f"  Emoji tags: {emoji_tags}")
    print(f"  Custom tags: {custom_tags}")
    print()
    
    # 3. Interactive suggestions
    print("3. Interactive tag suggestions:")
    partials = ["gam", "ref", "act", "ur"]
    for partial in partials:
        interactive_tag_suggestion(partial)
    
    print()
    
    # 4. Reverse lookup (emoji to aliases)
    print("4. Emoji to aliases lookup:")
    emojis = ["🎯", "🚀", "🐛", "✨"]
    for emoji in emojis:
        aliases = get_aliases_for_emoji(emoji)
        print(f"  {emoji} → {', '.join(aliases)}")
    
    print()


def simulate_emdx_save_command(title: str, tags_input: str) -> None:
    """Simulate how emoji aliases would work in 'emdx save' command.
    
    This shows the practical integration into the EMDX save workflow.
    """
    print(f"Simulating: emdx save --title '{title}' --tags '{tags_input}'")
    
    # Process tag input
    processed_tags = enhanced_tag_input(tags_input)
    emoji_tags, custom_tags = validate_user_tags(processed_tags)
    
    all_tags = emoji_tags + custom_tags
    
    print(f"  Processed tags: {all_tags}")
    print(f"  Emoji tags: {emoji_tags}")
    print(f"  Custom tags: {custom_tags}")
    
    # Here you would call the actual save function:
    # db.save_document(title, content, project, tags=all_tags)
    
    print("  → Document would be saved with processed tags\n")


def main():
    """Main demonstration function."""
    
    # Show all available aliases
    print_alias_summary()
    print("\n" + "="*60 + "\n")
    
    # Demonstrate workflows
    demonstrate_tag_workflows()
    
    print("5. Simulated EMDX command integration:")
    # Simulate various save commands
    test_cases = [
        ("Authentication Gameplan", "gameplan active urgent"),
        ("Bug Fix Analysis", "bug analysis done success"),
        ("Code Review Notes", "notes refactor code-quality"),
        ("Project Status", "project-management active custom-milestone"),
    ]
    
    for title, tags in test_cases:
        simulate_emdx_save_command(title, tags)


if __name__ == "__main__":
    main()