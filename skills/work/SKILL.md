---
name: work
description: Work on an emdx task end-to-end — pick up a ready task, research, create subtasks, implement, test, and mark done. Accepts a task ID or picks the next ready task.
---

# Work on Task

Work on task: $ARGUMENTS

## Workflow

### 1. Identify the Task

If a task ID was provided (e.g. `FIX-12`, `FEAT-30`, or a numeric ID), use it directly. Otherwise pick the next ready task:
```bash
emdx task ready
```

### 2. Get Task Details and Mark Active

```bash
emdx task view <id>
emdx task active <id>
```

### 3. Research

Before writing any code, understand the problem:

1. **Check KB for prior work:** `emdx find "<topic>" -s` and `emdx find --tags "analysis"` for related analysis
2. **Read the relevant code** — use Grep/Glob/Read tools to understand the current state
3. **Identify root cause** (for FIX) or **design approach** (for FEAT/ARCH)

### 4. Create Subtasks

Break the work into 3+ trackable steps BEFORE starting implementation:
```bash
emdx task add "Research and understand the code" --epic <parent_id> --cat <CAT>
emdx task add "Implement the changes" --epic <parent_id> --cat <CAT>
emdx task add "Run tests and fix issues" --epic <parent_id> --cat <CAT>
```

Use the parent task's category (`FIX`, `FEAT`, `ARCH`, `DOCS`, `TEST`, `CHORE`).
Mark each subtask done as you complete it: `emdx task done <id>`

### 5. Implement

- Use parallel subagents (Agent tool) for independent work streams when possible
- Follow all code quality rules: ruff lint, 100-char line limit, type safety
- Keep changes focused — don't over-engineer

### 6. Test

```bash
# Run relevant tests
poetry run pytest tests/<relevant_test_file>.py -x -q

# Lint
poetry run ruff check . --fix
poetry run ruff check .
```

If tests fail, fix the issues and re-run.

### 7. Save Findings

Save significant analysis or decisions to the KB:
```bash
echo "findings" | emdx save --title "Title" --tags "analysis,active"
```

### 8. Mark Complete

```bash
emdx task done <id>       # Mark subtasks done
emdx task done <parent>   # Mark parent task done
```

Create follow-up tasks for any discovered work:
```bash
emdx task add "Follow-up title" -D "Details" --cat FEAT
```

## Important

- **Always research before implementing** — read the code, check the KB
- **Always create subtasks** for visibility into progress
- **Always run tests** before declaring done
- **Never skip linting** — `ruff check` must pass with zero errors
- The subcommand is `task add`, NOT `task create`
- Tasks use `--epic` and `--cat`, NOT `--tags`
