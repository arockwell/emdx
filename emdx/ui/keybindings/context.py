"""
UI Context definitions for the keybinding system.

Contexts represent the different "modes" or "states" where keybindings apply.
They form a hierarchy where child contexts inherit from parent contexts.
"""

from enum import Enum


class Context(Enum):
    """
    Define all UI contexts where keybindings apply.

    Hierarchy:
        GLOBAL
        ├── ACTIVITY_*
        ├── TASK_*
        ├── DOCUMENT_*
        └── MODAL_* (highest priority, overrides all)
    """

    # Global context - always active at app level
    GLOBAL = "global"

    # Activity browser contexts
    ACTIVITY_NORMAL = "activity:normal"

    # Document browser contexts
    DOCUMENT_NORMAL = "document:normal"

    # Task browser contexts
    TASK_NORMAL = "task:normal"

    # Modal contexts (override all others)
    MODAL_THEME = "modal:theme"
    MODAL_DELETE = "modal:delete"

    @classmethod
    def get_parent_contexts(cls, context: "Context") -> list["Context"]:
        """
        Get parent contexts in inheritance hierarchy.

        Child contexts inherit keybindings from parent contexts.
        More specific contexts override less specific ones.
        """
        hierarchy = {
            # Activity inherits from global
            cls.ACTIVITY_NORMAL: [cls.GLOBAL],
            # Document contexts
            cls.DOCUMENT_NORMAL: [cls.GLOBAL],
            # Task contexts
            cls.TASK_NORMAL: [cls.GLOBAL],
            # Modals don't inherit - they override everything
            cls.MODAL_THEME: [],
            cls.MODAL_DELETE: [],
            # Global has no parent
            cls.GLOBAL: [],
        }
        return hierarchy.get(context, [cls.GLOBAL])

    @classmethod
    def is_modal(cls, context: "Context") -> bool:
        """Check if a context is a modal context."""
        return context.value.startswith("modal:")

    @classmethod
    def contexts_can_overlap(cls, ctx1: "Context", ctx2: "Context") -> bool:
        """
        Check if two contexts can be active at the same time.

        Used for conflict detection - only overlapping contexts can conflict.
        """
        # Modals never overlap with anything except themselves
        if cls.is_modal(ctx1) or cls.is_modal(ctx2):
            return ctx1 == ctx2

        # Check if one is a parent/child of the other
        parents1 = cls.get_parent_contexts(ctx1)
        parents2 = cls.get_parent_contexts(ctx2)

        return ctx1 in parents2 or ctx2 in parents1 or ctx1 == ctx2

    @classmethod
    def from_widget_class(cls, widget_class_name: str) -> "Context":
        """
        Map a widget class name to its primary context.

        Used by the extractor to determine context from BINDINGS.
        """
        mapping = {
            # Main app
            "BrowserContainer": cls.GLOBAL,
            # Activity browser
            "ActivityView": cls.ACTIVITY_NORMAL,
            "ActivityBrowser": cls.ACTIVITY_NORMAL,
            # Theme selector
            "ThemeSelectorScreen": cls.MODAL_THEME,
            # Task browser
            "TaskBrowser": cls.TASK_NORMAL,
            "TaskView": cls.TASK_NORMAL,
        }
        return mapping.get(widget_class_name, cls.GLOBAL)
