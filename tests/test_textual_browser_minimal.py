"""Tests for textual_browser_minimal module."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest
from textual.pilot import Pilot

from emdx import textual_browser_minimal
from test_fixtures import TestDatabase


class TestFullScreenView:
    """Test FullScreenView screen."""

    def setup_method(self):
        """Set up test database and sample data."""
        self.db = TestDatabase(":memory:")
        self.doc_id = self.db.save_document("Test Document", "# Test Document\n\nTest content", "test-project")

    @patch("emdx.textual_browser_minimal.db")
    def test_fullscreen_view_init(self, mock_db):
        """Test FullScreenView initialization."""
        view = textual_browser_minimal.FullScreenView(doc_id=123)
        assert view.doc_id == 123

    @patch("emdx.textual_browser_minimal.db")
    def test_fullscreen_view_on_mount_with_document(self, mock_db):
        """Test loading document content on mount."""
        mock_db.get_document.return_value = {
            "id": 1,
            "title": "Test Document",
            "content": "# Test Document\n\nTest content",
            "project": "test-project"
        }
        
        view = textual_browser_minimal.FullScreenView(doc_id=1)
        
        # Mock the query_one method to return a mock RichLog
        mock_content_log = MagicMock()
        view.query_one = MagicMock(return_value=mock_content_log)
        
        view.on_mount()
        
        mock_db.get_document.assert_called_once_with("1")
        mock_content_log.clear.assert_called_once()
        mock_content_log.write.assert_called()

    @patch("emdx.textual_browser_minimal.db")
    def test_fullscreen_view_on_mount_no_document(self, mock_db):
        """Test mounting when document doesn't exist."""
        mock_db.get_document.return_value = None
        
        view = textual_browser_minimal.FullScreenView(doc_id=999)
        view.query_one = MagicMock()
        
        view.on_mount()
        
        mock_db.get_document.assert_called_once_with("999")

    @patch("emdx.textual_browser_minimal.db")
    def test_fullscreen_view_content_with_existing_title(self, mock_db):
        """Test content handling when title already exists."""
        mock_db.get_document.return_value = {
            "id": 1,
            "title": "Test Document",
            "content": "# Test Document\n\nContent with existing title",
            "project": "test-project"
        }
        
        view = textual_browser_minimal.FullScreenView(doc_id=1)
        mock_content_log = MagicMock()
        view.query_one = MagicMock(return_value=mock_content_log)
        
        view.on_mount()
        
        # Should not duplicate the title
        args, kwargs = mock_content_log.write.call_args
        content = args[0]
        assert "# Test Document\n\nContent with existing title" in str(content)

    @patch("emdx.textual_browser_minimal.db")
    def test_fullscreen_view_content_without_title(self, mock_db):
        """Test content handling when title doesn't exist."""
        mock_db.get_document.return_value = {
            "id": 1,
            "title": "Test Document",
            "content": "Content without title",
            "project": "test-project"
        }
        
        view = textual_browser_minimal.FullScreenView(doc_id=1)
        mock_content_log = MagicMock()
        view.query_one = MagicMock(return_value=mock_content_log)
        
        view.on_mount()
        
        # Should add the title
        args, kwargs = mock_content_log.write.call_args
        content = args[0]
        assert "# Test Document" in str(content)


class TestKnowledgeBaseBrowser:
    """Test KnowledgeBaseBrowser app."""

    def setup_method(self):
        """Set up test database and sample data."""
        self.db = TestDatabase(":memory:")
        self.doc_id = self.db.save_document("Test Document", "Test content", "test-project")

    @patch("emdx.textual_browser_minimal.db")
    def test_browser_init(self, mock_db):
        """Test browser initialization."""
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        assert hasattr(browser, 'search_term')
        assert hasattr(browser, 'current_filter')

    @patch("emdx.textual_browser_minimal.db")
    def test_browser_on_mount(self, mock_db):
        """Test browser mounting and initial load."""
        mock_db.search_documents.return_value = [
            (1, "Test Document", "Test content", "test-project", "2024-01-01", 1)
        ]
        
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        
        # Mock the query_one methods
        mock_table = MagicMock()
        mock_input = MagicMock()
        mock_label = MagicMock()
        
        def mock_query_one(selector, widget_type=None):
            if selector == "#documents":
                return mock_table
            elif selector == "#search":
                return mock_input
            elif selector == "#status":
                return mock_label
            return MagicMock()
        
        browser.query_one = mock_query_one
        
        browser.on_mount()
        
        mock_db.search_documents.assert_called()
        mock_table.clear.assert_called()

    @patch("emdx.textual_browser_minimal.db")
    def test_load_documents(self, mock_db):
        """Test loading documents into the table."""
        mock_db.search_documents.return_value = [
            (1, "Test Document", "Test content", "test-project", "2024-01-01", 1),
            (2, "Another Document", "More content", "other-project", "2024-01-02", 2)
        ]
        
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        mock_table = MagicMock()
        mock_label = MagicMock()
        
        browser.query_one = MagicMock(side_effect=lambda selector, widget_type=None: 
            mock_table if selector == "#documents" else mock_label)
        
        browser.load_documents()
        
        mock_db.search_documents.assert_called()
        assert mock_table.add_row.call_count == 2

    @patch("emdx.textual_browser_minimal.db")
    def test_on_input_changed_search(self, mock_db):
        """Test search input handling."""
        mock_db.search_documents.return_value = []
        
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        browser.load_documents = MagicMock()
        
        # Mock input change event
        mock_input = MagicMock()
        mock_input.value = "test search"
        
        browser.on_input_changed(mock_input)
        
        assert browser.search_term == "test search"
        browser.load_documents.assert_called_once()

    @patch("emdx.textual_browser_minimal.db")
    def test_on_data_table_row_selected(self, mock_db):
        """Test row selection in data table."""
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        browser.push_screen = MagicMock()
        
        # Mock table data
        mock_table = MagicMock()
        mock_table.get_row_at.return_value = ["1", "Test Document", "test-project", "2024-01-01", "1"]
        
        browser.query_one = MagicMock(return_value=mock_table)
        
        # Mock row selected event
        mock_event = MagicMock()
        mock_event.row_key.value = 0
        
        browser.on_data_table_row_selected(mock_event)
        
        browser.push_screen.assert_called_once()

    def test_action_quit(self):
        """Test quit action."""
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        browser.exit = MagicMock()
        
        browser.action_quit()
        
        browser.exit.assert_called_once()

    @patch("emdx.textual_browser_minimal.db")
    def test_action_refresh(self, mock_db):
        """Test refresh action."""
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        browser.load_documents = MagicMock()
        
        browser.action_refresh()
        
        browser.load_documents.assert_called_once()

    @patch("os.environ.get")
    @patch("subprocess.run")
    @patch("tempfile.NamedTemporaryFile")
    def test_action_edit_with_nvim(self, mock_temp, mock_run, mock_env):
        """Test edit action with nvim."""
        mock_env.return_value = "/usr/bin/nvim"
        mock_temp.return_value.__enter__.return_value.name = "/tmp/test.md"
        mock_run.return_value.returncode = 0
        
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        browser.get_selected_document_id = MagicMock(return_value=1)
        browser.load_documents = MagicMock()
        
        with patch("emdx.textual_browser_minimal.db") as mock_db:
            mock_db.get_document.return_value = {
                "id": 1,
                "title": "Test",
                "content": "Content",
                "project": "test"
            }
            
            browser.action_edit()
        
        mock_run.assert_called()

    def test_get_selected_document_id(self):
        """Test getting selected document ID."""
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        
        mock_table = MagicMock()
        mock_table.cursor_row = 0
        mock_table.get_row_at.return_value = ["123", "Test", "project", "date", "count"]
        
        browser.query_one = MagicMock(return_value=mock_table)
        
        doc_id = browser.get_selected_document_id()
        
        assert doc_id == 123

    def test_get_selected_document_id_no_selection(self):
        """Test getting document ID when no row is selected."""
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        
        mock_table = MagicMock()
        mock_table.cursor_row = None
        
        browser.query_one = MagicMock(return_value=mock_table)
        
        doc_id = browser.get_selected_document_id()
        
        assert doc_id is None

    def test_get_selected_document_id_empty_table(self):
        """Test getting document ID from empty table."""
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        
        mock_table = MagicMock()
        mock_table.cursor_row = 0
        mock_table.get_row_at.side_effect = IndexError()
        
        browser.query_one = MagicMock(return_value=mock_table)
        
        doc_id = browser.get_selected_document_id()
        
        assert doc_id is None


class TestBrowserActions:
    """Test browser action methods."""

    @patch("emdx.textual_browser_minimal.db")
    def test_action_filter_none(self, mock_db):
        """Test filter action with no filter."""
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        browser.load_documents = MagicMock()
        
        browser.action_filter_none()
        
        assert browser.current_filter is None
        browser.load_documents.assert_called_once()

    @patch("emdx.textual_browser_minimal.db")
    def test_action_toggle_help(self, mock_db):
        """Test help toggle action."""
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        browser.toggle_class = MagicMock()
        
        browser.action_toggle_help()
        
        browser.toggle_class.assert_called_once_with("show-help")

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_edit_document_with_vim(self, mock_run, mock_temp):
        """Test editing document with vim editor."""
        mock_temp.return_value.__enter__.return_value.name = "/tmp/test.md"
        mock_run.return_value.returncode = 0
        
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        
        with patch("emdx.textual_browser_minimal.db") as mock_db:
            mock_db.get_document.return_value = {
                "id": 1,
                "title": "Test",
                "content": "Content",
                "project": "test"
            }
            
            result = browser.edit_document_with_vim(1)
        
        assert result is True
        mock_run.assert_called()

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_edit_document_with_vim_cancelled(self, mock_run, mock_temp):
        """Test editing document when user cancels."""
        mock_temp.return_value.__enter__.return_value.name = "/tmp/test.md"
        mock_run.return_value.returncode = 1  # User cancelled
        
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        
        with patch("emdx.textual_browser_minimal.db") as mock_db:
            mock_db.get_document.return_value = {
                "id": 1,
                "title": "Test",
                "content": "Content",
                "project": "test"
            }
            
            result = browser.edit_document_with_vim(1)
        
        assert result is False

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    def test_edit_document_with_vim_no_document(self, mock_run, mock_temp):
        """Test editing non-existent document."""
        browser = textual_browser_minimal.KnowledgeBaseBrowser()
        
        with patch("emdx.textual_browser_minimal.db") as mock_db:
            mock_db.get_document.return_value = None
            
            result = browser.edit_document_with_vim(999)
        
        assert result is False
        mock_run.assert_not_called()


class TestUtilityFunctions:
    """Test utility functions in the module."""

    def test_main_function_exists(self):
        """Test that main function exists."""
        assert hasattr(textual_browser_minimal, 'main')
        
    @patch("emdx.textual_browser_minimal.KnowledgeBaseBrowser")
    def test_main_function_runs_app(self, mock_browser_class):
        """Test that main function creates and runs the app."""
        mock_app = MagicMock()
        mock_browser_class.return_value = mock_app
        
        textual_browser_minimal.main()
        
        mock_browser_class.assert_called_once()
        mock_app.run.assert_called_once()