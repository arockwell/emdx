"""
Tests for the layout management system.
"""

import pytest
from pathlib import Path
from typing import Dict, Any

from textual.widgets import DataTable, RichLog, Static


class TestSizeSpec:
    """Tests for SizeSpec dataclass."""

    def test_fraction_creation(self):
        """Test creating fractional sizes."""
        from emdx.ui.layout import SizeSpec

        size = SizeSpec.fraction(2)
        assert size.value == 2
        assert size.unit == "fr"
        assert size.to_css() == "2fr"

    def test_percent_creation(self):
        """Test creating percentage sizes."""
        from emdx.ui.layout import SizeSpec

        size = SizeSpec.percent(40)
        assert size.value == 40
        assert size.unit == "%"
        assert size.to_css() == "40%"

    def test_fixed_creation(self):
        """Test creating fixed sizes."""
        from emdx.ui.layout import SizeSpec

        size = SizeSpec.fixed(20)
        assert size.value == 20
        assert size.unit == "px"
        assert size.to_css() == "20"

    def test_auto_creation(self):
        """Test creating auto sizes."""
        from emdx.ui.layout import SizeSpec

        size = SizeSpec.auto()
        assert size.unit == "auto"
        assert size.to_css() == "auto"

    def test_from_string_fraction(self):
        """Test parsing fraction from string."""
        from emdx.ui.layout import SizeSpec

        size = SizeSpec.from_string("2fr")
        assert size.value == 2
        assert size.unit == "fr"

    def test_from_string_percent(self):
        """Test parsing percentage from string."""
        from emdx.ui.layout import SizeSpec

        size = SizeSpec.from_string("40%")
        assert size.value == 40
        assert size.unit == "%"

    def test_from_string_fixed(self):
        """Test parsing fixed size from string."""
        from emdx.ui.layout import SizeSpec

        size = SizeSpec.from_string("20px")
        assert size.value == 20
        assert size.unit == "px"

    def test_from_string_auto(self):
        """Test parsing auto from string."""
        from emdx.ui.layout import SizeSpec

        size = SizeSpec.from_string("auto")
        assert size.unit == "auto"

    def test_from_string_bare_number(self):
        """Test parsing bare number defaults to fraction."""
        from emdx.ui.layout import SizeSpec

        size = SizeSpec.from_string("3")
        assert size.value == 3
        assert size.unit == "fr"

    def test_invalid_unit_raises(self):
        """Test that invalid units raise ValueError."""
        from emdx.ui.layout import SizeSpec

        with pytest.raises(ValueError, match="Invalid unit"):
            SizeSpec(10, "invalid")

    def test_negative_value_raises(self):
        """Test that negative values raise ValueError."""
        from emdx.ui.layout import SizeSpec

        with pytest.raises(ValueError, match="non-negative"):
            SizeSpec(-10, "fr")


class TestPanelSpec:
    """Tests for PanelSpec dataclass."""

    def test_basic_creation(self):
        """Test basic panel creation."""
        from emdx.ui.layout import PanelSpec

        panel = PanelSpec(
            panel_type="list",
            panel_id="doc-list",
        )
        assert panel.panel_type == "list"
        assert panel.panel_id == "doc-list"
        assert panel.config == {}
        assert not panel.collapsible

    def test_with_config(self):
        """Test panel with configuration."""
        from emdx.ui.layout import PanelSpec

        panel = PanelSpec(
            panel_type="table",
            panel_id="doc-table",
            config={"cursor_type": "row", "show_header": True},
        )
        assert panel.config["cursor_type"] == "row"
        assert panel.config["show_header"] is True

    def test_from_dict(self):
        """Test creating from dictionary."""
        from emdx.ui.layout import PanelSpec

        data = {
            "type": "preview",
            "id": "doc-preview",
            "config": {"wrap": True},
            "size": "60%",
            "collapsible": True,
        }
        panel = PanelSpec.from_dict(data)

        assert panel.panel_type == "preview"
        assert panel.panel_id == "doc-preview"
        assert panel.config["wrap"] is True
        assert panel.size.value == 60
        assert panel.size.unit == "%"
        assert panel.collapsible is True


class TestSplitSpec:
    """Tests for SplitSpec dataclass."""

    def test_basic_creation(self):
        """Test basic split creation."""
        from emdx.ui.layout import SplitSpec, PanelSpec

        split = SplitSpec(
            direction="horizontal",
            children=[
                PanelSpec("list", "doc-list"),
                PanelSpec("preview", "doc-preview"),
            ],
        )
        assert split.direction == "horizontal"
        assert len(split.children) == 2

    def test_with_sizes(self):
        """Test split with explicit sizes."""
        from emdx.ui.layout import SplitSpec, PanelSpec, SizeSpec

        split = SplitSpec(
            direction="horizontal",
            children=[
                PanelSpec("list", "doc-list"),
                PanelSpec("preview", "doc-preview"),
            ],
            sizes=[SizeSpec.percent(40), SizeSpec.percent(60)],
        )
        sizes = split.get_child_sizes()
        assert len(sizes) == 2
        assert sizes[0].value == 40
        assert sizes[1].value == 60

    def test_nested_splits(self):
        """Test nested split structures."""
        from emdx.ui.layout import SplitSpec, PanelSpec

        inner_split = SplitSpec(
            direction="vertical",
            children=[
                PanelSpec("list", "doc-list"),
                PanelSpec("details", "doc-details"),
            ],
        )
        outer_split = SplitSpec(
            direction="horizontal",
            children=[
                inner_split,
                PanelSpec("preview", "doc-preview"),
            ],
        )
        assert len(outer_split.children) == 2
        assert isinstance(outer_split.children[0], SplitSpec)

    def test_from_dict_with_ratio(self):
        """Test parsing ratio format from dict."""
        from emdx.ui.layout import SplitSpec

        data = {
            "direction": "horizontal",
            "ratio": [40, 60],
            "children": [
                {"type": "list", "id": "doc-list"},
                {"type": "preview", "id": "doc-preview"},
            ],
        }
        split = SplitSpec.from_dict(data)
        sizes = split.get_child_sizes()

        # Ratio [40, 60] should convert to [40%, 60%]
        assert sizes[0].value == 40
        assert sizes[1].value == 60

    def test_empty_children_raises(self):
        """Test that empty children raises ValueError."""
        from emdx.ui.layout import SplitSpec

        with pytest.raises(ValueError, match="at least one child"):
            SplitSpec(direction="horizontal", children=[])


class TestLayoutConfig:
    """Tests for LayoutConfig dataclass."""

    def test_basic_creation(self):
        """Test basic layout creation."""
        from emdx.ui.layout import LayoutConfig, PanelSpec

        config = LayoutConfig(
            name="simple-layout",
            root=PanelSpec("list", "doc-list"),
        )
        assert config.name == "simple-layout"
        assert config.version == "1.0"

    def test_from_dict(self):
        """Test creating from dictionary."""
        from emdx.ui.layout import LayoutConfig

        data = {
            "description": "Test layout",
            "theme": "dark",
            "root": {
                "type": "split",
                "direction": "horizontal",
                "children": [
                    {"type": "list", "id": "doc-list"},
                    {"type": "preview", "id": "doc-preview"},
                ],
            },
        }
        config = LayoutConfig.from_dict("test-layout", data)

        assert config.name == "test-layout"
        assert config.description == "Test layout"
        assert config.theme == "dark"

    def test_to_dict_roundtrip(self):
        """Test serialization roundtrip."""
        from emdx.ui.layout import LayoutConfig, SplitSpec, PanelSpec, SizeSpec

        original = LayoutConfig(
            name="test-layout",
            root=SplitSpec(
                direction="horizontal",
                children=[
                    PanelSpec("list", "doc-list", size=SizeSpec.percent(40)),
                    PanelSpec("preview", "doc-preview", size=SizeSpec.percent(60)),
                ],
            ),
            theme="dark",
            description="Test layout",
        )

        data = original.to_dict()
        restored = LayoutConfig.from_dict(data["name"], data)

        assert restored.name == original.name
        assert restored.theme == original.theme
        assert restored.description == original.description


class TestPanelRegistry:
    """Tests for the panel registry."""

    def test_register_panel(self):
        """Test registering a panel type."""
        from emdx.ui.layout import PanelRegistry

        registry = PanelRegistry()
        registry.register("test-panel", Static, description="Test panel")

        assert registry.has("test-panel")
        assert "test-panel" in registry.list_types()

    def test_create_panel(self):
        """Test creating a panel instance."""
        from emdx.ui.layout import PanelRegistry

        registry = PanelRegistry()
        registry.register("static", Static)

        widget = registry.create("static", "my-static", {})
        assert widget.id == "my-static"
        assert isinstance(widget, Static)

    def test_unknown_panel_raises(self):
        """Test that creating unknown panel raises."""
        from emdx.ui.layout import PanelRegistry

        registry = PanelRegistry()

        with pytest.raises(ValueError, match="Unknown panel type"):
            registry.create("nonexistent", "test-id", {})

    def test_decorator_registration(self):
        """Test decorator-based registration."""
        from emdx.ui.layout import PanelRegistry
        from textual.widget import Widget

        registry = PanelRegistry()

        @registry.decorator("custom-panel", description="Custom panel")
        class CustomPanel(Widget):
            pass

        assert registry.has("custom-panel")
        reg = registry.get("custom-panel")
        assert reg.description == "Custom panel"

    def test_validate_config(self):
        """Test configuration validation."""
        from emdx.ui.layout import PanelRegistry

        registry = PanelRegistry()
        registry.register(
            "validated-panel",
            Static,
            required_config=["required_field"],
            config_schema={
                "required_field": {"type": "string", "required": True},
                "number_field": {"type": "number", "min": 0, "max": 100},
            },
        )

        # Missing required field
        errors = registry.validate_config("validated-panel", {})
        assert len(errors) > 0
        assert any("required_field" in e for e in errors)

        # Valid config
        errors = registry.validate_config(
            "validated-panel", {"required_field": "value"}
        )
        assert len(errors) == 0


class TestLayoutManager:
    """Tests for the LayoutManager."""

    def test_load_builtin_layout(self):
        """Test loading a built-in layout."""
        from emdx.ui.layout import LayoutManager, register_builtin_panels

        # Register panels first
        register_builtin_panels()

        manager = LayoutManager()

        # This should find the builtin document-browser.yaml
        try:
            config = manager.load_layout("document-browser")
            assert config.name == "document-browser"
        except FileNotFoundError:
            # Layout file might not be installed in test environment
            pytest.skip("Built-in layout not found")

    def test_validate_layout(self):
        """Test layout validation."""
        from emdx.ui.layout import (
            LayoutManager,
            LayoutConfig,
            SplitSpec,
            PanelSpec,
            register_builtin_panels,
        )

        register_builtin_panels()
        manager = LayoutManager()

        # Valid layout
        config = LayoutConfig(
            name="valid-layout",
            root=SplitSpec(
                direction="horizontal",
                children=[
                    PanelSpec("table", "doc-table"),
                    PanelSpec("richlog", "doc-preview"),
                ],
            ),
        )
        errors = manager.validate_layout(config)
        assert len(errors) == 0

        # Layout with duplicate IDs
        config_dup = LayoutConfig(
            name="dup-layout",
            root=SplitSpec(
                direction="horizontal",
                children=[
                    PanelSpec("table", "same-id"),
                    PanelSpec("richlog", "same-id"),
                ],
            ),
        )
        errors = manager.validate_layout(config_dup)
        assert any("Duplicate" in e for e in errors)

    def test_list_layouts(self):
        """Test listing available layouts."""
        from emdx.ui.layout import LayoutManager

        manager = LayoutManager()
        layouts = manager.list_layouts()

        # Should find at least the builtin layouts
        # (This might be empty if builtins aren't installed)
        assert isinstance(layouts, list)
        for name, location in layouts:
            assert location in ("user", "builtin")


class TestCreateLayout:
    """Tests for programmatic layout creation."""

    def test_create_simple_layout(self):
        """Test creating a simple layout."""
        from emdx.ui.layout import create_layout, PanelSpec

        layout = create_layout(
            "simple",
            PanelSpec("table", "my-table"),
        )
        assert layout.name == "simple"
        assert isinstance(layout.root, PanelSpec)

    def test_create_split_layout(self):
        """Test creating a split layout."""
        from emdx.ui.layout import create_layout, SplitSpec, PanelSpec, SizeSpec

        layout = create_layout(
            "split-layout",
            SplitSpec(
                direction="horizontal",
                children=[
                    PanelSpec("table", "left-panel"),
                    PanelSpec("richlog", "right-panel"),
                ],
                sizes=[SizeSpec.percent(40), SizeSpec.percent(60)],
            ),
            theme="dark",
            description="A test split layout",
        )

        assert layout.name == "split-layout"
        assert layout.theme == "dark"
        assert isinstance(layout.root, SplitSpec)
        assert layout.root.direction == "horizontal"


class TestComposableBrowser:
    """Tests for the ComposableBrowser base class."""

    def test_get_default_layout(self):
        """Test that subclasses can define default layouts."""
        from emdx.ui.layout import (
            ComposableBrowser,
            PanelSpec,
            create_layout,
        )

        class TestBrowser(ComposableBrowser):
            def get_default_layout(self):
                return create_layout(
                    "test-browser",
                    PanelSpec("static", "main-panel"),
                )

        browser = TestBrowser()
        config = browser._get_layout_config()
        assert config is not None
        assert config.name == "test-browser"

    def test_layout_name_attribute(self):
        """Test LAYOUT_NAME class attribute."""
        from emdx.ui.layout import ComposableBrowser

        class TestBrowser(ComposableBrowser):
            LAYOUT_NAME = "test-layout"

        browser = TestBrowser()
        assert browser.get_layout_name() == "test-layout"

    def test_create_simple_split_layout(self):
        """Test the convenience method for creating simple splits."""
        from emdx.ui.layout import ComposableBrowser

        browser = ComposableBrowser()
        layout = browser.create_simple_split_layout(
            "test",
            [
                {"type": "table", "id": "left"},
                {"type": "richlog", "id": "right"},
            ],
            direction="horizontal",
            sizes=["40%", "60%"],
        )

        assert layout.name == "test"
        from emdx.ui.layout import SplitSpec

        assert isinstance(layout.root, SplitSpec)
        assert layout.root.direction == "horizontal"

    def test_create_nested_split_layout(self):
        """Test the convenience method for nested splits."""
        from emdx.ui.layout import ComposableBrowser, SplitSpec

        browser = ComposableBrowser()
        layout = browser.create_nested_split_layout(
            "nested",
            {
                "direction": "horizontal",
                "sizes": ["40%", "60%"],
                "children": [
                    {
                        "direction": "vertical",
                        "sizes": ["66%", "34%"],
                        "children": [
                            {"type": "table", "id": "list"},
                            {"type": "richlog", "id": "details"},
                        ],
                    },
                    {"type": "richlog", "id": "preview"},
                ],
            },
        )

        assert layout.name == "nested"
        assert isinstance(layout.root, SplitSpec)
        assert isinstance(layout.root.children[0], SplitSpec)
