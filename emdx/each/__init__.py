"""EMDX Each - Reusable parallel commands with discovery patterns.

This module provides:
- Built-in discovery commands (@prs-with-conflicts, @open-prs, etc.)
- User-extensible custom discoveries
- Shell command safety utilities
"""

from .discoveries import (
    BuiltinDiscovery,
    DiscoveryCategory,
    BUILTIN_DISCOVERIES,
    resolve_discovery,
    is_discovery_reference,
    check_requirements,
)

__all__ = [
    "BuiltinDiscovery",
    "DiscoveryCategory",
    "BUILTIN_DISCOVERIES",
    "resolve_discovery",
    "is_discovery_reference",
    "check_requirements",
]
