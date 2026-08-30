"""Setup command: install emdx integrations (Claude Code skills).

Installs the bundled Claude Code skills into the personal skills
directory (~/.claude/skills/) so pip/uv installs get working skills
without cloning the repo (issue #1033).

Kept intentionally light (stdlib + typer only) — it is registered
eagerly in main.py and must not slow down CLI startup.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import typer

# Installed directory name becomes the slash-command name in Claude Code.
# Prefix to avoid collisions and mirror the plugin's /emdx:<name> commands.
SKILL_PREFIX = "emdx-"

DEFAULT_SKILLS_DIR = Path.home() / ".claude" / "skills"


def find_skills_source() -> Path | None:
    """Locate the bundled skills directory.

    Installed wheels bundle repo-root skills/ as emdx/skills (mapped in
    pyproject.toml). In an editable/dev checkout emdx/skills does not
    exist on disk, so fall back to <repo-root>/skills next to the
    emdx package.
    """
    try:
        from importlib import resources

        pkg_skills = resources.files("emdx") / "skills"
        if pkg_skills.is_dir():
            return Path(str(pkg_skills))
    except (ModuleNotFoundError, TypeError, NotADirectoryError):
        pass

    repo_skills = Path(__file__).resolve().parents[2] / "skills"
    if repo_skills.is_dir():
        return repo_skills
    return None


def list_skills(source: Path) -> list[Path]:
    """Return skill directories (those containing a SKILL.md), sorted by name."""
    return sorted(
        (entry for entry in source.iterdir() if entry.is_dir() and (entry / "SKILL.md").is_file()),
        key=lambda entry: entry.name,
    )


def _rewrite_skill_name(skill_md: Path, new_name: str) -> None:
    """Rewrite the frontmatter `name:` field to match the installed dir name.

    The Agent Skills standard expects the frontmatter name to match the
    directory name, and the installed directory is prefixed (emdx-save).
    """
    lines = skill_md.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            lines[i] = f"name: {new_name}\n"
            skill_md.write_text("".join(lines), encoding="utf-8")
            return


def _install_skill(skill_dir: Path, dest: Path, force: bool, dry_run: bool) -> str:
    """Install one skill directory. Returns a status: installed/overwritten/skipped."""
    exists = dest.exists()
    if exists and not force:
        return "skipped"
    if dry_run:
        return "overwritten" if exists else "installed"
    if exists:
        shutil.rmtree(dest)
    shutil.copytree(skill_dir, dest)
    _rewrite_skill_name(dest / "SKILL.md", dest.name)
    return "overwritten" if exists else "installed"


def setup(
    component: str = typer.Argument(
        "claude-skills",
        help="What to set up (currently only: claude-skills)",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite skills that already exist"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be done without copying anything"
    ),
    target_dir: Path | None = typer.Option(
        None,
        "--target-dir",
        help="Install into this directory instead of ~/.claude/skills",
    ),
) -> None:
    """Install emdx integrations (Claude Code skills).

    Copies the bundled skills into ~/.claude/skills/ as emdx-<name>
    directories, usable as /emdx-<name> commands in Claude Code.
    Re-running skips existing skills unless --force is given.
    """
    if component != "claude-skills":
        print(f"Unknown component: {component}")
        print("Available components: claude-skills")
        raise typer.Exit(1)

    source = find_skills_source()
    if source is None:
        print("Error: could not locate bundled skills (emdx/skills or <repo>/skills).")
        print("Reinstall emdx (pip install --force-reinstall emdx) and try again.")
        raise typer.Exit(1)

    skills = list_skills(source)
    if not skills:
        print(f"Error: no skills found in {source}")
        raise typer.Exit(1)

    dest_root = target_dir if target_dir is not None else DEFAULT_SKILLS_DIR
    verb = "Would install" if dry_run else "Installing"
    print(f"{verb} Claude Code skills to {dest_root}")

    if not dry_run:
        dest_root.mkdir(parents=True, exist_ok=True)

    counts = {"installed": 0, "overwritten": 0, "skipped": 0}
    for skill_dir in skills:
        dest = dest_root / f"{SKILL_PREFIX}{skill_dir.name}"
        status = _install_skill(skill_dir, dest, force=force, dry_run=dry_run)
        counts[status] += 1
        if status == "skipped":
            print(f"  skipped     {dest.name} (already exists, use --force to overwrite)")
        elif dry_run:
            print(f"  would {'overwrite' if status == 'overwritten' else 'install'} {dest.name}")
        else:
            print(f"  {status:<11} {dest.name}")

    summary = (
        f"{counts['installed']} installed, "
        f"{counts['overwritten']} overwritten, "
        f"{counts['skipped']} skipped."
    )
    if dry_run:
        print(f"Dry run: {summary} Nothing was copied.")
    else:
        print(summary)
        if counts["installed"] or counts["overwritten"]:
            print("Skills are available in Claude Code as /emdx-<name> (e.g. /emdx-save).")
