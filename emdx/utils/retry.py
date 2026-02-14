"""
Retry utilities for network/IO operations.

Uses tenacity for exponential backoff with configurable retries.
"""

import logging
import subprocess
from functools import wraps
from typing import Any, Callable, Tuple, Type, TypeVar, Union

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_MIN_WAIT = 1  # seconds
DEFAULT_MAX_WAIT = 10  # seconds


def with_retry(
    max_retries: int = DEFAULT_MAX_RETRIES,
    min_wait: float = DEFAULT_MIN_WAIT,
    max_wait: float = DEFAULT_MAX_WAIT,
    retry_exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for adding retry logic with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        min_wait: Minimum wait time between retries in seconds (default: 1)
        max_wait: Maximum wait time between retries in seconds (default: 10)
        retry_exceptions: Tuple of exception types to retry on

    Returns:
        Decorated function with retry behavior

    Example:
        @with_retry(max_retries=3, retry_exceptions=(ConnectionError, TimeoutError))
        def fetch_data():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type(retry_exceptions),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            return func(*args, **kwargs)
        return wrapper
    return decorator


# Exception types for network operations
NETWORK_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)

# Exception types for subprocess operations (GitHub CLI, etc.)
SUBPROCESS_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    subprocess.TimeoutExpired,
    # CalledProcessError is NOT included - we don't want to retry on actual command failures
    # Only retry on transient network/IO issues
)


def retry_network(
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying network operations.

    Retries on ConnectionError, TimeoutError, and OSError.

    Args:
        max_retries: Maximum number of retry attempts

    Example:
        @retry_network()
        def call_api():
            ...
    """
    return with_retry(
        max_retries=max_retries,
        retry_exceptions=NETWORK_EXCEPTIONS,
    )


def retry_subprocess(
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying subprocess operations.

    Only retries on TimeoutExpired - not on CalledProcessError
    (which indicates the command actually ran but failed).

    Args:
        max_retries: Maximum number of retry attempts

    Example:
        @retry_subprocess()
        def run_git_command():
            ...
    """
    return with_retry(
        max_retries=max_retries,
        retry_exceptions=SUBPROCESS_EXCEPTIONS,
    )


def retry_api_call(
    max_retries: int = DEFAULT_MAX_RETRIES,
    additional_exceptions: Tuple[Type[Exception], ...] = (),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying API calls with common transient errors.

    Includes network exceptions plus any additional API-specific exceptions.

    Args:
        max_retries: Maximum number of retry attempts
        additional_exceptions: Additional exception types to retry on

    Example:
        @retry_api_call(additional_exceptions=(anthropic.RateLimitError,))
        def call_claude():
            ...
    """
    all_exceptions = NETWORK_EXCEPTIONS + additional_exceptions
    return with_retry(
        max_retries=max_retries,
        retry_exceptions=all_exceptions,
    )
