"""Code-drift detection for EMDX documents.

Scans documents for backtick-wrapped code identifiers (function names, class names,
file paths) and cross-references them against the codebase using rg and git log
to detect stale references.

Registered as `emdx maintain code-drift`.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from typing import TypedDict

import typer

logger = logging.getLogger(__name__)

# ── TypedDicts for structured output ──────────────────────────────────


class StaleReference(TypedDict):
    """A single stale code reference found in a document."""

    doc_id: int
    doc_title: str
    identifier: str
    reason: str
    suggestion: str | None


class CodeDriftReport(TypedDict):
    """Full drift report for JSON output."""

    total_docs_scanned: int
    total_identifiers_checked: int
    stale_references: list[StaleReference]


# ── Identifier extraction ─────────────────────────────────────────────

# Match backtick-wrapped identifiers:
# - function_name() or method_name()
# - ClassName (PascalCase, 2+ chars)
# - path/to/file.ext (file paths with extension)
# - module.attribute style
_BACKTICK_PATTERN = re.compile(r"`([^`\n]{2,80})`")

# Sub-patterns to classify what's inside backticks
_FUNC_PATTERN = re.compile(r"^[a-zA-Z_]\w*\(\)$")
_CLASS_PATTERN = re.compile(r"^[A-Z][a-zA-Z0-9]+$")
_FILE_PATH_PATTERN = re.compile(r"^[\w./\\-]+\.\w{1,10}$")
_DOTTED_NAME_PATTERN = re.compile(r"^[a-zA-Z_]\w*\.[a-zA-Z_]\w*$")

# Skip these common non-code identifiers
_SKIP_PATTERNS = {
    # Common CLI flags and options
    "--",
    "-",
    # Common words that appear in backticks but aren't code
    "true",
    "false",
    "null",
    "none",
    "True",
    "False",
    "None",
    "yes",
    "no",
    "on",
    "off",
}

# Skip identifiers that are just CLI commands or flags
_CLI_FLAG_PATTERN = re.compile(r"^--?[a-zA-Z]")
# Skip shell commands (single word, all lowercase, no dots/parens)
_SHELL_CMD_PATTERN = re.compile(r"^[a-z]+$")
# Skip very short identifiers (likely noise)
_MIN_IDENTIFIER_LEN = 3


def extract_code_identifiers(content: str) -> list[str]:
    """Extract code identifiers from backtick-wrapped text in document content.

    Returns deduplicated list of identifiers that look like code references.
    """
    identifiers: set[str] = set()

    for match in _BACKTICK_PATTERN.finditer(content):
        raw = match.group(1).strip()

        # Skip empty, too short, or known non-code
        if len(raw) < _MIN_IDENTIFIER_LEN:
            continue
        if raw in _SKIP_PATTERNS:
            continue
        if _CLI_FLAG_PATTERN.match(raw):
            continue

        # Check if it matches any code pattern
        if _FUNC_PATTERN.match(raw):
            identifiers.add(raw)
        elif _CLASS_PATTERN.match(raw):
            identifiers.add(raw)
        elif _FILE_PATH_PATTERN.match(raw):
            identifiers.add(raw)
        elif _DOTTED_NAME_PATTERN.match(raw):
            identifiers.add(raw)

    return sorted(identifiers)


# ── Codebase search tools ─────────────────────────────────────────────


def _has_tool(name: str) -> bool:
    """Check if a CLI tool is available."""
    return shutil.which(name) is not None


def _is_git_repo() -> bool:
    """Check if current directory is inside a git repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def _search_codebase(identifier: str, use_rg: bool) -> bool:
    """Check if an identifier exists in the codebase.

    Args:
        identifier: The code identifier to search for
        use_rg: Whether to use rg (ripgrep) or fall back to grep

    Returns:
        True if the identifier was found in any file
    """
    # Strip trailing () for function names when searching
    search_term = identifier.rstrip("()")

    if use_rg:
        result = subprocess.run(
            ["rg", "-l", "--max-count=1", search_term, "."],
            capture_output=True,
            text=True,
        )
    else:
        result = subprocess.run(
            ["grep", "-rl", "--max-count=1", search_term, "."],
            capture_output=True,
            text=True,
        )
    return result.returncode == 0 and bool(result.stdout.strip())


def _check_git_history(
    identifier: str,
) -> tuple[str | None, str | None]:
    """Check git log for recent changes to an identifier.

    Uses `git log -S` (pickaxe) to find commits that added/removed the
    identifier, which helps detect renames and deletions.

    Args:
        identifier: The code identifier to check

    Returns:
        Tuple of (commit_info, suggestion):
        - commit_info: e.g. "deleted in commit abc1234 (3 days ago)"
        - suggestion: potential replacement name if detected
    """
    search_term = identifier.rstrip("()")

    result = subprocess.run(
        [
            "git",
            "log",
            "--oneline",
            "-1",
            "--all",
            "-S",
            search_term,
            "--format=%h %ar %s",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None, None

    commit_line = result.stdout.strip()
    parts = commit_line.split(" ", 1)
    commit_hash = parts[0] if parts else "unknown"
    commit_desc = parts[1] if len(parts) > 1 else ""

    # Try to detect renames by looking at the commit message
    suggestion = None
    rename_indicators = ["rename", "Rename", "refactor", "Refactor"]
    for indicator in rename_indicators:
        if indicator in commit_desc:
            # Try to extract what it was renamed to from the diff
            diff_result = subprocess.run(
                [
                    "git",
                    "diff",
                    commit_hash + "~1",
                    commit_hash,
                    "--unified=0",
                ],
                capture_output=True,
                text=True,
            )
            if diff_result.returncode == 0:
                suggestion = _extract_rename_target(diff_result.stdout, search_term)
            break

    commit_info = f"last changed in {commit_hash} ({commit_desc})"
    return commit_info, suggestion


def _extract_rename_target(diff_output: str, old_name: str) -> str | None:
    """Try to extract a rename target from a git diff.

    Looks for lines added (starting with +) that contain a similar
    pattern to the old_name, suggesting a rename.
    """
    added_lines = [
        line[1:]
        for line in diff_output.split("\n")
        if line.startswith("+") and not line.startswith("+++")
    ]
    removed_lines = [
        line[1:]
        for line in diff_output.split("\n")
        if line.startswith("-") and not line.startswith("---")
    ]

    # If old_name appears in removed lines, look for similar
    # definitions in added lines
    old_in_removed = any(old_name in line for line in removed_lines)
    if not old_in_removed:
        return None

    # Look for function/class definitions in added lines
    for line in added_lines:
        # Match def new_name or class NewName
        def_match = re.search(r"(?:def|class)\s+(\w+)", line)
        if def_match:
            new_name = def_match.group(1)
            if new_name != old_name:
                return new_name

    return None


# ── Main drift detection ──────────────────────────────────────────────


def _get_documents(
    project: str | None = None,
    limit: int | None = None,
) -> list[tuple[int, str, str]]:
    """Fetch documents from the database.

    Returns list of (id, title, content) tuples.
    """
    from emdx.database.connection import db_connection

    with db_connection.get_connection() as conn:
        conditions = [
            "is_deleted = FALSE",
            "archived_at IS NULL",
        ]
        params: list[str | int] = []

        if project:
            conditions.append("project = ?")
            params.append(project)

        where = " AND ".join(conditions)
        query = f"SELECT id, title, content FROM documents WHERE {where} ORDER BY id DESC"

        if limit is not None and limit > 0:
            query += " LIMIT ?"
            params.append(limit)

        cursor = conn.execute(query, params)
        return [(row["id"], row["title"], row["content"]) for row in cursor.fetchall()]


def detect_code_drift(
    project: str | None = None,
    limit: int | None = None,
) -> CodeDriftReport:
    """Detect stale code references across all documents.

    Args:
        project: Optional project name to scope the scan
        limit: Maximum number of documents to check

    Returns:
        CodeDriftReport with all findings
    """
    use_rg = _has_tool("rg")
    use_git = _has_tool("git") and _is_git_repo()

    docs = _get_documents(project=project, limit=limit)

    stale_refs: list[StaleReference] = []
    total_identifiers = 0

    for doc_id, doc_title, content in docs:
        identifiers = extract_code_identifiers(content)
        total_identifiers += len(identifiers)

        for ident in identifiers:
            found = _search_codebase(ident, use_rg=use_rg)
            if found:
                continue

            # Not found in codebase — check git history
            reason = "not found in codebase"
            suggestion: str | None = None

            if use_git:
                commit_info, rename_target = _check_git_history(ident)
                if commit_info:
                    reason = commit_info
                if rename_target:
                    suggestion = rename_target

            stale_refs.append(
                StaleReference(
                    doc_id=doc_id,
                    doc_title=doc_title,
                    identifier=ident,
                    reason=reason,
                    suggestion=suggestion,
                )
            )

    return CodeDriftReport(
        total_docs_scanned=len(docs),
        total_identifiers_checked=total_identifiers,
        stale_references=stale_refs,
    )


# ── CLI command ───────────────────────────────────────────────────────


def code_drift_command(
    project: str | None = typer.Option(
        None,
        "--project",
        "-p",
        help="Scope to a specific project's documents",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of documents to check",
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output results as JSON",
    ),
    fix: bool = typer.Option(
        False,
        "--fix",
        help="Show suggested replacements when available",
    ),
) -> None:
    """
    Detect stale code references in knowledge base documents.

    Scans documents for backtick-wrapped code identifiers (function names,
    class names, file paths) and cross-references them against the codebase
    to find references that no longer exist.

    Examples:
        emdx maintain code-drift
        emdx maintain code-drift --project myproject
        emdx maintain code-drift --limit 50
        emdx maintain code-drift --json
        emdx maintain code-drift --fix
    """
    report = detect_code_drift(project=project, limit=limit)

    if output_json:
        print(json.dumps(report, indent=2, default=str))
        return

    # Plain text output
    stale = report["stale_references"]
    total_docs = report["total_docs_scanned"]
    total_idents = report["total_identifiers_checked"]

    if total_docs == 0:
        print("No documents to check.")
        return

    print(f"Scanned {total_docs} documents, checked {total_idents} code references.")

    if not stale:
        print("All code references look current!")
        return

    print(f"\nFound {len(stale)} stale reference(s):\n")

    # Group by document for readable output
    by_doc: dict[int, list[StaleReference]] = {}
    for ref in stale:
        by_doc.setdefault(ref["doc_id"], []).append(ref)

    for doc_id, refs in by_doc.items():
        title = refs[0]["doc_title"]
        print(f"  #{doc_id} - {title}")
        for ref in refs:
            ident = ref["identifier"]
            reason = ref["reason"]
            print(f"    `{ident}` — {reason}")
            if fix and ref["suggestion"]:
                print(f"      -> suggestion: `{ref['suggestion']}`")
        print()
