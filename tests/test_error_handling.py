"""Tests for emdx error handling utilities."""

import logging
from unittest.mock import MagicMock, Mock, patch

import pytest
import typer
from rich.console import Console

from emdx.utils.error_handling import (
    EmdxDatabaseError,
    EmdxError,
    EmdxExecutionError,
    EmdxIOError,
    EmdxNotFoundError,
    EmdxValidationError,
    database_operation,
    ensure_database,
    handle_cli_error,
    log_and_raise,
    log_errors,
    require_document,
    retry_on_error,
    safe_query_one,
    safe_widget_call,
    validate_exists,
    with_fallback,
)


class TestCustomExceptions:
    """Test custom exception classes."""

    def test_emdx_error_basic(self):
        """Test basic EmdxError creation."""
        error = EmdxError("Test error")
        assert error.message == "Test error"
        assert error.details is None
        assert str(error) == "Test error"

    def test_emdx_error_with_details(self):
        """Test EmdxError with details."""
        error = EmdxError("Test error", details="Additional info")
        assert error.message == "Test error"
        assert error.details == "Additional info"

    def test_emdx_database_error(self):
        """Test EmdxDatabaseError inheritance."""
        error = EmdxDatabaseError("DB connection failed")
        assert isinstance(error, EmdxError)
        assert error.message == "DB connection failed"

    def test_emdx_validation_error(self):
        """Test EmdxValidationError inheritance."""
        error = EmdxValidationError("Invalid input", details="Expected integer")
        assert isinstance(error, EmdxError)
        assert error.details == "Expected integer"

    def test_emdx_io_error(self):
        """Test EmdxIOError inheritance."""
        error = EmdxIOError("File not readable")
        assert isinstance(error, EmdxError)

    def test_emdx_not_found_error(self):
        """Test EmdxNotFoundError with resource info."""
        error = EmdxNotFoundError("Document", 42)
        assert error.resource_type == "Document"
        assert error.identifier == 42
        assert error.message == "Document '42' not found"

    def test_emdx_execution_error(self):
        """Test EmdxExecutionError inheritance."""
        error = EmdxExecutionError("Execution failed")
        assert isinstance(error, EmdxError)


class TestHandleCliError:
    """Test the handle_cli_error decorator."""

    def test_successful_execution(self):
        """Test decorator allows successful execution."""
        console = Console()

        @handle_cli_error("testing", console=console)
        def successful_func():
            return "success"

        result = successful_func()
        assert result == "success"

    def test_handles_generic_exception(self):
        """Test decorator handles generic exceptions."""
        console = Console()

        @handle_cli_error("testing", console=console)
        def failing_func():
            raise ValueError("test error")

        with pytest.raises(typer.Exit) as exc_info:
            failing_func()
        assert exc_info.value.exit_code == 1

    def test_handles_emdx_not_found_error(self):
        """Test decorator handles EmdxNotFoundError."""
        console = Console()

        @handle_cli_error("finding document", console=console)
        def not_found_func():
            raise EmdxNotFoundError("Document", 123)

        with pytest.raises(typer.Exit) as exc_info:
            not_found_func()
        assert exc_info.value.exit_code == 1

    def test_handles_emdx_validation_error(self):
        """Test decorator handles EmdxValidationError."""
        console = Console()

        @handle_cli_error("validating", console=console)
        def validation_func():
            raise EmdxValidationError("Invalid", details="Must be positive")

        with pytest.raises(typer.Exit) as exc_info:
            validation_func()
        assert exc_info.value.exit_code == 1

    def test_handles_emdx_database_error(self):
        """Test decorator handles EmdxDatabaseError."""
        console = Console()

        @handle_cli_error("querying", console=console)
        def db_func():
            raise EmdxDatabaseError("Connection failed")

        with pytest.raises(typer.Exit) as exc_info:
            db_func()
        assert exc_info.value.exit_code == 1

    def test_reraises_typer_exit(self):
        """Test decorator re-raises typer.Exit."""
        console = Console()

        @handle_cli_error("testing", console=console)
        def exit_func():
            raise typer.Exit(42)

        with pytest.raises(typer.Exit) as exc_info:
            exit_func()
        assert exc_info.value.exit_code == 42

    def test_handles_typer_abort(self):
        """Test decorator handles typer.Abort."""
        console = Console()

        @handle_cli_error("testing", console=console)
        def abort_func():
            raise typer.Abort()

        with pytest.raises(typer.Exit) as exc_info:
            abort_func()
        assert exc_info.value.exit_code == 0

    def test_custom_exit_code(self):
        """Test decorator respects custom exit code."""
        console = Console()

        @handle_cli_error("testing", console=console, exit_code=5)
        def failing_func():
            raise RuntimeError("test")

        with pytest.raises(typer.Exit) as exc_info:
            failing_func()
        assert exc_info.value.exit_code == 5


class TestEnsureDatabase:
    """Test the ensure_database function."""

    def test_successful_initialization(self):
        """Test successful database initialization."""
        with patch("emdx.database.db.ensure_schema") as mock_ensure:
            ensure_database()
            mock_ensure.assert_called_once()

    def test_handles_exception(self):
        """Test exception handling during initialization."""
        with patch("emdx.database.db.ensure_schema", side_effect=Exception("DB error")):
            with pytest.raises(EmdxDatabaseError) as exc_info:
                ensure_database()
            assert "Failed to initialize database" in str(exc_info.value.message)


class TestDatabaseOperation:
    """Test the database_operation context manager."""

    def test_successful_operation(self):
        """Test successful database operation."""
        with database_operation("saving") as _:
            pass  # No exception

    def test_handles_exception(self):
        """Test exception handling in database operation."""
        with pytest.raises(EmdxDatabaseError):
            with database_operation("saving"):
                raise ValueError("Something went wrong")

    def test_preserves_emdx_database_error(self):
        """Test that EmdxDatabaseError is re-raised as-is."""
        with pytest.raises(EmdxDatabaseError) as exc_info:
            with database_operation("saving"):
                raise EmdxDatabaseError("Original error")
        assert "Original error" in str(exc_info.value.message)


class TestRequireDocument:
    """Test the require_document function."""

    def test_returns_document_when_found(self):
        """Test returning document when found."""
        mock_doc = {"id": 1, "title": "Test"}
        with patch("emdx.models.documents.get_document", return_value=mock_doc):
            result = require_document(1)
            assert result == mock_doc

    def test_raises_when_not_found(self):
        """Test raising EmdxNotFoundError when not found."""
        with patch("emdx.models.documents.get_document", return_value=None):
            with pytest.raises(EmdxNotFoundError) as exc_info:
                require_document(999)
            assert exc_info.value.resource_type == "Document"
            assert exc_info.value.identifier == 999


class TestValidateExists:
    """Test the validate_exists function."""

    def test_validates_existing_path(self, tmp_path):
        """Test validation of existing path."""
        existing_file = tmp_path / "test.txt"
        existing_file.touch()
        validate_exists(str(existing_file))  # Should not raise

    def test_raises_for_nonexistent_path(self):
        """Test raising EmdxNotFoundError for nonexistent path."""
        with pytest.raises(EmdxNotFoundError) as exc_info:
            validate_exists("/nonexistent/path/file.txt", "File")
        assert exc_info.value.resource_type == "File"


class TestLogAndRaise:
    """Test the log_and_raise function."""

    def test_logs_and_raises(self, caplog):
        """Test that function logs and raises wrapped exception."""
        original_error = ValueError("Original")
        with caplog.at_level(logging.ERROR):
            with pytest.raises(EmdxError):
                log_and_raise(original_error, "Test operation failed")
        assert "Test operation failed" in caplog.text

    def test_custom_error_class(self):
        """Test custom error class is used."""
        original_error = IOError("File error")
        with pytest.raises(EmdxIOError):
            log_and_raise(original_error, "IO failed", error_class=EmdxIOError)


class TestLogErrors:
    """Test the log_errors context manager."""

    def test_logs_on_exception(self, caplog):
        """Test logging on exception."""
        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError):
                with log_errors("testing"):
                    raise ValueError("Test error")
        assert "Error during testing" in caplog.text

    def test_no_reraise_option(self, caplog):
        """Test reraise=False suppresses exception."""
        with caplog.at_level(logging.ERROR):
            with log_errors("testing", reraise=False):
                raise ValueError("Suppressed")
        assert "Error during testing" in caplog.text


class TestWithFallback:
    """Test the with_fallback function."""

    def test_returns_primary_on_success(self):
        """Test returning primary result on success."""
        result = with_fallback(
            primary_func=lambda: "primary",
            fallback_func=lambda: "fallback",
        )
        assert result == "primary"

    def test_returns_fallback_on_failure(self):
        """Test returning fallback result on failure."""

        def failing():
            raise ValueError("fail")

        result = with_fallback(
            primary_func=failing,
            fallback_func=lambda: "fallback",
        )
        assert result == "fallback"

    def test_respects_exception_types(self):
        """Test respecting specific exception types."""

        def failing():
            raise RuntimeError("wrong type")

        # RuntimeError should not be caught when only ValueError is specified
        with pytest.raises(RuntimeError):
            with_fallback(
                primary_func=failing,
                fallback_func=lambda: "fallback",
                exception_types=(ValueError,),
            )


class TestRetryOnError:
    """Test the retry_on_error decorator."""

    def test_succeeds_on_first_try(self):
        """Test successful execution on first try."""
        call_count = 0

        @retry_on_error(max_attempts=3)
        def succeeding_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = succeeding_func()
        assert result == "success"
        assert call_count == 1

    def test_retries_on_failure(self):
        """Test retrying on failure."""
        call_count = 0

        @retry_on_error(max_attempts=3)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Flaky")
            return "success"

        result = flaky_func()
        assert result == "success"
        assert call_count == 3

    def test_raises_after_max_attempts(self):
        """Test raising after max attempts exhausted."""
        call_count = 0

        @retry_on_error(max_attempts=2)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")

        with pytest.raises(ValueError):
            always_fails()
        assert call_count == 2

    def test_respects_exception_types(self):
        """Test respecting specific exception types."""
        call_count = 0

        @retry_on_error(max_attempts=3, exception_types=(ValueError,))
        def runtime_error_func():
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Not a ValueError")

        with pytest.raises(RuntimeError):
            runtime_error_func()
        assert call_count == 1  # Should not retry


class TestSafeQueryOne:
    """Test the safe_query_one function."""

    def test_returns_widget_on_success(self):
        """Test returning widget on successful query."""
        mock_widget = Mock()
        mock_app = Mock()
        mock_app.query_one = Mock(return_value=mock_widget)

        result = safe_query_one(mock_app, "#test", Mock)
        assert result == mock_widget

    def test_returns_default_on_failure(self):
        """Test returning default on failed query."""
        mock_app = Mock()
        mock_app.query_one = Mock(side_effect=Exception("Query failed"))

        result = safe_query_one(mock_app, "#missing", Mock, default="default")
        assert result == "default"

    def test_returns_none_by_default(self):
        """Test returning None when no default specified."""
        mock_app = Mock()
        mock_app.query_one = Mock(side_effect=Exception("Query failed"))

        result = safe_query_one(mock_app, "#missing", Mock)
        assert result is None


class TestSafeWidgetCall:
    """Test the safe_widget_call function."""

    def test_calls_method_successfully(self):
        """Test successful method call."""
        mock_widget = Mock()
        mock_widget.test_method = Mock(return_value="result")

        result = safe_widget_call(mock_widget, "test_method", "arg1", kwarg1="val")
        assert result == "result"
        mock_widget.test_method.assert_called_once_with("arg1", kwarg1="val")

    def test_returns_default_on_missing_method(self):
        """Test returning default for missing method."""
        mock_widget = Mock(spec=[])  # No methods

        result = safe_widget_call(mock_widget, "missing_method", default="default")
        assert result == "default"

    def test_returns_default_on_exception(self):
        """Test returning default on method exception."""
        mock_widget = Mock()
        mock_widget.failing_method = Mock(side_effect=Exception("Failed"))

        result = safe_widget_call(mock_widget, "failing_method", default="default")
        assert result == "default"
