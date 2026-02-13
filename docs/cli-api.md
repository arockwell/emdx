# EMDX CLI API Reference

## 📋 **Command Overview**

EMDX provides a comprehensive CLI for knowledge base management, execution tracking, and system maintenance.

```bash
emdx [OPTIONS] COMMAND [ARGS]...
```

## 📚 **Document Management**

### **emdx save**
Save content to the knowledge base.

```bash
# Save file with auto-detected title
emdx save document.md

# Save with custom title
emdx save document.md --title "Custom Title"

# Save from stdin
echo "Content here" | emdx save --title "My Note"

# Save with tags using text aliases
echo "Gameplan content" | emdx save --title "Auth Gameplan" --tags "gameplan,active"

# Save from command output
ls -la | emdx save --title "Directory Listing"

# Save and create a secret gist
echo "Shareable notes" | emdx save --title "Notes" --gist

# Save and create a public gist, copy URL
emdx save notes.md --public --copy
```

**Options:**
- `--title TEXT` - Custom title (auto-detected from filename if not provided)
- `--tags TEXT` - Comma-separated tags using text aliases
- `--project TEXT` - Override project detection
- `--gist` / `--share` - Create a GitHub gist after saving
- `--secret` - Create a secret gist (default; implies `--gist`)
- `--public` - Create a public gist (implies `--gist`)
- `--copy, -c` - Copy gist URL to clipboard
- `--open, -o` - Open gist in browser

### **emdx find**
Search documents with full-text and tag-based search.

```bash
# Full-text search
emdx find "docker compose"
emdx find "kubernetes deployment"

# Tag-based search using text aliases
emdx find --tags "gameplan,active"      # Active gameplans
emdx find --tags "bug,urgent"           # Urgent bugs
emdx find --tags "feature,done"         # Completed features

# Combined search
emdx find "authentication" --tags "gameplan"

# Project-scoped search
emdx find "config" --project "emdx"
```

**Options:**
- `--tags TEXT` - Search by tags (using text aliases)
- `--project TEXT` - Limit search to specific project
- `--limit INTEGER` - Maximum results to return (default: 10)

### **emdx view**
View document content.

```bash
# View by ID
emdx view 42

# View with syntax highlighting
emdx view 42 --highlight

# View raw content (no formatting)
emdx view 42 --raw
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

### **emdx tag**
Manage document tags using intuitive text aliases.

```bash
# Add tags using text aliases (much easier than emojis!)
emdx tag 42 gameplan active urgent

# View current tags for document
emdx tag 42

# Add status tags
emdx tag 123 feature done success
```

### **emdx untag**
Remove tags from documents.

```bash
# Remove specific tags
emdx untag 42 urgent active

# Remove multiple tags
emdx untag 42 old-tag another-tag
```

### **emdx tags**
List all tags with usage statistics.

```bash
# Show all tags with counts
emdx tags

# Show only emoji tags (space-efficient)
emdx tags --emoji-only
```

### **emdx legend**
View emoji legend with text aliases (NEW!).

```bash
# Show complete emoji legend with text aliases
emdx legend

# This helps you remember that:
# gameplan = 🎯, active = 🚀, bug = 🐛, etc.
```

### **emdx retag**
Rename tags globally across all documents.

```bash
# Convert old word tags to emoji system
emdx retag "old-word-tag" "gameplan"

# Standardize tag names
emdx retag "todo" "active"
```

### **emdx merge-tags**
Merge multiple tags into a single target tag.

```bash
# Merge several tags into one
emdx merge-tags "old-tag1" "old-tag2" --into "new-tag"

# Skip confirmation prompt
emdx merge-tags "todo" "task" --into "active" --force
```

**Options:**
- `--into, -i TEXT` - Target tag to merge into (required)
- `--force, -f` - Skip confirmation

### **emdx batch**
Batch auto-tag multiple documents using content analysis.

```bash
# Dry run: preview what would be tagged (default)
emdx batch

# Actually apply auto-tags
emdx batch --execute

# Only process untagged documents (default)
emdx batch --untagged

# Process all documents including already-tagged
emdx batch --all

# Filter by project
emdx batch --project myapp --execute

# Custom confidence threshold and max tags
emdx batch --confidence 0.8 --max-tags 2 --execute

# Limit number of documents to process
emdx batch --limit 50 --execute
```

**Options:**
- `--untagged/--all` - Only process untagged documents (default: untagged only)
- `--project, -p TEXT` - Filter by project
- `--confidence, -c FLOAT` - Minimum confidence threshold (default: 0.7)
- `--max-tags, -m INTEGER` - Maximum tags per document (default: 3)
- `--dry-run/--execute` - Preview or execute tagging (default: dry run)
- `--limit, -l INTEGER` - Maximum documents to process

## ⚡ **Execution Management**

### **emdx exec**
Manage and monitor command executions.

#### **emdx exec \<doc_id\>**
Execute a document with Claude (shortcut for `emdx claude execute`).

```bash
# Execute document in background (default)
emdx exec 42

# Execute in foreground
emdx exec 42 --foreground

# Execute with specific tools
emdx exec 42 --tools "Read,Write,Bash"
```

**Options:**
- `--background/--foreground` - Run in background (default) or foreground
- `--tools, -t TEXT` - Comma-separated list of allowed tools

#### **emdx exec list**
List recent executions.

```bash
# Show recent executions
emdx exec list

# Show more executions
emdx exec list --limit 100
```

#### **emdx exec show**
Show execution details with integrated log viewer.

```bash
# Show execution with auto-follow for running executions
emdx exec show 42

# Show specific number of log lines
emdx exec show 42 --lines 100

# Show full log file
emdx exec show 42 --full

# Just logs, no metadata
emdx exec logs 42

# Follow logs (alias for show -f)
emdx exec tail 42
```

#### **emdx exec logs**
Show only the logs for an execution (no metadata header).

```bash
# Show last 50 lines of logs
emdx exec logs 42

# Follow log output
emdx exec logs 42 --follow

# Show specific number of lines
emdx exec logs 42 --lines 100
```

**Options:**
- `--follow, -f` - Follow log output
- `--lines, -n INTEGER` - Number of lines to show (default: 50)

#### **emdx exec tail**
Follow the log of a running execution (alias for `exec show -f`).

```bash
# Follow execution logs in real-time
emdx exec tail 42
```

#### **emdx exec running**
Show currently running executions.

```bash
# List all running executions
emdx exec running
```

#### **emdx exec health**
Show detailed health status of running executions.

```bash
# Health check with process details
emdx exec health
```

#### **emdx exec monitor**
Real-time monitoring of executions.

```bash
# Monitor with 5-second refresh
emdx exec monitor

# Custom refresh interval
emdx exec monitor --interval 10

# One-time check (no continuous monitoring)
emdx exec monitor --no-follow
```

#### **emdx exec kill**
Terminate running executions.

```bash
# Kill specific execution (use partial ID)
emdx exec kill 42ab8f

# Show running executions to choose from
emdx exec kill

# Kill ALL running executions (with confirmation)
emdx exec killall
```

#### **emdx exec stats**
Show execution statistics.

```bash
# Overall execution statistics
emdx exec stats
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
# List all recipes (documents tagged 📋)
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
System maintenance and cleanup operations.

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

### **emdx gc**
Garbage collection for unused data.

```bash
# Show what would be garbage collected
emdx gc

# Perform garbage collection
emdx gc --execute

# Aggressive cleanup (removes more data)
emdx gc --aggressive --execute
```

## 📊 **Information Commands**

### **emdx list**
List documents by project.

```bash
# List all documents grouped by project
emdx list

# List documents for specific project
emdx list --project "emdx"
```

### **emdx recent**
Show recently accessed documents.

```bash
# Show 10 most recent documents
emdx recent

# Show more recent documents
emdx recent 25
```

### **emdx stats**
Show knowledge base statistics.

```bash
# Overall statistics
emdx stats
```

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
# - File browser (press 'f')
# - Vim-like navigation and editing
```

**TUI Key Bindings:**
- `j/k` - Navigate up/down
- `g/G` - Go to top/bottom
- `/` - Search
- `l` - Switch to log browser
- `f` - Switch to file browser
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

**Tip:** Use `emdx save --gist` (or `--secret`/`--public`) to save and create a gist in one step:

```bash
echo "content" | emdx save --title "Share Me" --secret --copy
```

### **emdx gdoc**
Export documents to Google Docs.

#### **emdx gdoc-auth**
Authenticate with Google via interactive OAuth flow.

```bash
# Start Google OAuth authentication
emdx gdoc-auth
```

Opens a browser window for Google OAuth authentication. Requires OAuth credentials to be configured at the expected credentials file path.

#### **emdx gdoc-list**
List all Google Docs created from EMDX documents.

```bash
# List all exported Google Docs
emdx gdoc-list

# Filter by project
emdx gdoc-list --project myapp
```

**Options:**
- `--project TEXT` - Filter by project

## 🤖 **Claude Document Execution** (`emdx claude`)

Execute EMDX documents with Claude Code. The `emdx claude` subcommands provide direct document execution and environment management.

### **emdx claude check-env**
Check if the execution environment is properly configured.

```bash
# Basic environment check
emdx claude check-env

# Verbose mode with PATH details
emdx claude check-env --verbose
```

**Options:**
- `--verbose, -v` - Show detailed environment info

Checks for: Python version, Claude Code installation, Git, EMDX CLI, and PATH configuration.

### **emdx claude execute**
Execute a document with Claude Code.

```bash
# Execute in background with smart context-aware mode (default)
emdx claude execute 42

# Execute in background
emdx claude execute 42 --background

# Execute with specific tools
emdx claude execute 42 --tools "Read,Write,Bash"

# Disable smart context-aware execution
emdx claude execute 42 --no-smart

# Use an existing execution ID from the database
emdx claude execute 42 --exec-id 100
```

**Options:**
- `--background, -b` - Run in background
- `--tools, -t TEXT` - Comma-separated list of allowed tools
- `--smart/--no-smart` - Use smart context-aware execution (default: smart)
- `--exec-id INTEGER` - Use existing execution ID from database

---

## ⚙️ **Configuration**

### **Environment Variables**
- `EMDX_DB_PATH` - Custom database location
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
emdx cascade add "idea"  # Will show: Command 'cascade' is disabled in safe mode.

# Or set per-command
EMDX_SAFE_MODE=1 emdx delegate "task"  # Will show disabled message
```

**Disabled commands in safe mode:**
- `cascade` - Autonomous document transformation pipeline
- `delegate` - One-shot AI execution
- `recipe` - Recipe execution

**Always available commands:**
- `save`, `find`, `view`, `edit`, `delete` - Document management
- `tag`, `untag`, `tags`, `legend`, `retag` - Tag management
- `list`, `recent`, `stats` - Information commands
- `gui`, `prime`, `status` - Interface and overview
- `ai` (ask, search, context) - AI-powered features
- `export`, `export-profile` - Export functionality
- `exec` - Execution monitoring (read-only)
- `group`, `task`, `lifecycle` - Organization commands

**Error message:**
When a disabled command is invoked, you'll see:
```
Command 'cascade' is disabled in safe mode. Set EMDX_SAFE_MODE=0 to enable.
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

# Save with context tags
echo "Bug in auth system" | emdx save --title "Auth Bug" --tags "bug,urgent"
```

### **Research Documentation**
```bash
# Save research findings
emdx save research.md --tags "analysis,done"

# Find related research later
emdx find --tags "analysis"
```

### **Execution Monitoring**
```bash
# Start monitoring executions
emdx exec monitor

# In another terminal, check specific execution
emdx exec show 42 --follow

# Kill stuck executions
emdx exec health  # Check what's unhealthy
emdx exec kill <execution_id>
```

### **Project Management**
```bash
# Track project gameplan
echo "Phase 1: Setup infrastructure" | emdx save --title "Project Gameplan" --tags "gameplan,active"

# Mark phases complete
emdx tag 123 done success
emdx untag 123 active

# Review project progress
emdx find --tags "gameplan" --project "myproject"
```

---

## 📡 Delegate — One-Shot AI Execution (`emdx delegate`)

`emdx delegate` is the **single command for all one-shot AI execution**. It handles single tasks, parallel execution, sequential chains, PR creation, worktree isolation, and document context — all in one command.

**The Execution Ladder:**
| Level | Command | Use When |
|-------|---------|----------|
| 1 | `emdx delegate` | All one-shot AI execution |
| 2 | `emdx cascade` | Ideas → code through stages |

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

### Sequential Chains

Run tasks sequentially where each step receives the previous step's output:

```bash
# Three-step pipeline
emdx delegate --chain "analyze the auth module" "create an implementation plan" "implement the plan"

# Chain with PR creation (only last step creates PR)
emdx delegate --chain --pr "analyze the issue" "implement the fix"

# Chain with document context
emdx delegate --doc 42 --chain "analyze" "implement"
```

### PR Creation

Instruct the agent to create a PR after making code changes:

```bash
# Single task with PR
emdx delegate --pr "fix the auth bug"

# With worktree isolation (recommended for PRs)
emdx delegate --worktree --pr "fix the null pointer in auth"

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

# Chain in worktree (all steps share same worktree)
emdx delegate --worktree --chain "analyze" "fix" "test"
```

### Dynamic Discovery

Discover items at runtime via a shell command, then process each in parallel:

```bash
# Review all Python files
emdx delegate --each "fd -e py src/" --do "Review {{item}} for security issues"

# Process all feature branches
emdx delegate --each "git branch -r | grep feature" --do "Review branch {{item}}"

# Combine with explicit tasks
emdx delegate --each "fd -e py src/" --do "Check {{item}}" "Also review the README"
```

### Options Reference

| Option | Short | Description |
|--------|-------|-------------|
| `--tags` | `-t` | Tags to apply to outputs (comma-separated) |
| `--title` | `-T` | Title for output document(s) |
| `--synthesize` | `-s` | Combine parallel outputs with synthesis |
| `--jobs` | `-j` | Max parallel tasks (default: auto) |
| `--model` | `-m` | Override default model |
| `--quiet` | `-q` | Suppress metadata on stderr |
| `--doc` | `-d` | Document ID to use as input context |
| `--pr` | | Instruct agent to create a PR after code changes |
| `--worktree` | `-w` | Run in isolated git worktree |
| `--base-branch` | | Base branch for worktree (default: main) |
| `--chain` | | Run tasks sequentially, piping output forward |
| `--each` | | Shell command to discover items (one per line) |
| `--do` | | Template for each discovered item (use `{{item}}`) |

**Note:** `--chain` and `--synthesize` are mutually exclusive. `--each` requires `--do`.

### Output Format

- **stdout**: Full content of the result (for reading inline)
- **stderr**: `doc_id:XXXX tokens:N cost:$X.XX duration:Xs`

For chains: `doc_ids:101,102,103 chain_final:103`

---

## ✨ AI-Powered Knowledge Base

The `emdx ai` commands provide semantic search and Q&A capabilities over your knowledge base using embeddings and LLMs.

### Getting Started

```bash
# Build the embedding index (one-time, ~1-2 minutes)
emdx ai index

# Check index status
emdx ai stats
```

### Semantic Search

Find documents by meaning, not just keywords:

```bash
# Search for conceptually related documents
emdx ai search "authentication flow"
emdx ai search "error handling patterns" --limit 10

# Filter by project
emdx ai search "database optimization" --project myapp

# Adjust similarity threshold (0-1)
emdx ai search "caching strategy" --threshold 0.5
```

### Find Similar Documents

```bash
# Find documents similar to a given document
emdx ai similar 42
emdx ai similar 42 --limit 10
```

### Q&A with Claude API

Ask questions and get synthesized answers (requires `ANTHROPIC_API_KEY`):

```bash
# Ask questions about your knowledge base
emdx ai ask "What's our caching strategy?"
emdx ai ask "How did we solve the auth bug?" --project myapp

# Reference specific documents
emdx ai ask "What does ticket AUTH-123 involve?"

# Force keyword search (no embeddings)
emdx ai ask "recent changes" --keyword
```

### Context Retrieval (for Claude CLI)

Retrieve context and pipe to the `claude` CLI to use your Claude Max subscription instead of API:

```bash
# Basic usage - pipe to claude
emdx ai context "How does the cascade system work?" | claude

# With a specific prompt
emdx ai context "What are the tag conventions?" | claude "summarize briefly"

# Limit docs and filter by project
emdx ai context "error handling" --limit 5 --project emdx | claude

# Raw docs without question
emdx ai context "auth patterns" --no-question | claude "list the patterns"
```

### Index Management

```bash
# Build index for new documents only
emdx ai index

# Force reindex everything
emdx ai index --force

# Check index statistics
emdx ai stats

# Clear all embeddings (requires reindexing)
emdx ai clear --yes
```

### Commands Reference

| Command | Description | Needs API Key? |
|---------|-------------|----------------|
| `emdx ai index` | Build/update embedding index | No |
| `emdx ai search` | Semantic search | No |
| `emdx ai similar` | Find similar documents | No |
| `emdx ai stats` | Show index statistics | No |
| `emdx ai clear` | Clear embedding index | No |
| `emdx ai ask` | Q&A with Claude API | **Yes** |
| `emdx ai context` | Get context for piping | No |

### How It Works

1. **Indexing**: Documents are converted to 384-dimensional vectors using `all-MiniLM-L6-v2` (runs locally, no API cost)
2. **Search**: Queries are vectorized and compared using cosine similarity
3. **Fallback**: If embeddings aren't available, falls back to keyword search (FTS5)
4. **Q&A**: Top-N relevant docs are sent to Claude as context for answering

### Tips

- Run `emdx ai index` periodically to index new documents
- Use `emdx ai context | claude` to avoid API costs (uses Claude Max)
- Semantic search works best with natural language queries
- Lower threshold values (0.2-0.3) return more results but less relevant

---

## 🔍 Document Similarity (`emdx similar`)

Find related documents using TF-IDF content analysis and tag similarity.

### Find Similar by Document ID

```bash
# Find top 5 similar documents
emdx similar 42

# Find more results
emdx similar 42 --limit 10

# Only content similarity (ignore tags)
emdx similar 42 --content-only

# Only tag similarity (ignore content)
emdx similar 42 --tags-only

# Filter to same project
emdx similar 42 --same-project

# Lower similarity threshold (find more matches)
emdx similar 42 --threshold 0.05

# Output as JSON
emdx similar 42 --json
```

### Find Similar by Text

```bash
# Search by natural language
emdx similar-text "kubernetes deployment strategies"
emdx similar-text "how to configure docker compose" --limit 10

# Output as JSON
emdx similar-text "authentication patterns" --json
```

### Index Management

```bash
# Rebuild TF-IDF index (auto-built on first use)
emdx build-index

# Force rebuild even if cache exists
emdx build-index --force

# Show index statistics
emdx index-stats
emdx index-stats --json
```

### Options Reference

| Option | Short | Description |
|--------|-------|-------------|
| `--limit` | `-l` | Number of results (default: 5) |
| `--threshold` | `-t` | Minimum similarity score 0-1 (default: 0.1) |
| `--content-only` | `-c` | Only use content similarity |
| `--tags-only` | `-T` | Only use tag similarity |
| `--same-project` | `-p` | Only find similar docs in same project |
| `--json` | `-j` | Output as JSON |

---

## 📋 Task Management (`emdx task`)

Manage tasks with dependencies and execution tracking.

### Creating Tasks

```bash
# Create a basic task
emdx task create "Implement user authentication"

# Create with priority (1-5, lower is higher priority)
emdx task create "Fix critical bug" --priority 1

# Create with dependencies
emdx task create "Deploy to production" --depends "123,124"

# Create linked to a gameplan document
emdx task create "Setup database" --gameplan 456

# Create with description
emdx task create "Refactor API" --description "Improve performance and add caching"

# Create in specific project
emdx task create "Add tests" --project myapp
```

### Listing Tasks

```bash
# List all tasks
emdx task list

# Filter by status
emdx task list --status open
emdx task list --status active,blocked

# Filter by gameplan
emdx task list --gameplan 456

# Filter by project
emdx task list --project myapp

# Limit results
emdx task list --limit 20
```

### Viewing and Updating

```bash
# Show task details
emdx task show 1

# Update task status
emdx task update 1 --status active
emdx task update 1 --status done

# Update priority
emdx task update 1 --priority 2

# Add note to task log
emdx task update 1 --note "Made progress on this"

# Set current step (for resume)
emdx task update 1 --step "Implementing API endpoints"
```

### Task Dependencies

```bash
# Show current dependencies
emdx task depends 1

# Add dependency
emdx task depends 1 --on 2

# Remove dependency
emdx task depends 1 --remove 2
```

### Finding Ready Tasks

```bash
# Show tasks ready to work (open + dependencies satisfied)
emdx task ready

# Filter by gameplan
emdx task ready --gameplan 456

# Filter by project
emdx task ready --project myapp
```

### Running Tasks

```bash
# Run task with Claude (direct execution)
emdx task run 1

# Preview prompt without running
emdx task run 1 --dry-run

# Mark as manually completed
emdx task manual 1
emdx task manual 1 --note "Completed via separate PR"
```

### Marking Tasks as Manually Complete

```bash
# Mark task as manually completed
emdx task manual 1

# Mark with a note explaining how it was completed
emdx task manual 1 --note "Completed via separate PR"
```

**Options:**
- `--note, -n TEXT` - Completion note

### Task Execution History

```bash
# Show execution history for a task
emdx task executions 1
emdx task executions 1 --limit 20
```

### Log Management

```bash
# Add entry to task log
emdx task log 1 "Started implementation"
```

### Deleting Tasks

```bash
# Delete a task
emdx task delete 1

# Skip confirmation
emdx task delete 1 --force
```

### Task Statuses

| Status | Icon | Description |
|--------|------|-------------|
| `open` | ○ | Not yet started |
| `active` | ● | Currently being worked on |
| `blocked` | ⚠ | Waiting on dependencies or external factors |
| `done` | ✓ | Completed successfully |
| `failed` | ✗ | Could not be completed |

---

## 🌊 Cascade - Ideas to Code

The Cascade system transforms raw ideas through stages into working code with PRs.

### Stage Flow

| Stage | Description |
|-------|-------------|
| `idea` | Raw idea enters the cascade |
| `prompt` | Claude transforms idea into well-formed prompt |
| `analyzed` | Claude analyzes the prompt thoroughly |
| `planned` | Claude creates detailed implementation gameplan |
| `done` | Claude implements code and creates PR |

### Adding Ideas

```bash
# Add an idea to the cascade
emdx cascade add "Add dark mode toggle to settings"

# Add with custom title
emdx cascade add "Feature idea" --title "Dark Mode Implementation"

# Add and auto-run through stages
emdx cascade add "Add dark mode" --auto

# Auto-run and stop at specific stage
emdx cascade add "Add dark mode" --auto --stop planned

# Shortcuts for common patterns
emdx cascade add "Add dark mode" --analyze    # idea → analyzed
emdx cascade add "Add dark mode" --plan       # idea → planned

# Add at a specific starting stage
emdx cascade add "My gameplan content" --stage planned --auto
```

### Checking Status

```bash
# Show cascade status (documents at each stage)
emdx cascade status

# Show documents at specific stage
emdx cascade show idea
emdx cascade show analyzed --limit 20
```

### Processing Documents

```bash
# Process one document at a stage (sync - waits for completion)
emdx cascade process idea --sync
emdx cascade process prompt --sync
emdx cascade process analyzed --sync
emdx cascade process planned --sync  # Creates code and PR

# Process specific document
emdx cascade process analyzed --doc 123 --sync

# Dry run (show what would be processed)
emdx cascade process idea --dry-run
```

### Running Continuously

```bash
# Run cascade continuously (one stage at a time)
emdx cascade run

# Auto mode: process ideas end-to-end
emdx cascade run --auto

# Auto mode with stop stage
emdx cascade run --auto --stop planned

# Process one document then exit
emdx cascade run --once

# Custom check interval
emdx cascade run --interval 10
```

### Manual Operations

```bash
# Manually advance a document to next stage
emdx cascade advance 123

# Advance to specific stage
emdx cascade advance 123 --to done

# Remove from cascade (keeps document)
emdx cascade remove 123
```

### Synthesizing Documents

```bash
# Combine multiple documents at a stage into one
emdx cascade synthesize analyzed

# With custom title
emdx cascade synthesize analyzed --title "Combined Analysis"

# Keep source documents (don't advance to done)
emdx cascade synthesize analyzed --keep

# Output to different stage
emdx cascade synthesize analyzed --next planned
```

### Viewing Run History

```bash
# Show cascade run history
emdx cascade runs

# Filter by status
emdx cascade runs --status running
emdx cascade runs --status completed

# Show more runs
emdx cascade runs --limit 20
```

---

This CLI provides powerful knowledge management with intuitive commands and comprehensive execution tracking, all optimized for developer workflows and productivity.
