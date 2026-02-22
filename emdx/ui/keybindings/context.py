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
        │   └── VIM_* (when editing)
        ├── AGENT_*
        ├── LOG_*
        └── MODAL_* (highest priority, overrides all)
    """

    # Global context - always active at app level
    GLOBAL = "global"

    # Activity browser contexts
    ACTIVITY_NORMAL = "activity:normal"

    # Document browser contexts
    DOCUMENT_NORMAL = "document:normal"
    DOCUMENT_SEARCH = "document:search"
    DOCUMENT_TAG = "document:tag"
    DOCUMENT_EDIT = "document:edit"
    DOCUMENT_SELECTION = "document:selection"

    # Agent browser contexts
    AGENT_NORMAL = "agent:normal"
    AGENT_FORM = "agent:form"

    # Task browser contexts
    TASK_NORMAL = "task:normal"

    # Log browser contexts
    LOG_NORMAL = "log:normal"
    LOG_SEARCH = "log:search"

    # Vim editor contexts (nested within edit contexts)
    VIM_NORMAL = "vim:normal"
    VIM_INSERT = "vim:insert"
    VIM_VISUAL = "vim:visual"
    VIM_VLINE = "vim:vline"
    VIM_COMMAND = "vim:command"

    # Modal contexts (override all others)
    MODAL_THEME = "modal:theme"
    MODAL_CONFIRM = "modal:confirm"
    MODAL_DELETE = "modal:delete"
    MODAL_AGENT = "modal:agent"
    MODAL_AGENT_CREATE = "modal:agent_create"
    MODAL_AGENT_EDIT = "modal:agent_edit"
    MODAL_AGENT_RUN = "modal:agent_run"
    MODAL_AGENT_SELECT = "modal:agent_select"
    MODAL_FULLSCREEN = "modal:fullscreen"

    # Nested view contexts (widgets within browsers)
    LOG_VIEW = "log:view"

    # Input contexts (when typing in an input field)
    INPUT_TITLE = "input:title"
    INPUT_AGENT_NAME = "input:agent_name"
    INPUT_AGENT_DISPLAY = "input:agent_display"
    INPUT_AGENT_DESC = "input:agent_desc"

    # Widget-specific contexts for agent modals
    AGENT_LIST_WIDGET = "widget:agent_list"

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
            cls.DOCUMENT_SEARCH: [cls.DOCUMENT_NORMAL, cls.GLOBAL],
            cls.DOCUMENT_TAG: [cls.DOCUMENT_NORMAL, cls.GLOBAL],
            cls.DOCUMENT_EDIT: [cls.DOCUMENT_NORMAL, cls.GLOBAL],
            cls.DOCUMENT_SELECTION: [cls.DOCUMENT_NORMAL, cls.GLOBAL],
            # Agent contexts
            cls.AGENT_NORMAL: [cls.GLOBAL],
            cls.AGENT_FORM: [cls.AGENT_NORMAL, cls.GLOBAL],
            # Task contexts
            cls.TASK_NORMAL: [cls.GLOBAL],
            # Log contexts
            cls.LOG_NORMAL: [cls.GLOBAL],
            cls.LOG_SEARCH: [cls.LOG_NORMAL, cls.GLOBAL],
            # Vim contexts (nested in edit)
            cls.VIM_NORMAL: [cls.DOCUMENT_EDIT, cls.GLOBAL],
            cls.VIM_INSERT: [cls.VIM_NORMAL, cls.DOCUMENT_EDIT, cls.GLOBAL],
            cls.VIM_VISUAL: [cls.VIM_NORMAL, cls.DOCUMENT_EDIT, cls.GLOBAL],
            cls.VIM_VLINE: [cls.VIM_NORMAL, cls.DOCUMENT_EDIT, cls.GLOBAL],
            cls.VIM_COMMAND: [cls.VIM_NORMAL, cls.DOCUMENT_EDIT, cls.GLOBAL],
            # Nested view contexts
            cls.LOG_VIEW: [cls.LOG_NORMAL, cls.GLOBAL],
            # Modals don't inherit - they override everything
            cls.MODAL_THEME: [],
            cls.MODAL_CONFIRM: [],
            cls.MODAL_DELETE: [],
            cls.MODAL_AGENT: [],
            cls.MODAL_FULLSCREEN: [],
            # Input contexts - don't inherit from each other (only one active at a time)
            cls.INPUT_TITLE: [],
            cls.INPUT_AGENT_NAME: [],
            cls.INPUT_AGENT_DISPLAY: [],
            cls.INPUT_AGENT_DESC: [],
            # Widget contexts - isolated
            cls.AGENT_LIST_WIDGET: [],
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
            # Agent browser
            "AgentBrowser": cls.AGENT_NORMAL,
            "AgentHistoryModal": cls.MODAL_AGENT,
            # Log browser
            "LogBrowser": cls.LOG_NORMAL,
            "LogView": cls.LOG_VIEW,
            # Selection text area
            "SelectionTextArea": cls.DOCUMENT_SELECTION,
            # Theme selector
            "ThemeSelectorScreen": cls.MODAL_THEME,
            # Agent modals
            "CreateAgentModal": cls.MODAL_AGENT_CREATE,
            "EditAgentModal": cls.MODAL_AGENT_EDIT,
            "RunAgentModal": cls.MODAL_AGENT_RUN,
            "DeleteAgentModal": cls.MODAL_DELETE,
            "AgentSelectionModal": cls.MODAL_AGENT_SELECT,
            "AgentListWidget": cls.AGENT_LIST_WIDGET,
            # Agent inputs - each gets its own context to avoid false conflicts
            "AgentNameInput": cls.INPUT_AGENT_NAME,
            "AgentDisplayNameInput": cls.INPUT_AGENT_DISPLAY,
            "AgentDescriptionArea": cls.INPUT_AGENT_DESC,
            # Title input
            "TitleInput": cls.INPUT_TITLE,
            # Delete confirmation
            "DeleteConfirmationDialog": cls.MODAL_DELETE,
            # Activity browser
            "ActivityBrowser": cls.ACTIVITY_NORMAL,
            # Task browser
            "TaskBrowser": cls.TASK_NORMAL,
            "TaskView": cls.TASK_NORMAL,
        }
        return mapping.get(widget_class_name, cls.GLOBAL)
