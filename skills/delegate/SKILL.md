---
name: delegate
description: Batch-dispatch tasks via emdx delegate with automatic KB persistence. Use for parallel CLI execution when results should auto-save to the knowledge base.
disable-model-invocation: true
---

# Delegate (Batch Dispatch)

Run tasks via emdx delegate: $ARGUMENTS

## When to Use Delegate

Use `emdx delegate` when you want **automatic KB persistence** — results are saved to the
knowledge base without manual `emdx save`. This is useful for:
- Batch parallel research (2-10 concurrent tasks)
- Tasks where you want guaranteed output persistence
- CLI-driven dispatch (not interactive Claude Code sessions)

For interactive work, prefer using the Agent tool directly and saving results with
`emdx save` afterward.

## Core Usage

**Single task:**
```bash
emdx delegate "analyze the auth module"
```

**Parallel tasks (up to 10 concurrent):**
```bash
emdx delegate "check auth" "review tests" "scan for XSS"
```

**Parallel with combined summary:**
```bash
emdx delegate --synthesize "task1" "task2" "task3"
```

## Options

| Flag | Short | Purpose |
|---|---|---|
| `--doc` | `-d` | Pass a KB document as context |
| `--pr` | | Create a PR (implies `--worktree`) |
| `--branch` | | Push branch, no PR (implies `--worktree`) |
| `--draft` / `--no-draft` | | Draft PR toggle (default: `--no-draft`) |
| `--base-branch` | `-b` | Custom base branch |
| `--worktree` | `-w` | Run in a git worktree |
| `--synthesize` | `-s` | Combine parallel results into a summary |
| `--jobs` | `-j` | Max parallel tasks (default: auto) |
| `--tags` | `-t` | Tag saved results |
| `--title` | `-T` | Custom title for saved results |
| `--model` | `-m` | Override model |
| `--sonnet` | | Shortcut for `--model sonnet` |
| `--opus` | | Shortcut for `--model opus` |
| `--quiet` | `-q` | Quiet mode |
| `--epic` | `-e` | Assign to epic |
| `--cat` | `-c` | Assign category |
| `--cleanup` | | Remove stale worktrees |

## Flag Ordering

All `--flags` must come BEFORE positional arguments:
```bash
# Correct
emdx delegate --synthesize --tags "analysis" "task1" "task2"

# Wrong — flags after positional args
emdx delegate "task1" "task2" --synthesize
```

## Examples

```bash
# Research with synthesis
emdx delegate --synthesize "analyze auth patterns" "review error handling" "check test coverage"

# Code change with PR
emdx delegate --pr "fix the auth bug described in issue #123"

# With document context
emdx delegate --doc 42 "implement the plan described here"

# Use a faster model
emdx delegate --sonnet "quick analysis of the config module"

# Clean up stale worktrees
emdx delegate --cleanup
```
