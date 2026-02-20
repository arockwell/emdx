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
```

### 2. Create Tasks for Remaining Work

For anything discovered but not finished:
```bash
emdx task add "Title" -D "Details about what remains" --epic <id> --cat FEAT
```

Use `--cat` for category: `FEAT`, `FIX`, `ARCH`, `DOCS`, `TEST`, `CHORE`
Use `--epic <id>` to group under a parent epic.

**Note:** The subcommand is `task add`, not `task create`.

### 3. Save Session Summary

Persist a summary of what was accomplished:
```bash
echo "## Session Summary

### Completed
- Implemented X
- Fixed Y

### In Progress
- Working on Z (task #123)

### Remaining
- Need to do W (created task #456)" | emdx save --title "Session Summary - $(date +%Y-%m-%d)" --tags "notes,active"
```

### 4. Tag Completed Documents

Update tags on documents that changed status:
```bash
emdx tag add <id> done success     # Completed successfully
emdx tag remove <id> active        # No longer active
```

## Checklist

- [ ] All completed tasks marked `done`
- [ ] New tasks created for remaining work
- [ ] Session summary saved to KB
- [ ] Document tags updated
