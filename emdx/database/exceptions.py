"""Database exceptions for emdx.

This module provides custom exceptions for database operations,
enabling consistent error handling and better debugging.
"""


class DatabaseError(Exception):
    """Base exception for database errors."""

    pass


class DocumentNotFoundError(DatabaseError):
    """Raised when a document is not found."""

    def __init__(self, identifier):
        self.identifier = identifier
        super().__init__(f"Document not found: {identifier}")


class DuplicateDocumentError(DatabaseError):
    """Raised when a document already exists."""

    def __init__(self, identifier, message=None):
        self.identifier = identifier
        super().__init__(message or f"Document already exists: {identifier}")


class GroupNotFoundError(DatabaseError):
    """Raised when a group is not found."""

    def __init__(self, group_id):
        self.group_id = group_id
        super().__init__(f"Group not found: {group_id}")


class CycleDetectedError(DatabaseError):
    """Raised when an operation would create a cycle."""

    def __init__(self, message="Operation would create a cycle"):
        super().__init__(message)


class IntegrityError(DatabaseError):
    """Raised when a database integrity constraint is violated."""

    pass


class InvalidStageError(DatabaseError):
    """Raised when an invalid cascade stage is specified."""

    def __init__(self, stage, valid_stages=None):
        self.stage = stage
        self.valid_stages = valid_stages
        if valid_stages:
            message = f"Invalid cascade stage: {stage}. Valid stages: {', '.join(sorted(valid_stages))}"
        else:
            message = f"Invalid cascade stage: {stage}"
        super().__init__(message)
