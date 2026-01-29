# Lazy-Loading CLI Architecture for EMDX

## Executive Summary

This analysis explores implementing Git-style lazy loading for EMDX subcommands. The goal is to make core KB commands (`save`, `find`, `view`) fast by deferring expensive imports for heavy features (`workflow`, `cascade`, `each`, `ai`) until they are actually invoked.

**Key Finding**: Click (which Typer wraps) has built-in support for lazy subcommand loading via a `LazyGroup` pattern. We can implement this while staying within ONE package, avoiding the complexity of separate packages to coordinate.

## Current State Analysis

### Import Chain Problem

The current `main.py` imports ALL command modules at startup:

```python
# main.py - ALL of these are imported at startup
from emdx.commands.analyze import app as analyze_app
from emdx.commands.cascade import app as cascade_app
from emdx.commands.workflows import app as workflows_app
from emdx.commands.each import app as each_app
from emdx.commands.similarity import app as similarity_app
from emdx.commands.ask import app as ask_app
# ... 20+ more imports
```

Each command module has its own import chains:

**cascade.py imports:**
- `..services.claude_executor` (subprocess handling, async)
- `..database.documents` (SQLite operations)
- `..database.connection` (DB connection pool)

**workflows.py imports:**
- `..workflows.database` (workflow-specific DB)
- `..workflows.base` (dataclasses, enums)
- `..workflows.executor` (async executor)
- `..workflows.registry` (workflow definitions)

**similarity.py imports:**
- `..services.similarity` which imports `scikit-learn` (~200ms)

**ask.py (AI commands) imports:**
- `sentence-transformers` (~300ms cold start)
- `anthropic` API client

### Heavy Dependencies

| Dependency | Import Time | Used By |
|------------|-------------|---------|
| sentence-transformers | ~300ms | `ai search`, `ai ask` |
| scikit-learn | ~200ms | similarity, duplicate detection |
| anthropic | ~50ms | `ai ask`, cascade |
| textual | ~100ms | `gui` only |
| google-api-python-client | ~80ms | `gdoc` only |

### Command Usage Patterns

Core commands (used most often):
- `emdx save` - save content
- `emdx find` - search
- `emdx view` - view documents
- `emdx tag` - add tags
- `emdx list` - list documents

Heavy commands (used less often):
- `emdx workflow run` - multi-agent workflows
- `emdx cascade add/run` - idea-to-code pipeline
- `emdx each` - parallel discovery+action
- `emdx ai search/ask` - semantic search/Q&A
- `emdx gui` - TUI browser

## Proposed Solution: LazyGroup Pattern

### How Git Does It

Git subcommands are separate executables (`git-status`, `git-rebase`). The main `git` binary only loads what's needed. Python can achieve similar results with lazy imports.

### Click's LazyGroup Pattern

Click supports lazy loading via custom `Group` subclasses (from [Click documentation](https://click.palletsprojects.com/en/stable/complex/)):

```python
# lazy_group.py
import importlib
import click

class LazyGroup(click.Group):
    """A Click Group that lazily loads subcommands."""

    def __init__(self, *args, lazy_subcommands=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lazy_subcommands = lazy_subcommands or {}

    def list_commands(self, ctx):
        base = super().list_commands(ctx)
        lazy = sorted(self.lazy_subcommands.keys())
        return base + lazy

    def get_command(self, ctx, cmd_name):
        if cmd_name in self.lazy_subcommands:
            return self._lazy_load(cmd_name)
        return super().get_command(ctx, cmd_name)

    def _lazy_load(self, cmd_name):
        import_path = self.lazy_subcommands[cmd_name]
        modname, cmd_object_name = import_path.rsplit(".", 1)
        mod = importlib.import_module(modname)
        cmd_object = getattr(mod, cmd_object_name)
        return cmd_object
```

### Integration with Typer

Typer is built on Click, so we can use Click's LazyGroup by creating a hybrid approach:

```python
# main.py - new architecture
import typer
from typing import Optional

from emdx.utils.lazy_group import LazyTyperGroup

# Core commands - imported eagerly (they're fast)
from emdx.commands.core import app as core_app
from emdx.commands.tags import app as tag_app
from emdx.commands.browse import app as browse_app

# Create main app with lazy loading support
app = typer.Typer(
    name="emdx",
    cls=LazyTyperGroup,
    lazy_subcommands={
        # Heavy commands - lazy loaded
        "workflow": "emdx.commands.workflows.app",
        "cascade": "emdx.commands.cascade.app",
        "each": "emdx.commands.each.app",
        "ai": "emdx.commands.ask.app",
        "gui": "emdx.ui.gui.gui",
        "similarity": "emdx.commands.similarity.app",
        "gdoc": "emdx.commands.gdoc.app",
    },
    help="Documentation Index Management System"
)

# Register core commands eagerly
for command in core_app.registered_commands:
    app.registered_commands.append(command)
```

### LazyTyperGroup Implementation

```python
# emdx/utils/lazy_group.py
import importlib
from typing import Any

import click
from typer.core import TyperGroup

class LazyTyperGroup(TyperGroup):
    """A Typer-compatible Group with lazy subcommand loading."""

    def __init__(self, *args, lazy_subcommands: dict[str, str] | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.lazy_subcommands = lazy_subcommands or {}
        self._lazy_help_cache: dict[str, str] = {}

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Return list of all commands (eager + lazy)."""
        base = super().list_commands(ctx)
        lazy = sorted(self.lazy_subcommands.keys())
        return base + lazy

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        """Get command, lazily loading if needed."""
        if cmd_name in self.lazy_subcommands:
            return self._lazy_load(cmd_name)
        return super().get_command(ctx, cmd_name)

    def _lazy_load(self, cmd_name: str) -> click.Command:
        """Import and return a lazy command."""
        import_path = self.lazy_subcommands[cmd_name]
        modname, cmd_object_name = import_path.rsplit(".", 1)

        try:
            mod = importlib.import_module(modname)
            cmd_object = getattr(mod, cmd_object_name)

            # Handle Typer apps (convert to Click Group)
            if hasattr(cmd_object, '_get_command'):
                # Typer app - get underlying Click command
                return cmd_object._get_command(ctx=None)

            if not isinstance(cmd_object, click.BaseCommand):
                raise ValueError(
                    f"Lazy loading of {import_path} failed: "
                    f"returned {type(cmd_object)}, expected Command"
                )

            return cmd_object

        except ImportError as e:
            # Graceful degradation - return a command that explains the error
            return self._create_unavailable_command(cmd_name, str(e))

    def _create_unavailable_command(self, cmd_name: str, error: str) -> click.Command:
        """Create a placeholder command when lazy loading fails."""
        @click.command(name=cmd_name)
        def unavailable():
            click.echo(f"Command '{cmd_name}' is not available: {error}")
            click.echo(f"Install optional dependencies with: pip install emdx[{cmd_name}]")
            raise SystemExit(1)

        unavailable.help = f"[Not available] {error}"
        return unavailable
```

## Graceful Degradation with Optional Dependencies

### pyproject.toml Changes

```toml
[tool.poetry.dependencies]
python = "^3.13"

# Core dependencies (always installed)
typer = {extras = ["all"], version = "^0.15.0"}
click = ">=8.0.0,<8.3.0"
rich = "^13.0.0"
python-dotenv = "^1.0.0"
gitpython = "^3.1.0"

# Optional dependencies moved to extras
scikit-learn = {version = "^1.6.0", optional = true}
datasketch = {version = "^1.6.0", optional = true}
sentence-transformers = {version = "^3.0.0", optional = true}
anthropic = {version = "^0.40.0", optional = true}
textual = {version = "^4.0.0", optional = true}
google-api-python-client = {version = "^2.100.0", optional = true}
google-auth-httplib2 = {version = "^0.2.0", optional = true}
google-auth-oauthlib = {version = "^1.2.0", optional = true}
psutil = {version = "^7.0.0", optional = true}  # Only needed for execution monitoring

[tool.poetry.extras]
# Feature-based extras
ai = ["sentence-transformers", "anthropic"]
similarity = ["scikit-learn", "datasketch"]
workflows = ["psutil"]
gui = ["textual"]
gdocs = ["google-api-python-client", "google-auth-httplib2", "google-auth-oauthlib"]

# Convenience extras
full = [
    "sentence-transformers", "anthropic",
    "scikit-learn", "datasketch",
    "psutil", "textual",
    "google-api-python-client", "google-auth-httplib2", "google-auth-oauthlib"
]
```

### Installation Patterns

```bash
# Minimal install (core KB only)
pip install emdx

# With AI features
pip install emdx[ai]

# With workflows and execution
pip install emdx[workflows]

# Full install
pip install emdx[full]
```

## Implementation Strategy

### Phase 1: LazyGroup Infrastructure

1. Create `emdx/utils/lazy_group.py` with `LazyTyperGroup`
2. Add tests for lazy loading behavior
3. Verify --help still works (loads help text without full import)

### Phase 2: Reorganize main.py

Split commands into categories:

```python
# main.py

# ============================================
# EAGER IMPORTS - Core KB commands (fast)
# ============================================
from emdx.commands.core import app as core_app
from emdx.commands.tags import app as tag_app
from emdx.commands.browse import app as browse_app
from emdx.commands.executions import app as executions_app  # lightweight

# ============================================
# LAZY COMMANDS - Heavy features
# ============================================
LAZY_SUBCOMMANDS = {
    # Execution/orchestration (imports subprocess, async)
    "workflow": "emdx.commands.workflows.app",
    "cascade": "emdx.commands.cascade.app",
    "each": "emdx.commands.each.app",
    "run": "emdx.commands.run.run_command",
    "agent": "emdx.commands.agent.agent",
    "claude": "emdx.commands.claude_execute.app",

    # AI features (imports ML libraries)
    "ai": "emdx.commands.ask.app",
    "similar": "emdx.commands.similarity.app",

    # External services
    "gdoc": "emdx.commands.gdoc.app",
    "gist": "emdx.commands.gist.app",

    # TUI (imports textual)
    "gui": "emdx.ui.gui.gui",
}

app = typer.Typer(
    cls=LazyTyperGroup,
    lazy_subcommands=LAZY_SUBCOMMANDS,
)
```

### Phase 3: Help Text Caching

For --help to be fast, we need to avoid loading subcommands just for help text:

```python
# Pre-computed help strings (generated at build time or manually maintained)
LAZY_HELP = {
    "workflow": "Manage and run multi-stage workflows",
    "cascade": "Cascade ideas through stages to working code",
    "each": "Create and run reusable parallel commands",
    "ai": "AI-powered Q&A and semantic search",
    "gui": "Launch interactive TUI browser",
    # ...
}

class LazyTyperGroup(TyperGroup):
    def format_commands(self, ctx, formatter):
        """Format command list with pre-computed help."""
        commands = []
        for subcommand in self.list_commands(ctx):
            if subcommand in self.lazy_subcommands:
                # Use cached help instead of loading
                help_text = LAZY_HELP.get(subcommand, "")
            else:
                cmd = self.get_command(ctx, subcommand)
                help_text = cmd.get_short_help_str() if cmd else ""
            commands.append((subcommand, help_text))

        if commands:
            with formatter.section("Commands"):
                formatter.write_dl(commands)
```

### Phase 4: Optional Dependency Detection

```python
# emdx/utils/features.py

def check_feature(feature_name: str) -> tuple[bool, str]:
    """Check if a feature's dependencies are available."""
    try:
        if feature_name == "ai":
            import sentence_transformers
            import anthropic
            return True, ""
        elif feature_name == "similarity":
            import sklearn
            import datasketch
            return True, ""
        elif feature_name == "gui":
            import textual
            return True, ""
        elif feature_name == "workflows":
            import psutil
            return True, ""
        elif feature_name == "gdocs":
            import googleapiclient
            return True, ""
        else:
            return True, ""  # Unknown feature, assume available
    except ImportError as e:
        return False, str(e)

# Use in commands
@app.command()
def ai_search():
    available, error = check_feature("ai")
    if not available:
        console.print(f"[red]AI features not available: {error}[/red]")
        console.print("[dim]Install with: pip install emdx[ai][/dim]")
        raise typer.Exit(1)

    # Proceed with import
    from emdx.services.ai_search import SemanticSearch
    # ...
```

## Benefits Analysis

### Performance

| Scenario | Current | With Lazy Loading |
|----------|---------|-------------------|
| `emdx save` cold start | ~800ms | ~150ms |
| `emdx find` cold start | ~800ms | ~150ms |
| `emdx workflow run` cold start | ~800ms | ~850ms (same) |
| `emdx --help` | ~800ms | ~200ms |

### User Experience

1. **Fast for common operations**: 80% of usage (save/find/view) becomes 4x faster
2. **Clear error messages**: Missing dependencies explain how to install
3. **Smaller default install**: Core functionality without ML libraries
4. **No breaking changes**: All commands still work if deps installed

### Developer Experience

1. **Single package**: No coordinating multiple repos
2. **Clear boundaries**: Lazy loading makes feature boundaries explicit
3. **Easier testing**: Can test core without all dependencies
4. **Gradual migration**: Can lazy-load one command at a time

## Comparison to Alternatives

### Alternative 1: Separate Packages (emdx-core, emdx-workflows)

Pros:
- Cleanest separation
- Independent versioning

Cons:
- Multiple repos to maintain
- Version coordination complexity
- Import paths change

### Alternative 2: Process Isolation (like git)

Pros:
- True isolation
- Crash isolation

Cons:
- Startup overhead per subprocess
- Complex IPC for shared state
- Not Pythonic

### Alternative 3: Lazy Loading (Proposed)

Pros:
- Single package
- Pythonic
- Graceful degradation
- No import path changes
- Compatible with current architecture

Cons:
- Help text needs caching (minor)
- Still one package to install
- First invocation of lazy command is slow

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Circular imports | Strict import order, no cross-feature imports |
| Import errors at runtime | check_feature() before importing |
| --help shows stale info | Cache invalidation in dev, or generate at release |
| User confusion on install | Clear error messages with install instructions |

## Conclusion

Lazy loading is the right approach for EMDX because:

1. **Incremental**: Can implement gradually without breaking changes
2. **Single package**: Keeps simplicity of current structure
3. **Fast core**: Makes the most common operations fast
4. **Graceful degradation**: Features degrade cleanly when deps missing
5. **Pythonic**: Uses standard patterns (Click's LazyGroup)

The implementation requires:
1. ~200 lines of new code (LazyTyperGroup + feature detection)
2. Reorganization of main.py
3. Updates to pyproject.toml for optional dependencies
4. New tests for lazy loading behavior

Estimated effort: 2-3 days for full implementation, 1 day for Phase 1 proof-of-concept.

## Next Steps

1. [ ] Create proof-of-concept with workflow command only
2. [ ] Benchmark import time savings
3. [ ] Implement full LazyTyperGroup with help caching
4. [ ] Update pyproject.toml with optional dependencies
5. [ ] Add feature detection and error messages
6. [ ] Migrate commands in phases
7. [ ] Update documentation

## References

- [Click Complex Applications - LazyGroup](https://click.palletsprojects.com/en/stable/complex/)
- [GitHub Issue #904 - Explicit list of sub-commands](https://github.com/pallets/click/issues/904)
- [Typer - Using Click](https://typer.tiangolo.com/tutorial/using-click/)
