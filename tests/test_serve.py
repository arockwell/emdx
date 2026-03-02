"""Tests for the serve command (JSON-RPC server)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from unittest.mock import patch

import pytest

from emdx.commands.serve import _handle_request, _serialize


# ---------------------------------------------------------------------------
# Unit tests for _serialize
# ---------------------------------------------------------------------------
class TestSerialize:
    """Tests for the JSON serializer helper."""

    def test_serialize_datetime(self) -> None:
        dt = datetime(2026, 1, 15, 10, 30, 0)
        result = _serialize(dt)
        assert result == "2026-01-15 10:30:00"

    def test_serialize_unsupported_type_raises(self) -> None:
        with pytest.raises(TypeError, match="not JSON serializable"):
            _serialize(set())


# ---------------------------------------------------------------------------
# Unit tests for _handle_request
# ---------------------------------------------------------------------------
class TestHandleRequest:
    """Tests for the JSON-RPC request handler."""

    def test_unknown_method(self) -> None:
        """Unknown method returns error with code -32601."""
        request: dict[str, Any] = {
            "id": 1,
            "method": "nonexistent.method",
            "params": {},
        }
        response = _handle_request(request)
        assert response["id"] == 1
        assert "error" in response
        assert response["error"]["code"] == -32601
        assert "Unknown method" in response["error"]["message"]

    @patch("emdx.commands.serve.get_recent_documents")
    def test_find_recent(self, mock_recent: Any) -> None:
        """find.recent returns recent documents."""
        mock_recent.return_value = [
            {"id": 1, "title": "Doc 1", "created_at": "2026-01-15"},
            {"id": 2, "title": "Doc 2", "created_at": "2026-01-14"},
        ]

        request: dict[str, Any] = {
            "id": 1,
            "method": "find.recent",
            "params": {"limit": 10},
        }
        response = _handle_request(request)
        assert response["id"] == 1
        assert "result" in response
        assert len(response["result"]) == 2

    @patch("emdx.commands.serve.search_documents")
    def test_find_search(self, mock_search: Any) -> None:
        """find.search returns search results."""
        mock_search.return_value = [
            {"id": 1, "title": "Found Doc"},
        ]

        request: dict[str, Any] = {
            "id": 2,
            "method": "find.search",
            "params": {"query": "test", "limit": 5},
        }
        response = _handle_request(request)
        assert response["id"] == 2
        assert len(response["result"]) == 1
        assert response["result"][0]["title"] == "Found Doc"

    @patch("emdx.commands.serve.search_by_tags")
    def test_find_by_tags(self, mock_tags: Any) -> None:
        """find.by_tags returns tag-filtered results."""
        mock_tags.return_value = [
            {"id": 5, "title": "Tagged Doc"},
        ]

        request: dict[str, Any] = {
            "id": 3,
            "method": "find.by_tags",
            "params": {"tags": "python,testing"},
        }
        response = _handle_request(request)
        assert response["id"] == 3
        assert len(response["result"]) == 1

    @patch("emdx.database.document_links.get_links_for_document")
    @patch("emdx.models.tags.get_document_tags")
    @patch("emdx.commands.serve.get_document")
    def test_view_document(self, mock_get_doc: Any, mock_get_tags: Any, mock_links: Any) -> None:
        """view returns document with tags and links."""
        mock_get_doc.return_value = {
            "id": 42,
            "title": "My Document",
            "content": "Hello world",
            "project": "test",
        }
        mock_get_tags.return_value = ["python"]
        mock_links.return_value = []

        request: dict[str, Any] = {
            "id": 4,
            "method": "view",
            "params": {"id": 42},
        }
        response = _handle_request(request)
        assert response["id"] == 4
        assert response["result"]["title"] == "My Document"
        assert response["result"]["tags"] == ["python"]
        assert response["result"]["linked_docs"] == []

    @patch("emdx.commands.serve.get_document")
    def test_view_document_not_found(self, mock_get_doc: Any) -> None:
        """view returns None for missing document."""
        mock_get_doc.return_value = None

        request: dict[str, Any] = {
            "id": 5,
            "method": "view",
            "params": {"id": 999},
        }
        response = _handle_request(request)
        assert response["id"] == 5
        assert response["result"] is None

    @patch("emdx.commands.serve.save_document")
    def test_save_document(self, mock_save: Any) -> None:
        """save creates a new document."""
        mock_save.return_value = 100

        request: dict[str, Any] = {
            "id": 6,
            "method": "save",
            "params": {"title": "New Doc", "content": "Content here"},
        }
        response = _handle_request(request)
        assert response["id"] == 6
        assert response["result"]["id"] == 100
        assert response["result"]["title"] == "New Doc"

    @patch("emdx.commands.serve.list_all_tags")
    def test_tag_list(self, mock_tags: Any) -> None:
        """tag.list returns all tags."""
        mock_tags.return_value = [
            {"name": "python", "usage_count": 10},
            {"name": "testing", "usage_count": 5},
        ]

        request: dict[str, Any] = {
            "id": 7,
            "method": "tag.list",
            "params": {},
        }
        response = _handle_request(request)
        assert response["id"] == 7
        assert len(response["result"]) == 2

    @patch("emdx.commands.serve.list_tasks")
    def test_task_list(self, mock_tasks: Any) -> None:
        """task.list returns tasks."""
        mock_tasks.return_value = [
            {"id": 1, "title": "Task 1", "status": "open"},
        ]

        request: dict[str, Any] = {
            "id": 8,
            "method": "task.list",
            "params": {},
        }
        response = _handle_request(request)
        assert response["id"] == 8
        assert len(response["result"]) == 1

    @patch("emdx.commands.serve.update_task")
    def test_task_update(self, mock_update: Any) -> None:
        """task.update changes task status."""
        request: dict[str, Any] = {
            "id": 9,
            "method": "task.update",
            "params": {"id": 1, "status": "done"},
        }
        response = _handle_request(request)
        assert response["id"] == 9
        assert response["result"]["ok"] is True
        mock_update.assert_called_once_with(1, status="done")

    @patch("emdx.commands.serve.log_progress")
    def test_task_log_progress(self, mock_log: Any) -> None:
        """task.log_progress creates a progress entry."""
        mock_log.return_value = 42

        request: dict[str, Any] = {
            "id": 10,
            "method": "task.log_progress",
            "params": {"id": 1, "message": "Working on it"},
        }
        response = _handle_request(request)
        assert response["id"] == 10
        assert response["result"]["id"] == 42

    @patch("emdx.commands.serve.list_tasks")
    def test_status_method(self, mock_tasks: Any) -> None:
        """status returns current task status."""
        mock_tasks.return_value = [
            {"id": 1, "title": "Active Task", "status": "active"},
        ]

        request: dict[str, Any] = {
            "id": 11,
            "method": "status",
            "params": {},
        }
        response = _handle_request(request)
        assert response["id"] == 11
        assert "tasks" in response["result"]

    def test_handler_exception_returns_error(self) -> None:
        """Handler exceptions are caught and returned as errors."""
        # find.search requires a 'query' param -- omitting it raises KeyError
        request: dict[str, Any] = {
            "id": 99,
            "method": "find.search",
            "params": {},
        }
        response = _handle_request(request)
        assert response["id"] == 99
        assert "error" in response
        assert response["error"]["code"] == -1

    def test_missing_id_in_request(self) -> None:
        """Request without id returns None as id."""
        request: dict[str, Any] = {
            "method": "nonexistent",
            "params": {},
        }
        response = _handle_request(request)
        assert response["id"] is None

    def test_default_params(self) -> None:
        """Request without params defaults to empty dict."""
        request: dict[str, Any] = {
            "id": 100,
            "method": "nonexistent",
        }
        response = _handle_request(request)
        assert "error" in response


# ---------------------------------------------------------------------------
# Verify all registered methods
# ---------------------------------------------------------------------------
class TestMethodRegistry:
    """Tests for the method dispatch table."""

    def test_all_expected_methods_registered(self) -> None:
        """All expected RPC methods are in the dispatch table."""
        from emdx.commands.serve import METHODS

        expected_methods = [
            "find.recent",
            "find.search",
            "find.by_tags",
            "view",
            "save",
            "tag.list",
            "task.list",
            "task.log",
            "task.update",
            "task.log_progress",
            "status",
        ]
        for method in expected_methods:
            assert method in METHODS, f"Method {method} not registered"
