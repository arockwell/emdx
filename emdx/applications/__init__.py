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
"""

from .maintenance import MaintenanceApplication

__all__ = ["MaintenanceApplication"]
