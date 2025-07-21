# emdx - Documentation Index Management System

[![Version](https://img.shields.io/badge/version-0.7.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

Transform your knowledge base from a passive store to an active assistant. EMDX is an intelligent documentation management system with auto-tagging, health monitoring, Unix pipeline integration, and a refined terminal interface.

## Features

### 🎯 Core Features
- 🚀 **Unified CLI**: Single `emdx` command with intuitive subcommands
- 🔍 **Full-Text Search**: SQLite FTS5-powered search with ranking and fuzzy matching
- 📝 **Flexible Input**: Save files, text, or piped input with one command
- 🎨 **Rich Terminal UI**: Beautiful tables, markdown rendering, and syntax highlighting
- 🔧 **Git Integration**: Automatically detects project names from Git repositories
- 💾 **SQLite Backend**: Zero-setup, portable, fast local storage
- 🏷️ **Emoji Tag System**: Organize with emoji tags + intuitive text aliases (gameplan→🎯, active→🚀)

### ✨ New in 0.7.0
- 🤖 **Intelligent Auto-Tagging**: Automatically organize documents with smart tag suggestions
- 🏥 **Health Monitoring**: Track knowledge base health with 6 weighted metrics
- 🚀 **Unix Pipeline Integration**: `--ids-only`, `--json`, date filtering for automation
- 🔄 **Command Consolidation**: 15 commands → 3 focused commands (analyze, maintain, lifecycle)
- 🎨 **Refined TUI**: Smart 66/34 layout with tags column and improved performance
- 🧹 **Automated Maintenance**: One-command cleanup with `emdx maintain --auto`

### 🖥️ Advanced UI Features
- **TUI Browser**: Split-panel layout with document details and tags column
- **Complete Vim Editor**: Full modal editing (NORMAL/INSERT/VISUAL modes) with line numbers
- **File Browser**: Yazi-inspired file navigation with real-time preview
- **Git Diff Browser**: Visual git diff viewer with worktree switching
- **Claude Execution**: Execute prompts directly from TUI with live streaming logs
- **GitHub Gist Integration**: Share your knowledge base entries as GitHub Gists

## Installation

### Prerequisites

- Python 3.9+
- textual (for interactive GUI - installed automatically)
- nvim (for seamless editing integration)

### Install from source

```bash
git clone https://github.com/arockwell/emdx.git
cd emdx
pip install -e .
```

### Development installation

```bash
git clone https://github.com/arockwell/emdx.git
cd emdx

# Install Just (task runner)
# macOS
brew install just
# Linux
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Install dependencies
poetry install

# Run development version
just dev

# See all available commands
just
```

### No database setup required!

emdx uses SQLite and stores your knowledge base at `~/.config/emdx/knowledge.db`. It's created automatically on first use.

## ⚠️ Migration Notice (0.6.x → 0.7.0)

**Major Changes:**
- Many commands consolidated into `analyze` and `maintain`
- `maintain` operations are **dry-run by default** (add `--execute` to apply)
- See [MIGRATION.md](MIGRATION.md) for detailed upgrade instructions
- Database is backward compatible - your data is safe!

## Quick Start

### 🆕 New in 0.7.0: Power User Features

```bash
# Auto-tag documents on save
emdx save README.md --auto-tag

# Check knowledge base health
emdx analyze --health

# Run automated maintenance (dry-run)
emdx maintain --auto
emdx maintain --auto --execute  # Actually apply fixes

# Unix pipeline integration
emdx find "docker" --ids-only | xargs -I {} emdx tag {} devops
emdx find --tags "bug" --created-after "1 week ago" --ids-only | wc -l

# JSON output for automation
emdx analyze --health --json | jq '.overall_score'
emdx find "api" --format json | jq '.[].title'
```

## 📃 Quick Reference Card

### Essential Daily Commands
```bash
# Save and organize
emdx save file.md --auto-tag              # Save with smart tagging
echo "note" | emdx save --title "Note"    # Save text via stdin

# Search and filter  
emdx find "query" --tags "active"         # Search with tag filter
emdx find --created-after "yesterday"     # Recent documents

# Browse and view
emdx gui                                  # Interactive TUI browser
emdx recent 10                            # Last 10 accessed docs
emdx view 123                             # View specific document

# Maintain your knowledge base
emdx analyze --health                     # Check knowledge base health
emdx maintain --auto                      # Preview all fixes
emdx maintain --auto --execute            # Apply all fixes
```

### Save content
```bash
# Save a markdown file
emdx save README.md

# Save text directly (use stdin for text)
echo "Remember to fix the API endpoint" | emdx save --title "API Note"

# Save from pipe
docker ps | emdx save --title "Running containers"

# Save from clipboard
pbpaste | emdx save --title "Code snippet"

# Save command output
ls -la | emdx save --title "Directory listing"

# With custom project
emdx save notes.md --title "Project Notes" --project "my-app"

# With tags (using text aliases - auto-converts to emojis!)
emdx save README.md --tags "docs,feature,done"
```

### Search documents
```bash
# Basic search
emdx find "python async"

# Search with snippets
emdx find "database" --snippets

# Search within a project
emdx find "todo" --project "my-app"

# Fuzzy search (typo-tolerant)
emdx find "datbase" --fuzzy

# Search by tags (using text aliases!)
emdx find --tags "gameplan,active"  # Documents with ALL tags
emdx find --tags "bug,urgent" --any-tags  # Documents with ANY tag

# Combine text and tag search
emdx find "async" --tags "python"
```

### View documents
```bash
# View by ID
emdx view 42

# View by title
emdx view "Project Notes"

# View raw markdown (no formatting)
emdx view 42 --raw
```

### Edit and delete documents
```bash
# Edit a document in your default editor
emdx edit 42
emdx edit "Project Notes"

# Delete a document (moves to trash)
emdx delete 42
emdx delete "Project Notes"

# Force delete without confirmation
emdx delete 42 --force

# Restore from trash
emdx restore 42

# Permanently delete from trash
emdx purge 42
```

### Emoji Tag System & Text Aliases

emdx uses a powerful emoji tag system with intuitive text aliases for easy typing:

```bash
# View emoji legend and all text aliases
emdx legend

# Use text aliases (auto-converts to emojis)
emdx save plan.md --tags "gameplan,active,urgent"  # → 🎯,🚀,🚨
emdx find --tags "bug,blocked"                     # → finds 🐛,🚧 tagged docs
emdx tag 42 feature test success                   # → adds ✨,🧪,🎉

# Mixed emoji/text usage works too
emdx find --tags "gameplan,🚀,bug"                 # Mix and match!

# Common text aliases:
# gameplan → 🎯, active → 🚀, done → ✅, bug → 🐛, urgent → 🚨
# docs → 📚, test → 🧪, feature → ✨, success → 🎉, refactor → 🔧
```

### Tag management
```bash
# Add tags to a document (using aliases)
emdx tag 42 gameplan active feature

# View tags for a document
emdx tag 42

# Remove tags from a document
emdx untag 42 feature

# List all tags with statistics
emdx tags
emdx tags --sort usage  # Sort by usage count
emdx tags --sort name   # Sort alphabetically

# View emoji legend (shows all emoji meanings and aliases)
emdx legend

# Rename a tag globally
emdx retag "old-tag" "new-tag"

# Merge multiple tags into one
emdx merge-tags old1 old2 --into newtag
```

### List documents
```bash
# List all documents
emdx list

# List from specific project
emdx list --project "my-app"

# Export as JSON
emdx list --format json

# Export as CSV
emdx list --format csv
```


### Share via GitHub Gists
```bash
# Create a secret gist (default)
emdx gist 42

# Create a public gist
emdx gist "Project Notes" --public

# Create gist with custom description
emdx gist 42 --desc "My project documentation"

# Create gist and copy URL to clipboard
emdx gist 42 --copy

# Create gist and open in browser
emdx gist 42 --open

# Update an existing gist
emdx gist 42 --update abc123def456

# List all created gists
emdx gist-list

# List gists for a specific project
emdx gist-list --project "my-app"
```

### Interactive browser
```bash
# Launch modern textual browser with seamless nvim integration
emdx gui
```

The GUI browser provides:
- **In-place vim editing**: Full vim modal editing directly in the preview pane
- **Modal interface**: True vim-style NORMAL/SEARCH modes  
- **Live search**: Real-time document filtering as you type
- **Rich markdown preview**: Clean document rendering with syntax highlighting
- **Mouse support**: Click and scroll support alongside keyboard navigation
- **Keyboard navigation**:
  - `j/k` - Move up/down through documents
  - `g/G` - Go to first/last document
  - `/` - Enter search mode
  - `e` - Edit document with vim keybindings (in-place)
  - `s` - Text selection mode
  - `d` - Delete document (modal confirmation)
  - `v` or `Enter` - View document in full-screen
  - `q` or `Esc` - Exit browser

### **🎯 Vim Editing Mode**

When you press `e` to edit a document, you enter a powerful vim-like editing experience:

#### **Vim Modes**
- **INSERT** mode (default) - Normal text editing, press `ESC` to enter NORMAL mode
- **NORMAL** mode - Vim commands and navigation, press `ESC` again to save and exit
- **VISUAL** mode - Character-wise selection (`v` from NORMAL mode)
- **VISUAL LINE** mode - Line-wise selection (`V` from NORMAL mode)

#### **Core Vim Commands**
```bash
# Navigation (NORMAL mode)
h/j/k/l         # Left/Down/Up/Right
w/b/e           # Word forward/backward/end
0/$             # Start/end of line
gg/G            # Start/end of document

# Mode switching
i/a/I/A/o/O     # Enter INSERT mode (various positions)
v/V             # Enter VISUAL/VISUAL LINE mode
ESC             # INSERT→NORMAL→EXIT edit mode

# Editing (NORMAL mode)
x               # Delete character
dd              # Delete line
yy              # Yank (copy) line
p/P             # Paste after/before cursor

# With repeat counts
3j              # Move down 3 lines
5w              # Move forward 5 words
2dd             # Delete 2 lines
```

#### **Smart Status Bar**
The status bar shows your current vim mode with color coding:
- 🟢 `-- INSERT --` (ready to type)
- 🔵 `-- NORMAL --` (command mode)
- 🟡 `-- VISUAL --` (selection mode)
- Shows pending commands and repeat counts

## Command Reference

### 🎯 Essential Commands
```bash
emdx save [input] [--title] [--tags] [--auto-tag]  # Save with optional auto-tagging
emdx find <query> [--tags] [--ids-only] [--json]   # Search with pipeline support
emdx gui                                           # Launch enhanced TUI browser
```

### 📊 Analysis & Maintenance (NEW in 0.7.0)
```bash
# Read-only analysis
emdx analyze [--health|--duplicates|--similar|--tags|--all] [--json]

# Maintenance operations (dry-run by default)
emdx maintain [--auto|--clean|--merge|--tags|--gc] [--execute]

# Interactive maintenance wizard
emdx maintain  # Guides you through recommended fixes
```

### 🏷️ Tag Management
```bash
emdx tag <id> [tags...] [--suggest]      # Add tags or get suggestions
emdx untag <id> <tags...>                # Remove tags
emdx tags [--format json]                # List all tags
emdx legend                              # View emoji meanings
emdx retag <old> <new>                   # Rename tag globally
emdx merge-tags <tags...> --into <tag>   # Merge multiple tags
```

### 📄 Core Document Commands
```bash
emdx view <id|title> [--raw]             # View document
emdx edit <id|title>                     # Edit document
emdx delete <id|title> [--force]         # Soft delete
emdx restore <id|title>                  # Restore from trash
emdx trash                               # List deleted documents
emdx purge <id|title>                    # Permanently delete
```

### 📊 Browse & Export Commands
```bash
emdx list [--format json|csv]            # List all documents
emdx recent [count]                      # Recently accessed
emdx stats [--json]                      # Knowledge base statistics
emdx project-stats                       # Detailed project breakdown
emdx projects                            # List all projects
```

### 🔄 Lifecycle Management
```bash
emdx lifecycle status                     # Show document lifecycles
emdx lifecycle transition <id> <stage>   # Change lifecycle stage
emdx lifecycle analyze                   # Success rate analysis
emdx lifecycle auto-detect               # Suggest transitions
```

### 🌐 GitHub Integration
```bash
emdx gist <id> [--public] [--copy]       # Create gist
emdx gist-list [--project]               # List created gists
```

### 🧠 Claude Integration
```bash
emdx claude execute <id>                  # Execute with Claude
emdx exec list                           # List executions
emdx exec show <id>                      # Show execution details
```

## Configuration

### Database Location

By default, emdx stores your knowledge base at `~/.config/emdx/knowledge.db`. This location is created automatically.

### Git Integration

emdx automatically detects the Git repository name when saving files. This helps organize documents by project without manual tagging.

### GitHub Authentication

To use the gist commands, you need GitHub authentication. emdx supports two methods:

1. **GitHub CLI (recommended)**: If you have `gh` installed and authenticated, emdx will use it automatically.
   ```bash
   gh auth login
   ```

2. **Personal Access Token**: Set the `GITHUB_TOKEN` environment variable:
   ```bash
   export GITHUB_TOKEN=your_github_token
   ```
   To create a token, visit https://github.com/settings/tokens/new and select the 'gist' scope.

## 🚀 Power User Features

### Unix Pipeline Integration
```bash
# Bulk operations with xargs
emdx find "TODO" --ids-only | xargs -I {} emdx tag {} urgent

# Count documents by criteria
emdx find --tags "bug,active" --ids-only | wc -l

# Export and process with jq
emdx analyze --health --json | jq '.metrics | to_entries[] | select(.value.score < 70)'

# Date-based filtering
emdx find --created-after "2025-01-01" --modified-before "today" --ids-only

# Exclude specific tags
emdx find --tags "gameplan" --no-tags "done,failed" --format json
```

### Automated Workflows
```bash
# Daily maintenance script
#!/bin/bash
emdx analyze --health
emdx maintain --auto --execute
emdx lifecycle --stale-days 90

# Cron job for health tracking
0 */6 * * * emdx analyze --health --json >> ~/emdx-health.jsonl
```

### Advanced Search
```bash
# Complex queries
emdx find "docker OR kubernetes" --tags "devops" --created-after "1 month ago"

# Export search results
emdx find "api" --format json | jq -r '.[] | "[\(.id)] \(.title)"'

# Find untagged recent documents
emdx find --created-after "1 week ago" --no-tags "*" --ids-only
```

## Architecture

### Technical Details

emdx uses SQLite with FTS5 (Full-Text Search 5) for powerful search capabilities:

- **Instant search** across all your documents
- **Ranked results** based on relevance (BM25 algorithm)
- **Stemming support** (search "running" finds "run", "runs")
- **Phrase search** with quotation marks
- **Portable database** - just one file you can backup or sync
- **Soft deletes** - Documents are moved to trash before permanent deletion
- **Tag system** - Flexible tagging with autocomplete and bulk operations
- **Database migrations** - Automatic schema updates when upgrading
- **Health metrics** - 6 weighted metrics track knowledge base quality
- **Auto-tagging** - Rule-based pattern matching with confidence scoring

### Project Structure

```
emdx/
├── __init__.py
├── main.py                    # Main CLI entry point using Typer
├── commands/                  # CLI command implementations
│   ├── __init__.py
│   ├── core.py               # Core commands (save, find, view, edit, delete)
│   ├── browse.py             # Browse and stats commands
│   ├── gist.py               # GitHub Gist integration
│   ├── tags.py               # Tag-related CLI commands
│   ├── analyze.py            # NEW: Unified analysis command
│   ├── maintain.py           # NEW: Unified maintenance command
│   ├── lifecycle.py          # Document lifecycle management
│   ├── executions.py         # Claude execution tracking
│   └── claude_execute.py     # Claude integration
├── services/                  # NEW: Service layer for complex operations
│   ├── __init__.py
│   ├── auto_tagger.py        # Intelligent auto-tagging engine
│   ├── health_monitor.py     # Health metrics and scoring
│   ├── duplicate_finder.py   # Duplicate detection algorithms
│   └── maintenance.py        # Automated maintenance operations
├── models/                   # Data models and business logic
│   ├── __init__.py
│   ├── documents.py          # Document model operations
│   └── tags.py               # Tag model operations
├── database/                 # Database layer
│   ├── __init__.py
│   ├── connection.py         # Database connection management
│   ├── documents.py          # Document database operations
│   ├── search.py             # Search functionality
│   └── migrations.py         # Database migration system
├── ui/                       # User interface components
│   ├── __init__.py
│   ├── formatting.py         # Tag display and formatting
│   ├── gui.py                # GUI wrapper
│   ├── textual_browser.py    # Interactive TUI browser
│   ├── nvim_wrapper.py       # Neovim integration
│   ├── markdown_config.py    # Markdown rendering
│   └── mdcat_renderer.py     # External mdcat integration
├── utils/                    # Shared utilities
│   ├── __init__.py
│   ├── git.py                # Git project detection utilities
│   └── emoji_aliases.py      # Emoji alias system
└── config/                   # Configuration management
    ├── __init__.py
    └── settings.py
```

## Data Management

### Backup

Your entire knowledge base is stored in a single SQLite file:
```bash
# Default location
~/.config/emdx/knowledge.db

# Backup
cp ~/.config/emdx/knowledge.db ~/backups/emdx-backup-$(date +%Y%m%d).db
```

### Export

```bash
# Export all documents as JSON
emdx list --format json > my-knowledge-base.json

# Export as CSV
emdx list --format csv > my-knowledge-base.csv

# Export specific project
emdx list --project "my-app" --format json > my-app-docs.json
```

## Troubleshooting

### Common Issues

**FZF not found error when using `emdx gui`**
```bash
# Install fzf
brew install fzf              # macOS
sudo apt-get install fzf      # Ubuntu/Debian
sudo dnf install fzf          # Fedora
```

**"No documents found" after installation**
- This is normal! Start by saving your first document:
  ```bash
  emdx save README.md
  ```

**Permission denied errors**
- Check that `~/.config/emdx/` is writable
- The directory is created automatically with user permissions

**Search not finding expected results**
- Use quotes for exact phrases: `emdx find "exact phrase"`
- Try fuzzy search for typos: `emdx find "datbase" --fuzzy`
- Check if the document exists: `emdx list`

**Editor not opening for `emdx edit`**
- Set your preferred editor: `export EDITOR=vim`
- Or specify directly: `EDITOR=nano emdx edit 42`

## Development

### Setting up for development

```bash
# Clone and install
git clone https://github.com/arockwell/emdx.git
cd emdx
pip install -e ".[dev]"

# Run code quality tools
black emdx/              # Format code
ruff check emdx/         # Lint
mypy emdx/               # Type checking
```

### Code Style

- Black formatting with 100 character line length
- Ruff linting with pycodestyle, pyflakes, and isort rules
- Type hints required (enforced by mypy)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Priorities

- [x] ~~Add tagging system~~ - **COMPLETED** with emoji tags + text aliases
- [x] ~~Implement search operators~~ - **COMPLETED** with tag search modes
- [x] ~~Add vim-like editing~~ - **COMPLETED** with full modal editing in TUI
- [x] ~~Auto-tagging system~~ - **COMPLETED** with rule-based pattern matching
- [x] ~~Health monitoring~~ - **COMPLETED** with 6 weighted metrics
- [x] ~~Unix pipeline support~~ - **COMPLETED** with --ids-only and --json
- [ ] Machine learning tag suggestions
- [ ] Cloud sync capabilities
- [ ] Team collaboration features
- [ ] Add comprehensive test suite
- [ ] Create web UI companion

## License

MIT License - see LICENSE file for details

## 📚 Documentation

- **[Quick Start](#quick-start)** - Get up and running quickly
- **[EXAMPLES.md](EXAMPLES.md)** - Real-world workflows and automation scripts
- **[MIGRATION.md](MIGRATION.md)** - Upgrade guide from 0.6.x to 0.7.0  
- **[AUTOMATION.md](AUTOMATION.md)** - Unix pipeline integration and automation
- **[MAINTENANCE.md](MAINTENANCE.md)** - Keep your knowledge base healthy
- **[COMMAND_MIGRATION_TABLE.md](COMMAND_MIGRATION_TABLE.md)** - Complete command mapping
- **[CLAUDE.md](CLAUDE.md)** - Technical architecture and development guide

