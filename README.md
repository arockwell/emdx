# emdx

[![Version](https://img.shields.io/badge/version-0.7.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**A terminal-native knowledge base with full-text search, emoji tags, and AI agent integration.**

Stop losing notes in scattered markdown files. EMDX gives you instant search across all your documents, smart tagging with emoji aliases, and deep integration with Claude Code for AI-powered workflows.

## Key Features

- **Instant Search** - SQLite FTS5 full-text search with ranking
- **Emoji Tags** - Type `gameplan` and get 🎯, type `active` and get 🚀
- **Rich TUI** - Vim-style navigation across documents, files, git diffs, and logs
- **AI Agents** - Create custom agents for code review, research, and automation
- **Claude Integration** - Execute documents directly with Claude Code
- **Git Aware** - Auto-detects projects, visual diff browser, worktree switching
- **Zero Config** - SQLite backend, no server required

## Quick Start

```bash
# Install
git clone https://github.com/arockwell/emdx.git
cd emdx && pip install -e .

# Save your first document
echo "Remember to refactor the auth module" | emdx save --title "Auth TODO" --tags "bug,active"

# Search
emdx find "auth"
emdx find --tags "active"

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

### Document Formatting

EMDX fully supports standard markdown with excellent content preservation:

```bash
# Supported markdown features:
# - Headers (all levels), **bold**, *italic*, `code`
# - Lists (ordered, unordered, nested, task lists)
# - Code blocks with syntax highlighting
# - Tables, blockquotes, links, images
# - Full Unicode support (中文, 日本語, العربية, 🎯🚀✨)
# - Special characters (<>&"', math symbols ∑∏∫∞)

# View formatted document
emdx view 42

# View raw markdown
emdx view 42 --raw

# All formatting is preserved through save/retrieve cycles
```

See [docs/formatting-guide.md](docs/formatting-guide.md) for the complete formatting guide.

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

## Core Concepts

### Documents
Every piece of content is a **document** with a unique ID. Documents belong to **projects** (auto-detected from git repos).

```bash
emdx save notes.md                    # Save a file
echo "quick note" | emdx save --title "Note"  # Save from stdin
emdx view 42                          # View document #42
emdx edit 42                          # Edit in $EDITOR
```

### Emoji Tags
Tags use emoji for visual density. Type text aliases instead of hunting for emoji:

| Type this | Get this | Use for |
|-----------|----------|---------|
| `gameplan`, `plan` | 🎯 | Strategic documents |
| `analysis`, `research` | 🔍 | Investigations |
| `notes`, `memo` | 📝 | General notes |
| `docs` | 📚 | Documentation |
| `active`, `working` | 🚀 | Currently in progress |
| `done`, `complete` | ✅ | Finished work |
| `blocked`, `stuck` | 🚧 | Waiting on something |
| `success`, `win` | 🎉 | Positive outcome |
| `failed` | ❌ | Negative outcome |
| `bug`, `issue` | 🐛 | Problems to fix |
| `feature` | ✨ | New functionality |
| `urgent`, `critical` | 🚨 | High priority |
| `refactor` | 🔧 | Code improvements |

```bash
# Add tags when saving
emdx save plan.md --tags "gameplan,active"

# Add tags to existing document
emdx tag 42 analysis done success

# Search by tags
emdx find --tags "active"
emdx find --tags "gameplan,done"
```

## Essential Commands

```bash
# Save content
emdx save file.md                         # Save file (title from filename)
emdx save file.md --title "Custom Title"  # Save with custom title
echo "text" | emdx save --title "Title"   # Save from stdin (CORRECT)

# Search
emdx find "search terms"                  # Full-text search
emdx find --tags "tag1,tag2"              # Search by tags

# Browse
emdx list                                 # List all documents
emdx recent                               # Recently accessed
emdx view <id>                            # View document
emdx edit <id>                            # Edit in $EDITOR

# Tags
emdx tag <id> tag1 tag2                   # Add tags
emdx untag <id> tag1                      # Remove tag
emdx tags                                 # List all tags with counts
emdx legend                               # Show emoji alias reference

# TUI
emdx gui                                  # Launch interactive browser
```

## AI Integration

EMDX is designed to work with Claude Code and other AI assistants.

### For AI Agents: Critical Syntax

```bash
# CORRECT: Save text via stdin
echo "My content here" | emdx save --title "Title"

# WRONG: This looks for a FILE named "My content here"
emdx save "My content here"
```

### Using with Claude Code

Documents can be executed directly with Claude:

```bash
# In TUI: press 'x' on any document to execute with Claude
# Or run agents on documents:
emdx agent run code-reviewer --doc 123
```

### Custom Agents

Create AI agents for repeatable tasks:

```bash
emdx agent list                           # List available agents
emdx agent run <name> --doc <id>          # Run agent on document
emdx agent run <name> --query "text"      # Run agent with query
```

See [AI Agents Guide](docs/ai-agents.md) for creating custom agents.

## TUI Browser

Launch with `emdx gui`. Vim-style keybindings:

| Key | Action |
|-----|--------|
| `j/k` | Navigate down/up |
| `Enter` | Select/open |
| `e` | Edit with vim |
| `f` | File browser mode |
| `d` | Git diff browser |
| `l` | Log browser |
| `a` | Agent browser |
| `x` | Execute with Claude |
| `/` | Search |
| `q` | Quit/back |

### Browser Modes

- **Documents** (default) - Browse and manage your knowledge base
- **Files** (`f`) - Browse filesystem with preview
- **Git** (`d`) - Visual diff viewer, worktree switching
- **Logs** (`l`) - Execution monitoring
- **Agents** (`a`) - AI agent management

## Configuration

| Setting | Location | Notes |
|---------|----------|-------|
| Database | `~/.emdx/emdx.db` | Created automatically |
| Editor | `$EDITOR` env var | For external editing |
| GitHub | `GITHUB_TOKEN` or `gh auth login` | For GitHub integration |

## Documentation

- [AI Agents Guide](docs/ai-agents.md) - Create and run custom AI agents
- [CLI Reference](docs/cli-api.md) - Complete command documentation
- [Architecture](docs/architecture.md) - System design and code structure
- [UI Guide](docs/ui-architecture.md) - TUI components and theming
- [Development Setup](docs/development-setup.md) - Contributing guide
- [Database Design](docs/database-design.md) - Schema and migrations

## Contributing

```bash
# Development install
git clone https://github.com/arockwell/emdx.git
cd emdx
poetry install
poetry run emdx --help
```

See [Development Setup](docs/development-setup.md) for testing and code quality guidelines.

## License

MIT License - see LICENSE file for details.
