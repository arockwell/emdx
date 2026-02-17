# emdx

[![Version](https://img.shields.io/badge/version-0.16.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**The knowledge base that can go get its own knowledge.**

Every Claude Code session starts from zero. Your research, decisions, and AI-generated analysis vanish when the session ends. You re-explain context. You re-run searches. You lose work.

emdx fixes this. It's a CLI tool — a local knowledge base backed by SQLite. Save your research, pipe in command output, or delegate tasks to Claude agents — every result lands in one searchable place. Next session, it's all still there.

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

Everything prints to stdout and gets saved to your knowledge base.

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

Anything you save becomes searchable — files, notes, piped command output. Tag things so you can find them by topic later.

```bash
# Save a file
$ emdx save meeting-notes.md
✅ Saved as #12: meeting-notes

# Save a quick note
$ emdx save "the auth bug is in token refresh" --title "Auth Bug"
✅ Saved as #13: Auth Bug

# Pipe in anything
$ docker logs api --since 1h | emdx save --title "API errors"
✅ Saved as #14: API errors

# Tag things so you can slice by topic
$ emdx tag 12 planning active
$ emdx tag 13 bugfix security

# Find by keyword — full-text search across everything
$ emdx find "auth"
🔍 Found 3 results for 'auth'

# Or filter by tags
$ emdx find --tags "security"
```

## Delegate work to agents

You saw the basics in the hero. Here's where it gets interesting — you can control how agents work, combine their output, and chain results together.

```bash
# Throttle concurrency when you have a lot of tasks
$ emdx delegate -j 3 "t1" "t2" "t3" "t4" "t5"

# Combine outputs into one synthesized summary
$ emdx delegate --synthesize "analyze auth" "analyze api" "analyze db"
📋 Saved as #60: Synthesis: analyze auth, analyze api, analyze db

# Feed previous results into new tasks
$ emdx delegate --doc 60 "write an action plan based on this analysis"
📋 Saved as #61: Delegate: write an action plan...

# Or run a saved document as a prompt directly
$ emdx delegate 61
```

Agents can also make code changes. They work in isolated git worktrees so your working tree stays clean:

```bash
# Create a branch and open a PR
$ emdx delegate --pr "fix the auth bug"
🔀 PR #88: fix the auth bug

# Use a doc as context for the change
$ emdx delegate --doc 42 --pr "implement this plan"
🔀 PR #89: implement this plan
```

## AI features

With `emdx[ai]` installed, search by meaning instead of just keywords:

```bash
# "rate limiting" finds docs about throttling, backoff, quotas...
$ emdx find "how we handle rate limiting" --mode semantic

# Build a context package and pipe it to Claude
$ emdx ai context "How does auth work?" | claude

# Or ask your KB directly (needs API key)
$ emdx ai ask "What did we decide about the API redesign?"
```

## Claude Code integration

Add `emdx prime` to your CLAUDE.md and every Claude Code session starts with context — ready tasks, recent documents, and in-progress work.

```bash
$ emdx prime    # Output current work context for Claude Code session injection
```

## More features

```bash
emdx compact --dry-run                           # Deduplicate similar docs
emdx compact --auto                              # Merge discovered clusters
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
