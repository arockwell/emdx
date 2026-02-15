"""ActivityTree — Tree[ActivityItem] widget for the activity view.

Replaces DataTable with Textual's native Tree widget to eliminate
scroll jumping on periodic refresh. TreeNode objects persist across
refreshes; we update .data and .label via set_label() which only
repaints the label line, never touching scroll or cursor position.

Each row is rendered as a table-like line with aligned columns.
render_label() produces a fixed-width Text that, combined with the
Tree's guide prefix, always fills the widget width:

  Left edge                                          Right edge
  |[guides][expand][icon] title..............  [time] [  id]|

Title fills available space. Time and id are right-justified and
aligned across all rows regardless of depth.
"""

import logging

from rich.style import Style
from rich.text import Text
from textual.widgets import Tree
from textual.widgets._tree import TreeNode

from .activity_items import ActivityItem

logger = logging.getLogger(__name__)

# Type alias for the key that uniquely identifies an item
ItemKey = tuple[str, int]  # (item_type, item_id)

# guide_depth=2 is the minimum Textual allows.
# With show_root=False, a node at depth d gets (d+1)*2 chars of guide prefix.
GUIDE_DEPTH = 2

# Right-side column widths
TIME_WIDTH = 3   # "2m", "1h", "3d" — compact
ID_WIDTH = 6     # " #5921" / "   #42" right-aligned

def _item_key(item: ActivityItem) -> ItemKey:
    """Return a unique key for an ActivityItem."""
    return (item.item_type, item.item_id)

def _node_depth(node: TreeNode) -> int:
    """Compute depth of a node (0 = direct child of root)."""
    depth = 0
    n = node._parent
    while n is not None and n._parent is not None:
        depth += 1
        n = n._parent
    return depth

class ActivityTree(Tree[ActivityItem]):
    """Tree widget for the activity stream.

    Each TreeNode.data holds an ActivityItem instance.
    The tree handles expand/collapse, cursor tracking, and scroll
    preservation natively — no manual ViewState needed.

    Rows are rendered with aligned columns via render_label().
    """

    show_root = False
    show_guides = False
    guide_depth = GUIDE_DEPTH
    auto_expand = False

    # Suppress Tree's default expand icons — we render our own in render_label()
    ICON_NODE = ""
    ICON_NODE_EXPANDED = ""

    BINDINGS = []  # Parent ActivityView owns all bindings

    def get_label_width(self, node: TreeNode[ActivityItem]) -> int:
        """Return label width so virtual_size equals the viewport.

        We need virtual_size.width == size.width so the Tree never
        adds right-padding that would push our right-justified columns
        away from the edge.
        """
        depth = _node_depth(node)
        guides_width = (depth + 1) * GUIDE_DEPTH
        return max(0, self.size.width - guides_width)

    def _get_icon(self, item: ActivityItem) -> str:
        """Get the display icon for an item."""
        if item.status in ("running", "failed", "pending", "queued"):
            return item.status_icon
        else:
            return item.type_icon

    def _get_suffix(self, item: ActivityItem) -> str:
        """Get the badge or progress bar suffix for an item's title."""
        doc_count = getattr(item, "doc_count", 0)

        if not item.expanded:
            if doc_count > 0 and item.item_type == "group":
                return f" [{doc_count}]"
        return ""

    def _get_id_str(self, item: ActivityItem) -> str:
        """Get the ID string for an item."""
        if item.item_type == "group":
            return f"#{item.item_id}" if item.item_id else ""
        elif item.item_type in ("document", "cascade"):
            return f"#{item.doc_id}" if getattr(item, "doc_id", None) else ""
        else:
            return f"#{item.item_id}" if item.item_id else ""

    def _make_label(self, item: ActivityItem) -> str:
        """Build a compact change-detection string for set_label().

        The visual rendering is handled by render_label(). This string
        is only used to detect changes (so set_label triggers repaints).
        """
        from .activity_view import format_time_ago

        icon = self._get_icon(item)
        time_str = format_time_ago(item.timestamp)
        suffix = self._get_suffix(item)
        id_str = self._get_id_str(item)
        return f"{icon}|{time_str}|{item.title}{suffix}|{id_str}"

    def render_label(
        self, node: TreeNode[ActivityItem], base_style: Style, style: Style
    ) -> Text:
        """Render a fixed-width table row with aligned columns.

        Layout: [expand][icon] title...  [time] [  id]

        The Tree prepends (depth+1)*GUIDE_DEPTH chars of guides. We return
        a Text exactly (widget_width - guides_width) chars wide, so that
        guides + label = widget_width on every row. Time and id are
        right-justified and stay flush against the right edge at every depth.
        """
        from .activity_view import format_time_ago

        item = node.data
        if item is None:
            return Text("")

        depth = _node_depth(node)
        guides_width = (depth + 1) * GUIDE_DEPTH
        widget_width = self.size.width
        label_width = max(0, widget_width - guides_width)

        # Expand indicator
        if node._allow_expand:
            expand = "▼ " if node.is_expanded else "▶ "
        else:
            expand = "  "

        icon = self._get_icon(item)
        time_str = format_time_ago(item.timestamp)
        suffix = self._get_suffix(item)
        # Collapse newlines — titles with \n break single-line row rendering
        # because Rich counts \n as 0 cells but the text after \n is invisible
        clean_title = item.title.replace("\n", " ").replace("  ", " ").strip()
        full_title = f"{clean_title}{suffix}"
        id_str = self._get_id_str(item)

        # Styles — layer decorations on top of `style` so cursor background shows through
        title_style = style + Style(bold=True) if item.status == "running" else style
        icon_style = style + Style(color="red") if item.status == "failed" else style
        dim_style = style + Style(dim=True)

        # Build left portion: expand + "icon "
        left = Text()
        left.append(expand, style=style)
        left.append(f"{icon} ", style=icon_style)
        left_cells = left.cell_len

        # Build right portion: " time  #id" (always present for alignment)
        right = Text()
        right.append(f" {time_str:>{TIME_WIDTH}}", style=dim_style)
        if id_str:
            right.append(f" {id_str:>{ID_WIDTH}}", style=dim_style)
        right_cells = right.cell_len

        # Title fills the remaining space exactly
        title_avail = max(0, label_width - left_cells - right_cells)

        # Truncate title to fit (accounting for cell width, not char count)
        title_text = Text(full_title)
        if title_text.cell_len > title_avail:
            truncated = full_title
            while Text(truncated + "…").cell_len > title_avail and truncated:
                truncated = truncated[:-1]
            title_display = truncated + "…" if truncated else ""
        else:
            title_display = full_title

        # Pad title to exact cell width (pushes right columns flush-right)
        title_cell_len = Text(title_display).cell_len
        pad_needed = max(0, title_avail - title_cell_len)

        # Assemble the row
        text = Text()
        text.append_text(left)
        text.append(title_display, style=title_style)
        if pad_needed > 0:
            text.append(" " * pad_needed, style=style)
        text.append_text(right)

        return text

    def _add_children(
        self, parent: TreeNode[ActivityItem], children: list[ActivityItem]
    ) -> None:
        """Add child items to a parent node."""
        for child in children:
            if child.can_expand():
                parent.add(self._make_label(child), data=child)
            else:
                parent.add_leaf(self._make_label(child), data=child)

    def populate_from_items(self, items: list[ActivityItem]) -> None:
        """Initial full load: clear tree and add all top-level items."""
        self.clear()
        for item in items:
            if item.can_expand():
                node = self.root.add(self._make_label(item), data=item)
                node.allow_expand = True
            else:
                node = self.root.add_leaf(self._make_label(item), data=item)

    def refresh_from_items(self, items: list[ActivityItem]) -> None:
        """Diff-based periodic refresh.

        Updates existing nodes in-place via set_label() (no scroll disruption).
        Adds new nodes and removes stale ones.
        Recursively refreshes children of expanded nodes.
        """
        self._refresh_children(self.root, items)

    def _refresh_children(
        self, parent: TreeNode[ActivityItem], fresh_items: list[ActivityItem]
    ) -> None:
        """Diff and update children of a parent node.

        Updates labels in-place when possible, adds/removes as needed,
        and does a full repopulate when the order changes (e.g., new item
        at the top).
        """
        # Build map of existing children by item key
        existing: dict[ItemKey, TreeNode[ActivityItem]] = {}
        for child in parent.children:
            if child.data is not None:
                existing[_item_key(child.data)] = child

        fresh_keys = {_item_key(item) for item in fresh_items}
        existing_keys = [
            _item_key(child.data)
            for child in parent.children
            if child.data is not None
        ]

        # Compute the expected order of keys that already exist
        fresh_existing_order = [
            _item_key(item) for item in fresh_items if _item_key(item) in existing
        ]

        # Check if any new items or removals or order changes
        has_new = any(k not in existing for k in fresh_keys)
        has_removed = any(k not in fresh_keys for k in existing_keys)
        # Order changed among the surviving items?
        surviving_current = [k for k in existing_keys if k in fresh_keys]
        order_changed = surviving_current != fresh_existing_order

        if has_new or has_removed or order_changed:
            # Structural change — save expanded/cursor state, repopulate
            expanded_keys: set[ItemKey] = set()
            expanded_children: dict[ItemKey, list[ActivityItem]] = {}
            for child in parent.children:
                if child.data is not None and child.is_expanded:
                    key = _item_key(child.data)
                    expanded_keys.add(key)
                    if child.data.children:
                        expanded_children[key] = child.data.children

            # Remove all children and re-add in correct order
            for child in list(parent.children):
                child.remove()

            for item in fresh_items:
                key = _item_key(item)
                if item.can_expand():
                    node = parent.add(self._make_label(item), data=item)
                    node.allow_expand = True
                    if key in expanded_keys:
                        node.expand()
                        if key in expanded_children:
                            self._refresh_children(node, item.children or [])
                else:
                    parent.add_leaf(self._make_label(item), data=item)
        else:
            # No structural changes — update labels in-place (no scroll disruption)
            for child in parent.children:
                if child.data is not None:
                    key = _item_key(child.data)
                    # Find matching fresh item
                    for item in fresh_items:
                        if _item_key(item) == key:
                            child.data = item
                            child.set_label(self._make_label(item))
                            child.allow_expand = item.can_expand()
                            if child.is_expanded and item.children:
                                self._refresh_children(child, item.children)
                            break

    def find_node_by_item_key(
        self, item_type: str, item_id: int
    ) -> TreeNode[ActivityItem] | None:
        """Walk the tree to find a node matching (item_type, item_id)."""
        target_key = (item_type, item_id)

        def _search(node: TreeNode[ActivityItem]) -> TreeNode[ActivityItem] | None:
            if node.data is not None and _item_key(node.data) == target_key:
                return node
            for child in node.children:
                result = _search(child)
                if result is not None:
                    return result
            return None

        return _search(self.root)

    def find_node_by_doc_id(
        self, doc_id: int
    ) -> TreeNode[ActivityItem] | None:
        """Walk the tree to find a node with a matching doc_id."""

        def _search(node: TreeNode[ActivityItem]) -> TreeNode[ActivityItem] | None:
            if node.data is not None:
                if getattr(node.data, "doc_id", None) == doc_id:
                    return node
            for child in node.children:
                result = _search(child)
                if result is not None:
                    return result
            return None

        return _search(self.root)
