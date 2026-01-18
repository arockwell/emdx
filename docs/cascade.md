# Cascade - Autonomous Document Transformation

Cascade transforms raw ideas into working code through a series of Claude-powered stages. Drop an idea in at the top, and it cascades down to a finished pull request.

## Overview

```
idea → prompt → analyzed → planned → done
  │       │         │          │        │
  │       │         │          │        └─ PR created, code shipped
  │       │         │          └─ Implementation gameplan
  │       │         └─ Thorough analysis
  │       └─ Well-formed prompt
  └─ Raw idea
```

Each transition is handled by Claude, transforming the document at one stage into a more refined version at the next.

## Quick Start

```bash
# Add an idea
emdx cascade add "Add keyboard shortcuts help overlay"

# Process through stages (each uses Claude)
emdx cascade process idea --sync
emdx cascade process prompt --sync
emdx cascade process analyzed --sync
emdx cascade process planned --sync  # Creates actual PR!

# Check status
emdx cascade status
```

## Commands Reference

### `emdx cascade add`

Add a new idea to the cascade.

```bash
emdx cascade add "Build a REST API for user management"
emdx cascade add "Add dark mode" --title "Dark Mode Feature"
emdx cascade add "Refactor auth" --stage prompt  # Start at different stage
```

### `emdx cascade status`

Show document counts at each stage.

```
┏━━━━━━━━━━┳━━━━━━━┳━━━┓
┃ Stage    ┃ Count ┃ → ┃
┡━━━━━━━━━━╇━━━━━━━╇━━━┩
│ idea     │     3 │ → │
│ prompt   │     1 │ → │
│ analyzed │     0 │ → │
│ planned  │     2 │ → │
│ done     │     5 │   │
└──────────┴───────┴───┘
```

### `emdx cascade process`

Process the next document at a stage through Claude.

```bash
# Process oldest doc at 'idea' stage
emdx cascade process idea

# With --sync to wait for completion
emdx cascade process prompt --sync

# Process specific document
emdx cascade process analyzed --doc 123 --sync

# Dry run (show what would be processed)
emdx cascade process planned --dry-run
```

**Note:** The `planned → done` transition uses a special implementation prompt that instructs Claude to:
1. Write actual code implementing the gameplan
2. Create a git branch
3. Make commits
4. Create a pull request
5. Return the PR URL

This stage has a 30-minute timeout (vs 5 minutes for others) due to the complexity.

### `emdx cascade run`

Run the cascade continuously as a daemon.

```bash
# Process all stages continuously
emdx cascade run

# Single iteration
emdx cascade run --once

# Only process specific stages
emdx cascade run --stages idea,prompt

# Custom check interval
emdx cascade run --interval 10
```

### `emdx cascade advance`

Manually advance a document to the next stage (skip processing).

```bash
emdx cascade advance 123           # Move to next stage
emdx cascade advance 123 --to done # Jump to specific stage
```

### `emdx cascade remove`

Remove a document from the cascade (keeps the document in the knowledge base).

```bash
emdx cascade remove 123
```

### `emdx cascade synthesize`

Combine multiple documents at a stage into one synthesized document.

```bash
# Combine all analyzed docs into one planned doc
emdx cascade synthesize analyzed

# With custom title
emdx cascade synthesize analyzed --title "Combined Feature Analysis"

# Keep source docs at current stage (don't move to done)
emdx cascade synthesize analyzed --keep
```

## TUI Browser

Press `4` in the emdx GUI to access the Cascade browser.

### Navigation

| Key | Action |
|-----|--------|
| `h/l` | Switch between stages |
| `j/k` | Navigate documents in current stage |
| `Enter` | View document details |
| `a` | Advance document to next stage |
| `p` | Process document through Claude |
| `s` | Synthesize selected documents |
| `Space` | Toggle selection (for multi-select synthesis) |
| `r` | Refresh |

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│ 💡 3 │ 📝 1 │ 🔍 0 │ 📋 2 │ ✅ 5                    [idea]  │  ← Summary bar
├─────────────────────────────────────────────────────────────┤
│ Documents at 'idea':          │ Preview:                    │
│                               │                             │
│ > Dark mode toggle            │ # Dark mode toggle          │
│   Keyboard shortcuts          │                             │
│   User avatars                │ Add a dark mode toggle...   │
│                               │                             │
├───────────────────────────────┴─────────────────────────────┤
│ Recent Activity:                                            │
│ ✅ 12:34 Dark mode → done                                   │
│ 🔄 12:30 Keyboard shortcuts processing...                   │
└─────────────────────────────────────────────────────────────┘
```

### Done Stage Indicators

In the done stage, documents show:
- `🔗` - Has a linked PR
- `✓` - Has child documents (outputs) but no PR

## Architecture

### Stage Prompts

Each stage uses a specific prompt template:

| Stage | Transformation |
|-------|---------------|
| `idea` | "Convert this idea into a well-formed prompt..." |
| `prompt` | "Analyze this prompt and provide a thorough analysis..." |
| `analyzed` | "Based on this analysis, create a detailed implementation gameplan..." |
| `planned` | Special implementation prompt with PR creation instructions |

### Child Documents

Each processing step creates a **child document** preserving lineage:
- Original document stays at its stage
- New child document is created at the next stage
- Parent-child relationship tracked via `parent_id`

This means you can trace any finished PR back through all its transformations.

### PR URL Tracking

When the `planned → done` stage completes:
1. Claude's output is scanned for `PR_URL: https://github.com/...`
2. The URL is stored in the `pr_url` column
3. The cascade browser shows 🔗 for documents with PRs

### Database Schema

```sql
-- Documents table additions for cascade
ALTER TABLE documents ADD COLUMN stage TEXT;  -- 'idea', 'prompt', etc.
ALTER TABLE documents ADD COLUMN pr_url TEXT; -- PR link for done stage

-- Indexes for efficient stage queries
CREATE INDEX idx_documents_stage ON documents(stage);
CREATE INDEX idx_documents_pr_url ON documents(pr_url) WHERE pr_url IS NOT NULL;
```

## Integration with Activity View

Cascade executions appear in the Activity view (screen `1`) with:
- `📋` icon for cascade items
- Document title and current stage
- `🔗` prefix if PR was created
- Deduplication (only shows latest execution per document)

## Best Practices

1. **Start small** - Add simple, focused ideas rather than complex multi-feature requests
2. **Use --sync** - Wait for completion to see results immediately
3. **Review at planned** - Check the gameplan before letting it create a PR
4. **Use synthesize** - Combine related analyses into cohesive plans
5. **Check the PR** - The autonomous implementation may need tweaks

## Comparison with Other Systems

| Feature | Cascade | `emdx run` | `emdx workflow` |
|---------|---------|-----------|-----------------|
| Stage transformations | ✅ | ❌ | ❌ |
| Autonomous execution | ✅ | ✅ | ✅ |
| PR creation | ✅ | ❌ | ❌ |
| Document lineage | ✅ | ❌ | ✅ |
| Multi-agent parallel | ❌ | ✅ | ✅ |
| Custom stages | ❌ | ❌ | ✅ |

Use Cascade when you want ideas to flow automatically to implementation. Use `emdx run` for quick parallel tasks. Use workflows for complex multi-stage processes with custom configurations.
