"""Tests for the setup command (Claude Code skills installation)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from emdx.commands.setup import SKILL_PREFIX, find_skills_source, list_skills
from emdx.main import app

runner = CliRunner()

EXPECTED_SKILLS = [
    "bootstrap",
    "investigate",
    "prioritize",
    "research",
    "review",
    "save",
    "tasks",
    "work",
]


class TestSkillsSource:
    """Tests for locating the bundled skills."""

    def test_source_found_in_dev_checkout(self) -> None:
        source = find_skills_source()
        assert source is not None
        assert source.is_dir()

    def test_all_expected_skills_listed(self) -> None:
        source = find_skills_source()
        assert source is not None
        names = [d.name for d in list_skills(source)]
        assert names == EXPECTED_SKILLS

    def test_marker_init_not_listed_as_skill(self) -> None:
        """The skills/__init__.py packaging marker must not become a skill."""
        source = find_skills_source()
        assert source is not None
        for skill in list_skills(source):
            assert skill.is_dir()
            assert (skill / "SKILL.md").is_file()


class TestSetupInstall:
    """Tests for `emdx setup claude-skills`."""

    def test_installs_all_skills(self, tmp_path: Path) -> None:
        target = tmp_path / "skills"
        result = runner.invoke(app, ["setup", "claude-skills", "--target-dir", str(target)])
        assert result.exit_code == 0
        installed = sorted(d.name for d in target.iterdir())
        assert installed == [f"{SKILL_PREFIX}{name}" for name in EXPECTED_SKILLS]
        for skill_dir in target.iterdir():
            assert (skill_dir / "SKILL.md").is_file()
        assert "8 installed, 0 overwritten, 0 skipped." in result.output

    def test_default_component_is_claude_skills(self, tmp_path: Path) -> None:
        """`emdx setup` with no component installs the skills."""
        target = tmp_path / "skills"
        result = runner.invoke(app, ["setup", "--target-dir", str(target)])
        assert result.exit_code == 0
        assert len(list(target.iterdir())) == len(EXPECTED_SKILLS)

    def test_frontmatter_name_matches_installed_dir(self, tmp_path: Path) -> None:
        """Installed SKILL.md name field is rewritten to the prefixed dir name."""
        target = tmp_path / "skills"
        result = runner.invoke(app, ["setup", "--target-dir", str(target)])
        assert result.exit_code == 0
        content = (target / f"{SKILL_PREFIX}save" / "SKILL.md").read_text()
        assert f"name: {SKILL_PREFIX}save" in content
        assert "name: save" not in content

    def test_rerun_skips_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "skills"
        runner.invoke(app, ["setup", "--target-dir", str(target)])
        result = runner.invoke(app, ["setup", "--target-dir", str(target)])
        assert result.exit_code == 0
        assert "0 installed, 0 overwritten, 8 skipped." in result.output
        assert "use --force to overwrite" in result.output

    def test_force_overwrites_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "skills"
        runner.invoke(app, ["setup", "--target-dir", str(target)])
        marker = target / f"{SKILL_PREFIX}save" / "SKILL.md"
        marker.write_text("locally modified")
        result = runner.invoke(app, ["setup", "--force", "--target-dir", str(target)])
        assert result.exit_code == 0
        assert "0 installed, 8 overwritten, 0 skipped." in result.output
        assert marker.read_text() != "locally modified"

    def test_dry_run_touches_nothing(self, tmp_path: Path) -> None:
        target = tmp_path / "skills"
        result = runner.invoke(app, ["setup", "--dry-run", "--target-dir", str(target)])
        assert result.exit_code == 0
        assert "Nothing was copied." in result.output
        assert not target.exists()

    def test_dry_run_leaves_existing_untouched(self, tmp_path: Path) -> None:
        target = tmp_path / "skills"
        runner.invoke(app, ["setup", "--target-dir", str(target)])
        marker = target / f"{SKILL_PREFIX}save" / "SKILL.md"
        marker.write_text("locally modified")
        result = runner.invoke(
            app, ["setup", "--dry-run", "--force", "--target-dir", str(target)]
        )
        assert result.exit_code == 0
        assert marker.read_text() == "locally modified"

    def test_unknown_component_fails(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["setup", "bogus", "--target-dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "Unknown component: bogus" in result.output
