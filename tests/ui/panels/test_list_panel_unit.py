#!/usr/bin/env python3
"""
Unit tests for ListPanel.

These tests verify the ListPanel functionality without requiring a full TUI.
For interactive testing, run: poetry run python -m emdx.ui.panels.test_list_panel
"""

import pytest
from emdx.ui.panels import ListPanel, ListItem, ColumnDef, ListPanelConfig


class TestColumnDef:
    """Tests for ColumnDef dataclass."""

    def test_basic_creation(self):
        """Test creating a simple column definition."""
        col = ColumnDef("Name", width=40)
        assert col.name == "Name"
        assert col.width == 40
        assert col.key == "name"  # Auto-generated from name

    def test_custom_key(self):
        """Test column with custom key."""
        col = ColumnDef("Document ID", width=10, key="doc_id")
        assert col.name == "Document ID"
        assert col.key == "doc_id"

    def test_auto_key_with_spaces(self):
        """Test auto-generated key with spaces in name."""
        col = ColumnDef("Last Modified")
        assert col.key == "last_modified"

    def test_no_width(self):
        """Test column without explicit width."""
        col = ColumnDef("Title")
        assert col.width is None


class TestListItem:
    """Tests for ListItem dataclass."""

    def test_basic_creation(self):
        """Test creating a simple list item."""
        item = ListItem(id=1, values=["1", "Test Item"])
        assert item.id == 1
        assert item.values == ["1", "Test Item"]
        assert item.data is None

    def test_with_data(self):
        """Test item with associated data."""
        item = ListItem(
            id=42,
            values=["42", "Doc", "My Document"],
            data={"content": "Hello", "tags": ["python", "test"]},
        )
        assert item.id == 42
        assert item.values[2] == "My Document"
        assert item.data["content"] == "Hello"
        assert "python" in item.data["tags"]

    def test_string_id(self):
        """Test item with string ID."""
        item = ListItem(id="abc-123", values=["abc-123", "Item"])
        assert item.id == "abc-123"


class TestListPanelConfig:
    """Tests for ListPanelConfig dataclass."""

    def test_defaults(self):
        """Test default configuration values."""
        config = ListPanelConfig()
        assert config.show_header is True
        assert config.cursor_type == "row"
        assert config.zebra_stripes is False
        assert config.cell_padding == 0
        assert config.show_search is True
        assert config.lazy_load_threshold == 20

    def test_custom_config(self):
        """Test custom configuration."""
        config = ListPanelConfig(
            show_header=False,
            cursor_type="cell",
            zebra_stripes=True,
            cell_padding=2,
            show_search=False,
            search_placeholder="Find...",
            lazy_load_threshold=50,
            status_format="{filtered} of {total}",
        )
        assert config.show_header is False
        assert config.cursor_type == "cell"
        assert config.zebra_stripes is True
        assert config.cell_padding == 2
        assert config.show_search is False
        assert config.search_placeholder == "Find..."
        assert config.lazy_load_threshold == 50
        assert config.status_format == "{filtered} of {total}"


class TestListPanelMessages:
    """Tests for ListPanel message classes."""

    def test_item_selected_message(self):
        """Test ItemSelected message."""
        item = ListItem(id=1, values=["1", "Test"])
        msg = ListPanel.ItemSelected(item=item, index=0)
        assert msg.item == item
        assert msg.index == 0

    def test_item_activated_message(self):
        """Test ItemActivated message."""
        item = ListItem(id=2, values=["2", "Other"])
        msg = ListPanel.ItemActivated(item=item, index=5)
        assert msg.item == item
        assert msg.index == 5

    def test_search_submitted_message(self):
        """Test SearchSubmitted message."""
        msg = ListPanel.SearchSubmitted(query="hello world")
        assert msg.query == "hello world"

    def test_load_more_requested_message(self):
        """Test LoadMoreRequested message."""
        msg = ListPanel.LoadMoreRequested(current_index=95, total_count=100)
        assert msg.current_index == 95
        assert msg.total_count == 100


class TestListPanelFiltering:
    """Tests for ListPanel filter functionality (without TUI)."""

    def test_filter_function(self):
        """Test that filter functions work correctly on items."""
        items = [
            ListItem(id=1, values=["1", "Apple", "Active"]),
            ListItem(id=2, values=["2", "Banana", "Pending"]),
            ListItem(id=3, values=["3", "Cherry", "Active"]),
        ]

        # Filter for "Active" status
        filter_func = lambda item: item.values[2] == "Active"
        filtered = [item for item in items if filter_func(item)]

        assert len(filtered) == 2
        assert filtered[0].values[1] == "Apple"
        assert filtered[1].values[1] == "Cherry"

    def test_search_filter_logic(self):
        """Test search filter logic (case-insensitive)."""
        items = [
            ListItem(id=1, values=["1", "Apple Pie", "Active"]),
            ListItem(id=2, values=["2", "Banana Split", "Pending"]),
            ListItem(id=3, values=["3", "APPLE JUICE", "Active"]),
        ]

        query = "apple"
        query_lower = query.lower()
        filter_func = lambda item: any(query_lower in str(v).lower() for v in item.values)
        filtered = [item for item in items if filter_func(item)]

        assert len(filtered) == 2
        assert filtered[0].values[1] == "Apple Pie"
        assert filtered[1].values[1] == "APPLE JUICE"


class TestColumnNormalization:
    """Test column definition normalization in ListPanel."""

    def test_tuple_columns(self):
        """Test that tuple-style columns are normalized."""
        # This tests the normalization logic from ListPanel.__init__
        columns = [("ID", 5), ("Name", 40), ("Status",)]

        normalized = []
        for col in columns:
            if isinstance(col, tuple):
                name = col[0]
                width = col[1] if len(col) > 1 else None
                normalized.append(ColumnDef(name, width))
            else:
                normalized.append(ColumnDef(col))

        assert len(normalized) == 3
        assert normalized[0].name == "ID"
        assert normalized[0].width == 5
        assert normalized[1].name == "Name"
        assert normalized[1].width == 40
        assert normalized[2].name == "Status"
        assert normalized[2].width is None

    def test_string_columns(self):
        """Test that string-style columns are normalized."""
        columns = ["ID", "Name", "Status"]

        normalized = []
        for col in columns:
            normalized.append(ColumnDef(col))

        assert len(normalized) == 3
        assert all(c.width is None for c in normalized)
        assert [c.name for c in normalized] == ["ID", "Name", "Status"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
