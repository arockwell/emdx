# Analysis: emdx delegate vs Native Claude Code Agents

## Context

`emdx delegate` was built when Claude Code had no native sub-agent support. It solved
a real problem: spawning Claude subprocess sessions with knowledge base integration.
Claude Code now has the Agent tool with worktree isolation, model selection, and parallel
execution. This analysis examines what delegate provides, what's now redundant, and what
the migration path looks like.

## What delegate actually does

Decomposing `emdx delegate "task"` into its constituent operations:

| Step | What delegate does | Could native Agent do it? |
|------|-------------------|--------------------------|
| 1. Create task | `_safe_create_task(title, status="active")` | No — needs explicit `emdx task add` call |
| 2. Build prompt | Append PR/branch instructions | Yes — prompt construction is just text |
| 3. Set env vars | `EMDX_TASK_ID`, `EMDX_DOC_ID`, `EMDX_AUTO_SAVE` | N/A — hooks would need different trigger |
| 4. Spawn Claude | `subprocess.run(["claude", "--print"])` | Yes — Agent tool does this natively |
| 5. Worktree | `create_worktree()` for isolation | Yes — `isolation: "worktree"` |
| 6. Save output | `_safe_save_document(title, output, tags)` | No — needs explicit `emdx save` call |
| 7. Update task | `_safe_update_task(task_id, status="done")` | No — needs explicit `emdx task done` call |
| 8. Extract PR URL | Parse output for github PR URLs | No — but not needed if Agent creates PR |
| 9. Print to stdout | Output visible to calling session | Yes — Agent tool returns results to parent |

**Core insight:** Steps 4-5 (spawn + isolate) are fully replaced by the Agent tool.
Steps 1, 6, 7 (KB integration) are the actual value — and they're just emdx CLI calls.

## The three things delegate really provides

### 1. Automatic KB persistence (save output)

Delegate auto-saves every sub-agent's output to the knowledge base. With native agents,
this requires the calling session to explicitly run `emdx save` after the agent returns.

**Gap assessment:** Small. The calling Claude session gets the agent's result and can
pipe it to `emdx save`. The CLAUDE.md already mandates saving significant outputs.

### 2. Automatic task lifecycle (create → active → done)

Delegate creates a task before execution and marks it done after. With native agents,
this requires the calling session to use `emdx task add` / `emdx task done`.

**Gap assessment:** Small. CLAUDE.md already mandates task tracking. The difference is
whether it happens automatically (delegate) or explicitly (CLAUDE.md instructions).

### 3. Parallel execution with synthesis

Delegate can run 2-10 tasks concurrently via ThreadPoolExecutor, collect all outputs,
and optionally run a synthesis pass that combines them into one document.

**Gap assessment:** Medium. Claude Code's Agent tool can launch multiple agents in
parallel (multiple Agent tool calls in one message). But there's no built-in synthesis —
the calling session would need to read all results and synthesize itself.

## What delegate does NOT provide that native agents do

| Capability | Delegate | Native Agent tool |
|-----------|----------|-------------------|
| Access to conversation context | No — `claude --print` starts fresh | Yes — "access to current context" agents see full history |
| Interactive tool approval | No — must pre-authorize all tools | Yes — user can approve/deny per tool |
| Model flexibility | `--model` flag | `model` parameter (sonnet/opus/haiku) |
| Resumability | No — fire and forget | Yes — agents can be resumed by ID |
| Background execution | Blocks the terminal | `run_in_background: true` with notifications |
| Cost visibility | Manual token tracking | Built into Claude Code |
| Sub-agent recursion | Explicitly forbidden | Supported (agents can spawn agents) |

**The conversation context gap is significant.** When you say "investigate the error
discussed above," a native Agent sees the full conversation. A delegate subprocess
starts completely fresh and needs the entire context re-stated in the prompt.

## Proposed migration: "emdx as habit, not harness"

### Philosophy shift

**Before:** "Use delegate to spawn sub-agents" (emdx controls execution)
**After:** "Use emdx commands naturally" (emdx is a knowledge store, Claude Code controls execution)

The key reframe: emdx is a **knowledge base that AI agents populate and humans curate**.
The CLI commands (`save`, `find`, `task`, `prime`) are the interface. How those commands
get invoked — by a human, by Claude Code directly, by an Agent sub-agent, or by
`emdx delegate` — doesn't matter.

### What changes in CLAUDE.md

#### Remove
- The mandate "NEVER use the Task tool to spawn sub-agents. Use `emdx delegate` instead."
- The separate "Delegate Sessions" behavioral rules (these become unnecessary when
  delegate isn't the primary path)

#### Reframe
- "Mandatory Behaviors" become about **using emdx commands**, not about using delegate:
  - Save significant findings: `emdx save`
  - Track work: `emdx task add` / `emdx task done`
  - Search before researching: `emdx find`
  - Check context on session start: `emdx prime`
  - Clean up on session end: `/emdx:wrapup`

#### Keep delegate as option
- Delegate remains useful for **batch CLI dispatch** (run 5 tasks from the terminal)
- Delegate remains useful when you want **guaranteed auto-save** without trusting the
  agent to remember
- Remove the mandate; keep the docs

### What changes in skills

| Skill | Change |
|-------|--------|
| `/emdx:delegate` | Keep, but rewrite description: "Batch dispatch for CLI use" |
| `/emdx:save` | No change — already correct |
| `/emdx:research` | No change — already correct |
| `/emdx:prime` | No change — already correct |
| `/emdx:tasks` | No change — already correct |
| `/emdx:wrapup` | No change — already correct |

### What changes in hooks

| Hook | Change |
|------|--------|
| `prime.sh` | Keep as-is — still useful for both human and delegate sessions |
| `save-output.sh` | Already deprecated (delegate saves inline). Can remove. |
| `session-end.sh` | Keep — still marks tasks done for delegate sessions |

### What changes in code

- `emdx/commands/delegate.py` — No code changes needed. It still works.
- `emdx/models/tasks.py` — The `exclude_delegate` parameter becomes less important
  but doesn't hurt.
- No breaking changes required.

## Proposed new CLAUDE.md section (replacing delegate mandate)

```markdown
### Using emdx with Sub-Agents

When using the Agent tool for sub-tasks, ensure KB integration:

**Before spawning:** Check if prior research exists
    emdx find "topic" -s

**After agent returns:** Save significant results
    echo "<agent output>" | emdx save --title "Title" --tags "analysis"

**For tracked work:** Use task lifecycle
    emdx task add "Research auth patterns" --epic <id> --cat FEAT
    # ... spawn agent, do work ...
    emdx task done <id>

**For batch/parallel dispatch:** `emdx delegate` remains available
    emdx delegate --synthesize "task1" "task2" "task3"
```

## Migration risks

1. **Agent forgets to save** — Without delegate's auto-save, results might not
   persist. Mitigation: strong CLAUDE.md instructions + the wrapup skill catches gaps.

2. **Task tracking drops** — Without auto-create/update, tasks might not get tracked.
   Mitigation: CLAUDE.md already requires task tracking for multi-step work.

3. **Parallel synthesis gap** — No built-in synthesis with native agents.
   Mitigation: The calling session can synthesize agent results itself, or use
   delegate specifically for the synthesis use case.

4. **Existing workflow disruption** — Users who've built muscle memory around
   `/emdx:delegate` would need to adapt. Mitigation: Keep delegate working, just
   remove the mandate.

## Recommendation

**Phase 1 (now):** Update CLAUDE.md to remove the delegate mandate. Reframe mandatory
behaviors around using emdx CLI commands naturally. Keep delegate as a documented option.

**Phase 2 (observe):** Watch whether Claude Code sessions actually save/track
consistently without the delegate harness. If compliance drops, consider a lightweight
"post-agent hook" that prompts to save.

**Phase 3 (optional):** If delegate usage drops to zero, deprecate it formally.
Remove the TUI delegate browser and execution tracking infrastructure.

## Decision needed

- **Scope:** Just CLAUDE.md + skills? Or also README, docs/cli-api.md, CHEATSHEET?
- **Aggressiveness:** Remove delegate mandate but keep docs? Or actively discourage?
- **Hooks:** Remove the deprecated `save-output.sh`? Or leave for backward compat?
