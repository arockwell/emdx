---
name: research
description: Search the emdx knowledge base for existing research, analysis, and decisions before starting new work. Use when investigating a topic, starting a task, or looking for prior art.
disable-model-invocation: true
---

# Research Knowledge Base

Search emdx for existing knowledge about: $ARGUMENTS

## Search Commands

**Full-text search (default):**
```bash
emdx find "query"
```

**Semantic/conceptual search:**
```bash
emdx find "concept" --mode semantic
```

**Search with key info extraction:**
```bash
emdx find "query" --extract
```

**Filter by tags:**
```bash
emdx find --tags "gameplan,active"              # AND logic (all tags)
emdx find --tags "gameplan,analysis" --any-tags  # OR logic (any tag)
```

**Exclude tags:**
```bash
emdx find "api" --no-tags "archived,draft"
```

**Filter by date:**
```bash
emdx find "query" --created-after 2026-01-01
emdx find "query" --modified-after 2026-02-01
```

**Recent documents:**
```bash
emdx recent        # Last 10 accessed
emdx recent 20     # Last 20
```

**View a specific document:**
```bash
emdx view <id>
```

**Short summary results:**
```bash
emdx find "query" -s
```

**Discover topics and coverage gaps:**
```bash
emdx explore              # Cluster docs into topics
emdx explore --gaps       # Find thin/stale areas
```

## Search Strategy

1. Start broad: `emdx find "topic" -s` to see what exists
2. Narrow with tags: `emdx find --tags "analysis,active"`
3. Try semantic if keyword search misses: `emdx find "concept" --mode semantic`
4. Check recent work: `emdx recent`
5. Explore topics: `emdx explore` for a high-level map

## Important: FTS5 Limitations

`emdx find` does NOT support OR/AND/NOT operators — terms get quoted internally. To search for multiple concepts, run separate find commands:
```bash
emdx find "authentication" -s
emdx find "login flow" -s
emdx find "session management" -s
```

## After Finding Results

- Use `emdx view <id>` to read full documents
- Reference existing work instead of redoing it
- If nothing exists, proceed with new research and save results with `/emdx:save`
