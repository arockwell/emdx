# Beads-Inspired Feature Proposals for emdx

Five concrete ideas inspired by Beads, evaluated against what emdx already has.

---

## 1. Formalize "Land the Plane" as `emdx land`

### What Beads Does

When an agent says "land the plane," Beads runs a scripted cleanup: sync all issues, close completed tasks, update statuses, and generate a handoff prompt for the next session. It's atomic — one command, full session hygiene.

### What emdx Has Today

- **wrapup skill** (`skills/wrapup/SKILL.md`) — a 4-step checklist the agent follows manually: update task statuses, create tasks for remaining work, run `emdx briefing --save`, update doc tags
- **session-end hook** (`.claude/hooks/session-end.sh`) — only fires if `EMDX_TASK_ID` is set; marks that one task done
- **briefing --save** — generates an AI summary of recent activity and saves it to KB

The gap: wrapup is instructions, not automation. The agent has to interpret the checklist and run 4-8 separate commands. There's no handoff prompt generation, and no single command that does everything.

### Proposal: `emdx land`

A single CLI command that performs full session closure:

```
emdx land                    # Interactive: prompt for each step
emdx land --auto             # Non-interactive: best-effort automation
emdx land --handoff          # Generate a handoff prompt for next session
emdx land --dry-run          # Show what would happen
```

**Steps it performs (in order):**

1. **Detect in-progress tasks** — query `status = 'active'`, prompt: mark done, leave active, or block?
   - `--auto` mode: leave as active (conservative)
2. **Scan for orphaned work** — check git diff for uncommitted changes, check for open PR branches. Warn if work isn't committed.
3. **Generate session briefing** — equivalent to `briefing --save` but with a tighter window (default: 2 hours, not 4)
4. **Generate handoff prompt** — the key new feature. Produces a markdown block designed to be injected into the next session:

```markdown
## Session Handoff (2026-03-02 14:30)

### Completed This Session
- FEAT-12: Add semantic search to wiki (done)
- FEAT-13: Update CLI help text (done)

### Still In Progress
- DEBT-7: Refactor prime output (active, ~60% done)
  - Remaining: wire up --smart flag for JSON output

### Blockers
- FIX-3: TUI crash on large documents (blocked on upstream Textual fix)

### Suggested Next Steps
1. Continue DEBT-7 — finish JSON smart output
2. Review PR #142 (open, relates to FEAT-12)

### Key Context
- Branch: feature/smart-prime
- Recent docs: #287 "Prime refactoring notes", #285 "TUI performance analysis"
```

5. **Save handoff doc** — persist the handoff to KB with tags `handoff, active`
6. **Update prime hook** — the next `emdx prime` call automatically includes the most recent handoff doc if it exists and is < 24h old

**Implementation scope:** ~200-300 lines. Mostly orchestration of existing queries (`_get_in_progress_tasks`, `_get_ready_tasks`, git context) plus a new LLM synthesis call for the handoff prompt. The handoff template can be deterministic (no LLM needed) for `--auto` mode.

**What this learns from Beads:** The key insight is that session-end is when context is richest, but emdx does its heavy lifting at session-start (prime). Landing the plane captures that rich context and stores it for the next session.

---

## 2. Completed Work Compaction

### What Beads Does

"Semantic memory decay" — old closed tasks get automatically summarized to save context window space. The full task history is still available, but the default view shows condensed summaries instead of raw details.

### What emdx Has Today

- **`compact`** — merges *documents* via TF-IDF clustering + AI synthesis. Works on docs, not tasks.
- **`briefing --save`** — summarizes recent activity into a single doc. But this is a point-in-time snapshot, not ongoing compaction.
- **Tasks stay forever** — all completed tasks remain as full records. `prime` simply caps output at 15 ready + 5 in-progress, so old done tasks don't clutter the view. But they do clutter `task list --done`.

The gap: there's no mechanism to compress old completed work into summaries. If you have 200 completed tasks across 6 months, there's no "what did we accomplish in January?" view without scrolling through all of them.

### Proposal: `emdx task digest`

Periodic summarization of completed tasks into digest documents.

```
emdx task digest                     # Summarize tasks completed in last 30 days
emdx task digest --period weekly     # Group by week
emdx task digest --period monthly    # Group by month
emdx task digest --epic FEAT         # Just one epic's completed work
emdx task digest --since 2026-01-01  # Custom window
emdx task digest --dry-run           # Preview without saving
```

**What it produces:**

A KB document per period, like:

```markdown
# Task Digest: February 2026

## FEAT (Features) — 12 completed
- Semantic search integration (FEAT-8 through FEAT-14)
  - Added embedding index, hybrid search mode, --similar flag
  - Key doc: #245 "Semantic Search Architecture"
- Wiki export (FEAT-15, FEAT-16)
  - MkDocs export with --topic filtering

## FIX (Bug Fixes) — 8 completed
- TUI mouse handling regression (FIX-3, FIX-4)
- FTS5 query escaping edge cases (FIX-7)

## DEBT (Tech Debt) — 3 completed
- Migrated from sequential to set-based migration IDs
```

**Implementation details:**

- Query: `SELECT * FROM tasks WHERE status IN ('done', 'wontdo') AND completed_at >= ? ORDER BY epic_key, completed_at`
- Group by epic_key, then by time period
- For each group, pull associated `source_doc_id` and `output_doc_id` to link to relevant KB docs
- Synthesis: LLM call to produce narrative summary from task titles + descriptions (optional, can be deterministic)
- Save as document with tags: `task-digest, {period}`
- Optionally mark digested tasks with a `digested_at` timestamp (new column) so they can be hidden from default `task list --done` output

**What this learns from Beads:** The insight is that completed task *details* are low-value for current work, but completed task *summaries* are high-value for understanding trajectory. Compress, don't delete.

---

## 3. Aggressive Prime Scoping

### What Beads Does

Yegge's philosophy: "Vague future work burns tokens without aiding execution." Beads only surfaces tasks relevant to *right now* — ready tasks with no blockers. Future work, someday-maybes, and vague plans are hidden by default.

### What emdx Has Today

`emdx prime` already does this reasonably well:
- Ready tasks (open + no blockers): 15 max
- In-progress: 5 max
- Epics: all active ones with progress bars
- Git context: branch + 3 commits + open PRs
- Smart mode adds: recent docs, key docs, tag map, stale docs

But there's room to be more ruthless. Prime currently shows *all* active epics regardless of relevance. If you have 8 active epics and you're working on a branch that clearly relates to one of them, the other 7 are noise.

### Proposal: Context-aware prime filtering

Enhance `emdx prime --smart` (or add `emdx prime --focus`):

**A. Branch-based epic detection:**
```
Branch: feature/wiki-export
→ Detect "wiki" keyword
→ Boost WIKI epic tasks, demote unrelated epics
→ Output: "FOCUS: WIKI epic (3 ready tasks)" + "Other epics: FEAT(2), DEBT(1), FIX(0)"
```

**B. Recency-weighted task ordering:**
Currently, ready tasks are ordered by `priority ASC, created_at ASC`. Add a recency signal:
- Tasks whose `source_doc_id` was accessed in the last 24h get boosted
- Tasks in the same epic as the most recently completed task get boosted
- Tasks related to the current git branch's epic get boosted

**C. Stale task suppression:**
Ready tasks older than 90 days with no activity (no log entries, no dependency changes) get demoted to a "Backlog" section instead of appearing in the main ready list. This prevents the ready queue from becoming a graveyard.

**D. Token budget mode:**
Add `emdx prime --budget 2000` that estimates output tokens and truncates to fit. Useful for constrained contexts (e.g., MCP servers with limited context injection).

**Implementation scope:**
- Branch detection: ~30 lines (parse branch name, match against epic keys)
- Recency boost: modify `_get_ready_tasks()` SQL to include a scoring column
- Stale suppression: add `HAVING` clause or post-filter based on `updated_at`
- Token budget: character counting with truncation (rough estimate: 1 token ≈ 4 chars)

**What this learns from Beads:** Ruthless relevance filtering. The agent doesn't need your complete backlog — it needs the 3-5 things it should consider doing *right now*, in *this* context.

---

## 4. Per-Repo Mode (`emdx init`)

### What Beads Does

Beads lives in `.beads/` inside the repo. It travels with the code. Multiple contributors can use the same Beads database. It's part of the project, not a personal tool.

### What emdx Has Today

- Central DB at `~/.config/emdx/knowledge.db` (production)
- Dev DB at `.emdx/dev.db` (only for emdx's own development)
- `EMDX_DB` env var for explicit override
- `project` column on documents for filtering within the central DB
- No `emdx init` command

The gap: emdx is strictly personal. You can't share KB context with teammates or have project-specific knowledge that travels with the repo.

### Proposal: `emdx init` for project-scoped databases

```
emdx init                          # Create .emdx/ in current repo
emdx init --gitignore              # Also add .emdx/ to .gitignore (personal mode)
emdx init --shared                 # Don't gitignore (team mode, committed to repo)
```

**How it works:**

1. `emdx init` creates `.emdx/project.db` + `.emdx/config.toml` in the repo root
2. **Path resolution change** — insert a new step between EMDX_DB and dev-checkout detection:
   ```
   1. EMDX_TEST_DB
   2. EMDX_DB
   3. NEW: Walk up from cwd looking for .emdx/config.toml → use .emdx/project.db
   4. Dev checkout detection → .emdx/dev.db
   5. Production default → ~/.config/emdx/knowledge.db
   ```
3. **Config file** (`.emdx/config.toml`):
   ```toml
   [project]
   name = "myproject"

   [database]
   # path is relative to .emdx/ directory
   path = "project.db"
   ```

**Two modes:**

| Mode | `.gitignore` | Use case |
|------|-------------|----------|
| **Personal** (default) | `.emdx/` is gitignored | Your private notes/tasks for this project |
| **Shared** | `.emdx/` is committed | Team KB — onboarding docs, architecture decisions, shared tasks |

**What stays in central DB:** Cross-project knowledge, personal preferences, documents not scoped to any repo. The central DB remains the default when you're not in a repo with `.emdx/`.

**Migration between modes:**
```
emdx db export --project myproject --out .emdx/project.db   # Copy project docs to repo DB
emdx db import .emdx/project.db                              # Merge repo DB into central
```

**Implementation scope:** This is the largest proposal. Rough estimate:
- Config file parsing: ~50 lines (toml parsing, path resolution)
- Path resolution change: ~20 lines in `get_db_path()`
- `init` command: ~80 lines
- Export/import: ~150 lines (query + insert with ID remapping)
- Tests: ~100 lines

**What this learns from Beads:** Knowledge should live where the code lives, at least optionally. The personal-vs-shared distinction is important — Beads only does shared, but emdx should support both because not all KB content is appropriate to commit.

**Caveat:** This is the proposal I'd be most cautious about. It adds meaningful complexity (two DB modes, path resolution edge cases, migration between them). It's worth doing *only* if you actually have a use case — a team project, or a desire to share architecture docs via git. Don't build it speculatively.

---

## 5. Handoff Prompt Generation

### What Beads Does

At session end, Beads generates a ready-to-paste prompt that briefs the next agent. This isn't just a summary — it's formatted as instructions the next agent can act on immediately.

### What emdx Has Today

- `prime` at session start gathers context, but it's broad (all ready tasks, all epics)
- `briefing --save` captures what happened, but it's a retrospective, not forward-looking
- No concept of "here's exactly what the next agent should do"

### Proposal: `emdx handoff`

A standalone command (also invoked by `emdx land --handoff`):

```
emdx handoff                       # Generate handoff for next session
emdx handoff --save                # Save to KB
emdx handoff --clipboard           # Copy to clipboard
emdx handoff --task FEAT-12        # Scope to specific task
```

**Output format — designed as agent instructions, not human prose:**

```markdown
# Handoff: Continue DEBT-7 (Refactor prime output)

## Status
- Branch: `refactor/prime-json`
- Last commit: `a1b2c3d Refactor _output_text to use builder pattern`
- Tests: passing (last run 23m ago)

## What Was Done
- Extracted query functions into typed helpers
- Added EpicInfo, ReadyTask, InProgressTask TypedDicts
- Refactored text output to use line builder

## What Remains
1. Wire --smart flag into JSON output path (_output_json doesn't handle smart_recent, tag_map yet)
2. Add tests for JSON smart output
3. Update docs/cli-api.md with new --smart examples

## Key Files
- `emdx/commands/prime.py` — main file being refactored
- `emdx/commands/types.py` — new TypedDicts
- `tests/test_prime.py` — needs new test cases

## Context Docs
- #287 "Prime refactoring plan" — the original plan
- #245 "TypedDict conventions" — style guide for new types

## Ready Tasks (unrelated to this work)
- FIX-3: TUI crash on large documents (blocked)
- FEAT-18: Add --watch-remove flag (ready)
```

**How it generates this:**

1. Determine scope — if `EMDX_TASK_ID` is set or `--task` is given, focus on that task. Otherwise, use the most recently active task.
2. Pull git context — branch, last 3 commits, uncommitted changes, test status
3. Pull task context — the focused task's description, log entries, related tasks
4. Pull doc context — `source_doc_id`, recently accessed docs
5. Assemble deterministically — no LLM call needed for the basic handoff. The structure is templated. (Optional `--smart` flag can use LLM to generate the "what remains" section from task logs + git diff.)
6. Save as doc with tags `handoff, active`

**Integration with prime:**

Add to `_output_text()` in prime.py:
```python
# Check for recent handoff
handoff = _get_recent_handoff()  # Last handoff doc < 24h old
if handoff:
    lines.append("HANDOFF FROM LAST SESSION:")
    lines.append(handoff["content"][:500])  # First 500 chars
```

This closes the loop: session N ends with `land` (which generates a handoff), session N+1 starts with `prime` (which injects that handoff).

**Implementation scope:** ~150-200 lines. Mostly query assembly + templating. The template is the key design artifact — getting the format right matters more than the code.

**What this learns from Beads:** The handoff is the bridge between sessions. It's not a summary (backward-looking) or a prime (broad). It's a focused, forward-looking set of instructions: "here's where I stopped, here's what you should do next." This is the single highest-leverage idea from Beads for emdx.

---

## Priority Ranking

If I were building these, in order:

1. **Handoff prompt generation** (#5) — highest leverage, smallest scope, closes the biggest gap
2. **`emdx land`** (#1) — orchestrates the handoff + existing cleanup, makes session-end crisp
3. **Aggressive prime scoping** (#3) — incremental improvements to an already-good system
4. **Completed work compaction** (#2) — nice-to-have, becomes important at scale
5. **Per-repo mode** (#4) — only if you have a concrete team/sharing use case

Items 1+2 together form a complete "session lifecycle" that mirrors Beads' strongest pattern: prime → work → land → prime → work → land.
