"""Tag display utilities for consistent ordering and formatting."""


def order_tags(tags: list[str]) -> list[str]:
    """
    Order tags according to category: Document Type -> Status -> Other

    Args:
        tags: List of tag strings

    Returns:
        Ordered list of tags
    """
    # Define tag categories
    document_types = {"gameplan", "plan", "analysis", "notes", "docs", "architecture"}
    status_tags = {"active", "done", "blocked"}

    # Sort tags into categories
    doc_type_tags = [t for t in tags if t in document_types]
    status_list = [t for t in tags if t in status_tags]
    other_tags = [t for t in tags if t not in document_types and t not in status_tags]

    # Combine in order
    return doc_type_tags + status_list + other_tags


def format_tags(tags: list[str]) -> str:
    """
    Format tags for display with proper ordering and comma separation.

    Args:
        tags: List of tag strings

    Returns:
        Formatted tag string with comma separation
    """
    if not tags:
        return ""

    ordered = order_tags(tags)
    return ", ".join(ordered)
