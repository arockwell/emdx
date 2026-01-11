"""Data models for EMDX entities.

This package defines the core data models and operations for:

- documents: Document model with metadata and content
- executions: Execution records for tracking agent runs
- tags: Tag system with emoji aliases and categorization
- tasks: Task management with dependencies and status tracking
- task_executions: Linking tasks to their execution history
- export_profiles: Export profile management for document exports
"""

from emdx.models import export_profiles
