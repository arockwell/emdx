# Release Preparation

Prepare a release for emdx version $ARGUMENTS.

## Steps

1. **Preview changes** — Run `just changelog` to see what's changed since last release
2. **Bump version** — Run `just bump $ARGUMENTS` to update `pyproject.toml`, `emdx/__init__.py`, and `.claude-plugin/plugin.json`
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
9. **After PR merges — tag and push** (remind user):
   ```
   ⚠️  IMPORTANT: After this PR merges to main, create and push the git tag:
   git fetch origin main && git tag v$ARGUMENTS origin/main && git push origin v$ARGUMENTS
   ```

## Important

- All three version files must stay in sync: `pyproject.toml`, `emdx/__init__.py`, `.claude-plugin/plugin.json` — `just bump` handles all three
- Prefer hand-written changelog over auto-generated — match the voice and structure of existing entries
- Always include the PR/issue number references in changelog entries
- **Tags are NOT created by the PR** — they must be pushed manually after the release PR merges to main
