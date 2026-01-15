# EMDX Testing Guide

## 🧪 **Test Suite Overview**

EMDX has 36 test files with comprehensive coverage. The test suite is fully functional with all tests passing.

### **Current Test Status** 🎉 **FULLY FUNCTIONAL TEST SUITE**

```bash
# 🎉 Test suite is fully operational!
poetry run pytest tests/ -v

# 🎉 Current Results (as of 2026-01-14):
# - 395 tests collected
# - 395 tests passing ✅ (100% success rate)
# - 0 tests failing
# - 5 tests skipped
# - 0 collection errors ✅

# ✅ ALL IMPORT ERRORS FIXED:
# - emdx.browse → emdx.commands.browse
# - emdx.cli → emdx.main
# - emdx.sqlite_database → emdx.database
# - emdx.migrations → emdx.database.migrations
# - emdx.utils get_git_project → emdx.utils.git
# - TestDatabase → DatabaseForTesting (pytest collection fix)
# - Added asyncio marker for TUI tests
```

## 📁 **Test Structure**

```
tests/
├── conftest.py                       # Pytest configuration and fixtures
├── test_agent_executor_integration.py # Agent executor integration tests
├── test_agent_system.py              # Agent system tests
├── test_agents.py                    # Agent configuration and registry tests
├── test_auto_tagger.py               # Automatic tagging system
├── test_browse.py                    # Browse commands (list, stats, recent)
├── test_claude_execute.py            # Claude Code integration
├── test_cli.py                       # CLI integration tests
├── test_config.py                    # Configuration management
├── test_core.py                      # Core CLI commands (save, find, view)
├── test_database.py                  # Database operations and models
├── test_execution_system.py          # Execution tracking and monitoring
├── test_export_profiles.py           # Export profile functionality
├── test_file_size.py                 # File size utilities
├── test_file_watcher.py              # File watcher service tests
├── test_groups.py                    # Document group management
├── test_init.py                      # Package initialization
├── test_input_content.py             # Content input handling
├── test_lazy_loading.py              # Lazy loading functionality
├── test_log_browser.py               # Log browser TUI component
├── test_log_browser_timestamps.py    # Log parsing and timestamps
├── test_migrations.py                # Database schema migrations
├── test_overlay.py                   # Overlay functionality tests
├── test_search.py                    # Search functionality tests
├── test_similarity.py                # Document similarity service
├── test_smart_execution.py           # Smart execution features
├── test_sqlite_database.py           # SQLite-specific database tests
├── test_tags.py                      # Tag system and emoji aliases
├── test_timestamp_parsing.py         # Timestamp parsing logic
├── test_utils.py                     # Utility functions
├── test_vim_line_numbers.py          # Vim editor line numbering
└── test_workflow_executor.py         # Workflow executor tests
```

## 🎯 **Test Categories**

### **Core Functionality Tests**
- **CLI Commands** (`test_core.py`, `test_cli.py`) - save, find, view, edit, delete
- **Database Operations** (`test_database.py`, `test_sqlite_database.py`) - CRUD, search, migrations
- **Tag System** (`test_tags.py`, `test_tagging_config.py`) - emoji tags, aliases, management

### **Advanced Feature Tests**
- **Claude Integration** (`test_claude_execute.py`, `test_smart_execution.py`) - Execution system
- **TUI Components** (`test_log_browser.py`, `test_vim_line_numbers.py`) - UI widget tests
- **Log Processing** (`test_log_browser_timestamps.py`, `test_timestamp_parsing.py`) - Log parsing

### **Infrastructure Tests**
- **Database Migrations** (`test_migrations.md`) - Schema evolution
- **Configuration** (`test_config.py`) - Settings and configuration
- **Utilities** (`test_utils.py`, `test_file_size.py`) - Helper functions

## 🔧 **Common Test Patterns**

### **Database Testing**
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
```

### **CLI Testing**
```python
from click.testing import CliRunner
from emdx.main import cli

def test_save_command():
    """Test the save command."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Create test file
        with open('test.md', 'w') as f:
            f.write('# Test Document')

        # Test save command
        result = runner.invoke(cli, ['save', 'test.md'])
        assert result.exit_code == 0
```

### **TUI Component Testing**
```python
from textual.app import App
from emdx.ui.log_browser import LogBrowser

class TestApp(App):
    def compose(self):
        yield LogBrowser()

def test_log_browser():
    """Test log browser widget behavior."""
    app = TestApp()
    # Test widget behavior
    # Note: Full TUI testing is complex and limited
```

## 🚨 **Known Test Issues**

### **Resolved Issues** ✅
1. ✅ **Import errors FIXED** - All module path issues resolved
2. ✅ **Module paths FIXED** - Updated to current code structure
3. ✅ **Missing imports FIXED** - All import references corrected
4. ✅ **Asyncio marker FIXED** - TUI tests now have proper markers
5. ✅ **Test fixture issues FIXED** - Collection warnings resolved
6. ✅ **All tests passing** - 395/395 tests pass (5 skipped)

### **Minor Considerations**
- **TUI testing is limited** - Textual widget testing is challenging
- **Some timing-dependent tests** - May be sensitive to system load

### **Test Coverage Gaps**
- **Full TUI integration** - Hard to test complete user workflows
- **Cross-platform behavior** - Most testing on single platform
- **Performance testing** - No performance regression tests

## 🎯 **Running Tests Effectively**

### **Development Workflow**
```bash
# Quick test run (most common)
poetry run pytest tests/test_core.py -v

# Test specific functionality
poetry run pytest -k "test_save" -v

# Run tests with output
poetry run pytest -s tests/test_database.py

# Run only failed tests from last run
poetry run pytest --lf

# Run tests in parallel (faster)
poetry run pytest -n auto
```

### **CI/CD Testing**
```bash
# Full test suite with coverage
poetry run pytest --cov=emdx --cov-report=html

# Test against multiple Python versions (if configured)
tox
```

## ✅ **Writing New Tests**

### **Test Writing Guidelines**
1. **Use descriptive test names** - `test_save_command_creates_document`
2. **One assertion per test** - Keep tests focused
3. **Use fixtures for setup** - Avoid repetitive setup code
4. **Mock external dependencies** - File system, network, processes
5. **Test both success and failure cases** - Happy path and edge cases

### **Test Template**
```python
import pytest
from emdx.models.documents import Document

class TestDocumentModel:
    """Test the Document model operations."""

    def test_create_document_success(self, temp_db):
        """Test successful document creation."""
        doc = Document.create(
            title="Test Document",
            content="Test content",
            project="test-project"
        )

        assert doc.id is not None
        assert doc.title == "Test Document"
        assert doc.project == "test-project"

    def test_create_document_missing_title_fails(self, temp_db):
        """Test document creation fails with missing title."""
        with pytest.raises(ValueError, match="Title is required"):
            Document.create(title="", content="content")
```

## 🔄 **Test Maintenance**

### **Regular Tasks**
- **Run full test suite** before major changes
- **Update tests** when changing functionality
- **Add tests** for new features
- **Remove obsolete tests** when removing features
- **Check coverage** to identify untested code

### **Improving Test Quality**
- **Reduce test flakiness** - Fix timing-dependent tests
- **Better mocking** - Consistent mock usage patterns
- **Organize tests** - Group related tests better
- **Add integration tests** - Test complete workflows
- **Performance tests** - Ensure no regressions

## 🛠️ **Test Suite Maintenance**

### **Current State: Healthy** ✅
The test suite is fully operational with 100% pass rate (395 tests passing, 5 skipped).

### **Future Improvements**
1. **Add performance regression testing** - Track test execution times
2. **Cross-platform testing automation** - CI/CD for multiple platforms
3. **Visual regression testing for TUI** - Screenshot comparisons
4. **Load testing for large document collections** - Stress testing

## 💡 **Contributing Tests**

When adding new features, follow the patterns in existing test files:
- Use `temp_db` fixture for database tests
- Use `CliRunner` for CLI integration tests
- Mock external dependencies consistently
- Clean up resources in fixtures using `yield` pattern
