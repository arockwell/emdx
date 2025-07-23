"""
Document formatting and validation utilities for emdx
"""

import re
from typing import Optional, Tuple, Dict, Any, List


class FormatValidationError(ValueError):
    """Raised when document content fails validation"""
    pass


class DocumentFormatter:
    """
    Document formatter that validates and normalizes content.
    
    Features:
    - Validates non-empty content
    - Normalizes line endings (CRLF -> LF)
    - Removes trailing whitespace from lines
    - Ensures single newline at end of document
    - Preserves Unicode/emoji characters
    - Detects binary content
    """
    
    def __init__(
        self,
        strict: bool = False,
        max_line_length: Optional[int] = None,
        max_document_size: Optional[int] = None,
        allow_tabs: bool = True,
        require_final_newline: bool = True,
        generate_report: bool = False
    ):
        """
        Initialize formatter with configuration options.
        
        Args:
            strict: If True, raises errors for formatting issues instead of fixing
            max_line_length: Maximum allowed line length (None = no limit)
            max_document_size: Maximum document size in bytes (None = no limit)
            allow_tabs: Whether to allow tab characters
            require_final_newline: Whether to require/add final newline
            generate_report: Whether to generate detailed formatting report
        """
        self.strict = strict
        self.max_line_length = max_line_length
        self.max_document_size = max_document_size
        self.allow_tabs = allow_tabs
        self.require_final_newline = require_final_newline
        self.generate_report = generate_report
    
    def validate_and_format(self, content: Optional[str]) -> str:
        """
        Validate and format document content.
        
        Args:
            content: Raw document content
            
        Returns:
            Formatted content
            
        Raises:
            FormatValidationError: If content fails validation
        """
        if self.generate_report:
            formatted, _ = self.validate_and_format_with_report(content)
            return formatted
        
        # Check for None or empty content
        if content is None or content == "":
            raise FormatValidationError("Document content cannot be empty")
        
        # Check for binary content
        if self._contains_binary(content):
            raise FormatValidationError("Document contains binary content")
        
        # Check for whitespace-only content
        if not content.strip():
            raise FormatValidationError("Document content cannot be empty")
        
        # Check document size
        if self.max_document_size and len(content.encode('utf-8')) > self.max_document_size:
            raise FormatValidationError(
                f"Document exceeds maximum size of {self.max_document_size} bytes"
            )
        
        # Process content
        formatted = content
        
        # Remove BOM if present
        if formatted.startswith('\ufeff'):
            formatted = formatted[1:]
        
        # Normalize line endings (CRLF -> LF)
        formatted = formatted.replace('\r\n', '\n').replace('\r', '\n')
        
        # Process lines
        lines = formatted.split('\n')
        processed_lines = []
        
        for i, line in enumerate(lines):
            # Remove trailing whitespace
            processed_line = line.rstrip()
            
            # Check line length
            if self.max_line_length and len(processed_line) > self.max_line_length:
                raise FormatValidationError(
                    f"Line {i+1} exceeds maximum length of {self.max_line_length}"
                )
            
            # Check for tabs
            if not self.allow_tabs and '\t' in processed_line:
                raise FormatValidationError(f"Line {i+1} contains tabs")
            
            processed_lines.append(processed_line)
        
        # Rejoin lines
        formatted = '\n'.join(processed_lines)
        
        # Remove multiple trailing newlines first
        while formatted.endswith('\n\n'):
            formatted = formatted[:-1]
        
        # Ensure final newline
        if self.require_final_newline and formatted and not formatted.endswith('\n'):
            formatted += '\n'
        
        # Final validation - ensure we still have content
        if not formatted.strip():
            raise FormatValidationError("Document becomes empty after formatting")
        
        return formatted
    
    def validate_and_format_with_report(
        self, content: Optional[str]
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Validate and format with detailed report.
        
        Returns:
            Tuple of (formatted_content, report_dict)
        """
        report = {
            'changes_made': False,
            'line_endings_normalized': False,
            'trailing_whitespace_removed': False,
            'final_newline_added': False,
            'bom_removed': False,
            'lines_affected': [],
            'original_size': 0,
            'formatted_size': 0
        }
        
        if content is None or content == "":
            raise FormatValidationError("Document content cannot be empty")
        
        report['original_size'] = len(content)
        original = content
        
        # Check for binary content
        if self._contains_binary(content):
            raise FormatValidationError("Document contains binary content")
        
        # Check for whitespace-only content
        if not content.strip():
            raise FormatValidationError("Document content cannot be empty")
        
        formatted = content
        
        # Remove BOM
        if formatted.startswith('\ufeff'):
            formatted = formatted[1:]
            report['bom_removed'] = True
            report['changes_made'] = True
        
        # Normalize line endings
        if '\r\n' in formatted or '\r' in formatted:
            formatted = formatted.replace('\r\n', '\n').replace('\r', '\n')
            report['line_endings_normalized'] = True
            report['changes_made'] = True
        
        # Process lines
        lines = formatted.split('\n')
        processed_lines = []
        
        for i, line in enumerate(lines):
            original_line = line
            processed_line = line.rstrip()
            
            if original_line != processed_line:
                report['trailing_whitespace_removed'] = True
                report['lines_affected'].append(i + 1)
                report['changes_made'] = True
            
            processed_lines.append(processed_line)
        
        formatted = '\n'.join(processed_lines)
        
        # Remove multiple trailing newlines first
        while formatted.endswith('\n\n'):
            formatted = formatted[:-1]
            report['changes_made'] = True
        
        # Ensure final newline
        if self.require_final_newline and formatted and not formatted.endswith('\n'):
            formatted += '\n'
            report['final_newline_added'] = True
            report['changes_made'] = True
        
        report['formatted_size'] = len(formatted)
        
        return formatted, report
    
    def format_title(self, title: str) -> str:
        """
        Format document title.
        
        Args:
            title: Raw title string
            
        Returns:
            Formatted title
            
        Raises:
            FormatValidationError: If title is empty after formatting
        """
        if not title:
            raise FormatValidationError("Document title cannot be empty")
        
        # Strip all whitespace
        formatted = title.strip()
        
        if not formatted:
            raise FormatValidationError("Document title cannot be only whitespace")
        
        return formatted
    
    def _contains_binary(self, content: str) -> bool:
        """Check if content contains binary/control characters"""
        # Allow tab (9), newline (10), carriage return (13)
        allowed_control_chars = {9, 10, 13}
        
        for char in content:
            code = ord(char)
            # Control characters (except allowed ones)
            if code < 32 and code not in allowed_control_chars:
                return True
            # Null byte
            if code == 0:
                return True
        
        return False
    
    def _is_binary(self, content: bytes) -> bool:
        """Check if byte content is binary"""
        # Check for null bytes
        if b'\x00' in content:
            return True
        
        # Check for high ratio of non-text bytes
        non_text_bytes = 0
        sample = content[:1024]  # Check first 1KB
        
        for byte in sample:
            if byte < 32 and byte not in (9, 10, 13):  # Tab, LF, CR
                non_text_bytes += 1
            elif byte >= 127:  # High bytes that aren't valid UTF-8
                # Simple check - if it's really high, likely binary
                if byte >= 0xF0:
                    non_text_bytes += 1
        
        # If more than 30% non-text, consider binary
        return non_text_bytes > len(sample) * 0.3
    
    def _count_lines(self, content: str) -> int:
        """Count number of lines in content"""
        if not content:
            return 0
        lines = content.split('\n')
        # Don't count empty final line from trailing newline
        if lines and lines[-1] == '':
            return len(lines) - 1
        return len(lines)


# Convenience functions
def format_document(content: str, **kwargs) -> str:
    """
    Format document content with default settings.
    
    This is a convenience function that creates a formatter
    and processes the content in one step.
    """
    formatter = DocumentFormatter(**kwargs)
    return formatter.validate_and_format(content)


def validate_content(content: str) -> bool:
    """
    Check if content is valid without modifying it.
    
    Returns:
        True if content is valid, False otherwise
    """
    try:
        formatter = DocumentFormatter()
        formatter.validate_and_format(content)
        return True
    except FormatValidationError:
        return False