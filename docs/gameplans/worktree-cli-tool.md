# Gameplan: Git Worktree Management CLI Tool

**Status:** 🚀 Active
**Type:** 🎯 Feature Implementation
**Created:** 2026-01-17

## Executive Summary

Build a comprehensive CLI tool (`emdx worktree`) that helps developers manage git worktrees more efficiently. The tool will provide intuitive commands for creating, listing, switching, and cleaning up worktrees, with smart defaults and project-aware behavior that integrates naturally into the existing EMDX ecosystem.

## Problem Statement

Git worktrees are powerful but the native `git worktree` commands are verbose and require manual path management:

1. **Creation friction**: `git worktree add -b branch-name ../project-worktrees/branch-name origin/main` is tedious
2. **Path management**: Developers must manually track where worktrees live
3. **No project awareness**: Native git doesn't understand multi-worktree project layouts
4. **Cleanup complexity**: Orphaned worktrees and stale branches accumulate
5. **Context switching**: No easy way to see all worktrees and jump between them

## Goals

1. **Simplify worktree creation**: `emdx worktree create feature-auth` should "just work"
2. **Project-aware defaults**: Automatically use `~/dev/worktrees/` with smart naming
3. **Visual status overview**: See all worktrees, their branches, and status at a glance
4. **Safe cleanup**: Identify and remove stale worktrees with confirmation
5. **Quick navigation**: Generate shell commands or integrate with cd/jump utilities

## Non-Goals

- Replacing the full git worktree API (we wrap, not replace)
- Cross-repository worktree management (focus on single project)
- GUI/TUI interface (CLI only for this iteration)
- Automated conflict resolution

---

## Technical Design

### Architecture Overview

```
emdx/
├── commands/
│   └── worktree.py          # NEW: CLI command definitions
├── services/
│   └── worktree_manager.py  # NEW: Business logic layer
├── utils/
│   └── git_ops.py           # EXTEND: Add worktree operations
└── config/
    └── constants.py         # EXTEND: Add worktree defaults
```

### Leveraging Existing Code

The codebase already has significant worktree infrastructure:

1. **`emdx/utils/git_ops.py`** - Already contains:
   - `GitWorktree` dataclass
   - `GitProject` dataclass
   - `get_worktrees()` - List worktrees with porcelain parsing
   - `create_worktree()` - Basic creation with auto-path
   - `remove_worktree()` - Basic removal
   - `discover_projects_from_main_repos()` - Project discovery

2. **`emdx/workflows/worktree_pool.py`** - Contains:
   - `WorktreePool` class for parallel execution
   - Async worktree creation/cleanup patterns

### Command Structure

```bash
# Core commands
emdx worktree create <name> [--from <branch>] [--path <path>]
emdx worktree list [--all] [--json]
emdx worktree remove <name-or-path> [--force]
emdx worktree status [<name-or-path>]

# Navigation helpers
emdx worktree cd <name>          # Print cd command (use with: cd $(emdx worktree cd foo))
emdx worktree path <name>        # Just print the path

# Maintenance
emdx worktree prune              # Clean up stale worktree references
emdx worktree gc [--dry-run]     # Find and optionally remove orphaned worktrees
```

---

## Implementation Plan

### Phase 1: Core Service Layer

**File:** `emdx/services/worktree_manager.py`

Create a service class that encapsulates worktree operations with smart defaults:

```python
@dataclass
class WorktreeConfig:
    """Configuration for worktree operations."""
    worktree_base_dir: Path = Path.home() / "dev" / "worktrees"
    naming_pattern: str = "{project}-{branch}"  # e.g., "emdx-feature-auth"
    default_base_branch: str = "main"

class WorktreeManager:
    """High-level worktree management with smart defaults."""

    def __init__(self, repo_path: Optional[str] = None, config: Optional[WorktreeConfig] = None):
        self.repo_path = repo_path or get_repository_root()
        self.config = config or WorktreeConfig()
        self.project_name = Path(self.repo_path).name

    def create(self, name: str, base_branch: Optional[str] = None, path: Optional[str] = None) -> WorktreeResult:
        """Create a new worktree with smart path generation."""

    def list(self, include_main: bool = True) -> List[WorktreeInfo]:
        """List all worktrees with enhanced info."""

    def remove(self, identifier: str, force: bool = False) -> WorktreeResult:
        """Remove worktree by name or path."""

    def find(self, identifier: str) -> Optional[WorktreeInfo]:
        """Find worktree by partial name match."""

    def get_status(self, identifier: Optional[str] = None) -> WorktreeStatus:
        """Get detailed status for worktree(s)."""

    def prune(self) -> PruneResult:
        """Clean up stale worktree references."""

    def gc(self, dry_run: bool = True) -> GCResult:
        """Find orphaned worktrees for cleanup."""
```

**Key Features:**

1. **Smart Path Generation**
   - Default: `~/dev/worktrees/{project}-{branch}`
   - Customizable via config
   - Handles special characters in branch names

2. **Fuzzy Matching**
   - `emdx worktree remove auth` finds `emdx-feature-auth`
   - Match by branch name, worktree name, or partial path

3. **Enhanced Status Info**
   - Uncommitted changes count
   - Behind/ahead of remote
   - Last accessed timestamp
   - Stale branch detection

### Phase 2: CLI Commands

**File:** `emdx/commands/worktree.py`

```python
import typer
from rich.table import Table
from emdx.services.worktree_manager import WorktreeManager
from emdx.utils.output import console

app = typer.Typer(help="Manage git worktrees efficiently")

@app.command()
def create(
    name: str = typer.Argument(..., help="Branch/worktree name"),
    from_branch: Optional[str] = typer.Option(None, "--from", "-f", help="Base branch"),
    path: Optional[str] = typer.Option(None, "--path", "-p", help="Custom worktree path"),
    cd: bool = typer.Option(False, "--cd", help="Print cd command after creation"),
):
    """Create a new worktree with smart defaults."""

@app.command("list")
def list_cmd(
    all_projects: bool = typer.Option(False, "--all", "-a", help="Show all projects"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List worktrees for current project."""

@app.command()
def remove(
    identifier: str = typer.Argument(..., help="Worktree name, branch, or path"),
    force: bool = typer.Option(False, "--force", "-f", help="Force removal"),
    delete_branch: bool = typer.Option(False, "--delete-branch", "-D", help="Also delete the branch"),
):
    """Remove a worktree."""

@app.command()
def status(
    identifier: Optional[str] = typer.Argument(None, help="Specific worktree (default: all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed info"),
):
    """Show worktree status with git info."""

@app.command()
def path(
    identifier: str = typer.Argument(..., help="Worktree name or branch"),
):
    """Print worktree path (for scripting)."""

@app.command()
def cd(
    identifier: str = typer.Argument(..., help="Worktree name or branch"),
):
    """Print cd command for shell integration."""

@app.command()
def prune():
    """Remove stale worktree references."""

@app.command()
def gc(
    dry_run: bool = typer.Option(True, "--dry-run/--execute", help="Preview vs execute"),
    days: int = typer.Option(30, "--days", "-d", help="Consider stale after N days"),
):
    """Find and clean up orphaned/stale worktrees."""
```

### Phase 3: Enhanced Features

#### 3.1 Status Display

Rich table output showing:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ emdx worktrees (4 total)                                                     │
├──────────────────────┬────────────────┬─────────┬───────────┬───────────────┤
│ Name                 │ Branch         │ Status  │ Changes   │ Path          │
├──────────────────────┼────────────────┼─────────┼───────────┼───────────────┤
│ emdx-main          ★ │ main           │ clean   │           │ ~/dev/emdx    │
│ emdx-gas-town        │ gas-town-reven │ clean   │           │ ~/dev/workt.. │
│ emdx-feature-auth    │ feature-auth   │ dirty   │ 3M 1?     │ ~/dev/workt.. │
│ emdx-fix-search      │ fix-search     │ ahead 2 │           │ ~/dev/workt.. │
└──────────────────────┴────────────────┴─────────┴───────────┴───────────────┘
★ = current worktree | M = modified | ? = untracked
```

#### 3.2 Shell Integration

Generate shell functions for seamless navigation:

```bash
# Add to ~/.zshrc or ~/.bashrc
eval "$(emdx worktree shell-init)"

# Enables:
wt() { cd "$(emdx worktree path "$1")" }
wtc() { emdx worktree create "$@" && cd "$(emdx worktree path "$1")" }
wtl() { emdx worktree list "$@" }
wtr() { emdx worktree remove "$@" }
```

#### 3.3 Fuzzy Matching

Support partial name matching for convenience:

```bash
# All equivalent (assuming emdx-feature-auth exists):
emdx worktree cd feature-auth
emdx worktree cd auth
emdx worktree cd emdx-feature-auth
```

#### 3.4 Garbage Collection

Identify stale worktrees based on:
- No git activity in N days
- Branch merged to main
- Branch deleted from remote
- Orphaned directories without valid git link

### Phase 4: Integration

#### 4.1 Register in Main CLI

**File:** `emdx/main.py`

```python
from emdx.commands import worktree

app.add_typer(worktree.app, name="worktree", help="Manage git worktrees efficiently")
```

#### 4.2 Configuration Constants

**File:** `emdx/config/constants.py`

```python
# Worktree Management
DEFAULT_WORKTREE_BASE_DIR = "~/dev/worktrees"
DEFAULT_WORKTREE_NAMING_PATTERN = "{project}-{branch}"
WORKTREE_STALE_DAYS = 30
WORKTREE_GC_KEEP_MAIN = True
```

---

## Detailed Task Breakdown

### Tasks

| # | Task | Est. Complexity | Dependencies |
|---|------|-----------------|--------------|
| 1 | Create `WorktreeConfig` dataclass | Low | - |
| 2 | Create `WorktreeManager` service class skeleton | Medium | 1 |
| 3 | Implement `create()` with smart path generation | Medium | 2 |
| 4 | Implement `list()` with enhanced status info | Medium | 2 |
| 5 | Implement `find()` with fuzzy matching | Medium | 2 |
| 6 | Implement `remove()` with branch deletion option | Low | 2, 5 |
| 7 | Implement `get_status()` with git status parsing | Medium | 2 |
| 8 | Implement `prune()` wrapper | Low | 2 |
| 9 | Implement `gc()` with stale detection | Medium | 2, 7 |
| 10 | Create CLI `worktree.py` with Typer commands | Medium | 2-9 |
| 11 | Implement Rich table output for `list` | Low | 10 |
| 12 | Implement `shell-init` command | Low | 10 |
| 13 | Add worktree constants to config | Low | - |
| 14 | Register commands in `main.py` | Low | 10 |
| 15 | Write unit tests for WorktreeManager | Medium | 2-9 |
| 16 | Write integration tests for CLI | Medium | 10-14 |
| 17 | Update documentation | Low | All |

### Implementation Order

1. **Foundation** (Tasks 1, 2, 13, 14)
   - Set up the basic structure and registration

2. **Core Operations** (Tasks 3, 4, 6, 10, 11)
   - Create, list, remove - the essentials

3. **Enhanced Features** (Tasks 5, 7, 8, 9)
   - Fuzzy matching, status, maintenance

4. **Polish** (Tasks 12, 15, 16, 17)
   - Shell integration, tests, docs

---

## Data Models

### WorktreeInfo (Enhanced)

```python
@dataclass
class WorktreeInfo:
    """Enhanced worktree information."""
    path: str
    branch: str
    commit: str
    is_current: bool
    is_main: bool

    # Enhanced fields
    project_name: str
    display_name: str  # Shortened name for display

    # Git status
    modified_count: int = 0
    untracked_count: int = 0
    staged_count: int = 0
    ahead: int = 0
    behind: int = 0

    # Metadata
    last_accessed: Optional[datetime] = None
    is_stale: bool = False

    @property
    def status_summary(self) -> str:
        """Human-readable status summary."""
        parts = []
        if self.modified_count:
            parts.append(f"{self.modified_count}M")
        if self.untracked_count:
            parts.append(f"{self.untracked_count}?")
        if self.ahead:
            parts.append(f"↑{self.ahead}")
        if self.behind:
            parts.append(f"↓{self.behind}")
        return " ".join(parts) or "clean"
```

### WorktreeResult

```python
@dataclass
class WorktreeResult:
    """Result of a worktree operation."""
    success: bool
    message: str
    worktree: Optional[WorktreeInfo] = None
    path: Optional[str] = None
    error: Optional[str] = None
```

---

## Error Handling

| Scenario | Handling |
|----------|----------|
| Not in a git repo | Clear error message with suggestion |
| Worktree name already exists | Offer to cd to existing or use different name |
| Branch already exists | Ask to reuse existing branch or create new |
| Dirty worktree on remove | Require --force flag with warning |
| Path already exists | Error with suggestion to use different path |
| Network errors (fetch) | Graceful degradation, show local info |

---

## Testing Strategy

### Unit Tests

```python
class TestWorktreeManager:
    def test_smart_path_generation(self):
        """Test that paths are generated correctly."""

    def test_fuzzy_matching(self):
        """Test partial name matching."""

    def test_stale_detection(self):
        """Test identification of stale worktrees."""
```

### Integration Tests

```python
class TestWorktreeCLI:
    def test_create_and_list(self):
        """Create worktree and verify it appears in list."""

    def test_remove_with_force(self):
        """Remove dirty worktree with force flag."""
```

---

## Success Criteria

1. **Create workflow**: `emdx worktree create feature-x` creates worktree in <2 seconds
2. **List clarity**: Clear visual distinction between current, clean, dirty worktrees
3. **Fuzzy matching**: 90%+ of reasonable partial matches resolve correctly
4. **Safe defaults**: No data loss without explicit --force flags
5. **Integration**: Works seamlessly with existing EMDX workflows

---

## Future Enhancements (Out of Scope)

- TUI browser for worktrees (like `emdx gui`)
- Automatic stale worktree notifications
- Integration with GitHub PRs (show PR status per worktree)
- Worktree templates (pre-configured setups)
- Multi-repo worktree management

---

## References

- [Git Worktree Documentation](https://git-scm.com/docs/git-worktree)
- Existing code: `emdx/utils/git_ops.py`
- Existing code: `emdx/workflows/worktree_pool.py`
- EMDX CLI patterns: `emdx/commands/tasks.py`, `emdx/commands/delegate.py`

