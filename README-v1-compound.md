# emdx

[![Version](https://img.shields.io/badge/version-0.19.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**AI sessions forget. emdx compounds.**

Every Claude session starts from zero — your research, decisions, and context vanish when the window closes. emdx is a local knowledge base that makes AI sessions cumulative. Save findings, dispatch parallel agents, track tasks, and start the next session exactly where you left off.

## See it in action

Three sessions. Each one picks up where the last left off.

**Session 1 — Research and save**

```bash
# Claude investigates an auth bug and saves what it finds
$ emdx save "Token refresh fails when clock skew > 30s..." --title "Auth Bug Analysis"
✅ Saved as #42: Auth Bug Analysis

# Fire off parallel agents for deeper analysis
$ emdx delegate "audit auth for race conditions" \
                "review error handling patterns" \
                "check input validation coverage"
📋 Saved as #43, #44, #45
```

**Session 2 — Pick up context, delegate deeper**

```bash
# New session. Claude checks what exists.
$ emdx prime
📋 Ready tasks: 0  |  Recent: #45, #44, #43, #42

# Reads the audit results, creates tasks
$ emdx task add "Fix token refresh race condition" --cat FIX
$ emdx task add "Add clock skew tolerance" --cat FEAT
$ emdx task dep add 2 1   # FEAT depends on FIX

# Chains previous results into a PR
$ emdx delegate --doc 43 --pr "fix the token refresh race condition"
🔀 PR #87: fix the token refresh race condition
```

**Session 3 — Ship and summarize**

```bash
# Everything from sessions 1 and 2 is waiting
$ emdx prime
📋 Ready tasks: 1  |  In-progress: 0  |  Recent: PR #87 merged

$ emdx task done FIX-1
$ emdx task ready          # FEAT-2 is now unblocked
$ emdx briefing --save     # AI summary of what happened
```

Each session builds on the last. Research compounds. Context never dies.

## Install

```bash
uv tool install emdx    # or: pip install emdx
emdx --help
```

## Save

Files, notes, piped command output — anything you save becomes searchable.

```bash
$ emdx save --file meeting-notes.md
✅ Saved as #12: meeting-notes

$ emdx save "the auth bug is in token refresh" --title "Auth Bug"
✅ Saved as #13: Auth Bug

$ docker logs api --since 1h | emdx save --title "API errors"
✅ Saved as #14: API errors

$ emdx tag 13 bugfix security
$ emdx find "auth"
$ emdx find --tags "security"
```

## Find

Keyword search, semantic search, or ask a question directly.

```bash
$ emdx find "auth"                                    # keyword (FTS5)
$ emdx find "how does rate limiting work?" --mode semantic  # conceptual
$ emdx find --ask "What did we decide about the API redesign?"  # RAG Q&A
$ emdx find --context "auth" | claude                 # pipe context to Claude
$ emdx find --recent 10                               # recently accessed
```

## Delegate

Parallel agents that save results back to your knowledge base.

```bash
# Single task
$ emdx delegate "audit auth for vulnerabilities"
📋 Saved as #43: Delegate: audit auth...

# Parallel (up to 10)
$ emdx delegate "check auth" "review tests" "scan for XSS"

# Synthesize parallel results into one doc
$ emdx delegate --synthesize "analyze auth" "analyze api" "analyze db"
📋 Saved as #60: Synthesis: analyze auth, analyze api, analyze db

# Feed previous results into new tasks
$ emdx delegate --doc 60 "write an action plan based on this analysis"

# Code changes — isolated worktree, auto-PR
$ emdx delegate --pr "fix the auth bug"
🔀 PR #88: fix the auth bug

# Doc context + PR
$ emdx delegate --doc 43 --pr "implement fixes from this audit"
```

## Track

Tasks with categories, epics, and dependencies.

```bash
$ emdx task add "Fix token refresh" --cat FIX
$ emdx task add "Add rate limiting" --cat FEAT --epic 42
$ emdx task dep add 2 1                # task 2 depends on task 1
$ emdx task chain 1 2 3 4              # wire up: 1→2→3→4
$ emdx task ready                      # show unblocked tasks
$ emdx task active FIX-1               # prefixed IDs work everywhere
$ emdx task done FIX-1
```

## Explore and maintain

Your knowledge base gets smarter the more you use it.

```bash
$ emdx explore                         # topic map of your KB
$ emdx explore --gaps                  # coverage gaps and stale areas
$ emdx briefing                        # what happened in the last 24h
$ emdx briefing --save                 # AI summary, persisted to KB
$ emdx maintain compact --dry-run      # find near-duplicate docs
$ emdx maintain link --all             # auto-link related documents
$ emdx maintain index                  # build semantic search index
```

## Session workflow

```bash
$ emdx prime              # start here — full context from last session
$ emdx task ready          # what's unblocked
# ... do work ...
$ emdx briefing --save     # end here — summarize what happened
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
| See ready tasks | `emdx task ready` |
| Task dependencies | `emdx task dep add 2 1` |
| What happened today | `emdx briefing` |
| Topic map | `emdx explore` |
| TUI browser | `emdx gui` |

## Documentation

- [CLI Reference](docs/cli-api.md) — Complete command documentation
- [Architecture](docs/architecture.md) — System design
- [Development Setup](docs/development-setup.md) — Contributing guide

## License

MIT License — see LICENSE file.
