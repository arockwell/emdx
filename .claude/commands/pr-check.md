# Pre-PR Quality Gate

Run before creating a PR to catch common issues.

## Checks

### 1. Commit Format
Verify all commits on this branch follow conventional commit format:
- `feat(scope): description`
- `fix(scope): description`
- `refactor(scope): description`
- `chore: description`
- `docs: description`

Run: `git log main..HEAD --oneline`

### 2. Issue/PR Reference
Check that the branch name or commit messages reference an issue number where appropriate. The CLAUDE.md says to include emdx numbers in PR titles like `(Issue #NNN)`.

### 3. Tests Pass
Run: `poetry run pytest tests/ -x -q`

### 4. No Obvious Bugs (Quick Scan)
Do a fast check of the diff for:
- Undefined variables in new code
- `async def` passed as sync callbacks
- New optional dep imports without `try/except` guards
- Bare `except Exception: pass`
- Hardcoded paths instead of `EMDX_CONFIG_DIR`/`EMDX_LOG_DIR`

Run: `git diff main...HEAD`

### 5. No Sensitive Files
Check that the diff doesn't include:
- `.env` files
- API keys or tokens
- `credentials.json`
- Large binary files

### 6. Version Consistency
If `pyproject.toml` version changed, verify `emdx/__init__.py` matches.

## Output

Print a pass/fail summary:
```
✓ Commit format: all 3 commits follow conventional format
✓ Tests: 411 passed
✓ No obvious bugs found
✓ No sensitive files
✗ Issue reference: no issue number in branch name or commits
```

If anything fails, provide the specific fix needed.
