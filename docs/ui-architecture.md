# EMDX UI Architecture

## 🎨 **TUI Framework: Textual**

EMDX uses the [Textual](https://textual.textualize.io/) framework for its terminal user interface, providing a rich, responsive experience with modern terminal features.

### **Why Textual?**
- **Modern TUI** - Rich widgets, CSS styling, smooth animations
- **Reactive Design** - Automatic UI updates when data changes
- **Cross-platform** - Works consistently across different terminals
- **Developer-friendly** - Hot reload, debugging tools, comprehensive docs

## 🏗️ **UI Component Hierarchy**

```
EMDXApp (Main Application)
└── BrowserContainer (Modal Router)
    ├── DocumentBrowser (Default Mode - press 'd')
    │   ├── DocumentTable (Left)
    │   ├── PreviewPanel (Right)
    │   └── StatusBar
    ├── LogBrowser (Press 'l')
    │   ├── ExecutionTable (Left)
    │   └── LogViewer (Right, with live streaming)
    ├── ActivityView (Press 'a')
    │   ├── ActivityTree (executions, documents, groups)
    │   └── ContextPanel (details for selected item)
    └── FileBrowser (Press 'f')
        ├── FileTree (Left)
        └── FilePreview (Right)
```

## 📱 **Core UI Components**

### **1. BrowserContainer - Modal Router**

```python
class BrowserContainer(Widget):
    """Main container that manages different browser modes."""

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("l", "switch_to_logs", "Logs"),
        ("d", "switch_to_documents", "Documents"),
    ]

    def __init__(self):
        super().__init__()
        self.current_mode = "documents"
        self.document_browser = DocumentBrowser()
        self.log_browser = LogBrowser()
```

**Key Features:**
- **Modal switching** - One browser visible at a time
- **State preservation** - Each browser maintains its state when hidden
- **Global keybindings** - Consistent navigation across modes
- **Responsive layout** - Adapts to terminal size

### **2. DocumentBrowser - Knowledge Base Interface**

```python
class DocumentBrowser(Widget):
    """Main document management interface."""
    
    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"), 
        ("g", "go_top", "Top"),
        ("G", "go_bottom", "Bottom"),
        ("/", "search", "Search"),
        ("enter", "view_document", "View"),
        ("e", "edit_document", "Edit"),
        ("t", "tag_document", "Tag"),
        ("r", "refresh", "Refresh"),
    ]
```

#### **DocumentTable Component**
- **Sortable columns** - ID, Title, Project, Tags, Last Modified
- **Emoji tag display** - Space-efficient visual organization
- **Real-time filtering** - As-you-type search
- **Pagination** - Handle large document collections

#### **PreviewPanel Component**
- **Markdown rendering** - Rich content display with syntax highlighting
- **Lazy loading** - Load content only when selected
- **Auto-refresh** - Updates when document changes
- **Scroll synchronization** - Smooth navigation

#### **DetailsPanel Component**
- **Tag management** - Add/remove tags with text aliases
- **Metadata display** - Created, modified, access count
- **Quick actions** - Edit, delete, share, export

### **3. LogBrowser - Execution Monitoring**

```python
class LogBrowser(Widget):
    """Real-time execution and log monitoring."""
    
    BINDINGS = [
        ("space", "toggle_live", "Live Mode"),
        ("f", "follow_logs", "Follow"),
        ("c", "clear_logs", "Clear"),
        ("k", "kill_execution", "Kill"),
        ("h", "health_check", "Health"),
    ]
```

#### **ExecutionTable Component**
- **Status indicators** - Running, completed, failed states
- **Health monitoring** - PID, duration, heartbeat status
- **Filterable** - By status, project, time range
- **Real-time updates** - Live execution tracking

#### **LogViewer Component (Event-Driven)**
- **Real-time streaming** - Event-driven log updates via LogStream
- **Live mode toggle** - Auto-scroll for running executions
- **Search integration** - Find text in streaming logs
- **Performance optimized** - Incremental updates only

```python
class LogBrowser(Widget):
    def __init__(self):
        super().__init__()
        self.log_stream: Optional[LogStream] = None
        self.is_live_mode = False
        
    def action_toggle_live(self):
        """Toggle live log streaming."""
        if self.is_live_mode:
            self._stop_live_mode()
        else:
            self._start_live_mode()
    
    def _start_live_mode(self):
        if self.current_execution and self.current_execution.log_file:
            log_path = Path(self.current_execution.log_file)
            self.log_stream = LogStream(log_path)
            self.subscriber = LogBrowserSubscriber(self)
            self.log_stream.subscribe(self.subscriber)
            self.is_live_mode = True
```

### **4. ActivityView - Unified Activity Display**

The ActivityView (press `a`) shows a unified tree of recent executions, documents, and groups.

- **Tree-based display** - Hierarchical view with expandable items
- **Lazy loading** - Children loaded on expand
- **Multiple item types** - Executions, documents, groups in one view
- **Refresh** - Press `r` to refresh

## 🎮 **Key Binding System**

### **Global Bindings (Available in All Modes)**
```python
GLOBAL_BINDINGS = [
    ("ctrl+c", "quit", "Quit"),
    ("q", "quit_or_back", "Quit/Back"),
    ("?", "help", "Help"),
    (":", "command_mode", "Command"),
]
```

### **Mode-Specific Bindings**
- **Document Mode**: vim-like navigation (j/k/g/G), search (/), edit (e)
- **Log Mode**: live toggle (space), follow (f), kill (k)
- **Activity Mode**: expand/collapse (l/h), refresh (r), fullscreen (f)

## 🎨 **Styling & Theming**

### **CSS-like Styling with Textual**
```python
# Widget styling using Textual CSS
class DocumentBrowser(Widget):
    DEFAULT_CSS = """
    DocumentBrowser {
        layout: vertical;
    }
    
    DocumentTable {
        dock: left;
        width: 60%;
        border: solid $primary;
    }
    
    PreviewPanel {
        dock: right; 
        width: 40%;
        border: solid $secondary;
    }
    
    TagDisplay {
        background: $surface;
        color: $on-surface;
        padding: 1;
    }
    """
```

### **Color Schemes**
- **Adaptive theming** - Respects terminal color preferences
- **Emoji emphasis** - Tags use emoji for visual organization
- **Status indicators** - Color-coded execution states
- **Syntax highlighting** - Rich code display

## 📊 **Responsive Design**

### **Terminal Size Adaptation**
```python
def on_resize(self, event):
    """Adapt layout to terminal size changes."""
    width, height = event.terminal_size
    
    if width < 120:
        # Narrow terminal: vertical layout
        self.layout = "vertical"
        self.preview_panel.display = False
    else:
        # Wide terminal: horizontal layout
        self.layout = "horizontal"
        self.preview_panel.display = True
```

### **Content Scaling**
- **Column width adaptation** - Tables adjust to available space
- **Text wrapping** - Intelligent line breaking for narrow terminals
- **Panel collapsing** - Hide panels on very small screens
- **Zoom support** - Adjust font size via terminal settings

## 🔄 **State Management**

### **Reactive Data Flow**
```python
# Documents update → UI automatically refreshes
class DocumentBrowser(Widget):
    documents = reactive([])  # Reactive list
    selected_doc = reactive(None)  # Reactive selection
    
    def watch_documents(self, new_docs):
        """Called automatically when documents change."""
        self.document_table.update_rows(new_docs)
    
    def watch_selected_doc(self, doc):
        """Called automatically when selection changes."""
        self.preview_panel.show_document(doc)
        self.details_panel.show_metadata(doc)
```

### **Event-Driven Updates**
- **Document changes** → UI refreshes automatically
- **Log updates** → Real-time streaming to UI
- **Execution status** → Live status indicator updates
- **Search results** → Instant filtering and highlighting

## 🚀 **Performance Optimizations**

### **Lazy Loading**
- **Documents** - Load content only when viewed
- **Logs** - Stream only visible content
- **File tree** - Expand directories on demand
- **Preview** - Render content when panel is visible

### **Virtual Scrolling**
```python
class OptimizedTable(DataTable):
    """Virtual scrolling for large datasets."""
    
    def __init__(self, max_visible=100):
        super().__init__()
        self.max_visible = max_visible
        self.virtual_start = 0
    
    def update_visible_rows(self):
        """Show only visible rows for performance."""
        visible_data = self.data[
            self.virtual_start:self.virtual_start + self.max_visible
        ]
        self.clear()
        self.add_rows(visible_data)
```

### **Incremental Updates**
- **Log streaming** - Append only new content
- **Search results** - Update results as you type
- **File watching** - React to external file changes
- **Database queries** - Pagination for large result sets

## 🧪 **Testing UI Components**

### **Widget Testing**
```python
import pytest
from textual.app import App
from emdx.ui.document_browser import DocumentBrowser

class TestApp(App):
    def compose(self):
        yield DocumentBrowser()

@pytest.mark.asyncio
async def test_document_browser():
    """Test document browser widget behavior."""
    app = TestApp()
    async with app.run_test() as pilot:
        # Test key presses
        await pilot.press("j")  # Move down
        await pilot.press("/")  # Search
        
        # Test widget state
        browser = app.query_one(DocumentBrowser)
        assert browser.selected_row == 1
```

### **Integration Testing**
```python
async def test_log_streaming_ui():
    """Test real-time log streaming in UI."""
    app = EMDXApp()
    async with app.run_test() as pilot:
        # Switch to log browser
        await pilot.press("l")
        
        # Start live mode
        await pilot.press("space")
        
        # Simulate log file change
        append_to_log_file("test content")
        
        # Verify UI updates
        log_widget = app.query_one(RichLog)
        assert "test content" in log_widget.renderable
```

## 🎯 **User Experience Design**

### **Progressive Disclosure**
- **Start simple** - Document browser is default view
- **Power user features** - Vim mode, advanced search, scripting
- **Context-sensitive help** - Different help for each mode
- **Smart defaults** - Reasonable behavior without configuration

### **Accessibility**
- **Keyboard-first** - All features accessible via keyboard
- **Screen reader support** - Proper labels and descriptions
- **High contrast** - Readable in all terminal themes
- **Consistent navigation** - Predictable key bindings across modes

### **Error Handling & User Feedback**
```python
def show_error(self, message: str, details: str = ""):
    """Display user-friendly error messages."""
    self.notify(
        title="Error",
        message=message,
        severity="error",
        timeout=10
    )
    
    # Log technical details for debugging
    logger.error(f"{message}: {details}")
```

This UI architecture provides a powerful, responsive terminal interface that scales from simple document viewing to complex execution monitoring, all while maintaining excellent performance and user experience.