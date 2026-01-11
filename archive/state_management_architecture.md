# State Management Architecture Design for EMDX Browser System

## Executive Summary

This document presents a comprehensive state management architecture for the EMDX browser system that addresses the challenges of maintaining predictable, debuggable, and performant state across multiple browser types while supporting seamless transitions and reactive UI updates. The design leverages Textual's reactive system while introducing clear patterns for state ownership, persistence, and validation.

## Current State Analysis

### Existing State Management Patterns

1. **Reactive Properties**: The current implementation uses Textual's `reactive()` for UI state:
   ```python
   # From MinimalDocumentBrowser
   mode = reactive("NORMAL")
   search_query = reactive("")
   tag_action = reactive("")
   current_tag_completion = reactive(0)
   selection_mode = reactive(False)
   edit_mode = reactive(False)
   
   # From FileBrowser
   current_path = reactive(Path.cwd())
   selected_index = reactive(0)
   show_hidden = reactive(False)
   selection_mode = reactive(False)
   edit_mode = reactive(False)
   ```

2. **Ad-hoc State Preservation**: State is preserved manually during operations:
   ```python
   # Cursor position preservation during edit mode
   self.edit_mode_cursor_position = table.cursor_coordinate
   # Later restored with:
   table.cursor_coordinate = self.edit_mode_cursor_position
   ```

3. **Browser-Specific State**: Each browser maintains its own state without clear contracts:
   - DocumentBrowser: search_query, mode, editing_doc_id
   - FileBrowser: current_path, show_hidden
   - GitBrowser: current_worktree_path, git_files, current_file_index

### Current Challenges

1. **State Scattered Across Classes**: No central state management
2. **Manual State Preservation**: Error-prone cursor position tracking
3. **No State Validation**: State changes can leave app in invalid states
4. **Limited Persistence**: State lost on app restart
5. **Unclear State Ownership**: Browser vs container state boundaries unclear
6. **No State History**: Cannot undo/redo operations
7. **Reactive Update Issues**: Manual coordination of UI updates

## Proposed State Management Architecture

### Core Principles

1. **Single Source of Truth**: All state flows through central store
2. **Immutable Updates**: State changes create new state objects
3. **Type-Safe Contracts**: Clear interfaces for all state shapes
4. **Reactive Integration**: Seamless with Textual's reactive system
5. **Predictable Updates**: State machines for complex flows
6. **Debug-First Design**: Every state change is loggable and traceable

### State Hierarchy

```python
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Union
from enum import Enum, auto
from pathlib import Path
import datetime

# State Types
class BrowserType(Enum):
    DOCUMENTS = "documents"
    FILE = "file"
    GIT = "git"
    LOG = "log"
    SEARCH = "search"

class ViewMode(Enum):
    NORMAL = "normal"
    SEARCH = "search"
    TAG = "tag"
    EDIT = "edit"
    VIM = "vim"
    SELECTION = "selection"

# Browser-Specific State
@dataclass(frozen=True)
class DocumentBrowserState:
    """Immutable state for document browser."""
    search_query: str = ""
    tag_filter: List[str] = field(default_factory=list)
    selected_doc_id: Optional[int] = None
    cursor_position: int = 0
    scroll_offset: int = 0
    sort_by: str = "modified"
    sort_reverse: bool = True

@dataclass(frozen=True)
class FileBrowserState:
    """Immutable state for file browser."""
    current_path: Path = field(default_factory=Path.cwd)
    show_hidden: bool = False
    selected_index: int = 0
    scroll_offset: int = 0
    path_history: List[Path] = field(default_factory=list)
    bookmarks: List[Path] = field(default_factory=list)

@dataclass(frozen=True)
class GitBrowserState:
    """Immutable state for git browser."""
    worktree_path: Path = field(default_factory=Path.cwd)
    worktree_index: int = 0
    selected_file_index: int = 0
    scroll_offset: int = 0
    show_staged: bool = True
    show_unstaged: bool = True
    show_untracked: bool = True

# Shared Global State
@dataclass(frozen=True)
class UIState:
    """Global UI state shared across browsers."""
    active_browser: BrowserType = BrowserType.DOCUMENTS
    view_mode: ViewMode = ViewMode.NORMAL
    preview_visible: bool = True
    sidebar_width: int = 50
    theme: str = "default"
    vim_mode: Optional[str] = None  # NORMAL, INSERT, VISUAL, etc.
    status_message: str = ""
    notification: Optional[tuple[str, str]] = None  # (message, severity)

@dataclass(frozen=True)
class SessionState:
    """Session-level state that persists across browser switches."""
    browser_history: List[BrowserType] = field(default_factory=list)
    last_search_queries: Dict[BrowserType, str] = field(default_factory=dict)
    clipboard: Optional[str] = None
    undo_stack: List['AppState'] = field(default_factory=list)
    redo_stack: List['AppState'] = field(default_factory=list)

# Root State Container
@dataclass(frozen=True)
class AppState:
    """Root immutable application state."""
    ui: UIState = field(default_factory=UIState)
    session: SessionState = field(default_factory=SessionState)
    documents: DocumentBrowserState = field(default_factory=DocumentBrowserState)
    file: FileBrowserState = field(default_factory=FileBrowserState)
    git: GitBrowserState = field(default_factory=GitBrowserState)
    # Extensible for new browser types
    custom_browsers: Dict[str, Any] = field(default_factory=dict)
```

### State Store Implementation

```python
from typing import Callable, TypeVar, Generic
from textual.reactive import reactive
import logging

T = TypeVar('T')
logger = logging.getLogger(__name__)

class StateStore(Generic[T]):
    """
    Central state store with Redux-like patterns.
    Integrates with Textual's reactive system.
    """
    
    def __init__(self, initial_state: T):
        self._state = reactive(initial_state)
        self._subscribers: List[Callable[[T, T], None]] = []
        self._middleware: List[Callable] = []
        self._state_history: List[T] = [initial_state]
        self._history_index = 0
        self._max_history = 100
        
    @property
    def state(self) -> T:
        """Get current state (read-only)."""
        return self._state
    
    def subscribe(self, callback: Callable[[T, T], None]) -> Callable[[], None]:
        """Subscribe to state changes. Returns unsubscribe function."""
        self._subscribers.append(callback)
        return lambda: self._subscribers.remove(callback)
    
    def dispatch(self, action: 'Action') -> None:
        """Dispatch an action to update state."""
        old_state = self._state
        
        # Apply middleware
        for middleware in self._middleware:
            action = middleware(action, old_state)
            if action is None:
                return  # Middleware cancelled action
        
        # Apply reducer
        new_state = self._reduce(old_state, action)
        
        if new_state != old_state:
            # Update state
            self._state = new_state
            
            # Update history
            self._add_to_history(new_state)
            
            # Log state change
            logger.debug(f"State change: {action.type}")
            logger.debug(f"  Old: {self._state_summary(old_state)}")
            logger.debug(f"  New: {self._state_summary(new_state)}")
            
            # Notify subscribers
            for subscriber in self._subscribers:
                try:
                    subscriber(old_state, new_state)
                except Exception as e:
                    logger.error(f"Subscriber error: {e}")
    
    def _reduce(self, state: T, action: 'Action') -> T:
        """Pure reducer function."""
        # This would be implemented with pattern matching in Python 3.10+
        # For now, using if/elif
        if isinstance(state, AppState):
            return app_reducer(state, action)
        return state
    
    def _add_to_history(self, state: T) -> None:
        """Add state to history for undo/redo."""
        # Truncate any redo history
        self._state_history = self._state_history[:self._history_index + 1]
        
        # Add new state
        self._state_history.append(state)
        self._history_index += 1
        
        # Limit history size
        if len(self._state_history) > self._max_history:
            self._state_history.pop(0)
            self._history_index -= 1
    
    def undo(self) -> bool:
        """Undo to previous state."""
        if self._history_index > 0:
            self._history_index -= 1
            self._state = self._state_history[self._history_index]
            return True
        return False
    
    def redo(self) -> bool:
        """Redo to next state."""
        if self._history_index < len(self._state_history) - 1:
            self._history_index += 1
            self._state = self._state_history[self._history_index]
            return True
        return False
    
    def _state_summary(self, state: T) -> str:
        """Create concise state summary for logging."""
        if isinstance(state, AppState):
            return f"Browser: {state.ui.active_browser.value}, Mode: {state.ui.view_mode.value}"
        return str(state)
```

### Action System

```python
from dataclasses import dataclass
from typing import Union, Any

@dataclass(frozen=True)
class Action:
    """Base action class."""
    type: str
    timestamp: datetime.datetime = field(default_factory=datetime.datetime.now)

# UI Actions
@dataclass(frozen=True)
class SwitchBrowser(Action):
    type: str = "SWITCH_BROWSER"
    browser: BrowserType = BrowserType.DOCUMENTS
    preserve_state: bool = True

@dataclass(frozen=True)
class ChangeViewMode(Action):
    type: str = "CHANGE_VIEW_MODE"
    mode: ViewMode = ViewMode.NORMAL

@dataclass(frozen=True)
class UpdateStatus(Action):
    type: str = "UPDATE_STATUS"
    message: str = ""

# Document Browser Actions
@dataclass(frozen=True)
class SearchDocuments(Action):
    type: str = "SEARCH_DOCUMENTS"
    query: str = ""

@dataclass(frozen=True)
class SelectDocument(Action):
    type: str = "SELECT_DOCUMENT"
    doc_id: int
    cursor_position: int

@dataclass(frozen=True)
class UpdateDocumentCursor(Action):
    type: str = "UPDATE_DOCUMENT_CURSOR"
    position: int
    scroll_offset: int = 0

# File Browser Actions
@dataclass(frozen=True)
class NavigateToPath(Action):
    type: str = "NAVIGATE_TO_PATH"
    path: Path
    add_to_history: bool = True

@dataclass(frozen=True)
class ToggleHiddenFiles(Action):
    type: str = "TOGGLE_HIDDEN_FILES"

# Git Browser Actions
@dataclass(frozen=True)
class SwitchWorktree(Action):
    type: str = "SWITCH_WORKTREE"
    worktree_path: Path
    worktree_index: int

@dataclass(frozen=True)
class SelectGitFile(Action):
    type: str = "SELECT_GIT_FILE"
    file_index: int

# Composite Actions
@dataclass(frozen=True)
class RestoreBrowserState(Action):
    type: str = "RESTORE_BROWSER_STATE"
    browser: BrowserType
    state: Union[DocumentBrowserState, FileBrowserState, GitBrowserState]
```

### Reducer Implementation

```python
def app_reducer(state: AppState, action: Action) -> AppState:
    """Root reducer for application state."""
    
    # UI reducers
    if isinstance(action, SwitchBrowser):
        new_history = state.session.browser_history + [action.browser]
        return dataclasses.replace(
            state,
            ui=dataclasses.replace(state.ui, active_browser=action.browser),
            session=dataclasses.replace(
                state.session,
                browser_history=new_history[-10:]  # Keep last 10
            )
        )
    
    elif isinstance(action, ChangeViewMode):
        return dataclasses.replace(
            state,
            ui=dataclasses.replace(state.ui, view_mode=action.mode)
        )
    
    elif isinstance(action, UpdateStatus):
        return dataclasses.replace(
            state,
            ui=dataclasses.replace(state.ui, status_message=action.message)
        )
    
    # Document browser reducers
    elif isinstance(action, SearchDocuments):
        # Save search query for this browser
        new_queries = state.session.last_search_queries.copy()
        new_queries[BrowserType.DOCUMENTS] = action.query
        
        return dataclasses.replace(
            state,
            documents=dataclasses.replace(
                state.documents,
                search_query=action.query,
                cursor_position=0  # Reset cursor on new search
            ),
            session=dataclasses.replace(
                state.session,
                last_search_queries=new_queries
            )
        )
    
    elif isinstance(action, SelectDocument):
        return dataclasses.replace(
            state,
            documents=dataclasses.replace(
                state.documents,
                selected_doc_id=action.doc_id,
                cursor_position=action.cursor_position
            )
        )
    
    elif isinstance(action, UpdateDocumentCursor):
        return dataclasses.replace(
            state,
            documents=dataclasses.replace(
                state.documents,
                cursor_position=action.position,
                scroll_offset=action.scroll_offset
            )
        )
    
    # File browser reducers
    elif isinstance(action, NavigateToPath):
        new_history = state.file.path_history + [action.path] if action.add_to_history else state.file.path_history
        return dataclasses.replace(
            state,
            file=dataclasses.replace(
                state.file,
                current_path=action.path,
                selected_index=0,  # Reset selection
                path_history=new_history[-20:]  # Keep last 20 paths
            )
        )
    
    elif isinstance(action, ToggleHiddenFiles):
        return dataclasses.replace(
            state,
            file=dataclasses.replace(
                state.file,
                show_hidden=not state.file.show_hidden
            )
        )
    
    # Git browser reducers
    elif isinstance(action, SwitchWorktree):
        return dataclasses.replace(
            state,
            git=dataclasses.replace(
                state.git,
                worktree_path=action.worktree_path,
                worktree_index=action.worktree_index,
                selected_file_index=0  # Reset selection
            )
        )
    
    elif isinstance(action, SelectGitFile):
        return dataclasses.replace(
            state,
            git=dataclasses.replace(
                state.git,
                selected_file_index=action.file_index
            )
        )
    
    # Restore browser state
    elif isinstance(action, RestoreBrowserState):
        if action.browser == BrowserType.DOCUMENTS:
            return dataclasses.replace(state, documents=action.state)
        elif action.browser == BrowserType.FILE:
            return dataclasses.replace(state, file=action.state)
        elif action.browser == BrowserType.GIT:
            return dataclasses.replace(state, git=action.state)
    
    return state
```

### Integration with Textual's Reactive System

```python
from textual.app import App
from textual.reactive import reactive

class EMDXApp(App):
    """Main application with integrated state management."""
    
    # Make store state reactive for Textual
    app_state = reactive(AppState())
    
    def __init__(self):
        super().__init__()
        self.store = StateStore(AppState())
        
        # Subscribe to store changes to update reactive property
        self.store.subscribe(self._on_store_change)
        
        # Set up state persistence
        self._setup_persistence()
    
    def _on_store_change(self, old_state: AppState, new_state: AppState) -> None:
        """Update reactive property when store changes."""
        self.app_state = new_state
        
        # Handle side effects
        self._handle_side_effects(old_state, new_state)
    
    def _handle_side_effects(self, old_state: AppState, new_state: AppState) -> None:
        """Handle side effects from state changes."""
        # Browser switching
        if old_state.ui.active_browser != new_state.ui.active_browser:
            self._switch_browser_widget(new_state.ui.active_browser)
        
        # Status updates
        if old_state.ui.status_message != new_state.ui.status_message:
            self._update_status_bar(new_state.ui.status_message)
        
        # Notifications
        if new_state.ui.notification and new_state.ui.notification != old_state.ui.notification:
            message, severity = new_state.ui.notification
            self.notify(message, severity=severity)
    
    def watch_app_state(self, old_state: AppState, new_state: AppState) -> None:
        """Textual watcher for reactive state changes."""
        # This enables child widgets to react to state changes
        pass
    
    def dispatch(self, action: Action) -> None:
        """Dispatch action to store."""
        self.store.dispatch(action)
    
    def get_browser_state(self, browser_type: BrowserType) -> Any:
        """Get current state for a specific browser."""
        state = self.store.state
        if browser_type == BrowserType.DOCUMENTS:
            return state.documents
        elif browser_type == BrowserType.FILE:
            return state.file
        elif browser_type == BrowserType.GIT:
            return state.git
        return None
```

### State-Connected Browser Components

```python
class StateConnectedBrowser(Widget):
    """Base class for state-connected browser widgets."""
    
    def __init__(self, browser_type: BrowserType):
        super().__init__()
        self.browser_type = browser_type
        self._unsubscribe = None
    
    def on_mount(self) -> None:
        """Subscribe to state changes when mounted."""
        # Get app instance
        app = self.app
        if hasattr(app, 'store'):
            self._unsubscribe = app.store.subscribe(self._on_state_change)
            
            # Initial state sync
            self._sync_with_state(app.store.state)
    
    def on_unmount(self) -> None:
        """Unsubscribe when unmounted."""
        if self._unsubscribe:
            self._unsubscribe()
    
    def _on_state_change(self, old_state: AppState, new_state: AppState) -> None:
        """Handle state changes."""
        # Only react to relevant changes
        old_browser_state = self._get_browser_state(old_state)
        new_browser_state = self._get_browser_state(new_state)
        
        if old_browser_state != new_browser_state:
            self._sync_with_state(new_state)
    
    def _get_browser_state(self, app_state: AppState) -> Any:
        """Extract relevant browser state."""
        if self.browser_type == BrowserType.DOCUMENTS:
            return app_state.documents
        elif self.browser_type == BrowserType.FILE:
            return app_state.file
        elif self.browser_type == BrowserType.GIT:
            return app_state.git
        return None
    
    def _sync_with_state(self, app_state: AppState) -> None:
        """Sync widget with state - override in subclasses."""
        raise NotImplementedError
    
    def dispatch(self, action: Action) -> None:
        """Dispatch action to store."""
        if hasattr(self.app, 'dispatch'):
            self.app.dispatch(action)


class DocumentBrowserWidget(StateConnectedBrowser):
    """Document browser connected to state store."""
    
    def __init__(self):
        super().__init__(BrowserType.DOCUMENTS)
    
    def _sync_with_state(self, app_state: AppState) -> None:
        """Sync widget with document browser state."""
        state = app_state.documents
        
        # Update search input
        search_input = self.query_one("#search-input", Input)
        if search_input.value != state.search_query:
            search_input.value = state.search_query
        
        # Update cursor position
        table = self.query_one("#doc-table", DataTable)
        if table.cursor_coordinate.row != state.cursor_position:
            table.move_cursor(row=state.cursor_position)
        
        # Update scroll position
        # ... etc
    
    def on_data_table_cursor_changed(self, event) -> None:
        """Handle cursor movement."""
        self.dispatch(UpdateDocumentCursor(
            position=event.cursor_coordinate.row,
            scroll_offset=self._get_scroll_offset()
        ))
    
    def on_input_changed(self, event) -> None:
        """Handle search input changes."""
        if event.input.id == "search-input":
            self.dispatch(SearchDocuments(query=event.value))
```

### State Persistence

```python
import json
from pathlib import Path

class StatePersistence:
    """Handle state persistence to disk."""
    
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
    
    def save_state(self, state: AppState) -> None:
        """Save state to disk."""
        # Convert to JSON-serializable dict
        state_dict = self._state_to_dict(state)
        
        # Write atomically
        temp_file = self.state_file.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(state_dict, f, indent=2)
        
        # Atomic rename
        temp_file.replace(self.state_file)
    
    def load_state(self) -> Optional[AppState]:
        """Load state from disk."""
        if not self.state_file.exists():
            return None
        
        try:
            with open(self.state_file) as f:
                state_dict = json.load(f)
            
            return self._dict_to_state(state_dict)
        except Exception as e:
            logger.error(f"Failed to load state: {e}")
            return None
    
    def _state_to_dict(self, state: AppState) -> dict:
        """Convert state to JSON-serializable dict."""
        return {
            'version': '1.0',
            'ui': {
                'active_browser': state.ui.active_browser.value,
                'view_mode': state.ui.view_mode.value,
                'preview_visible': state.ui.preview_visible,
                'sidebar_width': state.ui.sidebar_width,
                'theme': state.ui.theme
            },
            'documents': {
                'search_query': state.documents.search_query,
                'tag_filter': state.documents.tag_filter,
                'selected_doc_id': state.documents.selected_doc_id,
                'cursor_position': state.documents.cursor_position,
                'sort_by': state.documents.sort_by,
                'sort_reverse': state.documents.sort_reverse
            },
            'file': {
                'current_path': str(state.file.current_path),
                'show_hidden': state.file.show_hidden,
                'selected_index': state.file.selected_index,
                'bookmarks': [str(p) for p in state.file.bookmarks]
            },
            'git': {
                'worktree_path': str(state.git.worktree_path),
                'worktree_index': state.git.worktree_index,
                'show_staged': state.git.show_staged,
                'show_unstaged': state.git.show_unstaged,
                'show_untracked': state.git.show_untracked
            }
        }
    
    def _dict_to_state(self, data: dict) -> AppState:
        """Convert dict to state object."""
        # Validate version
        if data.get('version') != '1.0':
            raise ValueError(f"Unsupported state version: {data.get('version')}")
        
        return AppState(
            ui=UIState(
                active_browser=BrowserType(data['ui']['active_browser']),
                view_mode=ViewMode(data['ui']['view_mode']),
                preview_visible=data['ui']['preview_visible'],
                sidebar_width=data['ui']['sidebar_width'],
                theme=data['ui']['theme']
            ),
            documents=DocumentBrowserState(
                search_query=data['documents']['search_query'],
                tag_filter=data['documents']['tag_filter'],
                selected_doc_id=data['documents']['selected_doc_id'],
                cursor_position=data['documents']['cursor_position'],
                sort_by=data['documents']['sort_by'],
                sort_reverse=data['documents']['sort_reverse']
            ),
            file=FileBrowserState(
                current_path=Path(data['file']['current_path']),
                show_hidden=data['file']['show_hidden'],
                selected_index=data['file']['selected_index'],
                bookmarks=[Path(p) for p in data['file']['bookmarks']]
            ),
            git=GitBrowserState(
                worktree_path=Path(data['git']['worktree_path']),
                worktree_index=data['git']['worktree_index'],
                show_staged=data['git']['show_staged'],
                show_unstaged=data['git']['show_unstaged'],
                show_untracked=data['git']['show_untracked']
            )
        )
```

### State Validation and Migrations

```python
from typing import Protocol

class StateValidator(Protocol):
    """Protocol for state validators."""
    
    def validate(self, state: Any) -> tuple[bool, list[str]]:
        """Validate state, return (is_valid, errors)."""
        ...

class DocumentStateValidator:
    """Validate document browser state."""
    
    def validate(self, state: DocumentBrowserState) -> tuple[bool, list[str]]:
        errors = []
        
        if state.cursor_position < 0:
            errors.append("Cursor position cannot be negative")
        
        if state.scroll_offset < 0:
            errors.append("Scroll offset cannot be negative")
        
        if state.sort_by not in ["modified", "created", "title", "id"]:
            errors.append(f"Invalid sort field: {state.sort_by}")
        
        return len(errors) == 0, errors

class StateMiddleware:
    """Validation middleware for state store."""
    
    def __init__(self, validators: dict[type, StateValidator]):
        self.validators = validators
    
    def __call__(self, action: Action, state: AppState) -> Optional[Action]:
        """Validate state changes."""
        # Apply action to get new state
        new_state = app_reducer(state, action)
        
        # Validate each browser state
        for browser_type, validator in self.validators.items():
            browser_state = self._get_browser_state(new_state, browser_type)
            if browser_state:
                is_valid, errors = validator.validate(browser_state)
                if not is_valid:
                    logger.error(f"State validation failed for {browser_type}: {errors}")
                    return None  # Cancel action
        
        return action
```

### Performance Optimizations

```python
class MemoizedSelector:
    """Memoized state selectors for performance."""
    
    def __init__(self):
        self._cache = {}
    
    def select_visible_documents(self, state: AppState) -> list[Document]:
        """Select visible documents based on search/filters."""
        cache_key = (
            state.documents.search_query,
            tuple(state.documents.tag_filter),
            state.documents.sort_by,
            state.documents.sort_reverse
        )
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        # Compute filtered/sorted documents
        result = self._compute_visible_documents(state)
        self._cache[cache_key] = result
        
        # Limit cache size
        if len(self._cache) > 100:
            self._cache.pop(next(iter(self._cache)))
        
        return result
    
    def _compute_visible_documents(self, state: AppState) -> list[Document]:
        """Actually compute the filtered documents."""
        # Implementation here
        pass

# Debounced actions for performance
class DebouncedDispatcher:
    """Debounce rapid state updates."""
    
    def __init__(self, store: StateStore, delay_ms: int = 100):
        self.store = store
        self.delay_ms = delay_ms
        self._pending = {}
    
    def dispatch_debounced(self, action: Action, key: str) -> None:
        """Dispatch action with debouncing."""
        # Cancel pending action with same key
        if key in self._pending:
            self._pending[key].cancel()
        
        # Schedule new action
        timer = Timer(self.delay_ms / 1000, lambda: self.store.dispatch(action))
        timer.start()
        self._pending[key] = timer
```

## Testing Strategy

### Unit Tests for Reducers

```python
def test_search_documents_reducer():
    """Test document search state updates."""
    initial = AppState()
    action = SearchDocuments(query="test")
    
    new_state = app_reducer(initial, action)
    
    assert new_state.documents.search_query == "test"
    assert new_state.documents.cursor_position == 0
    assert new_state.session.last_search_queries[BrowserType.DOCUMENTS] == "test"

def test_state_immutability():
    """Ensure state updates are immutable."""
    initial = AppState()
    action = ToggleHiddenFiles()
    
    new_state = app_reducer(initial, action)
    
    assert new_state is not initial
    assert new_state.file is not initial.file
    assert new_state.file.show_hidden != initial.file.show_hidden
```

### Integration Tests

```python
async def test_browser_state_preservation():
    """Test state preservation during browser switches."""
    app = EMDXApp()
    
    # Set up document browser state
    app.dispatch(SearchDocuments(query="test"))
    app.dispatch(SelectDocument(doc_id=123, cursor_position=5))
    
    # Switch to file browser
    app.dispatch(SwitchBrowser(browser=BrowserType.FILE))
    
    # Switch back
    app.dispatch(SwitchBrowser(browser=BrowserType.DOCUMENTS))
    
    # Verify state was preserved
    state = app.store.state
    assert state.documents.search_query == "test"
    assert state.documents.selected_doc_id == 123
    assert state.documents.cursor_position == 5
```

### Performance Tests

```python
def test_state_update_performance():
    """Ensure state updates are fast."""
    store = StateStore(AppState())
    
    start = time.perf_counter()
    for i in range(1000):
        store.dispatch(UpdateDocumentCursor(position=i))
    elapsed = time.perf_counter() - start
    
    assert elapsed < 0.1  # 1000 updates in < 100ms
```

## Migration Plan

### Phase 1: Core Infrastructure (Week 1)
1. Implement StateStore and Action system
2. Create state shapes for all browsers
3. Implement root reducer
4. Add state persistence layer

### Phase 2: Browser Integration (Week 2)
1. Refactor DocumentBrowser to use state store
2. Refactor FileBrowser to use state store
3. Refactor GitBrowser to use state store
4. Update container to coordinate through store

### Phase 3: Advanced Features (Week 3)
1. Add undo/redo functionality
2. Implement state validation middleware
3. Add performance optimizations
4. Create comprehensive test suite

### Phase 4: Polish and Documentation (Week 4)
1. Add developer tools for state debugging
2. Create migration guide for adding new browsers
3. Performance profiling and optimization
4. User documentation for new features

## Benefits of This Architecture

1. **Predictable State Updates**: All state changes go through reducers
2. **Time-Travel Debugging**: Full undo/redo support
3. **Easy Testing**: Pure functions are simple to test
4. **Performance**: Memoization and selective updates
5. **Extensibility**: New browsers just need state shape and reducers
6. **Type Safety**: Full TypeScript-like type checking
7. **Developer Experience**: Clear patterns and debugging tools

## Conclusion

This state management architecture provides a solid foundation for the EMDX browser system that addresses all current pain points while enabling rapid feature development. The combination of immutable state, Redux-like patterns, and Textual's reactive system creates a powerful and maintainable solution that scales with the application's growth.