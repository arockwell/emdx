# Option C: Plugin Architecture for EMDX - Deep Dive Analysis

## Executive Summary

This document explores comprehensive approaches to making EMDX extensible through a plugin architecture. We analyze the current monolithic structure, study successful plugin systems in the Python ecosystem, explore wild experimental ideas, and propose a concrete implementation path with working interface designs.

---

## Part 1: Current EMDX Architecture Analysis

### Command Registration (main.py)

EMDX currently uses **Typer** for CLI command management with three patterns:

1. **Direct Command Registration** - Individual functions registered with `app.command()`
```python
app.command(name="run")(run_command)
app.command(name="agent")(agent_command)
```

2. **Subcommand Groups** - Sub-Typers added with `app.add_typer()`
```python
app.add_typer(cascade_app, name="cascade", help="Cascade ideas through stages")
app.add_typer(workflows_app, name="workflow", help="Manage workflows")
```

3. **Merged Commands** - Commands from sub-apps merged into main app
```python
for command in core_app.registered_commands:
    app.registered_commands.append(command)
```

### Database Architecture

- **SQLite + FTS5** via `DatabaseConnection` singleton
- **Migration system** in `database/migrations.py`
- **Modular operations**: `documents.py`, `groups.py`, `search.py`
- **Test isolation** via `EMDX_TEST_DB` environment variable

### Service Layer

Located in `emdx/services/`:
- `claude_executor.py` - AI execution
- `embedding_service.py` - Semantic search
- `file_watcher.py` - File system monitoring
- `unified_executor.py` - Task execution abstraction
- 15+ specialized services

### TUI Architecture

Uses **Textual** framework with:
- `BrowserContainer` - Main app managing browser switching
- Numbered browser types (1=Activity, 2=Cascade, 3=Search, etc.)
- Dynamic browser loading and lazy instantiation
- Theme system with runtime switching

---

## Part 2: Python Plugin System Research

### Pluggy (pytest's system)
**Source**: https://github.com/pytest-dev/pluggy

Key concepts:
- **Hook specifications** - Declare extension points with `@hookspec`
- **Hook implementations** - Plugins implement with `@hookimpl`
- **Plugin manager** - Central registration and invocation
- **Call order control** - `firstresult`, `trylast`, `tryfirst` options

```python
# Host defines hooks
@hookspec
def on_document_saved(doc_id: int, title: str, content: str) -> None:
    """Called after a document is saved."""

# Plugin implements
@hookimpl
def on_document_saved(doc_id: int, title: str, content: str):
    # Auto-tag, notify, etc.
    pass
```

### MkDocs Plugin Pattern
**Source**: https://www.mkdocs.org/dev-guide/plugins/

- Plugins are `BasePlugin` subclasses
- Event system with 14 lifecycle events
- Configuration via YAML
- Entry points for discovery

```python
class MyPlugin(BasePlugin):
    config_scheme = (
        ('option', config_options.Type(str, default='value')),
    )

    def on_page_content(self, html, page, config, files):
        return modified_html
```

### Pre-commit Framework
**Source**: https://pre-commit.com/

- Language-agnostic (hooks can be any executable)
- Repository-based distribution (git clone)
- YAML configuration
- Automatic environment isolation

---

## Part 3: Wild Ideas Exploration

### A. Microkernel Architecture

**Concept**: Core EMDX provides only document CRUD and a plugin bus. Everything else (cascade, workflows, tagging, TUI) becomes a plugin.

**Structure**:
```
emdx-core/           # Minimal kernel
├── database/        # SQLite + FTS5
├── plugin_bus/      # Message passing
└── cli_shell/       # Plugin loader

emdx-cascade/        # First-party plugin
emdx-workflows/      # First-party plugin
emdx-tui/           # First-party plugin
```

**Pros**: Maximum flexibility, clean separation, testable
**Cons**: Significant refactoring, complexity, potential performance overhead

### B. Language-Agnostic Plugins (Subprocess Model)

**Concept**: Plugins are standalone executables in any language. EMDX communicates via stdin/stdout JSON.

**Protocol**:
```json
// EMDX sends:
{"event": "document_saved", "doc_id": 123, "title": "...", "content": "..."}

// Plugin responds:
{"tags": ["urgent", "bug"], "notifications": [{"type": "slack", "channel": "#dev"}]}
```

**Implementation**:
```python
# Plugin manifest (emdx-plugin.yaml)
name: slack-notifier
language: nodejs
entry: index.js
events:
  - document_saved
  - task_completed
```

**Pros**: Any language works, process isolation, crash safety
**Cons**: IPC overhead, complex error handling, no direct DB access

### C. WebAssembly Plugins (Sandboxed)

**Concept**: Plugins compiled to WASM, run in sandboxed environment with capability-based permissions.

**Sources**:
- https://www.atlantbh.com/sandboxing-python-code-execution-with-wasm/
- https://wasmer.io/posts/py2wasm-a-python-to-wasm-compiler

```python
# Host
sandbox = WasmRuntime()
sandbox.grant_capability("read_documents")
sandbox.grant_capability("add_tags")
# Cannot access filesystem, network without explicit grant

result = sandbox.call("on_document_saved", doc_id=123)
```

**Pros**: True sandboxing, security, portable
**Cons**: Immature tooling, limited Python WASM support, performance questions

### D. Git-Based Plugin Distribution

**Concept**: Plugins are git repositories. `emdx plugin install github.com/user/emdx-plugin` clones and registers.

```bash
emdx plugin install https://github.com/user/emdx-slack-notifications
# Clones to ~/.config/emdx/plugins/emdx-slack-notifications
# Runs setup.py or pyproject.toml install

emdx plugin update  # git pull all plugins
emdx plugin list    # Show installed
```

**Pros**: Familiar workflow, automatic updates, version control
**Cons**: Security concerns (arbitrary code), dependency management

### E. AI-Generated Plugins

**Concept**: Describe what you want, Claude writes and installs the plugin.

```bash
emdx plugin generate "Notify me on Slack when docs tagged 'urgent' are created"
# Claude generates:
# - Plugin code with slack API integration
# - Configuration schema
# - Tests

# User reviews and approves
emdx plugin approve slack-urgent-notifier
```

**Pros**: Zero coding required, rapid prototyping
**Cons**: Security review needed, quality variance, trust issues

---

## Part 4: Practical Implementation Approaches

### Approach 1: Entry Points (pip install)

The most Pythonic approach using setuptools entry points.

**Plugin Package Structure**:
```
emdx-plugin-slack/
├── pyproject.toml
├── emdx_slack/
│   ├── __init__.py
│   └── commands.py
```

**pyproject.toml**:
```toml
[project]
name = "emdx-plugin-slack"
version = "0.1.0"

[project.entry-points."emdx.plugins"]
slack = "emdx_slack:SlackPlugin"

[project.entry-points."emdx.commands"]
slack = "emdx_slack.commands:app"
```

**Plugin Class**:
```python
# emdx_slack/__init__.py
from emdx.plugins import Plugin, hookimpl

class SlackPlugin(Plugin):
    name = "slack"
    version = "0.1.0"

    @hookimpl
    def on_document_saved(self, doc_id: int, title: str, content: str):
        # Send Slack notification
        pass
```

**EMDX main.py changes**:
```python
import importlib.metadata

def load_plugins():
    plugins = {}
    for ep in importlib.metadata.entry_points(group="emdx.plugins"):
        try:
            plugin_class = ep.load()
            plugins[ep.name] = plugin_class()
        except Exception as e:
            logger.warning(f"Failed to load plugin {ep.name}: {e}")
    return plugins

def load_plugin_commands(app):
    for ep in importlib.metadata.entry_points(group="emdx.commands"):
        try:
            plugin_app = ep.load()
            app.add_typer(plugin_app, name=ep.name)
        except Exception as e:
            logger.warning(f"Failed to load commands for {ep.name}: {e}")
```

### Approach 2: Runtime Plugin Directory

Simpler approach for local/development plugins.

**Plugin Location**: `~/.config/emdx/plugins/`

**Plugin Structure**:
```
~/.config/emdx/plugins/
├── slack_notifier/
│   ├── plugin.yaml
│   └── __init__.py
├── custom_tags/
│   ├── plugin.yaml
│   └── __init__.py
```

**plugin.yaml**:
```yaml
name: slack_notifier
version: 0.1.0
author: User
description: Send Slack notifications

commands:
  - name: slack
    description: Slack notification commands

hooks:
  - on_document_saved
  - on_task_completed

config:
  webhook_url:
    type: string
    required: true
  channel:
    type: string
    default: "#general"
```

**Loader**:
```python
# emdx/plugins/loader.py
from pathlib import Path
import importlib.util

PLUGINS_DIR = Path.home() / ".config" / "emdx" / "plugins"

def discover_plugins():
    plugins = []
    for plugin_dir in PLUGINS_DIR.iterdir():
        if plugin_dir.is_dir() and (plugin_dir / "plugin.yaml").exists():
            plugins.append(load_plugin(plugin_dir))
    return plugins

def load_plugin(plugin_dir: Path):
    manifest = yaml.safe_load((plugin_dir / "plugin.yaml").read_text())

    # Dynamic import
    spec = importlib.util.spec_from_file_location(
        manifest["name"],
        plugin_dir / "__init__.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return PluginInstance(manifest, module)
```

### Approach 3: Pluggy-Based (Full Hook System)

Most flexible, based on pytest's proven system.

**Hook Specifications**:
```python
# emdx/plugins/hookspec.py
import pluggy

hookspec = pluggy.HookspecMarker("emdx")
hookimpl = pluggy.HookimplMarker("emdx")

class EmdxHookSpec:
    """Hook specifications for EMDX plugins."""

    # Document lifecycle
    @hookspec
    def on_document_saved(self, doc_id: int, title: str, content: str, project: str):
        """Called after a document is saved."""

    @hookspec
    def on_document_deleted(self, doc_id: int):
        """Called after a document is deleted."""

    @hookspec(firstresult=True)
    def transform_content_before_save(self, content: str) -> str:
        """Transform content before saving. First non-None result wins."""

    # Cascade events
    @hookspec
    def on_cascade_stage_complete(self, doc_id: int, stage: str, next_stage: str):
        """Called when a cascade stage completes."""

    # Task events
    @hookspec
    def on_task_created(self, task_id: int, title: str):
        """Called when a task is created."""

    @hookspec
    def on_task_status_changed(self, task_id: int, old_status: str, new_status: str):
        """Called when task status changes."""

    # CLI extension
    @hookspec
    def register_commands(self, app):
        """Register additional CLI commands."""

    # TUI extension
    @hookspec
    def register_browsers(self) -> list[tuple[str, type]]:
        """Return list of (name, browser_class) tuples to register."""

    @hookspec
    def modify_theme(self, theme: dict) -> dict:
        """Modify theme settings."""
```

**Plugin Manager**:
```python
# emdx/plugins/manager.py
import pluggy
from .hookspec import EmdxHookSpec

class PluginManager:
    def __init__(self):
        self.pm = pluggy.PluginManager("emdx")
        self.pm.add_hookspecs(EmdxHookSpec)

    def load_builtin_plugins(self):
        """Load first-party plugins."""
        from emdx.plugins.builtin import auto_tagger, lifecycle_tracker
        self.pm.register(auto_tagger)
        self.pm.register(lifecycle_tracker)

    def load_external_plugins(self):
        """Load from entry points."""
        self.pm.load_setuptools_entrypoints("emdx.plugins")

    def load_local_plugins(self):
        """Load from ~/.config/emdx/plugins/."""
        # ... discovery and loading

    @property
    def hook(self):
        return self.pm.hook
```

**Usage in Core**:
```python
# emdx/models/documents.py
from emdx.plugins import plugin_manager

def save_document(title, content, project=None):
    # Transform content (plugins can modify)
    transformed = plugin_manager.hook.transform_content_before_save(content=content)
    final_content = transformed or content

    # Save to DB
    doc_id = _db_save(title, final_content, project)

    # Notify plugins
    plugin_manager.hook.on_document_saved(
        doc_id=doc_id,
        title=title,
        content=final_content,
        project=project
    )

    return doc_id
```

---

## Part 5: Plugin Interface Design

### Base Plugin Class

```python
# emdx/plugins/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Callable, Any
from pathlib import Path

@dataclass
class PluginMetadata:
    name: str
    version: str
    description: str
    author: Optional[str] = None
    homepage: Optional[str] = None
    requires_emdx: str = ">=0.7.0"
    dependencies: list[str] = None

class Plugin(ABC):
    """Base class for EMDX plugins."""

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        pass

    def on_load(self, context: "PluginContext") -> None:
        """Called when plugin is loaded. Override to initialize."""
        pass

    def on_unload(self) -> None:
        """Called when plugin is unloaded. Override to cleanup."""
        pass

@dataclass
class PluginContext:
    """Context provided to plugins."""
    db_connection: Any  # DatabaseConnection
    config: dict  # Plugin-specific config
    data_dir: Path  # Plugin data directory
    log: Any  # Logger instance

    # Safe API methods
    def get_document(self, doc_id: int) -> Optional[dict]:
        """Read a document."""
        pass

    def save_document(self, title: str, content: str, project: str = None) -> int:
        """Save a new document."""
        pass

    def add_tags(self, doc_id: int, tags: list[str]) -> None:
        """Add tags to a document."""
        pass

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search documents."""
        pass

    def emit_event(self, event_type: str, data: dict) -> None:
        """Emit a custom event for other plugins."""
        pass
```

### Example Plugin Implementation

```python
# emdx_plugin_slack/__init__.py
from emdx.plugins import Plugin, PluginMetadata, hookimpl
import httpx

class SlackPlugin(Plugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="slack-notifications",
            version="0.1.0",
            description="Send Slack notifications for EMDX events",
            author="Your Name"
        )

    def on_load(self, context):
        self.webhook_url = context.config.get("webhook_url")
        self.channel = context.config.get("channel", "#general")
        self.ctx = context

    @hookimpl
    def on_document_saved(self, doc_id: int, title: str, content: str, project: str):
        # Check if document has urgent tag
        doc = self.ctx.get_document(doc_id)
        if doc and "urgent" in doc.get("tags", []):
            self._send_notification(
                f"Urgent document created: {title}",
                f"Project: {project}\nDoc ID: #{doc_id}"
            )

    @hookimpl
    def on_task_status_changed(self, task_id: int, old_status: str, new_status: str):
        if new_status == "done":
            self._send_notification(
                f"Task #{task_id} completed",
                f"Status: {old_status} -> {new_status}"
            )

    def _send_notification(self, title: str, text: str):
        if not self.webhook_url:
            self.ctx.log.warning("Slack webhook URL not configured")
            return

        httpx.post(self.webhook_url, json={
            "channel": self.channel,
            "text": f"*{title}*\n{text}"
        })
```

### TUI Browser Plugin

```python
# emdx_plugin_metrics/__init__.py
from emdx.plugins import Plugin, PluginMetadata, hookimpl
from textual.widget import Widget
from textual.containers import Container

class MetricsBrowser(Widget):
    """Custom TUI browser showing document metrics."""

    def compose(self):
        yield Container(id="metrics-content")

    async def on_mount(self):
        # Load and display metrics
        pass

class MetricsPlugin(Plugin):
    @property
    def metadata(self):
        return PluginMetadata(
            name="metrics-browser",
            version="0.1.0",
            description="Document analytics and metrics browser"
        )

    @hookimpl
    def register_browsers(self):
        """Register custom browser."""
        return [("metrics", MetricsBrowser)]

    @hookimpl
    def register_commands(self, app):
        """Register CLI commands."""
        import typer

        metrics_app = typer.Typer()

        @metrics_app.command()
        def summary():
            """Show document metrics summary."""
            # Implementation
            pass

        app.add_typer(metrics_app, name="metrics")
```

---

## Part 6: Migration Path

### Phase 1: Foundation (Week 1-2)

1. **Create plugin infrastructure**:
   - `emdx/plugins/__init__.py` - Public API
   - `emdx/plugins/hookspec.py` - Hook specifications
   - `emdx/plugins/manager.py` - Plugin discovery and management
   - `emdx/plugins/base.py` - Base classes

2. **Add hook calls to existing code**:
   - `models/documents.py` - Document lifecycle hooks
   - `commands/cascade.py` - Cascade stage hooks
   - `commands/tasks.py` - Task lifecycle hooks

3. **Plugin configuration**:
   - Add `[tool.emdx.plugins]` section to pyproject.toml support
   - Create `~/.config/emdx/plugins.yaml` for user config

### Phase 2: Convert Internal Features (Week 3-4)

1. **Extract auto-tagger as plugin**:
   - Currently in `services/auto_tagger.py`
   - Convert to built-in plugin
   - Register with hook system

2. **Extract lifecycle tracker**:
   - Currently in `services/lifecycle_tracker.py`
   - Convert to built-in plugin

3. **Create example third-party plugins**:
   - Slack notifications
   - GitHub issue integration
   - Custom export formats

### Phase 3: TUI Extensibility (Week 5-6)

1. **Browser registration hook**:
   - Allow plugins to add new browsers
   - Dynamic key binding assignment
   - Theme customization hooks

2. **Widget injection points**:
   - Status bar extensions
   - Preview pane customization
   - Modal dialogs

### Phase 4: Documentation & Ecosystem (Week 7-8)

1. **Plugin developer guide**
2. **Example plugin repository**
3. **Plugin marketplace/registry**
4. **CI/CD templates for plugins**

---

## Part 7: Design Questions & Answers

### Q: How do plugins register commands?

**A**: Via `register_commands` hook or entry points:

```python
# Option 1: Hook
@hookimpl
def register_commands(self, app):
    app.add_typer(my_commands, name="mycommand")

# Option 2: Entry point (pyproject.toml)
[project.entry-points."emdx.commands"]
mycommand = "my_plugin.commands:app"
```

### Q: How do plugins access the database?

**A**: Through the `PluginContext` API, not direct access:

```python
# Safe - uses context API
doc = self.ctx.get_document(doc_id)
self.ctx.add_tags(doc_id, ["processed"])

# Not allowed - direct DB access
# with db_connection.get_connection() as conn: ...
```

This provides:
- API stability across versions
- Query optimization
- Audit logging
- Permission enforcement (future)

### Q: How do plugins extend the TUI?

**A**: Via hooks for browser registration and modification:

```python
@hookimpl
def register_browsers(self):
    return [("mybrowser", MyBrowserWidget)]

@hookimpl
def on_browser_mounted(self, browser_name: str, browser: Widget):
    # Inject widgets, modify behavior
    if browser_name == "document":
        browser.inject_status_widget(MyStatusWidget())
```

### Q: What's the plugin lifecycle?

**A**:
1. **Discovery** - Find plugins via entry points and local directory
2. **Load** - Import module, instantiate class
3. **Initialize** - Call `on_load()` with context
4. **Active** - Hooks are called during operation
5. **Unload** - Call `on_unload()` for cleanup

### Q: How do you handle plugin conflicts?

**A**: Priority system + explicit conflict declaration:

```python
@hookimpl(trylast=True)  # Run after others
def transform_content_before_save(self, content: str):
    pass

# In metadata
class MyPlugin(Plugin):
    conflicts_with = ["other-plugin"]  # Won't load if other is present
    depends_on = ["required-plugin"]   # Load order dependency
```

---

## Part 8: Recommendation

### Recommended Approach: Hybrid (Entry Points + Pluggy)

Combine the best aspects:

1. **Entry Points** for discovery - Standard Python, works with pip
2. **Pluggy** for hook system - Proven, flexible, battle-tested
3. **Local plugins** for development - Easy iteration
4. **Safe Context API** for database - Stability, security

### Implementation Priority

1. **Start with hooks** - Add hook calls to existing code first
2. **Then entry points** - Enable pip-installable plugins
3. **Then TUI hooks** - Browser registration, theming
4. **Finally, advanced features** - WASM sandboxing, AI generation

### Estimated Effort

- Phase 1 (Foundation): 20-30 hours
- Phase 2 (Convert internals): 15-20 hours
- Phase 3 (TUI): 25-35 hours
- Phase 4 (Docs/Ecosystem): 15-20 hours

**Total: 75-105 hours** to production-ready plugin system

---

## References

- [Pluggy Documentation](https://pluggy.readthedocs.io/)
- [MkDocs Plugin Guide](https://www.mkdocs.org/dev-guide/plugins/)
- [Pytest Plugin Development](https://docs.pytest.org/en/stable/how-to/writing_plugins.html)
- [Typer Subcommands](https://typer.tiangolo.com/tutorial/subcommands/add-typer/)
- [Python Packaging Entry Points](https://packaging.python.org/en/latest/specifications/entry-points/)
- [Wasmtime Python](https://github.com/bytecodealliance/wasmtime-py)
- [Pre-commit Framework](https://pre-commit.com/)
