# Plugin Skills Reference

emdx ships as a [Claude Code plugin](https://agentskills.io) with skills that extend Claude's capabilities for knowledge base management. Install with `--plugin-dir` or via the marketplace; skills are namespaced as `/emdx:<skill>`.

## Overview

| Skill | Description | Invocation |
|-------|-------------|------------|
| [bootstrap](#bootstrap) | Generate foundational KB documents from a codebase | `/emdx:bootstrap [focus]` |
| [investigate](#investigate) | Deep-dive analysis combining KB search + source code | `/emdx:investigate <topic>` |
| [prioritize](#prioritize) | AI-assisted task triage and priority ranking | `/emdx:prioritize` |
| [research](#research) | Search the KB for existing knowledge before starting work | `/emdx:research <topic>` |
| [review](#review) | Run quality checks and produce an improvement plan | `/emdx:review [focus]` |
| [save](#save) | Persist findings, analysis, or decisions to the KB | `/emdx:save [content]` |
| [tasks](#tasks) | Manage tasks — add, plan subtasks, get briefs, track status | `/emdx:tasks [action]` |
| [work](#work) | Work on a task end-to-end: research, implement, test, done | `/emdx:work [task_id]` |

## Skills

### bootstrap

Generate foundational KB documents by analyzing the current codebase. Creates structured knowledge covering architecture, components, patterns, gotchas, and operational runbooks.

**Use when:** Starting a new KB for a project, or rebuilding after data loss.

**Arguments:** Optional focus area — `"architecture"`, `"patterns"`, or `"all"` (default).

**Phases:**
1. **Discovery** — reads project docs, dependencies, git history
2. **Document generation** — creates docs in 5 categories: architecture, components, patterns, gotchas, runbooks
3. **Cross-linking** — runs `emdx maintain wikify --all` to connect documents
4. **Summary** — reports what was generated and identifies gaps

```bash
/emdx:bootstrap                  # Full codebase bootstrap
/emdx:bootstrap architecture     # Focus on architecture docs only
```

---

### investigate

Deep-dive investigation that searches the KB, reads source code, identifies knowledge gaps, and produces a comprehensive analysis document saved to the KB with follow-up tasks.

**Use when:** You need to thoroughly understand a topic before making decisions or changes.

**Arguments:** The topic to investigate (required).

**Phases:**
1. **Search KB** — keyword, semantic, tag-based, and recent document searches
2. **Read source code** — traces data flows, reads tests, checks git history
3. **Identify gaps** — compares KB knowledge against codebase reality
4. **Synthesize** — writes a structured analysis (prior knowledge, codebase analysis, gaps, recommendations)
5. **Save** — persists analysis to KB with `analysis,active` tags
6. **Create tasks** — files follow-up tasks for actionable recommendations

```bash
/emdx:investigate authentication
/emdx:investigate "database migration system"
```

---

### prioritize

Analyzes all ready tasks and recommends a priority ordering based on epic progress, dependency chains, category, and age.

**Use when:** You have many open tasks and need to decide what to work on next.

**Arguments:** None.

**Priority scale:**
- P1 — Critical, do now
- P2 — High, do soon
- P3 — Normal (default)
- P4 — Low, nice to have
- P5 — Backlog, defer

```bash
/emdx:prioritize
```

The skill presents a ranked table with reasoning, then applies priorities after user confirmation via `emdx task priority <id> <1-5>`.

---

### research

Searches the KB for existing knowledge about a topic. A lightweight, non-destructive skill that helps avoid redoing work.

**Use when:** Starting a task, investigating a topic, or looking for prior art.

**Arguments:** The topic or query to search for.

**Search strategy:**
1. Broad keyword search: `emdx find "<topic>" -s`
2. Narrow with tags: `emdx find --tags "analysis,active"`
3. Semantic search: `emdx find "<concept>" --mode semantic`
4. Recent docs: `emdx find --recent`

```bash
/emdx:research authentication
/emdx:research "error handling patterns"
```

---

### review

Runs all KB quality checks and produces a prioritized, actionable improvement plan.

**Use when:** Doing periodic KB maintenance, or when the KB feels stale or disorganized.

**Arguments:** Optional focus area to prioritize findings.

**Checks performed:**
- `emdx maintain freshness --stale` — stale documents
- `emdx maintain compact --dry-run` — redundancies
- `emdx maintain contradictions` — conflicting claims
- `emdx maintain drift` — stale work items
- `emdx maintain code-drift` — outdated code references
- `emdx maintain gaps` — thin coverage areas
- `emdx stale --tier critical` — critical staleness
- `emdx status --vitals` — overall health

```bash
/emdx:review                     # Full quality review
/emdx:review "architecture docs" # Focus on architecture
```

The report groups fixes by risk level (safe/moderate/destructive) and applies only user-approved actions.

---

### save

Persists content to the KB. A lightweight skill that provides the right syntax for different save patterns.

**Use when:** You have research results, investigation notes, or decisions worth keeping across sessions.

**Arguments:** Content to save or description of what to save.

**Save patterns:**
```bash
# Inline content
emdx save "Quick note" --title "Title" --tags "notes"

# From a file
emdx save --file document.md

# From stdin (most common for agent use)
echo "content" | emdx save --title "Title" --tags "analysis,active"
```

**Useful options:** `--auto-link`, `--task <id>`, `--done`, `--gist`, `--supersede`

**Tag conventions:**

| Content Type | Tags |
|---|---|
| Plans/strategy | `gameplan, active` |
| Investigation | `analysis` |
| Bug fixes | `bugfix` |
| Notes | `notes` |

---

### tasks

Manages tasks in the KB — adding, planning subtasks, getting agent-ready briefs, and tracking status.

**Use when:** Creating, updating, or querying tasks.

**Arguments:** The task action to perform.

**Core commands:**
```bash
# Add a task
emdx task add "Title" -D "Details" --epic <id> --cat FEAT

# Batch-create sequential subtasks under a parent
emdx task plan FEAT-25 "Read code" "Implement" "Test"
emdx task plan FEAT-25 --cat FEAT "Read code" "Implement"

# Get a comprehensive task brief (for agents starting work)
emdx task brief FEAT-25
emdx task brief 42 --json
emdx task brief FEAT-25 --agent-prompt

# View and manage
emdx task ready                     # Unblocked tasks
emdx task view <id>                 # Task details
emdx task active <id>               # Mark in-progress
emdx task done <id>                 # Mark complete
emdx task done <id> --output-doc 42 # Complete and link output
```

**Categories:** `FEAT`, `FIX`, `ARCH`, `DOCS`, `TEST`, `CHORE`

**Epics:** Group tasks with `--epic <id>`. Manage with `emdx task epic list|create|view|done|delete`.

---

### work

Works on a task end-to-end: picks up a ready task, researches, creates subtasks, implements, tests, and marks done.

**Use when:** You want Claude to autonomously complete a task from start to finish.

**Arguments:** Optional task ID (e.g., `FEAT-30`, `42`). If omitted, picks the next ready task.

**Workflow:**
1. Identify task (from argument or `emdx task ready`)
2. Get details and mark active
3. Research — check KB and read relevant code
4. Create subtasks for visibility
5. Implement — write code, follow quality rules
6. Test — `pytest`, `ruff check`
7. Save findings to KB
8. Mark complete and create follow-up tasks

```bash
/emdx:work FEAT-30               # Work on a specific task
/emdx:work                       # Pick the next ready task
```
