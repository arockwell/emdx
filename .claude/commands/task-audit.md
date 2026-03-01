# Task Audit

Reconcile open tasks with merged PRs — find tasks that are already done but not marked complete.

## Steps

1. Get all open tasks:
   ```bash
   emdx task ready
   ```

2. For each task (or batch by keyword), search for merged PRs:
   ```bash
   gh pr list --state all --search "<task title keywords>" --limit 5
   ```

3. For DOC tasks, grep the actual docs to check if the content already exists:
   ```bash
   rg "keyword" docs/cli-api.md docs/architecture.md CLAUDE.md
   ```

4. Mark confirmed-done tasks:
   ```bash
   emdx task done <KEY-N>
   ```

5. Report: tasks closed, tasks still genuinely open.

## Important

- Delegate PRs auto-update task status via session-end.sh hook, but this can miss some
- DOC tasks are the most likely to be done-but-not-marked — docs get updated in feature PRs
- Check both PR titles AND PR diffs for task coverage
