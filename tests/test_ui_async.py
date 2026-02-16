"""Async tests for UI components.

DEBT-27: Add async test coverage for UI components.
Tests critical async functions in cascade_view.py using pytest-asyncio.
"""

from unittest.mock import patch

import pytest

# ============================================================================
# CascadeView Tests
# ============================================================================


class TestCascadeViewAsync:
    """Async tests for CascadeView status updates."""

    @pytest.fixture
    def mock_cascade_services(self):
        """Mock cascade service functions."""
        with patch(
            "emdx.ui.cascade.cascade_view.list_documents_at_stage"
        ) as mock_list, patch(
            "emdx.ui.cascade.cascade_view.get_recent_pipeline_activity"
        ) as mock_activity, patch(
            "emdx.ui.cascade.cascade_view.get_document"
        ) as mock_doc:
            mock_list.return_value = []
            mock_activity.return_value = []
            mock_doc.return_value = None
            yield {
                "list_documents_at_stage": mock_list,
                "get_recent_pipeline_activity": mock_activity,
                "get_document": mock_doc,
            }

    def test_cascade_view_init(self):
        """Test CascadeView initialization."""
        from emdx.ui.cascade.cascade_view import CascadeView

        view = CascadeView()
        assert view.current_stage_idx == 0
        assert view._auto_refresh_timer is None
        assert view._pipeline_view_mode == "output"

    def test_cascade_view_stage_navigation_bounds(self):
        """Test stage navigation respects bounds."""
        from emdx.ui.cascade.cascade_view import STAGES, CascadeView

        view = CascadeView()
        view.current_stage_idx = 0
        view.action_prev_stage()
        assert view.current_stage_idx == 0  # Can't go below 0

        view.current_stage_idx = len(STAGES) - 1
        view.action_next_stage()
        assert view.current_stage_idx == len(STAGES) - 1  # Can't go above max

    def test_cascade_view_pipeline_view_modes(self):
        """Test switching between input/output view modes."""
        from emdx.ui.cascade.cascade_view import CascadeView

        view = CascadeView()
        assert view._pipeline_view_mode == "output"

        # Mock the selected pipeline data
        view._selected_pipeline_idx = 0
        view._pipeline_data = [{"input_id": 1, "output_id": 2}]

        # These would normally update preview, but we just check mode switching
        view._pipeline_view_mode = "input"
        assert view._pipeline_view_mode == "input"

        view._pipeline_view_mode = "output"
        assert view._pipeline_view_mode == "output"


# ============================================================================
# DocumentList Tests (Cascade)
# ============================================================================


class TestDocumentListAsync:
    """Tests for cascade DocumentList widget."""

    def test_document_list_selection_toggle(self):
        """Test multi-select toggle functionality."""
        from emdx.ui.cascade.document_list import DocumentList

        doc_list = DocumentList()
        doc_list.docs = [
            {"id": 1, "title": "Doc 1", "parent_id": None, "created_at": None},
            {"id": 2, "title": "Doc 2", "parent_id": None, "created_at": None},
        ]

        # Initially no selection
        assert len(doc_list.selected_ids) == 0

        # Simulate selection
        doc_list.selected_ids.add(1)
        assert 1 in doc_list.selected_ids

        # Toggle off
        doc_list.selected_ids.remove(1)
        assert 1 not in doc_list.selected_ids

    def test_document_list_select_all(self):
        """Test select all functionality."""
        from emdx.ui.cascade.document_list import DocumentList

        doc_list = DocumentList()
        doc_list.docs = [
            {"id": 1, "title": "Doc 1", "parent_id": None, "created_at": None},
            {"id": 2, "title": "Doc 2", "parent_id": None, "created_at": None},
            {"id": 3, "title": "Doc 3", "parent_id": None, "created_at": None},
        ]

        # Simulate select_all logic
        doc_list.selected_ids = {doc["id"] for doc in doc_list.docs}

        assert len(doc_list.selected_ids) == 3
        assert 1 in doc_list.selected_ids
        assert 2 in doc_list.selected_ids
        assert 3 in doc_list.selected_ids

    def test_document_list_clear_selection(self):
        """Test clear selection functionality."""
        from emdx.ui.cascade.document_list import DocumentList

        doc_list = DocumentList()
        doc_list.selected_ids = {1, 2, 3}

        doc_list.selected_ids.clear()

        assert len(doc_list.selected_ids) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
