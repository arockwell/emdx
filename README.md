# emdx

[![Version](https://img.shields.io/badge/version-0.7.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**A terminal-native knowledge base with full-text search, emoji tags, and AI agent integration.**

Transform your knowledge base from a passive store to an active assistant with auto-tagging, health monitoring, and Unix pipeline integration.

Stop losing notes in scattered markdown files. EMDX gives you instant search across all your documents, smart tagging with emoji aliases, and deep integration with Claude Code for AI-powered workflows.

## Key Features

- **Instant Search** - SQLite FTS5 full-text search with ranking
- **Emoji Tags** - Type `gameplan` and get 🎯, type `active` and get 🚀
- **Rich TUI** - Vim-style navigation across documents, files, git diffs, and logs
- **AI Agents** - Create custom agents for code review, research, and automation
- **Claude Integration** - Execute documents directly with Claude Code
- **Git Aware** - Auto-detects projects, visual diff browser, worktree switching
- **Zero Config** - SQLite backend, no server required

### New in 0.7.0

- **Intelligent Auto-Tagging** - Automatically organize documents with smart tag suggestions
- **Health Monitoring** - Track knowledge base health with 6 weighted metrics
- **Unix Pipeline Integration** - `--ids-only`, `--json`, date filtering for automation
- **Command Consolidation** - 15 commands → 3 focused commands (analyze, maintain, lifecycle)
- **Refined TUI** - Smart 66/34 layout with tags column and improved performance
- **Automated Maintenance** - One-command cleanup with `emdx maintain --auto`

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

# Browse in TUI
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

---

**Quick Links**: [Installation](#quick-start) • [Documentation](docs/) • [CLI Reference](docs/cli-api.md) • [Contributing](docs/development-setup.md)
