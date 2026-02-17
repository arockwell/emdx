# emdx

[![Version](https://img.shields.io/badge/version-0.16.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**A knowledge base that AI agents can read, write, and search — and so can you.**

Every Claude Code session starts from zero. Your research, decisions, and AI-generated analysis vanish when the session ends. You re-explain context. You re-run searches. You lose work.

emdx fixes this. It's a local knowledge base backed by SQLite. Save your research, pipe in command output, or delegate tasks to Claude agents — every result lands in one searchable place. Next session, it's all still there.

## See it in action

```bash
# Save your research
$ emdx save security-audit.md
✅ Saved as #42: security-audit

# Dispatch agents to act on it — in parallel
$ emdx delegate --doc 42 "fix the critical issues" "write tests for the fixes"

# A week later, find everything — your notes and the agents' output
$ emdx find "security"
🔍 Found 4 results for 'security'
```

Every result prints to stdout and gets saved to your knowledge base. Next session, it's all still there.

## Install

```bash
uv tool install emdx    # or: pip install emdx
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

## The knowledge base

The foundation of emdx: save anything, find it later, organize with tags.

### Save anything

```bash
emdx save meeting-notes.md                              # Save a file
emdx save "the auth bug is in token refresh" --title "Auth Bug"  # Save a note
echo "plan: migrate to v2 API" | emdx save --title "Migration Plan"  # Pipe text
```

### Find it later

```bash
emdx find "auth bug"                # Full-text search (SQLite FTS5)
emdx find --tags "security,active"  # Filter by tags
emdx view 42                        # View a specific document
emdx recent                         # See what you worked on recently
```

### Tag and organize

```bash
emdx tag 42 gameplan active         # Add tags
emdx find --tags "gameplan,active"  # Search by tags
```

## Delegate work to agents

This is where emdx gets powerful. `delegate` sends tasks to Claude Code agents. Each agent runs independently, and its output is saved to your knowledge base automatically.

```bash
# Send a task to a Claude agent
emdx delegate "analyze the auth module for security issues"

# Run multiple tasks in parallel — each gets its own agent
emdx delegate "check auth" "review tests" "scan for XSS"

# Control concurrency
emdx delegate -j 3 "t1" "t2" "t3" "t4" "t5"

# Combine outputs into a synthesized summary
emdx delegate --synthesize "analyze auth" "analyze api" "analyze db"
```

### Code changes with PRs

Agents work in isolated git worktrees and can open PRs directly:

```bash
emdx delegate --pr "fix the auth bug"                   # Branch + PR
emdx delegate --doc 42 --pr "implement this plan"        # Use a doc as context
```

### Build on past work

The knowledge base and delegate feed into each other. Save research, delegate work based on it, find the results later, delegate more:

```bash
emdx delegate --doc 42 "implement the plan described here"
emdx delegate 42                                         # Run a doc directly
```

## AI features

With `emdx[ai]` installed, search by meaning and query your knowledge base:

```bash
emdx find "how we handle rate limiting" --mode semantic   # Semantic search
emdx ai context "How does auth work?" | claude            # Q&A (Claude Max — no API cost)
emdx ai ask "What did we decide about the API redesign?"  # Direct query (needs API key)
```

## Claude Code integration

Add `emdx prime` to your CLAUDE.md and every Claude Code session starts with context — ready tasks, recent documents, and in-progress work.

```bash
emdx prime    # Output current work context for Claude Code session injection
```

## More features

<details>
<summary>Compact, distill, recipes, execution monitoring, TUI, and more</summary>

### Compact — deduplicate over time

As your KB grows, `compact` clusters similar docs and merges them:

```bash
emdx compact --dry-run           # Preview clusters
emdx compact --auto              # Merge all discovered clusters
```

### Distill — synthesize for any audience

```bash
emdx distill "authentication"                    # Personal summary
emdx distill --for coworkers "sprint progress"   # Team briefing
```

### Recipes — reusable agent instructions

```bash
emdx recipe create security-audit.md --title "Security Audit"
emdx recipe run "Security Audit" -- "check auth module"
```

### Monitor running agents

```bash
emdx exec running          # List active executions
emdx exec show 42          # Follow logs
```

### Interactive TUI

```bash
emdx gui                   # Browse, edit, and manage your KB visually
```

### Activity overview

```bash
emdx status                # Delegate activity dashboard
emdx briefing              # Recent activity summary
emdx wrapup                # Synthesize what happened in the last few hours
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
| Ask your KB a question | `emdx ai context "question" \| claude` |
| Start a Claude session | `emdx prime` |

## Documentation

- [CLI Reference](docs/cli-api.md) — Complete command documentation
- [AI System](docs/ai-system.md) — Semantic search and Q&A
- [Architecture](docs/architecture.md) — System design
- [Development Setup](docs/development-setup.md) — Contributing guide

## License

MIT License — see LICENSE file.
