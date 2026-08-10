# EMDX Development Setup

## 🚀 **Quick Start**

### **Prerequisites**
- **Python 3.11+** (required by project)
- **Git** for version control
- **Poetry** for dependency management (recommended)

### **Installation Options**

#### **Option 1: Poetry (Recommended for Development)**
```bash
# Clone the repository
git clone https://github.com/arockwell/emdx.git
cd emdx

# Install with Poetry - core only (fast, lightweight)
poetry install

# Install with all extras (e.g. wiki topic clustering)
poetry install --all-extras

# Or install just the wiki extra (python-igraph, leidenalg)
poetry install -E wiki

# Run commands with Poetry
poetry run emdx --help
```

#### **Option 2: pipx (Recommended for Global CLI Usage)**
```bash
# Install globally with pipx
pipx install -e . --python python3.11

# Use directly from anywhere
emdx --help
emdx gui
```

#### **Option 3: Virtual Environment + pip**
```bash
# Create and activate virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .

# Run commands
emdx --help
```

## 🛠️ **Development Workflow**

### **Project Structure**
```
emdx/
├── emdx/                    # Main package
│   ├── commands/           # CLI command implementations
│   ├── ui/                # TUI components (Textual widgets)
│   ├── services/          # Business logic and coordination
│   ├── models/            # Data models and database operations
│   ├── database/          # Database connection and migrations
│   ├── utils/             # Utility functions and helpers
│   └── config/            # Configuration management
├── tests/                 # Test suite
├── docs/                  # Documentation (this folder)
├── pyproject.toml        # Project configuration and dependencies
└── README.md             # Project overview
```

### **Running Tests**
```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=emdx

# Run specific test file
poetry run pytest tests/test_database.py

# Run tests matching pattern
poetry run pytest -k "test_streaming"
```

### **Code Quality Tools**

#### **Linting and Formatting**
```bash
# Check code style (if configured)
poetry run ruff check .

# Format code (if configured)  
poetry run ruff format .

# Type checking (if mypy is configured)
poetry run mypy emdx/
```

#### **Pre-commit Hooks (if configured)**
```bash
# Install pre-commit hooks
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

### **Database Development**

#### **Working with Migrations**
```bash
# Database is created automatically in ~/.emdx/
# Migration system is in emdx/database/migrations.py

# Check current database version
poetry run python -c "
from emdx.database.connection import db_connection
print(f'Database version: {db_connection.get_version()}')
"

# Run migrations manually (usually automatic)
poetry run python -c "
from emdx.database.migrations import run_migrations
run_migrations()
"
```

#### **Database Location**
- **Default (production)**: `~/.config/emdx/knowledge.db`
- **Dev checkout**: `<project-root>/.emdx/dev.db` (auto-detected)
- **Custom**: Set `EMDX_DB` environment variable
- **Testing**: Set `EMDX_TEST_DB` for test isolation (pytest fixtures do this automatically)

#### **Dev Database Isolation**

When running via `poetry run emdx` (editable install), emdx automatically uses a local `.emdx/dev.db` instead of the production database. This prevents development processes from corrupting production data.

**Priority chain for database path:**
1. `EMDX_TEST_DB` — test isolation (set by pytest fixtures)
2. `EMDX_DB` — explicit override (e.g. `EMDX_DB=/tmp/test.db poetry run emdx status`)
3. Dev checkout detection → `<project-root>/.emdx/dev.db`
4. Production default → `~/.config/emdx/knowledge.db`

**Useful commands:**
```bash
emdx db status        # Show active DB path and reason
emdx db path          # Print just the path (for scripts)
emdx db copy-from-prod  # Copy production DB to dev DB
```

### **TUI Development**

#### **Running the TUI**
```bash
# Launch interactive TUI
poetry run emdx gui

# Enable debug mode for TUI development
TEXTUAL_LOG=DEBUG poetry run emdx gui
```

#### **TUI Development Tips**
- **Live reload**: Use Textual's hot reload features during development
- **CSS debugging**: Textual provides excellent CSS debugging tools
- **Widget testing**: Create standalone widget tests in `tests/ui/`

## 🧪 **Testing Guidelines**

### **Test Organization**
```
tests/
├── conftest.py              # Pytest configuration and fixtures
├── test_commands_core.py    # Core command tests (save, find, view)
├── test_commands_tags.py    # Tag command tests
├── test_task_commands.py    # Task command tests
├── test_database.py         # Database operations
├── test_documents.py        # Document CRUD
├── test_core.py             # Core CLI commands
├── test_log_browser.py      # TUI component tests
└── ...                      # 65 test files total
```

### **Common Test Patterns**

#### **Database Testing**
```python
import pytest
import tempfile
from pathlib import Path
from emdx.database.connection import DatabaseConnection

@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    
    # Use temporary database
    db = DatabaseConnection(db_path)
    yield db
    
    # Cleanup
    db_path.unlink()

def test_document_creation(temp_db):
    # Test with isolated database
    pass
```

#### **UI Component Testing**
```python
from textual.app import App
from emdx.ui.log_browser import LogBrowser

class TestApp(App):
    def compose(self):
        yield LogBrowser()

def test_log_browser():
    app = TestApp()
    # Test widget behavior
    pass
```

#### **Service Testing**
```python
from unittest.mock import Mock, patch
from emdx.services.log_stream import LogStream

def test_log_stream():
    with patch('emdx.services.log_stream.FileWatcher') as mock_watcher:
        stream = LogStream(Path('/test/log'))
        # Test service behavior with mocked dependencies
        pass
```

## 🔧 **Common Development Tasks**

### **Adding a New CLI Command**
1. Create command function in appropriate `commands/` module
2. Add typer decorators and type hints
3. Register with main CLI app in `main.py`
4. Add tests in `tests/` (e.g., `tests/test_commands_<name>.py`)
5. Update CLI documentation

### **Adding a New UI Component**
1. Create widget class extending Textual `Widget`
2. Implement `compose()` method for layout
3. Add CSS styling and keybindings
4. Add to appropriate browser container
5. Create tests for widget behavior

### **Adding a New Service**
1. Create service class in `services/` directory
2. Define clear interface and error handling
3. Add dependency injection if needed
4. Create comprehensive tests
5. Update service documentation

### **Database Schema Changes**
1. Create new migration function in `migrations.py`
2. Add to `MIGRATIONS` list with a timestamp-based string ID (format: `"YYYYMMDD_HHMMSS"`)
3. Test migration with existing databases
4. Update model classes as needed
5. Add tests for migration behavior

Migrations use **set-based tracking** with string IDs. Legacy migrations (0-54) use numeric strings. New migrations use timestamp IDs:
```python
("20260301_120000", "Add new feature", migration_20260301_120000_add_new_feature)
```

## 🐛 **Debugging**

### **Common Issues**

#### **Python Version Mismatch**
```bash
# EMDX requires Python 3.11+
python3.11 --version

# Poetry will automatically find compatible Python
poetry env use python3.11
```

#### **Database Issues**
```bash
# Reset database (careful - loses all data!)
rm ~/.config/emdx/knowledge.db

# Check database integrity
sqlite3 ~/.config/emdx/knowledge.db "PRAGMA integrity_check;"
```

#### **TUI Display Issues**
```bash
# Check terminal compatibility
echo $TERM

# Test with basic terminal
TERM=xterm-256color poetry run emdx gui

# Enable debug logging
TEXTUAL_LOG=DEBUG poetry run emdx gui 2> debug.log
```

### **Debugging Tools**

#### **Python Debugging**
```python
# Use pdb for debugging
import pdb; pdb.set_trace()

# Or use rich for better output
from rich import print as rprint
rprint(complex_object)
```

#### **Textual Debugging**
```python
# Textual provides excellent debugging
from textual import log
log("Debug message", data=some_object)

# View logs in separate terminal
textual console
```

#### **Headless TUI Testing**

Use Textual's `run_test()` to debug TUI crashes without launching an interactive terminal. This is especially useful in CI or when working inside Claude Code where interactive TUIs can't run.

```python
# test_tui_headless.py - reproduce TUI crashes without a terminal
import asyncio
from textual.app import App, ComposeResult
from emdx.ui.activity.activity_view import ActivityView

class TestApp(App):
    def compose(self) -> ComposeResult:
        yield ActivityView(id="activity-view")

async def main():
    app = TestApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await asyncio.sleep(2)  # Let data load
        print("App loaded OK")

asyncio.run(main())
```

Run it:
```bash
poetry run python test_tui_headless.py
```

The headless test app mounts real widgets, runs `on_mount()`, loads data, and renders — so it catches the same errors you'd see in the live GUI (e.g. type errors in `format_time_ago`, missing attributes on new item types, rendering bugs). Tracebacks print to stderr with full locals.

You can also interact with the app via the `pilot`:
```python
async with app.run_test(size=(120, 40)) as pilot:
    await pilot.pause()
    await pilot.press("j")      # Navigate down
    await pilot.press("l")      # Expand
    await pilot.press("a")      # Custom action
```

## 📦 **Build and Distribution**

### **Building the Package**
```bash
# Build wheel and source distribution
poetry build

# Built packages appear in dist/
ls dist/
```

### **Local Installation Testing**
```bash
# Install locally built package
pipx install dist/emdx-*.whl

# Test installation
emdx --version
```

## 🤝 **Contributing Guidelines**

### **Pull Request Process**
1. **Fork** the repository and create feature branch
2. **Implement** changes with tests and documentation
3. **Test** thoroughly with existing test suite
4. **Update** relevant documentation in `docs/`
5. **Submit** PR with clear description of changes

### **Code Standards**
- **Type hints** required for all function signatures
- **Docstrings** for all public functions and classes
- **Tests** for all new functionality
- **Documentation** updates for significant changes

#### **Logging Standards**
Use the standard Python logging pattern:
```python
import logging

logger = logging.getLogger(__name__)
```
This allows callers to configure logging as needed. The `emdx/utils/logging_utils.py` module provides `get_logger()` for cases requiring automatic file handler setup, but standard library usage is preferred for most modules.

#### **Console Output Standards**
Use the shared console instance for CLI output:
```python
from emdx.utils.output import console

console.print("[green]Success![/green]")
```
This ensures consistent formatting across the CLI.

### **Commit Message Format**
```
feat: add event-driven log streaming
fix: resolve database migration issue
docs: update architecture documentation
test: add comprehensive streaming tests
```

This development setup ensures a smooth contributor experience while maintaining code quality and project consistency.