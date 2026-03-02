"""
Application Service Layer for EMDX.

This layer sits between commands and services, providing:
- Centralized database initialization
- Service orchestration for complex operations
- Cross-cutting concerns (logging, error handling)
- Testable business logic separated from CLI

The application layer breaks bidirectional dependencies by:
- Commands depend on applications (not directly on services)
- Applications orchestrate services
- Services remain independent and focused

MaintenanceApplication is lazy-imported to avoid pulling in heavy
sklearn/scipy dependencies on every CLI invocation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .maintenance import MaintenanceApplication

__all__ = ["MaintenanceApplication"]


def __getattr__(name: str) -> type:
    if name == "MaintenanceApplication":
        from .maintenance import MaintenanceApplication

        return MaintenanceApplication
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
