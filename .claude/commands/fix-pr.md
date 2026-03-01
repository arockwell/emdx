# Fix PR

Fix a broken pull request — resolve merge conflicts, fix CI failures, or rebase stale branches.

## Scope
$ARGUMENTS — PR number(s) to fix (e.g., "687", "687 689")

## Steps

### 1. Diagnose
For each PR, fetch details with:
```
gh pr view <N> --json title,headRefName,mergeable,statusCheckRollup,body
```

Categorize the problem:
- **Merge conflicts** (mergeable=CONFLICTING) → needs rebase
- **CI failures** → check `gh run view <run_id> --log-failed` for root cause
- **Stale base** → needs rebase, may introduce new failures after rebase

### 2. Check if failure is pre-existing
Compare against main's CI: `gh api repos/{owner}/{repo}/actions/runs --method GET -f branch=main -f status=completed -f per_page=1`

If main is also failing on the same check, the PR isn't at fault.

### 3. Fix
- **Merge conflicts**: `gh pr checkout <N>`, rebase onto origin/main, resolve conflicts preserving the PR's intent, force-push
- **Type errors (mypy)**: Read the error log, fix each error in the branch
- **Lint errors (ruff)**: `ruff check . --fix` then manual fixes for what remains
- **Test failures**: Investigate root cause, fix, verify with `pytest -x -q`
- **Stale/unfixable**: If the PR's changes are already on main or the fix is simpler than a rebase, close and redo fresh from main

### 4. Verify
Run the full check suite locally before pushing:
```
poetry run ruff check .
poetry run mypy emdx
poetry run pytest tests/ -x -q
```

### 5. Push
- For rebases: `git push --force-with-lease`
- For fixes: `git push`
- If redone from scratch: create new PR, close old one with "Superseded by #NNN"

## Output
Per-PR summary: what was wrong, what was fixed, verification results.
