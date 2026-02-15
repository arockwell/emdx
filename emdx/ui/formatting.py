"""Tag display utilities for consistent ordering and formatting."""

def order_tags(tags: list[str]) -> list[str]:
    """
    Order tags according to category: Document Type -> Status -> Other

    Args:
        tags: List of tag strings (usually emojis)

    Returns:
        Ordered list of tags
    """
    # Define tag categories
    document_types = {"🎯", "🔍", "📝", "📚", "🏗️"}
    status_tags = {"🚀", "✅", "🚧"}

    # Sort tags into categories
    doc_type_tags = [t for t in tags if t in document_types]
    status_list = [t for t in tags if t in status_tags]
    other_tags = [t for t in tags if t not in document_types and t not in status_tags]

    # Combine in order
    return doc_type_tags + status_list + other_tags

def format_tags(tags: list[str]) -> str:
    """
    Format tags for display with proper ordering and spacing.

    Args:
        tags: List of tag strings

    Returns:
        Formatted tag string with space separation
    """
    if not tags:
        return ""

    ordered = order_tags(tags)
    return " ".join(ordered)

def truncate_emoji_safe(text: str, max_chars: int) -> tuple[str, bool]:
    """
    Truncate text at emoji boundaries to avoid breaking multi-char emojis.

    This is important for emojis like 🏗️ which consist of multiple Unicode
    code points (base emoji + variation selector).

    Args:
        text: Text to truncate
        max_chars: Maximum character count

    Returns:
        Tuple of (truncated_text, was_truncated)
    """
    if len(text) <= max_chars:
        return text, False

    # Find safe truncation point
    truncate_at = max_chars

    # Check if we're in the middle of a multi-char sequence
    while truncate_at > 0 and truncate_at < len(text):
        next_char = text[truncate_at]
        # Check for variation selectors (U+FE00-U+FE0F) and other combining marks
        if 0xFE00 <= ord(next_char) <= 0xFE0F:
            # Move back to include the whole emoji
            truncate_at -= 1
        else:
            break

    return text[:truncate_at], True
