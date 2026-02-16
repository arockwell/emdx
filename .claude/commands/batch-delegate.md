# Batch Delegate

Dispatch multiple emdx delegate tasks in parallel and monitor their completion.

## Usage

$ARGUMENTS should be a comma-separated list of doc IDs containing gameplans/specs, or a description of what to delegate.

## Steps

### 1. Identify Tasks
If doc IDs provided, view each doc to extract the task title and scope.
If descriptions provided, use those directly.

### 2. Dispatch
For each task, run as a background Bash command:
```bash
poetry run emdx delegate --pr --doc <id> --tags "enhancement,active" "<task description>" 2>&1
```

IMPORTANT:
- Run each delegate as a **separate** background command — do NOT combine multiple `--doc` flags in one call
- Keep prompts concise (<200 words) — long prompts can cause the claude CLI to hang
- Do NOT use `--doc` if the document is very large; summarize key points in the prompt instead

### 3. Monitor
Check each background task periodically:
- Read the output file for completion
- Check `ps` for the claude process — verify it has TCP connections (healthy) vs 0 connections (stuck)
- If stuck >8 minutes with 0% CPU and no TCP connections, kill and re-dispatch

### 4. Report
As each delegate completes, report:
- PR URL and number
- What was implemented
- Any duplicates or mismatches (agent built wrong feature)

### 5. Cleanup
- Identify duplicate PRs and close them
- List all resulting PRs in a summary table

## Known Gotchas

- Delegates share a virtualenv — if one delegate's worktree gets cleaned up while the editable install points to it, `poetry run pytest` breaks for everyone. Fix with `poetry install`.
- The `--doc` flag injects the full document content into the CLI arguments. Very large docs can cause the claude CLI to hang.
- Agents sometimes go off-script when given synthesis docs containing multiple gameplans — use the specific gameplan doc, not the synthesis.
