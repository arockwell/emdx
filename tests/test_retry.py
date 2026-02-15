"""Tests for the retry decorator module."""

import subprocess
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from emdx.utils.retry import (
    NonRetryableError,
    RetryableError,
    is_transient_subprocess_error,
    retry,
    retry_subprocess,
)


class TestRetryDecorator:
    """Tests for the basic retry decorator."""

    def test_retry_succeeds_on_first_attempt(self):
        """Test that a successful function doesn't retry."""
        call_count = 0

        @retry(max_retries=3)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_retry_on_timeout_error(self):
        """Test that TimeoutError triggers retry."""
        call_count = 0

        @retry(max_retries=3, min_backoff=0.01, max_backoff=0.05)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("Connection timed out")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3

    def test_retry_on_connection_error(self):
        """Test that ConnectionError triggers retry."""
        call_count = 0

        @retry(max_retries=3, min_backoff=0.01, max_backoff=0.05)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Connection refused")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 2

    def test_max_retries_exceeded(self):
        """Test that max retries are respected."""
        call_count = 0

        @retry(max_retries=2, min_backoff=0.01, max_backoff=0.05)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("Always times out")

        with pytest.raises(TimeoutError):
            always_fails()

        # Initial call + 2 retries = 3 total calls
        assert call_count == 3

    def test_non_retryable_error_not_retried(self):
        """Test that NonRetryableError is not retried."""
        call_count = 0

        @retry(max_retries=3)
        def fails_with_non_retryable():
            nonlocal call_count
            call_count += 1
            raise NonRetryableError("Authentication failed")

        with pytest.raises(NonRetryableError):
            fails_with_non_retryable()

        assert call_count == 1

    def test_retryable_error_is_retried(self):
        """Test that RetryableError is always retried."""
        call_count = 0

        @retry(max_retries=3, min_backoff=0.01, max_backoff=0.05)
        def flaky_with_retryable():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("Temporary failure")
            return "success"

        result = flaky_with_retryable()
        assert result == "success"
        assert call_count == 3

    def test_unknown_exception_not_retried(self):
        """Test that unknown exceptions are not retried."""
        call_count = 0

        @retry(max_retries=3)
        def fails_with_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid input")

        with pytest.raises(ValueError):
            fails_with_value_error()

        assert call_count == 1

    def test_on_retry_callback(self):
        """Test that on_retry callback is called before each retry."""
        call_count = 0
        retry_events = []

        def on_retry_handler(exc, attempt):
            retry_events.append((type(exc).__name__, attempt))

        @retry(max_retries=3, min_backoff=0.01, max_backoff=0.05, on_retry=on_retry_handler)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("Timed out")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert retry_events == [("TimeoutError", 1), ("TimeoutError", 2)]

    def test_custom_exceptions(self):
        """Test retry with custom exception types."""

        class CustomNetworkError(Exception):
            pass

        call_count = 0

        @retry(max_retries=2, min_backoff=0.01, exceptions=(CustomNetworkError,))
        def flaky_with_custom():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise CustomNetworkError("Custom network error")
            return "success"

        result = flaky_with_custom()
        assert result == "success"
        assert call_count == 2


class TestIsTransientSubprocessError:
    """Tests for the is_transient_subprocess_error function."""

    def test_non_subprocess_error(self):
        """Test that non-CalledProcessError returns False."""
        assert is_transient_subprocess_error(ValueError("test")) is False

    def test_timeout_exit_code(self):
        """Test that exit code 124 (timeout) is transient."""
        error = subprocess.CalledProcessError(124, ["cmd"], stderr="")
        assert is_transient_subprocess_error(error) is True

    def test_connection_reset_in_stderr(self):
        """Test that connection reset in stderr is transient."""
        error = subprocess.CalledProcessError(1, ["cmd"], stderr="Connection reset by peer")
        assert is_transient_subprocess_error(error) is True

    def test_timeout_in_stderr(self):
        """Test that timeout message in stderr is transient."""
        error = subprocess.CalledProcessError(1, ["cmd"], stderr="Request timeout")
        assert is_transient_subprocess_error(error) is True

    def test_rate_limit_in_stderr(self):
        """Test that rate limit in stderr is transient."""
        error = subprocess.CalledProcessError(1, ["cmd"], stderr="API rate limit exceeded")
        assert is_transient_subprocess_error(error) is True

    def test_503_in_stderr(self):
        """Test that 503 error in stderr is transient."""
        error = subprocess.CalledProcessError(1, ["cmd"], stderr="HTTP 503 Service Unavailable")
        assert is_transient_subprocess_error(error) is True

    def test_auth_failure_not_transient(self):
        """Test that authentication failure is not transient."""
        error = subprocess.CalledProcessError(1, ["cmd"], stderr="Authentication failed")
        assert is_transient_subprocess_error(error) is False

    def test_not_found_not_transient(self):
        """Test that 404 errors are not transient."""
        error = subprocess.CalledProcessError(1, ["cmd"], stderr="HTTP 404 Not Found")
        assert is_transient_subprocess_error(error) is False

    def test_bytes_stderr(self):
        """Test handling of bytes stderr."""
        error = subprocess.CalledProcessError(1, ["cmd"], stderr=b"Connection timed out")
        assert is_transient_subprocess_error(error) is True


class TestRetrySubprocess:
    """Tests for the retry_subprocess decorator."""

    def test_retry_subprocess_on_timeout(self):
        """Test that subprocess timeout triggers retry."""
        call_count = 0

        @retry_subprocess(max_retries=2, min_backoff=0.01, max_backoff=0.05)
        def subprocess_call():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise subprocess.TimeoutExpired(["cmd"], 10)
            return "success"

        result = subprocess_call()
        assert result == "success"
        assert call_count == 2

    def test_retry_subprocess_on_transient_error(self):
        """Test that transient subprocess error triggers retry."""
        call_count = 0

        @retry_subprocess(max_retries=2, min_backoff=0.01, max_backoff=0.05)
        def subprocess_call():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                error = subprocess.CalledProcessError(1, ["cmd"], stderr="Connection reset")
                raise error
            return "success"

        result = subprocess_call()
        assert result == "success"
        assert call_count == 2

    def test_subprocess_auth_failure_not_retried(self):
        """Test that authentication failure is not retried."""
        call_count = 0

        @retry_subprocess(max_retries=3)
        def subprocess_call():
            nonlocal call_count
            call_count += 1
            error = subprocess.CalledProcessError(1, ["gh", "auth"], stderr="not logged in")
            raise error

        with pytest.raises(subprocess.CalledProcessError):
            subprocess_call()

        assert call_count == 1


class TestRetryBackoff:
    """Tests for exponential backoff behavior."""

    def test_exponential_backoff_timing(self):
        """Test that backoff increases exponentially."""
        sleep_times = []
        original_sleep = time.sleep

        def mock_sleep(seconds):
            sleep_times.append(seconds)
            # Actually sleep a tiny bit to avoid test flakiness
            original_sleep(0.001)

        call_count = 0

        @retry(max_retries=3, min_backoff=0.1, max_backoff=1.0)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("Always fails")

        with patch("time.sleep", side_effect=mock_sleep):
            with pytest.raises(TimeoutError):
                always_fails()

        # Should have 3 sleep calls (for 3 retries)
        assert len(sleep_times) == 3

        # Each backoff should roughly double (with jitter)
        # First: ~0.1s, Second: ~0.2s, Third: ~0.4s
        # Allow some variance for jitter
        assert 0.09 < sleep_times[0] < 0.15  # ~0.1 + jitter
        assert 0.18 < sleep_times[1] < 0.25  # ~0.2 + jitter
        assert 0.36 < sleep_times[2] < 0.5   # ~0.4 + jitter

    def test_max_backoff_cap(self):
        """Test that backoff is capped at max_backoff."""
        sleep_times = []
        original_sleep = time.sleep

        def mock_sleep(seconds):
            sleep_times.append(seconds)
            original_sleep(0.001)

        call_count = 0

        @retry(max_retries=5, min_backoff=1.0, max_backoff=2.0)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise TimeoutError("Always fails")

        with patch("time.sleep", side_effect=mock_sleep):
            with pytest.raises(TimeoutError):
                always_fails()

        # All sleep times should be <= max_backoff + max jitter (10% of max_backoff)
        for sleep_time in sleep_times:
            assert sleep_time <= 2.2  # 2.0 + 10% jitter


class TestRetryIntegration:
    """Integration tests for retry with real subprocess calls."""

    def test_retry_with_mock_subprocess(self):
        """Test retry decorator with mocked subprocess."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "success"

        call_count = 0

        def mock_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                error = subprocess.CalledProcessError(1, args[0], stderr="Connection timed out")
                raise error
            return mock_result

        @retry_subprocess(max_retries=3, min_backoff=0.01, max_backoff=0.05)
        def make_subprocess_call():
            return subprocess.run(["echo", "test"], capture_output=True, text=True, check=True)

        with patch("subprocess.run", side_effect=mock_run):
            result = make_subprocess_call()

        assert result.stdout == "success"
        assert call_count == 2
