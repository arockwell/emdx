# EMDX CLI Cheat Sheet

Quick reference for the most common emdx commands and patterns.

---

## 🔍 Search & Discovery

```bash
# Full-text search (keyword-based)
$ emdx find "authentication bug"

# Semantic/conceptual search
$ emdx find "how to handle errors" --mode semantic

# Search by tags (comma = AND)
$ emdx find --tags "gameplan,active"

# Search by tags (OR logic)
$ emdx find --tags "analysis,bugfix" --any-tags

# List all documents
$ emdx find --all

# Recently accessed documents
$ emdx find --recent 10

# Find similar documents
$ emdx find --similar 42

# RAG: question + answer
$ emdx find --ask "What's the authentication flow?"

# RAG: just context (for piping)
$ emdx find --context "What's the auth flow?" | claude

# Extract key info from results
$ emdx find "performance optimization" --extract
```

**Search Tips:**
- OR/AND/NOT do NOT work in FTS5 queries (terms get quoted)
- Use separate `find` calls or `--tags` with `--any-tags` for OR logic
- Semantic search requires embeddings: `emdx maintain index`

---

## 💾 Save Content

```bash
# Save from file
$ emdx save document.md
$ emdx save --file notes.txt --tags "notes,active"

# Save from stdin
$ echo "Quick note about the bug" | emdx save --title "Bug Notes"
$ echo "Analysis results" | emdx save --title "Analysis" --tags "analysis,done"

# DON'T: emdx save "text content"  # Looks for a FILE named "text content"
# DO: echo "text content" | emdx save --title "Title"
```

**Common Tags:**
- **Content:** `gameplan`, `analysis`, `bugfix`, `security`, `notes`
- **Status:** `active`, `done`, `blocked`
- **Outcome:** `success`, `failed`, `partial`

---

## 👁️ View & Edit

```bash
# View document
$ emdx view 42

# View with link graph
$ emdx view 42 --links

# Edit document
$ emdx edit 42

# Edit title/tags only
$ emdx edit 42 --title "New Title" --tags "updated,tags"

# Delete (moves to trash)
$ emdx delete 42

# Restore from trash
$ emdx restore 42
```

---

## 🏷️ Tags

```bash
# Add tags (text aliases auto-convert to emojis)
$ emdx tag add 42 gameplan active

# Remove tags
$ emdx tag remove 42 active

# List all tags with counts
$ emdx tag list

# View emoji legend
$ emdx tag legend
```

---

## ✅ Tasks

### Basic Task Management

```bash
# Create task (use --epic and --cat, NOT --tags)
$ emdx task add "Fix auth bug" -D "Details here" --epic 898 --cat FIX

# Show ready tasks (unblocked, not done)
$ emdx task ready

# Mark in-progress
$ emdx task active 42

# Mark complete
$ emdx task done 42

# Block/unblock
$ emdx task block 42 "Waiting on API docs"
$ emdx task unblock 42

# View task details
$ emdx task view 42
```

### Categories & Epics

```bash
# List available categories
$ emdx task cat list

# Rename or merge categories
$ emdx task cat rename OLD NEW

# List active epics
$ emdx task epic list

# Create epic
$ emdx task add "Q1 Auth Overhaul" --cat EPIC

# Group task under epic
$ emdx task add "Add OAuth provider" --epic 42 --cat FEAT
```

### Dependencies

```bash
# Add dependency (42 depends on 41)
$ emdx task dep add 42 41

# Remove dependency
$ emdx task dep remove 42 41

# View task's dependencies
$ emdx task view 42  # Shows deps in output
```

---

## 📊 Status & Stats

```bash
# Knowledge base overview
$ emdx status

# Knowledge base statistics
$ emdx status --stats

# Detailed stats with project breakdown
$ emdx status --stats --detailed

# Current work context (tasks + recent docs)
$ emdx prime

# JSON output (for scripting)
$ emdx prime --json
```

---

## 🛠️ Maintenance

### Database & Index

```bash
# Build/update embedding index (for semantic search)
$ emdx maintain index

# Find similar docs to merge
$ emdx maintain compact --dry-run

# Auto-link related documents
$ emdx maintain link --all
$ emdx maintain link --doc 42  # Link single doc

# Vacuum database (reclaim space)
$ emdx maintain vacuum
```

### Wiki Generation

```bash
# Full bootstrap (index → entities → topics → auto-label)
$ emdx maintain wiki setup

# Discover topics and auto-label them
$ emdx maintain wiki topics --save --auto-label

# Bulk skip low-coherence topics
$ emdx maintain wiki triage --skip-below 0.05

# LLM-label all unlabeled topics
$ emdx maintain wiki triage --auto-label

# Show generation progress + costs
$ emdx maintain wiki progress

# Generate articles (sequential)
$ emdx maintain wiki generate

# Generate with concurrency
$ emdx maintain wiki generate -c 3

# Export to MkDocs site
$ emdx maintain wiki export ./wiki-site

# Export single article
$ emdx maintain wiki export ./wiki-site --topic 42
```

---

## 🎛️ Common Patterns

### Multi-Step Task Workflow

```bash
# 1. Check what's ready
$ emdx task ready

# 2. Start working on a task
$ emdx task active 42

# 3. Create subtasks for visibility (3+ steps)
$ emdx task add "Read and understand code" --epic 42
$ emdx task add "Implement changes" --epic 42
$ emdx task add "Run tests" --epic 42

# 4. Mark subtasks done as you complete them
$ emdx task done 43

# 5. Complete main task when finished
$ emdx task done 42
```

### Research & Document Workflow

```bash
# 1. Check existing knowledge first
$ emdx find "topic" --recent

# 2. Research using Claude Code agents directly
# (use Explore or general-purpose subagents for parallel research)

# 3. Save findings
$ echo "research results" | emdx save --title "Topic Analysis" --tags "analysis"

# 4. Tag appropriately
$ emdx tag add 123 analysis done success
```

### Code Change Workflow

```bash
# 1. Create task
$ emdx task add "Fix bug X" --cat FIX -D "Details..."

# 2. Implement fix (use Claude Code agents for code changes and PRs)

# 3. Check status
$ emdx status

# 4. After PR merges, mark task done
$ emdx task done 42
```

### Bulk Operations

```bash
# Find and tag multiple docs
$ emdx find "authentication" --json | jq -r '.[].id' | \
  xargs -I {} emdx tag add {} security

# Archive completed tasks
$ emdx task ready --json | jq -r '.[] | select(.status=="done") | .id' | \
  xargs -I {} emdx task archive {}
```

---

## 🔌 Output Modes

Most commands support multiple output formats:

```bash
# Default: Rich formatted output (human-friendly)
$ emdx find "query"

# Plain text (machine/pipe friendly)
$ emdx find "query" --plain

# JSON (for scripting/automation)
$ emdx find "query" --json

# Rich with colors and markup
$ emdx find "query" --rich
```

---

## 🚫 What NOT to Do

```bash
# ❌ DON'T run the TUI from Claude Code (it hangs)
$ emdx gui

# ❌ DON'T use emdx save with text as argument
$ emdx save "some text"  # Looks for FILE named "some text"

# ✅ DO pipe text via stdin
$ echo "some text" | emdx save --title "Title"

# ❌ DON'T use OR/AND/NOT in find queries
$ emdx find "bug OR error"  # Doesn't work (terms get quoted)

# ✅ DO use separate queries or --tags with --any-tags
$ emdx find "bug"
$ emdx find "error"
$ emdx find --tags "bug,error" --any-tags

```

---

## 📚 More Info

- **Full CLI Reference:** `docs/cli-api.md`
- **Architecture:** `docs/architecture.md`
- **Development Setup:** `docs/development-setup.md`
- **Help:** `emdx --help` or `emdx <command> --help`
