# Release

Full release pipeline: prep, PR, merge, sync, tag. One command, no babysitting.

## Version Detection

Automatically determine the next version:

1. Get the current version from `pyproject.toml` (e.g., `0.29.0`)
2. Run `just changelog` to preview changes since last release
3. Decide the bump:
   - **Patch** (0.29.0 → 0.29.1): Only bug fixes, docs, chores
   - **Minor** (0.29.0 → 0.30.0): New features, improvements
   - **Major**: Breaking changes (rare — confirm with user first)
4. If `$ARGUMENTS` is provided, use that version instead of auto-detecting

## Pipeline

### Phase 1: Prep Release

1. **Preview changes** — Run `just changelog`
2. **Determine version** — Auto-detect or use `$ARGUMENTS` if provided
3. **Bump version** — Run `just bump <version>`
4. **Write changelog** — Polished prose entry in `CHANGELOG.md`:
   - Group into `### 🚀 Major Features`, `### 🔧 Improvements`, `### 🐛 Bug Fixes`
   - Use `####` sub-headers for major features with PR number references
   - Add comparison link: `[X.Y.Z]: https://github.com/arockwell/emdx/compare/vPREV...vX.Y.Z`
5. **Update version badge** in `README.md`
6. **Check for new features needing docs** — scan for new commands/flags, update `docs/cli-api.md` if needed
7. **Run tests** — `poetry run pytest tests/ -x -q`

### Phase 2: PR + Merge

8. **Branch + commit + push**:
   ```bash
   git checkout -b release/v<version>
   git add -A
   git commit -m "chore: Release v<version>"
   git push -u origin release/v<version>
   ```
9. **Create PR**:
   ```bash
   gh pr create --title "chore: Release v<version>" --body "Release v<version>"
   ```
10. **Watch CI and merge**:
    ```bash
    gh pr checks <N> --watch --fail-fast
    # If green:
    gh api repos/{owner}/{repo}/pulls/<N>/merge -X PUT -f merge_method=squash
    # If failing: diagnose, fix, push, watch again (max 3 attempts)
    ```
11. **Verify merge**:
    ```bash
    gh pr view <N> --json state -q '.state'  # Must be "MERGED"
    ```

### Phase 3: Tag

12. **Fetch, tag, push**:
    ```bash
    git fetch origin main
    git tag v<version> origin/main
    git push origin v<version>
    ```
13. **Verify tag exists on remote**:
    ```bash
    git ls-remote --tags origin v<version>
    ```

### Phase 4: Sync Local

14. **Merge main into current branch**:
    ```bash
    git merge origin/main
    ```

## Output

Print a summary when done:
```
Released v0.30.0
   PR #991: merged
   Tag v0.30.0: pushed
   Local branch: synced with main
```

## Rules

- All version files must stay in sync — `just bump` handles this
- Hand-written changelog, not auto-generated dumps
- **Never skip CI** — always wait for green before merging
- If CI fails, fix and retry (max 3 attempts per failure)
- Use `gh api` for merge if `gh pr merge` fails due to worktree issues
- If merge conflicts arise during sync, report and stop
- The tag MUST point to the merge commit on main, not the branch commit
