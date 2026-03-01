# EMDX Testing Guide

## 🧪 **Test Suite Overview**

EMDX has 74 test files with comprehensive coverage. The test suite is fully functional with all tests passing.

### **Current Test Status**

```bash
poetry run pytest tests/ -v

# Run quick (stop on first failure)
poetry run pytest tests/ -x -q
```

## 📁 **Test Structure**

```
tests/
├── conftest.py                       # Pytest configuration and fixtures
├── test_activity_doc_type.py         # Activity view document type handling
├── test_activity_table.py            # Activity table rendering
├── test_activity_view.py             # Activity view TUI component
├── test_ask.py                       # Ask/RAG command tests
├── test_ask_modes.py                 # Ask mode variations
├── test_auto_tagger.py               # Automatic tagging system
├── test_backup.py                    # Backup and restore
├── test_categories.py                # Category management
├── test_chunk_splitter.py            # Document chunking
├── test_cli.py                       # CLI integration tests
├── test_code_drift.py                # Code drift detection
├── test_commands_core.py             # Core command tests (save, find, view)
├── test_commands_prime.py            # Prime command tests
├── test_commands_stale.py            # Staleness tracking tests
├── test_commands_tags.py             # Tag command tests
├── test_commands_trash.py            # Trash command tests
├── test_compact.py                   # Document compaction tests
├── test_config.py                    # Configuration management
├── test_contradictions.py            # Contradiction detection
├── test_core.py                      # Core CLI commands (save, find, view)
├── test_database.py                  # Database operations and models
├── test_distill.py                   # Distillation tests
├── test_document_links.py            # Document linking
├── test_document_merger.py           # Document merging
├── test_documents.py                 # Document CRUD operations
├── test_duplicate_detector.py        # Duplicate detection
├── test_entity_service.py            # Entity extraction service
├── test_epics.py                     # Epic management tests
├── test_events.py                    # Event system tests
├── test_explore.py                   # Explore command tests
├── test_file_watcher.py              # File watcher service tests
├── test_find_wander.py               # Find wander mode tests
├── test_fixtures.py                  # Test fixture tests
├── test_freshness.py                 # Document freshness tracking
├── test_gaps.py                      # Knowledge gap detection
├── test_history.py                   # Document history tracking
├── test_hybrid_search.py             # Hybrid search tests
├── test_init.py                      # Package initialization
├── test_input_content.py             # Content input handling
├── test_intelligence_integration.py  # Intelligence integration tests
├── test_lazy_loading.py              # Lazy loading functionality
├── test_maintain_drift.py            # Maintenance drift detection
├── test_migrations.py                # Database schema migrations
├── test_modal_keys.py                # Modal key bindings
├── test_models_tags.py               # Tag model tests
├── test_non_interactive.py           # Non-interactive mode tests
├── test_release_script.py            # Release script tests
├── test_save_task_flags.py           # Save with task flags
├── test_search.py                    # Search functionality tests
├── test_similarity.py                # Document similarity service
├── test_sqlite_database.py           # SQLite-specific database tests
├── test_tags.py                      # Tag system and emoji aliases
├── test_task_browser.py              # Task browser TUI component
├── test_task_commands.py             # Task command tests
├── test_text_formatting.py           # Text formatting utilities
├── test_title_normalization.py       # Title normalization
├── test_utils.py                     # Utility functions
├── test_view_review.py               # View review functionality
├── test_watch.py                     # File watch tests
├── test_wiki_article_diff.py         # Wiki article diffing
├── test_wiki_article_timing.py       # Wiki article timing
├── test_wiki_coverage.py             # Wiki coverage tracking
├── test_wiki_editorial_prompt.py     # Wiki editorial prompts
├── test_wiki_export.py               # Wiki export to MkDocs
├── test_wiki_model_override.py       # Wiki model override
├── test_wiki_progress.py             # Wiki generation progress
├── test_wiki_rating.py               # Wiki article rating
├── test_wiki_rename.py               # Wiki topic renaming
├── test_wiki_retitle.py              # Wiki article retitling
├── test_wiki_source_weight.py        # Wiki source weighting
├── test_wiki_topic_merge_split.py    # Wiki topic merge/split
├── test_wiki_topic_skip_pin.py       # Wiki topic skip/pin
├── test_wiki_triage_setup.py         # Wiki triage and setup
└── test_wikify_service.py            # Wikify service tests
```

## 🎯 **Test Categories**

### **Core Functionality Tests**
- **CLI Commands** (`test_core.py`, `test_cli.py`, `test_commands_core.py`) - save, find, view, edit, delete
- **Database Operations** (`test_database.py`, `test_sqlite_database.py`, `test_documents.py`) - CRUD, search, migrations
- **Tag System** (`test_tags.py`, `test_models_tags.py`, `test_commands_tags.py`, `test_emoji_aliases.py`) - plain text tags, management
- **Groups** (`test_groups.py`, `test_commands_groups.py`) - document group management
- **Tasks** (`test_task_commands.py`, `test_epics.py`, `test_categories.py`) - task queue, epics, categories

### **Advanced Feature Tests**
- **TUI Components** (`test_activity_*.py`, `test_task_browser.py`, `test_modal_keys.py`) - UI widget tests
- **Wiki** (`test_wiki_*.py`, `test_wikify_service.py`, `test_entity_service.py`) - wiki generation, topics, export
- **Similarity** (`test_similarity.py`, `test_duplicate_detector.py`) - document similarity and dedup
- **AI Features** (`test_compact.py`, `test_distill.py`, `test_hybrid_search.py`, `test_ask.py`) - compaction, distillation, hybrid search, RAG
- **Maintenance** (`test_freshness.py`, `test_gaps.py`, `test_code_drift.py`, `test_maintain_drift.py`, `test_contradictions.py`) - KB health and maintenance

### **Infrastructure Tests**
- **Database Migrations** (`test_migrations.py`) - Schema evolution
- **Configuration** (`test_config.py`) - Settings and configuration
- **Utilities** (`test_utils.py`, `test_file_size.py`, `test_text_formatting.py`, `test_title_normalization.py`, `test_output_parser.py`) - Helper functions
- **Search** (`test_search.py`, `test_hybrid_search.py`) - FTS5 and hybrid search
- **Input/Output** (`test_input_content.py`, `test_stream_json_parser.py`, `test_chunk_splitter.py`) - content handling and parsing
- **Other** (`test_commands_prime.py`, `test_commands_stale.py`, `test_commands_status.py`, `test_commands_trash.py`, `test_fixtures.py`) - additional command tests

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

Typer uses Click's `CliRunner` internally, so importing from `click.testing` is correct:

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

## 🚨 **Known Limitations**

- **TUI testing is limited** - Textual widget testing is challenging
- **Some timing-dependent tests** - May be sensitive to system load
- **No performance regression tests** - No benchmarks or perf tracking
- **Single-platform testing** - Most testing on macOS

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

## 💡 **Contributing Tests**

When adding new features, follow the patterns in existing test files:
- Use `temp_db` fixture for database tests
- Use `CliRunner` for CLI integration tests
- Mock external dependencies consistently
- Clean up resources in fixtures using `yield` pattern
