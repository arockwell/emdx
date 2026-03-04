# EMDX - Knowledge Base for AI Agents

EMDX is a knowledge base that AI agents populate and humans curate. It ships as a **Claude Code plugin** with skills that handle common workflows end-to-end.

**NEVER run `emdx gui`** — it launches an interactive TUI that hangs Claude Code sessions.

## Skills — Primary Workflows

Skills are the main way to interact with emdx. Each skill handles a complete workflow. Invoke with `/emdx:<skill>`.

| Skill | What it does | Invoke |
|-------|-------------|--------|
| **work** | Pick up a task, research, implement, test, mark done | `/emdx:work [task_id]` |
| **investigate** | Deep-dive a topic: KB search + source code + gap analysis | `/emdx:investigate <topic>` |
| **review** | Run all KB quality checks, produce prioritized fix plan | `/emdx:review [focus]` |
| **prioritize** | Triage ready tasks by epic progress, deps, category, age | `/emdx:prioritize` |
| **bootstrap** | Generate foundational KB docs from a codebase | `/emdx:bootstrap [focus]` |
| **research** | Search KB for prior art before starting new work | `/emdx:research <topic>` |
| **save** | Persist findings, analysis, or decisions to KB | `/emdx:save [content]` |
| **tasks** | Add, plan subtasks, get briefs, track task status | `/emdx:tasks [action]` |

For detailed skill documentation, see [Skills Reference](docs/skills-reference.md).

## Session Protocol

### Automatic Hooks

Claude Code hooks in `.claude/settings.json` fire automatically:

| Hook | Event | What it does |
|------|-------|-------------|
| `auto-backup.sh` | SessionStart | Creates a daily KB backup before work begins |
| `prime.sh` | SessionStart | Injects KB context (ready tasks, in-progress) |
| `save-output.sh` | SubagentStop | Saves output from substantive agents (explore, plan, general-purpose) to KB with task linkage |

### What to Do in a Session

**As the main agent (interactive Claude Code):**

1. Check ready tasks: `emdx task ready`
2. For multi-step work, create subtasks BEFORE starting:
   ```bash
   emdx task plan <parent_id> "Read and understand relevant code" "Implement the changes" "Run tests and fix issues"
   emdx task done <id>   # mark each step done as you complete it
   ```
3. Save significant outputs: `echo "findings" | emdx save --title "Title" --tags "analysis,active"`
4. Create tasks for discovered work: `emdx task add "Title" -D "Details" --epic <id> --cat FEAT`

**As a subagent:**

1. Get task brief: `emdx task brief $EMDX_TASK_ID` (or `--json`)
2. Create subtasks: `emdx task plan $EMDX_TASK_ID "Step 1" "Step 2" "Step 3"`
3. Mark subtasks done as you go: `emdx task done <id>`
4. Save findings: `echo "findings" | emdx save --title "Title"`
5. Mark parent done with output: `emdx task done $EMDX_TASK_ID --output-doc <doc_id>`

## CLI Quick Reference

### Save & Search

```bash
# Save
emdx save "text content" --title "Title" --tags "notes"
emdx save --file document.md
echo "text" | emdx save --title "Title"       # most common for agents

# Search — OR/AND/NOT do NOT work (terms are quoted). Run separate finds instead.
emdx find "query"                      # Hybrid search (default)
emdx find "concept" --mode semantic    # Semantic/conceptual search
emdx find --tags "gameplan,active"     # Tag filtering (comma = AND, --any-tags for OR)
emdx find --recent 10                  # Recently accessed docs
emdx find --ask "question"             # RAG: retrieve context + LLM answer
emdx find --context "question" | claude  # Pipe retrieved context
```

### Tasks

```bash
emdx task add "Title" -D "Details" --epic 898 --cat FEAT
emdx task plan <parent> "Step 1" "Step 2" "Step 3"
emdx task brief <id>                   # Agent-ready task context
emdx task ready                        # Show unblocked tasks
emdx task active <id>                  # Mark in-progress
emdx task done <id>                    # Mark complete
emdx task done <id> --output-doc <doc> # Complete and link output document
emdx task duplicate <id>               # Mark as duplicate
emdx task epic list                    # See active epics
emdx task cat list                     # See available categories
```

**Tasks** use categories (`--cat FEAT`/`FIX`/`ARCH`/etc.) and epics (`--epic <id>`), NOT tags.

### View, Context & Status

```bash
emdx view 42                           # View document content
emdx view 42 --links                   # Show document's link graph
emdx context 87                        # Graph-walk context bundle from doc 87
emdx prime                             # Full context injection
emdx prime --smart                     # Context-aware priming
emdx status                            # KB overview
emdx stale                             # Documents needing review
```

### Maintenance

```bash
emdx maintain compact --dry-run        # Find similar docs to merge
emdx maintain index                    # Build/update embedding index
emdx maintain link --all               # Auto-link related documents
emdx maintain backup                   # Create compressed daily backup
emdx maintain freshness --stale        # Show stale docs
emdx maintain gaps                     # Detect knowledge gaps
emdx maintain drift                    # Detect stale work items
emdx maintain contradictions           # Find conflicting claims
emdx maintain code-drift               # Detect outdated code references
```

### Document Tags

| Content Type | Tags |
|--------------|------|
| Plans/strategy | `gameplan, active` |
| Investigation | `analysis` |
| Bug fixes | `bugfix` |
| Security | `security` |
| Notes | `notes` |

**Status:** `active` (working), `done` (completed), `blocked` (stuck)

For complete CLI reference, see [CLI Reference](docs/cli-api.md).

## Development

```bash
poetry install                         # Install dependencies
poetry run emdx --help                 # Always use poetry run in project dir
poetry run pytest tests/ -x -q         # Run tests
```

Dev installs use `.emdx/dev.db` automatically (not production DB). See [Development Setup](docs/development-setup.md) for details.

### Code Quality — MANDATORY

Pre-commit hooks run ruff lint, ruff format, and mypy on staged files.

```bash
poetry run ruff check . --fix          # Auto-fix what it can
poetry run ruff check .                # Must pass with zero errors
```

**Key rules:**
- Line length: **100 characters**
- Rule sets: E, W, F, I, B, C4, UP
- B904: Always `raise ... from err` or `raise ... from None` in `except` blocks
- All `--flags` before positional arguments in CLI calls
- Use `TypedDict` for known dict shapes, never `dict[str, Any]`
- Use `TYPE_CHECKING` guards for optional/heavy imports
- Default CLI output is plain text; `--rich` for colors, `--json` for structured

### Worktree Development

In a worktree, `emdx` points to the system install. Always use `poetry run emdx`.

```bash
poetry install              # Set up venv with worktree code
poetry run emdx --help      # Uses THIS worktree's code
```

### Project Structure

- `commands/` — CLI command implementations
- `config/` — Settings, constants, tagging rules
- `database/` — SQLite operations and migrations
- `ui/` — TUI components (Textual widgets)
- `services/` — Business logic
- `models/` — Data models and operations
- `utils/` — Shared utilities
- `skills/` — Claude Code plugin skills

Detailed docs: [Architecture](docs/architecture.md) | [CLI Reference](docs/cli-api.md) | [Testing](docs/testing.md) | [Development Setup](docs/development-setup.md)

### Migrations

Set-based tracking with string IDs. Existing migrations (0-58) use numeric strings. New migrations use timestamp IDs: `"YYYYMMDD_HHMMSS"`.

### Release Process

```bash
just changelog          # Preview changes since last release
just bump 0.X.Y         # Bump version in pyproject.toml + emdx/__init__.py
```

Version files that must stay in sync: `pyproject.toml`, `emdx/__init__.py`, `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`.

## Known Gotchas

- **`emdx find` does not support OR/AND/NOT** — `escape_fts5_query()` quotes each term. Use separate find calls or `--tags` with `--any-tags`.
- **`emdx task add`** not `emdx task create` — the subcommand is `add`.
- **FTS5 queries**: `documents_fts` is a separate virtual table. Must JOIN: `SELECT d.id FROM documents d JOIN documents_fts fts ON d.id = fts.rowid WHERE fts.documents_fts MATCH ?`. See `emdx/database/search.py`.
- **Mocked functions in tests**: When refactoring a function's signature, grep for mocks: `rg "mock.*<func_name>\|patch.*<func_name>" tests/`
- **Terminal state corruption in TUI**: Background threads importing heavy libraries (torch, sentence-transformers) can reset terminal from raw to cooked mode. Fix: save/restore terminal state with `termios.tcgetattr()`/`tcsetattr()`.
- **Textual `@click` meta resolution**: `@click` actions resolve only on the widget that received the click, not parent widgets. Use `app.open_url(...)` prefix to target the App.
- **`@click` + DOM mutations must be sync + `run_worker`**: Async `@click` actions that mutate the DOM deadlock. Make the action sync and use `self.run_worker(async_fn(), exclusive=True)`.
- **Don't add `on_click`/`on_mouse_down` to parent widgets** — breaks all mouse interaction globally. Use Rich Style `@click` meta with namespace prefixes.
- **Agent worktree isolation in nested worktrees**: `isolation: "worktree"` may fail silently when CWD is already a worktree. Group agents needing the same file into one agent.
- **`remove_children()` is async** — causes silent `DuplicateIds`. Always use globally unique IDs for dynamically mounted widgets.
- **RichLog sizing** — A `RichLog` starting `display: none` renders at zero width. Compose permanently, toggle `display` on the parent container, or use Textual's `Markdown` widget.
- **Rich console pager** — `console.pager()` strips colors by default. Use `console.pager(styles=True)`.

### Textual Testing Patterns

See [Testing Guide](docs/testing.md) and `tests/test_task_browser.py` for canonical patterns.

- `Static.content` returns `VisualType` — wrap with `str()` for mypy
- `RichLog.lines` contains `Strip` objects — use `line.text` property
- OptionList doesn't auto-fire `OptionHighlighted` on mount — press `j` then `k` in tests
- Mock `get_theme` to return `"textual-dark"` in BrowserContainer tests

## Plugin

emdx ships as a Claude Code plugin. Skills live in `skills/`. Manifest at `.claude-plugin/plugin.json`. Skills follow the [Agent Skills](https://agentskills.io) open standard.
