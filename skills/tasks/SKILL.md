---
name: tasks
description: Manage tasks in the emdx knowledge base — add, prioritize, and track work items with epics and categories.
disable-model-invocation: true
---

# Task Management

Manage emdx tasks: $ARGUMENTS

## Core Commands

**Add a task:**
```bash
emdx task add "Title" -D "Detailed description" --epic <id> --cat FEAT
```

**View ready tasks (unblocked):**
```bash
emdx task ready
```

**Update task status:**
```bash
emdx task active <id>    # Mark in-progress
emdx task done <id>      # Mark complete
```

**List epics and categories:**
```bash
emdx task epic list      # See active epics
emdx task cat list       # See available categories
```

## Categories

Use `--cat` to classify tasks:

| Category | Use For |
|---|---|
| `FEAT` | New features |
| `FIX` | Bug fixes |
| `ARCH` | Architecture/refactoring |
| `DOCS` | Documentation |
| `TEST` | Testing |
| `CHORE` | Maintenance |

## Epics

Group related tasks under an epic with `--epic <id>`. Use `emdx task epic list` to see active epics.

## Important

- The subcommand is `task add`, NOT `task create`
- Tasks use `--epic` and `--cat` for organization, NOT `--tags` (tags are for documents)
- Use `emdx task ready` to see what's actionable — it filters out blocked tasks
