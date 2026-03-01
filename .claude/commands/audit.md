# Codebase Audit

Run a structured parallel audit of the emdx codebase.

## Scope

If $ARGUMENTS is provided, focus the audit on that area (e.g., "commands", "ui", "database", "security"). Otherwise, run a full audit.

## Audit Categories

Launch parallel agents (up to 6) to check each category simultaneously:

1. **Dead code** — Unused imports, unreachable functions, orphaned files, unused variables
2. **Error handling** — Bare `except:`, `except Exception: pass`, missing error handling on I/O operations
3. **Test coverage gaps** — Public functions/methods without any test coverage, untested error paths
4. **Security** — SQL injection risks, command injection, hardcoded secrets, unsafe file operations
5. **Async correctness** — Unawaited coroutines, sync/async boundary violations, missing `run_worker()` bridges
6. **Config hygiene** — Hardcoded paths, stale model references, undefined config variables

## Execution

Use the Agent tool with `subagent_type: "Explore"` to run each category in parallel. Each agent should search the `emdx/` directory for its category's issues using Grep and Read tools.

For scoped audits ($ARGUMENTS provided), launch only the relevant agents.

## Output

Present findings grouped by severity:
- **Critical** — Will crash or has security implications
- **Warning** — Silent bugs or data correctness issues
- **Info** — Code quality improvements

For each finding, include file:line and a specific fix suggestion.
