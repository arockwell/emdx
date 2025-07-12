"""Tests for textual_browser_minimal module."""

import os
from unittest.mock import MagicMock, patch

import pytest

from test_fixtures import TestDatabase


class TestBrowserImports:
    """Test textual browser module imports."""

    def test_module_imports(self):
        """Test that textual_browser_minimal module can be imported."""
        from emdx import textual_browser_minimal
        assert hasattr(textual_browser_minimal, 'FullScreenView')
        assert hasattr(textual_browser_minimal, 'KnowledgeBaseBrowser')

    def test_fullscreen_view_class(self):
        """Test FullScreenView class exists and is properly defined."""
        from emdx import textual_browser_minimal
        
        assert hasattr(textual_browser_minimal, 'FullScreenView')
        view_class = getattr(textual_browser_minimal, 'FullScreenView')
        assert hasattr(view_class, '__init__')
        assert hasattr(view_class, 'compose')

    def test_browser_class(self):
        """Test KnowledgeBaseBrowser class exists and is properly defined."""
        from emdx import textual_browser_minimal
        
        assert hasattr(textual_browser_minimal, 'KnowledgeBaseBrowser')
        browser_class = getattr(textual_browser_minimal, 'KnowledgeBaseBrowser')
        assert hasattr(browser_class, '__init__')
        assert hasattr(browser_class, 'compose')


class TestFullScreenView:
    """Test FullScreenView functionality."""

    @patch("emdx.textual_browser_minimal.db")
    def test_fullscreen_view_init(self, mock_db):
        """Test FullScreenView initialization."""
        from emdx.textual_browser_minimal import FullScreenView
        
        view = FullScreenView(doc_id=123)
        assert view.doc_id == 123

    @patch("emdx.textual_browser_minimal.db")
    def test_fullscreen_view_on_mount_with_document(self, mock_db):
        """Test document loading in FullScreenView."""
        from emdx.textual_browser_minimal import FullScreenView
        
        mock_db.get_document.return_value = {
            "id": 1,
            "title": "Test Document",
            "content": "# Test Document\n\nTest content",
            "project": "test-project"
        }
        
        view = FullScreenView(doc_id=1)
        
        # Mock the query_one method
        mock_content_log = MagicMock()
        view.query_one = MagicMock(return_value=mock_content_log)
        
        view.on_mount()
        
        mock_db.get_document.assert_called_once_with("1")
        mock_content_log.clear.assert_called_once()

    @patch("emdx.textual_browser_minimal.db")
    def test_fullscreen_view_no_document(self, mock_db):
        """Test FullScreenView when document doesn't exist."""
        from emdx.textual_browser_minimal import FullScreenView
        
        mock_db.get_document.return_value = None
        
        view = FullScreenView(doc_id=999)
        view.query_one = MagicMock()
        
        view.on_mount()
        
        mock_db.get_document.assert_called_once_with("999")


class TestKnowledgeBaseBrowser:
    """Test KnowledgeBaseBrowser functionality."""

    @patch("emdx.textual_browser_minimal.db")
    def test_browser_init(self, mock_db):
        """Test browser initialization."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        browser = KnowledgeBaseBrowser()
        assert hasattr(browser, 'search_term')
        assert hasattr(browser, 'current_filter')

    @patch("emdx.textual_browser_minimal.db")
    def test_browser_load_documents(self, mock_db):
        """Test loading documents into the browser."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        mock_db.search_documents.return_value = [
            (1, "Test Document", "Test content", "test-project", "2024-01-01", 1),
            (2, "Another Document", "More content", "other-project", "2024-01-02", 2)
        ]
        
        browser = KnowledgeBaseBrowser()
        mock_table = MagicMock()
        mock_label = MagicMock()
        
        browser.query_one = MagicMock(side_effect=lambda selector, widget_type=None: 
            mock_table if selector == "#documents" else mock_label)
        
        browser.load_documents()
        
        mock_db.search_documents.assert_called()
        assert mock_table.add_row.call_count == 2

    @patch("emdx.textual_browser_minimal.db")
    def test_browser_search_functionality(self, mock_db):
        """Test search functionality."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        mock_db.search_documents.return_value = []
        
        browser = KnowledgeBaseBrowser()
        browser.load_documents = MagicMock()
        
        # Mock input change
        mock_input = MagicMock()
        mock_input.value = "test search"
        
        browser.on_input_changed(mock_input)
        
        assert browser.search_term == "test search"
        browser.load_documents.assert_called_once()


class TestBrowserActions:
    """Test browser action methods."""

    def test_browser_quit_action(self):
        """Test quit action."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        browser = KnowledgeBaseBrowser()
        browser.exit = MagicMock()
        
        browser.action_quit()
        
        browser.exit.assert_called_once()

    @patch("emdx.textual_browser_minimal.db")
    def test_browser_refresh_action(self, mock_db):
        """Test refresh action."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        browser = KnowledgeBaseBrowser()
        browser.load_documents = MagicMock()
        
        browser.action_refresh()
        
        browser.load_documents.assert_called_once()

    def test_browser_help_toggle(self):
        """Test help toggle action."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        browser = KnowledgeBaseBrowser()
        browser.toggle_class = MagicMock()
        
        browser.action_toggle_help()
        
        browser.toggle_class.assert_called_once_with("show-help")


class TestDocumentSelection:
    """Test document selection functionality."""

    def test_get_selected_document_id(self):
        """Test getting selected document ID."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        browser = KnowledgeBaseBrowser()
        
        mock_table = MagicMock()
        mock_table.cursor_row = 0
        mock_table.get_row_at.return_value = ["123", "Test", "project", "date", "count"]
        
        browser.query_one = MagicMock(return_value=mock_table)
        
        doc_id = browser.get_selected_document_id()
        
        assert doc_id == 123

    def test_get_selected_document_id_no_selection(self):
        """Test getting document ID when no row is selected."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        browser = KnowledgeBaseBrowser()
        
        mock_table = MagicMock()
        mock_table.cursor_row = None
        
        browser.query_one = MagicMock(return_value=mock_table)
        
        doc_id = browser.get_selected_document_id()
        
        assert doc_id is None

    def test_get_selected_document_id_empty_table(self):
        """Test getting document ID from empty table."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        browser = KnowledgeBaseBrowser()
        
        mock_table = MagicMock()
        mock_table.cursor_row = 0
        mock_table.get_row_at.side_effect = IndexError()
        
        browser.query_one = MagicMock(return_value=mock_table)
        
        doc_id = browser.get_selected_document_id()
        
        assert doc_id is None


class TestDocumentEditing:
    """Test document editing functionality."""

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    @patch("emdx.textual_browser_minimal.db")
    def test_edit_document_with_vim_success(self, mock_db, mock_run, mock_temp):
        """Test successful document editing with vim."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        mock_temp.return_value.__enter__.return_value.name = "/tmp/test.md"
        mock_run.return_value.returncode = 0
        
        mock_db.get_document.return_value = {
            "id": 1,
            "title": "Test",
            "content": "Content",
            "project": "test"
        }
        
        browser = KnowledgeBaseBrowser()
        result = browser.edit_document_with_vim(1)
        
        assert result is True

    @patch("tempfile.NamedTemporaryFile")
    @patch("subprocess.run")
    @patch("emdx.textual_browser_minimal.db")
    def test_edit_document_with_vim_cancelled(self, mock_db, mock_run, mock_temp):
        """Test document editing when user cancels."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        mock_temp.return_value.__enter__.return_value.name = "/tmp/test.md"
        mock_run.return_value.returncode = 1
        
        mock_db.get_document.return_value = {
            "id": 1,
            "title": "Test",
            "content": "Content",
            "project": "test"
        }
        
        browser = KnowledgeBaseBrowser()
        result = browser.edit_document_with_vim(1)
        
        assert result is False

    @patch("emdx.textual_browser_minimal.db")
    def test_edit_document_not_found(self, mock_db):
        """Test editing non-existent document."""
        from emdx.textual_browser_minimal import KnowledgeBaseBrowser
        
        mock_db.get_document.return_value = None
        
        browser = KnowledgeBaseBrowser()
        result = browser.edit_document_with_vim(999)
        
        assert result is False


class TestMainFunction:
    """Test main function and module execution."""

    def test_main_function_exists(self):
        """Test that main function exists."""
        from emdx import textual_browser_minimal
        assert hasattr(textual_browser_minimal, 'main')

    @patch("emdx.textual_browser_minimal.KnowledgeBaseBrowser")
    def test_main_function_execution(self, mock_browser_class):
        """Test main function execution."""
        from emdx import textual_browser_minimal
        
        mock_app = MagicMock()
        mock_browser_class.return_value = mock_app
        
        textual_browser_minimal.main()
        
        mock_browser_class.assert_called_once()
        mock_app.run.assert_called_once()