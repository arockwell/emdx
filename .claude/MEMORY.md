# EMDX Project Memory

## Design Philosophy
- **Claude is the primary user of emdx, not the human directly.** Alex tells Claude to use emdx. All features should optimize for machine-readability, minimal token cost, structured output (JSON), and composability. The human UX is for oversight; the hot path is Claude -> emdx CLI -> stdout -> Claude's context window.

## User Preferences
- Always use Opus 4.6 (`model: "opus"`) for all subagents — max quality, not cost optimization
- Use `poetry run emdx` in this project, never global `emdx`
- Prefer small, focused PRs over monolithic ones
- When running teams, commit work as agents finish rather than waiting for all
- When emdx delegate fails, fall back to direct web search + manual save

## Architecture Notes
- TUI screens: 1=Activity, 2=Tasks, 3=Search, 4=Cascade (reordered Feb 2026)
- Document browser removed; replaced by TaskBrowser (`task_browser.py` + `task_view.py`)
- Activity view uses `Tree[ActivityItem]` widget (migrated from DataTable in Feb 2026)
- `activity_tree.py` is the ActivityTree widget, `activity_view.py` is the main view
- `cascade_browser.py` has its own separate `ActivityFeed` with `#activity-table` — independent
- No tests exist for the activity module (all tests are for DB, CLI, workflows, etc.)

## Key Patterns
- `_get_selected_item()` returns the currently selected ActivityItem via `tree.cursor_node.data`
- `refresh_from_items()` does diff-based updates using `set_label()` — never disrupts scroll
- `populate_from_items()` is for initial full load (clears tree first)
- Tree expansion loads children lazily via `item.load_children(wf_db, doc_db)`

## Delegate System
- Branch naming: `delegate/{slug}-{5char-hash}` via `generate_delegate_branch_name()` in `utils/git.py`
- `slugify_for_branch()` strips common prefixes (Gameplan, Feature, Plan, Kink, etc.)
- PR validation: `validate_pr_preconditions()` checks commits, push status, file changes before `gh pr create`
- Streaming: `_reader_thread()` in `unified_executor.py` uses background threads + `queue.Queue` (not `select.select()`)

## Development
- Tests: `poetry run pytest tests/ -x -q` (1230+ tests, ~12s)
- No `--timeout` flag available for pytest in this project
- Always use `poetry run` for commands in the emdx project directory
- Python requirement relaxed from ^3.13 to ^3.11
- Pre-commit hooks active: ruff lint, ruff format, mypy (staged files only)
- mypy has pre-existing errors in test files (missing type annotations); use `SKIP=mypy` if blocking

## Textual Gotchas
- `Separator` does NOT exist in `textual.widgets.option_list` in our Textual version. Use `Option("", disabled=True)` as a visual spacer instead.

## emdx delegate — Known Issues & Usage Notes
- **Don't use delegate for stateful git operations** (rebase, push, commit). Delegates start fresh sessions without checkout state. Only use for read-only research/analysis.
- **`--synthesize` error**: One of 3 tasks reported "agent completed but no document was saved" before synthesis succeeded. Possible bug when using `--synthesize` with multiple tasks.
- **All `--flags` must come BEFORE positional arguments** in `emdx delegate` calls.
- **Appropriate use cases**: code review, PR evaluation, research, analysis. NOT: rebasing, committing, pushing.
- **`select.select()` broken on macOS**: Root cause of 0-byte delegate logs and hung agents. Fixed with threaded reader approach.

## Codebase Audit (2026-02-08)
- Completed comprehensive audit with 14 agents (PR #414)
- Key remaining work:
  - UI dead code: 1,272 lines across 7 files (execution/, file_list.py, file_preview.py, document_viewer.py)
  - cascade_browser.py (1,881 lines) needs SRP refactor
  - 29 direct DB/model import violations in UI layer
  - docs/cli-api.md has 8 undocumented commands
  - models/tags.py still needs proper tests (test_tags.py tests raw SQL)
  - workflows/database.py (1,051 lines) untested

## Team Patterns That Worked
- Non-overlapping file ownership prevents merge conflicts
- Test writers only CREATE new files, never touch source
- Explore agents for audit, general-purpose for implementation
- Shut down agents as they finish to free resources
- Don't do git operations (stash, checkout) while agents share working dir

## Feature Research Priorities (as of Feb 2026)
Top paths for enhancement (ranked by impact x feasibility):
1. MCP Server (emdx as native Claude tool)
2. Semantic Search (emdx find --mode semantic / emdx embed)
3. Smart Priming (context-aware session bootstrap)
4. Auto-Linking (KB self-organization on save)
5. "Dream Journal" overnight consolidation
See emdx #6092 for full 10-path deep dive.

## Optional Dependencies (Split in Feb 2026)
- Heavy deps (sklearn, datasketch, anthropic, numpy, sentence-transformers, google-*) are optional extras
- Core install: `pip install emdx` or `poetry install` (lightweight, no ML/AI)
- Extras: `[ai]`, `[similarity]`, `[google]`, `[all]`
- Import guards: try/except + `from __future__ import annotations` + `_require_*()` helpers
- `analyze`/`maintain` commands eagerly imported but deps guarded at method level
