# EMDX CLI API Reference

## 📋 **Command Overview**

EMDX provides a comprehensive CLI for knowledge base management, execution tracking, and system maintenance.

```bash
emdx [OPTIONS] COMMAND [ARGS]...
```

## 📚 **Document Management**

### **emdx save**
Save content to the knowledge base. Content sources in priority order: stdin > `--file` > positional argument.

```bash
# Save inline content (positional arg is always content, never a file path)
emdx save "Quick note about the auth module"

# Save from file (explicit --file flag)
emdx save --file document.md
emdx save --file document.md --title "Custom Title"

# Save from stdin
echo "Content here" | emdx save --title "My Note"

# Save with tags
echo "Gameplan content" | emdx save --title "Auth Gameplan" --tags "gameplan,active"

# Save from command output
ls -la | emdx save --title "Directory Listing"

# Save and auto-link to related documents
emdx save --file notes.md --auto-link

```

**Options:**
- `--file, -f TEXT` - Read content from a file path
- `--title, -t TEXT` - Custom title (auto-detected from filename if not provided)
- `--tags TEXT` - Comma-separated tags
- `--project, -p TEXT` - Override project detection
- `--group, -g INTEGER` - Add document to group
- `--group-role TEXT` - Role in group (primary, exploration, synthesis, variant, member)
- `--auto-link` - Auto-link to semantically similar documents (requires `emdx maintain index`)
- `--auto-tag` - Automatically apply suggested tags
- `--suggest-tags` - Show tag suggestions after saving
- `--supersede` - Auto-link to existing doc with same title
- `--task INTEGER` - Link saved document to a task as its output
- `--done` - Also mark the linked task as done (requires `--task`)

### **emdx find**
Search documents with hybrid (default when index exists), keyword, or semantic search. Also supports listing, similar-doc lookup, RAG Q&A, and context retrieval.

```bash
# Full-text search (keyword mode)
emdx find "docker compose"
emdx find "kubernetes deployment"

# Tag-based search
emdx find --tags "gameplan,active"      # Active gameplans
emdx find --tags "bug,urgent"           # Urgent bugs
emdx find --tags "feature,done"         # Completed features

# Combined search
emdx find "authentication" --tags "gameplan"

# Project-scoped search
emdx find "config" --project "emdx"

# Hybrid search (combines keyword + semantic)
emdx find "how to handle errors" --mode hybrid

# Semantic search (meaning-based, requires embeddings)
emdx find "authentication patterns" --mode semantic

# Force keyword-only search
emdx find "docker" --mode keyword

# Show matching chunk text instead of document snippets
emdx find "error handling" --mode hybrid --extract

# Exclude documents with specific tags
emdx find "api" --no-tags "archived,draft"

# Output as JSON
emdx find "config" --json

# Show snippet previews (default behavior, explicit)
emdx find "database" --snippets

# List all documents (replaces old `emdx list` command)
emdx find --all
emdx find --all --project "emdx"

# Show recently accessed documents (replaces old `emdx recent` command)
emdx find --recent 10

# Find similar documents (replaces old `emdx ai similar` command)
emdx find --similar 42

# RAG Q&A: retrieve context + LLM answer (replaces old `emdx ai ask`)
emdx find --ask "What's our caching strategy?"

# Context retrieval for piping to claude (replaces old `emdx ai context`)
emdx find --context "How does auth work?" | claude
```

**Options:**
- `--tags, -t TEXT` - Search by tags
- `--any-tags` - Match ANY tag instead of ALL tags
- `--no-tags TEXT` - Exclude documents with specified tags (comma-separated)
- `--project, -p TEXT` - Limit search to specific project
- `--limit, -n INTEGER` - Maximum results to return (default: 10)
- `--mode, -m [keyword|semantic|hybrid]` - Search mode (hybrid default when index exists)
- `--extract, -e` - Show matching chunk text instead of document snippets
- `--snippets, -s` - Show snippet previews in results
- `--fuzzy, -f` - Use fuzzy search
- `--ids-only` - Output only document IDs (for piping)
- `--created-after TEXT` - Filter by creation date (YYYY-MM-DD)
- `--created-before TEXT` - Filter by creation date (YYYY-MM-DD)
- `--modified-after TEXT` - Filter by modification date (YYYY-MM-DD)
- `--modified-before TEXT` - Filter by modification date (YYYY-MM-DD)
- `--json, -j` - Output results as JSON
- `--all, -a` - List all documents (no search query needed)
- `--recent INTEGER` - Show N most recently accessed documents
- `--similar INTEGER` - Find documents similar to this doc ID
- `--ask` - Answer the query using RAG (retrieves context + LLM)
- `--context` - Output retrieved context as plain text (for piping to claude)

### **emdx view**
View document content.

```bash
# View by ID
emdx view 42

# View with rich formatting (colors, panel header)
emdx view 42 --rich

# View raw content (no formatting)
emdx view 42 --raw

# Output as JSON
emdx view 42 --json

# Disable pager (for piping)
emdx view 42 --no-pager

# Hide document header
emdx view 42 --no-header

# Show document's link graph (replaces old `emdx ai links`)
emdx view 42 --links
```

### **emdx edit**
Edit document in your default editor.

```bash
# Edit by ID
emdx edit 42

# Edit with specific editor
EDITOR=vim emdx edit 42
```

### **emdx delete**
Soft delete documents (moves to trash).

```bash
# Delete by ID
emdx delete 42

# Delete multiple documents
emdx delete 42 43 44
```

## 🏷️ **Tag Management**

### **emdx tag add**
Add tags to a document.

```bash
# Add tags
emdx tag add 42 gameplan active urgent

# Add tags with auto-tagging
emdx tag add 42 --auto

# Show tag suggestions
emdx tag add 42 --suggest
```

### **emdx tag remove**
Remove tags from documents.

```bash
# Remove specific tags
emdx tag remove 42 urgent active

# Remove multiple tags
emdx tag remove 42 old-tag another-tag
```

### **emdx tag list**
List all tags with usage statistics.

```bash
# Show all tags with counts
emdx tag list

# Sort by name
emdx tag list --sort name
```

### **emdx tag rename**
Rename tags globally across all documents.

```bash
# Rename a tag across all documents
emdx tag rename "old-tag" "gameplan" --force

# Standardize tag names
emdx tag rename "todo" "active" --force
```

### **emdx tag merge**
Merge multiple tags into a single target tag.

```bash
# Merge several tags into one
emdx tag merge "old-tag1" "old-tag2" --into "new-tag" --force

# Skip confirmation prompt
emdx tag merge "todo" "task" --into "active" --force
```

**Options:**
- `--into, -i TEXT` - Target tag to merge into (required)
- `--force, -f` - Skip confirmation

### **emdx tag batch**
Batch auto-tag multiple documents using content analysis.

```bash
# Dry run: preview what would be tagged (default)
emdx tag batch

# Actually apply auto-tags
emdx tag batch --execute

# Only process untagged documents (default)
emdx tag batch --untagged

# Process all documents including already-tagged
emdx tag batch --all

# Filter by project
emdx tag batch --project myapp --execute

# Custom confidence threshold and max tags
emdx tag batch --confidence 0.8 --max-tags 2 --execute

# Limit number of documents to process
emdx tag batch --limit 50 --execute
```

**Options:**
- `--untagged/--all` - Only process untagged documents (default: untagged only)
- `--project, -p TEXT` - Filter by project
- `--confidence, -c FLOAT` - Minimum confidence threshold (default: 0.7)
- `--max-tags, -m INTEGER` - Maximum tags per document (default: 3)
- `--dry-run/--execute` - Preview or execute tagging (default: dry run)
- `--limit, -l INTEGER` - Maximum documents to process

## ⚡ **Execution Management**

### **emdx delegate** (execution management)
Manage and monitor delegate executions.

#### **emdx delegate list**
List recent executions.

```bash
# Show recent executions
emdx delegate list

# Show more executions
emdx delegate list --limit 100
```

#### **emdx delegate show**
Show execution details with integrated log viewer.

```bash
# Show execution with auto-follow for running executions
emdx delegate show 42

# Show specific number of log lines
emdx delegate show 42 --lines 100

# Show full log file
emdx delegate show 42 --full

# Just logs, no metadata
emdx delegate logs 42

# Follow logs (alias for show -f)
emdx delegate tail 42
```

#### **emdx delegate logs**
Show only the logs for an execution (no metadata header).

```bash
# Show last 50 lines of logs
emdx delegate logs 42

# Follow log output
emdx delegate logs 42 --follow

# Show specific number of lines
emdx delegate logs 42 --lines 100
```

**Options:**
- `--follow, -f` - Follow log output
- `--lines, -n INTEGER` - Number of lines to show (default: 50)

#### **emdx delegate tail**
Follow the log of a running execution (alias for `delegate show -f`).

```bash
# Follow execution logs in real-time
emdx delegate tail 42
```

#### **emdx delegate running**
Show currently running executions.

```bash
# List all running executions
emdx delegate running
```

#### **emdx delegate health**
Show detailed health status of running executions.

```bash
# Health check with process details
emdx delegate health
```

#### **emdx delegate monitor**
Real-time monitoring of executions.

```bash
# Monitor with 5-second refresh
emdx delegate monitor

# Custom refresh interval
emdx delegate monitor --interval 10

# One-time check (no continuous monitoring)
emdx delegate monitor --no-follow
```

#### **emdx delegate kill**
Terminate running executions.

```bash
# Kill specific execution (use partial ID)
emdx delegate kill 42ab8f

# Show running executions to choose from
emdx delegate kill

# Kill ALL running executions (with confirmation)
emdx delegate killall
```

#### **emdx delegate stats**
Show execution statistics.

```bash
# Overall execution statistics
emdx delegate stats
```

## 📁 **Document Groups**

### **emdx group**
Organize documents into hierarchical groups for better organization.

#### **emdx group create**
Create a new document group.

```bash
# Create a simple group
emdx group create "My Research"

# Create a group with type and description
emdx group create "Q1 Planning" --type initiative --description "Q1 2025 planning docs"

# Create nested group (child of another group)
emdx group create "Sprint 1" --parent 42 --type round

# Create project-scoped group
emdx group create "API Docs" --project myapp --type batch
```

**Options:**
- `--type, -t TEXT` - Group type: `batch`, `initiative`, `round`, `session`, `custom` (default: batch)
- `--parent, -p INTEGER` - Parent group ID for nesting
- `--project TEXT` - Associated project name
- `--description, -d TEXT` - Group description

#### **emdx group add**
Add documents to a group.

```bash
# Add single document
emdx group add 1 42

# Add multiple documents
emdx group add 1 42 43 44

# Add with specific role
emdx group add 1 42 --role primary
emdx group add 1 43 44 --role exploration
```

**Options:**
- `--role, -r TEXT` - Role in group: `primary`, `exploration`, `synthesis`, `variant`, `member` (default: member)

#### **emdx group remove**
Remove documents from a group.

```bash
# Remove single document
emdx group remove 1 42

# Remove multiple documents
emdx group remove 1 42 43 44
```

#### **emdx group list**
List document groups.

```bash
# List all groups
emdx group list

# Show as tree structure
emdx group list --tree

# Filter by parent (top-level only)
emdx group list --parent -1

# Filter by project
emdx group list --project myapp

# Filter by type
emdx group list --type initiative

# Include deleted groups
emdx group list --all
```

**Options:**
- `--parent, -p INTEGER` - Filter by parent group ID (-1 for top-level)
- `--project TEXT` - Filter by project
- `--type, -t TEXT` - Filter by type
- `--tree` - Show as tree structure
- `--all, -a` - Include inactive (deleted) groups

#### **emdx group show**
Show detailed information about a group.

```bash
emdx group show 1
```

#### **emdx group edit**
Edit group properties.

```bash
# Rename group
emdx group edit 1 --name "New Name"

# Update description
emdx group edit 1 --description "Updated description"

# Change parent (move group)
emdx group edit 1 --parent 2

# Remove from parent (make top-level)
emdx group edit 1 --parent 0

# Change type
emdx group edit 1 --type initiative
```

**Options:**
- `--name, -n TEXT` - New name
- `--description, -d TEXT` - New description
- `--parent, -p INTEGER` - New parent group ID (0 to remove)
- `--type, -t TEXT` - New group type

#### **emdx group delete**
Delete a document group.

```bash
# Soft delete (can be restored)
emdx group delete 1

# Skip confirmation
emdx group delete 1 --force

# Permanent delete
emdx group delete 1 --hard
```

**Options:**
- `--force, -f` - Skip confirmation
- `--hard` - Permanently delete (not soft-delete)

---

## 📋 **Recipe System**

Recipes are reusable emdx documents tagged with `recipe` that contain instructions for Claude to follow via `emdx delegate`.

### **emdx recipe list**
List all recipes.

```bash
# List all recipes (documents tagged "recipe")
emdx recipe list
```

### **emdx recipe run**
Run a recipe by passing it to `emdx delegate`.

```bash
# Run by ID
emdx recipe run 42

# Run by title search
emdx recipe run "Deep Analysis"

# Run with extra arguments
emdx recipe run 42 -- "analyze auth module"

# Run with PR creation and worktree isolation
emdx recipe run 42 --pr --worktree
```

**Options:**
- `--quiet, -q` - Suppress metadata on stderr
- `--model, -m TEXT` - Model to use
- `--pr` - Instruct agent to create a PR
- `--worktree, -w` - Run in isolated git worktree

### **emdx recipe create**
Create a recipe from a markdown file.

```bash
# Save a file as a recipe (tags it with 📋)
emdx recipe create instructions.md

# With custom title
emdx recipe create instructions.md --title "Security Audit"
```

Equivalent to `emdx save <file> --tags "recipe"`.

---

## 🧹 **Maintenance Commands**

### **emdx maintain**
System maintenance, cleanup, embedding index, and document linking.

#### **emdx maintain cleanup**
```bash
# Show what cleanup would do (dry run)
emdx maintain cleanup

# Actually perform cleanup
emdx maintain cleanup --execute

# Clean up executions only
emdx maintain cleanup --executions --execute

# Clean up orphaned files
emdx maintain cleanup --files --execute

# Full system cleanup
emdx maintain cleanup --all --execute
```

#### **emdx maintain compact**
AI-powered document synthesis to reduce knowledge base sprawl (moved from top-level `compact`).

```bash
# Dry run: show clusters without synthesizing (no API calls)
emdx maintain compact --dry-run

# Automatically synthesize all discovered clusters
emdx maintain compact --auto

# Compact specific documents together
emdx maintain compact 42 43 44

# Filter to a specific topic
emdx maintain compact --topic "authentication"

# Adjust similarity threshold
emdx maintain compact --threshold 0.7

# Skip confirmation prompts
emdx maintain compact --yes
```

**Options:**
- `--dry-run, -n` - Show clusters without synthesizing
- `--auto` - Automatically synthesize all clusters
- `--threshold, -t FLOAT` - Similarity threshold (0.0-1.0, default: 0.5)
- `--topic TEXT` - Filter to documents matching this topic
- `--model, -m TEXT` - Model to use for synthesis
- `--yes, -y` - Skip confirmation prompts

#### **emdx maintain index**
Build and manage the embedding index (moved from `emdx ai index`).

```bash
# Build index for new documents only
emdx maintain index

# Force reindex everything
emdx maintain index --force

# Check index statistics
emdx maintain index --stats

# Clear all embeddings (requires reindexing)
emdx maintain index --clear
```

**Options:**
- `--force` - Reindex all documents
- `--batch-size INTEGER` - Batch size for indexing
- `--chunks` - Use chunk-level embeddings
- `--stats` - Show index statistics
- `--clear` - Clear all embeddings

#### **emdx maintain link**
Create semantic links between related documents (moved from `emdx ai link`).

```bash
# Create links for a specific document
emdx maintain link 42

# Backfill links for all indexed documents
emdx maintain link --all

# Adjust similarity threshold and max links
emdx maintain link 42 --threshold 0.6 --max 3
```

**Options:**
- `--all` - Backfill links for all indexed documents
- `--threshold, -t FLOAT` - Minimum similarity (0-1, default: 0.5)
- `--max, -m INTEGER` - Maximum links per document (default: 5)

#### **emdx maintain unlink**
Remove a link between two documents (moved from `emdx ai unlink`).

```bash
emdx maintain unlink 42 57
```

## 📊 **Information Commands**

### **emdx trash**
Manage deleted documents.

```bash
# Show deleted documents
emdx trash

# Restore document from trash
emdx trash restore 42

# Permanently delete all trash (careful!)
emdx trash purge --force
```

## 🎨 **Interactive Interface**

### **emdx gui**
Launch interactive TUI browser.

```bash
# Launch full TUI interface
emdx gui

# Note: This is the main interactive interface with:
# - Document browser (default view)
# - Log browser (press 'l')
# - Activity view (press 'a')
# - Task browser (press 't')
# - Vim-like navigation and editing
```

**TUI Key Bindings:**
- `j/k` - Navigate up/down
- `g/G` - Go to top/bottom
- `/` - Search
- `l` - Switch to log browser
- `a` - Switch to activity view
- `t` - Switch to task browser
- `q` - Return to document browser / quit
- `e` - Edit mode (full vim-like editing)
- `s` - Selection mode
- `r` - Refresh

## 🔗 **Integration Commands**

### **emdx gist**
GitHub Gist integration.

```bash
# Create secret gist from document
emdx gist 42

# Create public gist
emdx gist 42 --public

# Create gist and copy URL to clipboard
emdx gist 42 --copy
```

## ⚙️ **Configuration**

### **Environment Variables**
- `EMDX_DATABASE_URL` - Custom database connection URL
- `EMDX_SAFE_MODE` - Enable safe mode (see below)
- `GITHUB_TOKEN` - For Gist integration
- `EDITOR` - Default editor for `emdx edit`

### **Safe Mode**

Safe mode disables execution commands that can spawn external processes or make changes. This is useful for:
- Read-only access to the knowledge base
- Environments where external execution should be prevented
- Security-conscious deployments

**Enable safe mode:**

```bash
# Via environment variable
export EMDX_SAFE_MODE=1
emdx delegate "task"  # Will show: Command 'delegate' is disabled in safe mode.

# Or set per-command
EMDX_SAFE_MODE=1 emdx delegate "task"  # Will show disabled message
```

**Disabled commands in safe mode:**
- `delegate` - One-shot AI execution
- `recipe` - Recipe execution

**Always available commands:**
- `save`, `find`, `view`, `edit`, `delete` - Document management
- `tag` (add, remove, list, rename, merge, batch) - Tag management
- `briefing` - Activity summary
- `gui`, `prime`, `status` - Interface and overview
- `maintain` (cleanup, compact, index, link, unlink) - Maintenance
- `gist` - GitHub Gist integration
- `exec` - Execution monitoring (read-only)
- `group`, `task` (including `task epic`, `task cat`), `trash` - Organization commands
- `stale` (list, touch) - Staleness tracking

**Error message:**
When a disabled command is invoked, you'll see:
```
Command 'delegate' is disabled in safe mode. Set EMDX_SAFE_MODE=0 to enable.
```

### **Default Locations**
- **Database**: `~/.emdx/emdx.db`
- **Logs**: `~/.emdx/logs/`
- **Config**: `~/.emdx/config.json` (if used)

## 🎯 **Common Workflows**

### **Quick Note Capture**
```bash
# Save a quick thought
echo "Remember to update documentation" | emdx save --title "Todo: Docs"

# Save with tags
echo "Bug in auth system" | emdx save --title "Auth Bug" --tags "bug,urgent"
```

### **Research Documentation**
```bash
# Save research findings
emdx save --file research.md --tags "analysis,done"

# Find related research later
emdx find --tags "analysis"
```

### **Execution Monitoring**
```bash
# Start monitoring executions
emdx delegate monitor

# In another terminal, check specific execution
emdx delegate show 42 --follow

# Kill stuck executions
emdx delegate health  # Check what's unhealthy
emdx delegate kill <execution_id>
```

### **Project Management**
```bash
# Track project gameplan
echo "Phase 1: Setup infrastructure" | emdx save --title "Project Gameplan" --tags "gameplan,active"

# Mark phases complete
emdx tag add 123 done success
emdx tag remove 123 active

# Review project progress
emdx find --tags "gameplan" --project "myproject"
```

---

## 📡 Delegate — One-Shot AI Execution (`emdx delegate`)

`emdx delegate` is the **single command for all one-shot AI execution**. It handles single tasks, parallel execution, PR creation, worktree isolation, and document context — all in one command.

**The Execution Ladder:**
| Level | Command | Use When |
|-------|---------|----------|
| 1 | `emdx delegate` | All one-shot AI execution |

### Basic Usage

```bash
# Single task
emdx delegate "analyze the auth module"

# Multiple tasks in parallel
emdx delegate "task1" "task2" "task3"

# Parallel with synthesis
emdx delegate --synthesize "analyze" "review" "plan"

# Control concurrency
emdx delegate -j 3 "task1" "task2" "task3" "task4" "task5"

# Set a title
emdx delegate -T "Auth Analysis" "check login" "check logout"
```

### Document Context

Use a saved document as input context for tasks:

```bash
# Use doc as context with a task
emdx delegate --doc 42 "implement the plan described here"

# Execute a doc directly (no extra prompt needed)
emdx delegate --doc 42

# Doc context with multiple parallel tasks
emdx delegate --doc 42 "check for bugs" "review tests" "check docs"
```

### PR Creation

Instruct the agent to create a PR after making code changes. `--pr` automatically creates an isolated git worktree.

```bash
# Single task with PR (worktree created automatically)
emdx delegate --pr "fix the auth bug"

# From a document with PR
emdx delegate --doc 123 --pr "implement this plan"
```

### Worktree Isolation

Run tasks in an isolated git worktree for clean environments:

```bash
# Single task in worktree
emdx delegate --worktree "fix X"

# Worktree with PR (worktree kept for the PR branch)
emdx delegate --worktree --pr "fix X"

```

### Options Reference

| Option | Short | Description |
|--------|-------|-------------|
| `--tags` | `-t` | Tags to apply to outputs (comma-separated) |
| `--title` | `-T` | Title for output document(s) |
| `--synthesize` | `-s` | Combine parallel outputs with synthesis |
| `--jobs` | `-j` | Max parallel tasks (default: auto) |
| `--model` | `-m` | Override default model |
| `--sonnet` | | Shortcut for `--model sonnet` |
| `--opus` | | Shortcut for `--model opus` |
| `--quiet` | `-q` | Suppress metadata on stderr |
| `--doc` | `-d` | Document ID to use as input context |
| `--pr` | | Instruct agent to create a PR (implies `--worktree`) |
| `--branch` | | Commit and push to origin branch (implies `--worktree`, no PR) |
| `--draft` / `--no-draft` | | Create PR as draft (default: `--no-draft`) |
| `--worktree` | `-w` | Run in isolated git worktree |
| `--base-branch` | `-b` | Base branch for worktree (default: main) |
| `--epic` | `-e` | Epic task ID to add tasks to |
| `--cat` | `-c` | Category key for auto-numbered tasks |
| `--cleanup` | | Remove stale delegate worktrees (>1 hour old) |

### Output Format

- **stdout**: Full content of the result (for reading inline)
- **stderr**: `doc_id:XXXX tokens:N cost:$X.XX duration:Xs`

---

## 📋 Task Management (`emdx task`)

Agent work queue for tracking tasks with status, epics, and categories.

### Adding Tasks

```bash
# Add a basic task
emdx task add "Implement user authentication"

# Add with description
emdx task add "Refactor API" --description "Improve performance and add caching"

# Add linked to a document
emdx task add "Implement this plan" --doc 42

# Add to an epic
emdx task add "Setup database" --epic 510

# Add with category key
emdx task add "Fix auth bug" --cat SEC
```

**Options:**
- `--doc, -d INTEGER` - Link to document ID
- `--description, -D TEXT` - Task description
- `--epic, -e INTEGER` - Add to epic (task ID)
- `--cat, -c TEXT` - Category key (e.g. SEC)

### Finding Ready Tasks

```bash
# Show tasks ready to work on
emdx task ready
```

### Viewing Tasks

```bash
# View full task details
emdx task view 1
```

### Listing Tasks

```bash
# List all tasks
emdx task list
```

### Updating Task Status

```bash
# Mark task as in-progress
emdx task active 1

# Mark task as done
emdx task done 1

# Mark task as blocked
emdx task blocked 1
```

### Work Log

```bash
# View task work log
emdx task log 1

# Add entry to task log
emdx task log 1 "Started implementation"
```

### Deleting Tasks

```bash
# Delete a task
emdx task delete 1
```

### Deleting Categories and Epics

```bash
# Delete a category (unlinks tasks, doesn't delete them)
emdx task cat delete SEC

# Force delete even if open/active tasks exist
emdx task cat delete SEC --force

# Delete an epic (unlinks child tasks, doesn't delete them)
emdx task epic delete 510

# Force delete even if open/active children exist
emdx task epic delete 510 --force
```

### Task Statuses

| Status | Icon | Description |
|--------|------|-------------|
| `open` | ○ | Not yet started |
| `active` | ● | Currently being worked on |
| `blocked` | ⚠ | Waiting on dependencies or external factors |
| `done` | ✓ | Completed successfully |

---

## 🏔️ Epic Management (`emdx task epic`)

Organize tasks into epics for larger initiatives.

```bash
# Create an epic
emdx task epic create "Auth System Overhaul"

# List all epics with task counts
emdx task epic list

# View an epic and its tasks
emdx task epic view 510

# Mark epic as active
emdx task epic active 510

# Mark epic as done
emdx task epic done 510

# Delete an epic (unlinks child tasks)
emdx task epic delete 510
```

---

## 🏷️ Category Management (`emdx task cat`)

Manage task categories for auto-numbered task titles (e.g., SEC-1, SEC-2).

```bash
# Create a category
emdx task cat create SEC --description "Security tasks"

# List all categories with task counts
emdx task cat list

# Backfill existing tasks into the category system
emdx task cat adopt SEC

# Delete a category (unlinks tasks)
emdx task cat delete SEC
```

---

## 📰 Briefing (`emdx briefing`)

Show recent emdx activity summary. Use `--save` to generate and persist a session wrapup (replaces old `wrapup` command).

```bash
# Show activity from the last 24 hours (default)
emdx briefing

# Show activity since a specific time
emdx briefing --since "2 days ago"
emdx briefing --since 2026-02-14
emdx briefing --since yesterday

# Output as JSON for agent consumption
emdx briefing --json

# Generate session wrapup and save to KB (replaces old `emdx wrapup`)
emdx briefing --save
emdx briefing --save --hours 8
emdx briefing --save --model sonnet
```

---

## ⏳ Staleness Tracking (`emdx stale`)

Track knowledge decay and identify documents needing review.

```bash
# Show stale documents prioritized by urgency
emdx stale list
```

### **emdx stale touch**

Reset a document's staleness timer without incrementing the view count.

```bash
# Touch single document
emdx stale touch 42

# Touch multiple documents
emdx stale touch 42 43 44
```
