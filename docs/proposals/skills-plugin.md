# Proposal: Skills Plugin System for emdx

> GitHub Issue: To be filed — see content below.

## Summary

emdx has two existing "skill-like" systems that work well individually but leave gaps between them:

1. **Claude Code commands** (`.claude/commands/`) — Markdown prompts that run inside Claude Code sessions. Powerful but repo-locked, no emdx integration, no persistence, no Python hooks.
2. **Recipes** (`emdx recipe`) — Document-as-prompt with YAML frontmatter and `{{var}}` substitution, executed via delegate. Good but no conditional logic, no KB queries, no learning between runs.

A skills plugin would bridge these: **KB-aware logic + delegate execution + persistent results.** A skill is a recipe that can think.

## The Problem

### Recipes are prompts, not programs

Recipes can't query the KB before running, make decisions based on current state, react to results, or remember anything between runs. The recipe executor (`recipe_executor.py`) pipes step N into step N+1, but there's no logic layer.

### Claude Code commands live in a different world

The `.claude/commands/` (fix-chain, audit, pr-check, etc.) only run inside Claude Code sessions. They can't be scheduled, triggered, or composed outside of a human driving Claude Code. They don't persist results structurally.

### No state between runs

Every delegate, recipe, and command starts from scratch. `/audit` doesn't know you ran an audit two days ago. `/fix-chain` doesn't know which bug patterns have manifested in this codebase. The KB *has* this state — nothing uses it proactively.

### No closed loops

When a delegate finishes, nothing happens until a human runs `emdx review list`. When `/fix-chain` finds a bug, nothing creates a task. When a gameplan goes stale, nothing detects it.

## What a Skill Is (in emdx terms)

A skill is a Python function that gets a context object with:
- **Read access** to the KB (find docs, get tasks, check execution history)
- **Write access** to the KB (save docs, create/update tasks, manage tags)
- **Delegate execution** (single, parallel, synthesis)
- **Shell execution** (tests, git, etc.)
- **User arguments**

And returns structured results that emdx tracks.

## Proposed CLI Surface

```bash
emdx skill list                          # List installed skills
emdx skill run audit                     # Run a skill
emdx skill run audit --input focus=security --input since="last monday"
emdx skill run verify --input doc=latest  # Verify delegate output
emdx skill run garden                    # KB hygiene
emdx skill run focus --input task=42     # Smart context loading
emdx skill info audit                    # Show skill details + inputs
emdx skill history audit                 # Execution history for a skill
```

## Skill Ideas

### Tier 1: Port and Enhance Existing `.claude/commands/`

These already exist as prompts. As skills, they'd gain KB-awareness and persistence.

**`audit`** — Currently runs 6 blind delegate prompts. As a skill:
- Checks KB for previous audit results
- Only scans files changed since last audit
- Compares new findings against existing tasks
- Creates tasks for genuinely new findings, marks resolved ones as done
- Saves a diff report: "3 new issues, 2 resolved, 4 persistent"

**`fix-chain`** — Currently analyzes PR diffs for bug patterns. As a skill:
- Loads known bug patterns from KB docs tagged `bug-pattern`
- When a finding is confirmed as a real bug, saves the pattern back to KB for next time
- Tracks which PRs have been swept (no re-work)
- Creates tasks grouped under an auto-generated epic

**`gameplan-review`** — Currently cross-references gameplans with PRs. As a skill:
- Directly queries KB for `gameplan,active` docs
- Calls GitHub API for merged PRs
- Actually updates tags on gameplans (done, stale, blocked)
- Saves review report with diff against previous review

**`pr-check`** — Currently a prompt for pre-PR quality checks. As a skill:
- Runs `pytest` and `ruff check .` directly (subprocess)
- Checks commit format via regex on `git log`
- Delegates only the "scan for subtle bugs" part to AI
- Produces structured pass/fail checklist

### Tier 2: New Skills That Fill Workflow Gaps

**`garden`** — KB hygiene, because knowledge bases rot:
- Find docs with overlapping content (semantic similarity)
- Identify stale docs that haven't been accessed or updated
- Detect orphaned tasks (no epic, no recent activity)
- Suggest merges and archives
- Runs incrementally — only checks docs modified/created since last garden run

**`verify`** — Trust but verify agent output:
- Takes a delegate output doc and verifies claims against actual code
- Checks that referenced file paths, function names, classes exist
- Flags hallucinated content
- Scores confidence: high/medium/low

**`retro`** — Learn from delegate history:
- Analyze recent delegate success rate, cost, duration
- Identify prompts that produce high-quality vs. garbage output
- Flag cost outliers
- Track trends

**`focus`** — Smart context loading (better than `prime`):
- Takes a task ID or description of what you're about to work on
- Searches KB semantically for related docs, past findings, patterns
- Checks for related unreviewed delegate outputs
- Produces a focused brief for the specific task

**`handoff`** — Session continuity:
- More structured than `wrapup` — oriented toward "what does the next session need"
- Identifies in-progress tasks with context
- Gathers relevant docs from this session
- Notes what was attempted and didn't work

### Tier 3: Workflow Automation

**`sweep`** — Closed-loop delegate quality:
- After delegates finish: check output quality, auto-tag for review
- If delegate failed, check error, decide if retryable, queue retry
- If all delegates in a group succeeded, run synthesis automatically

**`cascade`** — Chained multi-step workflows (recipes on steroids):
- Like recipes but with conditional branching and KB queries between steps
- Example: audit → create tasks from findings → delegate each → synthesize → pr-check → open PR
- Each step can query KB, decide whether to proceed, adjust the next step's prompt

## Suggested Implementation Order

1. **Skill runner infrastructure** — `emdx/skills/base.py` (SkillContext, SkillResult), `emdx/skills/registry.py` (discover skills in `emdx/skills/builtin/`), `emdx/commands/skill_cmd.py` (`emdx skill list|run|info|history`)
2. **`garden` skill** — Best first skill because it's purely KB-native (no delegates needed), demonstrates KB-awareness, solves a real problem (KB entropy)
3. **`audit` skill** — Best ported skill because the current `.claude/commands/audit.md` already calls delegate, so we can show the before/after clearly
4. **Iterate** — Add remaining skills based on what we learn from the first two

## Design Principles

- Skills are Python files with a `run(ctx)` function — start simple, no registry/entry-points/pip-packages until needed
- Built-in skills live in `emdx/skills/builtin/`, user skills in `~/.config/emdx/skills/`
- Recipes remain the lightweight, prompt-only option. Skills are for when you need Python logic, KB access, or composability
- Same output mode convention: plain text default, `--rich` for Rich, `--json` for structured
- Execution tracked in the existing executions table
