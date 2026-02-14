"""Retry utilities for transient failures.

This module provides retry decorators and utilities for handling transient
failures in API calls, git operations, and file system operations.

Usage:
    from emdx.utils.retry import retry_api_call, retry_git_operation

    @retry_api_call
    def call_anthropic_api():
        ...

    @retry_git_operation
    def git_commit():
        ...
"""

import logging
import sqlite3
import subprocess
from functools import wraps
from typing import Any, Callable, TypeVar, Union

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    wait_fixed,
    before_sleep_log,
)

from ..exceptions import (
    ApiConnectionError,
    ApiRateLimitError,
    DatabaseError,
    GitLockError,
)

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# =============================================================================
# API Retry Configuration
# =============================================================================

# Retry API calls up to 3 times with exponential backoff (1s, 2s, 4s)
retry_api_call = retry(
    retry=retry_if_exception_type((
        ApiConnectionError,
        ApiRateLimitError,
        ConnectionError,
        TimeoutError,
    )),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


# =============================================================================
# Git Retry Configuration
# =============================================================================

def _is_git_lock_error(exception: BaseException) -> bool:
    """Check if exception is a git lock error."""
    if isinstance(exception, GitLockError):
        return True
    if isinstance(exception, subprocess.CalledProcessError):
        stderr = getattr(exception, "stderr", "") or ""
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return "lock" in stderr.lower() or ".lock" in stderr
    return False


# Retry git operations up to 5 times with fixed 1s delay (for lock contention)
retry_git_operation = retry(
    retry=retry_if_exception_type((GitLockError, subprocess.CalledProcessError)),
    stop=stop_after_attempt(5),
    wait=wait_fixed(1),
    before_sleep=before_sleep_log(logger, logging.DEBUG),
    reraise=True,
)


# =============================================================================
# Database Retry Configuration
# =============================================================================

# Retry database operations up to 3 times with short delays (for busy database)
retry_database_operation = retry(
    retry=retry_if_exception_type((
        sqlite3.OperationalError,  # Database is locked
        DatabaseError,
    )),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.1, min=0.1, max=1),
    before_sleep=before_sleep_log(logger, logging.DEBUG),
    reraise=True,
)


# =============================================================================
# File System Retry Configuration
# =============================================================================

# Retry file operations up to 3 times with short delays
retry_file_operation = retry(
    retry=retry_if_exception_type((
        OSError,
        IOError,
        PermissionError,
    )),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.1, min=0.1, max=1),
    before_sleep=before_sleep_log(logger, logging.DEBUG),
    reraise=True,
)


# =============================================================================
# Utility Functions
# =============================================================================

def with_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    exceptions: tuple = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[F], F]:
    """Create a custom retry decorator.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Base delay between retries in seconds
        exceptions: Tuple of exception types to retry on
        on_retry: Optional callback called before each retry with (exception, attempt)

    Returns:
        Decorator that adds retry behavior to a function

    Example:
        @with_retry(max_attempts=5, delay=2.0, exceptions=(ConnectionError,))
        def flaky_network_call():
            ...
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        if on_retry:
                            on_retry(e, attempt)
                        else:
                            logger.debug(
                                f"Retry {attempt}/{max_attempts} for {func.__name__}: {e}"
                            )
                        import time
                        time.sleep(delay * attempt)  # Linear backoff
                    else:
                        raise
            # Should not reach here, but satisfy type checker
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop exit")
        return wrapper  # type: ignore
    return decorator


def is_retryable_error(exception: BaseException) -> bool:
    """Check if an exception is typically retryable.

    Args:
        exception: The exception to check

    Returns:
        True if the exception represents a transient failure that may succeed on retry
    """
    from ..exceptions import EmdxError

    # Check our custom exceptions
    if isinstance(exception, EmdxError):
        return exception.retryable

    # Check common retryable exceptions
    retryable_types = (
        ConnectionError,
        TimeoutError,
        sqlite3.OperationalError,  # Database locked
    )

    if isinstance(exception, retryable_types):
        return True

    # Check subprocess errors for specific retryable conditions
    if isinstance(exception, subprocess.CalledProcessError):
        return _is_git_lock_error(exception)

    return False
