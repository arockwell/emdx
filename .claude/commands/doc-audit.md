# Documentation Audit

Audit all documentation files against the actual codebase for staleness.

## Steps

1. Launch parallel agents (Agent tool, `subagent_type: "Explore"`) to audit each doc:
   - **README.md** — Check every CLI example, command, flag against actual codebase. Find stale/missing items with line numbers.
   - **CLAUDE.md** — Check command references, hook descriptions, env vars against actual code and `.claude/` scripts.
   - **docs/ folder** — Check cli-api.md, architecture.md, development-setup.md against current codebase.

2. Review agent results for actionable items.

3. Fix issues directly or create PRs for larger changes.

4. If multiple fixes touch the same file, apply them sequentially to avoid conflicts.

## Important

- README.md is usually healthy — examples are tested by users
- cli-api.md and architecture.md rot fastest — they're the most detailed
- When multiple PRs touch the same file, merge one at a time and rebase the rest
