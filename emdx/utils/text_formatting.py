"""
Text formatting utilities for EMDX.

This module provides reusable functions for consistent text truncation
and formatting across the application.
"""


def truncate_title(text: str, max_len: int = 50) -> str:
    """
    Truncate title text to a maximum length with ellipsis.

    Args:
        text: The text to truncate
        max_len: Maximum length before truncation (default: 50)

    Returns:
        Truncated text with "..." if it was too long, otherwise original text
    """
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def truncate_description(text: str, max_len: int = 40) -> str:
    """
    Truncate description text to a maximum length with ellipsis.

    Args:
        text: The text to truncate
        max_len: Maximum length before truncation (default: 40)

    Returns:
        Truncated text with "..." if it was too long, otherwise original text
    """
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def truncate_path(text: str, max_len: int = 35) -> str:
    """
    Truncate file path text to a maximum length with ellipsis.

    Args:
        text: The text to truncate
        max_len: Maximum length before truncation (default: 35)

    Returns:
        Truncated text with "..." if it was too long, otherwise original text
    """
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text


def truncate_text(text: str, max_len: int = 30) -> str:
    """
    Truncate general text to a maximum length with ellipsis.

    Args:
        text: The text to truncate
        max_len: Maximum length before truncation (default: 30)

    Returns:
        Truncated text with "..." if it was too long, otherwise original text
    """
    if len(text) > max_len:
        return text[:max_len] + "..."
    return text
