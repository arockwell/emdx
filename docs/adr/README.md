# Architecture Decision Records

This directory contains Architecture Decision Records (ADRs) for EMDX. ADRs document significant architectural decisions made during development.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [ADR-001](001-sqlite-fts5-storage.md) | SQLite + FTS5 as Storage Layer | Accepted |
| [ADR-002](002-typer-cli-framework.md) | Typer for CLI Framework | Accepted |
| [ADR-003](003-textual-tui.md) | Textual for TUI | Accepted |
| [ADR-004](004-delegate-worktree-pattern.md) | Delegate/Worktree Pattern for Parallel Execution | Superseded |

## ADR Template

When creating new ADRs, use this template:

```markdown
# ADR-XXX: Title

## Status

Accepted | Proposed | Deprecated | Superseded

## Context

What is the issue that we're seeing that is motivating this decision?

## Decision

What is the change that we're proposing and/or doing?

## Consequences

What becomes easier or more difficult to do because of this change?
```

## References

- [Michael Nygard's ADR article](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)
- [ADR GitHub Organization](https://adr.github.io/)
