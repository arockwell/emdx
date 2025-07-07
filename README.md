# emdx - Documentation Index Management System

A powerful command-line tool for managing your personal knowledge base with PostgreSQL full-text search, Git integration, and a beautiful terminal interface.

## Features

- 🚀 **Unified CLI**: Single `emdx` command with intuitive subcommands
- 🔍 **Full-Text Search**: PostgreSQL-powered search with ranking and fuzzy matching
- 📝 **Multiple Input Methods**: Save files, create notes, pipe output, or paste from clipboard
- 🎨 **Rich Terminal UI**: Beautiful tables, markdown rendering, and syntax highlighting
- 🔧 **Git Integration**: Automatically detects project names from Git repositories
- 🖥️ **Interactive Browser**: FZF-based document browser for quick navigation
- 💾 **SQLite Backend**: Zero-setup, portable, fast local storage

## Installation

### Prerequisites

- Python 3.8+
- fzf (for interactive mode)
- mdcat (optional, for better markdown viewing with pagination)

### Install from source

```bash
git clone https://github.com/yourusername/emdx.git
cd emdx
pip install -e .
```

### No database setup required!

emdx uses SQLite and stores your knowledge base at `~/.config/emdx/knowledge.db`. It's created automatically on first use.

## Quick Start

### Save a document
```bash
# Save a markdown file
emdx save README.md

# Save with custom title
emdx save notes.md "Project Notes"

# Save with specific project
emdx save doc.md "API Docs" "my-project"
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

### Quick capture
```bash
# Save a quick note
emdx note "Remember to review PR #123"

# Save clipboard contents
emdx clip "Useful code snippet"

# Pipe command output
ls -la | emdx pipe "Directory structure"

# Execute and save command output
emdx cmd "git log --oneline -10" --title "Recent commits"

# Direct text input
emdx direct "Meeting notes" "Discussed project timeline..."
```

### Interactive browser
```bash
# Launch interactive FZF browser
emdx gui
```

In the browser:
- `j/k` or `↑/↓` - Navigate
- `/` - Toggle search
- `Enter` - View document
- `Ctrl-R` - Refresh list
- `q` - Quit

## Command Reference

### Core Commands
- `emdx save <file> [title] [project]` - Save a markdown file
- `emdx find <query> [--project] [--limit] [--snippets] [--fuzzy]` - Search documents
- `emdx view <id|title> [--raw]` - View a document
- `emdx list [--project] [--limit] [--format]` - List documents
- `emdx edit <id|title>` - Edit a document
- `emdx delete <id|title> [--force]` - Delete a document

### Capture Commands
- `emdx note <text>` - Save a quick note
- `emdx clip [title]` - Save clipboard contents
- `emdx pipe <title>` - Save piped input
- `emdx cmd <command>` - Execute and save command output
- `emdx direct <title> <content>` - Save text directly

### Browse Commands
- `emdx recent [count]` - Show recently accessed documents
- `emdx stats [--project]` - Show statistics
- `emdx gui` - Launch interactive browser

## Migrating from PostgreSQL

If you were using emdx with PostgreSQL, you can easily migrate your data:

```bash
# Install with PostgreSQL support
pip install "emdx[postgres]"

# Run migration
emdx migrate

# Or specify custom connections
emdx migrate --postgres-url "postgresql://user@localhost/db" --sqlite-path ~/my-knowledge.db
```

## Configuration

### Database Location

By default, emdx stores your knowledge base at `~/.config/emdx/knowledge.db`. This location is created automatically.

### Git Integration

emdx automatically detects the Git repository name when saving files. This helps organize documents by project without manual tagging.

## Technical Details

emdx uses SQLite with FTS5 (Full-Text Search 5) for powerful search capabilities:

- **Instant search** across all your documents
- **Ranked results** based on relevance
- **Stemming support** (search "running" finds "run", "runs")
- **Phrase search** with quotation marks
- **Portable database** - just one file you can backup or sync

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details

