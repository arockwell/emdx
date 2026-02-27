"""Mixin for applying configurable panel sizes from ui_config.

Each view that uses this mixin must define:
- _layout_list_panel_id: CSS id of the top/list panel (e.g. "#activity-panel")
- _layout_detail_panel_id: CSS id of the bottom/detail panel (e.g. "#preview-panel")
- _layout_list_section_id: CSS id of the list section inside list panel (optional)
- _layout_sidebar_section_id: CSS id of the sidebar section (optional)
"""

from __future__ import annotations

import logging

from emdx.config.ui_config import LayoutConfig, get_layout, set_layout

logger = logging.getLogger(__name__)

# Hard limits so the UI stays usable
MIN_LIST_HEIGHT_PCT = 15
MAX_LIST_HEIGHT_PCT = 85
ADJUST_STEP = 5


class LayoutMixin:
    """Mixin that reads layout config and applies panel sizes."""

    _layout_list_panel_id: str = ""
    _layout_detail_panel_id: str = ""
    _layout_list_section_id: str = ""
    _layout_sidebar_section_id: str = ""

    _layout: LayoutConfig | None = None

    def _apply_layout(self) -> None:
        """Read layout config and set panel styles."""
        from textual.widget import Widget

        assert isinstance(self, Widget)
        layout = get_layout()
        self._layout = layout

        list_h = layout["list_height_pct"]
        detail_h = 100 - list_h

        try:
            list_panel = self.query_one(self._layout_list_panel_id)
            list_panel.styles.height = f"{list_h}%"
        except Exception:
            pass

        try:
            detail_panel = self.query_one(self._layout_detail_panel_id)
            detail_panel.styles.height = f"{detail_h}%"
        except Exception:
            pass

        # Sidebar widths (if this view has a sidebar)
        if self._layout_list_section_id and self._layout_sidebar_section_id:
            sidebar_w = layout["sidebar_width_pct"]
            list_w = 100 - sidebar_w
            try:
                list_section = self.query_one(self._layout_list_section_id)
                list_section.styles.width = f"{list_w}%"
            except Exception:
                pass
            try:
                sidebar_section = self.query_one(self._layout_sidebar_section_id)
                sidebar_section.styles.width = f"{sidebar_w}%"
            except Exception:
                pass

    def _adjust_list_height(self, delta: int) -> None:
        """Change the list panel height by delta percent and persist."""
        layout = get_layout()
        new_pct = max(
            MIN_LIST_HEIGHT_PCT,
            min(MAX_LIST_HEIGHT_PCT, layout["list_height_pct"] + delta),
        )
        if new_pct == layout["list_height_pct"]:
            return
        layout["list_height_pct"] = new_pct
        set_layout(layout)
        self._layout = layout
        self._apply_layout()

    def action_grow_list(self) -> None:
        """Increase the list panel height."""
        self._adjust_list_height(ADJUST_STEP)

    def action_shrink_list(self) -> None:
        """Decrease the list panel height."""
        self._adjust_list_height(-ADJUST_STEP)
