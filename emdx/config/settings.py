"""Configuration utilities for emdx."""

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Re-export constants for backward compatibility
from .constants import DEFAULT_CLAUDE_MODEL, EMDX_CONFIG_DIR, ENV_VAR_DEFINITIONS


def get_db_path() -> Path:
    """Get the database path, respecting EMDX_TEST_DB environment variable.

    When running tests, set EMDX_TEST_DB to a temp file path to prevent
    tests from polluting the real database.
    """
    test_db = os.environ.get("EMDX_TEST_DB")
    if test_db:
        return Path(test_db)

    EMDX_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return EMDX_CONFIG_DIR / "knowledge.db"


def validate_env_var(name: str, value: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate a single environment variable value.

    Args:
        name: The environment variable name.
        value: The current value (or None if not set).

    Returns:
        Tuple of (is_valid, error_message).
    """
    if name not in ENV_VAR_DEFINITIONS:
        return True, None  # Unknown vars are always valid

    definition = ENV_VAR_DEFINITIONS[name]
    valid_values = definition.get("valid_values")
    default = definition.get("default")

    # If not set and has no default, that's not an error (optional)
    if value is None:
        return True, None

    # If valid_values is None, any value is valid
    if valid_values is None:
        return True, None

    # Check against valid values
    if value.lower() not in [v.lower() for v in valid_values]:
        return False, f"Invalid value '{value}' for {name}. Valid values: {valid_values}"

    return True, None


def validate_all_env_vars() -> List[str]:
    """Validate all EMDX environment variables.

    Returns:
        List of error messages (empty if all valid).
    """
    errors = []
    for name in ENV_VAR_DEFINITIONS:
        value = os.environ.get(name)
        is_valid, error = validate_env_var(name, value)
        if not is_valid:
            errors.append(error)
    return errors


def get_env_var(name: str, validate: bool = True) -> Optional[str]:
    """Get an environment variable with optional validation.

    Args:
        name: The environment variable name.
        validate: Whether to validate the value against known definitions.

    Returns:
        The environment variable value, or None if not set.

    Raises:
        ValueError: If validate=True and the value is invalid.
    """
    value = os.environ.get(name)

    if validate and value is not None:
        is_valid, error = validate_env_var(name, value)
        if not is_valid:
            raise ValueError(error)

    # Return value or default
    if value is None and name in ENV_VAR_DEFINITIONS:
        return ENV_VAR_DEFINITIONS[name].get("default")

    return value


def get_env_info() -> Dict[str, Dict]:
    """Get information about all EMDX environment variables.

    Returns:
        Dictionary mapping env var names to their info including:
        - description: What the variable does
        - value: Current value (masked for sensitive vars)
        - valid: Whether the current value is valid
        - default: The default value if not set
    """
    info = {}
    for name, definition in ENV_VAR_DEFINITIONS.items():
        value = os.environ.get(name)
        is_valid, _ = validate_env_var(name, value)

        # Mask sensitive values
        display_value = value
        if value and definition.get("sensitive"):
            display_value = value[:4] + "..." if len(value) > 4 else "***"

        info[name] = {
            "description": definition.get("description", ""),
            "value": display_value,
            "is_set": value is not None,
            "valid": is_valid,
            "default": definition.get("default"),
            "sensitive": definition.get("sensitive", False),
        }
    return info
