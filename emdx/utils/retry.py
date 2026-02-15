"""Retry decorator with exponential backoff for transient errors.

This module provides a simple retry decorator for network/IO operations that may
fail due to transient issues like network timeouts or connection errors.

Only transient errors are retried - authentication failures (4xx errors) and
other permanent errors are NOT retried.
"""

import functools
import logging
import random
import time
from typing import Callable, Optional, Tuple, Type, TypeVar, Union

logger = logging.getLogger(__name__)

# Type variable for generic function return type
T = TypeVar("T")

# Default transient exceptions that should be retried
DEFAULT_TRANSIENT_EXCEPTIONS: Tuple[Type[Exception], ...] = (
    TimeoutError,
    ConnectionError,
    ConnectionResetError,
    ConnectionRefusedError,
    ConnectionAbortedError,
    BrokenPipeError,
    OSError,  # Covers many network-related errors
)


class RetryableError(Exception):
    """Exception that indicates a retryable error occurred.

    Use this to explicitly mark an error as retryable when wrapping
    other error types.
    """

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


class NonRetryableError(Exception):
    """Exception that indicates an error should NOT be retried.

    Use this to explicitly mark an error as non-retryable, such as
    authentication failures or validation errors.
    """

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.original_error = original_error


def is_transient_subprocess_error(exc: Exception) -> bool:
    """Check if a subprocess error is transient and should be retried.

    Args:
        exc: The exception to check.

    Returns:
        True if the error is transient, False otherwise.
    """
    import subprocess

    if not isinstance(exc, subprocess.CalledProcessError):
        return False

    # Transient subprocess errors (exit codes that suggest retry might help)
    # - Exit code 124: timeout
    # - Exit code 1 with specific error messages indicating network issues
    if exc.returncode == 124:  # Timeout
        return True

    # Check stderr for common transient error patterns
    stderr = exc.stderr if exc.stderr else ""
    transient_patterns = [
        "connection reset",
        "connection refused",
        "connection timed out",
        "timeout",
        "temporary failure",
        "network unreachable",
        "host unreachable",
        "could not resolve",
        "rate limit",
        "502",
        "503",
        "504",
    ]

    stderr_lower = stderr.lower() if isinstance(stderr, str) else stderr.decode("utf-8", errors="ignore").lower()
    return any(pattern in stderr_lower for pattern in transient_patterns)


def retry(
    max_retries: int = 3,
    min_backoff: float = 1.0,
    max_backoff: float = 10.0,
    exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that retries a function on transient failures with exponential backoff.

    Only retries on transient errors (timeouts, connection errors). Does NOT retry
    on authentication failures, validation errors, or other permanent errors.

    Args:
        max_retries: Maximum number of retry attempts (default: 3).
        min_backoff: Minimum backoff time in seconds (default: 1.0).
        max_backoff: Maximum backoff time in seconds (default: 10.0).
        exceptions: Tuple of exception types to retry on. If None, uses
            DEFAULT_TRANSIENT_EXCEPTIONS.
        on_retry: Optional callback called before each retry with (exception, attempt).

    Returns:
        A decorator function.

    Example:
        @retry(max_retries=3, min_backoff=1.0, max_backoff=10.0)
        def make_api_call():
            # This will be retried up to 3 times on transient failures
            response = requests.get("https://api.example.com/data")
            response.raise_for_status()
            return response.json()
    """
    if exceptions is None:
        exceptions = DEFAULT_TRANSIENT_EXCEPTIONS

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception: Optional[Exception] = None
            attempt = 0

            while attempt <= max_retries:
                try:
                    return func(*args, **kwargs)
                except NonRetryableError:
                    # Never retry non-retryable errors
                    raise
                except RetryableError as e:
                    # Always retry retryable errors
                    last_exception = e
                except exceptions as e:
                    # Retry on configured transient exceptions
                    last_exception = e
                except Exception as e:
                    # Check if it's a subprocess error that might be transient
                    import subprocess

                    if isinstance(e, subprocess.CalledProcessError):
                        if is_transient_subprocess_error(e):
                            last_exception = e
                        else:
                            # Non-transient subprocess error
                            raise
                    else:
                        # Unknown exception type - don't retry
                        raise

                # We caught a retryable exception
                attempt += 1

                if attempt > max_retries:
                    # Max retries exceeded
                    logger.warning(
                        "Max retries (%d) exceeded for %s: %s",
                        max_retries,
                        func.__name__,
                        last_exception,
                    )
                    raise last_exception

                # Calculate backoff with exponential increase and jitter
                backoff = min(min_backoff * (2 ** (attempt - 1)), max_backoff)
                # Add jitter to prevent thundering herd
                jitter = random.uniform(0, backoff * 0.1)
                sleep_time = backoff + jitter

                logger.debug(
                    "Retry %d/%d for %s after %.2fs: %s",
                    attempt,
                    max_retries,
                    func.__name__,
                    sleep_time,
                    last_exception,
                )

                if on_retry:
                    on_retry(last_exception, attempt)

                time.sleep(sleep_time)

            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
            raise RuntimeError("Unexpected retry loop termination")

        return wrapper

    return decorator


def retry_subprocess(
    max_retries: int = 3,
    min_backoff: float = 1.0,
    max_backoff: float = 10.0,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Specialized retry decorator for subprocess calls.

    This decorator handles subprocess-specific errors and only retries on
    transient failures (timeouts, network errors in output). It does NOT retry
    on authentication failures or permission errors.

    Args:
        max_retries: Maximum number of retry attempts (default: 3).
        min_backoff: Minimum backoff time in seconds (default: 1.0).
        max_backoff: Maximum backoff time in seconds (default: 10.0).

    Returns:
        A decorator function.

    Example:
        @retry_subprocess()
        def call_github_api():
            result = subprocess.run(
                ["gh", "api", "repos/owner/repo"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
    """
    import subprocess

    # Include subprocess-related exceptions
    exceptions = DEFAULT_TRANSIENT_EXCEPTIONS + (subprocess.TimeoutExpired,)

    return retry(
        max_retries=max_retries,
        min_backoff=min_backoff,
        max_backoff=max_backoff,
        exceptions=exceptions,
    )
