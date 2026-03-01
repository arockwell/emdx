# emdx

[![Version](https://img.shields.io/badge/version-0.26.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**Send agents. Save everything. Track what's next.**

Claude sessions start from zero. emdx doesn't. Save your research, fire off agents that write results back to your knowledge base, and track what's left. One CLI, local SQLite, nothing vanishes.

![emdx TUI demo](demo.gif)

## See it in action

```bash
# You ask Claude to research something. It saves the findings.
$ emdx save "Token refresh fails when clock skew > 30s..." --title "Auth Bug Analysis"
✅ Saved as #42: Auth Bug Analysis

# It fires off parallel agents for deeper analysis
$ emdx delegate "audit auth for vulnerabilities" \
                "review error handling patterns" \
                "check input validation coverage"
📋 Saved as #43: Delegate: audit auth...
📋 Saved as #44: Delegate: review error handling...
📋 Saved as #45: Delegate: check input validation...

# It tracks what needs doing
$ emdx task add "Fix token refresh bug" --cat FIX
$ emdx task add "Add rate limiting" --cat FEAT

# Everything accumulates. Nothing vanishes.
$ emdx find "auth"
🔍 Found 4 results for 'auth'

# Chain agent output into a PR
$ emdx delegate --doc 43 --pr "fix the issues from this audit"
🔀 PR #87: fix the issues from this audit
```

## Install

```bash
uv tool install emdx    # or: pip install emdx
emdx --help
```

## Save

Files, notes, piped command output — anything you save becomes searchable. Tag things so you can find them by topic later.

```bash
# Save a file
$ emdx save --file meeting-notes.md
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

## Delegate

Control how agents work, combine their output, and chain results together.

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

## Track

Organize work with tasks, epics, and categories. Delegate results feed back into the task list.

```bash
# Create tasks as you discover work
$ emdx task add "Fix token refresh bug" --cat FIX
$ emdx task add "Add rate limiting to API" --cat FEAT --epic 42

# See what's ready to work on
$ emdx task ready

# Mark progress
$ emdx task active 15
$ emdx task done 15

# Group work under epics
$ emdx task epic list
```

## AI features

Search by meaning instead of just keywords:

```bash
# "rate limiting" finds docs about throttling, backoff, quotas...
$ emdx find "how we handle rate limiting" --mode semantic

# Build a context package and pipe it to Claude
$ emdx find --context "How does auth work?" | claude

# Or ask your KB directly (needs API key)
$ emdx find --ask "What did we decide about the API redesign?"
```

## Wiki

Auto-generate a wiki from your knowledge base:

```bash
# Bootstrap: build index, extract entities, discover topics
$ emdx wiki setup

# Generate articles from topic clusters
$ emdx wiki generate -c 3
📝 Generated 47/52 articles ($0.83)

# Search and view wiki articles
$ emdx wiki search "authentication"
$ emdx wiki view 42

# Export as a static MkDocs site
$ emdx wiki export ./wiki-site --build
```

## More features

```bash
emdx maintain compact --dry-run                  # Deduplicate similar docs
emdx maintain compact --auto                     # Merge discovered clusters
emdx status                                      # Delegate activity dashboard
emdx delegate running                            # Monitor running agents
emdx gui                                         # Interactive TUI browser
```

## Quick reference

| I want to... | Command |
|--------------|---------|
| Save a file | `emdx save --file doc.md` |
| Save a note | `emdx save "quick note" --title "Title"` |
| Find by keyword | `emdx find "query"` |
| Find by tag | `emdx find --tags "active"` |
| View a document | `emdx view 42` |
| Tag a document | `emdx tag 42 analysis active` |
| Run an AI task | `emdx delegate "task"` |
| Run tasks in parallel | `emdx delegate "t1" "t2" "t3"` |
| Create a PR from a task | `emdx delegate --pr "fix the bug"` |
| Add a task | `emdx task add "title" --cat FEAT` |
| See ready tasks | `emdx task ready` |
| Ask your KB a question | `emdx find --context "question" \| claude` |
| Generate a wiki | `emdx wiki setup && emdx wiki generate` |
| Search wiki articles | `emdx wiki search "query"` |

## Documentation

- [CLI Reference](docs/cli-api.md) — Complete command documentation
- [AI System](docs/cli-api.md#find) — Semantic search, embeddings, and Q&A
- [Architecture](docs/architecture.md) — System design
- [Development Setup](docs/development-setup.md) — Contributing guide

## License

MIT License — see LICENSE file.
