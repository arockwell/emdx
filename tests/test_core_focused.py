"""Focused tests for core functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import tempfile
from pathlib import Path

# We need to mock the database to test core functions
@pytest.fixture
def mock_db():
    """Mock database for testing core functions."""
    db = Mock()
    db.save_document = Mock(return_value=1)
    db.get_document = Mock(return_value={
        'id': 1,
        'title': 'Test Doc',
        'content': 'Test content',
        'project': 'test'
    })
    db.search_documents = Mock(return_value=[
        {'id': 1, 'title': 'Test Doc', 'snippet': 'Test...'}
    ])
    db.list_documents = Mock(return_value=[])
    return db


@patch('emdx.core.db')
def test_save_command(mock_db_global, tmp_path):
    """Test save command functionality."""
    from emdx.core import save_document
    
    # Create a test file
    test_file = tmp_path / "test.md"
    test_file.write_text("# Test Document\n\nTest content")
    
    mock_db_global.save_document.return_value = 1
    
    # Import here to ensure mock is in place
    with patch('emdx.core.console') as mock_console:
        save_document(str(test_file), title="Custom Title", project="test-project")
    
    # Verify save was called with correct args
    mock_db_global.save_document.assert_called_once()
    call_args = mock_db_global.save_document.call_args[0]
    assert call_args[0] == "Custom Title"
    assert "Test content" in call_args[1]
    assert call_args[2] == "test-project"


@patch('emdx.core.db')
@patch('emdx.core.console')
def test_find_command(mock_console, mock_db_global):
    """Test find command functionality."""
    from emdx.core import find_documents
    
    mock_db_global.search_documents.return_value = [
        {
            'id': 1,
            'title': 'Python Guide',
            'snippet': 'Learn <b>Python</b>...',
            'project': 'docs'
        }
    ]
    
    find_documents("Python", project=None, limit=10)
    
    mock_db_global.search_documents.assert_called_once_with("Python", project=None, limit=10)
    # Should print results
    mock_console.print.assert_called()


@patch('emdx.core.db')
@patch('emdx.core.get_editor')
@patch('emdx.core.subprocess.run')
@patch('emdx.core.console')
def test_view_command(mock_console, mock_subprocess, mock_editor, mock_db_global):
    """Test view command functionality."""
    from emdx.core import view_document
    
    mock_db_global.get_document.return_value = {
        'id': 1,
        'title': 'Test Doc',
        'content': '# Test\n\nContent here',
        'project': 'test'
    }
    mock_editor.return_value = "vim"
    mock_subprocess.return_value.returncode = 0
    
    with patch('tempfile.NamedTemporaryFile'):
        view_document("1", raw=False)
    
    mock_db_global.get_document.assert_called_once_with("1")
    mock_subprocess.assert_called_once()


@patch('emdx.core.db') 
@patch('emdx.core.Confirm.ask')
@patch('emdx.core.console')
def test_delete_command(mock_console, mock_confirm, mock_db_global):
    """Test delete command functionality."""
    from emdx.core import delete_document
    
    mock_db_global.get_document.return_value = {
        'id': 1,
        'title': 'To Delete',
        'content': 'Content'
    }
    mock_db_global.delete_document.return_value = True
    mock_confirm.return_value = True
    
    delete_document("1", force=False)
    
    mock_db_global.get_document.assert_called_once_with("1")
    mock_confirm.assert_called_once()
    mock_db_global.delete_document.assert_called_once_with("1")