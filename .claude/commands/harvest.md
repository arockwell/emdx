# Harvest — Extract Reusable Skills from This Session

Analyze the current conversation and extract reusable patterns that should be saved as Claude Code commands or agents.

## What to Look For

Scan everything discussed in this conversation for:

### 1. Commands/Skills (→ `.claude/commands/*.md`)
- Multi-step workflows that were executed and worked well
- Audit patterns, deployment flows, review checklists
- Anything the user might want to run again with `/command-name`
- Look for: repeated structure, clear steps, parameterizable with `$ARGUMENTS`

### 2. Agent Personas (→ `.claude/agents/*.md`)
- Specialized behaviors that emerged — e.g., "you acted as a security reviewer"
- Roles with specific knowledge, patterns, and analysis approaches
- Look for: domain expertise, specific bug patterns, review criteria

### 3. Prompt Templates
- Agent tool invocations or multi-step workflows that produced good results
- Prompts with clear structure that could be reused
- These become either commands (if multi-step) or agent recipes

### 4. CLAUDE.md Additions
- Conventions or patterns discovered that should be remembered project-wide
- New rules, gotchas, or preferences that emerged

## How to Analyze

1. Review the full conversation history available to you
2. Identify moments where a workflow, approach, or persona was particularly effective
3. For each finding, draft the file contents matching existing format conventions

## Format Conventions

**Commands** follow this pattern (see existing `.claude/commands/` files):
```markdown
# Title

One-line description.

## Scope / Target
How $ARGUMENTS is used (if applicable).

## Steps / What to Check
Numbered steps or categorized checks.

## Output
What the command produces.
```

**Agents** follow this pattern (see existing `.claude/agents/` files):
```markdown
# Agent Name

You are a [role] specialized in [domain]. Your job is to [goal].

## Your Specialization
What makes this agent different from generic Claude.

## Patterns / Knowledge
Specific patterns, historical context, domain expertise.

## Analysis Approach
Step-by-step method.

## Important
Constraints and anti-patterns.
```

## Output

Present findings as a numbered list:

```
1. **Command: /deploy-check** — Pre-deployment verification flow
   File: .claude/commands/deploy-check.md
   [proposed contents]

2. **Agent: performance-reviewer** — Reviews code for perf regressions
   File: .claude/agents/performance-reviewer.md
   [proposed contents]

3. **CLAUDE.md addition** — "Always run X before Y"
   [proposed addition]
```

If $ARGUMENTS is "dry" or "preview", only show findings without creating files.

If nothing worth harvesting is found, say so — don't invent patterns that weren't there.

## On Confirmation

After the user approves (or selects which items to create):

1. Write approved `.claude/commands/*.md` and `.claude/agents/*.md` files
2. Apply any approved CLAUDE.md additions via Edit
3. Summarize what was created
