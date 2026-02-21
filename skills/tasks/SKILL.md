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
emdx task add "Implement this plan" --doc 42     # Link to a document
```

**View ready tasks (unblocked):**
```bash
emdx task ready
```

**View task details:**
```bash
emdx task view <id>
```

**Update task status:**
```bash
emdx task active <id>     # Mark in-progress
emdx task done <id>       # Mark complete
emdx task blocked <id>    # Mark blocked
```

**Work log and notes:**
```bash
emdx task log <id>                        # View task log
emdx task log <id> "Started implementation"  # Add log entry
emdx task note <id> "Progress update"     # Add note without status change
```

**Delete a task:**
```bash
emdx task delete <id>
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

**Manage categories:**
```bash
emdx task cat list                            # List categories
emdx task cat create SEC --description "Security tasks"  # Create
emdx task cat adopt SEC                       # Backfill existing tasks
emdx task cat delete SEC                      # Delete (unlinks tasks)
```

## Epics

Group related tasks under an epic with `--epic <id>`.

**Manage epics:**
```bash
emdx task epic list                           # List epics
emdx task epic create "Auth System Overhaul"  # Create
emdx task epic view <id>                      # View with tasks
emdx task epic active <id>                    # Mark in-progress
emdx task epic done <id>                      # Mark complete
emdx task epic delete <id>                    # Delete (unlinks tasks)
```

## Task Statuses

| Status | Icon | Description |
|---|---|---|
| `open` | ○ | Not yet started |
| `active` | ● | Currently being worked on |
| `blocked` | ⚠ | Waiting on dependencies |
| `done` | ✓ | Completed |

## Important

- The subcommand is `task add`, NOT `task create`
- Tasks use `--epic` and `--cat` for organization, NOT `--tags` (tags are for documents)
- Use `emdx task ready` to see what's actionable — it filters out blocked tasks
