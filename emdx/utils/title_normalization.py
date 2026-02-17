"""Title normalization for document deduplication.

Normalizes document titles by removing variable parts like dates, timestamps,
agent numbers, etc. to enable automatic supersede detection.
"""

import re


def normalize_title(title: str) -> str:
    """Normalize a document title for comparison.

    Removes:
    - Dates in various formats: (2025-01-10), - 2025-01-10, 2025-01-10T...
    - Agent numbers: (Agent 1), (Agent 5)
    - Task/Issue numbers: #123, Task #45
    - ISO timestamps: - 2026-01-11T00:05:45.123456
    - Version suffixes: v1, v2, (v1)
    - Trailing whitespace and extra spaces

    Args:
        title: The document title to normalize

    Returns:
        Normalized title suitable for comparison
    """
    if not title:
        return ""

    result = title

    # Remove ISO timestamps with optional timezone: - 2026-01-11T00:05:45.123456+00:00
    result = re.sub(
        r"\s*-?\s*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2}|Z)?", "", result
    )  # noqa: E501

    # Remove dates in parentheses: (2025-01-10)
    result = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)", "", result)

    # Remove dates after dash: - 2025-01-10
    result = re.sub(r"\s*-\s*\d{4}-\d{2}-\d{2}", "", result)

    # Remove standalone dates: 2025-01-10
    result = re.sub(r"\s+\d{4}-\d{2}-\d{2}(?:\s|$)", " ", result)

    # Remove agent numbers: (Agent 1), (Agent 5)
    result = re.sub(r"\s*\(Agent\s+\d+\)", "", result, flags=re.IGNORECASE)

    # Remove task/issue numbers: #123, Task #45, Issue #678
    result = re.sub(r"\s*(?:Task|Issue)?\s*#\d+", "", result, flags=re.IGNORECASE)

    # Remove version suffixes: v1, v2, (v1), (v2)
    result = re.sub(r"\s*\(?v\d+\)?", "", result, flags=re.IGNORECASE)

    # Remove (error) suffix from synthesis docs
    result = re.sub(r"\s*\(error\)", "", result, flags=re.IGNORECASE)

    # Normalize whitespace
    result = re.sub(r"\s+", " ", result).strip()

    return result


def titles_match(title1: str, title2: str) -> bool:
    """Check if two titles match after normalization.

    Args:
        title1: First title
        title2: Second title

    Returns:
        True if normalized titles are equal
    """
    return normalize_title(title1) == normalize_title(title2)


def title_similarity(title1: str, title2: str) -> float:
    """Calculate similarity ratio between two titles.

    Uses SequenceMatcher for fuzzy matching after normalization.

    Args:
        title1: First title
        title2: Second title

    Returns:
        Similarity ratio between 0.0 and 1.0
    """
    from difflib import SequenceMatcher

    norm1 = normalize_title(title1).lower()
    norm2 = normalize_title(title2).lower()

    if not norm1 or not norm2:
        return 0.0

    return SequenceMatcher(None, norm1, norm2).ratio()
