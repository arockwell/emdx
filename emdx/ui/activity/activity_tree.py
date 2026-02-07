"""ActivityTree — Tree[ActivityItem] widget for the activity view.

Replaces DataTable with Textual's native Tree widget to eliminate
scroll jumping on periodic refresh. TreeNode objects persist across
refreshes; we update .data and .label via set_label() which only
repaints the label line, never touching scroll or cursor position.
"""

import logging
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from rich.text import Text
from textual.widgets import Tree
from textual.widgets._tree import TreeNode

from .activity_items import ActivityItem

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Type alias for the key that uniquely identifies an item
ItemKey = Tuple[str, int]  # (item_type, item_id)


def _item_key(item: ActivityItem) -> ItemKey:
    """Return a unique key for an ActivityItem."""
    return (item.item_type, item.item_id)


class ActivityTree(Tree[ActivityItem]):
    """Tree widget for the activity stream.

    Each TreeNode.data holds an ActivityItem instance.
    The tree handles expand/collapse, cursor tracking, and scroll
    preservation natively — no manual ViewState needed.
    """

    show_root = False
    show_guides = False
    guide_depth = 2
    auto_expand = False  # We handle expand/collapse explicitly

    BINDINGS = []  # Parent ActivityView owns all bindings

    def _make_label(self, item: ActivityItem) -> str:
        """Build a Rich-markup label string for a tree node.

        Combines icon + time + title + badge/progress + id into a
        single line. The Tree's built-in guide lines handle indentation.
        """
        from .activity_view import format_time_ago

        # Icon: status icon for actionable states, type icon otherwise
        is_recently_completed = (
            item.item_type == "workflow"
            and hasattr(self, "_recently_completed")
            and item.item_id in self._recently_completed
        )
        if is_recently_completed:
            icon = "✨"
        elif item.status in ("running", "failed", "pending", "queued"):
            icon = item.status_icon
        else:
            icon = item.type_icon

        time_str = format_time_ago(item.timestamp)

        # Badge or progress bar
        suffix = ""
        output_count = getattr(item, "output_count", 0)
        doc_count = getattr(item, "doc_count", 0)

        if item.item_type == "workflow" and item.status == "running":
            progress_total = getattr(item, "progress_total", 0)
            progress_completed = getattr(item, "progress_completed", 0)
            if getattr(item, "_is_synthesizing", False):
                suffix = " 🔮 Synthesizing..."
            elif progress_total > 0:
                pct = progress_completed / progress_total
                bar_width = 10
                filled_exact = pct * bar_width
                filled_full = int(filled_exact)
                remainder = filled_exact - filled_full
                partial_chars = " ▏▎▍▌▋▊▉█"
                partial_idx = int(remainder * 8)
                partial = partial_chars[partial_idx] if partial_idx > 0 else ""
                empty = bar_width - filled_full - (1 if partial else 0)
                bar = "█" * filled_full + partial + "░" * empty
                suffix = f" {bar} {progress_completed}/{progress_total}"
        elif not item.expanded:
            if output_count > 0 and item.item_type == "workflow":
                suffix = f" [{output_count}]"
            elif doc_count > 0 and item.item_type == "group":
                suffix = f" [{doc_count}]"

        # ID string
        if item.item_type in ("workflow", "group"):
            id_str = f"#{item.item_id}" if item.item_id else ""
        elif item.item_type in ("document", "exploration", "synthesis", "cascade"):
            id_str = f"#{item.doc_id}" if getattr(item, "doc_id", None) else ""
        elif item.item_type == "individual_run":
            doc_id = getattr(item, "doc_id", None)
            if doc_id:
                id_str = f"#{doc_id}"
            elif item.item_id:
                id_str = f"r{item.item_id}"
            else:
                id_str = ""
        else:
            id_str = f"#{item.item_id}" if item.item_id else ""

        # Combine: icon  time  title+suffix  id
        parts = [icon, time_str, f"{item.title}{suffix}"]
        if id_str:
            parts.append(id_str)
        return "  ".join(parts)

    def populate_from_items(self, items: List[ActivityItem]) -> None:
        """Initial full load: clear tree and add all top-level items."""
        self.clear()
        for item in items:
            if item.can_expand():
                node = self.root.add(self._make_label(item), data=item)
                node.allow_expand = True
            else:
                node = self.root.add_leaf(self._make_label(item), data=item)

    def refresh_from_items(self, items: List[ActivityItem]) -> None:
        """Diff-based periodic refresh.

        Updates existing nodes in-place via set_label() (no scroll disruption).
        Adds new nodes and removes stale ones.
        Recursively refreshes children of expanded nodes.
        """
        self._refresh_children(self.root, items)

    def _refresh_children(
        self, parent: TreeNode[ActivityItem], fresh_items: List[ActivityItem]
    ) -> None:
        """Diff and update children of a parent node."""
        # Build map of existing children by item key
        existing: Dict[ItemKey, TreeNode[ActivityItem]] = {}
        for child in parent.children:
            if child.data is not None:
                existing[_item_key(child.data)] = child

        # Build set of fresh keys for removal detection
        fresh_keys = {_item_key(item) for item in fresh_items}

        # Remove nodes no longer present
        to_remove = [
            node for key, node in existing.items() if key not in fresh_keys
        ]
        for node in to_remove:
            node.remove()

        # Rebuild existing map after removals
        existing = {}
        for child in parent.children:
            if child.data is not None:
                existing[_item_key(child.data)] = child

        # Update existing nodes and add new ones
        for i, item in enumerate(fresh_items):
            key = _item_key(item)

            if key in existing:
                node = existing[key]
                # Update data and label in-place
                node.data = item
                new_label = self._make_label(item)
                node.set_label(new_label)

                # Update expandability
                if item.can_expand():
                    node.allow_expand = True
                else:
                    node.allow_expand = False

                # If this node is expanded, refresh its children too
                if node.is_expanded and node.data and node.data.children:
                    self._refresh_children(node, node.data.children)
            else:
                # New item — add it
                if item.can_expand():
                    parent.add(self._make_label(item), data=item)
                else:
                    parent.add_leaf(self._make_label(item), data=item)

    def find_node_by_item_key(
        self, item_type: str, item_id: int
    ) -> Optional[TreeNode[ActivityItem]]:
        """Walk the tree to find a node matching (item_type, item_id)."""
        target_key = (item_type, item_id)

        def _search(node: TreeNode[ActivityItem]) -> Optional[TreeNode[ActivityItem]]:
            if node.data is not None and _item_key(node.data) == target_key:
                return node
            for child in node.children:
                result = _search(child)
                if result is not None:
                    return result
            return None

        return _search(self.root)

    def find_node_by_doc_id(
        self, doc_id: int, skip_workflows: bool = True
    ) -> Optional[TreeNode[ActivityItem]]:
        """Walk the tree to find a node with a matching doc_id."""

        def _search(node: TreeNode[ActivityItem]) -> Optional[TreeNode[ActivityItem]]:
            if node.data is not None:
                if skip_workflows and node.data.item_type == "workflow":
                    pass  # Skip workflow nodes, look for actual document children
                elif getattr(node.data, "doc_id", None) == doc_id:
                    return node
            for child in node.children:
                result = _search(child)
                if result is not None:
                    return result
            return None

        return _search(self.root)
