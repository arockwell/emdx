# emdx Plugin Guide

Getting started with emdx as a Claude Code plugin.

## What is emdx?

emdx is a knowledge base that AI agents populate and humans curate. It gives Claude Code persistent memory across sessions — research findings, task tracking, and project knowledge survive after conversations end.

## Installation

Install the plugin from the emdx repository:

```bash
claude --plugin-dir /path/to/emdx
```

Or clone and install:

```bash
git clone https://github.com/arockwell/emdx.git
claude --plugin-dir ./emdx
```

You also need the `emdx` CLI installed:

```bash
pip install emdx
# or
pipx install emdx
```

Verify it works:

```bash
emdx status
```

## Available Skills

The plugin provides eight slash commands, all namespaced under `/emdx:`:

| Skill | Description |
|-------|-------------|
| `/emdx:bootstrap` | Populate a KB from scratch by analyzing your codebase — architecture, patterns, gotchas, runbooks |
| `/emdx:research` | Search the KB for existing knowledge before starting new work |
| `/emdx:investigate` | Deep-dive a topic — searches KB, reads source code, identifies gaps, saves analysis |
| `/emdx:save` | Save findings, analysis, or decisions to the KB |
| `/emdx:tasks` | Manage tasks — add, prioritize, track with epics and categories |
| `/emdx:work` | Work on a task end-to-end — pick up, research, implement, test, mark done |
| `/emdx:prioritize` | AI-assisted triage — rank ready tasks by epic progress, dependencies, and age |
| `/emdx:review` | Audit KB quality — find stale docs, contradictions, gaps, code drift |

## Basic Workflow

A typical session follows this flow:

### 1. Bootstrap (first time only)

When starting a fresh KB for a project:

```
/emdx:bootstrap
```

This analyzes your codebase and creates foundational documents covering architecture, components, patterns, and operational knowledge.

### 2. Research before working

Before starting a task, check what the KB already knows:

```
/emdx:research authentication
```

This runs keyword, semantic, and tag-based searches so you don't redo prior work.

### 3. Work on tasks

Pick up and complete a task:

```
/emdx:work FEAT-12
```

This walks through the full cycle: get context, create subtasks, implement, test, and mark done.

### 4. Save findings

Persist research or decisions for future sessions:

```
/emdx:save
```

### 5. Review KB health

Periodically check for stale docs, contradictions, and gaps:

```
/emdx:review
```

## Hooks

The plugin includes three session hooks that run automatically. These are configured in `.claude/settings.json` and fire on specific Claude Code lifecycle events.

### SessionStart hooks

**auto-backup.sh** — Creates a daily backup of your KB before work begins. Skips if today's backup already exists. Fast path: a single file glob, no Python import.

**prime.sh** — Injects KB context into Claude's conversation. Runs `emdx prime` to show ready tasks, in-progress work, and recent documents. If `EMDX_TASK_ID` is set, it also activates that task and injects a task brief. If `EMDX_DOC_ID` is set, it injects that document's content.

### SubagentStop hook

**save-output.sh** — Saves subagent output to the KB when a substantive agent completes. Only fires on SubagentStop (not Stop). Only saves output from substantive agent types: `explore`, `plan`, and `general-purpose` — other agent types (unknown, custom, etc.) are silently skipped. Also filters out short messages (< 200 chars) to avoid noise. Auto-detects PR URLs and adds a `has-pr` tag. If `EMDX_TASK_ID` is set, links the saved document to that task.

### Hook summary

| Hook | Event | What it does |
|------|-------|--------------|
| `auto-backup.sh` | SessionStart | Daily KB backup |
| `prime.sh` | SessionStart | Injects task context and ready work |
| `save-output.sh` | SubagentStop | Saves output from substantive agents (explore, plan, general-purpose) to KB |

## Environment Variables

| Variable | Purpose | Set by |
|----------|---------|--------|
| `EMDX_TASK_ID` | Task being worked on — hooks auto-activate it and link output docs | Parent agent or launch script |
| `EMDX_DOC_ID` | Document to inject as context on session start | Parent agent |
| `EMDX_DB` | Override the database path | Environment config |
| `EMDX_TEST_DB` | Test database (used by pytest fixtures) | Test harness |

## Common Patterns

### Research task

```bash
emdx task brief $EMDX_TASK_ID
emdx task active $EMDX_TASK_ID
# ... research ...
echo "$findings" | emdx save --title "Research: topic" \
  --tags "analysis" --task $EMDX_TASK_ID --done
```

### Implementation task

```bash
emdx task brief $EMDX_TASK_ID
emdx task plan $EMDX_TASK_ID "Read code" "Implement" "Test" "Lint"
emdx task active FEAT-36
# ... implement each step, marking done as you go ...
emdx task done $EMDX_TASK_ID
```

### Multi-session task

```bash
# Session 1: partial progress
emdx task active $EMDX_TASK_ID
emdx task log $EMDX_TASK_ID "Completed auth refactor, tests remain"

# Session 2: pick up where you left off
emdx task brief $EMDX_TASK_ID   # Shows previous work log
emdx task active $EMDX_TASK_ID
# ... finish remaining work ...
emdx task done $EMDX_TASK_ID
```

## Tips and Gotchas

- **`emdx find` does not support OR/AND/NOT** — terms are quoted internally. Run separate searches for multiple concepts.
- **The subcommand is `task add`**, not `task create`.
- **Tasks use `--epic` and `--cat`** for organization, not `--tags`. Tags are for documents.
- **Use `emdx task ready`** to see actionable work — it filters out blocked tasks automatically.
- **Never run `emdx gui`** in Claude Code — it launches an interactive TUI that will hang the session.
- **`--flags` must come before positional arguments** in CLI calls.
- **Saving from stdin** requires `--title`: `echo "text" | emdx save --title "Title"`
- **Don't use `emdx save "text"`** as a positional arg — it looks for a file. Use `echo "text" | emdx save --title "Title"` instead.

## Further Reading

- [CLI Reference](cli-api.md) — Complete command documentation
- [Agent Workflow](agent-workflow.md) — Detailed agent interaction patterns
- [Architecture](architecture.md) — How emdx works internally
