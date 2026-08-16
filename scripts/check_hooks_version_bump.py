#!/usr/bin/env python3
"""
Guard against hooks/ changes shipping without a plugin version bump.

The Claude Code plugin caches by version, so a PR that edits hooks/*
without bumping .claude-plugin/plugin.json never reaches installed
plugins until some later, unrelated release happens to bump it.

Usage:
    python scripts/check_hooks_version_bump.py <base_ref> [head_ref]

    <base_ref> defaults to comparing against the merge-base; [head_ref]
    defaults to the working tree (HEAD).

Exits non-zero with an explanation when hooks/ changed but the plugin
version did not.
"""

import json
import subprocess
import sys

PLUGIN_JSON = ".claude-plugin/plugin.json"
HOOKS_PREFIX = "hooks/"


def changed_files(base_ref: str, head_ref: str) -> list[str]:
    """Return paths changed between base_ref and head_ref (merge-base diff)."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def plugin_version_at(ref: str) -> str | None:
    """Return the version field of plugin.json at the given ref, or None if absent."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{PLUGIN_JSON}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        version = json.loads(result.stdout).get("version")
    except json.JSONDecodeError:
        return None
    return str(version) if version is not None else None


def hooks_changed(files: list[str]) -> bool:
    """True if any changed path lives under hooks/."""
    return any(f.startswith(HOOKS_PREFIX) for f in files)


def version_bumped(base_version: str | None, head_version: str | None) -> bool:
    """True if the plugin version differs between base and head."""
    return base_version != head_version and head_version is not None


def check(
    files: list[str], base_version: str | None, head_version: str | None
) -> tuple[bool, str]:
    """Return (ok, message) for the given diff facts."""
    if not hooks_changed(files):
        return True, "hooks/ unchanged — nothing to check"

    if version_bumped(base_version, head_version):
        return (
            True,
            f"hooks/ changed and plugin version bumped ({base_version} -> {head_version})",
        )

    return (
        False,
        "hooks/ changed but .claude-plugin/plugin.json version did not "
        f"({base_version!r} -> {head_version!r}). Plugin consumers only pick up "
        "hook changes when the plugin version bumps, so this change would "
        "silently never reach installed plugins. Run "
        "`python scripts/release.py bump <version>` (or bump "
        ".claude-plugin/plugin.json and .claude-plugin/marketplace.json by hand) "
        "before merging.",
    )


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    base_ref = sys.argv[1]
    head_ref = sys.argv[2] if len(sys.argv) > 2 else "HEAD"

    files = changed_files(base_ref, head_ref)
    base_version = plugin_version_at(base_ref)
    head_version = plugin_version_at(head_ref)

    ok, message = check(files, base_version, head_version)
    print(message)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
