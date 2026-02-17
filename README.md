# emdx

[![Version](https://img.shields.io/badge/version-0.16.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**A knowledge base that AI agents can read, write, and search — and so can you.**

Every Claude Code session starts from zero. Your research, decisions, and AI-generated analysis vanish when the session ends. You re-explain context. You re-run searches. You lose work.

emdx fixes this. It's a local knowledge base backed by SQLite. Save your research, pipe in command output, or delegate tasks to Claude agents — every result lands in one searchable place. Next session, it's all still there.

## See it in action

```bash
# You're working on a project. Save what you know.
$ emdx save security-audit.md
✅ Saved as #42: security-audit

# Have Claude analyze it for you
$ emdx delegate --doc 42 "analyze each finding and suggest fixes"
📋 Saved as #43: Delegate: analyze each finding...

# Or run three analyses in parallel — each gets its own agent
$ emdx delegate "audit auth for vulnerabilities" \
                "review error handling patterns" \
                "check for missing input validation"
📋 Saved as #44: Delegate: audit auth...
📋 Saved as #45: Delegate: review error handling...
📋 Saved as #46: Delegate: check for missing input...

# A week later, find everything — your notes and all the agent output
$ emdx find "security"
🔍 Found 5 results for 'security'

# Go straight from analysis to pull request
$ emdx delegate --doc 43 --pr "fix the issues from this analysis"
🔀 PR #87: fix the issues from this analysis
```

Everything prints to stdout and gets saved to your knowledge base. Next session, it's all still there.

## Install

```bash
uv tool install emdx    # or: pip install emdx
emdx --help
```

```bash
uv tool install 'emdx[ai]'     # Add semantic search, embeddings, Q&A
uv tool install 'emdx[all]'    # Everything
```

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

```bash
emdx compact --dry-run                           # Deduplicate similar docs
emdx distill "authentication"                    # Synthesize a topic summary
emdx distill --for coworkers "sprint progress"   # Audience-aware summaries
emdx status                                      # Delegate activity dashboard
emdx exec running                                # Monitor running agents
emdx gui                                         # Interactive TUI browser
```

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
