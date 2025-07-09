# emdx - Documentation Index Management System

A powerful command-line tool for managing your personal knowledge base with SQLite full-text search, Git integration, and a beautiful terminal interface.

## Features

- 🚀 **Unified CLI**: Single `emdx` command with intuitive subcommands
- 🔍 **Full-Text Search**: SQLite FTS5-powered search with ranking and fuzzy matching
- 📝 **Flexible Input**: Save files, text, or piped input with one command
- 🎨 **Rich Terminal UI**: Beautiful tables, markdown rendering, and syntax highlighting
- 🔧 **Git Integration**: Automatically detects project names from Git repositories
- 🖥️ **Interactive Browser**: FZF-based document browser for quick navigation
- 💾 **SQLite Backend**: Zero-setup, portable, fast local storage
- 🌐 **GitHub Gist Integration**: Share your knowledge base entries as GitHub Gists

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
- `emdx save [input] [--title] [--project]` - Save content (file, text, or stdin)
- `emdx find <query> [--project] [--limit] [--snippets] [--fuzzy]` - Search documents
- `emdx view <id|title> [--raw]` - View a document
- `emdx list [--project] [--limit] [--format]` - List documents
- `emdx edit <id|title>` - Edit a document
- `emdx delete <id|title> [--force]` - Delete a document

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

