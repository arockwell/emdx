# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.3.2]: https://github.com/arockwell/emdx/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/arockwell/emdx/compare/v0.2.1...v0.3.1
[0.2.1]: https://github.com/arockwell/emdx/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/arockwell/emdx/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/arockwell/emdx/releases/tag/v0.1.0