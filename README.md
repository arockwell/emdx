# emdx - Intelligent Knowledge Assistant

[![Version](https://img.shields.io/badge/version-0.7.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

A powerful command-line knowledge management system with AI-powered analysis, automated maintenance, Unix pipeline integration, and a modern terminal interface. Transform your documentation workflow with intelligent organization, health monitoring, and lifecycle tracking.

## Features

### Core Capabilities
- 🚀 **Unified CLI**: Single `emdx` command with intuitive subcommands
- 🔍 **Advanced Search**: Full-text search with date filtering, tag combinations, and fuzzy matching
- 📝 **Flexible Input**: Save files, text, or piped input with automatic project detection
- 🎨 **Rich Terminal UI**: Split-panel browser with vim editing, file navigation, and git diffs
- 💾 **SQLite Backend**: Zero-setup, portable database with FTS5 full-text search

### Intelligence & Automation (New in 0.7.0)
- 🤖 **Auto-Tagging**: AI-powered content analysis for automatic tag suggestions
- 📊 **Health Monitoring**: Knowledge base health scoring with actionable recommendations
- 🔧 **Smart Maintenance**: Automated duplicate detection, document merging, and cleanup
- 📈 **Lifecycle Tracking**: Gameplan progression tracking with success analytics
- 🔄 **Unix Pipeline Integration**: JSON output for seamless tool integration

### Organization & Workflow
- 🏷️ **Emoji Tag System**: Visual tags with text aliases (gameplan→🎯, active→🚀)
- 🔧 **Git Integration**: Automatic project detection from repositories
- 📁 **Multi-Mode Browser**: Documents, files, and git diffs in one interface
- ✨ **Vim Editor**: Full modal editing (NORMAL/INSERT/VISUAL) with line numbers
- 🌐 **GitHub Integration**: Create and manage Gists directly from documents

### Data Management
- 📊 **Export Options**: JSON, CSV, and pipeline-friendly output formats
- ♻️ **Trash System**: Safe deletion with restore capabilities
- 🔍 **Advanced Filtering**: Date ranges, project scopes, and tag combinations
- 📖 **Documentation**: Built-in legend and comprehensive help system

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

### ⚠️ Version 0.7.0 Migration Notes

If upgrading from 0.6.x:
1. **Database will auto-migrate** on first run
2. **Deprecated commands removed**: `health`, `clean`, `merge` (see [Migration Guide](#migration-from-06x))
3. **New consolidated commands**: `analyze`, `maintain`, `lifecycle`
4. Run `emdx analyze` after upgrade to check knowledge base health

## Quick Start

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

## Power User Features (New in 0.7.0)

### Unix Pipeline Integration

emdx now fully supports JSON output and pipeline integration for advanced workflows:

```bash
# Health check in CI/CD pipeline
emdx analyze --health --json | jq '.health_score' || exit 1

# Find urgent bugs with JSON filtering
emdx find "bug" --json | jq '.documents[] | select(.tags | contains(["urgent"]))'

# Export document IDs for batch processing
emdx find "refactor" --ids-only | xargs -I {} emdx tag {} "needs-review"

# Generate daily activity report
emdx find --date-from "yesterday" --json | jq -r '.documents[] | "\(.title) - \(.project)"'

# Automated duplicate cleanup (dry run)
emdx analyze --duplicates --json | jq -r '.duplicates[].ids[]' | head -5

# Pipeline document content to other tools
emdx view 42 --raw | pandoc -f markdown -t html > doc.html
```

### Advanced Search Capabilities

```bash
# Date-based filtering
emdx find "meeting" --date-from "2024-01-01" --date-to "2024-12-31"
emdx find --date-from "last week" --date-to "today"
emdx find --created-after "30 days ago"

# Complex tag queries
emdx find --tags "gameplan,active" --exclude-tags "blocked"
emdx find --tags "bug" --any-tags "urgent,critical"

# Project-scoped searches with multiple filters
emdx find "api" --project "backend" --tags "bug" --date-from "this month"

# Output control for scripting
emdx find "todo" --ids-only              # Just IDs for xargs
emdx find "todo" --json | jq '.count'    # Count matches
emdx find "todo" --limit 5 --offset 10   # Pagination
```

### Automated Maintenance

```bash
# Schedule regular maintenance (add to cron)
0 2 * * * emdx maintain --auto --execute >> /var/log/emdx-maintenance.log

# Health monitoring script
#!/bin/bash
HEALTH=$(emdx analyze --health --json | jq '.health_score')
if [ "$HEALTH" -lt 80 ]; then
    emdx maintain --auto --execute
    echo "Knowledge base maintained, health improved to $(emdx analyze --health --json | jq '.health_score')%"
fi

# Automated lifecycle transitions
emdx lifecycle auto-detect --execute    # Move stale gameplans to appropriate stages
emdx lifecycle analyze --json | jq '.success_rate'  # Track gameplan success

# Batch operations with dry-run safety
emdx maintain --clean                   # Preview what would be cleaned
emdx maintain --clean --execute         # Actually perform cleanup
```

### Integration Examples

```bash
# Generate markdown report of active gameplans
emdx find --tags "gameplan,active" --json | \
    jq -r '.documents[] | "## \(.title)\n\n*Project:* \(.project)\n*Created:* \(.created_at)\n"'

# Create Jira tickets from urgent bugs
emdx find --tags "bug,urgent" --json | \
    jq -r '.documents[] | @base64' | \
    while read -r doc; do
        echo "$doc" | base64 -d | jq -r '
            "jira create --project PROJ --type Bug",
            "--summary \"[EMDX] \(.title)\"",
            "--description \"Document ID: \(.id)\n\n\(.content | .[0:500])...\""
        ' | xargs
    done

# Sync to external backup with metadata
emdx list --json > backup/metadata.json
emdx list --ids-only | while read -r id; do
    emdx view "$id" --raw > "backup/docs/${id}.md"
done
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

### Core Commands
- `emdx save [input] [--title] [--project] [--tags]` - Save content (file, text, or stdin)
- `emdx find <query> [options]` - Advanced search with filters
  - `--project` - Filter by project
  - `--tags` / `--any-tags` - Filter by tags (all/any mode)
  - `--date-from` / `--date-to` - Date range filtering
  - `--fuzzy` - Typo-tolerant search
  - `--json` - JSON output for pipelines
  - `--ids-only` - Output only document IDs
- `emdx view <id|title> [--raw]` - View a document
- `emdx list [--project] [--limit] [--format]` - List documents
- `emdx edit <id|title>` - Edit a document
- `emdx delete <id|title> [--force]` - Delete a document (moves to trash)
- `emdx restore <id|title>` - Restore from trash
- `emdx purge <id|title> [--force]` - Permanently delete

### Analysis & Intelligence Commands (New in 0.7.0)
- `emdx analyze [options]` - Analyze knowledge base health
  - `--health` - Show health score and metrics
  - `--duplicates` - Find duplicate documents
  - `--similar` - Find similar documents for merging
  - `--empty` - Find empty documents
  - `--tags` - Analyze tag coverage
  - `--lifecycle` - Analyze gameplan patterns
  - `--all` - Run all analyses
  - `--json` - Output as JSON
- `emdx maintain [options]` - Automated maintenance
  - `--auto` - Fix all issues automatically
  - `--clean` - Remove duplicates and empty docs
  - `--merge` - Merge similar documents
  - `--tags` - Auto-tag documents
  - `--gc` - Database optimization
  - `--execute` - Perform changes (default: dry run)
- `emdx lifecycle <subcommand>` - Document lifecycle management
  - `status` - Show lifecycle status
  - `transition <id> <stage>` - Change document stage
  - `analyze` - Analyze lifecycle patterns
  - `auto-detect` - Suggest transitions
  - `flow` - Visualize lifecycle flow

### Tag Commands
- `emdx tag <id> [tags...]` - Add tags using text aliases (or view if no tags given)
- `emdx untag <id> <tags...>` - Remove tags from a document
- `emdx tags [--sort] [--limit]` - List all tags with usage statistics
- `emdx legend` - View emoji legend with text aliases
- `emdx retag <old_tag> <new_tag> [--force]` - Rename a tag globally
- `emdx merge-tags <tags...> --into <target> [--force]` - Merge multiple tags

### Browse Commands
- `emdx recent [count]` - Show recently accessed documents
- `emdx stats [--project]` - Show statistics
- `emdx project-stats` - Detailed project breakdown
- `emdx projects` - List all projects
- `emdx gui` - Launch interactive browser

### Gist Commands
- `emdx gist <id|title> [--public] [--copy] [--open]` - Create a GitHub Gist
- `emdx gist <id|title> --update <gist-id>` - Update an existing gist
- `emdx gist-list [--project]` - List all created gists

### ⚠️ Deprecated Commands (Removed in 0.7.0)
The following commands have been removed and replaced:
- ~~`emdx health`~~ → Use `emdx analyze --health`
- ~~`emdx clean`~~ → Use `emdx maintain --clean`
- ~~`emdx merge`~~ → Use `emdx maintain --merge`

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
│   └── tags.py               # Tag-related CLI commands
├── models/                   # Data models and business logic
│   ├── __init__.py
│   ├── documents.py          # Document model operations
│   └── tags.py               # Tag model operations
├── database/                 # Database layer (split from sqlite_database.py)
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
│   └── emoji_aliases.py      # Emoji alias system (NEW!)
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

## Migration from 0.6.x

### Command Changes
Version 0.7.0 consolidates several commands for a cleaner, more intuitive interface:

| Old Command (0.6.x) | New Command (0.7.0) | Notes |
|-------------------|-------------------|--------|
| `emdx health` | `emdx analyze --health` | More comprehensive analysis |
| `emdx clean` | `emdx maintain --clean` | Now includes dry-run by default |
| `emdx merge` | `emdx maintain --merge` | Smarter similarity detection |
| N/A | `emdx analyze` | New unified analysis command |
| N/A | `emdx maintain` | New automated maintenance |
| N/A | `emdx lifecycle` | New lifecycle tracking |

### New Features to Explore
After upgrading, try these new capabilities:

```bash
# Check your knowledge base health
emdx analyze --health

# Find and fix issues automatically
emdx maintain --auto  # Preview changes
emdx maintain --auto --execute  # Apply changes

# Track gameplan success rates
emdx lifecycle analyze

# Use JSON output for automation
emdx find "todo" --json | jq '.documents[].title'
```

### Breaking Changes
1. **Removed commands**: `health`, `clean`, `merge` no longer exist
2. **Default dry-run**: `maintain` commands preview by default, use `--execute` to apply
3. **JSON structure**: New standardized JSON output format for all commands

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
- [x] ~~Health monitoring system~~ - **COMPLETED** with analyze command
- [x] ~~Automated maintenance~~ - **COMPLETED** with maintain command
- [x] ~~JSON/pipeline integration~~ - **COMPLETED** with --json flags
- [x] ~~Auto-tagging system~~ - **COMPLETED** with AI-powered analysis
- [ ] Add comprehensive test suite
- [ ] Set up GitHub Actions CI/CD  
- [ ] Add more export formats (Markdown, HTML)
- [ ] Create web UI companion

## License

MIT License - see LICENSE file for details

