# EMDX - Knowledge Base CLI Tool

## CRITICAL: Interactive Commands

**NEVER run `emdx gui`** - This launches an interactive TUI that will hang Claude Code sessions.

## Project Overview

EMDX is a CLI knowledge base and documentation management system. Python 3.11+, SQLite + FTS5, Textual TUI, Typer CLI.

**Key Components:**
- `commands/` - CLI command implementations
- `config/` - Configuration management (settings, constants, tagging rules)
- `database/` - SQLite operations and migrations
- `ui/` - TUI components (Textual widgets)
- `services/` - Business logic (log streaming, file watching, etc.)
- `models/` - Data models and operations
- `utils/` - Shared utilities (git, emoji aliases, Claude integration)

**Detailed docs:** [docs/](docs/) | [Architecture](docs/architecture.md) | [CLI Reference](docs/cli-api.md) | [Development Setup](docs/development-setup.md)

## Development

```bash
poetry install          # Install dependencies
poetry run emdx --help  # Always use poetry run in project dir
poetry run pytest tests/ -x -q  # Run tests
```

## Worktree Cleanup

When working in the emdx repo, stale delegate worktrees may accumulate in the parent directory. These can block `gh pr checkout` and other git operations.

- Use `git worktree list` to find active worktrees
- Use `emdx delegate --cleanup` to remove worktrees older than 1 hour
- If `gh pr checkout` fails due to existing worktrees, clone to `/tmp` instead
- After merging delegate-created PRs, the local worktrees are no longer needed (branches are already pushed to remote)

## Code Quality — MANDATORY

**Pre-commit hooks are active** (ruff lint, ruff format, mypy on staged files). They run automatically on `git commit`. Config: `.pre-commit-config.yaml`. To run manually: `poetry run pre-commit run --files <files>`.

**Before every commit, run lint and fix errors:**

```bash
poetry run ruff check . --fix   # Auto-fix what it can
poetry run ruff check .         # Verify zero errors remain
```

**Rules:**
- Line length limit: **100 characters** (configured in pyproject.toml)
- Enabled rule sets: E, W, F, I, B, C4, UP (pycodestyle, pyflakes, isort, bugbear, comprehensions, pyupgrade)
- B904: Always use `raise ... from err` or `raise ... from None` inside `except` blocks
- B008 is ignored (typer pattern for function call defaults)
- `ruff check` must pass with **zero errors** before pushing any branch
- When writing SQL strings that exceed 100 chars, break across lines or use implicit string concatenation
- All `--flags` must come BEFORE positional arguments in `emdx delegate` calls

## CLI Output Mode Convention

- Default CLI output should be plain text (no Rich markup) for machine/pipe friendliness
- `--rich` flag enables colored Rich output (panels, markdown rendering, syntax highlighting)
- `--json` flag for structured machine output
- Use `print()` for plain output, `console.print()` only in `--rich` mode

## Rich Console Gotcha

- `console.pager()` defaults to `styles=False`, stripping all colors. Always use `console.pager(styles=True)` when rendering Rich markup inside a pager.

## Claude Code Integration - MANDATORY

### Session Start Protocol
```bash
emdx prime    # Get current work context (ready tasks, in-progress, recent docs)
emdx status   # Quick overview
```

### Mandatory Behaviors

1. **Check ready tasks** before starting work: `emdx task ready`
2. **Save significant outputs** to emdx: `echo "findings" | emdx save --title "Title" --tags "analysis,active"`
3. **Create tasks** for discovered work: `emdx task add "Title" --description "Details"`
4. **Never end session** without updating task status and creating tasks for remaining work

### CRITICAL: Use `emdx delegate` Instead of Task Tool Sub-Agents

**NEVER use the Task tool to spawn sub-agents.** Use `emdx delegate` instead — results print to stdout AND persist to the knowledge base.

```bash
# Single task
emdx delegate "analyze the auth module"

# Parallel (up to 10 concurrent)
emdx delegate "check auth" "review tests" "scan for XSS"

# Parallel with synthesis
emdx delegate --synthesize "task1" "task2" "task3"

# With document context
emdx delegate --doc 42 "implement the plan described here"

# With PR creation (--pr implies --worktree)
emdx delegate --pr "fix the auth bug"

# All flags compose together
emdx delegate --doc 42 --pr "fix the bug"

# Dynamic discovery
emdx delegate --each "fd -e py src/" --do "Review {{item}}"
```

**Other options:** `--tags`, `--title`, `-j` (max parallel), `--model`, `-q` (quiet), `--base-branch`

### Quick Reference

| Situation | Command |
|-----------|---------|
| Research/analysis | `emdx delegate "task"` |
| Parallel research | `emdx delegate "t1" "t2" "t3"` |
| Combined summary | `emdx delegate --synthesize "t1" "t2"` |
| Discover + process | `emdx delegate --each "cmd" --do "Review {{item}}"` |
| Doc as input | `emdx delegate --doc 42 "implement this"` |
| Code changes with PR | `emdx delegate --pr "fix the bug"` |
| Run saved recipe | `emdx recipe run 42` |

### Auto-Tagging Guidelines

| Content Type | Tags |
|--------------|------|
| Plans/strategy | `gameplan, active` |
| Investigation | `analysis` |
| Bug fixes | `bugfix` |
| Security | `security` |
| Notes | `notes` |

**Status:** `active` (working), `done` (completed), `blocked` (stuck)
**Outcome:** `success`, `failed`, `partial`

## Essential Commands

```bash
# Save
emdx save document.md
emdx save "text content" --title "Title"
echo "text" | emdx save --title "Title" --tags "notes"

# Search
emdx find "query"                      # Hybrid search (default when index exists)
emdx find "concept" --mode semantic    # Semantic/conceptual search
emdx find "query" --extract            # Extract key info from results
emdx find --tags "gameplan,active"

# Tags
emdx tag add 42 gameplan active
emdx tag list

# AI search (requires emdx[ai] extra)
# Note: emdx find now supports semantic search natively via --mode semantic
emdx ai search "concept"
emdx ai context "question" | claude
```

For complete command reference, see [CLI Reference](docs/cli-api.md).
For AI system docs, see [AI System](docs/ai-system.md).

## Known Gotchas

- **`select.select()` on macOS**: Python's `select.select()` does not work reliably on `subprocess.Popen` stdout/stderr pipes on macOS. Use background threads with `queue.Queue` instead (see `_reader_thread()` in `unified_executor.py`).
- **Delegate log monitoring**: When running parallel delegates, verify logs are non-zero with `wc -c` on the log files. Zero-byte logs indicate a streaming bug, not an empty task.

## Release Process

```bash
just changelog          # Preview changes since last release
just bump 0.X.Y         # Bump version in pyproject.toml + emdx/__init__.py
# Write changelog entry in CHANGELOG.md
# Branch, commit, PR, merge, then:
git tag vX.Y.Z && git push --tags
```

Version files that must stay in sync: `pyproject.toml` and `emdx/__init__.py`.
