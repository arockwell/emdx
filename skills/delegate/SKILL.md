---
name: delegate
description: Dispatch parallel work to sub-agents via emdx delegate. Use when you need to run research, analysis, or code tasks in parallel — results persist to the knowledge base.
disable-model-invocation: true
---

# Delegate Work

Dispatch the following via emdx delegate: $ARGUMENTS

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

| Flag | Purpose |
|---|---|
| `--doc <id>` | Pass a KB document as context |
| `--pr` | Create a PR (implies `--worktree`) |
| `--branch` | Push branch, no PR (implies `--worktree`) |
| `--draft` / `--no-draft` | Draft PR toggle |
| `-b <branch>` | Custom base branch |
| `--worktree` / `-w` | Run in a git worktree |
| `--synthesize` | Combine parallel results into a summary |
| `-j <n>` | Max parallel tasks (default: 5) |
| `--tags` | Tag saved results |
| `--title` | Custom title for saved results |
| `--model` | Override model |
| `-q` | Quiet mode |
| `--epic` / `-e` | Assign to epic |
| `--cat` / `-c` | Assign category |
| `--cleanup` | Remove stale worktrees |

## Flag Ordering

All `--flags` must come BEFORE positional arguments:
```bash
# Correct
emdx delegate --synthesize --tags "analysis" "task1" "task2"

# Wrong — flags after positional args
emdx delegate "task1" "task2" --synthesize
```

## When to Delegate vs Do Inline

**Delegate when:**
- You need parallel research (2-10 tasks)
- The task involves code changes that should become a PR
- Results should persist to the KB for future reference
- The work is independent and doesn't need your conversation context

**Do inline when:**
- Quick, single-step lookups (use Grep/Glob/Read directly)
- The task depends on your current conversation state
- You need to iterate interactively with the user

## Examples

```bash
# Research with synthesis
emdx delegate --synthesize "analyze auth patterns" "review error handling" "check test coverage"

# Code change with PR
emdx delegate --pr "fix the auth bug described in issue #123"

# With document context
emdx delegate --doc 42 "implement the plan described here"

# Push branch without PR
emdx delegate --branch -b develop "add feature X"

# Clean up stale worktrees
emdx delegate --cleanup
```
