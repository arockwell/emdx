---
name: bootstrap
description: Bootstrap a knowledge base from a codebase. Reads source code, docs, git history, and CLAUDE.md to generate foundational KB documents covering architecture, components, patterns, history, and operations. Use when starting a new emdx KB for a project or rebuilding after data loss.
---

# Bootstrap Knowledge Base from Codebase

Generate foundational knowledge base documents by analyzing the current codebase. This creates the "EMDX about X" — a structured knowledge base that captures architecture, design decisions, patterns, conventions, and operational knowledge.

## Arguments

`$ARGUMENTS` — optional focus area (e.g., "architecture", "patterns", "all"). Defaults to "all".

## Process

### Phase 1: Discovery

Read the project's foundational documents to understand what exists:

```bash
# Check what's already in the KB
emdx find --recent 10 -s
emdx find --tags "architecture,gameplan" -s

# Read project docs
cat CLAUDE.md 2>/dev/null
cat README.md 2>/dev/null
ls docs/ 2>/dev/null
```

Also read:
- `pyproject.toml` or `package.json` (dependencies, project metadata)
- Key source directories (identify from project structure)
- Git log for major milestones: `git log --oneline --since="6 months ago" | head -50`
- Any existing design docs in `docs/`

### Phase 2: Document Generation

Generate documents in these categories. Each document should be a self-contained knowledge article, not a reference manual. Write in the voice of someone explaining to a knowledgeable colleague.

#### Category 1: Architecture & Design Decisions
For each major architectural choice, create a document explaining:
- **What** was chosen
- **Why** it was chosen over alternatives
- **Trade-offs** accepted
- **When** this might need to change

Save with: `echo "<content>" | emdx save --title "<title>" --tags "architecture,bootstrap"`

#### Category 2: Component Deep Dives
For each major component/service/module, create a document covering:
- **Purpose** — what problem it solves
- **How it works** — key algorithms, data flow
- **Dependencies** — what it relies on, what relies on it
- **Extension points** — how to add to it

Save with: `echo "<content>" | emdx save --title "<title>" --tags "component,bootstrap"`

#### Category 3: Patterns & Conventions
For each recurring pattern in the codebase, document:
- **The pattern** — what it looks like
- **Where it's used** — concrete examples
- **Why** — what problem it prevents
- **Anti-patterns** — what NOT to do

Save with: `echo "<content>" | emdx save --title "<title>" --tags "pattern,bootstrap"`

#### Category 4: Gotchas & Hard-Won Knowledge
Extract from CLAUDE.md's gotchas section, git blame for bug fixes, and test comments:
- **The problem** — what goes wrong
- **Root cause** — why it happens
- **Solution** — how to fix/avoid it
- **Detection** — how to notice early

Save with: `echo "<content>" | emdx save --title "<title>" --tags "gotcha,bootstrap"`

#### Category 5: Operational Runbooks
For each operational task (release, debugging, deployment):
- **When** to do it
- **Step-by-step** procedure
- **What can go wrong** and how to recover
- **Verification** — how to confirm success

Save with: `echo "<content>" | emdx save --title "<title>" --tags "runbook,bootstrap"`

### Phase 3: Cross-Linking

After saving all documents, run wikification to discover connections:

```bash
emdx maintain wikify --all --dry-run  # Preview links
emdx maintain wikify --all            # Create links
```

### Phase 4: Summary

Report what was generated:
- Number of documents per category
- Key documents created
- Suggested next steps (manual review, additional docs needed, gaps identified)

## Guidelines

- **Be opinionated**: Don't just describe what exists — explain WHY it exists
- **Be concrete**: Include file paths, function names, actual code patterns
- **Be honest about gaps**: If something is unclear or poorly documented, say so
- **Don't duplicate docs**: If good docs exist (README, CLAUDE.md, docs/), reference them rather than copying
- **Focus on tacit knowledge**: The stuff that's in developers' heads but not written down
- **One concept per document**: Each KB entry should be about one thing. Split aggressively.
- **Tag consistently**: Use the category tags above plus project-specific tags

## Scaling

For large codebases, use the Agent tool to parallelize — launch multiple subagents
that each handle one category or component, reading source code and saving docs
independently.
