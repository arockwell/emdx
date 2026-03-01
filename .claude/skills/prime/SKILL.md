---
name: prime
description: Start a session by loading current work context from emdx — ready tasks, in-progress work, and recent documents.
disable-model-invocation: true
---

# Prime Session

Load current work context from emdx.

## Run

```bash
emdx prime
```

This outputs:
- **Ready tasks** — unblocked tasks you can start working on
- **In-progress tasks** — work that's already underway
- **Recent documents** — recently accessed KB entries for context

## Follow Up

After priming, check for ready tasks:
```bash
emdx task ready
```

Then pick a task to work on:
```bash
emdx task active <id>    # Mark a task as in-progress
```

## What to Do With the Context

1. **Review ready tasks** — pick the highest-priority unblocked task
2. **Check in-progress tasks** — continue or unblock stalled work
3. **Scan recent docs** — orient around what was worked on recently
4. **Ask the user** what they'd like to focus on if multiple tasks are available

If the user provided specific instructions with $ARGUMENTS, use the primed context to inform that work rather than asking.
