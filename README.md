# emdx

[![Version](https://img.shields.io/badge/version-0.16.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**A knowledge base that AI agents can read, write, and search — and so can you.**

Every Claude Code session starts from zero. Your research, decisions, and AI-generated analysis vanish when the session ends. You re-explain context. You re-run searches. You lose work.

emdx fixes this. It's a local knowledge base backed by SQLite. Save your research, pipe in command output, or delegate tasks to Claude agents — every result lands in one searchable place. Next session, it's all still there.

## See it in action

```bash
# Dispatch three agents in parallel — results saved to your KB
emdx delegate "analyze auth module" "review test coverage" "check for XSS"

# A week later, find what they discovered
emdx find "XSS"

# Build on past work — feed a previous analysis into a new task
emdx delegate --doc 84 "implement the fixes from this security analysis"

# Or go straight to a PR
emdx delegate --pr "fix the null pointer in token refresh"
```

Each result prints to stdout (so you can read it inline) and gets saved to your knowledge base (so you can find it later).

## Install

```bash
pip install emdx        # or: uv tool install emdx
emdx --help
```

<details>
<summary>Optional extras</summary>

```bash
pip install 'emdx[ai]'          # Semantic search, embeddings, Q&A
pip install 'emdx[similarity]'  # TF-IDF duplicate detection
pip install 'emdx[all]'         # Everything
```

</details>

## The basics: save, find, build

### Save anything

```bash
emdx save meeting-notes.md                              # Save a file
emdx save "the auth bug is in token refresh" --title "Auth Bug"  # Save a note
docker ps | emdx save --title "Running containers"       # Pipe any command
```

### Find it later

```bash
emdx find "auth bug"                # Full-text search (SQLite FTS5)
emdx find --tags "security,active"  # Filter by tags
emdx view 42                        # View a specific document
emdx recent                         # See what you worked on recently
```

### Tag and organize

Tags use plain text that maps to emoji under the hood:

```bash
emdx tag 42 gameplan active         # Add tags
emdx find --tags "gameplan,active"  # Search by tags
```

| You type | Means | Use for |
|----------|-------|---------|
| `gameplan` | 🎯 | Plans and strategy |
| `analysis` | 🔍 | Research and investigation |
| `active` | 🚀 | Currently working on |
| `done` | ✅ | Completed |
| `blocked` | 🚧 | Stuck or waiting |

## Delegate work to Claude agents

This is where emdx gets powerful. `delegate` sends tasks to Claude Code agents and saves their output to your knowledge base.

### Parallel execution

Run multiple tasks concurrently — each gets its own agent:

```bash
emdx delegate "check auth" "review tests" "scan for XSS"

# Control concurrency
emdx delegate -j 3 "t1" "t2" "t3" "t4" "t5"

# Combine outputs into a single synthesized summary
emdx delegate --synthesize "analyze auth" "analyze api" "analyze db"
```

### Dynamic discovery

Find items at runtime, then process each one:

```bash
# Review every Python file in src/
emdx delegate --each "fd -e py src/" --do "Review {{item}} for issues"

# Review all open PRs
emdx delegate --each "gh pr list --json number -q '.[].number'" \
  --do "Review PR #{{item}}"
```

### Code changes with PRs

Agents can make changes in isolated git worktrees and open PRs:

```bash
emdx delegate --pr "fix the auth bug"                   # Branch + PR
emdx delegate --worktree --pr "fix X"                    # Isolated worktree + PR
emdx delegate --doc 42 --pr "implement this plan"        # Use a doc as context
```

### Use your knowledge base as input

```bash
emdx delegate --doc 42 "implement the plan described here"
emdx delegate 42                                         # Run a doc directly
```

## Search and synthesize

### Semantic search

Find documents by meaning, not just keywords (requires `emdx[ai]`):

```bash
emdx find "how we handle rate limiting" --mode semantic
```

### Q&A over your knowledge base

```bash
# Pipe relevant docs to Claude (uses Claude Max — no API cost)
emdx ai context "How does the auth system work?" | claude

# Or query directly (requires ANTHROPIC_API_KEY)
emdx ai ask "What did we decide about the API redesign?"
```

### Compact: deduplicate over time

As your KB grows, related documents pile up. `compact` clusters similar docs and merges them:

```bash
emdx compact --dry-run           # Preview clusters (no API calls)
emdx compact --auto              # Merge all discovered clusters
emdx compact --topic "auth"      # Only cluster docs about a topic
```

Originals are tagged `superseded` (not deleted) so nothing is lost.

### Distill: synthesize for any audience

```bash
emdx distill "authentication"                    # Personal summary
emdx distill --for coworkers "sprint progress"   # Team briefing
emdx distill --for docs "API design" --save      # Save result to KB
```

## Claude Code integration

emdx is designed to work alongside Claude Code. Add emdx commands to your CLAUDE.md and agents will use them as part of their workflow.

```bash
emdx prime    # Inject current work context at session start
emdx status   # Quick overview of recent activity
emdx wrapup   # Generate a session summary before ending
```

## More features

<details>
<summary>Recipes, execution monitoring, TUI, and more</summary>

### Recipes — reusable agent instructions

```bash
emdx recipe create security-audit.md --title "Security Audit"
emdx recipe list
emdx recipe run "Security Audit" -- "check auth module"
```

### Monitor running agents

```bash
emdx exec running          # List active executions
emdx exec show 42          # Follow logs
emdx exec kill 42          # Kill a stuck execution
```

### Interactive TUI

Browse, edit, and manage your knowledge base visually:

```bash
emdx gui
```

### Briefings

See what happened in your knowledge base recently:

```bash
emdx briefing              # Activity summary
```

</details>

## Quick reference

| I want to... | Command |
|--------------|---------|
| Save a file or note | `emdx save file.md` |
| Find by keyword | `emdx find "query"` |
| Find by tag | `emdx find --tags "active"` |
| View a document | `emdx view 42` |
| Tag a document | `emdx tag 42 analysis active` |
| Run an AI task | `emdx delegate "task"` |
| Run tasks in parallel | `emdx delegate "t1" "t2" "t3"` |
| Create a PR from a task | `emdx delegate --pr "fix the bug"` |
| Process items dynamically | `emdx delegate --each "cmd" --do "task {{item}}"` |
| Search by meaning | `emdx find "concept" --mode semantic` |
| Ask your KB a question | `emdx ai context "question" \| claude` |
| Deduplicate the KB | `emdx compact --dry-run` |
| Synthesize a topic | `emdx distill "topic"` |
| Start a Claude session | `emdx prime` |

## Documentation

- [CLI Reference](docs/cli-api.md) — Complete command documentation
- [AI System](docs/ai-system.md) — Semantic search and Q&A
- [Architecture](docs/architecture.md) — System design
- [Development Setup](docs/development-setup.md) — Contributing guide

## License

MIT License — see LICENSE file.
