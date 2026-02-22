# emdx

[![Version](https://img.shields.io/badge/version-0.19.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**Claude sessions are stateless. Your work shouldn't be.**

You spend an hour with Claude mapping a gnarly auth bug — call chains, root causes, three related issues. Session ends. Tomorrow you open a new chat. "Can you look at the auth module?" It reads the same files. Asks the same questions. Your hour is gone.

emdx fixes this. Save findings, fire off parallel agents, track what's left. Everything lives in local SQLite. Next session, run `emdx prime` — Claude sees yesterday's work and picks up where it left off. Half the PRs in this repo were opened by emdx agents.

```bash
# Save research — it persists across sessions
$ emdx save "Token refresh fails when clock skew > 30s..." --title "Auth Bug Analysis"
✅ Saved as #42: Auth Bug Analysis

# Fire off 3 agents in parallel — results auto-save to the KB
$ emdx delegate "audit auth for vulnerabilities" \
                "review error handling patterns" \
                "check input validation coverage"
📋 Saved as #43, #44, #45

# Track what needs doing
$ emdx task add "Fix token refresh race condition" --cat FIX
$ emdx task add "Add clock skew tolerance" --cat FEAT
$ emdx task dep add FEAT-2 FIX-1

# Next session: everything is waiting
$ emdx prime
📋 Ready tasks: 2  |  Recent: #45, #44, #43, #42

# Chain agent output into a PR
$ emdx delegate --doc 43 --pr "fix the token refresh race condition"
🔀 PR #87: fix the token refresh race condition

# End of day: AI-generated summary of what happened
$ emdx briefing --save
```

Every session compounds. Context never dies.

## Install

```bash
uv tool install emdx    # or: pip install emdx
emdx --help
```

## What it replaces

| Tool category | emdx equivalent |
|---|---|
| **Notes** (Notion, Obsidian) | `save`, `find`, `tag` |
| **Tasks** (Linear, GitHub Issues) | `task add`, `task ready`, `task dep`, `task epic` |
| **RAG** (LangChain, custom) | `find --mode semantic`, `find --ask` |
| **Agent orchestrator** (CrewAI, AutoGen) | `delegate`, `delegate --pr` |

One knowledge base. Data flows between all four without import/export.

## Save

```bash
$ emdx save --file meeting-notes.md
$ emdx save "quick note" --title "Note"
$ docker logs api --since 1h | emdx save --title "API errors"
$ emdx tag 12 analysis active
```

## Find

```bash
$ emdx find "auth"                                         # keyword
$ emdx find "how does rate limiting work?" --mode semantic  # conceptual
$ emdx find --ask "What did we decide about the redesign?" # RAG Q&A
$ emdx find --context "auth" | claude                      # pipe to Claude
$ emdx find --tags "security"                              # by tag
$ emdx find --recent 10                                    # recently accessed
```

## Delegate

```bash
$ emdx delegate "audit auth for vulnerabilities"           # single task
$ emdx delegate "t1" "t2" "t3"                             # parallel (up to 10)
$ emdx delegate --synthesize "analyze auth" "analyze api"  # combined summary
$ emdx delegate --doc 43 "action plan from this audit"     # feed previous results
$ emdx delegate --pr "fix the auth bug"                    # isolated worktree → PR
$ emdx delegate --doc 43 --pr "implement this audit"       # doc context + PR
```

## Track

```bash
$ emdx task add "Fix token refresh" --cat FIX
$ emdx task add "Add rate limiting" --cat FEAT --epic 42
$ emdx task dep add 2 1                # task 2 depends on task 1
$ emdx task chain 1 2 3 4              # sequential: 1→2→3→4
$ emdx task ready                      # what's unblocked
$ emdx task done FIX-1                 # prefixed IDs work everywhere
```

## Explore

```bash
$ emdx explore                         # topic map of your KB
$ emdx explore --gaps                  # coverage gaps and stale areas
$ emdx briefing                        # what happened in the last 24h
$ emdx briefing --save                 # AI summary, persisted to KB
$ emdx maintain compact --dry-run      # find near-duplicate docs
$ emdx maintain link --all             # auto-link related documents
```

## The loop

```bash
$ emdx prime              # start — context from last session
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
| Parallel agents | `emdx delegate "t1" "t2" "t3"` |
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
