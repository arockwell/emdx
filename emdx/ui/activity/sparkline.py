"""Sparkline utilities for terminal visualization."""

from typing import List, Optional


BLOCKS = "▁▂▃▄▅▆▇█"


def sparkline(values: List[float], width: Optional[int] = None) -> str:
    """Generate a sparkline string from values.

    Args:
        values: List of numeric values to visualize
        width: Optional fixed width (will sample/pad values)

    Returns:
        String of Unicode block characters representing the values
    """
    if not values:
        return ""

    # Handle width adjustment
    if width and len(values) != width:
        if len(values) > width:
            # Sample evenly
            step = len(values) / width
            values = [values[int(i * step)] for i in range(width)]
        else:
            # Pad with zeros
            values = values + [0] * (width - len(values))

    min_val = min(values)
    max_val = max(values)
    range_val = max_val - min_val

    if range_val == 0:
        # All values are the same
        return BLOCKS[4] * len(values)

    result = ""
    for v in values:
        # Normalize to 0-7 range for block selection
        idx = int((v - min_val) / range_val * 7)
        idx = max(0, min(7, idx))  # Clamp to valid range
        result += BLOCKS[idx]

    return result


def sparkline_with_labels(
    values: List[float],
    labels: Optional[List[str]] = None,
) -> str:
    """Generate sparkline with optional labels below.

    Args:
        values: List of numeric values
        labels: Optional labels (e.g., day names)

    Returns:
        Multi-line string with sparkline and labels
    """
    spark = sparkline(values)

    if not labels:
        return spark

    # Truncate labels to 1 char each
    label_line = "".join(l[0] if l else " " for l in labels[: len(values)])

    return f"{spark}\n{label_line}"
