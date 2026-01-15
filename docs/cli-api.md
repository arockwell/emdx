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
```

**Options:**
- `--title TEXT` - Custom title (auto-detected from filename if not provided)
- `--tags TEXT` - Comma-separated tags using text aliases
- `--project TEXT` - Override project detection

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

# Add workflow tags
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

## ⚡ **Execution Management**

### **emdx exec**
Manage and monitor command executions.

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

## 🔄 **Workflow System**

Workflows are execution patterns that define HOW to process tasks. Tasks are provided at runtime.

### **emdx workflow list**
List available workflows.

```bash
# List all workflows
emdx workflow list

# Show workflow details
emdx workflow show parallel_analysis
```

### **emdx workflow run**
Run a workflow with tasks.

```bash
# Run with inline tasks (task-driven model)
emdx workflow run task_parallel \
  -t "Analyze authentication security" \
  -t "Review database queries" \
  -t "Check error handling"

# Run with document IDs as tasks
emdx workflow run task_parallel -t 5182 -t 5183

# Use a preset for saved configurations
emdx workflow run parallel_analysis --preset security_audit

# Control concurrency
emdx workflow run task_parallel -t "Task 1" -t "Task 2" -j 3  # max 3 concurrent

# Run in background
emdx workflow run task_parallel -t "Long task" --background

# Use worktree isolation (recommended for parallel)
emdx workflow run task_parallel -t "Task 1" -t "Task 2" --worktree
```

**Options:**
- `--task/-t TEXT` - Task to run (string or doc ID). Can be repeated.
- `--preset/-p TEXT` - Use saved preset for variables
- `--var/-v TEXT` - Override variables (key=value)
- `--max-concurrent/-j INTEGER` - Max parallel executions
- `--background/--foreground` - Run mode
- `--worktree/--no-worktree` - Git isolation

### **emdx workflow runs**
List workflow runs.

```bash
# List recent runs
emdx workflow runs

# Filter by status
emdx workflow runs --status running
emdx workflow runs --status completed

# Show run details
emdx workflow status 123
```

### **emdx workflow preset**
Manage workflow presets (saved configurations).

```bash
# List presets
emdx workflow presets

# Create a preset
emdx workflow preset create parallel_analysis security_audit \
  --var topic="Security Review"

# Use a preset
emdx workflow run parallel_analysis --preset security_audit
```


## 🔄 **Lifecycle Management**

### **emdx lifecycle**
Track and analyze document lifecycle patterns.

```bash
# Show lifecycle analysis for all documents
emdx lifecycle analyze

# Track specific document evolution
emdx lifecycle track 42

# Show lifecycle statistics
emdx lifecycle stats
```

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

## 📤 **Export Profiles**

### **emdx export-profile**
Manage export profiles for document transformation and sharing.

#### **emdx export-profile create**
Create a new export profile.

```bash
# Basic clipboard profile
emdx export-profile create simple-share

# Blog post with frontmatter
emdx export-profile create blog-post \
  --frontmatter --fm-fields title,date,tags \
  --dest file --path ~/blog/drafts/{{title}}.md

# GitHub issue format
emdx export-profile create github-issue \
  --strip-tags 🚧,🚨 \
  --tag-labels '{"🐛": "bug", "✨": "enhancement"}'

# Google Docs export
emdx export-profile create team-share \
  --format gdoc --dest gdoc \
  --display "Team Share"

# Gist export
emdx export-profile create quick-gist \
  --format gist --dest gist

# With header and footer templates
emdx export-profile create report \
  --header "# Report: {{title}}\nGenerated: {{date}}" \
  --footer "---\nEnd of report"

# Project-scoped profile
emdx export-profile create docs-export \
  --project myapp --desc "Export for documentation site"
```

**Options:**
- `--display, -D TEXT` - Human-readable name
- `--format, -f TEXT` - Output format: `markdown`, `gdoc`, `gist` (default: markdown)
- `--dest, -d TEXT` - Destination type: `clipboard`, `file`, `gdoc`, `gist` (default: clipboard)
- `--path TEXT` - File path (supports `{{title}}`, `{{date}}` variables)
- `--strip-tags TEXT` - Comma-separated emoji tags to strip
- `--frontmatter` - Add YAML frontmatter
- `--fm-fields TEXT` - Comma-separated frontmatter fields: `title`, `date`, `tags`, `author`
- `--header TEXT` - Header template (supports variables)
- `--footer TEXT` - Footer template
- `--tag-labels TEXT` - Tag to label mapping as JSON
- `--desc TEXT` - Profile description
- `--project, -p TEXT` - Project scope (default: global)

#### **emdx export-profile list**
List all export profiles.

```bash
# List all profiles
emdx export-profile list

# Filter by project
emdx export-profile list --project myapp

# Output as JSON
emdx export-profile list --format json

# Include inactive profiles
emdx export-profile list --all
```

**Options:**
- `--project, -p TEXT` - Filter by project
- `--format, -f TEXT` - Output format: `table`, `json` (default: table)
- `--all, -a` - Include inactive profiles

#### **emdx export-profile show**
Show details of an export profile.

```bash
emdx export-profile show blog-post
emdx export-profile show 5  # by ID
```

#### **emdx export-profile edit**
Edit an export profile in your editor.

```bash
emdx export-profile edit blog-post
```

Opens the profile configuration as JSON in your default editor.

#### **emdx export-profile delete**
Delete an export profile.

```bash
# Soft delete
emdx export-profile delete old-profile

# Skip confirmation
emdx export-profile delete old-profile --force

# Permanent delete
emdx export-profile delete old-profile --hard
```

**Options:**
- `--force, -f` - Skip confirmation
- `--hard` - Permanently delete (not just deactivate)

#### **emdx export-profile export-json**
Export a profile as JSON for sharing.

```bash
# Export to stdout
emdx export-profile export-json blog-post

# Save to file
emdx export-profile export-json blog-post > blog-post-profile.json
```

#### **emdx export-profile import-json**
Import a profile from a JSON file.

```bash
# Import profile
emdx export-profile import-json blog-post-profile.json

# Overwrite existing profile
emdx export-profile import-json blog-post-profile.json --overwrite
```

**Options:**
- `--overwrite` - Overwrite existing profile

#### **emdx export-profile history**
Show export history.

```bash
# Show recent exports
emdx export-profile history

# Show more history
emdx export-profile history --limit 50

# Filter by profile
emdx export-profile history --profile blog-post
```

**Options:**
- `--limit, -n INTEGER` - Number of records to show (default: 20)
- `--profile, -p TEXT` - Filter by profile name

---

### **emdx export**
Export documents using profiles.

#### **emdx export export**
Export a document using an export profile.

```bash
# Export to clipboard using profile
emdx export export 42 --profile blog-post

# Preview without exporting
emdx export export "My Notes" --profile github-issue --preview

# Override destination
emdx export export 42 --profile blog-post --dest clipboard

# Export to specific file
emdx export export 42 --profile share-external --dest file --path ~/export.md

# Dry run (show what would happen)
emdx export export 42 --profile blog-post --dry-run
```

**Options:**
- `--profile, -p TEXT` - Export profile name (required)
- `--dest, -d TEXT` - Override destination: `clipboard`, `file`, `gdoc`, `gist`
- `--path TEXT` - Override destination path (for file destination)
- `--preview` - Show transformed content without exporting
- `--dry-run` - Show what would happen without exporting

#### **emdx export quick**
Quick export using profile number.

```bash
# Use most-used profile (number 1)
emdx export quick 42

# Use second most-used profile
emdx export quick 42 -n 2

# Use third most-used profile
emdx export quick "My Document" -n 3
```

**Options:**
- `--n, -n INTEGER` - Profile number from list 1-9 (default: 1)

#### **emdx export list-profiles**
List profiles with their quick-export numbers.

```bash
emdx export list-profiles
```

Shows profiles sorted by usage, with numbers 1-9 for quick export.

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

# Detailed project breakdown
emdx project-stats

# Show all projects
emdx projects
```

### **emdx trash**
Manage deleted documents.

```bash
# Show deleted documents
emdx trash

# Restore document from trash
emdx restore 42

# Permanently delete (careful!)
emdx trash --permanent
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
# Create public gist from document
emdx gist create 42

# Create private gist
emdx gist create 42 --private

# List your gists
emdx gist list

# Import gist to knowledge base
emdx gist import <gist_id>
```

## ⚙️ **Configuration**

### **Environment Variables**
- `EMDX_DB_PATH` - Custom database location
- `GITHUB_TOKEN` - For Gist integration
- `EDITOR` - Default editor for `emdx edit`

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

This CLI provides powerful knowledge management with intuitive commands and comprehensive execution tracking, all optimized for developer workflows and productivity.