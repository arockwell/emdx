# emdx - Documentation Index Management System

[![Version](https://img.shields.io/badge/version-0.5.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

A powerful command-line tool for managing your personal knowledge base with SQLite full-text search, Git integration, and a modern terminal interface with seamless nvim integration.

## Features

- 🚀 **Unified CLI**: Single `emdx` command with intuitive subcommands
- 🔍 **Full-Text Search**: SQLite FTS5-powered search with ranking and fuzzy matching
- 📝 **Flexible Input**: Save files, text, or piped input with one command
- 🎨 **Rich Terminal UI**: Beautiful tables, markdown rendering, and syntax highlighting
- 🔧 **Git Integration**: Automatically detects project names from Git repositories
- 🖥️ **Modern TUI Browser**: Textual-based browser with vim-style navigation and zero-flash nvim editing
- 💾 **SQLite Backend**: Zero-setup, portable, fast local storage
- 🌐 **GitHub Gist Integration**: Share your knowledge base entries as GitHub Gists
- ✏️ **Document Management**: Edit and delete documents with trash/restore functionality
- 📊 **Export Options**: Export your knowledge base as JSON or CSV
- 🏷️ **Tag System**: Organize documents with tags for better categorization and discovery

## Installation

### Prerequisites

- Python 3.8+
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
pip install -e ".[dev]"
```

### No database setup required!

emdx uses SQLite and stores your knowledge base at `~/.config/emdx/knowledge.db`. It's created automatically on first use.

## Quick Start

### Save content
```bash
# Save a markdown file
emdx save README.md

# Save text directly
emdx save "Remember to fix the API endpoint"

# Save from pipe
docker ps | emdx save --title "Running containers"

# Save from clipboard
pbpaste | emdx save --title "Code snippet"

# Save command output
ls -la | emdx save --title "Directory listing"

# With custom project
emdx save notes.md --title "Project Notes" --project "my-app"

# With tags
emdx save README.md --tags "documentation,python,api"
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

# Search by tags
emdx find --tags "python,tutorial"  # Documents with ALL tags
emdx find --tags "python,tutorial" --any-tags  # Documents with ANY tag

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

### Tag management
```bash
# Add tags to a document
emdx tag 42 python tutorial api

# View tags for a document
emdx tag 42

# Remove tags from a document
emdx untag 42 tutorial

# List all tags with statistics
emdx tags
emdx tags --sort usage  # Sort by usage count
emdx tags --sort name   # Sort alphabetically

# Rename a tag globally
emdx retag "python3" "python"

# Merge multiple tags into one
emdx merge-tags py python3 --into python
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
- **Zero-flash nvim editing**: Seamless transition to nvim without terminal flash
- **Modal interface**: True vim-style NORMAL/SEARCH modes  
- **Live search**: Real-time document filtering as you type
- **Rich markdown preview**: Clean document rendering with syntax highlighting
- **Mouse support**: Click and scroll support alongside keyboard navigation
- **Keyboard navigation**:
  - `j/k` - Move up/down through documents
  - `g/G` - Go to first/last document
  - `/` - Enter search mode
  - `e` - Edit document in nvim (seamless, no flash)
  - `d` - Delete document (modal confirmation)
  - `v` or `Enter` - View document in full-screen
  - `q` or `Esc` - Exit browser

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

### Tag Commands
- `emdx tag <id> [tags...]` - Add tags to a document (or view if no tags given)
- `emdx untag <id> <tags...>` - Remove tags from a document
- `emdx tags [--sort] [--limit]` - List all tags with usage statistics
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
├── cli.py              # Main CLI entry point using Typer
├── core.py             # Core commands (save, find, view, edit, delete)
├── browse.py           # Browse and stats commands
├── gist.py             # GitHub Gist integration
├── gui.py              # Interactive FZF browser
├── tags.py             # Core tag functionality
├── tag_commands.py     # Tag-related CLI commands
├── database.py         # Database abstraction layer
├── sqlite_database.py  # SQLite implementation
├── migrations.py       # Database migration system
├── config.py           # Configuration management
└── utils.py            # Shared utilities
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

- [ ] Add comprehensive test suite
- [ ] Set up GitHub Actions CI/CD
- [ ] Add more export formats (Markdown, HTML)
- [ ] Implement search operators (AND, OR, NOT)
- [ ] Add tagging system
- [ ] Create web UI companion

## License

MIT License - see LICENSE file for details

