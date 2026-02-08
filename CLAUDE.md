# EMDX - Knowledge Base CLI Tool

## CRITICAL: Never run `emdx gui`

This launches an interactive TUI that will hang Claude Code sessions. Use CLI commands instead.

## Project Overview

EMDX is a CLI knowledge base and documentation management system. Python 3.11+, SQLite+FTS5, Textual TUI, Typer CLI.

**Key Components:**
- `commands/` - CLI command implementations
- `database/` - SQLite operations and migrations
- `ui/` - TUI components (Textual widgets)
- `services/` - Business logic (log streaming, file watching)
- `models/` - Data models and operations
- `utils/` - Shared utilities (git, emoji aliases, Claude integration)

## Development

In the EMDX project directory, always use `poetry run emdx` instead of the global `emdx` command (global may point to a different worktree with missing deps).

```bash
poetry install              # Install deps
poetry run emdx --help      # Run CLI
poetry run pytest tests/ -x -q   # Run tests (~411 tests, ~23s)
```

## Documentation Pointers

- CLI reference: `docs/cli-api.md`
- Workflows (run, each, agent, workflow): `docs/workflows.md`
- Cascade system: `docs/cascade.md`
- AI search: `docs/ai-system.md`
- Architecture: `docs/architecture.md`
- Development setup: `docs/development-setup.md`
- UI architecture: `docs/ui-architecture.md`

## Optional Dependencies

Heavy deps (sklearn, anthropic, numpy, sentence-transformers, google-*) are optional extras:
- Core: `pip install emdx` or `poetry install` (lightweight)
- Extras: `[ai]`, `[similarity]`, `[google]`, `[all]`
- Import guards use try/except + `_require_*()` helpers

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
