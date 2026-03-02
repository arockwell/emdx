# Swarm

Dispatch a batch of independent tasks to parallel agents using teams.

## When to Use

- Multiple ready tasks that don't conflict on files (e.g., batch of FIX tasks, batch of DOC tasks)
- Tasks are small enough for a single agent to complete independently
- You want maximum throughput

## Steps

1. Get the task list:
   ```bash
   emdx task ready
   ```

2. Get briefs for each task:
   ```bash
   emdx task brief <ID>
   ```

3. Group tasks by file ownership — tasks that touch the same files go to the same agent. Tasks on different files can run in parallel.

4. Create a team:
   ```
   TeamCreate: team_name="<descriptive-name>"
   ```

5. For each group, launch an agent with `isolation: "worktree"` and `mode: "bypassPermissions"`:
   - Include the full task description and exact steps
   - Tell the agent to run lint (`poetry run ruff check . --fix`) and tests
   - Tell the agent to mark tasks done: `poetry run emdx task done <ID>`
   - Use `run_in_background: true` so agents run in parallel

6. As agents report back:
   - Check if changes landed in the working tree (agents may share CWD — see gotcha below)
   - If worktree isolation worked, cherry-pick or copy changes into the main branch
   - If agents wrote to shared working tree, just review the diffs

7. After all agents finish:
   - Run full lint: `poetry run ruff check . --fix && poetry run ruff format .`
   - Run tests: `poetry run pytest tests/ -x -q`
   - Commit all changes together
   - Shut down agents and delete team

## Agent Prompt Template

```
You are a teammate on team "<team-name>".

## Task
<task ID and title>
<full description from emdx task brief>

## Steps
1. Read the relevant source files
2. Make the fix/change
3. Run: `poetry run ruff check . --fix && poetry run ruff check .`
4. Run: `poetry run pytest tests/ -x -q -k <relevant_test>`
5. When done: `poetry run emdx task done <ID> 2>/dev/null || true`

## Rules
- Line length limit: 100 chars
- Keep changes minimal — only fix what's described
```

## Gotcha: Worktree Isolation in Nested Worktrees

When the CWD is already a git worktree (e.g., `.worktrees/feature-xyz`), `isolation: "worktree"` may fail silently — agents fall back to writing directly to the shared working tree. This is fine as long as agents own non-overlapping files. If two agents need to edit the same file, put those tasks in the same agent group.

Clean up stale worktrees periodically: `git worktree list` and `git worktree remove --force <path>`.
