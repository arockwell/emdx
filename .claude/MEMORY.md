# EMDX Project Memory

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

## Optional Dependencies (Split in Feb 2026)
- Heavy deps (sklearn, datasketch, anthropic, numpy, sentence-transformers, google-*) are optional extras
- Core install: `pip install emdx` or `poetry install` (lightweight, no ML/AI)
- Extras: `[ai]`, `[similarity]`, `[google]`, `[all]`
- Import guards: try/except + `from __future__ import annotations` + `_require_*()` helpers
- `analyze`/`maintain` commands eagerly imported but deps guarded at method level
