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
# Add an idea and run it all the way to done (creates PR!)
emdx cascade add "Add keyboard shortcuts help overlay" --auto

# Add an idea and stop before implementation (no PR)
emdx cascade add "Add dark mode toggle" --auto --stop planned

# Manual step-by-step processing (alternative approach)
emdx cascade add "Another idea"
emdx cascade process idea --sync
emdx cascade process prompt --sync
emdx cascade process analyzed --sync
emdx cascade process planned --sync  # Creates actual PR!

# Check status
emdx cascade status

# View cascade run history
emdx cascade runs
```

## Commands Reference

### `emdx cascade add`

Add a new idea to the cascade and optionally run it automatically.

```bash
# Basic usage
emdx cascade add "Build a REST API for user management"
emdx cascade add "Add dark mode" --title "Dark Mode Feature"
emdx cascade add "Refactor auth" --stage prompt  # Start at different stage

# Auto mode - run through all stages automatically
emdx cascade add "My feature idea" --auto              # Runs to done, creates PR
emdx cascade add "My idea" --auto --stop planned       # Stops at planned (no PR)
emdx cascade add "My idea" --auto --stop analyzed      # Stops at analyzed

# Start at a later stage with auto
emdx cascade add "My gameplan" --stage planned --auto  # Just implement and PR
```

**Options:**
- `--title TEXT` - Custom document title
- `--stage TEXT` - Starting stage (default: idea)
- `--auto` / `-a` - Run through stages automatically without manual intervention
- `--stop TEXT` - Stage to stop at when using --auto (default: done)

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

Run the cascade continuously or in auto mode.

```bash
# Auto mode - process all queued documents end-to-end
emdx cascade run --auto                    # Process all ideas to done
emdx cascade run --auto --stop planned     # Process all ideas to planned (no PRs)

# Continuous daemon mode (checks periodically)
emdx cascade run                           # Process all stages continuously
emdx cascade run --once                    # Single iteration then exit
emdx cascade run --interval 10             # Check every 10 seconds
```

**Options:**
- `--auto` / `-a` - Process documents end-to-end automatically
- `--stop TEXT` - Stage to stop at with --auto (default: done)
- `--once` - Run one iteration then exit
- `--interval FLOAT` - Seconds between checks (default: 5.0)

### `emdx cascade runs`

Show cascade run history. Each run represents an end-to-end cascade journey.

```bash
# Show recent cascade runs
emdx cascade runs

# Limit number of runs shown
emdx cascade runs --limit 5

# Filter by status
emdx cascade runs --status running
emdx cascade runs --status completed
emdx cascade runs --status failed
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
| `v` | Toggle activity view (runs vs executions) |

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
│ Cascade Runs:                  (v to toggle view)           │
│ #1  💡idea → ✅done ✓   ✓ PR    #42 Dark mode toggle        │
│ #2  💡idea → 📋planned  ⟳ run   #45 Keyboard shortcuts      │
└─────────────────────────────────────────────────────────────┘
```

### Activity Panel

The activity panel shows cascade runs (press `v` to toggle between views):

**Runs View (default):**
- Shows end-to-end cascade journeys as grouped runs
- Progress indicator: `💡idea → 📋planned → ✅done`
- Status: running, completed, failed, paused
- PR indicator when a pull request was created

**Executions View:**
- Shows individual stage executions
- Links executions to their parent cascade run
- More granular view of what's happening

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

-- Cascade runs table for tracking end-to-end cascade journeys
CREATE TABLE cascade_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_doc_id INTEGER NOT NULL,      -- Original document
    current_doc_id INTEGER,              -- Current document being processed
    start_stage TEXT NOT NULL,           -- Where cascade started
    stop_stage TEXT NOT NULL DEFAULT 'done',  -- Where to stop
    current_stage TEXT NOT NULL,         -- Current progress
    status TEXT NOT NULL DEFAULT 'running',   -- running/completed/failed/paused
    pr_url TEXT,                         -- PR URL if created
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    error_message TEXT
);

-- Executions link to cascade runs
ALTER TABLE executions ADD COLUMN cascade_run_id INTEGER REFERENCES cascade_runs(id);
```

## Integration with Activity View

The Cascade browser's activity panel shows cascade runs grouped together:
- **Runs view**: Shows end-to-end cascade journeys with progress indicators
- **Executions view**: Shows individual stage executions linked to their runs
- Press `v` to toggle between views

## Best Practices

1. **Start small** - Add simple, focused ideas rather than complex multi-feature requests
2. **Use --auto for hands-off** - Let cascade run end-to-end without manual intervention
3. **Use --stop planned to review** - Stop before implementation to review the gameplan
4. **Use synthesize** - Combine related analyses into cohesive plans
5. **Check the PR** - The autonomous implementation may need tweaks
6. **Monitor with `cascade runs`** - Track your cascade journeys and their status

## Comparison with Other Systems

| Feature | Cascade | `emdx delegate` | `emdx workflow` |
|---------|---------|-----------------|-----------------|
| Stage transformations | ✅ | ❌ | ❌ |
| Autonomous execution | ✅ | ✅ | ✅ |
| PR creation | ✅ | ✅ | ❌ |
| Document lineage | ✅ | ❌ | ✅ |
| Multi-agent parallel | ❌ | ✅ | ✅ |
| Sequential chains | ❌ | ✅ | ❌ |
| Custom stages | ❌ | ❌ | ✅ |

Use Cascade when you want ideas to flow automatically to implementation. Use `emdx delegate` for one-shot execution (parallel, chain, PR creation, worktree isolation). Use workflows for complex multi-stage processes with custom configurations.
