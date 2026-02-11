# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.12.0] - 2026-02-10

### 🚀 Major Features

#### `emdx delegate` — stdout-friendly parallel execution (#410)
- New command designed for Claude Code to call instead of Task tool sub-agents
- Results print to **stdout** (so the calling session reads them inline) AND persist to the knowledge base
- Supports parallel execution, synthesis, tags, and title options
- Updated CLAUDE.md decision tree to prefer `delegate` over Task tool

#### Optional dependencies and Python 3.11+ support (#408)
- **Core install is now lightweight** — `pip install emdx` no longer pulls in ML/AI packages
- Heavy deps (sklearn, datasketch, anthropic, numpy, sentence-transformers, google-*) moved to optional extras: `[ai]`, `[similarity]`, `[google]`, `[all]`
- Import guards with clear error messages when optional features are used without their extras
- **Python requirement relaxed from ^3.13 to ^3.11**

#### `emdx save --gist` — save and share in one step (#416)
- `--gist`/`--share` flag creates a GitHub gist after saving
- `--secret` and `--public` imply `--gist` so `emdx save "content" --secret` just works
- `--copy`/`-c` copies gist URL to clipboard, `--open`/`-o` opens in browser
- Gist failure is non-fatal — the save always succeeds

### 🔧 Improvements

#### Activity view overhaul
- **Tree widget migration** — replaced DataTable with Tree[ActivityItem] to fix scroll jumping (#406)
- **Column-aligned rows** — activity tree renders as aligned table columns (#413)
- **Descriptive execution titles** — delegate/workflow executions show meaningful names (#411)
- **Deduplication** — synthesis docs no longer appear twice in activity feed (#412)
- **Clean RHS preview** — fixed context panel rendering (#415)

#### Codebase audit (#414)
- Deleted ~4,982 lines of dead code (unused swarm module, orphaned scripts, archived docs)
- Fixed `DEFAULT_ALLOWED_TOOLS` config bug where `TodoRead` was silently lost
- Updated stale model reference to claude-sonnet-4-5-20250929
- Extracted hardcoded config paths into `EMDX_CONFIG_DIR`/`EMDX_LOG_DIR` constants
- Added 532 new tests covering documents, emoji aliases, JSON parsing, title normalization, export destinations, lifecycle tracking, and CLI commands
- Removed ~8,400 LOC of unused TUI components (#405)

### 🐛 Bug Fixes
- **activity**: Restore auto-refresh in activity TUI — async callback was silently never awaited (#417)
- **activity**: Record document source for synthesis docs to prevent duplicates (#412)
- **delegate**: Clean execution titles, deduplicate activity entries (#415)
- **config**: Fix undefined variable `pid` → `execution.pid` in execution monitor
- **db**: Replace blanket `except Exception: pass` with specific types + logging in cascade fallbacks
- **db**: Narrow exception handling in groups.py to `sqlite3.IntegrityError`
- **activity**: Protect against single bad item killing entire activity data load

## [0.10.0] - 2026-02-07

### 🚀 Major Features

#### Agent-to-Agent Mail (`emdx mail`)
- **`emdx mail`** - Point-to-point messaging between teammates' Claude Code agents via GitHub Issues
- `emdx mail setup <org/repo>` - One-time setup: configure mail repo and create labels
- `emdx mail send` - Send messages to GitHub users with optional emdx doc attachments
- `emdx mail inbox` - Check inbox with unread/sender filtering
- `emdx mail read` - Read message threads with auto-save to knowledge base
- `emdx mail reply` - Reply to messages with optional doc attachments and thread closing
- `emdx mail status` - Show mail configuration and unread count
- Label-based routing (`from:user`, `to:user`, `status:unread`/`status:read`)
- Local read receipt tracking via SQLite
- Activity screen integration for mail messages in TUI

### 🔧 Improvements

#### CLI Enhancements
- **Lazy loading** for heavy CLI commands - faster startup time
- **`emdx help`** command as alternative to `--help`
- **Safe mode** with strategic architecture analysis
- Pass `include_archived` param through model layer for list command

#### Cascade & Execution
- Extract cascade metadata to dedicated table for better organization
- Multi-line TextArea for cascade new idea input in TUI

#### Code Quality
- Migrate remaining files to shared Console module
- Update CLI documentation with missing commands

### 🐛 Bug Fixes
- **ui**: Prevent activity view from jumping to cursor on refresh
- **cli**: Pass include_archived param through model layer for list command
- **test**: Remove gui from lazy loading test expectations
- **scripts**: Only update poetry version in release script

### 🗑️ Housekeeping
- Remove completed TECH_DEBT_TASKS.md from repo root

## [0.8.0] - 2025-01-29

### 🚀 Major Features

#### Cascade - Autonomous Idea-to-Code Pipeline
- **`emdx cascade`** - Transform raw ideas into working code through autonomous stages
- Stage flow: idea → prompt → analyzed → planned → done (with PR creation)
- `--auto` flag for continuous processing without manual intervention
- `--analyze` and `--plan` shortcuts for common operations
- New Idea modal in TUI for quick idea capture
- Activity grouping for cascade-related documents

#### Execution System Enhancements
- **`emdx agent`** - Sub-agent execution with automatic EMDX tracking and metadata
- **`emdx each`** - Reusable parallel operations with discovery patterns
- **`emdx run`** - Quick parallel task execution with `--worktree` isolation
- **`emdx prime`** and **`emdx status`** - Native Claude Code integration commands
- `--pr` and `--pr-single` flags for automatic PR creation
- Cursor CLI support with live log streaming
- UnifiedExecutor for consistent execution across all commands

#### AI-Powered Features
- **Semantic search** with local embeddings (sentence-transformers)
- **RAG Q&A system** - Ask questions about your knowledge base
- **`emdx ai context`** - Pipe relevant docs to Claude CLI (uses Max subscription, no API cost!)
- TF-IDF similarity scoring for document relationships

#### TUI Improvements
- **GitHub PR browser** with diff viewer
- **Search screen** with Google-style command palette results
- **Synthesis phase indicator** in workflow execution
- Document titles shown in workflow task queue
- Central keybinding registry with conflict detection
- `?` help modal across all views
- `i` keybinding for quick gist/copy operations
- `d` key for single task deletion in workflow browser

### 🐛 Bug Fixes
- **search**: Escape hyphenated queries in FTS5 search
- **ui**: Prevent Activity Browser flicker when scrolling
- **ui**: Fix GUI keybindings, search selection, and semantic search
- **cascade**: Use detached execution for reliable process management
- **cli**: Add missing DEFAULT_ALLOWED_TOOLS constant
- **db**: Calculate total_tokens and total_cost_usd in group metrics
- **types**: Replace List[Any] with proper GitWorktree type annotations
- **logging**: Add logging to silent exception handlers
- Reduce default max concurrent from 10 to 5
- Replace cryptic mode icons with clearer symbols
- Correct task count display in workflow browser

### ⚡ Performance
- **Fast merge path** in maintenance operations
- Optimized Activity layout rendering

### 🔧 Technical Changes
- Standardized parallelism flag (`-j`) across all CLI commands
- Backward-compatible template aliases (`{{task}}` → `{{item}}`)
- Removed deprecated agent system
- Cleaned up unused tables and dead code
- Removed `--pattern` flag for clearer language

### 📚 Documentation
- Updated CLAUDE.md with execution methods decision tree
- Added documentation for `emdx run` and `emdx ai` commands
- Added examples to `emdx workflow run --help`
- Documented auto-loaded doc variables

## [0.7.0] - 2025-01-28

### 🔥 Major Features Added

#### Execution System Overhaul
- **Event-driven Log Streaming** - Real-time log updates without polling overhead
- **Comprehensive Process Management** - Heartbeat tracking, PID management, and lifecycle monitoring
- **Database Cleanup Tools** - New `emdx maintain cleanup` commands for branches, processes, and executions
- **Enhanced Execution Environment** - Comprehensive validation and better error handling
- **Unique Execution ID Generation** - Better collision detection with UUID components and microsecond precision

#### Test Suite Achievement
- **100% Test Passing Rate** - Complete test suite restoration from broken state
- **Comprehensive Test Coverage** - 172 tests now passing, up from ~50% pass rate
- **Robust Testing Framework** - Fixed auto-tagger, browse, migration, and smart execution tests

### 🏗️ Architecture Improvements

#### Process & Execution Management
- **Heartbeat Mechanism** - 30-second heartbeat updates for execution tracking
- **ExecutionMonitor Service** - Real-time process monitoring and health checks
- **Cleanup Commands** - Automated cleanup of zombie processes, stuck executions, and old branches
- **Enhanced Branch Management** - Better collision detection and unique branch naming

#### Database Enhancements
- **State Consistency** - Fixed 94 stuck 'running' executions in database
- **Execution Lifecycle** - Proper status tracking with timeout handling
- **Directory Management** - Improved temp directory cleanup and collision avoidance

### 🐛 Critical Bug Fixes

#### TUI Stability
- **Delete Key Crash** - Fixed parameter mismatch in DeleteConfirmScreen constructor
- **Git Branch Conflicts** - Resolved branch creation collisions and cleanup issues
- **Process Zombies** - Fixed zombie process accumulation and resource leaks
- **Database Corruption** - Cleaned up inconsistent execution states

#### Log System Improvements
- **Timestamp Preservation** - Maintain original timestamps during real-time streaming
- **Log Browser Performance** - Eliminated polling overhead with event-driven updates
- **Wrapper Coordination** - Fixed log coordination issues by making wrapper sole writer

### 🎨 User Experience Improvements

#### Enhanced Delete Behavior
- **Immediate Deletion** - Removed confirmation modal for faster workflow
- **Cursor Preservation** - Maintain cursor position after document deletion
- **Smart Positioning** - Intelligent cursor adjustment when deleting final document

#### Interface Improvements
- **Better Status Messages** - Clearer feedback for operations and errors
- **Header Visibility** - Restored and improved document browser headers
- **Tab Navigation** - Enhanced Tab navigation in edit mode between title and content
- **Refresh Command** - Restored 'r' key refresh functionality

#### Editor Enhancements
- **Markdown Headers** - Use clean markdown headers instead of unicode boxes
- **Document Creation** - Improved new document experience with better UI flow
- **Edit Mode Stability** - Fixed mounting errors and improved editor lifecycle

### 🔧 Technical Improvements

#### Environment & Tooling
- **Sonnet 4 Upgrade** - Default to claude-sonnet-4-20250514 model
- **Tool Display** - Improved visualization of allowed tools during execution
- **Python Environment** - Better detection and handling of pipx/venv environments
- **Error Recovery** - Enhanced error handling throughout the system

#### Documentation
- **Comprehensive Guides** - Updated testing guide and development documentation
- **Architecture Documentation** - Clean documentation structure in docs/ folder
- **Installation Instructions** - Fixed dependency management and setup process

### 💥 Breaking Changes
- **Delete Behavior** - 'd' key now immediately deletes without confirmation
- **Git Browser** - Moved to 'g' key (from 'd' key which now deletes)
- **Python Requirement** - Requires Python 3.13+ (was 3.9+)

### 🎯 Success Metrics
- **Test Success Rate**: 172/172 tests passing (100%)
- **Performance**: Event-driven log streaming eliminates polling overhead
- **Reliability**: Zero zombie processes and stuck executions after cleanup
- **User Experience**: Immediate delete response with cursor preservation

## [0.6.1] - 2025-07-27

### 🚨 Critical Documentation Fixes

#### Version Consistency
- **Fixed version badge** - Updated README.md badge from 0.6.0 to 0.6.1
- **Fixed Python requirement** - Updated from 3.9+ to 3.13+ (matches pyproject.toml)
- **Updated Black config** - Target version updated from py39 to py313
- **Updated MyPy config** - Python version updated from 3.9 to 3.13

#### Missing Command Documentation
- **Added missing command documentation** for new commands:
  - `emdx exec` - Execution management subcommands
  - `emdx claude` - Claude execution subcommands  
  - `emdx lifecycle` - Document lifecycle tracking
  - `emdx analyze` - Document analysis command
  - `emdx maintain` - Database maintenance command

#### Installation Process
- **Updated development setup** - Reflects Poetry + Just workflow
- **Added Just installation instructions** - Comprehensive setup guide
- **Fixed dependency installation** - Clarified Poetry vs pip usage

#### Architecture Documentation
- **Updated project structure** - Reflects new modular architecture with 27 UI files
- **Added UI component descriptions** - Complete documentation of modular UI system
- **Updated command module structure** - Documents all 11 command modules

### 🎯 Documentation Accuracy
- **Critical fix**: Documentation now accurately reflects actual codebase
- **User experience**: Installation instructions now work correctly
- **Contributor onboarding**: Development setup properly documented

## [0.6.0] - 2025-07-14

### 🔥 Major Features Added

#### File System Integration
- **Yazi-Inspired File Browser** - Built-in file system navigation with vim keybindings
- **File Preview** - Real-time file content preview in file browser
- **Seamless File Editing** - Edit files directly from browser with vim integration

#### Git Integration Enhancements  
- **Git Diff Browser** - Visual git diff viewer with syntax highlighting
- **Worktree Support** - Switch between git worktrees interactively with 'w' key
- **Git Operations** - Enhanced git project detection and repository management

#### Advanced TUI Features
- **Complete Vim Editor** - Full modal editing (NORMAL/INSERT/VISUAL/VISUAL LINE modes)
- **Vim Line Numbers** - Relative line numbers with proper cursor positioning
- **Enhanced Text Selection** - Robust text selection mode with copy/paste
- **Modal Navigation** - Multiple browser modes (documents, files, git diffs)

#### Execution System
- **Claude Execution Integration** - Execute prompts directly from TUI with 'x' key
- **Live Streaming Logs** - Real-time execution log viewer with 'l' key  
- **Execution History** - Track and view all execution attempts
- **Contextual Prompts** - Smart prompt selection based on document content

### 🏗️ Architecture Improvements

#### Modular Refactoring
- **Split Monolithic Browser** - Broke 3,097-line textual_browser.py into focused modules
- **Clean Component Architecture** - Separate modules for file browser, git browser, vim editor
- **Mixin Pattern** - Reusable GitBrowserMixin for git functionality across components

#### Database Enhancements  
- **Modular Database Layer** - Split database operations into focused modules
- **Migration System** - Robust schema migration support
- **Performance Optimizations** - Improved query performance and indexing

### 🐛 Critical Bug Fixes

#### TUI Stability
- **Keyboard Crash Fixes** - Resolved crashes with Ctrl+C, ESC, and modal key handling
- **Selection Mode Stability** - Fixed text selection mode crashes and escape handling
- **Widget Lifecycle** - Proper widget mounting/unmounting to prevent ID conflicts

#### Data Integrity  
- **Empty Documents Bug** - Fixed critical save command bug creating empty documents
- **Tag Display Issues** - Resolved tag formatting and display problems in TUI
- **Database Consistency** - Fixed schema migration issues and data corruption

#### Editor Improvements
- **Vim Line Numbers** - Fixed alignment and positioning issues with relative line numbers
- **Cursor Positioning** - Accurate cursor tracking across edit modes
- **Text Area Integration** - Seamless vim editor integration with Textual framework

### 🎨 User Experience

#### Enhanced UI/UX
- **Clean Mode Indicators** - Minimal, vim-style mode indicators
- **Better Error Handling** - Comprehensive error messages and recovery
- **Responsive Design** - Improved layout and spacing across all modes
- **Visual Feedback** - Real-time status updates and operation confirmation

#### Workflow Improvements
- **Quick Actions** - Fast gist creation with 'g' key in TUI
- **Smart Defaults** - Intelligent mode switching and content detection
- **Keyboard Efficiency** - Comprehensive vim-style keybindings throughout

### 🔧 Developer Experience

#### Code Quality
- **Python 3.9+ Modernization** - Full type annotations using built-in generics
- **Comprehensive Testing** - Expanded test suite with vim editor testing
- **Code Formatting** - Consistent black/ruff formatting throughout codebase
- **Documentation Updates** - Enhanced inline documentation and examples

#### Development Tools
- **justfile Integration** - Streamlined development workflow commands
- **Pre-commit Hooks** - Automated code quality checks
- **CI/CD Improvements** - Enhanced testing and release automation

## [0.5.0] - Previous Release

### Added
- **Vim-like Editing Mode** - Full vim modal editing directly in the TUI preview pane
  - Complete modal system: NORMAL, INSERT, VISUAL, and VISUAL LINE modes
  - Core vim navigation: h/j/k/l, w/b/e (word motions), 0/$ (line), gg/G (document)
  - Mode switching commands: i/a/I/A/o/O (insert variants), v/V (visual modes)
  - Editing operations: x (delete char), dd (delete line), yy (yank), p/P (paste)
  - Repeat count support: 3j, 5w, 2dd etc.
  - Smart dual ESC behavior: INSERT→NORMAL→EXIT edit mode
  - Color-coded status bar showing current vim mode and pending commands
  - Backward compatibility: EditTextArea alias maintains existing functionality

### Changed
- **TUI Edit Mode Enhanced** - Press 'e' now enters vim editing mode instead of external nvim
  - Starts in INSERT mode for immediate text editing
  - Full vim command set available in NORMAL mode
  - Visual feedback with mode indicators in status bar
  - Seamless integration with existing width constraint fixes

## [0.5.0] - 2025-01-10

### Added
- **Seamless nvim Integration** - Zero terminal flash when editing documents
  - External wrapper approach using proper terminal state management
  - Clean exit/restart cycle with signal-based process coordination
  - nvim gets full terminal control without visual artifacts
- **Modern Textual-based GUI** - Complete rewrite of the interactive browser
  - True modal behavior with NORMAL/SEARCH modes (like vim)
  - Vim-style navigation: j/k (up/down), g/G (top/bottom), / (search)
  - Live search with instant document filtering
  - Mouse support with modern textual widgets
  - Modal delete confirmation dialog with y/n shortcuts
  - Full-screen document viewer with vim navigation (j/k, ctrl+d/u, g/G)

### Changed
- **BREAKING**: `emdx gui` now uses textual browser instead of FZF
- **Clean markdown rendering** - Documents show only title + content
  - Removed project/created/views metadata headers
  - Matches mdcat behavior for clean reading experience
  - Both preview pane and full-screen view show consistent formatting

### Removed
- **FZF browser completely removed** - All FZF-related code and dependencies
- **Experimental commands removed**: modal, textual, markdown, seamless, wrapper
- All preview script helpers and leader key implementations

### Technical Details
- New `nvim_wrapper.py` handles terminal state management
- `textual_browser_minimal.py` provides the modal TUI interface
- Uses Textual library for modern terminal UI components
- Rich markdown rendering with syntax highlighting

## [0.4.0] - 2025-01-09

### Added
- **Comprehensive Tag System** - Organize documents with tags
  - Add tags when saving: `emdx save file.md --tags "python,tutorial"`
  - Search by tags: `emdx find --tags "python,api" --any-tags`
  - Tag management commands:
    - `emdx tag <id> [tags...]` - Add/view tags for a document
    - `emdx untag <id> <tags...>` - Remove tags from a document
    - `emdx tags` - List all tags with usage statistics
    - `emdx retag <old> <new>` - Rename a tag globally
    - `emdx merge-tags <tags...> --into <target>` - Merge multiple tags
  - Tags displayed in document view and search results
  - Tag autocomplete and suggestions
  - Database migration system for schema updates

### Changed
- **Simplified Input Interface** - Consolidated 5 capture commands into 1
  - Removed separate commands: `note`, `clip`, `pipe`, `cmd`, `direct`
  - Single `save` command now handles all input methods:
    - Files: `emdx save README.md`
    - Direct text: `emdx save "Quick note"`
    - Stdin: `echo "content" | emdx save --title "My Note"`
    - Clipboard: `pbpaste | emdx save --title "Clipboard"`
    - Command output: `ls -la | emdx save --title "Directory"`
- Improved GUI viewing experience with better markdown rendering
- Enhanced color output support in terminal

### Fixed
- GUI preview pane shell compatibility issues
- Command execution in interactive browser

### Removed
- `emdx/capture.py` module (functionality merged into core.py)

## [0.3.2] - 2025-01-09

### Fixed
- Fix GUI preview pane and command execution
- Make GUI commands shell-agnostic for better compatibility

## [0.3.1] - 2025-01-09

### Added
- GitHub Gist integration for sharing knowledge base entries
  - Create public/private gists from documents
  - Update existing gists
  - List all created gists
  - Copy gist URL to clipboard
  - Open gist in browser
- Edit and delete keybindings in GUI
  - `Ctrl-e` to edit documents
  - `Ctrl-d` to delete documents
  - `Ctrl-r` to restore from trash
  - `Ctrl-t` to toggle trash view

### Fixed
- Database migration order for soft delete columns

## [0.2.1] - 2025-01-08

### Added
- Edit and delete functionality with soft delete support
  - Documents are moved to trash before permanent deletion
  - Restore documents from trash
  - Purge to permanently delete

## [0.2.0] - 2025-01-07

### Added
- Rich pager support for `emdx view` command
- mdcat integration for markdown viewing with automatic pagination
- SQLite migration command for PostgreSQL to SQLite transition

### Changed
- **BREAKING**: Switched from PostgreSQL to SQLite for zero-setup installation
- Database now stored at `~/.config/emdx/knowledge.db`
- Removed all PostgreSQL dependencies

### Fixed
- SQLite datetime parsing

## [0.1.0] - 2025-01-07

### Added
- Initial release
- Core commands: save, find, view, list
- Quick capture: note, clip, pipe, cmd, direct
- Interactive FZF browser (gui)
- Full-text search with FTS5
- Git repository detection
- Project-based organization
- Recent documents tracking
- Statistics command
- JSON/CSV export
- User config file support at `~/.config/emdx/.env`

[0.12.0]: https://github.com/arockwell/emdx/compare/v0.10.0...v0.12.0
[0.10.0]: https://github.com/arockwell/emdx/compare/v0.8.0...v0.10.0
[0.8.0]: https://github.com/arockwell/emdx/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/arockwell/emdx/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/arockwell/emdx/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/arockwell/emdx/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/arockwell/emdx/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/arockwell/emdx/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/arockwell/emdx/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/arockwell/emdx/compare/v0.2.1...v0.3.1
[0.2.1]: https://github.com/arockwell/emdx/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/arockwell/emdx/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/arockwell/emdx/releases/tag/v0.1.0