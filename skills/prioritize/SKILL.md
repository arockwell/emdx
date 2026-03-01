---
name: prioritize
description: AI-assisted task triage — analyze all ready tasks and recommend priorities based on epic progress, dependencies, category, and age.
---

# Task Prioritization

Analyze all ready tasks and recommend a priority ordering.

## Steps

### 1. Gather context

Run these commands to understand the current state:

```bash
emdx task ready --json
emdx epic list
```

### 2. Fetch task details

For each ready task, get full details:

```bash
emdx task view <id>
```

Focus on: description, epic membership, category, dependencies, age, and any work log entries.

### 3. Analyze and rank

Consider these factors when ranking tasks:

| Factor | Why it matters |
|--------|---------------|
| **Epic progress** | Tasks in nearly-complete epics should be prioritized to close out the epic |
| **Blocked-by chains** | Tasks that unblock other tasks should be done first |
| **Category** | FIX > FEAT > ARCH > DOCS > CHORE (bugs before features) |
| **Age** | Older tasks may indicate forgotten work or growing tech debt |
| **Description clarity** | Well-defined tasks are easier to execute and should be prioritized |

### 4. Present recommendations

Show the user a ranked table like:

```
Priority  ID        Title                          Reasoning
────────  ────────  ─────────────────────────────  ──────────────────────
1 (P1)    FEAT-8    Implement auto-linking         Unblocks 3 downstream tasks
2 (P1)    TUI-10    Wire QA presenter              Nearly completes QA epic (7/8)
3 (P2)    FEAT-13   Add semantic search caching     Quick win, small scope
...
```

Priority scale:
- **P1** (value 1): Critical — do this now
- **P2** (value 2): High — do this soon
- **P3** (value 3): Normal — default priority (unchanged)
- **P4** (value 4): Low — nice to have
- **P5** (value 5): Backlog — defer indefinitely

### 5. Apply priorities

After the user confirms (or adjusts), apply priorities:

```bash
emdx task priority <id> <1-5>
```

Only set priorities that differ from the default (3). Skip tasks the user wants left at normal priority.

## Important

- Always show your reasoning before applying changes
- Let the user adjust the ranking before applying
- Only change priorities the user agrees with
- If the user provides additional context (e.g., "we're shipping feature X next week"), factor that into the ranking
