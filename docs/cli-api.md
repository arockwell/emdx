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
- `--auto-link/--no-auto-link` - Auto-link to semantically similar documents (default: auto-link)
- `--cross-project` - Allow auto-links across projects
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

# Show only wiki articles
emdx find "authentication" --wiki

# Show all document types (user docs + wiki articles)
emdx find "auth" --all-types
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
- `--wiki` - Show only wiki articles (`doc_type='wiki'`)
- `--all-types` - Show all document types (user, wiki, etc.)

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

---

## 🧹 **Maintenance Commands**

### **emdx maintain**
System maintenance, cleanup, embedding index, and document linking.

#### **emdx maintain cleanup**
Clean up system resources used by delegate executions (branches, processes, stuck DB records).

```bash
# Show what cleanup would do (dry run)
emdx maintain cleanup --all

# Actually perform cleanup
emdx maintain cleanup --all --execute

# Clean old execution branches only
emdx maintain cleanup --branches --execute

# Force delete unmerged branches too
emdx maintain cleanup --branches --force --execute

# Kill zombie processes
emdx maintain cleanup --processes --execute

# Clean stuck execution records
emdx maintain cleanup --executions --execute

# Custom age threshold for branches (default: 7 days)
emdx maintain cleanup --branches --age 14 --execute
```

**Options:**
- `--branches, -b` - Clean up old execution branches
- `--processes, -p` - Clean up zombie processes
- `--executions, -e` - Clean up stuck execution records
- `--all, -a` - Clean up everything
- `--execute / --dry-run` - Execute actions (default: dry run)
- `--force, -f` - Force delete unmerged branches
- `--age INTEGER` - Only clean branches older than N days (default: 7)
- `--max-runtime INTEGER` - Max process runtime in hours before considering stuck (default: 2)
- `--timeout INTEGER` - Minutes after which to consider execution stale (default: 30)

#### **emdx maintain cleanup-dirs**
Clean up temporary execution directories in `/tmp`.

```bash
# Show what would be cleaned (dry run)
emdx maintain cleanup-dirs

# Actually clean directories
emdx maintain cleanup-dirs --execute

# Clean dirs older than 48 hours (default: 24)
emdx maintain cleanup-dirs --age 48 --execute
```

**Options:**
- `--execute / --dry-run` - Execute actions (default: dry run)
- `--age INTEGER` - Clean directories older than N hours (default: 24)

#### **emdx maintain analyze**
Read-only analysis of your knowledge base — discover patterns, issues, and improvement opportunities.

```bash
# Show health overview with recommendations
emdx maintain analyze

# Detailed health metrics
emdx maintain analyze --health

# Find duplicate documents
emdx maintain analyze --duplicates

# Find similar documents (candidates for merging)
emdx maintain analyze --similar

# Find empty documents
emdx maintain analyze --empty

# Analyze tag coverage and patterns
emdx maintain analyze --tags

# Show project-level analysis
emdx maintain analyze --projects

# Run all analyses
emdx maintain analyze --all

# Filter by project
emdx maintain analyze --project myapp

# Output as JSON
emdx maintain analyze --json
```

**Options:**
- `--health, -h` - Show detailed health metrics
- `--duplicates, -d` - Find duplicate documents
- `--similar, -s` - Find similar documents for merging
- `--empty, -e` - Find empty documents
- `--tags, -t` - Analyze tag coverage and patterns
- `--projects, -p` - Show project-level analysis
- `--all, -a` - Run all analyses
- `--project TEXT` - Filter by specific project
- `--json` - Output results as JSON

#### **emdx maintain wikify**
Create title-match links between documents (auto-wikification). Scans document content for mentions of other documents' titles and creates links. No AI or embeddings required.

```bash
# Wikify a single document
emdx maintain wikify 42

# Backfill all documents
emdx maintain wikify --all

# Preview matches without creating links
emdx maintain wikify 42 --dry-run
emdx maintain wikify --all --dry-run
```

**Options:**
- `--all` - Wikify all documents
- `--dry-run` - Show matches without creating links

#### **emdx maintain entities**
Extract entities (key concepts, technical terms, proper nouns) from markdown structure and cross-reference them across documents to create links. No AI required.

```bash
# Extract entities + create links for one document
emdx maintain entities 42

# Backfill all documents
emdx maintain entities --all

# Extract only, no cross-linking
emdx maintain entities 42 --no-wikify

# Clean noisy entities and re-extract with current filters
emdx maintain entities --cleanup

# Clear entity-match links before regenerating
emdx maintain entities --all --rebuild
```

**Options:**
- `--all` - Extract entities for all documents
- `--wikify / --no-wikify` - Also create entity-match links (default: wikify)
- `--rebuild` - Clear entity-match links before regenerating
- `--cleanup` - Remove noisy entities and re-extract with current filters

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

#### **emdx maintain wiki**
Auto-wiki generation system using Leiden community detection for topic clustering and AI for article generation.

**Subcommands:**

| Command | Description |
|---------|-------------|
| `setup` | Run the full wiki bootstrap sequence (index → entities → topics → auto-label) |
| `topics` | Discover topic clusters using Leiden community detection |
| `triage` | Bulk triage saved topics: skip low-coherence, auto-label via LLM |
| `progress` | Show wiki generation progress: topics generated vs pending, costs |
| `status` | Show wiki generation status and statistics |
| `generate` | Generate wiki articles from topic clusters |
| `entities` | Browse entity index pages |
| `list` | List generated wiki articles |
| `runs` | List recent wiki generation runs |
| `coverage` | Show which documents are NOT covered by any topic cluster |
| `diff` | Show unified diff between previous and current article content |
| `rate` | Rate a wiki article's quality (1-5 scale) |
| `export` | Export wiki articles as a MkDocs site |
| `rename` | Rename a wiki topic (label, slug, and associated document title) |
| `retitle` | Batch-update topic labels from article H1 headings |
| `skip` | Skip a topic during wiki generation |
| `unskip` | Reset a skipped topic back to active |
| `pin` | Pin a topic so it always regenerates during wiki generation |
| `unpin` | Reset a pinned topic back to active |
| `model` | Set or clear a per-topic model override for wiki generation |
| `prompt` | Set or clear an editorial prompt for a wiki topic |
| `merge` | Merge two wiki topics into one |
| `split` | Split a wiki topic by extracting docs that mention an entity |
| `sources` | List source documents for a wiki topic with weights and status |
| `weight` | Set relevance weight for a source document within a topic |
| `exclude` | Exclude a source document from a wiki topic's synthesis |
| `include` | Re-include a previously excluded source document in a topic |

```bash
# Full bootstrap: index → entities → topics → auto-label
emdx maintain wiki setup

# Discover topic clusters (defaults to heading + proper_noun entities)
emdx maintain wiki topics
emdx maintain wiki topics --save --auto-label    # Save with LLM-generated names
emdx maintain wiki topics -e heading -e concept  # Custom entity types
emdx maintain wiki topics --min-df 3             # Prune rare entities

# Bulk triage saved topics
emdx maintain wiki triage --skip-below 0.05              # Skip low coherence
emdx maintain wiki triage --auto-label                    # LLM-label all topics
emdx maintain wiki triage --skip-below 0.03 --auto-label  # Both
emdx maintain wiki triage --skip-below 0.05 --dry-run    # Preview only

# Show generation progress
emdx maintain wiki progress          # Rich output with progress bar
emdx maintain wiki progress --json   # Machine-readable

# Generate wiki articles
emdx maintain wiki generate                  # Sequential (default)
emdx maintain wiki generate -c 3             # 3 concurrent generations
emdx maintain wiki generate --all --dry-run  # Preview costs

# Export to MkDocs
emdx maintain wiki export ./wiki-site              # All articles
emdx maintain wiki export ./wiki-site --topic 42   # Single article
emdx maintain wiki export ./wiki-site --build      # Build static site
emdx maintain wiki export ./wiki-site --deploy     # Deploy to GitHub Pages

# Show wiki generation status
emdx maintain wiki status

# List generated wiki articles
emdx maintain wiki list

# Show which docs aren't covered by any topic
emdx maintain wiki coverage

# Show diff between previous and current article content
emdx maintain wiki diff

# Rate a wiki article (1-5 scale)
emdx maintain wiki rate

# Topic management
emdx maintain wiki rename    # Rename a topic
emdx maintain wiki retitle   # Batch-update labels from article H1s
emdx maintain wiki skip      # Skip topic during generation
emdx maintain wiki unskip    # Reset skipped topic
emdx maintain wiki pin       # Force regeneration
emdx maintain wiki unpin     # Reset pinned topic
emdx maintain wiki model     # Set per-topic model override
emdx maintain wiki prompt    # Set editorial prompt

# Topic splitting and merging
emdx maintain wiki merge     # Merge two topics into one
emdx maintain wiki split     # Split topic by entity

# Source document control
emdx maintain wiki sources   # List sources with weights
emdx maintain wiki weight    # Set source relevance weight
emdx maintain wiki exclude   # Exclude a source from synthesis
emdx maintain wiki include   # Re-include an excluded source

# Browse entity index pages
emdx maintain wiki entities

# List recent wiki generation runs
emdx maintain wiki runs
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

# Launch with a specific theme
emdx gui --theme emdx-dark
```

**TUI Key Bindings:**

*Global:*
- `1` - Switch to activity view (Docs)
- `2` - Switch to task browser
- `3` - Switch to delegate browser
- `\` - Cycle theme
- `Ctrl+t` - Toggle dark/light mode
- `Ctrl+k` / `Ctrl+p` - Command palette
- `q` - Quit

*Activity View:*
- `j/k` - Navigate up/down
- `Enter` - Open fullscreen preview
- `/` - Filter
- `r` - Refresh
- `?` - Help

*Task Browser:*
- `j/k` - Navigate up/down
- `/` - Live filter bar
- `Escape` - Clear filter
- `g` - Toggle epic grouping
- `o` - Filter: open tasks
- `i` - Filter: active tasks
- `x` - Filter: blocked tasks
- `f` - Filter: done/failed/wontdo
- `*` - Show all (clear status filter)
- `d` - Mark done
- `a` - Mark active
- `w` - Mark won't do
- `r` - Refresh
- `?` - Help

*Delegate Browser:*
- `j/k` - Navigate up/down
- `z` - Zoom detail pane
- `r` - Refresh
- Click PR links to open in browser
- Click output doc links to navigate to document

## 🔗 **Integration Commands**

### **emdx gist**
Create or update a GitHub Gist from a document.

```bash
# Create secret gist from document (default)
emdx gist 42

# Create public gist
emdx gist 42 --public

# Create gist with description
emdx gist 42 --desc "Auth module analysis"

# Create gist and copy URL to clipboard
emdx gist 42 --copy

# Create gist and open in browser
emdx gist 42 --open

# Update an existing gist
emdx gist 42 --update abc123def456
```

**Options:**
- `--public` - Create public gist
- `--secret` - Create secret gist (default)
- `--desc, -d TEXT` - Gist description
- `--copy, -c` - Copy gist URL to clipboard
- `--open, -o` - Open gist in browser
- `--update, -u TEXT` - Update existing gist ID

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

**Always available commands:**
- `save`, `find`, `view`, `edit`, `delete` - Document management
- `tag` (add, remove, list, rename, merge, batch) - Tag management
- `briefing` - Activity summary
- `gui`, `prime`, `status` - Interface and overview
- `maintain` (cleanup, compact, index, link, unlink, wikify, entities, analyze, wiki, stale) - Maintenance
- `gist` - GitHub Gist integration
- `explore` - Topic map and coverage analysis
- `exec` - Execution monitoring (read-only)
- `task` (including `task epic`, `task cat`, `task dep`, `task chain`, `task note`), `trash` - Organization commands

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

### Task Association

Link a delegate execution to an existing task ID. This sets `EMDX_TASK_ID` so hooks can track the task lifecycle automatically.

```bash
# Associate with an existing task
emdx delegate --task 42 "implement the feature"

# Combine with other options
emdx delegate --task 42 --pr "fix the bug from this task"
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
| `--task` | | Existing task ID to associate with this delegate (sets `EMDX_TASK_ID`) |
| `--pr` | | Instruct agent to create a PR (implies `--worktree`) |
| `--branch` | | Commit and push to origin branch (implies `--worktree`, no PR) |
| `--draft` / `--no-draft` | | Create PR as draft (default: `--no-draft`) |
| `--worktree` | `-w` | Run in isolated git worktree |
| `--base-branch` | `-b` | Base branch for worktree (default: main) |
| `--epic` | `-e` | Epic task ID to add tasks to |
| `--cat` | `-c` | Category key for auto-numbered tasks |
| `--tool` | | Extra allowed tool patterns (repeatable, e.g. `--tool 'Bash(gh:*)'`) |
| `--cleanup` | | Remove stale delegate worktrees (>1 hour old) |
| `--json` | | Structured JSON output (implies `--quiet`) |

### JSON Output

Use `--json` for structured, machine-readable output. Metadata on stderr is suppressed (same as `--quiet`).

```bash
# Single task with JSON output
emdx delegate --json "analyze code"
```

**Single task output:**
```json
{
  "task_id": 42,
  "doc_id": 1234,
  "output_doc_id": 1235,
  "execution_id": 87,
  "exit_code": 0,
  "success": true,
  "duration_seconds": 34.52,
  "duration": "34s"
}
```

Fields `pr_url`, `branch_name`, and `error` are included when applicable (e.g., `--pr` adds `pr_url`).

**Parallel task output:**
```json
{
  "parent_task_id": 50,
  "task_count": 3,
  "succeeded": 3,
  "failed": 0,
  "doc_ids": [1234, 1235, 1236],
  "tasks": [
    {"index": 0, "task_id": 51, "doc_id": 1234, "exit_code": 0, "success": true, "duration_seconds": 28.1, "duration": "28s"},
    {"index": 1, "task_id": 52, "doc_id": 1235, "exit_code": 0, "success": true, "duration_seconds": 31.4, "duration": "31s"},
    {"index": 2, "task_id": 53, "doc_id": 1236, "exit_code": 0, "success": true, "duration_seconds": 25.7, "duration": "25s"}
  ],
  "total_duration_seconds": 31.4,
  "total_duration": "31s"
}
```

When `--synthesize` is used, a `synthesis` object is added with the same fields as a single task result.

### Output Format

- **stdout**: Full content of the result (for reading inline)
- **stderr**: `doc_id:XXXX tokens:N cost:$X.XX duration:Xs`

---

## 📋 Task Management (`emdx task`)

Agent work queue for tracking tasks with status, epics, and categories.

### Display IDs

Tasks assigned to a category show a `KEY-N` display ID (e.g. `FEAT-12`, `SEC-3`) instead of the raw `#id`. This ID is auto-assigned when a task is added with `--cat` and appears throughout command output. You can use either format to reference tasks:

```bash
emdx task view FEAT-12      # By display ID
emdx task view 42           # By raw ID
emdx task done SEC-3        # Display IDs work with all commands
```

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

# List by status or category
emdx task list --done
emdx task list --cat FEAT

# Filter completed tasks by date
emdx task list --done --today
emdx task list --done --since 2026-02-15
```

### Updating Task Status

```bash
# Mark task as in-progress
emdx task active 1

# Mark task as done
emdx task done 1

# Mark task as blocked
emdx task blocked 1

# Mark task as won't do (closed without completing)
emdx task wontdo 42
emdx task wontdo TOOL-12
emdx task wontdo 42 --note "Superseded by #55"
```

**`wontdo` Options:**
- `--note, -n TEXT` - Reason for closing (logged to task work log)
- `--json` - Output as JSON

### Setting Priority

```bash
# Show current priority
emdx task priority 42

# Set to highest priority (1=highest, 5=lowest)
emdx task priority 42 1

# Set priority using KEY-N display ID
emdx task priority FEAT-5 2
```

**Options:**
- `--json` - Output as JSON

### Work Log

```bash
# View task work log
emdx task log 1

# Add entry to task log
emdx task log 1 "Started implementation"
```

### Progress Notes

Log a progress note on a task without changing its status. Shorthand for `emdx task log <id> "message"`.

```bash
emdx task note 42 "Root cause is in auth middleware"
emdx task note TOOL-12 "Tried approach X, didn't work — switching to Y"
```

### Dependencies (`emdx task dep`)

Manage task dependencies to control execution order. A task with unresolved dependencies is considered blocked and won't appear in `emdx task ready`.

#### **emdx task dep add**

```bash
# Task 5 depends on task 3 (task 5 is blocked until task 3 is done)
emdx task dep add 5 3

# Works with display IDs
emdx task dep add FEAT-5 3
```

#### **emdx task dep rm**

```bash
# Remove a dependency
emdx task dep rm 5 3
emdx task dep rm FEAT-5 3
```

#### **emdx task dep list**

```bash
# Show what a task depends on and what depends on it
emdx task dep list 5
emdx task dep list FEAT-5

# Output as JSON
emdx task dep list 5 --json
```

**Options:**
- `--json` - Output as JSON

### Dependency Chain (`emdx task chain`)

Show the full dependency chain for a task. Traces upward through blockers and downward through dependents to show the complete dependency graph.

```bash
emdx task chain 5
emdx task chain FEAT-5

# Output as JSON
emdx task chain 5 --json
```

**Options:**
- `--json` - Output as JSON

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
| `wontdo` | ⊘ | Closed without completing (terminal, unblocks dependents) |

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

# Rename/merge a category
emdx task cat rename SEC SECURITY          # Rename SEC → SECURITY
emdx task cat rename OLD NEW               # Merge OLD into NEW (if NEW exists)

# Delete a category (unlinks tasks)
emdx task cat delete SEC
```

---

## 🔭 Explore (`emdx explore`)

Explore what your knowledge base knows. Clusters documents by content similarity to build a topic map, showing what areas your KB covers and how deep the coverage is.

Topic map generation is free (no API calls). Question generation uses the Claude API.

### Topic Map

```bash
# Show all topics (free, no API calls)
emdx explore

# Tighter clusters (higher threshold = fewer, more focused topics)
emdx explore --threshold 0.5

# Show coverage gaps (thin topics, stale areas, lonely tags)
emdx explore --gaps
```

### Question Generation

```bash
# What questions can my KB answer? (uses Claude API)
emdx explore --questions

# Limit to top N topics
emdx explore --limit 5 --questions
```

### Machine Output

```bash
# Full JSON output
emdx explore --json

# JSON with questions
emdx explore --json --questions
```

**Options:**
- `--threshold, -t FLOAT` - Similarity threshold for clustering (0.0-1.0, lower = more grouping, default: 0.5)
- `--questions, -q` - Generate answerable questions per topic (uses Claude API)
- `--gaps, -g` - Detect coverage gaps (thin topics, stale areas, lonely tags)
- `--json` - Output results as JSON
- `--rich` - Enable colored Rich output
- `--limit, -n INTEGER` - Max topics to show (0 = all, default: 0)

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

## ⏳ Staleness Tracking (`emdx maintain stale`)

Track knowledge decay and identify documents needing review.

```bash
# Show stale documents prioritized by urgency
emdx maintain stale list
```

### **emdx maintain stale touch**

Reset a document's staleness timer without incrementing the view count.

```bash
# Touch single document
emdx maintain stale touch 42

# Touch multiple documents
emdx maintain stale touch 42 43 44
```
