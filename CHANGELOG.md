# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[0.5.0]: https://github.com/arockwell/emdx/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/arockwell/emdx/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/arockwell/emdx/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/arockwell/emdx/compare/v0.2.1...v0.3.1
[0.2.1]: https://github.com/arockwell/emdx/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/arockwell/emdx/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/arockwell/emdx/releases/tag/v0.1.0