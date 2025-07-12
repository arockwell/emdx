"""
Tests for the standardized error handling system
"""

import pytest
import tempfile
from pathlib import Path

from emdx.error_handling import (
    EmdxError,
    DatabaseError,
    FileSystemError,
    ValidationError,
    NetworkError,
    ExternalToolError,
    ErrorSeverity,
    ErrorCategory,
    setup_logging,
    handle_error,
    safe_operation,
    database_connection_error,
    file_not_found_error,
    permission_denied_error,
    invalid_input_error,
)


class TestEmdxError:
    """Test custom error classes"""

    def test_basic_error_creation(self):
        """Test creating a basic EmdxError"""
        error = EmdxError(
            message="Test error message",
            category=ErrorCategory.INTERNAL,
            severity=ErrorSeverity.ERROR
        )
        
        assert error.message == "Test error message"
        assert error.category == ErrorCategory.INTERNAL
        assert error.severity == ErrorSeverity.ERROR
        assert error.details == {}
        assert error.suggestion is None
        assert error.exit_code == 1

    def test_error_with_details_and_suggestion(self):
        """Test creating an error with details and suggestion"""
        error = DatabaseError(
            message="Database connection failed",
            details={"db_path": "/tmp/test.db", "error_code": 123},
            suggestion="Check if the database file exists",
            exit_code=2
        )
        
        assert error.message == "Database connection failed"
        assert error.category == ErrorCategory.DATABASE
        assert error.severity == ErrorSeverity.ERROR
        assert error.details["db_path"] == "/tmp/test.db"
        assert error.details["error_code"] == 123
        assert error.suggestion == "Check if the database file exists"
        assert error.exit_code == 2

    def test_specialized_error_classes(self):
        """Test that specialized error classes have correct categories"""
        db_error = DatabaseError("DB error")
        fs_error = FileSystemError("FS error")
        val_error = ValidationError("Validation error")
        net_error = NetworkError("Network error")
        tool_error = ExternalToolError("Tool error")
        
        assert db_error.category == ErrorCategory.DATABASE
        assert fs_error.category == ErrorCategory.FILE_SYSTEM
        assert val_error.category == ErrorCategory.VALIDATION
        assert net_error.category == ErrorCategory.NETWORK
        assert tool_error.category == ErrorCategory.EXTERNAL_TOOL


class TestErrorHelpers:
    """Test error helper functions"""

    def test_database_connection_error(self):
        """Test database connection error helper"""
        db_path = Path("/tmp/test.db")
        original_error = Exception("Connection refused")
        
        error = database_connection_error(db_path, original_error)
        
        assert isinstance(error, DatabaseError)
        assert "Cannot connect to database" in error.message
        assert error.details["db_path"] == str(db_path)
        assert error.details["original_error"] == str(original_error)
        assert error.suggestion is not None

    def test_file_not_found_error(self):
        """Test file not found error helper"""
        file_path = Path("/tmp/missing.txt")
        
        error = file_not_found_error(file_path)
        
        assert isinstance(error, FileSystemError)
        assert "File not found" in error.message
        assert error.details["file_path"] == str(file_path)

    def test_permission_denied_error(self):
        """Test permission denied error helper"""
        path = Path("/root/secret.txt")
        operation = "read"
        
        error = permission_denied_error(path, operation)
        
        assert isinstance(error, FileSystemError)
        assert "Permission denied" in error.message
        assert error.details["path"] == str(path)
        assert error.details["operation"] == operation

    def test_invalid_input_error(self):
        """Test invalid input error helper"""
        error = invalid_input_error("email", "invalid-email", "valid email address")
        
        assert isinstance(error, ValidationError)
        assert "Invalid email" in error.message
        assert error.details["field"] == "email"
        assert error.details["value"] == "invalid-email"
        assert error.details["expected"] == "valid email address"


class TestSafeOperation:
    """Test the safe_operation decorator"""

    def test_safe_operation_success(self):
        """Test safe_operation decorator with successful operation"""
        @safe_operation("test operation")
        def successful_function(value):
            return value * 2
        
        result = successful_function(5)
        assert result == 10

    def test_safe_operation_with_emdx_error(self):
        """Test safe_operation decorator with EmdxError"""
        @safe_operation("test operation")
        def failing_function():
            raise ValidationError("Test validation error")
        
        with pytest.raises(SystemExit):
            failing_function()

    def test_safe_operation_with_generic_error(self):
        """Test safe_operation decorator with generic exception"""
        @safe_operation("test operation")
        def failing_function():
            raise ValueError("Generic error")
        
        with pytest.raises(SystemExit):
            failing_function()


class TestLoggingSetup:
    """Test logging configuration"""

    def test_setup_logging_default(self):
        """Test default logging setup"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"
            setup_logging(log_file=log_file)
            
            # Check that log file is created
            assert log_file.exists()

    def test_setup_logging_verbose(self):
        """Test verbose logging setup"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test_verbose.log"
            setup_logging(verbose=True, log_file=log_file)
            
            assert log_file.exists()

    def test_setup_logging_quiet(self):
        """Test quiet logging setup"""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test_quiet.log"
            setup_logging(quiet=True, log_file=log_file)
            
            assert log_file.exists()


class TestErrorHandling:
    """Test error handling functions"""

    def test_handle_error_with_emdx_error(self):
        """Test handling EmdxError instances"""
        error = ValidationError("Test validation error")
        
        with pytest.raises(SystemExit):
            handle_error(error, "test operation")

    def test_handle_error_with_generic_error(self):
        """Test handling generic exceptions"""
        error = ValueError("Generic error")
        
        with pytest.raises(SystemExit):
            handle_error(error, "test operation")