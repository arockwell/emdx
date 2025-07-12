# EMDX - Knowledge Base CLI Tool

## Project Overview

EMDX is a powerful command-line knowledge base and documentation management system built in Python. It provides full-text search, tagging, project organization, and multiple interfaces (CLI, TUI, web) for managing and accessing your knowledge base.

## Architecture

### Core Components
- **CLI Interface** (`emdx/cli.py`) - Main entry point and command orchestration
- **Database Layer** (`emdx/sqlite_database.py`) - SQLite with FTS5 full-text search
- **Core Operations** (`emdx/core.py`) - Save, find, view, edit, delete operations
- **Tagging System** (`emdx/tags.py`, `emdx/tag_commands.py`) - Tag management and search
- **Browse Commands** (`emdx/browse.py`) - List, stats, recent documents
- **TUI Browser** (`emdx/textual_browser_minimal.py`) - Interactive terminal interface
- **Integrations** (`emdx/gist.py`, `emdx/nvim_wrapper.py`) - External tool integrations

### Key Features
- **Full-text search** with SQLite FTS5 and fuzzy matching
- **Tag-based organization** with flexible search (all/any tag modes)
- **Project detection** from git repositories
- **Multiple interfaces**: CLI commands, interactive TUI browser
- **GitHub Gist integration** for sharing
- **Neovim integration** for editing
- **Rich formatting** with syntax highlighting and markdown rendering

## Development Guidelines

### Code Standards
- **Python 3.9+** minimum requirement (modern type annotations)
- **Type hints** required for all function signatures using built-in generics (`list[str]`, `dict[str, Any]`)
- **Exception handling** with proper chaining (`raise ... from e`)
- **Rich Console** for user-facing output with consistent formatting
- **Structured error handling** with meaningful messages
- **100 character line limit** for readability

### Testing
- **Pytest** with coverage reporting
- **Test database isolation** using temporary SQLite databases
- **Mock external dependencies** (GitHub API, subprocess calls, file operations)
- **Working test suite** in `tests/` directory with comprehensive coverage

### Database Schema
- **Documents table**: id, title, content, project, created_at, updated_at, accessed_at, access_count, is_deleted, deleted_at
- **Tags system**: tags table + document_tags junction table
- **FTS5 search**: documents_fts virtual table for full-text search
- **Migrations**: Versioned schema changes in `emdx/migrations.py`

## Common Development Tasks

### Adding New Commands
1. Add command function to appropriate module (`core.py`, `browse.py`, etc.)
2. Register with typer app in the module
3. Include in main CLI app (`cli.py`)
4. Add tests in corresponding test file
5. Update help documentation

### Database Changes
1. Create migration function in `emdx/migrations.py`
2. Add to MIGRATIONS list with incremented version
3. Test migration with existing databases
4. Update SQLiteDatabase methods as needed

### UI Changes (TUI Browser)
1. Modify `textual_browser_minimal.py`
2. Update CSS styling in class definitions
3. Add key bindings in BINDINGS list
4. Test with various document sets and edge cases

### External Integrations
1. Add new integration module (follow `gist.py` pattern)
2. Use subprocess for external tool calls
3. Add proper error handling and user feedback
4. Mock external dependencies in tests

## Key Files and Their Purpose

### Core System
- `emdx/cli.py` - Main CLI entry point, command routing
- `emdx/core.py` - Core CRUD operations (save, find, view, edit, delete)
- `emdx/sqlite_database.py` - Database abstraction layer
- `emdx/config.py` - Configuration management

### User Interfaces
- `emdx/browse.py` - Browse commands (list, recent, stats, projects)
- `emdx/textual_browser_minimal.py` - Interactive TUI with vim-like keybindings
- `emdx/gui.py` - Simple GUI wrapper (basic implementation)

### Feature Modules
- `emdx/tags.py` - Tag operations and search
- `emdx/tag_commands.py` - Tag management CLI commands
- `emdx/gist.py` - GitHub Gist integration
- `emdx/nvim_wrapper.py` - Neovim integration for editing

### Utilities
- `emdx/utils.py` - Git project detection, file utilities
- `emdx/markdown_config.py` - Markdown rendering configuration
- `emdx/mdcat_renderer.py` - External mdcat tool integration
- `emdx/migrations.py` - Database schema migrations

## Important Implementation Details

### Database Patterns
- Use `with db.get_connection() as conn:` for database operations
- Enable foreign keys with `PRAGMA foreign_keys = ON` when needed
- Handle datetime conversion between strings and datetime objects
- Use parameterized queries for SQL injection prevention

### Error Handling
- Use typer.Exit(1) for CLI errors with proper error messages
- Chain exceptions with `raise ... from e` for debugging
- Provide user-friendly error messages via Rich Console
- Log technical details for developer debugging

### Search Implementation
- FTS5 for full-text content search
- Tag-based search with "all" and "any" modes
- Project filtering for scoped searches
- Fuzzy matching for typos and partial matches

### TUI Browser Features
- Vim-like navigation (j/k, g/G, /, etc.)
- Live preview of document content
- Tag management (add/remove with visual feedback)
- Search integration with real-time filtering
- Refresh functionality to reload data

## Configuration

### Environment Variables
- `EMDX_DB_PATH` - Custom database location
- `GITHUB_TOKEN` - For Gist integration

### Config Files
- Database auto-created in user's home directory
- Git project detection for automatic project tagging
- Supports both Poetry and pip installation methods

## Troubleshooting

### Common Issues
- **Database locked**: Ensure proper connection management with context managers
- **Missing dependencies**: Check pyproject.toml for required packages
- **Git detection fails**: Verify git repository has remote origin configured
- **TUI display issues**: Check terminal compatibility and color support

### Development Setup
```bash
# Install with poetry (recommended)
poetry install
poetry run emdx --help

# Or with pip
pip install -e .
emdx --help

# Run tests
poetry run pytest
# or
pytest
```

### Useful Commands
```bash
# Save content
emdx save "My document" --tags "python,cli"
echo "content" | emdx save "Piped content"

# Search and browse
emdx find "search terms"
emdx find --tags "python,cli"
emdx browse  # Interactive TUI

# Management
emdx browse recent
emdx browse stats
emdx tag-list
```

This project emphasizes clean architecture, comprehensive testing, and user-friendly interfaces while maintaining high code quality standards.