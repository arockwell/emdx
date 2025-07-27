# emdx - Documentation Index Management System

[![Version](https://img.shields.io/badge/version-0.6.1-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

A powerful command-line tool for managing your personal knowledge base with SQLite full-text search, Git integration, and a modern terminal interface with seamless nvim integration.

## Features

- 🚀 **Unified CLI**: Single `emdx` command with intuitive subcommands
- 🔍 **Full-Text Search**: SQLite FTS5-powered search with ranking and fuzzy matching
- 📝 **Flexible Input**: Save files, text, or piped input with one command
- 🎨 **Rich Terminal UI**: Beautiful tables, markdown rendering, and syntax highlighting
- 🔧 **Git Integration**: Automatically detects project names from Git repositories
- 🖥️ **Advanced TUI Browser**: Multiple browser modes (documents, files, git diffs) with full vim editing
- 📁 **File Browser**: Yazi-inspired file navigation with real-time preview and vim integration
- 🔀 **Git Diff Browser**: Visual git diff viewer with worktree switching (press 'd' and 'w')
- ⚡ **Claude Execution**: Execute prompts directly from TUI with live streaming logs
- ✨ **Complete Vim Editor**: Full modal editing (NORMAL/INSERT/VISUAL modes) with line numbers
- 💾 **SQLite Backend**: Zero-setup, portable, fast local storage
- 🌐 **GitHub Gist Integration**: Share your knowledge base entries as GitHub Gists
- ✏️ **Document Management**: Edit and delete documents with trash/restore functionality
- 📊 **Export Options**: Export your knowledge base as JSON or CSV
- 🏷️ **Emoji Tag System**: Organize with emoji tags + intuitive text aliases (gameplan→🎯, active→🚀)
- 📖 **Emoji Legend**: `emdx legend` command for quick emoji reference and aliases

## Installation

### Prerequisites

- Python 3.13+
- textual (for interactive GUI - installed automatically)
- nvim (for seamless editing integration)

### Quick Install (Production Use)

```bash
git clone https://github.com/arockwell/emdx.git
cd emdx
pip install -e .
```

### Development Installation (Recommended)

For development work or contributing to EMDX, use the Poetry + Just workflow:

```bash
# 1. Clone the repository
git clone https://github.com/arockwell/emdx.git
cd emdx

# 2. Install Poetry (if not already installed)
# macOS/Linux
curl -sSL https://install.python-poetry.org | python3 -
# Or via Homebrew
brew install poetry

# 3. Install Just task runner
# macOS
brew install just
# Linux
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# 4. Install dependencies with Poetry
poetry install

# 5. Run development version using Just
just dev

# 6. See all available development commands
just
```

#### Available Just Commands

```bash
just dev              # Run emdx using Poetry environment
just test             # Run test suite
just lint             # Run code linting (ruff)
just format           # Format code (black)
just typecheck        # Run type checking (mypy)
just install          # Install dependencies
just clean            # Clean temporary files
just build            # Build distribution packages
```

#### Development vs Global Installation

**Important**: In the EMDX project directory, always use `poetry run emdx` or `just dev` instead of the global `emdx` command to ensure you're using the correct dependencies and Python version.

```bash
# ✅ Correct (in project directory)
poetry run emdx save README.md
just dev save README.md

# ❌ May cause issues (global installation may be outdated)
emdx save README.md
```

### No database setup required!

emdx uses SQLite and stores your knowledge base at `~/.config/emdx/knowledge.db`. It's created automatically on first use.

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

### Advanced Multi-Modal Browser
```bash
# Launch modern textual browser with multiple modes
emdx gui
```

The GUI browser provides four integrated browser modes:

#### **📖 Document Browser Mode (Default)**
- **In-place vim editing**: Full vim modal editing directly in the preview pane
- **Modal interface**: True vim-style NORMAL/SEARCH modes  
- **Live search**: Real-time document filtering as you type
- **Rich markdown preview**: Clean document rendering with syntax highlighting
- **Mouse support**: Click and scroll support alongside keyboard navigation

#### **📁 File Browser Mode (Press 'f')**
- **Yazi-inspired navigation**: Modern file system browser with vim keybindings
- **Real-time preview**: Instant file content preview with syntax highlighting
- **File operations**: Create, delete, rename files directly from browser
- **Git integration**: Shows git status indicators for tracked files
- **Seamless editing**: Edit any file with integrated vim editor

#### **🔀 Git Diff Browser Mode (Press 'd')**  
- **Visual diff viewer**: Side-by-side or unified diff view with syntax highlighting
- **Worktree switching**: Press 'w' to switch between git worktrees interactively
- **Branch comparison**: Compare changes across branches and commits
- **File-level navigation**: Navigate through changed files with j/k
- **Git operations**: Stage, unstage, commit changes from browser

#### **🚀 Claude Execution Integration**
- **Execute from browser**: Press 'x' to execute current document with Claude Code
- **Live streaming logs**: Press 'l' to view execution logs with real-time updates
- **Execution history**: Browse previous executions with status indicators
- **Contextual prompts**: Smart prompt selection based on document tags and content

#### **Keyboard Navigation (Universal)**
- `j/k` - Move up/down through items
- `g/G` - Go to first/last item
- `/` - Enter search mode
- `e` - Edit item with vim keybindings (in-place)
- `s` - Text selection mode
- `d` - Delete item (modal confirmation)
- `v` or `Enter` - View item in full-screen
- `f` - Switch to file browser mode
- `d` - Switch to git diff browser mode
- `w` - Switch git worktrees (in git mode)
- `x` - Execute with Claude (documents only)
- `l` - View execution logs
- `g` - Create GitHub gist
- `q` or `Esc` - Exit browser or return to previous mode

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
- `emdx find <query> [--project] [--limit] [--snippets] [--fuzzy] [--tags] [--any-tags]` - Search documents
- `emdx view <id|title> [--raw]` - View a document
- `emdx list [--project] [--limit] [--format]` - List documents
- `emdx edit <id|title>` - Edit a document
- `emdx delete <id|title> [--force]` - Delete a document (moves to trash)
- `emdx trash <id|title>` - Move document to trash
- `emdx restore <id|title>` - Restore from trash
- `emdx purge <id|title> [--force]` - Permanently delete

### Execution Management Commands
- `emdx exec list` - List recent Claude executions with status
- `emdx exec show <execution-id>` - Show detailed execution information
- `emdx exec logs <execution-id> [--follow] [--lines=N]` - View execution logs
- `emdx exec stats` - Show execution statistics and performance metrics
- `emdx exec cleanup` - Clean up old execution logs and data

### Claude Execution Commands  
- `emdx claude run <document-id>` - Execute a document with Claude Code
- `emdx claude stage <document-id>` - Stage a document for execution with restricted tools
- `emdx claude prompt <document-id>` - Show the prompt that would be sent to Claude
- `emdx claude validate <document-id>` - Validate document for Claude execution

### Document Lifecycle Commands
- `emdx lifecycle track <document-id>` - Start tracking document lifecycle
- `emdx lifecycle status <document-id>` - Show current lifecycle status
- `emdx lifecycle progress` - Show progress of all tracked documents
- `emdx lifecycle advance <document-id> <stage>` - Advance document to next stage
- `emdx lifecycle report` - Generate lifecycle analytics report

### Analysis Commands
- `emdx analyze [--health] [--duplicates] [--similar] [--orphans] [--lifecycle]` - Comprehensive analysis
  - `--health` - Show detailed health metrics and database statistics
  - `--duplicates` - Find duplicate documents for cleanup
  - `--similar` - Find similar documents for potential merging
  - `--orphans` - Find orphaned documents with broken references
  - `--lifecycle` - Show lifecycle stage distribution and trends

### Database Maintenance Commands
- `emdx maintain [--vacuum] [--reindex] [--merge-dupes] [--auto-tag] [--cleanup]` - Database maintenance
  - `--vacuum` - Compact database and reclaim space
  - `--reindex` - Rebuild search indexes for optimal performance
  - `--merge-dupes` - Interactively merge duplicate documents
  - `--auto-tag` - Automatically tag documents based on content analysis
  - `--cleanup` - Remove orphaned data and temporary files

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
- `emdx gui` - Launch interactive browser

### Gist Commands
- `emdx gist <id|title> [--public] [--copy] [--open]` - Create a GitHub Gist from a document
- `emdx gist <id|title> --update <gist-id>` - Update an existing gist
- `emdx gist-list [--project]` - List all created gists

## Advanced Features

### Claude Code Execution

Execute your documents directly with Claude Code for automated implementation, analysis, and development tasks.

```bash
# Execute a document (gameplan, analysis, etc.)
emdx claude run 42

# Execute with staging mode (restricted tools for safety)
emdx claude stage 42

# Preview the prompt that would be sent to Claude
emdx claude prompt 42

# Validate a document is ready for execution
emdx claude validate 42

# Monitor execution progress
emdx exec list
emdx exec logs <execution-id> --follow

# View execution statistics
emdx exec stats
```

#### Execution Types

EMDX automatically detects document types based on tags and content:

- **🎯 Gameplans** (`gameplan` tag) - Implementation plans executed step-by-step
- **🔍 Analysis** (`analysis` tag) - Analytical tasks with comprehensive reporting  
- **📝 Notes** (`note` tag) - Simple note processing and enhancement
- **⚡ Generic** - General document processing and transformation

#### Smart Prompt Selection

Claude receives contextually appropriate prompts based on document type:
- Gameplans get implementation-focused prompts with todo tracking
- Analysis documents get comprehensive research prompts
- Notes get enhancement and organization prompts

### Document Lifecycle Management

Track and manage document progression through defined stages:

```bash
# Start tracking a document's lifecycle
emdx lifecycle track 42

# Check current lifecycle status
emdx lifecycle status 42

# View progress of all tracked documents
emdx lifecycle progress

# Advance a document to the next stage
emdx lifecycle advance 42 active

# Generate lifecycle analytics report
emdx lifecycle report
```

#### Lifecycle Stages

- **🎯 Planning** - Initial planning and design phase
- **🚀 Active** - Currently being worked on
- **🚧 Blocked** - Waiting on dependencies or decisions
- **✅ Completed** - Work finished successfully
- **🎉 Success** - Completed with successful outcome
- **❌ Failed** - Did not complete successfully
- **📦 Archived** - No longer active but preserved

### Database Analysis & Maintenance

Keep your knowledge base healthy and optimized:

```bash
# Comprehensive health check
emdx analyze --health

# Find and review duplicates
emdx analyze --duplicates

# Identify similar documents for merging
emdx analyze --similar

# Show lifecycle stage distribution
emdx analyze --lifecycle

# Database maintenance operations
emdx maintain --vacuum          # Compact database
emdx maintain --reindex         # Rebuild search indexes  
emdx maintain --merge-dupes     # Interactive duplicate merging
emdx maintain --auto-tag        # AI-powered automatic tagging
emdx maintain --cleanup         # Remove orphaned data
```

### Advanced Search Capabilities

Beyond basic text search, EMDX provides powerful search operators:

```bash
# Tag-based search (documents with ALL tags)
emdx find --tags "gameplan,active"

# Tag-based search (documents with ANY tag)
emdx find --tags "python,rust,go" --any-tags

# Combine text and tag search
emdx find "authentication" --tags "security,feature"

# Fuzzy search (typo-tolerant)
emdx find "autentication" --fuzzy

# Project-specific search
emdx find "API endpoints" --project "my-web-app"

# Search with context snippets
emdx find "database migration" --snippets
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
├── main.py                          # Main CLI entry point using Typer
├── commands/                        # CLI command implementations (11 modules)
│   ├── __init__.py
│   ├── core.py                      # Core commands (save, find, view, edit, delete)
│   ├── browse.py                    # Browse and stats commands
│   ├── gist.py                      # GitHub Gist integration
│   ├── tags.py                      # Tag-related CLI commands
│   ├── executions.py                # NEW: Execution management subcommands
│   ├── claude_execute.py            # NEW: Claude execution subcommands
│   ├── lifecycle.py                 # NEW: Document lifecycle tracking
│   ├── analyze.py                   # NEW: Document analysis command
│   ├── maintain.py                  # NEW: Database maintenance command
│   └── gc.py                        # Garbage collection utilities
├── models/                          # Data models and business logic
│   ├── __init__.py
│   ├── documents.py                 # Document model operations
│   ├── tags.py                      # Tag model operations
│   └── executions.py                # NEW: Execution model operations
├── database/                        # Database layer (modular architecture)
│   ├── __init__.py
│   ├── connection.py                # Database connection management
│   ├── documents.py                 # Document database operations
│   ├── search.py                    # Full-text search functionality
│   └── migrations.py                # Database migration system
├── ui/                              # Modular UI components (25 specialized files)
│   ├── __init__.py
│   ├── browser_container.py         # Main browser container widget
│   ├── document_browser.py          # Document browsing interface
│   ├── document_viewer.py           # Document viewing component
│   ├── file_browser.py              # Yazi-inspired file browser with vim integration
│   ├── file_list.py                 # File listing widget
│   ├── file_modals.py               # File operation modals
│   ├── file_preview.py              # Real-time file content preview
│   ├── git_browser.py               # Git diff browser with worktree support
│   ├── git_browser_standalone.py    # Standalone git browser mode
│   ├── log_browser.py               # Execution log viewer with streaming
│   ├── log_parser.py                # Structured log parsing
│   ├── main_browser.py              # Main browser orchestration
│   ├── vim_editor.py                # Complete vim modal editor implementation
│   ├── vim_line_numbers.py          # Vim-style line numbering system
│   ├── worktree_picker.py           # Git worktree switching interface
│   ├── text_areas.py                # Enhanced text input components
│   ├── modals.py                    # Modal dialog components
│   ├── inputs.py                    # Custom input widgets
│   ├── run_browser.py               # Execution browser interface
│   ├── textual_browser.py           # Legacy unified browser (being modularized)
│   ├── formatting.py                # Tag display and rich formatting
│   ├── gui.py                       # GUI entry point and coordination
│   ├── markdown_config.py           # Markdown rendering configuration
│   ├── mdcat_renderer.py            # External mdcat integration
│   └── nvim_wrapper.py              # Seamless Neovim integration
├── services/                        # Business logic services (NEW!)
│   ├── __init__.py
│   ├── auto_tagger.py               # Automatic content-based tagging
│   ├── document_merger.py           # Document merging and deduplication
│   ├── duplicate_detector.py        # Duplicate document detection
│   ├── execution_monitor.py         # Claude execution monitoring
│   ├── health_monitor.py            # Database health monitoring
│   └── lifecycle_tracker.py         # Document lifecycle management
├── prompts/                         # Claude execution prompt templates (NEW!)
│   ├── __init__.py
│   ├── analyze_note.md              # Note analysis prompt template
│   ├── create_gameplan.md           # Gameplan creation template
│   └── implement_gameplan.md        # Gameplan implementation template
├── utils/                           # Shared utilities
│   ├── __init__.py
│   ├── git.py                       # Git project detection utilities
│   ├── git_ops.py                   # Advanced git operations
│   ├── emoji_aliases.py             # Emoji alias system with text shortcuts
│   ├── environment.py               # Environment validation for Claude execution
│   ├── structured_logger.py         # Structured logging for executions
│   ├── claude_wrapper.py            # Claude Code integration wrapper
│   ├── file_size.py                 # File size utilities
│   └── log_migration.py             # Log format migration utilities
└── config/                          # Configuration management
    ├── __init__.py
    ├── settings.py                  # Core configuration settings
    └── tagging_rules.py             # Automatic tagging rule definitions
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
- [ ] Add comprehensive test suite
- [ ] Set up GitHub Actions CI/CD  
- [ ] Add more export formats (Markdown, HTML)
- [ ] Create web UI companion
- [ ] Add fuzzy alias matching for typos

## License

MIT License - see LICENSE file for details

