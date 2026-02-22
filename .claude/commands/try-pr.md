# Try PR

Checkout a PR branch locally and manually verify the actual behavior works as described.

## Target

$ARGUMENTS — Required: PR number (e.g., "733") or branch name.

## Steps

### 1. Fetch PR Details
- `gh pr view <N> --json title,body,headRefName` — get the PR description and branch
- Understand what the PR claims to do from the title and body

### 2. Checkout the Branch
- `gh pr checkout <N>` — pull the branch locally
- If checkout fails due to worktree conflicts, try `git fetch origin <branch> && git checkout <branch>`

### 3. Install Dependencies
- `poetry install` — ensure the environment matches the branch

### 4. Manual Smoke Test
- Read the PR description to identify the specific behavior being changed or added
- Run the actual CLI commands that exercise the change (NOT the test suite)
- For bug fixes: reproduce the original bug scenario, then verify it's fixed
- For new features: try the new command/flag/behavior end-to-end
- For docs-only PRs: verify the files exist and render correctly

### 5. Report Results
Print a clear verdict:
```
PR #NNN: <title>
Branch: <branch>

Claimed behavior: <what the PR says it does>
Test: <the exact command(s) run>
Result: ✓ Works as described / ✗ Does not work (explain)
```

## Important
- This is about manual verification, NOT running `pytest`
- Focus on the happy path first, then edge cases if relevant
- If the PR fixes a specific issue number, reproduce that exact scenario
- Stay on the branch after testing so the user can continue exploring
- If the PR touches CLI commands, show the actual command output
