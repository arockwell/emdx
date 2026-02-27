# EMDX - Knowledge Base CLI Tool

## CRITICAL: Interactive Commands

**NEVER run `emdx gui`** - This launches an interactive TUI that will hang Claude Code sessions.

## Project Overview

EMDX is a knowledge base that AI agents populate and humans curate. Python 3.11+, SQLite + FTS5, Textual TUI, Typer CLI.

**Design principle:** Same commands, different output modes. Same data, different views. `--json` is the agent lens. Rich tables/TUI is the human lens. Epics/categories serve both — they organize for humans and scope for agents. Agents populate the KB; humans curate and direct it.

**What's good for whom:**
- **Humans:** Hierarchy (epics/categories/groups), TUI, rendered markdown, fuzzy search, briefings
- **Agents:** `--json` output, flat task queue (`task ready`), exact ID access, `prime --json`
- **Both:** Tags, save, find, delegate, task dependencies

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
- `cli_executor/` — genuinely polymorphic JSON from Claude CLI streaming
- `unified_executor.py` `ExecutionResult.to_dict()` — serialization method
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
- Use sequential doc IDs that make narrative sense (save produces #42, delegate references --doc 42)
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
| `prime.sh` | SessionStart | Injects KB context (ready tasks, in-progress) |
| `save-output.sh` | Stop | Auto-saves output to KB (delegate sessions only) |
| `session-end.sh` | SessionEnd | Updates task status (delegate sessions only) |

**Hooks are ambient** — `prime.sh` runs for all sessions. The save/end hooks only activate
when the delegate launcher sets env vars (`EMDX_AUTO_SAVE=1`, `EMDX_TASK_ID`).

**Env vars recognized by hooks:**

| Variable | Set by | Used by | Purpose |
|----------|--------|---------|---------|
| `EMDX_AUTO_SAVE` | delegate | save-output.sh | Enable auto-save ("1" to activate) |
| `EMDX_DOC_ID` | delegate | prime.sh | Include document as context |
| `EMDX_TASK_ID` | delegate | prime.sh, session-end.sh | Track task lifecycle |
| `EMDX_TITLE` | delegate | save-output.sh | Document title for saved output |
| `EMDX_TAGS` | delegate | save-output.sh | Tags for saved output |
| `EMDX_BATCH_FILE` | delegate | save-output.sh | Parallel coordination file |
| `EMDX_EXECUTION_ID` | delegate | session-end.sh | Execution record to update |

### Session Start Protocol

**Human sessions:** `prime.sh` hook runs automatically on session start, injecting KB context.
You can also run manually:
```bash
emdx prime    # Get current work context (ready tasks, in-progress, recent docs)
emdx status   # Quick overview
```

**Delegate sessions:** `prime.sh` runs automatically with task-specific context via `EMDX_TASK_ID`
and `EMDX_DOC_ID` env vars. No manual priming needed.

### Mandatory Behaviors

#### For Human Sessions (interactive Claude Code)

1. **Check ready tasks** before starting work: `emdx task ready`
2. **Save significant outputs** to emdx: `echo "findings" | emdx save --title "Title" --tags "analysis,active"`
3. **Create tasks** for discovered work: `emdx task add "Title" -D "Details" --epic <id> --cat FEAT`
4. **Never end session** without updating task status and creating tasks for remaining work

#### For Delegate Sessions (emdx delegate sub-agents)

1. **Focus exclusively on your assigned task** — do NOT check ready tasks or pick up other work
2. **Do NOT manually save output** — the `save-output.sh` hook handles this automatically
3. **Do NOT manually update task status** — the `session-end.sh` hook handles this automatically
4. **Do NOT sub-delegate** — no recursive `emdx delegate` calls

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

# Push branch only, no PR (--branch implies --worktree)
emdx delegate --branch "add logging to auth module"

# Draft PR
emdx delegate --pr --draft "experimental feature"

# Custom base branch
emdx delegate --branch -b develop "add feature X"

# All flags compose together
emdx delegate --doc 42 --pr "fix the bug"
```

**All options:** `--tags`, `--title`, `-j` (max parallel), `--model`, `--sonnet`, `--opus`, `-q` (quiet), `--base-branch`/`-b`, `--branch`, `--pr`, `--draft`/`--no-draft`, `--worktree`/`-w`, `--epic`/`-e`, `--cat`/`-c`, `--tool` (extra allowed tools), `--cleanup`

### Quick Reference

| Situation | Command |
|-----------|---------|
| Research/analysis | `emdx delegate "task"` |
| Parallel research | `emdx delegate "t1" "t2" "t3"` |
| Combined summary | `emdx delegate --synthesize "t1" "t2"` |
| Doc as input | `emdx delegate --doc 42 "implement this"` |
| Code changes with PR | `emdx delegate --pr "fix the bug"` |
| Push branch, no PR | `emdx delegate --branch "add feature"` |
| Clean up worktrees | `emdx delegate --cleanup` |

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
emdx find --ask "question"             # RAG: retrieve context + LLM answer
emdx find --context "question" | claude  # Output retrieved context for piping

# View
emdx view 42                           # View document content
emdx view 42 --links                   # Show document's link graph

# Tasks (use --epic and --cat, NOT --tags)
emdx task add "Title" -D "Details" --epic 898 --cat FEAT
emdx task ready                        # Show unblocked tasks
emdx task active <id>                  # Mark in-progress
emdx task done <id>                    # Mark complete
emdx task epic list                    # See active epics
emdx task cat list                     # See available categories
emdx task cat rename OLD NEW           # Rename or merge categories

# Tags
emdx tag add 42 gameplan active
emdx tag list

# Status
emdx status                            # Delegate activity overview
emdx status --stats                    # Knowledge base statistics
emdx status --stats --detailed         # Detailed stats with project breakdown

# Maintenance
emdx maintain compact --dry-run        # Find similar docs to merge
emdx maintain index                    # Build/update embedding index
emdx maintain link --all               # Auto-link related documents
# Note: `emdx save` auto-links new docs by default (--auto-link/--no-auto-link).
# Configure via `maintain.auto_link_on_save` setting.

# Wiki
emdx maintain wiki setup               # Full bootstrap (index → entities → topics → auto-label)
emdx maintain wiki topics --save --auto-label  # Discover and label topics
emdx maintain wiki triage --skip-below 0.05    # Bulk skip low-coherence topics
emdx maintain wiki triage --auto-label         # LLM-label all topics
emdx maintain wiki progress            # Show generation progress + costs
emdx maintain wiki generate            # Generate articles (sequential)
emdx maintain wiki generate -c 3       # Generate with 3 concurrent
emdx maintain wiki export ./wiki-site  # Export to MkDocs
emdx maintain wiki export ./wiki-site --topic 42  # Single article
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

## Delegate Cleanup Gotchas

- When delegates remove functions, they sometimes miss: (1) tests importing the removed code, (2) private methods called from OTHER files, (3) entirely dead files that should be deleted not just pruned
- Always check CI after delegate cleanup PRs — `ImportError` in tests is the most common failure mode
- When multiple delegate PRs touch the same file, merge one at a time — they WILL conflict with each other

## Known Gotchas

- **`emdx find` does not support OR/AND/NOT** — `escape_fts5_query()` quotes each term, making operators literal. Use separate find calls or `--tags` with `--any-tags`.
- **`emdx task add`** not `emdx task create` — the subcommand is `add`.
- **`select.select()` on macOS**: Python's `select.select()` does not work reliably on `subprocess.Popen` stdout/stderr pipes on macOS. Use background threads with `queue.Queue` instead (see `_reader_thread()` in `unified_executor.py`).
- **Delegate log monitoring**: When running parallel delegates, verify logs are non-zero with `wc -c` on the log files. Zero-byte logs indicate a streaming bug, not an empty task.
- **FTS5 virtual table queries**: `documents_fts` is a separate FTS5 virtual table, NOT a column on `documents`. You must JOIN it: `SELECT d.id FROM documents d JOIN documents_fts fts ON d.id = fts.rowid WHERE fts.documents_fts MATCH ?`. Never use `WHERE documents_fts MATCH ?` directly on the documents table — it silently fails with "no such column". See `emdx/database/search.py` for the canonical pattern.
- **Mocked internal functions in tests**: When refactoring a function's signature (parameters, return type), grep for tests that mock it — they break silently. Use: `rg "mock.*<func_name>\|patch.*<func_name>" tests/`
- **Duplicate PRs from redone delegates**: When closing a stale delegate PR and redoing it fresh, ensure the old PR is actually closed *before* the new one merges. If both get merged, you'll get duplicate definitions (as happened with #697/#698 both adding `ExecutionResultDict`, breaking main with mypy `no-redef` errors).
- **Terminal state corruption in TUI**: Running code in background threads (via `asyncio.to_thread`) that imports heavy libraries (torch, sentence-transformers) or runs subprocesses can reset the terminal from raw mode to cooked mode, killing Textual's mouse/key handling. **Fix**: Save terminal state with `termios.tcgetattr()` before the threaded call and restore with `termios.tcsetattr()` after. This also explains why `UnifiedExecutor` corrupted the terminal — its `get_subprocess_env()` or subprocess execution path triggers the same reset.
- **Textual `@click` meta namespace resolution**: `@click` actions in Rich Text rendered inside a widget resolve ONLY on the widget that received the click — they do NOT walk up the DOM. If you put `meta={"@click": "open_url(...)"}` in a RichLog's text, Textual looks for `action_open_url` on the RichLog, not on parent widgets. Use `app.open_url(...)` prefix to target the App, or `screen.open_url(...)` for the Screen. This applies to `@click`, `@mouse.down`, and `@mouse.up` meta actions.
- **Don't add `on_click`/`on_mouse_down` to parent widgets**: Adding `on_click`, `on_mouse_down`, or `on_mouse_up` handlers to a parent Widget (or subclassing RichLog with these handlers) can break all mouse interaction in the TUI globally. Prefer Rich Style `@click` meta with namespace prefixes (e.g. `app.action_name(...)`) instead of custom mouse event handlers.

## Textual Pilot Testing Patterns

- `Static.content` returns `VisualType` (not `str`) — always wrap with `str()` for mypy: `assert "text" in str(bar.content)`
- `RichLog.lines` contains `Strip` objects with `.text` property — use helper: `"\n".join(line.text for line in widget.lines)`
- OptionList doesn't auto-fire `OptionHighlighted` on mount — press `j` then `k` to trigger detail pane rendering in tests
- Mouse click tests need explicit `offset=(x, y)` to hit specific rows; clicking without offset may hit disabled headers
- BrowserContainer tests: let `register_all_themes` run normally, mock `get_theme` to return `"textual-dark"` (a built-in theme) to avoid `InvalidThemeError`
- `Static` has no `.renderable` attribute — use `.content` property instead
- See `tests/test_task_browser.py` for canonical patterns: `TaskTestApp`, `mock_task_data` fixture, `_richlog_text()` helper, `_select_first_task()` helper

## Delegate Debugging

### Stuck Delegate Diagnostics
If a delegate appears stuck (no output beyond worktree creation):

1. Check process: `ps -o etime=,%cpu= -p <PID>`
2. Check TCP connections: `lsof -p <PID> 2>/dev/null | grep TCP | wc -l`
   - **2+ connections** = healthy, waiting on API response
   - **0 connections** = stuck, kill and re-dispatch
3. Check worktree: `cd <worktree> && git status` — see if files were created
4. Kill: `kill <PID>` then clean up worktree: `git worktree remove <path> --force`

### Common Causes of Hanging
- Shared virtualenv editable install pointing to deleted worktree (fix: `poetry lock && poetry install`)

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

Version files that must stay in sync: `pyproject.toml`, `emdx/__init__.py`, and `.claude-plugin/plugin.json`.

**Doc check:** If new commands or flags were added, verify they appear in `docs/cli-api.md` (subcommand tables + examples) and `CLAUDE.md` (essential commands section).

## Claude Code Plugin

emdx ships as a Claude Code plugin with skills in the `skills/` directory. Users install it with `--plugin-dir` or via a marketplace. Skills are namespaced as `/emdx:<skill>`.

**Available skills:** `/emdx:save`, `/emdx:delegate`, `/emdx:research`, `/emdx:prime`, `/emdx:wrapup`, `/emdx:tasks`

The plugin manifest lives at `.claude-plugin/plugin.json`. Skills follow the [Agent Skills](https://agentskills.io) open standard.
