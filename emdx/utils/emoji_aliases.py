"""
Emoji alias system for EMDX tags.

This module provides a mapping from text aliases to emoji tags for easier input
while maintaining the space-efficient emoji tag system in the GUI.
"""

from typing import Dict, List, Set

# Emoji alias mappings - text -> emoji
EMOJI_ALIASES: Dict[str, str] = {
    # Document Types
    "gameplan": "🎯",
    "plan": "🎯",
    "strategy": "🎯",
    "goal": "🎯",

    "analysis": "🔍",
    "investigate": "🔍",
    "research": "🔍",
    "explore": "🔍",

    "notes": "📝",
    "note": "📝",
    "memo": "📝",
    "thoughts": "📝",

    "docs": "📚",
    "documentation": "📚",
    "readme": "📚",
    "guide": "📚",

    "architecture": "🏗️",
    "arch": "🏗️",
    "design": "🏗️",
    "structure": "🏗️",

    # Workflow Status
    "active": "🚀",
    "current": "🚀",
    "working": "🚀",
    "wip": "🚀",

    "done": "✅",
    "complete": "✅",
    "finished": "✅",
    "completed": "✅",

    "blocked": "🚧",
    "stuck": "🚧",
    "waiting": "🚧",
    "pending": "🚧",

    # Outcomes (Success Tracking)
    "success": "🎉",
    "works": "🎉",
    "good": "🎉",

    "failed": "❌",
    "broken": "❌",
    "error": "❌",
    "bad": "❌",

    "partial": "⚡",
    "mixed": "⚡",
    "halfway": "⚡",
    "some": "⚡",

    # Technical Work
    "refactor": "🔧",
    "refactoring": "🔧",
    "cleanup": "🔧",
    "improve": "🔧",

    "test": "🧪",
    "testing": "🧪",
    "tests": "🧪",
    "qa": "🧪",

    "bug": "🐛",
    "fix": "🐛",
    "issue": "🐛",
    "problem": "🐛",

    "feature": "✨",
    "new": "✨",
    "add": "✨",
    "enhancement": "✨",

    "quality": "💎",
    "code-quality": "💎",
    "codequality": "💎",
    "clean": "💎",

    # Priority
    "urgent": "🚨",
    "important": "🚨",
    "critical": "🚨",
    "asap": "🚨",

    "low": "🐌",
    "later": "🐌",
    "someday": "🐌",
    "maybe": "🐌",

    # Project Management
    "project": "📊",
    "management": "📊",
    "pm": "📊",
    "tracking": "📊",

    # Recipes
    "recipe": "📋",
    "template": "📋",
    "playbook": "📋",
}

# Reverse mapping - emoji -> text aliases (for display/reference)
REVERSE_ALIASES: Dict[str, List[str]] = {}
for alias, emoji in EMOJI_ALIASES.items():
    if emoji not in REVERSE_ALIASES:
        REVERSE_ALIASES[emoji] = []
    REVERSE_ALIASES[emoji].append(alias)

# Set of all emoji tags for validation
EMOJI_TAGS: Set[str] = set(EMOJI_ALIASES.values())


def expand_aliases(tags: List[str]) -> List[str]:
    """
    Expand text aliases to emojis in a list of tags.

    Args:
        tags: List of tag strings (mix of text aliases and emojis)

    Returns:
        List of tags with aliases expanded to emojis

    Examples:
        >>> expand_aliases(["gameplan", "active", "🔧"])
        ["🎯", "🚀", "🔧"]
        >>> expand_aliases(["notes", "urgent"])
        ["📝", "🚨"]
    """
    expanded = []
    for tag in tags:
        tag = tag.strip().lower()
        if tag in EMOJI_ALIASES:
            expanded.append(EMOJI_ALIASES[tag])
        else:
            # Keep as-is (might be an emoji or unrecognized text)
            expanded.append(tag)
    return expanded


def expand_alias_string(tag_string: str) -> str:
    """
    Expand aliases in a comma-separated tag string.

    Args:
        tag_string: Comma-separated string of tags

    Returns:
        Comma-separated string with aliases expanded

    Examples:
        >>> expand_alias_string("gameplan, active, refactor")
        "🎯, 🚀, 🔧"
        >>> expand_alias_string("notes,urgent")
        "📝,🚨"
    """
    if not tag_string:
        return ""

    tags = [t.strip() for t in tag_string.split(",") if t.strip()]
    expanded = expand_aliases(tags)
    return ", ".join(expanded)


def get_aliases_for_emoji(emoji: str) -> List[str]:
    """
    Get all text aliases for a given emoji.

    Args:
        emoji: The emoji tag

    Returns:
        List of text aliases for the emoji

    Examples:
        >>> get_aliases_for_emoji("🎯")
        ["gameplan", "plan", "strategy", "goal"]
    """
    return REVERSE_ALIASES.get(emoji, [])


def is_emoji_tag(tag: str) -> bool:
    """
    Check if a tag is a known emoji tag.

    Args:
        tag: The tag to check

    Returns:
        True if the tag is a known emoji
    """
    return tag in EMOJI_TAGS


def is_text_alias(tag: str) -> bool:
    """
    Check if a tag is a known text alias.

    Args:
        tag: The tag to check

    Returns:
        True if the tag is a known text alias
    """
    return tag.lower() in EMOJI_ALIASES


def normalize_tag_to_emoji(tag: str) -> str:
    """
    Convert a tag to its emoji equivalent if it's a known text alias.

    Args:
        tag: The tag to normalize (could be text alias or already emoji)

    Returns:
        Emoji version of the tag, or original tag if no alias exists

    Examples:
        >>> normalize_tag_to_emoji("gameplan")
        "🎯"
        >>> normalize_tag_to_emoji("🎯")
        "🎯"
        >>> normalize_tag_to_emoji("unknown-tag")
        "unknown-tag"
    """
    tag_lower = tag.strip().lower()
    return EMOJI_ALIASES.get(tag_lower, tag)


def get_all_aliases() -> Dict[str, str]:
    """
    Get all emoji aliases.

    Returns:
        Dictionary mapping text aliases to emojis
    """
    return EMOJI_ALIASES.copy()


def get_category_emojis() -> Dict[str, List[str]]:
    """
    Get emojis organized by category.

    Returns:
        Dictionary mapping categories to lists of emojis
    """
    categories = {
        "Document Types": ["🎯", "🔍", "📝", "📚", "🏗️"],
        "Workflow Status": ["🚀", "✅", "🚧"],
        "Outcomes": ["🎉", "❌", "⚡"],
        "Technical Work": ["🔧", "🧪", "🐛", "✨", "💎"],
        "Priority": ["🚨", "🐌"],
        "Project Management": ["📊"],
        "Recipes": ["📋"],
    }
    return categories


def suggest_aliases(partial: str) -> List[str]:
    """
    Suggest aliases based on partial input.

    Args:
        partial: Partial text to match against

    Returns:
        List of matching aliases
    """
    partial = partial.lower().strip()
    if not partial:
        return []

    matches = []
    for alias in EMOJI_ALIASES.keys():
        if alias.startswith(partial):
            matches.append(alias)

    # Sort by length (shorter matches first) then alphabetically
    matches.sort(key=lambda x: (len(x), x))
    return matches[:10]  # Limit to 10 suggestions
