# Analysis: emdx delegate vs Native Claude Code Agents

## Context

emdx is a knowledge base plugin used across multiple projects — not just for emdx
development itself. The CLAUDE.md, hooks, and skills ship to every project that installs
emdx as a plugin.

`emdx delegate` was built when Claude Code had poor sub-agent support. It solved a real
problem: spawning Claude subprocess sessions with automatic KB integration (save output,
track tasks, inject context). Claude Code now has the Agent tool with worktree isolation,
model selection, parallel execution, conversation context inheritance, and background
execution.

**The question:** Should the plugin continue mandating `emdx delegate` as the sub-agent
mechanism, or should it teach Claude to use emdx commands (`save`, `find`, `task`)
naturally alongside whatever execution model Claude Code provides?

## What delegate provides (as a plugin feature)

When a user in *any* project runs `/emdx:delegate "analyze auth"`, delegate:

1. Creates a task in the KB (`emdx task add`, status=active)
2. Spawns `claude --print` as a subprocess
3. Saves the output to the KB (`emdx save`)
4. Updates the task (`emdx task done`)
5. Prints output to stdout (visible to calling session)

For parallel tasks, it also:
6. Runs up to 10 tasks concurrently
7. Optionally synthesizes all outputs into one document

**The entire value is steps 1, 3, 4** — KB integration. Steps 2 and 5 are just subprocess
management that the native Agent tool now handles better.

## Why native Agent tool is better for plugin users

| Capability | Delegate | Native Agent tool |
|-----------|----------|-------------------|
| Conversation context | None — starts fresh | Full history — "investigate the error above" works |
| User approval | Must pre-authorize all tools | Interactive approve/deny |
| Background execution | Blocks the session | `run_in_background: true` |
| Resumability | Fire and forget | Resume by agent ID |
| Cost tracking | Manual | Built into Claude Code |
| Model selection | `--model` flag | `model` parameter |
| Worktree isolation | Custom worktree code | `isolation: "worktree"` |
| Works in any project | Only if emdx installed | Always available |

**The conversation context gap matters most.** When a user is debugging something and
wants to spawn a sub-agent, the native Agent sees everything discussed so far. A delegate
subprocess knows nothing — the user must re-explain the entire context in the prompt.

## What gets lost without delegate

### 1. Auto-save (medium risk)

Delegate guarantees output persists to the KB. Without it, Claude must remember to
`emdx save` after agent work. CLAUDE.md instructions help but aren't 100% reliable.

**Mitigation:** The `/emdx:wrapup` skill catches unsaved work at session end. The
`prime.sh` hook reminds Claude of save obligations at session start.

### 2. Auto task tracking (low risk)

Delegate auto-creates and updates tasks. Without it, Claude must explicitly
`emdx task add` / `emdx task done`.

**Mitigation:** CLAUDE.md already mandates task tracking for multi-step work. This is
the same instruction surface — it's just that delegate made it automatic.

### 3. Parallel synthesis (low risk)

Delegate's `--synthesize` combines N parallel outputs into one document. The native
Agent tool has no synthesis step.

**Mitigation:** The calling session receives all agent results and can synthesize them
itself. This is arguably better — the calling session has the full conversation context
to inform the synthesis.

## The plugin perspective

The key insight: emdx's value to plugin users is the **knowledge base**, not the
**execution engine**. Users install emdx because they want:

- Persistent memory across sessions (`save`, `find`)
- Task tracking (`task add`, `task ready`, `task done`)
- Session context (`prime`, `wrapup`)
- Searchable research history (`find`, `view`)

They don't install emdx because they want a different way to spawn sub-agents. The Agent
tool is Claude Code's native mechanism for that, and it's better at it.

## Proposed changes

### CLAUDE.md (the instructions that ship to all projects)

**Remove:**
- "NEVER use the Task tool to spawn sub-agents. Use `emdx delegate` instead."
- The separate "Delegate Sessions" behavioral section
- References to delegate as the primary execution mechanism

**Reframe mandatory behaviors as KB usage habits:**
- Save significant findings: `emdx save`
- Search before researching: `emdx find`
- Track multi-step work: `emdx task add` / `emdx task done`
- Prime on session start: `emdx prime` (hook does this)
- Wrap up on session end: `/emdx:wrapup`

**Keep delegate as documented option:**
- Useful for batch CLI dispatch (run 5 tasks from terminal, not from Claude)
- Useful when you specifically want guaranteed auto-save
- Just not mandated as THE way to do sub-agent work

### Skills

| Skill | Change |
|-------|--------|
| `/emdx:delegate` | Update description — "batch dispatch from CLI" not "how to do sub-agents" |
| `/emdx:save` | No change |
| `/emdx:research` | No change |
| `/emdx:prime` | No change |
| `/emdx:tasks` | No change |
| `/emdx:wrapup` | No change |

### Hooks

| Hook | Change |
|------|--------|
| `prime.sh` | Update — remove delegate-specific branching, focus on universal priming |
| `save-output.sh` | Already deprecated. Remove or keep as no-op. |
| `session-end.sh` | Keep — still useful for delegate sessions that do happen |

### Plugin metadata

Update `plugin.json` description from "delegate parallel work" emphasis to
"persistent memory and knowledge management."

## Migration risks

1. **Compliance gap** — Without auto-save, some findings won't get saved. The wrapup
   skill is the safety net. If this proves insufficient, a post-Agent-tool hook could
   prompt "save this result?"

2. **Plugin users who learned delegate** — `/emdx:delegate` keeps working. No breakage.
   The change is in what Claude reaches for by default.

3. **CLAUDE.md complexity** — Current CLAUDE.md has a lot of delegate-specific content.
   Removing it actually simplifies the instructions, which is good for plugin users
   whose projects have their own CLAUDE.md instructions to absorb.

## Recommendation

Update CLAUDE.md and skills to position emdx as a knowledge base that Claude uses
naturally, not an execution harness that replaces Claude's native tools. Keep delegate
as an option. No code changes needed.
