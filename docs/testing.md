# EMDX Testing Guide

## 🧪 **Test Suite Overview**

EMDX has 24 test files that cover functionality, but **many are currently broken** due to import errors and outdated module references. The test suite needs significant cleanup to be functional.

### **Current Test Status**

```bash
# WARNING: Many tests are broken due to import errors
# Run all tests (expect failures)
poetry run pytest

# Test what actually works
poetry run pytest tests/test_core.py -v

# Some tests pass, many fail with import errors:
# - ModuleNotFoundError: No module named 'emdx.browse'  
# - ModuleNotFoundError: No module named 'emdx.cli'
# - ImportError: cannot import name 'get_git_project'
```

## 📁 **Test Structure**

```
tests/
├── conftest.py                    # Pytest configuration and fixtures
├── test_core.py                   # Core CLI commands (save, find, view)
├── test_database.py               # Database operations and models
├── test_tags.py                   # Tag system and emoji aliases
├── test_migrations.py             # Database schema migrations
├── test_cli.py                    # CLI integration tests
├── test_browse.py                 # Browse commands (list, stats, recent)
├── test_auto_tagger.py            # Automatic tagging system
├── test_claude_execute.py         # Claude Code integration
├── test_execution_system.py       # Execution tracking and monitoring
├── test_log_browser.py            # Log browser TUI component
├── test_log_browser_timestamps.py # Log parsing and timestamps
├── test_smart_execution.py        # Smart execution features
├── test_vim_line_numbers.py       # Vim editor line numbering
├── test_input_content.py          # Content input handling
├── test_sqlite_database.py        # SQLite-specific database tests
├── test_utils.py                  # Utility functions
├── test_config.py                 # Configuration management
├── test_file_size.py              # File size utilities
├── test_tagging_config.py         # Tagging configuration
├── test_fixtures.py               # Test fixture utilities
├── test_timestamp_parsing.py      # Timestamp parsing logic
├── test_new_modules.py            # New module tests
├── test_init.py                   # Package initialization
└── test_*.py                      # Various other test modules
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
- **Database Migrations** (`test_migrations.py`) - Schema evolution
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

### **Critical Problems**
1. **Many tests don't run** - Import errors due to outdated module references
2. **Old module paths** - Tests reference `emdx.browse`, `emdx.cli` that don't exist
3. **Missing imports** - `get_git_project`, `sqlite_database` module references
4. **Asyncio marker missing** - TUI tests fail with marker configuration errors
5. **Test fixture issues** - Warnings about `__init__` constructors in test classes

### **Secondary Issues**
6. **Test organization could be better** - Some overlap between test files
7. **TUI testing is limited** - Textual widget testing is challenging  
8. **Some tests are flaky** - Especially timing-dependent execution tests
9. **Mock usage inconsistent** - Some tests use real files, others mock
10. **Test data cleanup** - Some tests don't clean up properly

### **Test Coverage Gaps**
- **Full TUI integration** - Hard to test complete user workflows
- **Cross-platform behavior** - Most testing on single platform
- **Error edge cases** - Some error conditions not well tested
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

## 🛠️ **Fixing the Test Suite**

### **Priority 1: Make Tests Run**
1. **Fix import errors** - Update module paths to match current code structure
2. **Add missing asyncio marker** - Fix pytest configuration for TUI tests
3. **Fix import paths** - Update references to moved/renamed modules
4. **Remove obsolete tests** - Delete tests for deleted functionality

### **Priority 2: Test Quality**
5. **Clean up test organization** and remove duplication
6. **Fix flaky execution system tests**  
7. **Improve TUI testing** with better patterns
8. **Add more error condition tests**

### **Priority 3: Enhancement**
9. **Add performance regression testing**
10. **Cross-platform testing automation**
11. **Visual regression testing for TUI**
12. **Load testing for large document collections**

## 💡 **Test Fix Strategy**

The test suite needs significant work before it can be considered functional. The tests contain valuable patterns and expected behavior documentation, but most don't currently run due to import errors from code refactoring.

**Quick win**: Fix the import errors in a few key test files to have some working tests, rather than trying to fix all 24 at once.