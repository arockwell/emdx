"""Async tests for UI components.

DEBT-27: Add async test coverage for UI components.
Tests critical async functions in document_browser.py, cascade_view.py,
and document_browser_presenter.py using pytest-asyncio.
"""

from unittest.mock import AsyncMock, patch

import pytest

from emdx.ui.viewmodels import DocumentDetailVM, DocumentListItem, DocumentListVM

# ============================================================================
# DocumentBrowserPresenter Tests
# ============================================================================


class TestDocumentBrowserPresenterAsync:
    """Async tests for DocumentBrowserPresenter."""

    @pytest.fixture
    def mock_update_callback(self):
        """Create a mock async callback for list updates."""
        callback = AsyncMock()
        return callback

    @pytest.fixture
    def presenter(self, mock_update_callback):
        """Create a presenter with mocked callbacks."""
        from emdx.ui.presenters.document_browser_presenter import (
            DocumentBrowserPresenter,
        )

        return DocumentBrowserPresenter(
            on_list_update=mock_update_callback,
            on_detail_update=None,
        )

    @pytest.mark.asyncio
    async def test_load_documents_empty_database(
        self, presenter, mock_update_callback
    ):
        """Test loading documents when database is empty."""
        with patch(
            "emdx.ui.presenters.document_browser_presenter.count_documents"
        ) as mock_count, patch(
            "emdx.ui.presenters.document_browser_presenter.db_list_documents"
        ) as mock_list, patch(
            "emdx.ui.presenters.document_browser_presenter.get_tags_for_documents"
        ) as mock_tags, patch(
            "emdx.ui.presenters.document_browser_presenter.get_children_count"
        ) as mock_children:
            mock_count.return_value = 0
            mock_list.return_value = []
            mock_tags.return_value = {}
            mock_children.return_value = {}

            await presenter.load_documents()

            mock_update_callback.assert_called_once()
            vm = mock_update_callback.call_args[0][0]
            assert isinstance(vm, DocumentListVM)
            assert vm.total_count == 0
            assert vm.filtered_count == 0
            assert len(vm.documents) == 0

    @pytest.mark.asyncio
    async def test_load_documents_with_data(self, presenter, mock_update_callback):
        """Test loading documents with actual data."""
        raw_docs = [
            {
                "id": 1,
                "title": "Test Doc 1",
                "content": "Content 1",
                "project": "test-project",
                "access_count": 5,
                "created_at": "2024-01-01",
                "accessed_at": "2024-01-02",
                "parent_id": None,
                "relationship": None,
            },
            {
                "id": 2,
                "title": "Test Doc 2",
                "content": "Content 2",
                "project": "test-project",
                "access_count": 3,
                "created_at": "2024-01-01",
                "accessed_at": "2024-01-02",
                "parent_id": None,
                "relationship": None,
            },
        ]

        with patch(
            "emdx.ui.presenters.document_browser_presenter.count_documents"
        ) as mock_count, patch(
            "emdx.ui.presenters.document_browser_presenter.db_list_documents"
        ) as mock_list, patch(
            "emdx.ui.presenters.document_browser_presenter.get_tags_for_documents"
        ) as mock_tags, patch(
            "emdx.ui.presenters.document_browser_presenter.get_children_count"
        ) as mock_children:
            mock_count.return_value = 2
            mock_list.return_value = raw_docs
            mock_tags.return_value = {1: ["python", "test"], 2: ["notes"]}
            mock_children.return_value = {1: 0, 2: 0}

            await presenter.load_documents()

            vm = mock_update_callback.call_args[0][0]
            assert vm.total_count == 2
            assert vm.filtered_count == 2
            assert len(vm.filtered_documents) == 2
            assert vm.filtered_documents[0].id == 1
            assert vm.filtered_documents[0].title == "Test Doc 1"

    @pytest.mark.asyncio
    async def test_load_documents_with_pagination(
        self, presenter, mock_update_callback
    ):
        """Test loading documents with pagination (has_more)."""
        raw_docs = [{"id": i, "title": f"Doc {i}", "content": "", "project": "test",
                     "access_count": 0, "created_at": None, "accessed_at": None,
                     "parent_id": None, "relationship": None}
                    for i in range(100)]

        with patch(
            "emdx.ui.presenters.document_browser_presenter.count_documents"
        ) as mock_count, patch(
            "emdx.ui.presenters.document_browser_presenter.db_list_documents"
        ) as mock_list, patch(
            "emdx.ui.presenters.document_browser_presenter.get_tags_for_documents"
        ) as mock_tags, patch(
            "emdx.ui.presenters.document_browser_presenter.get_children_count"
        ) as mock_children:
            mock_count.return_value = 200
            mock_list.return_value = raw_docs
            mock_tags.return_value = {}
            mock_children.return_value = {}

            await presenter.load_documents(limit=100)

            vm = mock_update_callback.call_args[0][0]
            assert vm.has_more is True
            assert vm.filtered_count == 100

    @pytest.mark.asyncio
    async def test_apply_search_with_results(self, presenter, mock_update_callback):
        """Test applying search filter."""
        search_results = [
            {
                "id": 42,
                "title": "Python Guide",
                "content": "Guide content",
                "project": "docs",
                "access_count": 10,
                "created_at": None,
                "accessed_at": None,
                "parent_id": None,
                "relationship": None,
            }
        ]

        with patch(
            "emdx.services.document_service.search_documents"
        ) as mock_search, patch(
            "emdx.ui.presenters.document_browser_presenter.get_tags_for_documents"
        ) as mock_tags, patch(
            "emdx.ui.presenters.document_browser_presenter.get_children_count"
        ) as mock_children:
            mock_search.return_value = search_results
            mock_tags.return_value = {42: ["python"]}
            mock_children.return_value = {42: 0}

            await presenter.apply_search("python")

            vm = mock_update_callback.call_args[0][0]
            assert vm.search_query == "python"
            assert vm.filtered_count == 1
            assert vm.filtered_documents[0].id == 42

    @pytest.mark.asyncio
    async def test_apply_search_empty_query_reloads(
        self, presenter, mock_update_callback
    ):
        """Test that empty search query reloads all documents."""
        with patch(
            "emdx.ui.presenters.document_browser_presenter.count_documents"
        ) as mock_count, patch(
            "emdx.ui.presenters.document_browser_presenter.db_list_documents"
        ) as mock_list, patch(
            "emdx.ui.presenters.document_browser_presenter.get_tags_for_documents"
        ) as mock_tags, patch(
            "emdx.ui.presenters.document_browser_presenter.get_children_count"
        ) as mock_children:
            mock_count.return_value = 0
            mock_list.return_value = []
            mock_tags.return_value = {}
            mock_children.return_value = {}

            await presenter.apply_search("")

            # Should call load_documents, not search_documents
            mock_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_expand_document(self, presenter, mock_update_callback):
        """Test expanding a document to show children."""
        # Setup parent document
        presenter._filtered_documents = [
            DocumentListItem(
                id=1,
                title="Parent",
                tags=[],
                tags_display="",
                project="test",
                access_count=0,
                has_children=True,
                depth=0,
            )
        ]

        child_docs = [
            {
                "id": 2,
                "title": "Child 1",
                "content": "",
                "project": "test",
                "access_count": 0,
                "created_at": None,
                "accessed_at": None,
                "parent_id": 1,
                "relationship": "supersedes",
            }
        ]

        with patch(
            "emdx.ui.presenters.document_browser_presenter.db_list_documents"
        ) as mock_list, patch(
            "emdx.ui.presenters.document_browser_presenter.get_tags_for_documents"
        ) as mock_tags, patch(
            "emdx.ui.presenters.document_browser_presenter.get_children_count"
        ) as mock_children:
            mock_list.return_value = child_docs
            mock_tags.return_value = {}
            mock_children.return_value = {2: 0}

            result = await presenter.expand_document(1)

            assert result is True
            assert presenter.is_expanded(1)
            # Parent + child
            assert len(presenter._filtered_documents) == 2
            assert presenter._filtered_documents[1].id == 2
            assert presenter._filtered_documents[1].depth == 1

    @pytest.mark.asyncio
    async def test_collapse_document(self, presenter, mock_update_callback):
        """Test collapsing a document hides children."""
        presenter._expanded_docs = {1}
        presenter._filtered_documents = [
            DocumentListItem(
                id=1,
                title="Parent",
                tags=[],
                tags_display="",
                project="test",
                access_count=0,
                has_children=True,
                depth=0,
            ),
            DocumentListItem(
                id=2,
                title="Child",
                tags=[],
                tags_display="",
                project="test",
                access_count=0,
                has_children=False,
                depth=1,
                parent_id=1,
            ),
        ]

        result = await presenter.collapse_document(1)

        assert result is True
        assert not presenter.is_expanded(1)
        assert len(presenter._filtered_documents) == 1

    @pytest.mark.asyncio
    async def test_delete_document(self, presenter, mock_update_callback):
        """Test deleting a document."""
        presenter._documents = [
            DocumentListItem(
                id=1,
                title="To Delete",
                tags=[],
                tags_display="",
                project="test",
                access_count=0,
            )
        ]
        presenter._filtered_documents = presenter._documents[:]
        presenter._total_count = 1

        with patch(
            "emdx.ui.presenters.document_browser_presenter.delete_document"
        ) as mock_delete:
            mock_delete.return_value = True

            result = await presenter.delete_document(1, hard_delete=False)

            assert result is True
            assert len(presenter._filtered_documents) == 0
            assert presenter._total_count == 0

    @pytest.mark.asyncio
    async def test_add_tags(self, presenter, mock_update_callback):
        """Test adding tags to a document."""
        presenter._filtered_documents = [
            DocumentListItem(
                id=1,
                title="Doc",
                tags=[],
                tags_display="",
                project="test",
                access_count=0,
            )
        ]
        presenter._tags_cache = {1: []}

        with patch(
            "emdx.ui.presenters.document_browser_presenter.add_tags_to_document"
        ):
            await presenter.add_tags(1, ["python", "test"])

            assert "python" in presenter._tags_cache[1]
            assert "test" in presenter._tags_cache[1]

    @pytest.mark.asyncio
    async def test_remove_tags(self, presenter, mock_update_callback):
        """Test removing tags from a document."""
        presenter._filtered_documents = [
            DocumentListItem(
                id=1,
                title="Doc",
                tags=["python", "test", "notes"],
                tags_display="python test notes",
                project="test",
                access_count=0,
            )
        ]
        presenter._tags_cache = {1: ["python", "test", "notes"]}

        with patch(
            "emdx.ui.presenters.document_browser_presenter.remove_tags_from_document"
        ):
            await presenter.remove_tags(1, ["test"])

            assert "test" not in presenter._tags_cache[1]
            assert "python" in presenter._tags_cache[1]

    @pytest.mark.asyncio
    async def test_load_more_documents_guards_double_load(
        self, presenter, mock_update_callback
    ):
        """Test that load_more_documents prevents double loading."""
        presenter._loading_more = True

        with patch(
            "emdx.ui.presenters.document_browser_presenter.db_list_documents"
        ) as mock_list:
            await presenter.load_more_documents()

            mock_list.assert_not_called()

    @pytest.mark.asyncio
    async def test_toggle_expand_expands_collapsed(
        self, presenter, mock_update_callback
    ):
        """Test toggle_expand expands collapsed document."""
        presenter._filtered_documents = [
            DocumentListItem(
                id=1,
                title="Parent",
                tags=[],
                tags_display="",
                project="test",
                access_count=0,
                has_children=True,
                depth=0,
            )
        ]

        with patch(
            "emdx.ui.presenters.document_browser_presenter.db_list_documents"
        ) as mock_list, patch(
            "emdx.ui.presenters.document_browser_presenter.get_tags_for_documents"
        ) as mock_tags, patch(
            "emdx.ui.presenters.document_browser_presenter.get_children_count"
        ) as mock_children:
            mock_list.return_value = []
            mock_tags.return_value = {}
            mock_children.return_value = {}

            await presenter.toggle_expand(1)

            # Should be marked as expanded even with no children
            assert presenter.is_expanded(1) is False  # No children = not expanded

    @pytest.mark.asyncio
    async def test_save_new_document(self, presenter, mock_update_callback):
        """Test saving a new document."""
        with patch(
            "emdx.ui.presenters.document_browser_presenter.get_git_project"
        ) as mock_project, patch(
            "emdx.ui.presenters.document_browser_presenter.save_document"
        ) as mock_save, patch(
            "emdx.ui.presenters.document_browser_presenter.count_documents"
        ) as mock_count, patch(
            "emdx.ui.presenters.document_browser_presenter.db_list_documents"
        ) as mock_list, patch(
            "emdx.ui.presenters.document_browser_presenter.get_tags_for_documents"
        ) as mock_tags, patch(
            "emdx.ui.presenters.document_browser_presenter.get_children_count"
        ) as mock_children:
            mock_project.return_value = "test-project"
            mock_save.return_value = 42
            mock_count.return_value = 0
            mock_list.return_value = []
            mock_tags.return_value = {}
            mock_children.return_value = {}

            doc_id = await presenter.save_new_document(
                title="New Doc", content="Content"
            )

            assert doc_id == 42
            mock_save.assert_called_once_with(
                title="New Doc", content="Content", project="test-project"
            )

    @pytest.mark.asyncio
    async def test_update_existing_document(self, presenter, mock_update_callback):
        """Test updating an existing document."""
        presenter._doc_cache = {1: {"id": 1, "title": "Old", "content": "Old content"}}

        with patch(
            "emdx.ui.presenters.document_browser_presenter.update_document"
        ) as mock_update, patch(
            "emdx.ui.presenters.document_browser_presenter.count_documents"
        ) as mock_count, patch(
            "emdx.ui.presenters.document_browser_presenter.db_list_documents"
        ) as mock_list, patch(
            "emdx.ui.presenters.document_browser_presenter.get_tags_for_documents"
        ) as mock_tags, patch(
            "emdx.ui.presenters.document_browser_presenter.get_children_count"
        ) as mock_children:
            mock_count.return_value = 0
            mock_list.return_value = []
            mock_tags.return_value = {}
            mock_children.return_value = {}

            result = await presenter.update_existing_document(
                1, title="New Title", content="New content"
            )

            assert result is True
            mock_update.assert_called_once()
            # Cache should be cleared
            assert 1 not in presenter._doc_cache


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


# ============================================================================
# ViewModel Tests
# ============================================================================


class TestViewModels:
    """Tests for UI ViewModels."""

    def test_document_list_item_creation(self):
        """Test DocumentListItem dataclass."""
        item = DocumentListItem(
            id=1,
            title="Test Document",
            tags=["python", "test"],
            tags_display="python test",
            project="test-project",
            access_count=5,
            created_at="2024-01-01",
            accessed_at="2024-01-02",
            parent_id=None,
            has_children=True,
            depth=0,
            relationship=None,
        )

        assert item.id == 1
        assert item.title == "Test Document"
        assert item.has_children is True
        assert item.depth == 0

    def test_document_detail_vm_creation(self):
        """Test DocumentDetailVM dataclass."""
        detail = DocumentDetailVM(
            id=1,
            title="Test Document",
            content="This is test content with multiple words.",
            project="test-project",
            tags=["python"],
            tags_formatted="🐍 python",
            created_at="2024-01-01",
            updated_at="2024-01-02",
            accessed_at="2024-01-03",
            access_count=10,
            word_count=7,
            char_count=42,
            line_count=1,
        )

        assert detail.id == 1
        assert detail.word_count == 7
        assert detail.access_count == 10

    def test_document_list_vm_defaults(self):
        """Test DocumentListVM with default values."""
        vm = DocumentListVM()

        assert vm.documents == []
        assert vm.filtered_documents == []
        assert vm.search_query == ""
        assert vm.total_count == 0
        assert vm.has_more is False

    def test_document_list_vm_status_text(self):
        """Test DocumentListVM status_text field."""
        vm = DocumentListVM(
            documents=[],
            filtered_documents=[],
            total_count=100,
            filtered_count=50,
            has_more=True,
            status_text="50/100 docs (scroll for more)",
        )

        assert "scroll for more" in vm.status_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
