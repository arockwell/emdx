"""Document formatting and validation module."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorLevel(Enum):
    """Severity levels for formatting issues."""
    ERROR = "error"      # Must fix
    WARNING = "warning"  # Should fix
    INFO = "info"        # Nice to have


@dataclass
class FormatIssue:
    """Represents a formatting issue in a document."""
    line: int
    column: Optional[int]
    level: ErrorLevel
    message: str
    rule: str
    fixable: bool = False


@dataclass
class FormatResult:
    """Result of formatting validation."""
    valid: bool
    issues: list[FormatIssue]
    fixed_content: Optional[str] = None
    stats: dict[str, int] = None

    def __post_init__(self):
        if self.stats is None:
            self.stats = {
                "errors": sum(1 for i in self.issues if i.level == ErrorLevel.ERROR),
                "warnings": sum(1 for i in self.issues if i.level == ErrorLevel.WARNING),
                "info": sum(1 for i in self.issues if i.level == ErrorLevel.INFO),
                "fixable": sum(1 for i in self.issues if i.fixable)
            }


class DocumentFormatter:
    """Validates and formats markdown documents according to EMDX standards."""

    # Regex patterns for validation
    HEADER_PATTERN = re.compile(r'^(#{1,6})\s+(.+?)(\s*#*)?$', re.MULTILINE)
    CODE_BLOCK_PATTERN = re.compile(r'^```(\w*)?$', re.MULTILINE)
    TRAILING_WHITESPACE = re.compile(r'[ \t]+$', re.MULTILINE)
    MULTIPLE_BLANKS = re.compile(r'\n{3,}')
    LIST_MARKER = re.compile(r'^(\s*)([*+-])\s+', re.MULTILINE)
    ORDERED_LIST = re.compile(r'^(\s*)(\d+)\.\s+', re.MULTILINE)

    # Line length limit for prose
    MAX_LINE_LENGTH = 100

    def validate(self, content: str, auto_fix: bool = False) -> FormatResult:
        """Validate document formatting."""
        issues = []
        lines = content.splitlines()
        fixed_content = content if auto_fix else None

        # Check for title
        if not self._has_title(lines):
            issues.append(FormatIssue(
                line=1, column=None, level=ErrorLevel.ERROR,
                message="Document must start with H1 title",
                rule="missing-title", fixable=False
            ))

        # Check line lengths
        issues.extend(self._check_line_lengths(lines))

        # Check header hierarchy
        issues.extend(self._check_header_hierarchy(lines))

        # Check code blocks
        issues.extend(self._check_code_blocks(lines))

        # Check whitespace issues
        whitespace_issues, fixed = self._check_whitespace(content)
        issues.extend(whitespace_issues)
        if auto_fix and fixed:
            fixed_content = fixed

        # Check list consistency
        issues.extend(self._check_list_consistency(lines))

        # Apply all auto-fixes if requested
        if auto_fix:
            from emdx.utils.format_helpers import apply_auto_fixes
            fixed_content, _ = apply_auto_fixes(fixed_content or content)

        # Check final newline (after other fixes to get correct line count)
        if not (fixed_content or content).endswith('\n'):
            issues.append(FormatIssue(
                line=len(lines), column=None, level=ErrorLevel.WARNING,
                message="File should end with newline",
                rule="missing-final-newline", fixable=True
            ))

        # Determine validity
        has_errors = any(i.level == ErrorLevel.ERROR for i in issues)

        return FormatResult(
            valid=not has_errors,
            issues=issues,
            fixed_content=fixed_content if auto_fix else None
        )

    def format(self, content: str) -> str:
        """Auto-format document fixing all fixable issues."""
        result = self.validate(content, auto_fix=True)
        return result.fixed_content or content

    def _has_title(self, lines: list[str]) -> bool:
        """Check if document has H1 title."""
        for line in lines:
            if line.strip():
                return line.strip().startswith('# ')
        return False

    def _check_line_lengths(self, lines: list[str]) -> list[FormatIssue]:
        """Check for lines exceeding maximum length."""
        issues = []
        in_code_block = False

        for i, line in enumerate(lines, 1):
            # Toggle code block state
            if line.strip().startswith('```'):
                in_code_block = not in_code_block
                continue

            # Skip length check in code blocks and for URLs
            if in_code_block or 'http://' in line or 'https://' in line:
                continue

            if len(line) > self.MAX_LINE_LENGTH:
                issues.append(FormatIssue(
                    line=i, column=self.MAX_LINE_LENGTH + 1,
                    level=ErrorLevel.ERROR,
                    message=f"Line exceeds {self.MAX_LINE_LENGTH} characters",
                    rule="line-too-long", fixable=False
                ))

        return issues

    def _check_header_hierarchy(self, lines: list[str]) -> list[FormatIssue]:
        """Check for proper header hierarchy."""
        issues = []
        headers = []

        for i, line in enumerate(lines, 1):
            match = self.HEADER_PATTERN.match(line.strip())
            if match:
                level = len(match.group(1))
                headers.append((i, level))

                # Check for trailing punctuation
                title = match.group(2).strip()
                if title and title[-1] in '.,:;!' and not title.endswith('?'):
                    issues.append(FormatIssue(
                        line=i, column=None, level=ErrorLevel.WARNING,
                        message="Headers should not have trailing punctuation (except ?)",
                        rule="header-punctuation", fixable=True
                    ))

        # Check hierarchy
        for i in range(1, len(headers)):
            prev_line, prev_level = headers[i-1]
            curr_line, curr_level = headers[i]

            if curr_level > prev_level + 1:
                issues.append(FormatIssue(
                    line=curr_line, column=None, level=ErrorLevel.ERROR,
                    message=f"Header level skipped (H{prev_level} to H{curr_level})",
                    rule="header-hierarchy", fixable=False
                ))

        return issues

    def _check_code_blocks(self, lines: list[str]) -> list[FormatIssue]:
        """Check code block formatting."""
        issues = []
        in_code_block = False
        code_block_start = 0

        for i, line in enumerate(lines, 1):
            if line.strip().startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    code_block_start = i

                    # Check for language identifier
                    lang = line.strip()[3:].strip()
                    if not lang:
                        issues.append(FormatIssue(
                            line=i, column=None, level=ErrorLevel.WARNING,
                            message="Code block should specify language",
                            rule="missing-code-language", fixable=False
                        ))
                else:
                    in_code_block = False

        # Check for unclosed code block
        if in_code_block:
            issues.append(FormatIssue(
                line=code_block_start, column=None, level=ErrorLevel.ERROR,
                message="Unclosed code block",
                rule="unclosed-code-block", fixable=False
            ))

        return issues

    def _check_whitespace(self, content: str) -> tuple[list[FormatIssue], Optional[str]]:
        """Check and fix whitespace issues."""
        issues = []
        fixed = content

        # Trailing whitespace
        if self.TRAILING_WHITESPACE.search(content):
            for i, line in enumerate(content.splitlines(), 1):
                if line != line.rstrip():
                    issues.append(FormatIssue(
                        line=i, column=len(line.rstrip()) + 1,
                        level=ErrorLevel.WARNING,
                        message="Trailing whitespace",
                        rule="trailing-whitespace", fixable=True
                    ))
            fixed = self.TRAILING_WHITESPACE.sub('', fixed)

        # Multiple blank lines
        if self.MULTIPLE_BLANKS.search(content):
            issues.append(FormatIssue(
                line=0, column=None, level=ErrorLevel.WARNING,
                message="Multiple consecutive blank lines",
                rule="multiple-blanks", fixable=True
            ))
            fixed = self.MULTIPLE_BLANKS.sub('\n\n', fixed)

        # Tabs
        if '\t' in content:
            for i, line in enumerate(content.splitlines(), 1):
                if '\t' in line:
                    issues.append(FormatIssue(
                        line=i, column=line.index('\t') + 1,
                        level=ErrorLevel.WARNING,
                        message="Tab character found (use spaces)",
                        rule="no-tabs", fixable=True
                    ))
            fixed = fixed.replace('\t', '    ')

        return issues, fixed if fixed != content else None

    def _check_list_consistency(self, lines: list[str]) -> list[FormatIssue]:
        """Check for consistent list markers."""
        issues = []
        list_markers = set()

        for i, line in enumerate(lines, 1):
            match = self.LIST_MARKER.match(line)
            if match:
                marker = match.group(2)
                list_markers.add(marker)

                if marker != '-':
                    issues.append(FormatIssue(
                        line=i, column=None, level=ErrorLevel.WARNING,
                        message=f"Use '-' for unordered lists (not '{marker}')",
                        rule="list-marker-consistency", fixable=True
                    ))

        return issues
