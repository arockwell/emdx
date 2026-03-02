# Agent Workflow Guide

How AI agents (Claude Code subagents) interact with emdx for task management
and knowledge capture.

## Quick Start

When starting work as an agent:

```bash
# 1. Get your task context
emdx task brief $EMDX_TASK_ID        # Plain text
emdx task brief $EMDX_TASK_ID --json  # Structured

# 2. Break work into subtasks
emdx task plan $EMDX_TASK_ID "Read code" "Implement" "Test" "Lint"

# 3. Work through subtasks
emdx task active FEAT-36    # Start first subtask
# ... do the work ...
emdx task done FEAT-36      # Complete it

# 4. Save findings to KB
echo "analysis..." | emdx save --title "Auth analysis" --tags "analysis,active"

# 5. Complete parent task
emdx task done $EMDX_TASK_ID
```

## Environment Variables

| Variable | Purpose | Set by |
|----------|---------|--------|
| `EMDX_TASK_ID` | Task being worked on | Parent agent or launch script |
| `EMDX_DOC_ID` | Document being analyzed | Parent agent |
| `EMDX_DB` | Database path override | Environment config |

## Task Lifecycle

### Getting Context

`emdx task brief` assembles everything an agent needs: task description,
dependencies, subtasks, work log from previous sessions, related KB
documents, and key file paths extracted from description/logs.

### Creating Subtasks

`emdx task plan` creates sequential subtasks in a single call:

```bash
emdx task plan FEAT-25 "Read code" "Implement" "Test"
# Creates FEAT-36 -> FEAT-37 -> FEAT-38 (chained dependencies)
```

Each subtask depends on the previous one. This means:
- Only the first subtask appears in `task ready`
- Completing one unblocks the next
- Progress is visible to the parent agent

### Tracking Progress

```bash
emdx task active FEAT-36          # Mark as in-progress
emdx task log FEAT-36 "Found the bug in auth.py:42"  # Add work log
emdx task done FEAT-36            # Complete, unblocks FEAT-37
```

View a task's full log with `emdx task log FEAT-36` (no message arg).

### Saving Knowledge

```bash
# Save findings from text
echo "Root cause: missing null check" | \
  emdx save --title "Auth bug analysis" --tags "analysis,bugfix"

# Save from file
emdx save --file analysis.md --tags "analysis"

# Link output to a task and mark it done in one step
echo "findings" | emdx save --title "Task output" --task 42 --done
```

The `--task` flag links the saved document to a task. Adding `--done`
also marks that task as complete.

### Completing Work

```bash
emdx task done $EMDX_TASK_ID                        # Simple
emdx task done $EMDX_TASK_ID --note "Fixed in #123" # With note
```

## Hook Integration

### Session Hooks

| Hook | Event | Behavior |
|------|-------|----------|
| `prime.sh` | SessionStart | Injects task context via `emdx prime` |
| `save-output.sh` | Stop, SubagentStop | Saves agent output to KB with task linkage |
| `auto-backup.sh` | SessionStart | Creates daily KB backup |

### How prime.sh Uses EMDX_TASK_ID

When `EMDX_TASK_ID` is set, `prime.sh` automatically:
1. Runs `emdx prime` to inject ready tasks and epics
2. Activates the specified task via `emdx task active`

When `EMDX_DOC_ID` is set, it also injects that document's content
as additional context.

## Best Practices

1. **Always get a brief first** -- one call gives you full context
2. **Create subtasks for 3+ step work** -- makes progress visible
3. **Save findings, not just code** -- analysis docs help future sessions
4. **Use task log for status updates** -- audit trail across sessions
5. **Link output docs** -- `--task` on `emdx save` connects knowledge
   to work

## Common Patterns

### Research Task

```bash
emdx task brief $EMDX_TASK_ID
emdx task active $EMDX_TASK_ID
# ... research ...
echo "$findings" | emdx save --title "Research: topic" \
  --tags "analysis" --task $EMDX_TASK_ID --done
```

### Implementation Task

```bash
emdx task brief $EMDX_TASK_ID
emdx task plan $EMDX_TASK_ID "Read code" "Implement" "Test" "Lint"
emdx task active FEAT-36
# ... implement each step, marking done as you go ...
emdx task done $EMDX_TASK_ID
```

### Multi-Session Task

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
