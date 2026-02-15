"""
Centralized datetime parsing utilities for EMDX.

This module provides consistent datetime parsing across the codebase,
handling various input formats from SQLite, JSON, and ISO 8601 strings.
"""

from datetime import datetime, timezone
from typing import Union


def parse_datetime(value: Union[str, datetime, None],
                   default: datetime | None = None,
                   assume_utc: bool = False) -> datetime | None:
    """
    Parse a datetime value from various formats.

    Handles:
    - ISO 8601 strings (with or without timezone)
    - SQLite datetime strings (space separator instead of 'T')
    - ISO strings with 'Z' suffix for UTC
    - Already-parsed datetime objects
    - None values

    Args:
        value: The value to parse (string, datetime, or None)
        default: Default value to return if parsing fails (default: None)
        assume_utc: If True, treat naive datetimes as UTC

    Returns:
        Parsed datetime object, or default if value is None/unparseable

    Examples:
        >>> parse_datetime("2024-01-15T10:30:00")
        datetime(2024, 1, 15, 10, 30, 0)

        >>> parse_datetime("2024-01-15 10:30:00")  # SQLite format
        datetime(2024, 1, 15, 10, 30, 0)

        >>> parse_datetime("2024-01-15T10:30:00Z")  # UTC
        datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    """
    if value is None:
        return default

    if isinstance(value, datetime):
        if assume_utc and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    if not isinstance(value, str):
        return default

    # Normalize the string
    normalized = value.strip()

    # Handle Z suffix for UTC
    if normalized.endswith('Z'):
        normalized = normalized[:-1] + '+00:00'

    # Handle SQLite space separator
    if ' ' in normalized and 'T' not in normalized:
        normalized = normalized.replace(' ', 'T', 1)

    try:
        dt = datetime.fromisoformat(normalized)
        if assume_utc and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        # Not ISO format, try fallback formats below
        pass

    # Fallback: try common formats
    fallback_formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d %H:%M:%S.%f',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%dT%H:%M:%S.%f',
    ]

    for fmt in fallback_formats:
        try:
            dt = datetime.strptime(value, fmt)
            if assume_utc and dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue

    return default


def parse_timestamp(value: Union[str, datetime, None]) -> datetime:
    """
    Parse a timestamp with timezone awareness for database operations.

    This is a specialized version that always returns a datetime
    (falling back to now() if parsing fails) and ensures UTC timezone
    for database consistency.

    Args:
        value: The value to parse

    Returns:
        Parsed datetime with UTC timezone, or current UTC time if parsing fails
    """
    result = parse_datetime(value, assume_utc=True)
    if result is None:
        return datetime.now(timezone.utc)
    if result.tzinfo is None:
        return result.replace(tzinfo=timezone.utc)
    return result


def format_datetime(dt: Union[str, datetime, None],
                    format_str: str = "%Y-%m-%d %H:%M") -> str:
    """
    Format a datetime value for display.

    Handles both string and datetime inputs for convenience.

    Args:
        dt: Datetime value (string or datetime object)
        format_str: strftime format string

    Returns:
        Formatted string, or "N/A" if value is None/unparseable
    """
    if dt is None:
        return "N/A"

    if isinstance(dt, str):
        dt = parse_datetime(dt)
        if dt is None:
            return "N/A"

    return dt.strftime(format_str)
