# EMDX - Knowledge Base CLI Tool

## CRITICAL: Never run `emdx gui`

This launches an interactive TUI that will hang Claude Code sessions. Use CLI commands instead.

## Project Overview

EMDX is a CLI knowledge base and documentation management system. Python 3.11+, SQLite+FTS5, Textual TUI, Typer CLI.

**Key Components:**
- `commands/` - CLI command implementations (Typer apps)
- `database/` - SQLite operations and migrations
- `ui/` - TUI components (Textual widgets)
- `services/` - Business logic (log streaming, file watching, auto-tagging)
- `models/` - Thin wrappers over database with business logic
- `utils/` - Shared utilities (git, emoji aliases, Claude integration)

## Development

Always use `poetry run emdx` in the project directory (global install may point to a different worktree).

```bash
poetry install                       # Install deps
poetry run emdx --help               # Run CLI
poetry run pytest tests/ -x -q       # Run tests (~411 tests, ~23s)
```

## Architecture

**Layer flow:** Commands → Models → Database. Services support all layers.

- Commands import from `models/`, never directly from `database/`
- Models are thin wrappers that add validation/formatting over DB operations
- Services implement complex logic (AutoTagger, DuplicateDetector, etc.)
- Database uses a global singleton: `from emdx.database import db_connection`
- Connection pattern: `with db_connection.get_connection() as conn:`

## Adding Features

**New CLI command:**
1. Create `emdx/commands/newcmd.py` with `app = typer.Typer()`
2. Register in `main.py` — add to `LAZY_SUBCOMMANDS` if it has heavy deps

**New database table:**
- Add `migration_NNN_description(conn)` function in `database/migrations.py`
- Migrations are versioned, tracked in `schema_version` table, and idempotent

**New optional dependency:**
```python
from __future__ import annotations  # Required for optional dep modules

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

def _require_sklearn() -> None:
    if not HAS_SKLEARN:
        raise ImportError("scikit-learn required. Install: pip install 'emdx[similarity]'")
```
- Guard at function entry, not module level
- Add to appropriate extras group in `pyproject.toml`: `[ai]`, `[similarity]`, `[google]`, `[all]`

## Testing

- pytest with fixtures in `conftest.py`
- DB tests use `DatabaseForTesting` with in-memory SQLite — auto-isolated per session
- Tags in test fixtures use direct SQL (not model layer) to avoid global state
- No `--timeout` flag available

## UI/TUI Patterns

- Textual framework — widgets inherit from `Widget`, define `compose()` → `ComposeResult`
- Activity view uses `Tree[ActivityItem]` (not DataTable — was migrated to fix scroll jumping)
- Tree updates: `populate_from_items()` for initial load, `refresh_from_items()` for diff-based updates via `set_label()` (preserves scroll position)
- Lazy child loading: `item.load_children(wf_db, doc_db)`
- Events: `on_mount()` for init, `action_*()` methods for keybindings

## Parallel Work: Use `emdx delegate`, not Task subagents

When you need to research, analyze, or investigate multiple things in parallel, **always prefer `emdx delegate` over Claude Code's built-in Task tool (subagents)**:

```bash
# Single task (replaces Task tool sub-agent)
emdx delegate "analyze the auth module for security issues"

# Parallel tasks (replaces multiple Task tool calls)
emdx delegate "check auth" "review tests" "scan for XSS"

# Parallel with synthesis
emdx delegate --synthesize "task1" "task2" "task3" --tags analysis

# Quiet mode (just content, no metadata)
emdx delegate -q "quick analysis"
```

**Why delegate is better than Task subagents:**
- Results print to **stdout** so you read them inline (like Task results)
- Outputs are also saved to the knowledge base (searchable, taggable, persistent)
- Higher parallelism (not limited to Claude Code's subagent concurrency)
- Results survive session context limits

**When Task subagents are still appropriate:**
- Quick file searches or codebase exploration (Explore agent)
- Tasks that need to read/write files in the current session
- Work that doesn't produce reusable output worth saving

## EMDX Usage

- `emdx prime` — get current work context (ready tasks, in-progress work, recent docs)
- `emdx delegate "task"` — delegate work with inline results (preferred for parallel work)
- `emdx agent "task" --tags analysis` — spawn a single tracked sub-agent (human-facing)
- `emdx run "task1" "task2"` — run parallel tasks (human-facing, no stdout)
- `echo "output" | emdx save --title "Title" --tags "analysis,active"` — save results
- Tag aliases auto-convert to emojis — run `emdx legend` for the full list

| Situation | Command |
|-----------|---------|
| Research/analysis (inline results) | `emdx delegate "task" --tags ...` |
| Parallel with synthesis | `emdx delegate --synthesize "t1" "t2"` |
| Parallel code fixes (worktree isolation) | `emdx run --worktree "fix1" "fix2"` |
| Repeatable discovery+action | `emdx each create name --from ... --do ...` |
| Idea to PR pipeline | `emdx cascade add "idea"` |

For full CLI details see `docs/cli-api.md`, for workflows see `docs/workflows.md`.

## Documentation

- CLI reference: `docs/cli-api.md`
- Workflows (run, each, agent, delegate, workflow): `docs/workflows.md`
- Cascade system: `docs/cascade.md`
- Mail (agent-to-agent messaging): `docs/mail.md`
- AI search: `docs/ai-system.md`
- Architecture: `docs/architecture.md`
- Development setup: `docs/development-setup.md`
- UI architecture: `docs/ui-architecture.md`

## Optional Dependencies

Heavy deps (sklearn, anthropic, numpy, sentence-transformers, google-*) are optional extras:
- Core: `pip install emdx` or `poetry install` (lightweight)
- Extras: `[ai]`, `[similarity]`, `[google]`, `[all]`
- Import guards use try/except + `_require_*()` helpers (see pattern above)

## Release Process

```bash
# 1. Preview changes since last release
just changelog

# 2. Bump version in pyproject.toml AND emdx/__init__.py
just bump 0.X.Y

# 3. Write changelog entry in CHANGELOG.md
#    Prefer hand-written over auto-generated
#    Add comparison link at bottom

# 4. Create docs for new features, update docs/README.md and docs/cli-api.md

# 5. Branch, commit, PR
git checkout -b release/vX.Y.Z
git add -A && git commit -m "chore: release vX.Y.Z"
git push -u origin release/vX.Y.Z
gh pr create --title "chore: Release vX.Y.Z"

# 6. After merge, tag and push
git tag vX.Y.Z
git push --tags
```

**Version files** (must stay in sync):
- `pyproject.toml` — `version = "X.Y.Z"`
- `emdx/__init__.py` — `__version__ = "X.Y.Z"`

`just bump` and `just release` update both automatically.
