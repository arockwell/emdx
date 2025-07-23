"""Helper functions for document formatting."""

import re
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.text import Text

from emdx.utils.formatter import ErrorLevel, FormatResult


def format_issue_table(result: FormatResult, console: Optional[Console] = None) -> Table:
    """Create a rich table displaying formatting issues."""
    if console is None:
        console = Console()

    table = Table(title="Formatting Issues", show_header=True)
    table.add_column("Line", style="cyan", width=6)
    table.add_column("Level", width=8)
    table.add_column("Rule", style="blue", width=25)
    table.add_column("Message", style="white")

    # Sort issues by line number
    sorted_issues = sorted(result.issues, key=lambda x: x.line)

    for issue in sorted_issues:
        level_style = {
            ErrorLevel.ERROR: "red bold",
            ErrorLevel.WARNING: "yellow",
            ErrorLevel.INFO: "blue"
        }[issue.level]

        level_text = Text(issue.level.value.upper(), style=level_style)
        line_text = str(issue.line) if issue.line > 0 else "-"

        table.add_row(
            line_text,
            level_text,
            issue.rule,
            issue.message
        )

    return table


def format_summary(result: FormatResult) -> str:
    """Generate a summary of formatting validation results."""
    if result.valid:
        if not result.issues:
            return "✅ Document formatting is valid!"
        else:
            return f"✅ Document is valid with {len(result.issues)} warnings/suggestions"
    else:
        stats = result.stats
        parts = []
        if stats["errors"] > 0:
            parts.append(f"{stats['errors']} errors")
        if stats["warnings"] > 0:
            parts.append(f"{stats['warnings']} warnings")
        if stats["info"] > 0:
            parts.append(f"{stats['info']} suggestions")

        summary = f"❌ Document has formatting issues: {', '.join(parts)}"
        if stats["fixable"] > 0:
            summary += f" ({stats['fixable']} auto-fixable)"

        return summary


def extract_line_context(
    content: str, line_num: int, context_lines: int = 2
) -> list[tuple[int, str, bool]]:
    """Extract lines around a specific line number for context.

    Returns list of (line_number, line_content, is_target_line) tuples.
    """
    lines = content.splitlines()
    if line_num < 1 or line_num > len(lines):
        return []

    start = max(1, line_num - context_lines)
    end = min(len(lines), line_num + context_lines)

    result = []
    for i in range(start, end + 1):
        result.append((
            i,
            lines[i - 1],
            i == line_num
        ))

    return result


def suggest_fixes(content: str, rule: str) -> Optional[str]:
    """Suggest fixes for specific formatting rules."""
    suggestions = {
        "missing-title": "Add a title at the beginning:\n# Document Title\n",
        "line-too-long": "Break long lines at logical points (e.g., after commas)",
        "header-hierarchy": "Ensure headers follow proper nesting (H1 → H2 → H3, not H1 → H3)",
        "missing-code-language": "Specify language after opening backticks:\n```python\n",
        "trailing-whitespace": "Remove spaces/tabs at end of lines",
        "multiple-blanks": "Use single blank lines between sections",
        "no-tabs": "Replace tabs with 4 spaces",
        "list-marker-consistency": "Use '-' for all unordered lists",
        "missing-final-newline": "Add newline at end of file",
        "header-punctuation": "Remove trailing punctuation from headers (except '?')"
    }

    return suggestions.get(rule)


def apply_auto_fixes(content: str) -> tuple[str, list[str]]:
    """Apply all auto-fixable formatting issues.

    Returns (fixed_content, list_of_applied_fixes).
    """
    fixed = content
    applied_fixes = []

    # Fix trailing whitespace
    if re.search(r'[ \t]+$', fixed, re.MULTILINE):
        fixed = re.sub(r'[ \t]+$', '', fixed, flags=re.MULTILINE)
        applied_fixes.append("Removed trailing whitespace")

    # Fix multiple blank lines
    if re.search(r'\n{3,}', fixed):
        fixed = re.sub(r'\n{3,}', '\n\n', fixed)
        applied_fixes.append("Normalized blank lines")

    # Fix tabs
    if '\t' in fixed:
        fixed = fixed.replace('\t', '    ')
        applied_fixes.append("Converted tabs to spaces")

    # Fix list markers
    fixed = re.sub(r'^(\s*)[*+]\s+', r'\1- ', fixed, flags=re.MULTILINE)
    if re.search(r'^(\s*)[*+]\s+', content, re.MULTILINE):
        applied_fixes.append("Standardized list markers to '-'")

    # Fix header punctuation
    def fix_header_punctuation(match):
        prefix = match.group(1)
        title = match.group(2).rstrip('.,:;!')
        return f"{prefix} {title}"

    fixed = re.sub(r'^(#{1,6})\s+(.+[.,:;!])$', fix_header_punctuation, fixed, flags=re.MULTILINE)
    if re.search(r'^#{1,6}\s+.+[.,:;!]$', content, re.MULTILINE):
        applied_fixes.append("Removed trailing punctuation from headers")

    # Ensure final newline
    if not fixed.endswith('\n'):
        fixed += '\n'
        applied_fixes.append("Added final newline")

    return fixed, applied_fixes
