# Codebase Audit

Run a structured parallel audit of the emdx codebase.

## Scope

If $ARGUMENTS is provided, focus the audit on that area (e.g., "commands", "ui", "database", "security"). Otherwise, run a full audit.

## Audit Categories

Run these checks in parallel using `emdx delegate --synthesize`:

1. **Dead code** — Unused imports, unreachable functions, orphaned files, unused variables
2. **Error handling** — Bare `except:`, `except Exception: pass`, missing error handling on I/O operations
3. **Test coverage gaps** — Public functions/methods without any test coverage, untested error paths
4. **Security** — SQL injection risks, command injection, hardcoded secrets, unsafe file operations
5. **Async correctness** — Unawaited coroutines, sync/async boundary violations, missing `run_worker()` bridges
6. **Config hygiene** — Hardcoded paths, stale model references, undefined config variables

## Execution

```bash
emdx delegate --synthesize \
  "Scan emdx/ for dead code: unused imports, unreachable functions, orphaned files" \
  "Scan emdx/ for error handling issues: bare except, swallowed errors, missing I/O error handling" \
  "Identify public functions in emdx/ that have zero test coverage in tests/" \
  "Scan emdx/ for security issues: SQL injection, command injection, hardcoded secrets" \
  "Scan emdx/ for async issues: unawaited coroutines, async/sync mismatches" \
  "Scan emdx/ for config issues: hardcoded paths, stale references, undefined variables" \
  --tags audit
```

## Output

Present findings grouped by severity:
- **Critical** — Will crash or has security implications
- **Warning** — Silent bugs or data correctness issues
- **Info** — Code quality improvements

For each finding, include file:line and a specific fix suggestion.
