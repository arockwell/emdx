# emdx - Documentation Index Management System

A powerful command-line tool for managing your personal knowledge base with PostgreSQL full-text search, Git integration, and a beautiful terminal interface.

## Features

- 🚀 **Unified CLI**: Single `emdx` command with intuitive subcommands
- 🔍 **Full-Text Search**: PostgreSQL-powered search with ranking and fuzzy matching
- 📝 **Multiple Input Methods**: Save files, create notes, pipe output, or paste from clipboard
- 🎨 **Rich Terminal UI**: Beautiful tables, markdown rendering, and syntax highlighting
- 🔧 **Git Integration**: Automatically detects project names from Git repositories
- 🖥️ **Interactive Browser**: FZF-based document browser for quick navigation
- 💾 **PostgreSQL Backend**: Reliable, fast, and scalable document storage

## Installation

### Prerequisites

- Python 3.8+
- PostgreSQL 12+
- fzf (for interactive mode)

### Install from source

```bash
git clone https://github.com/yourusername/emdx.git
cd emdx
pip install -e .
```

### Set up the database

By default, emdx connects to PostgreSQL using standard environment variables:
- `PGHOST` (default: localhost)
- `PGPORT` (default: 5432)
- `PGUSER` (default: your system username)
- `PGPASSWORD` (if needed)
- `PGDATABASE` (default: same as PGUSER)

Or set a complete connection URL:
```bash
export EMDX_DATABASE_URL="postgresql://user:password@localhost:5432/dbname"
```

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

## Configuration

### Environment Variables

- `EMDX_DATABASE_URL` - PostgreSQL connection URL
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` - Standard PostgreSQL variables

### Git Integration

emdx automatically detects the Git repository name when saving files. This helps organize documents by project without manual tagging.

## Database Schema

emdx uses a simple but powerful schema:

```sql
CREATE TABLE claude.knowledge (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    project TEXT,
    search_vector tsvector,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    accessed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    access_count INTEGER DEFAULT 0
);
```

Full-text search is powered by PostgreSQL's native text search with automatic stemming and ranking.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see LICENSE file for details

