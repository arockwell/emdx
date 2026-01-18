"""
UI Context definitions for the keybinding system.

Contexts represent the different "modes" or "states" where keybindings apply.
They form a hierarchy where child contexts inherit from parent contexts.
"""

from enum import Enum
from typing import List


class Context(Enum):
    """
    Define all UI contexts where keybindings apply.

    Hierarchy:
        GLOBAL
        ├── ACTIVITY_*
        ├── DOCUMENT_*
        │   └── VIM_* (when editing)
        ├── AGENT_*
        ├── FILE_*
        ├── TASK_*
        ├── WORKFLOW_*
        ├── LOG_*
        ├── CONTROL_*
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

    # File browser contexts
    FILE_NORMAL = "file:normal"
    FILE_EDIT = "file:edit"

    # Task browser contexts
    TASK_NORMAL = "task:normal"
    TASK_FILTER = "task:filter"

    # Workflow browser contexts
    WORKFLOW_NORMAL = "workflow:normal"

    # Log browser contexts
    LOG_NORMAL = "log:normal"
    LOG_SEARCH = "log:search"

    # Control center (Pulse) contexts
    CONTROL_NORMAL = "control:normal"
    CONTROL_ZOOM0 = "control:zoom0"
    CONTROL_ZOOM1 = "control:zoom1"
    CONTROL_ZOOM2 = "control:zoom2"

    # Git browser contexts
    GIT_NORMAL = "git:normal"
    GIT_DIFF = "git:diff"

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
    MODAL_FILE = "modal:file"
    MODAL_FILE_SAVE = "modal:file_save"
    MODAL_FILE_EXECUTE = "modal:file_execute"
    MODAL_WORKTREE = "modal:worktree"
    MODAL_WORKTREE_PICK = "modal:worktree_pick"
    MODAL_STAGE = "modal:stage"
    MODAL_STAGE_DOC = "modal:stage_doc"
    MODAL_STAGE_AGENT = "modal:stage_agent"
    MODAL_STAGE_PROJECT = "modal:stage_project"
    MODAL_STAGE_CONFIG = "modal:stage_config"
    MODAL_COMMIT = "modal:commit"
    MODAL_FULLSCREEN = "modal:fullscreen"
    MODAL_EXECUTION = "modal:execution"

    # Nested view contexts (widgets within browsers)
    LOG_VIEW = "log:view"
    FILE_LIST = "file:list"
    PULSE_VIEW = "control:pulse"

    # Input contexts (when typing in an input field)
    INPUT_TITLE = "input:title"
    INPUT_AGENT_NAME = "input:agent_name"
    INPUT_AGENT_DISPLAY = "input:agent_display"
    INPUT_AGENT_DESC = "input:agent_desc"
    INPUT_FILE = "input:file"

    # Widget-specific contexts for agent modals
    AGENT_LIST_WIDGET = "widget:agent_list"

    @classmethod
    def get_parent_contexts(cls, context: "Context") -> List["Context"]:
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
            # File contexts
            cls.FILE_NORMAL: [cls.GLOBAL],
            cls.FILE_EDIT: [cls.FILE_NORMAL, cls.GLOBAL],
            # Task contexts
            cls.TASK_NORMAL: [cls.GLOBAL],
            cls.TASK_FILTER: [cls.TASK_NORMAL, cls.GLOBAL],
            # Workflow contexts
            cls.WORKFLOW_NORMAL: [cls.GLOBAL],
            # Log contexts
            cls.LOG_NORMAL: [cls.GLOBAL],
            cls.LOG_SEARCH: [cls.LOG_NORMAL, cls.GLOBAL],
            # Control contexts
            cls.CONTROL_NORMAL: [cls.GLOBAL],
            cls.CONTROL_ZOOM0: [cls.CONTROL_NORMAL, cls.GLOBAL],
            cls.CONTROL_ZOOM1: [cls.CONTROL_NORMAL, cls.GLOBAL],
            cls.CONTROL_ZOOM2: [cls.CONTROL_NORMAL, cls.GLOBAL],
            # Git contexts
            cls.GIT_NORMAL: [cls.GLOBAL],
            cls.GIT_DIFF: [cls.GIT_NORMAL, cls.GLOBAL],
            # Vim contexts (nested in edit)
            cls.VIM_NORMAL: [cls.DOCUMENT_EDIT, cls.GLOBAL],
            cls.VIM_INSERT: [cls.VIM_NORMAL, cls.DOCUMENT_EDIT, cls.GLOBAL],
            cls.VIM_VISUAL: [cls.VIM_NORMAL, cls.DOCUMENT_EDIT, cls.GLOBAL],
            cls.VIM_VLINE: [cls.VIM_NORMAL, cls.DOCUMENT_EDIT, cls.GLOBAL],
            cls.VIM_COMMAND: [cls.VIM_NORMAL, cls.DOCUMENT_EDIT, cls.GLOBAL],
            # Nested view contexts
            cls.LOG_VIEW: [cls.LOG_NORMAL, cls.GLOBAL],
            cls.FILE_LIST: [cls.FILE_NORMAL, cls.GLOBAL],
            cls.PULSE_VIEW: [cls.CONTROL_NORMAL, cls.GLOBAL],
            # Modals don't inherit - they override everything
            cls.MODAL_THEME: [],
            cls.MODAL_CONFIRM: [],
            cls.MODAL_DELETE: [],
            cls.MODAL_AGENT: [],
            cls.MODAL_FILE: [],
            cls.MODAL_WORKTREE: [],
            cls.MODAL_WORKTREE_PICK: [],
            cls.MODAL_STAGE: [],
            cls.MODAL_FULLSCREEN: [],
            cls.MODAL_EXECUTION: [],
            # Input contexts - don't inherit from each other (only one active at a time)
            cls.INPUT_TITLE: [],
            cls.INPUT_AGENT_NAME: [],
            cls.INPUT_AGENT_DISPLAY: [],
            cls.INPUT_AGENT_DESC: [],
            cls.INPUT_FILE: [],
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
            "ActivityBrowser": cls.ACTIVITY_NORMAL,
            # Document browser and related
            "DocumentBrowser": cls.DOCUMENT_NORMAL,
            "FullScreenView": cls.MODAL_FULLSCREEN,
            # Agent browser
            "AgentBrowser": cls.AGENT_NORMAL,
            "AgentHistoryModal": cls.MODAL_AGENT,
            # File browser
            "FileBrowserView": cls.FILE_NORMAL,
            "FileView": cls.FILE_NORMAL,
            "FileList": cls.FILE_LIST,
            # Task browser
            "TaskBrowser": cls.TASK_NORMAL,
            # Workflow browser
            "WorkflowBrowser": cls.WORKFLOW_NORMAL,
            # Log browser
            "LogBrowser": cls.LOG_NORMAL,
            "LogView": cls.LOG_VIEW,
            # Control center / Pulse
            "ControlCenter": cls.CONTROL_NORMAL,
            "ControlCenterBrowser": cls.CONTROL_NORMAL,
            "PulseBrowser": cls.CONTROL_NORMAL,
            "PulseView": cls.PULSE_VIEW,
            # Git browser
            "GitBrowser": cls.GIT_NORMAL,
            # Vim editor
            "VimEditTextArea": cls.VIM_NORMAL,
            "SelectionTextArea": cls.DOCUMENT_SELECTION,
            # Theme selector
            "ThemeSelectorScreen": cls.MODAL_THEME,
            # Delete confirmation
            "DeleteConfirmScreen": cls.MODAL_DELETE,
            # Stage selection screens - each stage gets its own context
            "DocumentSelectionStage": cls.MODAL_STAGE_DOC,
            "AgentSelectionStage": cls.MODAL_STAGE_AGENT,
            "ProjectSelectionStage": cls.MODAL_STAGE_PROJECT,
            "WorktreeSelectionStage": cls.MODAL_WORKTREE,
            "ConfigStage": cls.MODAL_STAGE_CONFIG,
            "ConfigSelectionStage": cls.MODAL_STAGE_CONFIG,
            # Workflow execution
            "WorkflowExecutionOverlay": cls.MODAL_EXECUTION,
            "AgentExecutionOverlay": cls.MODAL_EXECUTION,
            # Agent modals
            "CreateAgentModal": cls.MODAL_AGENT_CREATE,
            "EditAgentModal": cls.MODAL_AGENT_EDIT,
            "RunAgentModal": cls.MODAL_AGENT_RUN,
            "DeleteAgentModal": cls.MODAL_DELETE,
            "AgentSelectionModal": cls.MODAL_AGENT_SELECT,
            "AgentHistoryModal": cls.MODAL_AGENT,
            "AgentListWidget": cls.AGENT_LIST_WIDGET,
            # Agent inputs - each gets its own context to avoid false conflicts
            "AgentNameInput": cls.INPUT_AGENT_NAME,
            "AgentDisplayNameInput": cls.INPUT_AGENT_DISPLAY,
            "AgentDescriptionArea": cls.INPUT_AGENT_DESC,
            # File modals
            "SaveFileModal": cls.MODAL_FILE_SAVE,
            "ExecuteFileModal": cls.MODAL_FILE_EXECUTE,
            "FileList": cls.FILE_NORMAL,
            "FilePreview": cls.FILE_NORMAL,
            "FileEditTextArea": cls.FILE_EDIT,
            "FileSelectionTextArea": cls.FILE_EDIT,
            # Title input
            "TitleInput": cls.INPUT_TITLE,
            # Worktree picker
            "WorktreePickerScreen": cls.MODAL_WORKTREE_PICK,
            # Commit message
            "CommitMessageScreen": cls.MODAL_COMMIT,
            # Delete confirmation
            "DeleteConfirmationDialog": cls.MODAL_DELETE,
            # Activity browser
            "ActivityBrowser": cls.ACTIVITY_NORMAL,
            # Category select
            "CategorySelect": cls.MODAL_STAGE,
        }
        return mapping.get(widget_class_name, cls.GLOBAL)
