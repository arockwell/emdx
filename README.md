# emdx

[![Version](https://img.shields.io/badge/version-0.14.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**A searchable knowledge base that captures everything you do — and lets you delegate work to Claude agents at scale.**

EMDX is a CLI tool that stores notes, research, decisions, and AI outputs in a local SQLite database with full-text search. It's also deeply integrated with Claude Code: you can delegate tasks to agents, run them in parallel, and every result automatically lands in your knowledge base — searchable forever.

## Installation

**Requirements:** Python 3.11+

```bash
# Install with uv (recommended)
uv tool install emdx

# Or install with pip
pip install emdx

# Verify
emdx --help
```

<details>
<summary>Optional extras and development setup</summary>

```bash
# Optional extras
uv tool install 'emdx[ai]'           # Semantic search, embeddings, Claude Q&A
uv tool install 'emdx[similarity]'    # TF-IDF, MinHash duplicate detection
uv tool install 'emdx[all]'           # Everything

# Development (from source)
git clone https://github.com/arockwell/emdx.git
cd emdx
uv sync                               # or: poetry install --all-extras
uv run pytest                          # or: poetry run pytest
```

</details>

## Quick Start

### Save something

EMDX stores documents — any text you want to keep.

```bash
# Save a file
emdx save README.md

# Save a note
emdx save "Remember: the auth bug is in token refresh" --title "Auth Bug Note"

# Pipe command output
docker ps | emdx save --title "Running containers"

# Save and tag it for organization
emdx save meeting-notes.md --tags "meeting,active"
```

### Find it later

```bash
# Full-text search
emdx find "auth bug"

# Filter by tags
emdx find --tags "meeting,active"

# Combine text and tags
emdx find "docker" --tags "ops"

# View a specific document
emdx view 42

# See recent documents
emdx recent
```

### Organize with tags

Tags use emoji under the hood, but you type plain text:

```bash
# Add tags to a document
emdx tag 42 gameplan active

# See all tags in use
emdx tag list

# Search by tags
emdx find --tags "gameplan,success"
```

| Alias | Emoji | Typical use |
|-------|-------|-------------|
| `gameplan` | 🎯 | Plans and strategy |
| `analysis` | 🔍 | Research and investigation |
| `active` | 🚀 | Currently working on |
| `done` | ✅ | Completed |
| `blocked` | 🚧 | Stuck or waiting |
| `success` | 🎉 | Worked as intended |
| `failed` | ❌ | Didn't work |

Run `emdx legend` for the full alias list.

## Delegating Work to Claude

This is where EMDX gets powerful. `emdx delegate` sends tasks to Claude Code agents, and everything they produce is automatically saved to your knowledge base.

### Single task

```bash
emdx delegate "analyze the auth module for security issues"
```

The agent runs, saves its output, and the result prints to stdout. The document is also persisted — you can `emdx find "auth"` to find it later.

### Parallel tasks

Run multiple tasks concurrently. Each gets its own agent.

```bash
emdx delegate "check auth" "review tests" "scan for XSS"

# Control concurrency (5 tasks, 3 slots)
emdx delegate "t1" "t2" "t3" "t4" "t5" -j 3

# Combine outputs into a single summary
emdx delegate --synthesize "analyze auth" "analyze api" "analyze db"
```

### Sequential pipelines

Chain tasks so each step sees the previous output:

```bash
emdx delegate --chain "analyze the problem" "design a solution" "implement it"
```

### Dynamic discovery

Find items at runtime, then process each one:

```bash
# Review every Python file in src/
emdx delegate --each "fd -e py src/" --do "Review {{item}} for issues"

# Review all feature branches
emdx delegate --each "git branch -r | grep feature" --do "Review {{item}}"
```

### Use documents as input

```bash
# Pass a doc as context alongside a task
emdx delegate --doc 42 "implement the plan described here"

# Or just run a document directly by ID
emdx delegate 42
```

### Code changes with PRs

```bash
# Agent makes changes and opens a PR
emdx delegate --pr "fix the null pointer in auth"

# Isolate changes in a git worktree
emdx delegate --worktree --pr "fix X"

# All flags compose together
emdx delegate --doc 42 --chain --worktree --pr "analyze" "implement"
```

## Searching Your Knowledge Base

As your knowledge base grows, EMDX gives you several ways to find things.

### Full-text search

Built on SQLite FTS5 — fast and works out of the box:

```bash
emdx find "authentication"
emdx find "docker" --project myapp
```

### Semantic search

Find documents by meaning, not just keywords (requires `emdx[ai]` extra):

```bash
# Build the index (one-time)
emdx ai index

# Search by concept
emdx ai search "how we handle rate limiting"
```

### Q&A over your knowledge base

```bash
# Pipe relevant docs to Claude CLI (uses Claude Max, no API cost)
emdx ai context "How does the workflow system work?" | claude

# Or use the API directly (requires ANTHROPIC_API_KEY)
emdx ai ask "How did we solve the auth bug?"
```

### Similar documents

```bash
emdx similar 42                                     # Docs similar to #42
emdx similar-text "retry logic with exponential backoff"
```

## Going Further

### Cascade: ideas to code

Transform raw ideas through stages — idea → prompt → analyzed → planned → done — with the final stage creating a PR.

```bash
emdx cascade add "Add dark mode toggle to settings"
emdx cascade status
emdx cascade run          # Process all stages automatically
```

See [Cascade documentation](docs/cascade.md) for details.

### Recipes — reusable instructions

Save instructions as recipes and run them repeatedly:

```bash
emdx recipe create security-audit.md --title "Security Audit"
emdx recipe list
emdx recipe run "Security Audit" -- "check auth module"
```

### Monitoring executions

```bash
emdx exec running          # List active executions
emdx exec show 42          # Follow logs
emdx exec health           # Health check
emdx exec kill 42          # Kill a stuck execution
```

### Interactive TUI

EMDX includes a full terminal UI for browsing, editing, and managing your knowledge base:

```bash
emdx gui
```

### Claude Code integration

EMDX works as a Claude Code extension. At the start of each session:

```bash
emdx prime    # Get current work context
emdx status   # Quick overview
```

## Quick Reference

| I want to... | Command |
|--------------|---------|
| Save a file or note | `emdx save file.md` or `emdx save "text" --title "T"` |
| Find by keyword | `emdx find "query"` |
| Find by tag | `emdx find --tags "active"` |
| View a document | `emdx view 42` |
| Tag a document | `emdx tag 42 analysis active` |
| Run an AI task | `emdx delegate "task"` |
| Run tasks in parallel | `emdx delegate "t1" "t2" "t3"` |
| Chain tasks | `emdx delegate --chain "analyze" "plan" "implement"` |
| Discover + process items | `emdx delegate --each "cmd" --do "Review {{item}}"` |
| Create a PR | `emdx delegate --pr "fix the bug"` |
| Search by meaning | `emdx ai search "concept"` |
| Ask a question | `emdx ai context "question" \| claude` |
| Idea to PR pipeline | `emdx cascade add "idea"` |

## Documentation

- [CLI Reference](docs/cli-api.md) — Complete command documentation
- [Cascade](docs/cascade.md) — Idea-to-code pipeline
- [AI System](docs/ai-system.md) — Semantic search and Q&A
- [Architecture](docs/architecture.md) — System design
- [Development Setup](docs/development-setup.md) — Contributing guide

## License

MIT License — see LICENSE file.
