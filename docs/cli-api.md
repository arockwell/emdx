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