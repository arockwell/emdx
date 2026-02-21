# emdx

[![Version](https://img.shields.io/badge/version-0.19.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**One CLI replaces four tool categories.**

| You used to need | emdx |
|---|---|
| **Notes app** (Notion, Obsidian) | `emdx save`, `emdx find`, `emdx tag` |
| **Task tracker** (Linear, GitHub Issues) | `emdx task`, `emdx task dep`, `emdx task epic` |
| **RAG pipeline** (LangChain, custom scripts) | `emdx find --mode semantic`, `emdx find --ask` |
| **Agent orchestrator** (CrewAI, AutoGen) | `emdx delegate`, `emdx delegate --pr` |

The difference: these four tools share a single knowledge base. Save a research note → it becomes searchable context → an agent picks it up → its output creates a task → the task drives a PR. One data store, local SQLite, nothing vanishes.

## See it in action

```bash
# Notes app — save anything, find it instantly
$ emdx save "Token refresh fails when clock skew > 30s..." --title "Auth Bug"
✅ Saved as #42: Auth Bug
$ emdx tag 42 bugfix security
$ emdx find "auth"

# Agent orchestrator — parallel agents, results auto-saved
$ emdx delegate "audit auth" "review error handling" "check validation"
📋 Saved as #43, #44, #45

# RAG pipeline — semantic search and Q&A, zero config
$ emdx find "how does token refresh work?" --mode semantic
$ emdx find --ask "What vulnerabilities did the auth audit find?"

# Task tracker — epics, categories, dependencies
$ emdx task add "Fix token refresh race condition" --cat FIX
$ emdx task add "Add clock skew tolerance" --cat FEAT
$ emdx task dep add FEAT-2 FIX-1       # FEAT depends on FIX
$ emdx task ready                       # show what's unblocked

# The loop closes — chain agent output into a PR
$ emdx delegate --doc 43 --pr "fix the issues from this audit"
🔀 PR #87: fix the issues from this audit
```

Every session compounds on the last. `emdx prime` loads full context — ready tasks, recent research, in-progress work. No re-explaining, no starting from scratch.

## Install

```bash
uv tool install emdx    # or: pip install emdx
emdx --help
```

## Save

```bash
$ emdx save --file meeting-notes.md
✅ Saved as #12: meeting-notes

$ emdx save "quick note about the API" --title "API Note"
✅ Saved as #13: API Note

$ docker logs api --since 1h | emdx save --title "API errors"
✅ Saved as #14: API errors

$ emdx tag 13 analysis active
```

## Find

```bash
$ emdx find "auth"                                         # keyword (FTS5)
$ emdx find "how does rate limiting work?" --mode semantic  # conceptual
$ emdx find --ask "What did we decide about the redesign?" # RAG Q&A
$ emdx find --context "auth" | claude                      # pipe to Claude
$ emdx find --tags "security,active"                       # filter by tags
$ emdx find --recent 10                                    # recently accessed
```

## Delegate

```bash
# Single task — results print AND persist
$ emdx delegate "audit auth for vulnerabilities"
📋 Saved as #43: Delegate: audit auth...

# Parallel (up to 10)
$ emdx delegate "check auth" "review tests" "scan for XSS"

# Synthesize into one doc
$ emdx delegate --synthesize "analyze auth" "analyze api" "analyze db"

# Feed previous results in
$ emdx delegate --doc 43 "write an action plan from this audit"

# Code changes — isolated worktree, auto-PR
$ emdx delegate --pr "fix the auth bug"
🔀 PR #88: fix the auth bug
```

## Track

```bash
$ emdx task add "Fix token refresh" --cat FIX
$ emdx task add "Add rate limiting" --cat FEAT --epic 42
$ emdx task dep add 2 1                # task 2 depends on task 1
$ emdx task chain 1 2 3 4              # sequential pipeline: 1→2→3→4
$ emdx task ready                      # show unblocked tasks
$ emdx task active FIX-1               # prefixed IDs work everywhere
$ emdx task done FIX-1
$ emdx task epic list
```

## Explore and maintain

```bash
$ emdx explore                         # topic map of your KB
$ emdx explore --gaps                  # coverage gaps and stale areas
$ emdx briefing                        # activity in the last 24h
$ emdx briefing --save                 # AI-synthesized session summary
$ emdx maintain compact --dry-run      # find near-duplicate docs
$ emdx maintain link --all             # auto-link related documents
$ emdx maintain index                  # build semantic search index
```

## Session workflow

```bash
$ emdx prime              # start — full context from last session
$ emdx task ready          # what's unblocked
# ... do work ...
$ emdx briefing --save     # end — summarize what happened
```

## Quick reference

| I want to... | Command |
|---|---|
| Save a file | `emdx save --file doc.md` |
| Save a note | `emdx save "text" --title "Title"` |
| Find by keyword | `emdx find "query"` |
| Find by meaning | `emdx find "concept" --mode semantic` |
| Ask a question | `emdx find --ask "question"` |
| Pipe context to Claude | `emdx find --context "topic" \| claude` |
| Run an agent | `emdx delegate "task"` |
| Run agents in parallel | `emdx delegate "t1" "t2" "t3"` |
| Agent makes a PR | `emdx delegate --pr "fix the bug"` |
| Add a task | `emdx task add "title" --cat FEAT` |
| Task dependencies | `emdx task dep add 2 1` |
| See ready tasks | `emdx task ready` |
| What happened today | `emdx briefing` |
| Topic map | `emdx explore` |
| TUI browser | `emdx gui` |

## Documentation

- [CLI Reference](docs/cli-api.md) — Complete command documentation
- [Architecture](docs/architecture.md) — System design
- [Development Setup](docs/development-setup.md) — Contributing guide

## License

MIT License — see LICENSE file.
