# EMDX - Knowledge Base CLI Tool

## 🧪 Git Diff Browser Testing (2025-07-14)
Test the new git diff browser functionality:
- Press 'd' in TUI to enter git diff browser mode
- Press 'w' to switch worktrees interactively
- Use j/k to navigate between changed files

## ⚠️ CRITICAL BUG: Interactive Commands (2025-07-13)

**NEVER run these commands as they will hang Claude Code:**
- `emdx gui` - Interactive TUI browser
- `emdx tui` - Alternative TUI interface
- `emdx gui`
- `emdx tui`
- Any command that opens an interactive terminal UI

**KNOWN BUG**: As of July 2025, Claude Code's deny rules are NOT working. Even with:
- Explicit deny patterns in settings.json
- PreToolUse hooks
- Multiple pattern formats

These commands STILL execute and hang the session. This is a critical bug in Claude Code's permission system.

**WORKAROUND**: Simply don't ask Claude to run these commands until the bug is fixed.

## Project Overview

EMDX is a powerful command-line knowledge base and documentation management system built in Python. It provides full-text search, tagging, project organization, and multiple interfaces (CLI, TUI, web) for managing and accessing your knowledge base.

## Architecture

### Core Components
- **CLI Interface** (`emdx/main.py`) - Main entry point and command orchestration
- **Database Layer** (`emdx/database/`) - Modular SQLite with FTS5 full-text search
- **Core Operations** (`emdx/commands/core.py`) - Save, find, view, edit, delete operations
- **Tagging System** (`emdx/models/tags.py`, `emdx/commands/tags.py`) - Tag management and search
- **Emoji Aliases** (`emdx/utils/emoji_aliases.py`) - Text-to-emoji alias system
- **Browse Commands** (`emdx/commands/browse.py`) - List, stats, recent documents
- **TUI Browser** (`emdx/ui/textual_browser.py`) - Interactive terminal interface
- **Integrations** (`emdx/commands/gist.py`, `emdx/ui/nvim_wrapper.py`) - External tool integrations

### Key Features
- **Full-text search** with SQLite FTS5 and fuzzy matching
- **Emoji tag system** with intuitive text aliases (gameplan→🎯, active→🚀)
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
1. Add command function to appropriate module in `commands/` directory
2. Register with typer app in the module
3. Include in main CLI app (`main.py`)
4. Add tests in corresponding test file
5. Update help documentation

### Database Changes
1. Create migration function in `emdx/database/migrations.py`
2. Add to MIGRATIONS list with incremented version
3. Test migration with existing databases
4. Update database methods in `database/` modules as needed

### UI Changes (TUI Browser)
1. Modify `ui/textual_browser.py`
2. Update CSS styling in class definitions
3. Add key bindings in BINDINGS list
4. Test with various document sets and edge cases

### Adding Emoji Aliases
1. Update `utils/emoji_aliases.py` with new alias mappings
2. Test alias expansion across CLI and TUI interfaces
3. Update legend display and documentation
4. Add comprehensive test coverage

### External Integrations
1. Add new integration module (follow `gist.py` pattern)
2. Use subprocess for external tool calls
3. Add proper error handling and user feedback
4. Mock external dependencies in tests

## Key Files and Their Purpose

### Core System
- `emdx/main.py` - Main CLI entry point, command routing
- `emdx/commands/core.py` - Core CRUD operations (save, find, view, edit, delete)
- `emdx/database/` - Modular database layer (connection, documents, search)
- `emdx/config/` - Configuration management

### User Interfaces
- `emdx/commands/browse.py` - Browse commands (list, recent, stats, projects)
- `emdx/ui/textual_browser.py` - Interactive TUI with vim-like keybindings
- `emdx/ui/gui.py` - Simple GUI wrapper (basic implementation)

### Feature Modules
- `emdx/models/tags.py` - Tag data operations and search
- `emdx/commands/tags.py` - Tag management CLI commands
- `emdx/utils/emoji_aliases.py` - Emoji alias system (NEW!)
- `emdx/commands/gist.py` - GitHub Gist integration
- `emdx/ui/nvim_wrapper.py` - Neovim integration for editing

### Utilities and UI Components
- `emdx/utils/git.py` - Git project detection, file utilities
- `emdx/ui/formatting.py` - Tag display and formatting
- `emdx/ui/markdown_config.py` - Markdown rendering configuration
- `emdx/ui/mdcat_renderer.py` - External mdcat tool integration
- `emdx/database/migrations.py` - Database schema migrations

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
# Install with pipx (recommended for global CLI usage)
pipx install -e . --python python3.13
emdx --help

# Or with poetry (for development)
poetry install
poetry run emdx --help

# Or with pip in a virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -e .
emdx --help

# Run tests
pytest
# or
poetry run pytest
```

### Useful Commands
```bash
# Save content (IMPORTANT: Use stdin for text, not direct strings)
emdx save document.md                                  # Save file
echo "My document content" | emdx save --title "Doc"  # CORRECT: Save text via stdin
echo "content" | emdx save --title "Piped"            # Save from stdin
emdx save file.md --title "Custom Title"              # Save with custom title

# Search and browse (using text aliases!)
emdx find "search terms"                               # Full-text search
emdx find --tags "gameplan,refactor"                   # Search by text aliases
emdx legend                                            # View emoji legend and aliases
emdx gui                                               # Interactive TUI browser

# View and edit
emdx view 123                                          # View by ID
emdx edit 123                                          # Edit in your editor
emdx recent                                            # Show recent documents
emdx list                                              # List all documents

# Emoji tag management with text aliases!
emdx tag 123 gameplan refactor active                  # Add tags via aliases
emdx untag 123 refactor                                # Remove tag
emdx tags                                              # List all tags
emdx legend                                            # View emoji legend and aliases
emdx find --tags "🎯,active"                           # Mixed emoji/alias usage

# Statistics
emdx stats                                             # Overall stats
emdx project-stats                                     # Detailed project breakdown
emdx projects                                          # List all projects

# Cleanup and maintenance
emdx trash                                             # View deleted documents
emdx restore 123                                       # Restore from trash
emdx delete 123                                        # Soft delete to trash
```

### ⚠️ Critical Save Syntax
**WRONG:** `emdx save "text content"` - This creates empty documents!
**RIGHT:** `echo "text content" | emdx save --title "My Title"`

The wrong syntax was causing ~40 empty documents because emdx was looking for a file named "text content" that didn't exist.

This project emphasizes clean architecture, comprehensive testing, and user-friendly interfaces while maintaining high code quality standards.

## Vim Editing Mode

### In-Place Vim Editor (NEW!)

EMDX TUI now features a complete vim-like editing mode accessible by pressing 'e' on any document:

#### Core Features
- **Full modal editing**: NORMAL, INSERT, VISUAL, and VISUAL LINE modes
- **Complete vim command set**: h/j/k/l, w/b/e, 0/$, gg/G, i/a/I/A/o/O, x/dd/yy/p
- **Repeat counts**: 3j, 5w, 2dd, etc.
- **Smart dual ESC**: INSERT→NORMAL→EXIT edit mode
- **Color-coded status**: Shows current mode with visual indicators
- **Seamless integration**: No external editor needed

#### Implementation Architecture
- `VimEditTextArea` extends Textual's TextArea with vim behavior
- Modal key routing based on current vim mode
- Reactive state management for UI updates
- Direct text manipulation for reliable operations
- Comprehensive error handling and boundary checks

#### User Experience Philosophy
- **Starts in INSERT mode** - Users expect to type immediately
- **Progressive vim adoption** - Casual users stay in INSERT, power users use NORMAL
- **Clear visual feedback** - Status bar shows mode and pending commands
- **Backward compatible** - Existing code continues to work

This implementation demonstrates how good architecture enables rapid feature development - the vim mode was implemented in a single session by leveraging existing modal patterns.

## Claude Code Workflow Integration

### Auto-Tagging for Project Management

When working with EMDX through Claude Code, automatically apply tags to documents based on content patterns to enable sophisticated project tracking and success analytics.

#### Core Tagging Taxonomy

Use these minimal, space-efficient tags:

**Document Types:**
- `gameplan` - Strategic plans and approaches
- `analysis` - Investigation results
- `notes` - General notes and observations

**Workflow Status:**
- `active` - Currently working on
- `done` - Completed
- `blocked` - Stuck/waiting

**Outcomes (Success Tracking):**
- `success` - Worked as intended
- `failed` - Didn't work
- `partial` - Mixed results

**Technical Work:**
- `refactor` - Code improvement
- `test` - Testing work
- `bug` - Bug fixes
- `feature` - New functionality

**Priority (Optional):**
- `urgent` - Do now
- `low` - When time permits

#### Auto-Tagging Rules

Apply tags automatically based on these patterns:

1. **Title Detection:**
   - "Gameplan:" → `gameplan, active`
   - "Analysis:" → `analysis`
   - Test-related content → `test`
   - Refactoring work → `refactor`

2. **Content Analysis:**
   - Completion language → `done, success/failed`
   - Blocking language → `blocked`
   - Bug descriptions → `bug`
   - Feature requests → `feature`

3. **Conservative Approach:**
   - Only tag obvious patterns
   - Ask permission for ambiguous cases
   - Suggest tags instead of auto-applying when uncertain

#### Workflow Examples

**Gameplan Lifecycle:**
```bash
# Create gameplan
emdx save "Gameplan: Add user authentication" --tags "gameplan,active"

# Update when blocked
emdx tag 123 blocked

# Mark complete with outcome
emdx tag 123 done success
emdx untag 123 active blocked
```

**Success Analytics:**
```bash
# Track gameplan success rates
emdx find "tags:gameplan,success"    # Successful plans
emdx find "tags:gameplan,failed"     # Failed plans
emdx find "tags:active"              # Current work
emdx find "tags:blocked"             # Stuck items
```

#### Integration Guidelines

When Claude Code helps with EMDX:

1. **Suggest tags** during save operations based on content
2. **Ask permission** before applying tags: "I detected this looks like a gameplan, should I tag it as `gameplan, active`?"
3. **Update tags** when project status changes
4. **Generate progress reports** from tag analytics
5. **Maintain minimal taxonomy** - resist adding too many tags

This enables powerful project management and success tracking while keeping the tag system simple and space-efficient in the GUI.
