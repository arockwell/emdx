# Release Preparation

Prepare a release for emdx version $ARGUMENTS.

## Steps

1. **Preview changes** — Run `just changelog` to see what's changed since last release
2. **Bump version** — Run `just bump $ARGUMENTS` to update `pyproject.toml` and `emdx/__init__.py`
3. **Write changelog** — Write a polished, prose-style entry in `CHANGELOG.md` following the existing format:
   - Group into `### 🚀 Major Features`, `### 🔧 Improvements`, `### 🐛 Bug Fixes` sections
   - Use `####` sub-headers for major features with PR number references
   - Write human-readable descriptions, not mechanical commit dumps
   - Add comparison link at the bottom: `[X.Y.Z]: https://github.com/arockwell/emdx/compare/vPREV...vX.Y.Z`
4. **Update version badge** — Update the version badge in `README.md`: `[![Version](https://img.shields.io/badge/version-X.Y.Z-blue.svg)]`
5. **Check for new features needing docs** — If any new commands or major features were added, check if `docs/cli-api.md` and `docs/README.md` need updates
6. **Verify** — Run `poetry run pytest tests/ -x -q` to make sure tests pass
7. **Branch + commit + PR**:
   ```bash
   git checkout -b release/v$ARGUMENTS
   git add -A
   git commit -m "chore: release v$ARGUMENTS"
   git push -u origin release/v$ARGUMENTS
   gh pr create --title "chore: Release v$ARGUMENTS" --body "Release v$ARGUMENTS"
   ```

## Important

- Both `pyproject.toml` (`version = "X.Y.Z"`) and `emdx/__init__.py` (`__version__ = "X.Y.Z"`) must stay in sync — `just bump` handles this
- Prefer hand-written changelog over auto-generated — match the voice and structure of existing entries
- Always include the PR/issue number references in changelog entries
