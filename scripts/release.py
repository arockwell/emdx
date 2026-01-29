#!/usr/bin/env python3
"""
Release helper script for EMDX.

Usage:
    python scripts/release.py changelog          # Generate changelog from commits
    python scripts/release.py bump <version>     # Bump version in pyproject.toml
    python scripts/release.py release <version>  # Do both and create git tag
"""

import re
import subprocess
import sys
from datetime import date
from pathlib import Path


def get_commits_since_version(version: str | None = None) -> list[dict]:
    """Get commits since the last version tag or all commits if no tag."""
    # Get commits (all if no tags exist)
    cmd = ["git", "log", "--pretty=format:%H|%s", "--reverse"]
    if version:
        cmd.append(f"v{version}..HEAD")

    result = subprocess.run(cmd, capture_output=True, text=True)
    commits = []

    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|", 1)
        if len(parts) == 2:
            commits.append({"hash": parts[0][:7], "message": parts[1]})

    return commits


def categorize_commits(commits: list[dict]) -> dict[str, list[str]]:
    """Categorize commits by type (feat, fix, refactor, etc.)."""
    categories = {
        "features": [],
        "fixes": [],
        "refactor": [],
        "docs": [],
        "perf": [],
        "chore": [],
        "other": [],
    }

    for commit in commits:
        msg = commit["message"]

        # Parse conventional commit format
        if msg.startswith("feat"):
            # Extract scope if present: feat(scope): message
            match = re.match(r"feat(?:\(([^)]+)\))?: (.+)", msg)
            if match:
                scope, description = match.groups()
                if scope:
                    categories["features"].append(f"**{scope}**: {description}")
                else:
                    categories["features"].append(description)
            else:
                categories["features"].append(msg[5:].strip(": "))
        elif msg.startswith("fix"):
            match = re.match(r"fix(?:\(([^)]+)\))?: (.+)", msg)
            if match:
                scope, description = match.groups()
                if scope:
                    categories["fixes"].append(f"**{scope}**: {description}")
                else:
                    categories["fixes"].append(description)
            else:
                categories["fixes"].append(msg[4:].strip(": "))
        elif msg.startswith("refactor"):
            categories["refactor"].append(msg[9:].strip(": "))
        elif msg.startswith("docs"):
            categories["docs"].append(msg[5:].strip(": "))
        elif msg.startswith("perf"):
            categories["perf"].append(msg[5:].strip(": "))
        elif msg.startswith("chore"):
            categories["chore"].append(msg[6:].strip(": "))
        else:
            # Skip merge commits and other noise
            if not msg.startswith("Merge"):
                categories["other"].append(msg)

    return categories


def generate_changelog_entry(version: str, categories: dict[str, list[str]]) -> str:
    """Generate a changelog entry for the given version."""
    today = date.today().isoformat()
    lines = [f"## [{version}] - {today}", ""]

    if categories["features"]:
        lines.append("### Added")
        for item in categories["features"]:
            lines.append(f"- {item}")
        lines.append("")

    if categories["fixes"]:
        lines.append("### Fixed")
        for item in categories["fixes"]:
            lines.append(f"- {item}")
        lines.append("")

    if categories["perf"]:
        lines.append("### Performance")
        for item in categories["perf"]:
            lines.append(f"- {item}")
        lines.append("")

    if categories["refactor"]:
        lines.append("### Changed")
        for item in categories["refactor"]:
            lines.append(f"- {item}")
        lines.append("")

    if categories["docs"]:
        lines.append("### Documentation")
        for item in categories["docs"]:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def get_current_version() -> str:
    """Get the current version from pyproject.toml."""
    pyproject = Path("pyproject.toml")
    content = pyproject.read_text()
    match = re.search(r'version = "([^"]+)"', content)
    if match:
        return match.group(1)
    raise ValueError("Could not find version in pyproject.toml")


def bump_version(new_version: str) -> None:
    """Bump the version in pyproject.toml.

    Only updates the [tool.poetry] version, not other version strings
    like typer version or python_version.
    """
    pyproject = Path("pyproject.toml")
    content = pyproject.read_text()

    # Only replace the version in [tool.poetry] section
    # Match: version = "x.y.z" that appears right after name = "emdx"
    new_content = re.sub(
        r'(\[tool\.poetry\]\nname = "emdx"\n)version = "[^"]+"',
        f'\\1version = "{new_version}"',
        content
    )

    pyproject.write_text(new_content)
    print(f"Updated pyproject.toml to version {new_version}")


def update_changelog(entry: str) -> None:
    """Insert a new entry at the top of the changelog."""
    changelog = Path("CHANGELOG.md")
    content = changelog.read_text()

    # Find where to insert (after the header)
    header_end = content.find("\n## [")
    if header_end == -1:
        # No existing entries, add after any header text
        lines = content.split("\n")
        header_lines = []
        for i, line in enumerate(lines):
            if line.startswith("## "):
                break
            header_lines.append(line)
        header = "\n".join(header_lines)
        rest = "\n".join(lines[len(header_lines):])
        new_content = header + "\n" + entry + "\n" + rest
    else:
        new_content = content[:header_end] + "\n" + entry + "\n" + content[header_end:]

    changelog.write_text(new_content)
    print(f"Updated CHANGELOG.md")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "changelog":
        # Generate changelog from recent commits
        commits = get_commits_since_version()
        # Limit to last 100 commits for sanity
        recent = commits[-100:] if len(commits) > 100 else commits
        categories = categorize_commits(recent)

        print("=== Features ===")
        for f in categories["features"][:20]:
            print(f"  - {f}")
        print(f"\n  ... and {len(categories['features']) - 20} more" if len(categories["features"]) > 20 else "")

        print("\n=== Fixes ===")
        for f in categories["fixes"][:20]:
            print(f"  - {f}")
        print(f"\n  ... and {len(categories['fixes']) - 20} more" if len(categories["fixes"]) > 20 else "")

        print(f"\nTotal: {len(categories['features'])} features, {len(categories['fixes'])} fixes")

    elif command == "bump":
        if len(sys.argv) < 3:
            print("Usage: python scripts/release.py bump <version>")
            sys.exit(1)
        bump_version(sys.argv[2])

    elif command == "release":
        if len(sys.argv) < 3:
            print("Usage: python scripts/release.py release <version>")
            sys.exit(1)
        new_version = sys.argv[2]

        # Generate changelog
        commits = get_commits_since_version()
        recent = commits[-100:] if len(commits) > 100 else commits
        categories = categorize_commits(recent)
        entry = generate_changelog_entry(new_version, categories)

        # Update files
        bump_version(new_version)
        update_changelog(entry)

        print(f"\nRelease {new_version} prepared!")
        print("Next steps:")
        print(f"  1. Review CHANGELOG.md")
        print(f"  2. git add -A && git commit -m 'chore: release v{new_version}'")
        print(f"  3. git tag v{new_version}")
        print(f"  4. git push && git push --tags")

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
