"""File size formatting utilities."""


def format_file_size(size_bytes: int) -> str:
    """
    Format a file size in bytes to a human-readable string.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable size string (e.g., "1.2 KB", "3.5 MB")
    """
    if size_bytes < 0:
        return "Invalid size"

    if size_bytes == 0:
        return "0 B"

    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    unit_index = 0
    size = float(size_bytes)

    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1

    # Format with appropriate decimal places
    if size == int(size):
        return f"{int(size)} {units[unit_index]}"
    elif size >= 100:
        return f"{size:.0f} {units[unit_index]}"
    elif size >= 10:
        # Strip trailing zeros for cleaner display
        formatted = f"{size:.1f}"
        if formatted.endswith('0'):
            formatted = formatted[:-1]
        return f"{formatted} {units[unit_index]}"
    else:
        # Strip trailing zeros for cleaner display
        formatted = f"{size:.2f}"
        if formatted.endswith('0'):
            formatted = formatted[:-1]
            if formatted.endswith('0'):
                formatted = formatted[:-1]
        return f"{formatted} {units[unit_index]}"
