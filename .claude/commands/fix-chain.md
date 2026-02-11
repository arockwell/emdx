# Post-Feature Bug Sweep

Analyze recently merged code for likely bugs before they become follow-up fix PRs.

## Target

If $ARGUMENTS is provided, analyze that PR number or branch. Otherwise, analyze the most recently merged PR.

## What to Check

Scan the diff for these patterns that have caused bugs in this codebase before:

### 1. Undefined Variable References
- Variables used but never assigned in scope (e.g., `config_dir` referenced but only `EMDX_CONFIG_DIR` defined — see PR #421)
- Copy-pasted code where variable names weren't updated

### 2. Async/Sync Mismatches
- `async def` passed where a sync callback is expected (e.g., `set_interval()` with async fn — see PR #417)
- Coroutines created but never awaited
- `run_worker()` not used to bridge async into sync contexts

### 3. Missing Import Guards
- New code using optional deps (sklearn, anthropic, numpy, etc.) without `try/except` import guards
- See PR #408 pattern: all optional deps need `_require_*()` helpers

### 4. Duplicate Data / Missing Dedup
- New records created without checking `document_source` tracking (see PR #412)
- SQL queries that may return duplicates when items appear in multiple contexts

### 5. Parameter Pass-through Gaps
- New CLI flags added to a command but not threaded through to the model/database layer (see PR #399: `include_archived`)
- Function signature changes not propagated to all callers

### 6. SQL / Database Issues
- Bare `except Exception: pass` hiding real errors
- Missing parameterized queries (injection risk)
- New columns or tables without migration

## Output

For each issue found:
- **File:line** — exact location
- **Pattern** — which category above
- **Severity** — will-crash / silent-bug / code-smell
- **Fix** — specific suggestion

If the code looks clean, say so — don't invent issues.
