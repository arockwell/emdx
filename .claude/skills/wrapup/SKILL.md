---
name: wrapup
description: End a session cleanly — save unfinished work, update task statuses, and create tasks for remaining work.
disable-model-invocation: true
---

# Wrap Up Session

Save session state and update tasks before ending.

## Steps

### 1. Update Task Statuses

Mark completed work:
```bash
emdx task done <id>      # Finished tasks
emdx task active <id>    # Still in progress (leave as active)
emdx task blocked <id>   # Blocked on something
```

### 2. Create Tasks for Remaining Work

For anything discovered but not finished:
```bash
emdx task add "Title" -D "Details about what remains" --epic <id> --cat FEAT
```

Use `--cat` for category: `FEAT`, `FIX`, `ARCH`, `DOCS`, `TEST`, `CHORE`
Use `--epic <id>` to group under a parent epic.

**Note:** The subcommand is `task add`, not `task create`.

### 3. Generate Session Summary

Use the briefing command to auto-generate a summary from recent activity:
```bash
emdx briefing --save                  # Summarize last 4 hours (default)
emdx briefing --save --hours 8        # Wider time window
```

The summary is auto-saved with `session-summary,active` tags.

### 4. Tag Completed Documents

Update tags on documents that changed status:
```bash
emdx tag add <id> done success     # Completed successfully
emdx tag remove <id> active        # No longer active
```

## Checklist

- [ ] All completed tasks marked `done`
- [ ] New tasks created for remaining work
- [ ] Session summary generated via `emdx briefing --save`
- [ ] Document tags updated
