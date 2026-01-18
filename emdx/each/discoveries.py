"""Built-in discovery commands for emdx each.

This module provides a registry of common discovery patterns that users
don't need to remember. Discoveries can be referenced using the @ prefix:

    emdx each --from @prs-with-conflicts --do "Fix conflicts in {{item}}"

Built-in discoveries are defined in code. Users can also register custom
discoveries that are stored in the database.
"""

import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from ..utils.output import console


class DiscoveryCategory(Enum):
    """Categories for organizing discoveries."""

    GITHUB = "github"
    GIT = "git"
    FILES = "files"
    CUSTOM = "custom"


@dataclass
class BuiltinDiscovery:
    """A built-in discovery command.

    Attributes:
        name: Unique identifier (used with @ prefix)
        command: Shell command that outputs items (one per line)
        description: Human-readable description
        category: Category for organization
        requires: List of required CLI tools (gh, fd, jq, etc.)
        example_output: Example of what the command outputs
        aliases: Alternative names for this discovery
    """

    name: str
    command: str
    description: str
    category: DiscoveryCategory
    requires: List[str] = field(default_factory=list)
    example_output: str = ""
    aliases: List[str] = field(default_factory=list)


# =============================================================================
# Built-in Discovery Registry
# =============================================================================

BUILTIN_DISCOVERIES: dict[str, BuiltinDiscovery] = {
    # -------------------------------------------------------------------------
    # GitHub Discoveries
    # -------------------------------------------------------------------------
    "prs-with-conflicts": BuiltinDiscovery(
        name="prs-with-conflicts",
        command=(
            "gh pr list --json headRefName,mergeStateStatus "
            "| jq -r '.[] | select(.mergeStateStatus==\"DIRTY\") | .headRefName'"
        ),
        description="PRs with merge conflicts that need resolution",
        category=DiscoveryCategory.GITHUB,
        requires=["gh", "jq"],
        example_output="feature/auth\nfix/api-error",
        aliases=["conflicts", "dirty-prs"],
    ),
    "open-prs": BuiltinDiscovery(
        name="open-prs",
        command="gh pr list --json number -q '.[] | .number'",
        description="All open pull request numbers",
        category=DiscoveryCategory.GITHUB,
        requires=["gh"],
        example_output="123\n124\n125",
        aliases=["prs"],
    ),
    "draft-prs": BuiltinDiscovery(
        name="draft-prs",
        command="gh pr list --draft --json number -q '.[] | .number'",
        description="Draft pull requests",
        category=DiscoveryCategory.GITHUB,
        requires=["gh"],
        example_output="126\n127",
        aliases=["drafts"],
    ),
    "open-issues": BuiltinDiscovery(
        name="open-issues",
        command="gh issue list --json number -q '.[] | .number'",
        description="Open GitHub issues",
        category=DiscoveryCategory.GITHUB,
        requires=["gh"],
        example_output="42\n43\n44",
        aliases=["issues"],
    ),
    "my-issues": BuiltinDiscovery(
        name="my-issues",
        command="gh issue list --assignee @me --json number -q '.[] | .number'",
        description="Issues assigned to me",
        category=DiscoveryCategory.GITHUB,
        requires=["gh"],
        example_output="42\n45",
        aliases=["assigned"],
    ),
    "pr-branches": BuiltinDiscovery(
        name="pr-branches",
        command="gh pr list --json headRefName -q '.[] | .headRefName'",
        description="Branch names of all open PRs",
        category=DiscoveryCategory.GITHUB,
        requires=["gh"],
        example_output="feature/auth\nfix/bug-123",
        aliases=["branches-with-prs"],
    ),
    # -------------------------------------------------------------------------
    # Git Discoveries
    # -------------------------------------------------------------------------
    "feature-branches": BuiltinDiscovery(
        name="feature-branches",
        command=(
            "git branch -r | grep -E 'origin/feature' | sed 's/.*origin\\///' | tr -d ' '"
        ),
        description="Remote feature branches",
        category=DiscoveryCategory.GIT,
        requires=["git"],
        example_output="feature/auth\nfeature/dashboard",
        aliases=["features"],
    ),
    "stale-branches": BuiltinDiscovery(
        name="stale-branches",
        command=(
            "git for-each-ref --sort=committerdate "
            '--format="%(refname:short)" refs/remotes/origin | head -20'
        ),
        description="Oldest remote branches (potential cleanup candidates)",
        category=DiscoveryCategory.GIT,
        requires=["git"],
        example_output="origin/old-feature\norigin/archived",
        aliases=["old-branches"],
    ),
    "changed-files": BuiltinDiscovery(
        name="changed-files",
        command="git diff --name-only HEAD~1",
        description="Files changed in the last commit",
        category=DiscoveryCategory.GIT,
        requires=["git"],
        example_output="src/api.py\ntests/test_api.py",
        aliases=["last-changed"],
    ),
    "staged-files": BuiltinDiscovery(
        name="staged-files",
        command="git diff --staged --name-only",
        description="Currently staged files",
        category=DiscoveryCategory.GIT,
        requires=["git"],
        example_output="src/new_feature.py",
        aliases=["staged"],
    ),
    "untracked-files": BuiltinDiscovery(
        name="untracked-files",
        command="git ls-files --others --exclude-standard",
        description="Untracked files not in .gitignore",
        category=DiscoveryCategory.GIT,
        requires=["git"],
        example_output="new_file.py\ndata/temp.json",
        aliases=["untracked"],
    ),
    "modified-files": BuiltinDiscovery(
        name="modified-files",
        command="git diff --name-only",
        description="Unstaged modified files",
        category=DiscoveryCategory.GIT,
        requires=["git"],
        example_output="src/config.py\nREADME.md",
        aliases=["modified", "dirty-files"],
    ),
    "uncommitted-files": BuiltinDiscovery(
        name="uncommitted-files",
        command="git status --porcelain | cut -c4-",
        description="All uncommitted files (staged, modified, and untracked)",
        category=DiscoveryCategory.GIT,
        requires=["git"],
        example_output="src/api.py\nnew_file.py",
        aliases=["uncommitted"],
    ),
    # -------------------------------------------------------------------------
    # File Discoveries
    # -------------------------------------------------------------------------
    "python-files": BuiltinDiscovery(
        name="python-files",
        command="fd -e py",
        description="All Python files in project",
        category=DiscoveryCategory.FILES,
        requires=["fd"],
        example_output="src/main.py\nsrc/utils.py",
        aliases=["py-files", "python"],
    ),
    "test-files": BuiltinDiscovery(
        name="test-files",
        command="fd -e py 'test_.*\\.py$'",
        description="Python test files (test_*.py)",
        category=DiscoveryCategory.FILES,
        requires=["fd"],
        example_output="tests/test_api.py\ntests/test_models.py",
        aliases=["tests"],
    ),
    "markdown-docs": BuiltinDiscovery(
        name="markdown-docs",
        command="fd -e md",
        description="Markdown documentation files",
        category=DiscoveryCategory.FILES,
        requires=["fd"],
        example_output="README.md\ndocs/api.md",
        aliases=["md-files", "docs"],
    ),
    "typescript-files": BuiltinDiscovery(
        name="typescript-files",
        command="fd -e ts -e tsx",
        description="TypeScript files",
        category=DiscoveryCategory.FILES,
        requires=["fd"],
        example_output="src/App.tsx\nsrc/utils.ts",
        aliases=["ts-files", "typescript"],
    ),
    "json-files": BuiltinDiscovery(
        name="json-files",
        command="fd -e json",
        description="JSON configuration files",
        category=DiscoveryCategory.FILES,
        requires=["fd"],
        example_output="package.json\ntsconfig.json",
        aliases=["json"],
    ),
    "large-files": BuiltinDiscovery(
        name="large-files",
        command="fd -t f -x stat -f '%z %N' {} | sort -rn | head -20 | awk '{print $2}'",
        description="Largest files in the project",
        category=DiscoveryCategory.FILES,
        requires=["fd"],
        example_output="data/large_dataset.csv\nnode_modules/react/index.js",
        aliases=["big-files"],
    ),
}

# Build alias lookup table
_ALIAS_MAP: dict[str, str] = {}
for name, discovery in BUILTIN_DISCOVERIES.items():
    for alias in discovery.aliases:
        _ALIAS_MAP[alias] = name


# =============================================================================
# Discovery Resolution
# =============================================================================


def is_discovery_reference(value: str) -> bool:
    """Check if a string is a discovery reference (starts with @)."""
    return value.startswith("@")


def resolve_discovery(name: str) -> Optional[BuiltinDiscovery]:
    """Resolve a discovery name to its command.

    Args:
        name: Discovery name (with or without @ prefix)

    Returns:
        BuiltinDiscovery if found, None otherwise
    """
    # Strip @ prefix if present
    name = name.lstrip("@")

    # Check built-in discoveries
    if name in BUILTIN_DISCOVERIES:
        return BUILTIN_DISCOVERIES[name]

    # Check aliases
    if name in _ALIAS_MAP:
        return BUILTIN_DISCOVERIES[_ALIAS_MAP[name]]

    # Check custom discoveries from database
    from . import database as discovery_db

    custom = discovery_db.get_discovery(name)
    if custom:
        return BuiltinDiscovery(
            name=custom.name,
            command=custom.command,
            description=custom.description or "",
            category=DiscoveryCategory.CUSTOM,
            requires=custom.requires or [],
            example_output=custom.example_output or "",
        )

    return None


def check_requirements(discovery: BuiltinDiscovery) -> List[str]:
    """Check if required tools are available.

    Args:
        discovery: The discovery to check

    Returns:
        List of missing tools (empty if all requirements met)
    """
    missing = []
    for tool in discovery.requires:
        if shutil.which(tool) is None:
            missing.append(tool)
    return missing


def run_discovery(discovery: BuiltinDiscovery, timeout: int = 30) -> List[str]:
    """Execute a discovery command and return items.

    Args:
        discovery: The discovery to run
        timeout: Timeout in seconds (default 30)

    Returns:
        List of discovered items

    Raises:
        DiscoveryError: If discovery fails
    """
    # Check requirements first
    missing = check_requirements(discovery)
    if missing:
        raise DiscoveryError(
            f"Missing required tools for @{discovery.name}: {', '.join(missing)}\n"
            f"Install them and try again."
        )

    try:
        result = subprocess.run(
            discovery.command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            stderr = result.stderr.strip()
            raise DiscoveryError(
                f"Discovery @{discovery.name} failed:\n"
                f"  Command: {discovery.command}\n"
                f"  Error: {stderr or 'Unknown error (exit code: ' + str(result.returncode) + ')'}"
            )

        # Parse output - one item per non-empty line
        items = [
            line.strip() for line in result.stdout.strip().split("\n") if line.strip()
        ]
        return items

    except subprocess.TimeoutExpired:
        raise DiscoveryError(
            f"Discovery @{discovery.name} timed out after {timeout}s\n"
            f"  Command: {discovery.command}"
        )


class DiscoveryError(Exception):
    """Error during discovery execution."""

    pass


# =============================================================================
# Discovery Listing
# =============================================================================


def list_discoveries(
    category: Optional[DiscoveryCategory] = None, include_custom: bool = True
) -> List[BuiltinDiscovery]:
    """List all available discoveries.

    Args:
        category: Filter by category (None for all)
        include_custom: Include user-defined discoveries

    Returns:
        List of discoveries
    """
    results = []

    # Add built-in discoveries
    for discovery in BUILTIN_DISCOVERIES.values():
        if category is None or discovery.category == category:
            results.append(discovery)

    # Add custom discoveries from database
    if include_custom:
        from . import database as discovery_db

        custom_discoveries = discovery_db.list_discoveries()
        for custom in custom_discoveries:
            if category is None or category == DiscoveryCategory.CUSTOM:
                results.append(
                    BuiltinDiscovery(
                        name=custom.name,
                        command=custom.command,
                        description=custom.description or "",
                        category=DiscoveryCategory.CUSTOM,
                        requires=custom.requires or [],
                        example_output=custom.example_output or "",
                    )
                )

    return results


def format_discovery_help(discovery: BuiltinDiscovery) -> str:
    """Format a discovery for help display.

    Args:
        discovery: The discovery to format

    Returns:
        Formatted help string
    """
    lines = [
        f"@{discovery.name}",
        f"  {discovery.description}",
        f"  Category: {discovery.category.value}",
    ]

    if discovery.requires:
        lines.append(f"  Requires: {', '.join(discovery.requires)}")

    if discovery.example_output:
        lines.append(f"  Example output:")
        for ex_line in discovery.example_output.split("\n")[:3]:
            lines.append(f"    {ex_line}")

    if isinstance(discovery, BuiltinDiscovery) and discovery.aliases:
        lines.append(f"  Aliases: {', '.join('@' + a for a in discovery.aliases)}")

    return "\n".join(lines)
