# EMDX - Knowledge Base CLI Tool

## ⚠️ CRITICAL BUG: Interactive Commands (2025-07-13)

**NEVER run these commands as they will hang Claude Code:**
- `emdx gui` - Interactive TUI browser
- `emdx tui` - Alternative TUI interface

**KNOWN BUG**: As of July 2025, Claude Code's deny rules are NOT working. Even with:
- Explicit deny patterns in settings.json
- PreToolUse hooks
- Multiple pattern formats

These commands STILL execute and hang the session. This is a critical bug in Claude Code's permission system.

**WORKAROUND**: Simply don't ask Claude to run these commands until the bug is fixed.

## ⚠️ CRITICAL: Destructive Operations

**ALWAYS use dry-run first for maintenance operations:**
- `emdx maintain --clean` - Shows what would be deleted
- `emdx maintain --clean --execute` - Actually deletes duplicates/empty docs
- `emdx maintain --merge` - Shows what would be merged
- `emdx maintain --merge --execute` - Actually merges documents

The `--execute` flag is required for ALL destructive operations in 0.7.0.

**Data Safety Best Practices:**
1. Always run without `--execute` first to preview changes
2. Review the dry-run output carefully
3. Use `--json` output to save a record of what will be changed
4. Consider backing up the database before major operations:
   ```bash
   cp ~/.config/emdx/knowledge.db ~/.config/emdx/knowledge.backup.db
   ```

## 🧪 Testing Features (2025-07-27)

Test these new features when working with EMDX:
- **Event-driven log streaming** - Real-time log updates without polling
- **Git diff browser** - Press 'd' in TUI to enter git diff browser mode
- **Worktree switching** - Press 'w' in git mode to switch worktrees interactively
- **Comprehensive docs** - New docs/ folder with detailed project documentation

## 📖 Project Overview

EMDX is a command-line knowledge base and documentation management system built in Python. It provides full-text search, tagging, project organization, and multiple interfaces for managing and accessing your knowledge base.

**For detailed information, see: [📚 Complete Documentation](docs/)**

### New in 0.7.0: Service Architecture
- **Unified Commands** (`emdx/commands/analyze.py`, `maintain.py`) - Consolidated analysis and maintenance
- **Service Layer** (`emdx/services/`) - Complex operations decoupled from commands
  - `auto_tagger.py` - Rule-based intelligent tagging with confidence scoring
  - `health_monitor.py` - 6 weighted health metrics and recommendations
  - `duplicate_finder.py` - Content-based duplicate detection algorithms
  - `maintenance.py` - Automated fix operations with dry-run support
- **Pipeline Support** - `--ids-only`, `--json` flags for Unix integration
- **Date Filtering** - `--created-after`, `--modified-before` for temporal queries

### Service Components (0.7.0+)
- **Auto Tagger** (`emdx/services/auto_tagger.py`) - AI-powered automatic document tagging
- **Health Monitor** (`emdx/services/health_monitor.py`) - Knowledge base health metrics and scoring
- **Document Merger** (`emdx/services/document_merger.py`) - Intelligent similar document merging
- **Duplicate Detector** (`emdx/services/duplicate_detector.py`) - Find and manage duplicate content
- **Lifecycle Tracker** (`emdx/services/lifecycle_tracker.py`) - Track document lifecycle stages
- **Garbage Collector** (`emdx/commands/gc.py`) - Database cleanup and optimization

### Consolidated Commands (0.7.0+)
- **Analyze Command** (`emdx/commands/analyze.py`) - Unified read-only analysis operations
- **Maintain Command** (`emdx/commands/maintain.py`) - Unified maintenance and fix operations
- **Lifecycle Command** (`emdx/commands/lifecycle.py`) - Document lifecycle management

### Key Features
- **Full-text search** with SQLite FTS5 and fuzzy matching
- **Emoji tag system** with intuitive text aliases (gameplan→🎯, active→🚀)
- **Tag-based organization** with flexible search (all/any tag modes)
- **Project detection** from git repositories
- **Multiple interfaces**: CLI commands, interactive TUI browser
- **GitHub Gist integration** for sharing
- **Neovim integration** for editing
- **Rich formatting** with syntax highlighting and markdown rendering
- **Auto-tagging** (NEW) - Pattern-based automatic tag suggestions
- **Health monitoring** (NEW) - Knowledge base quality metrics
- **Unix pipeline support** (NEW) - Composable operations with standard tools
- **Command consolidation** (NEW) - 15 commands → 3 focused commands

## 🏗️ Architecture Summary

**Core Technologies:**
- **Python 3.13+** (minimum requirement)
- **SQLite + FTS5** - Local database with full-text search
- **Textual TUI** - Modern terminal interface framework
- **Typer CLI** - Type-safe command-line interface

**Key Components:**
- `commands/` - CLI command implementations
- `database/` - SQLite operations and migrations  
- `ui/` - TUI components (Textual widgets)
- `services/` - Business logic (log streaming, file watching, etc.)
- `models/` - Data models and operations
- `utils/` - Shared utilities (git, emoji aliases, Claude integration)

**For complete architecture details, see: [🏗️ Architecture Guide](docs/architecture.md)**

## Command Migration Guide (0.6.x → 0.7.0)

### Command Consolidation
EMDX 0.7.0 consolidates multiple commands into focused, powerful commands:

| Old Command | New Command | Notes |
|------------|-------------|-------|
| `emdx health` | `emdx analyze --health` | Part of unified analysis |
| `emdx clean duplicates` | `emdx maintain --clean --execute` | Requires --execute |
| `emdx merge find` | `emdx analyze --similar` | Read-only analysis |
| `emdx gc` | `emdx maintain --gc --execute` | Part of maintenance |
| `emdx tag batch` | `emdx maintain --tags --execute` | Auto-tagging |

### Key Changes
1. **Dry-run by default**: `maintain` commands show what would happen unless you add `--execute`
2. **JSON everywhere**: Add `--json` to any analyze command for automation
3. **Pipeline support**: New `--ids-only` flag for Unix pipelines
4. **Date filtering**: `--created-after`, `--modified-before` for time-based queries

### Development Workflow Changes
- Use `emdx analyze --all` before making changes to understand the current state
- Always test with dry-run: `emdx maintain --auto` before `emdx maintain --auto --execute`
- Leverage JSON output for testing: `emdx analyze --health --json | jq '.overall_score'`

## 🔧 Development Setup

### Quick Setup
```bash
# Install with poetry (for development)
poetry install
poetry run emdx --help

# Or with pip in a virtual environment  
python3.13 -m venv venv
source venv/bin/activate
pip install -e .
emdx --help
```

### Important: Development vs Global Installation

In the EMDX project directory, always use `poetry run emdx` instead of the global `emdx` command:

```bash
# ✅ Correct (in project directory)
poetry run emdx save README.md
poetry run emdx find "search terms"

# ❌ May cause issues (global installation may be outdated)
emdx save README.md
```

**For complete setup guide, see: [⚙️ Development Setup](docs/development-setup.md)**

## 💡 Essential Commands

### Save Content (CRITICAL: Use stdin for text)
```bash
# Save files
poetry run emdx save document.md
poetry run emdx save file.md --title "Custom Title"

# Save text via stdin (CORRECT syntax)
echo "My document content" | poetry run emdx save --title "Doc"
echo "Remember to fix the API" | poetry run emdx save --title "API Note"

# ❌ WRONG: This looks for a file named "text content"
# poetry run emdx save "text content"
```

### Search and Browse
```bash
# Search content
poetry run emdx find "search terms"
poetry run emdx find --tags "gameplan,active"

# List and view
poetry run emdx list
poetry run emdx view 42
poetry run emdx recent
```

### Tag Management (using text aliases)
```bash
# Add tags using intuitive aliases (auto-converts to emojis)
poetry run emdx tag 42 gameplan active urgent
poetry run emdx tags  # List all tags
poetry run emdx legend  # View emoji legend and aliases
```

## 🎯 Claude Code Integration Workflow

### Auto-Tagging for Project Management

When working with EMDX through Claude Code, automatically apply tags based on content patterns:

**Document Types:**
- `gameplan` - Strategic plans → 🎯
- `analysis` - Investigation results → 🔍  
- `notes` - General notes → 📝

**Workflow Status:**
- `active` - Currently working on → 🚀
- `done` - Completed → ✅
- `blocked` - Stuck/waiting → 🚧

**Outcomes (Success Tracking):**
- `success` - Worked as intended → 🎉
- `failed` - Didn't work → ❌
- `partial` - Mixed results → ⚡

### Integration Guidelines

When Claude Code helps with EMDX:

1. **Suggest tags** during save operations based on content
2. **Ask permission** before applying tags: "I detected this looks like a gameplan, should I tag it as `gameplan, active`?"
3. **Update tags** when project status changes
4. **Generate progress reports** from tag analytics
5. **Use consistent workflows** for project tracking

### Example Workflow
```bash
# Create gameplan with Claude Code assistance
echo "Gameplan: Implement user authentication system" | poetry run emdx save --title "Auth Gameplan" --tags "gameplan,active"

# Update status as work progresses
poetry run emdx tag 123 blocked
poetry run emdx untag 123 active

# Mark complete with outcome
poetry run emdx tag 123 done success
poetry run emdx untag 123 blocked
```

## 📊 Key Features for Claude Integration

### Event-Driven Log Streaming (NEW!)
- **Real-time updates** without polling overhead
- **OS-level file watching** for reliable change detection
- **Clean resource management** with automatic cleanup
- **Cross-platform support** with fallback strategies

### Emoji Tag System
- **Text aliases** for easy typing (`gameplan` → 🎯, `active` → 🚀)
- **Visual organization** space-efficient in GUI
- **Flexible search** with all/any tag modes
- **Usage analytics** for optimization

### Git Integration
- **Auto-project detection** from git repositories
- **Diff browser** for visual change review
- **Worktree support** for managing multiple branches

## 🔍 Common Development Tasks

For detailed guides on these topics, see the comprehensive documentation:

- **Adding CLI Commands** → [Development Setup](docs/development-setup.md)
- **UI Development** → [UI Architecture](docs/ui-architecture.md)
- **Database Changes** → [Database Design](docs/database-design.md)
- **Testing Patterns** → [Development Setup](docs/development-setup.md)

## 🎯 Success Analytics

Track gameplan success rates with tag-based queries:
```bash
# Find successful plans
poetry run emdx find --tags "gameplan,success"

# Find failed plans  
poetry run emdx find --tags "gameplan,failed"

# Current active work
poetry run emdx find --tags "active"

# Blocked items needing attention
poetry run emdx find --tags "blocked"
```

This enables powerful project management and success tracking while keeping the tag system simple and space-efficient.

---

**Documentation Links:**
- [📚 Complete Documentation](docs/) - Full project guides
- [🏗️ Architecture](docs/architecture.md) - System design and code structure  
- [⚙️ Development Setup](docs/development-setup.md) - Contributing guide
- [📋 CLI Reference](docs/cli-api.md) - Complete command documentation