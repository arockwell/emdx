# emdx - Documentation Index Management System

[![Version](https://img.shields.io/badge/version-0.7.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

A powerful command-line tool for managing your personal knowledge base with SQLite full-text search, Git integration, and a modern terminal interface.

## ✨ **Key Features**

- **🔍 Fast Search** - SQLite FTS5 full-text search with ranking
- **🎨 Rich TUI** - Multiple browser modes (documents, files, git diffs) with vim editing  
- **🏷️ Smart Tagging** - Emoji tags with intuitive text aliases (`gameplan`→🎯, `active`→🚀)
- **⚡ Claude Integration** - Execute documents directly with Claude Code
- **🔧 Git Aware** - Auto-detects projects, diff viewer, worktree switching
- **💾 Zero Setup** - SQLite backend, no database server required

## 🚀 **Quick Start**

### Installation
```bash
git clone https://github.com/arockwell/emdx.git
cd emdx
pip install -e .
```

### Basic Usage
```bash
# Save content
emdx save README.md
echo "Remember to fix the API" | emdx save --title "API Note"

# Search documents  
emdx find "docker compose"
emdx find --tags "gameplan,active"

# Launch TUI browser
emdx gui
```

### Key TUI Commands
- `j/k` - Navigate up/down
- `e` - Edit with vim
- `f` - File browser mode
- `d` - Git diff browser  
- `l` - Log browser
- `x` - Execute with Claude
- `q` - Quit/back

## 📚 **Documentation**

For comprehensive guides and detailed information:

- **[📖 Complete Documentation](docs/)** - Full project documentation
- **[🏗️ Architecture](docs/architecture.md)** - System design and code structure
- **[⚙️ Development Setup](docs/development-setup.md)** - Contributing and development guide
- **[📋 CLI Reference](docs/cli-api.md)** - Complete command documentation
- **[🎨 UI Guide](docs/ui-architecture.md)** - TUI components and key bindings

## 💡 **Common Workflows**

### Knowledge Management
```bash
# Quick note capture
echo "Bug in auth system" | emdx save --title "Auth Bug" --tags "bug,urgent"

# Research documentation  
emdx save research.md --tags "analysis,done"
emdx find --tags "analysis"

# Project tracking
echo "Phase 1: Setup infrastructure" | emdx save --title "Project Plan" --tags "gameplan,active"
```

### TUI Browser
```bash
# Launch interactive browser
emdx gui

# Navigation
# - Documents (default): manage knowledge base
# - Files (f): browse filesystem with preview
# - Git (d): visual diff viewer, worktree switching  
# - Logs (l): execution monitoring
```

## 🔧 **Configuration**

- **Database**: `~/.emdx/emdx.db` (created automatically)
- **GitHub Integration**: Set `GITHUB_TOKEN` or use `gh auth login`
- **Editor**: Set `EDITOR` environment variable for external editing

## 🤝 **Contributing**

See [Development Setup](docs/development-setup.md) for:
- Installation with Poetry
- Code quality tools
- Testing guidelines
- Architecture patterns

## 📄 **License**

MIT License - see LICENSE file for details.

---

**Quick Links**: [Installation](#-quick-start) • [Documentation](docs/) • [CLI Reference](docs/cli-api.md) • [Contributing](docs/development-setup.md)