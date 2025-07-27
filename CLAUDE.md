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

## 🧪 Testing Features (2025-07-27)

Test these new features when working with EMDX:
- **Event-driven log streaming** - Real-time log updates without polling
- **Git diff browser** - Press 'd' in TUI to enter git diff browser mode
- **Worktree switching** - Press 'w' in git mode to switch worktrees interactively
- **Comprehensive docs** - New docs/ folder with detailed project documentation

## 📖 Project Overview

EMDX is a command-line knowledge base and documentation management system built in Python. It provides full-text search, tagging, project organization, and multiple interfaces for managing and accessing your knowledge base.

**For detailed information, see: [📚 Complete Documentation](docs/)**

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