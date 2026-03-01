# Gameplan Lifecycle Review

Review active gameplans and update their status based on what's actually been done.

## Process

1. **Find active gameplans**:
   ```bash
   emdx find --tags "gameplan,active"
   ```

2. **For each active gameplan**, check if its work has been completed:
   - Read the gameplan content to understand what was planned
   - Check merged PRs: `gh pr list --state merged --limit 30 --json title,number,mergedAt`
   - Check git log for related commits
   - Check if related issues are closed

3. **Classify each gameplan**:
   - **Done** — All planned work has been merged → `emdx tag <id> done success && emdx tag remove <id> active`
   - **Partial** — Some work done, some remaining → keep `active`, note what's left
   - **Stale** — No progress and no longer relevant → `emdx tag remove <id> active`
   - **Blocked** — Can't proceed for a reason → `emdx tag <id> blocked && emdx tag remove <id> active`

4. **Find orphaned work** — Look for merged PRs that don't correspond to any gameplan. These may need retrospective gameplans or at minimum should be noted.

5. **Create tasks for remaining work**:
   ```bash
   emdx task add "Title" -D "From gameplan #XXXX: ..."
   ```

## Output

```
## Gameplan Status Report

### Completed (→ done)
- #XXXX: "Title" — completed via PR #NNN, #NNN

### Still Active
- #YYYY: "Title" — 2/4 items done, remaining: [list]

### Stale (→ remove active)
- #ZZZZ: "Title" — no progress since [date], superseded by [reason]

### New Tasks Created
- "Task title" from gameplan #XXXX
```
