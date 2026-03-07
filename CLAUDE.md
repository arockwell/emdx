# EMDX - Knowledge Base CLI Tool

## CRITICAL: Interactive Commands

**NEVER run `emdx gui`** - This launches an interactive TUI that will hang Claude Code sessions.

## Project Overview

EMDX is a knowledge base that AI agents populate and humans curate. Python 3.11+, SQLite + FTS5, Textual TUI, Typer CLI.

**Design principle:** Same commands, different output modes. Same data, different views. `--json` is the agent lens. Rich tables/TUI is the human lens. Epics/categories serve both — they organize for humans and scope for agents. Agents populate the KB; humans curate and direct it.

**What's good for whom:**
- **Humans:** Hierarchy (epics/categories/groups), TUI, rendered markdown, fuzzy search, briefings
- **Agents:** `--json` output, flat task queue (`task ready`), exact ID access, `prime --json`
- **Both:** Tags, save, find, task dependencies

**Key Components:**
- `commands/` - CLI command implementations
- `config/` - Configuration management (settings, constants, tagging rules)
- `database/` - SQLite operations and migrations
- `ui/` - TUI components (Textual widgets)
- `services/` - Business logic (log streaming, file watching, etc.)
- `models/` - Data models and operations
- `utils/` - Shared utilities (git, tags, Claude integration)

**Detailed docs:** [docs/](docs/) | [Architecture](docs/architecture.md) | [CLI Reference](docs/cli-api.md) | [Development Setup](docs/development-setup.md)

## Development

```bash
poetry install          # Install dependencies
poetry run emdx --help  # Always use poetry run in project dir
poetry run pytest tests/ -x -q  # Run tests
```

### Dev Database Isolation

When running via `poetry run emdx` (editable install), emdx automatically uses a local `.emdx/dev.db` instead of `~/.config/emdx/knowledge.db`. This prevents development processes from corrupting the production database.

**Priority chain for database path:**
1. `EMDX_TEST_DB` — test isolation (set by pytest fixtures)
2. `EMDX_DB` — explicit override (e.g. `EMDX_DB=/tmp/test.db poetry run emdx status`)
3. Dev checkout detection → `<project-root>/.emdx/dev.db`
4. Production default → `~/.config/emdx/knowledge.db`

**Commands:**
- `emdx db status` — show active DB path and reason
- `emdx db path` — print just the path (for scripts)
- `emdx db copy-from-prod` — copy production DB to dev DB

### Migration Convention

Migrations use **set-based tracking** with string IDs. Existing migrations (0-58) use numeric strings. Future migrations SHOULD use timestamp IDs: `"YYYYMMDD_HHMMSS"`.

Example: `("20260301_120000", "Add new feature", migration_20260301_120000_add_new_feature)`

## Worktree Development

When working in a worktree, the global `emdx` command points to the system install — **not** the worktree code. Always run `poetry install` first, then use `poetry run emdx` to get the worktree's version:

```bash
poetry install              # Set up venv with worktree code
poetry run emdx --help      # Uses THIS worktree's code
emdx --help                 # Uses global install (may be outdated!)
```

### Worktree Cleanup

Stale worktrees can accumulate and block `gh pr checkout` and other git operations.

- Use `git worktree list` to find active worktrees
- Use `git worktree remove <path>` to remove stale worktrees
- If `gh pr checkout` fails due to existing worktrees, clone to `/tmp` instead

### Agent Worktree Patch Collection

When using `isolation: "worktree"` agents that create new files (not just modifications):
- `git diff` only captures modifications to tracked files — new/untracked files must be copied manually from the agent's worktree path (`.claude/worktrees/agent-<id>/`)
- After copying, run `ruff check --fix` and `ruff format` — agent code may not match project formatting exactly
- When multiple agents touch the same file, apply their patches sequentially with `git apply` and check for conflicts between each
- Always run the full test suite after combining all patches, not just individual agent tests

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
- All `--flags` must come BEFORE positional arguments in CLI calls

## Type Safety — MANDATORY

The codebase uses mypy strict checking. Pre-commit hooks run mypy on staged files.

**Patterns:**
- Use `TypedDict` for dict return types with known shapes — never `dict[str, Any]` when the keys are known
- Existing TypedDicts live in `database/types.py`, `models/types.py`, and `services/types.py`
- Use `TYPE_CHECKING` guards for optional/heavy imports (e.g., `EmbeddingService`, `SentenceTransformer`, `Observer`)
- Use `from __future__ import annotations` in files with forward references or TYPE_CHECKING guards
- Use `SqlParam = str | int` (or `Union[str, int, float, None]`) for dynamic SQL parameter lists — never `list[Any]`
- Use `cast()` when converting sqlite `Row` objects to TypedDicts
- Use `total=False` on TypedDicts where some fields are only present in certain code paths

**Avoid:**
- `dict[str, Any]` when the dict shape is known — define a TypedDict instead
- Bare `Any` for optional dependency types — use `TYPE_CHECKING` + `SomeType | None`
- `list[Any]` for SQL params — use a concrete union type alias

**Exceptions (intentionally `Any`):**
- Textual widget `*args: Any, **kwargs: Any` — framework convention

## CLI Output Mode Convention

- Default CLI output should be plain text (no Rich markup) for machine/pipe friendliness
- `--rich` flag enables colored Rich output (panels, markdown rendering, syntax highlighting)
- `--json` flag for structured machine output
- Use `print()` for plain output, `console.print()` only in `--rich` mode

## README Examples Convention

When writing CLI examples in README.md or docs:
- Use `$` prompts for commands
- Show realistic output (✅ Saved as #42, 📋 Saved as #43, 🔍 Found N results, 🔀 PR #87)
- Use sequential doc IDs that make narrative sense (save produces #42, later commands reference --doc 42)
- Comments should narrate the story, not describe flags
- Each code block should build progressively — later commands reference earlier output
- Don't use `<details>` collapsible sections — content is either worth showing or not

## Rich Console Gotcha

- `console.pager()` defaults to `styles=False`, stripping all colors. Always use `console.pager(styles=True)` when rendering Rich markup inside a pager.

## Claude Code Integration - MANDATORY

### Hooks (Automatic Session Lifecycle)

Claude Code hooks in `.claude/settings.json` handle session lifecycle automatically:

| Hook | Event | What it does |
|------|-------|-------------|
| `auto-backup.sh` | SessionStart | Creates a daily KB backup before work begins |
| `prime.sh` | SessionStart | Injects KB context (ready tasks, in-progress) |
| `save-output.sh` | SubagentStop | Saves output from substantive agents (explore, plan, general-purpose) to KB with task linkage |

### Session Start Protocol

`prime.sh` hook runs automatically on session start, injecting KB context.
You can also run manually:
```bash
emdx prime    # Get current work context (ready tasks, in-progress, recent docs)
emdx status   # Quick overview
```

### Mandatory Behaviors

#### For Human Sessions (interactive Claude Code)

1. **Check ready tasks** before starting work: `emdx task ready`
2. **Track progress on multi-step work** — for any task with 3+ steps, create subtasks BEFORE starting:
   ```bash
   emdx task plan <parent_id> "Read and understand relevant code" "Implement the changes" "Run tests and fix issues"
   emdx task done <id>   # mark each step done as you complete it
   ```
   This gives the user real-time visibility into progress, especially for longer tasks.
3. **Save significant outputs** to emdx: `echo "findings" | emdx save --title "Title" --tags "analysis,active"`
4. **Create tasks** for discovered work: `emdx task add "Title" -D "Details" --epic <id> --cat FEAT`
5. **Update task status as you work** — mark tasks done when complete, create new tasks for discovered work

#### For Agent/Subagent Sessions

1. **Get task brief first**: `emdx task brief $EMDX_TASK_ID` (or `--json`)
2. **Create subtasks for multi-step work**:
   `emdx task plan $EMDX_TASK_ID "Step 1" "Step 2" "Step 3"`
3. **Mark subtasks done** as you complete them: `emdx task done <id>`
4. **Save significant findings** to KB:
   `echo "findings" | emdx save --title "Title"`
5. **Mark parent task done** with output doc when complete:
   `emdx task done $EMDX_TASK_ID --output-doc <doc_id>`

### Document Tags vs Task Organization

**Documents** use plain text tags for classification:

| Content Type | Tags |
|--------------|------|
| Plans/strategy | `gameplan, active` |
| Investigation | `analysis` |
| Bug fixes | `bugfix` |
| Security | `security` |
| Notes | `notes` |

**Status:** `active` (working), `done` (completed), `blocked` (stuck)
**Outcome:** `success`, `failed`, `partial`

**Tasks** use categories and epics (NOT tags):
- `--cat FEAT` / `--cat FIX` / `--cat ARCH` etc. — assigns a category
- `--epic <id>` — groups task under a parent epic
- Use `emdx task cat list` to see available categories
- Use `emdx task epic list` to see active epics

## Essential Commands

```bash
# Save
emdx save "text content" --title "Title" --tags "notes"
emdx save --file document.md                  # Read from file
echo "text" | emdx save --title "Title"       # Pipe from stdin

# Search — FTS5 keyword search (default). OR/AND/NOT do NOT work (terms are quoted).
# To search for multiple concepts, run separate find commands or use --tags.
emdx find "query"                      # Hybrid search (default when index exists)
emdx find "concept" --mode semantic    # Semantic/conceptual search
emdx find "query" --extract            # Extract key info from results
emdx find --tags "gameplan,active"     # Tag filtering (comma = AND, use --any-tags for OR)
emdx find --all                        # List all documents
emdx find --recent 10                  # Show 10 most recently accessed docs
emdx find --similar 42                 # Find docs similar to doc #42
emdx find --context "question" | claude  # Output retrieved context for piping

# View
emdx view 42                           # View document content
emdx view 42 --links                   # Show document's link graph
emdx view 42 --review                  # Adversarial review of the document

# Tasks (use --epic and --cat, NOT --tags)
emdx task add "Title" -D "Details" --epic 898 --cat FEAT
emdx task plan <parent> "Step 1" "Step 2" "Step 3"  # Batch create subtasks
emdx task brief <id>                   # Agent-ready task context
emdx task brief <id> --json            # Structured for programmatic use
emdx task ready                        # Show unblocked tasks
emdx task active <id>                  # Mark in-progress
emdx task done <id>                    # Mark complete
emdx task done <id> --output-doc <doc> # Complete and link output document
emdx task duplicate <id>               # Mark as duplicate
emdx task epic list                    # See active epics
emdx task cat list                     # See available categories
emdx task cat rename OLD NEW           # Rename or merge categories

# Tags
emdx tag add 42 gameplan active
emdx tag list

# Priming
emdx prime                             # Full context injection
emdx prime --smart                     # Context-aware: recent activity, key docs, knowledge map
emdx prime --brief                     # Compact: tasks + epics only

# Staleness
emdx stale                             # Show documents needing review by urgency
emdx stale --tier critical             # Show only critical tier
emdx touch 42                          # Mark doc as reviewed (no view count bump)

# Status
emdx status                            # Knowledge base overview
emdx status --stats                    # Knowledge base statistics
emdx status --stats --detailed         # Detailed stats with project breakdown
emdx status --vitals                   # KB vitals dashboard
emdx status --mirror                   # Reflective KB summary (narrative)

# Maintenance (stable)
emdx maintain index                    # Build/update embedding index
emdx maintain link --all               # Auto-link related documents
# Note: `emdx save` auto-links new docs by default (--auto-link/--no-auto-link).
# Configure via `maintain.auto_link_on_save` setting.
emdx maintain backup                   # Create compressed daily backup
emdx maintain backup --list            # List existing backups
emdx maintain backup --restore <file>  # Restore from a backup
emdx maintain freshness                # Score document freshness (staleness)
emdx maintain freshness --stale        # Show only stale docs

# Labs — experimental commands (may change or be removed)
emdx labs ask "question"               # RAG: retrieve context + LLM answer
emdx labs ask --think "question"       # Deliberative: position paper
emdx labs ask --debug "bug"            # Socratic debugger
emdx labs ask --cite "question"        # Inline [#ID] citations
emdx labs wander                       # Serendipity: surprising connections
emdx labs wander "topic"              # Serendipity from a topic seed
emdx labs watch add "query"           # Save as standing query
emdx labs watch check                  # Check standing queries
emdx labs watch list                   # List standing queries
emdx labs context 87                   # Graph-walk context bundle
emdx labs briefing                     # Recent activity summary
emdx labs compact --dry-run            # AI-powered doc merging
emdx labs distill "topic"              # Audience-aware synthesis
emdx labs wiki setup                   # Auto-wiki bootstrap
emdx labs explore                      # Topic clustering map
emdx labs maintain drift               # Detect stale work items
emdx labs maintain gaps                # Detect knowledge gaps
emdx labs maintain contradictions      # Find conflicting claims
emdx labs maintain code-drift          # Detect stale code refs
emdx labs maintain cloud-backup upload # Cloud backup to Gists

# History / Diff — document versioning
emdx history 42                        # Show version history for doc #42
emdx diff 42                           # Diff current vs previous version
emdx diff 42 1                         # Diff current vs version 1

# Database
emdx db status                         # Show active DB path and reason
emdx db path                           # Print just the path (for scripts)
emdx db copy-from-prod                 # Copy production DB to dev DB
```

For complete command reference, see [CLI Reference](docs/cli-api.md).
For AI system docs, see [CLI Reference — Find](docs/cli-api.md#find).

## TUI Debugging & Logging

### Log File Locations
| File | Purpose | Written by |
|------|---------|------------|
| `~/.config/emdx/tui_debug.log` | TUI runtime logs | `setup_tui_logging()` in `run_browser.py` |
| `~/.config/emdx/emdx.log` | CLI command logs | `get_logger()` in `logging_utils.py` |
| `~/.config/emdx/key_events.log` | Key events (WARNING+ only) | `setup_tui_logging()` |

### Log Levels
- **Root logger**: WARNING (suppresses noisy third-party libs)
- **`emdx.*` loggers**: INFO (all emdx modules)
- To see `logger.debug()` calls, you must temporarily change the level in `setup_tui_logging()` or set it per-module

### Quick Debug Workflow
```bash
# Watch TUI logs live while running GUI in another terminal
tail -f ~/.config/emdx/tui_debug.log

# Check recent TUI logs after a session
tail -100 ~/.config/emdx/tui_debug.log

# Check for errors only
grep -E "ERROR|WARNING|CRITICAL" ~/.config/emdx/tui_debug.log | tail -30
```

### Common Pitfall
- `logger.debug("msg")` will NOT appear in TUI logs — emdx.* level is INFO. Use `logger.info()` or `logger.warning()` for debug output that must be visible.
- TUI logs and CLI logs go to DIFFERENT files. If you're debugging the GUI, check `tui_debug.log`, not `emdx.log`.

## Known Gotchas

- **`emdx find` does not support OR/AND/NOT** — `escape_fts5_query()` quotes each term, making operators literal. Use separate find calls or `--tags` with `--any-tags`.
- **`emdx task add`** not `emdx task create` — the subcommand is `add`.
- **FTS5 virtual table queries**: `documents_fts` is a separate FTS5 virtual table, NOT a column on `documents`. You must JOIN it: `SELECT d.id FROM documents d JOIN documents_fts fts ON d.id = fts.rowid WHERE fts.documents_fts MATCH ?`. Never use `WHERE documents_fts MATCH ?` directly on the documents table — it silently fails with "no such column". See `emdx/database/search.py` for the canonical pattern.
- **Mocked internal functions in tests**: When refactoring a function's signature (parameters, return type), grep for tests that mock it — they break silently. Use: `rg "mock.*<func_name>\|patch.*<func_name>" tests/`
- **Terminal state corruption in TUI**: Running code in background threads (via `asyncio.to_thread`) that imports heavy libraries (torch, sentence-transformers) or runs subprocesses can reset the terminal from raw mode to cooked mode, killing Textual's mouse/key handling. **Fix**: Save terminal state with `termios.tcgetattr()` before the threaded call and restore with `termios.tcsetattr()` after.
- **Textual `@click` meta namespace resolution**: `@click` actions in Rich Text rendered inside a widget resolve ONLY on the widget that received the click — they do NOT walk up the DOM. If you put `meta={"@click": "open_url(...)"}` in a RichLog's text, Textual looks for `action_open_url` on the RichLog, not on parent widgets. Use `app.open_url(...)` prefix to target the App, or `screen.open_url(...)` for the Screen. This applies to `@click`, `@mouse.down`, and `@mouse.up` meta actions.
- **Don't add `on_click`/`on_mouse_down` to parent widgets**: Adding `on_click`, `on_mouse_down`, or `on_mouse_up` handlers to a parent Widget (or subclassing RichLog with these handlers) can break all mouse interaction in the TUI globally. Prefer Rich Style `@click` meta with namespace prefixes (e.g. `app.action_name(...)`) instead of custom mouse event handlers.
- **`@click` actions that mutate the DOM must be sync + `run_worker`**: Textual dispatches `@click` meta actions synchronously. If the target action is `async` and does DOM mutations (`remove_children`, `mount`, `switch_browser`), it will deadlock the message loop and freeze the TUI. **Fix:** Make the action method sync, store any state you need, and use `self.run_worker(async_fn(), exclusive=True)` to defer the async work. See `BrowserContainer.action_select_doc()` for the canonical pattern. `action_open_url()` (sync, no DOM changes) works fine as-is.
- **Agent worktree isolation in nested worktrees**: When CWD is already a git worktree (e.g., `.worktrees/feature-xyz`), `isolation: "worktree"` on Agent tool may fail silently — agents fall back to writing directly to the shared working tree. This is fine if agents own non-overlapping files. If two agents need the same file, group them into one agent. Clean stale worktrees periodically: `git worktree list` + `git worktree remove --force <path>`.

## Textual Pilot Testing Patterns

- `Static.content` returns `VisualType` (not `str`) — always wrap with `str()` for mypy: `assert "text" in str(bar.content)`
- `RichLog.lines` contains `Strip` objects with `.text` property — use helper: `"\n".join(line.text for line in widget.lines)`
- OptionList doesn't auto-fire `OptionHighlighted` on mount — press `j` then `k` to trigger detail pane rendering in tests
- Mouse click tests need explicit `offset=(x, y)` to hit specific rows; clicking without offset may hit disabled headers
- BrowserContainer tests: let `register_all_themes` run normally, mock `get_theme` to return `"textual-dark"` (a built-in theme) to avoid `InvalidThemeError`
- `Static` has no `.renderable` attribute — use `.content` property instead
- See `tests/test_task_browser.py` for canonical patterns: `TaskTestApp`, `mock_task_data` fixture, `_richlog_text()` helper, `_select_first_task()` helper

## Release Process

```bash
just changelog          # Preview changes since last release
just bump 0.X.Y         # Bump version in pyproject.toml + emdx/__init__.py
# Write changelog entry in CHANGELOG.md
# Update version badge in README.md
# Update version in .claude-plugin/plugin.json
# Check for new commands/features needing docs updates (docs/cli-api.md, CLAUDE.md)
# Branch, commit, PR, merge, then:
git tag vX.Y.Z && git push --tags
```

Version files that must stay in sync: `pyproject.toml`, `emdx/__init__.py`, `.claude-plugin/plugin.json`, and `.claude-plugin/marketplace.json`.

**Doc check:** If new commands or flags were added, verify they appear in `docs/cli-api.md` (subcommand tables + examples) and `CLAUDE.md` (essential commands section).

## Claude Code Plugin

emdx ships as a Claude Code plugin with skills in the `skills/` directory at the repo root. Users install it with `--plugin-dir` or via a marketplace. Skills are namespaced as `/emdx:<skill>`.

**Available skills:** `/emdx:bootstrap`, `/emdx:investigate`, `/emdx:prioritize`, `/emdx:research`, `/emdx:review`, `/emdx:save`, `/emdx:tasks`, `/emdx:work`

The plugin manifest lives at `.claude-plugin/plugin.json`. Skills follow the [Agent Skills](https://agentskills.io) open standard.
