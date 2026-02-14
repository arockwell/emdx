"""Tests for retry utility module."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from emdx.utils.retry import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_MAX_WAIT,
    DEFAULT_MIN_WAIT,
    NETWORK_EXCEPTIONS,
    SUBPROCESS_EXCEPTIONS,
    retry_api_call,
    retry_network,
    retry_subprocess,
    with_retry,
)


class TestWithRetry:
    """Tests for the with_retry decorator."""

    def test_successful_call_no_retry(self):
        """Function that succeeds should only be called once."""
        mock_func = MagicMock(return_value="success")

        @with_retry(max_retries=3)
        def test_func():
            return mock_func()

        result = test_func()
        assert result == "success"
        assert mock_func.call_count == 1

    def test_retries_on_exception(self):
        """Function should retry on specified exceptions."""
        mock_func = MagicMock(side_effect=[ConnectionError, ConnectionError, "success"])

        @with_retry(max_retries=3, min_wait=0.01, max_wait=0.02, retry_exceptions=(ConnectionError,))
        def test_func():
            return mock_func()

        result = test_func()
        assert result == "success"
        assert mock_func.call_count == 3

    def test_exhausts_retries_and_raises(self):
        """Function should raise after exhausting retries."""
        mock_func = MagicMock(side_effect=ConnectionError("connection failed"))

        @with_retry(max_retries=2, min_wait=0.01, max_wait=0.02, retry_exceptions=(ConnectionError,))
        def test_func():
            return mock_func()

        with pytest.raises(ConnectionError):
            test_func()
        assert mock_func.call_count == 2

    def test_no_retry_on_unspecified_exception(self):
        """Function should not retry on exceptions not in retry_exceptions."""
        mock_func = MagicMock(side_effect=ValueError("wrong type"))

        @with_retry(max_retries=3, retry_exceptions=(ConnectionError,))
        def test_func():
            return mock_func()

        with pytest.raises(ValueError):
            test_func()
        assert mock_func.call_count == 1


class TestRetryNetwork:
    """Tests for retry_network decorator."""

    def test_retries_on_connection_error(self):
        """Should retry on ConnectionError."""
        mock_func = MagicMock(side_effect=[ConnectionError, "success"])

        @retry_network(max_retries=3)
        def test_func():
            return mock_func()

        # Need to mock time to speed up test
        with patch("time.sleep"):
            result = test_func()
        assert result == "success"
        assert mock_func.call_count == 2

    def test_retries_on_timeout_error(self):
        """Should retry on TimeoutError."""
        mock_func = MagicMock(side_effect=[TimeoutError, "success"])

        @retry_network(max_retries=3)
        def test_func():
            return mock_func()

        with patch("time.sleep"):
            result = test_func()
        assert result == "success"

    def test_retries_on_os_error(self):
        """Should retry on OSError (network-related)."""
        mock_func = MagicMock(side_effect=[OSError, "success"])

        @retry_network(max_retries=3)
        def test_func():
            return mock_func()

        with patch("time.sleep"):
            result = test_func()
        assert result == "success"


class TestRetrySubprocess:
    """Tests for retry_subprocess decorator."""

    def test_retries_on_timeout_expired(self):
        """Should retry on subprocess.TimeoutExpired."""
        timeout_error = subprocess.TimeoutExpired(cmd=["test"], timeout=5)
        mock_func = MagicMock(side_effect=[timeout_error, "success"])

        @retry_subprocess(max_retries=3)
        def test_func():
            return mock_func()

        with patch("time.sleep"):
            result = test_func()
        assert result == "success"

    def test_no_retry_on_called_process_error(self):
        """Should NOT retry on CalledProcessError (command failed, not transient)."""
        called_error = subprocess.CalledProcessError(returncode=1, cmd=["test"])
        mock_func = MagicMock(side_effect=called_error)

        @retry_subprocess(max_retries=3)
        def test_func():
            return mock_func()

        with pytest.raises(subprocess.CalledProcessError):
            test_func()
        # Should only be called once - no retry on CalledProcessError
        assert mock_func.call_count == 1


class TestRetryApiCall:
    """Tests for retry_api_call decorator."""

    def test_retries_on_network_exceptions(self):
        """Should retry on network exceptions."""
        mock_func = MagicMock(side_effect=[ConnectionError, "success"])

        @retry_api_call(max_retries=3)
        def test_func():
            return mock_func()

        with patch("time.sleep"):
            result = test_func()
        assert result == "success"

    def test_retries_on_additional_exceptions(self):
        """Should retry on additional specified exceptions."""

        class CustomAPIError(Exception):
            pass

        mock_func = MagicMock(side_effect=[CustomAPIError, "success"])

        @retry_api_call(max_retries=3, additional_exceptions=(CustomAPIError,))
        def test_func():
            return mock_func()

        with patch("time.sleep"):
            result = test_func()
        assert result == "success"


class TestConstants:
    """Tests for module constants."""

    def test_default_values(self):
        """Default values should be reasonable."""
        assert DEFAULT_MAX_RETRIES == 3
        assert DEFAULT_MIN_WAIT == 1
        assert DEFAULT_MAX_WAIT == 10

    def test_network_exceptions_tuple(self):
        """Network exceptions should be a tuple of exception types."""
        assert isinstance(NETWORK_EXCEPTIONS, tuple)
        assert ConnectionError in NETWORK_EXCEPTIONS
        assert TimeoutError in NETWORK_EXCEPTIONS
        assert OSError in NETWORK_EXCEPTIONS

    def test_subprocess_exceptions_tuple(self):
        """Subprocess exceptions should be a tuple."""
        assert isinstance(SUBPROCESS_EXCEPTIONS, tuple)
        assert subprocess.TimeoutExpired in SUBPROCESS_EXCEPTIONS
        # CalledProcessError should NOT be in retry exceptions
        assert subprocess.CalledProcessError not in SUBPROCESS_EXCEPTIONS
