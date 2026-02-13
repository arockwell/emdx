# EMDX Architecture Overview

## 🏗️ **System Design**

EMDX is a modular, SQLite-based knowledge management system with a clean CLI interface and rich TUI browser.

### **Core Principles**
- **Local-first** - SQLite database, no cloud dependencies
- **Simple and fast** - Direct command/database architecture  
- **Rich TUI** - Multiple browser modes with vim-like navigation
- **Git integration** - Automatic project detection

## 📦 **Actual Code Structure**

```
emdx/
├── main.py                 # CLI entry point (typer)
├── commands/               # CLI command implementations
│   ├── core.py            # save, find, view, edit, delete
│   ├── browse.py          # list, stats, recent
│   ├── tags.py            # tag management
│   ├── trash.py           # trash, restore, purge
│   ├── gist.py            # GitHub gist integration
│   ├── executions.py      # execution monitoring
│   ├── claude_execute.py  # Claude Code integration
│   ├── delegate.py        # one-shot AI execution
│   ├── cascade.py         # idea-to-code pipeline
│   ├── recipe.py          # reusable recipe management
│   ├── analyze.py         # database analysis
│   └── maintain.py        # maintenance operations
├── database/               # SQLite operations
│   ├── connection.py      # database connection
│   ├── documents.py       # document CRUD
│   ├── search.py          # FTS5 search
│   └── migrations.py      # schema migrations
├── models/                 # Data models
│   ├── documents.py       # document model
│   ├── tags.py           # tag model
│   └── executions.py     # execution model
├── ui/                     # TUI components (Textual)
│   ├── browser_container.py # main app container
│   ├── document_browser.py  # document management
│   ├── file_browser.py      # file system browser
│   ├── log_browser.py       # execution logs
│   ├── git_browser.py       # git diff viewer
│   ├── cascade_browser.py   # cascade stage browser
│   ├── activity/            # Activity view components
│   │   └── activity_view.py # unified activity display
│   └── vim_editor.py        # vim modal editing
├── services/               # Business logic
│   ├── log_stream.py      # event-driven log streaming
│   ├── file_watcher.py    # file monitoring
│   ├── auto_tagger.py     # automatic tagging
│   └── health_monitor.py  # system health
└── utils/                  # Shared utilities
    ├── git.py             # git operations
    ├── emoji_aliases.py   # tag alias system
    └── claude_wrapper.py  # Claude Code integration
```

## 🖥️ **TUI Browser Modes**

EMDX has a multi-modal TUI accessible via `emdx gui`:

### **Browser Container** (`browser_container.py`)
- **Document Mode** (default) - `d` or start here
- **File Mode** - `f` to switch from document mode
- **Git Mode** - `g` to switch from document mode
- **Log Mode** - `l` to switch from document mode
- **Activity Mode** - `a` to view execution activity
- **Cascade Mode** - `4` to view cascade stages
- **Back to Document** - `q` from any other mode

### **Actual Key Bindings** (from real code):

**Document Browser** (`document_browser.py`):
- `j/k` - move up/down
- `g/G` - go to top/bottom  
- `e` - edit document
- `n` - new document
- `/` - search
- `t/T` - add/remove tags
- `s` - selection mode
- `x` - execute document  
- `r` - refresh

**File Browser** (`file_browser.py`):
- `j/k` - move up/down
- `h/l` - parent dir/enter dir  
- `g/G` - go to top/bottom
- `.` - toggle hidden files
- `s` - selection mode
- `e` - edit file
- `/` - search

**Log Browser** (`log_browser.py`):
- `j/k` - move up/down
- `g/G` - go to top/bottom
- `s` - selection mode
- `r` - refresh  
- `l` - toggle live mode

**Activity View** (`activity/activity_view.py`):
- `j/k` - move up/down
- `g/G` - go to top/bottom
- `enter` - expand/view details
- `r` - refresh
- Filter by executions, documents, groups

## 🗃️ **Database Architecture**

### **Core Tables**
- **`documents`** - Document metadata, content, and indexing
- **`tags`** - Tag definitions with emoji and aliases
- **`document_tags`** - Many-to-many document-tag relationships
- **`executions`** - Execution tracking and lifecycle
- **`documents_fts`** - Full-text search virtual table
- **`cascade_runs`** - Cascade pipeline executions
- **`document_groups`** - Hierarchical document organization
- **`tasks`** - Task management with dependencies

### **Key Design Decisions**
- **SQLite with FTS5** - Fast full-text search with simple deployment
- **Emoji tags** - Space-efficient visual organization
- **JSON metadata** - Flexible document attributes
- **Versioned migrations** - Safe schema evolution

## 🎨 **UI Architecture (Textual TUI)**

### **Component Hierarchy**

```
App (emdx gui)
└── BrowserContainer
    ├── DocumentBrowser (default)
    │   ├── DocumentTable
    │   ├── PreviewPanel
    │   └── DetailsPanel
    ├── LogBrowser (press 'l')
    │   ├── ExecutionTable
    │   ├── LogViewer (with streaming)
    │   └── MetadataPanel
    ├── FileBrowser (press 'f')
    │   ├── FileTree
    │   └── FilePreview
    ├── ActivityView (press 'a')
    │   ├── ActivityTree (executions, documents, groups)
    │   └── ContextPanel (details for selected item)
    └── CascadeBrowser (press '4')
        ├── Stage columns (idea → prompt → analyzed → planned → done)
        └── Document processing controls
```

### **Key Patterns**
- **Widget Composition** - Complex UIs built from simple, reusable widgets
- **Event Bubbling** - Key presses bubble up through widget hierarchy
- **Reactive Updates** - UI automatically updates when data changes
- **Modal Editing** - Vim-like editing modes for power users

## 🔄 **Data Flow**

EMDX follows a simple, direct architecture:

### **Command Flow**
1. **CLI command** → `main.py` (typer) → specific `commands/*.py` module
2. **Command logic** → `models/*.py` for data operations → `database/*.py` for SQL
3. **Results** → back to command → formatted output via Rich

### **TUI Flow** 
1. **User input** → browser widget → action method
2. **Data change** → model operation → database update
3. **UI update** → reactive properties → widget refresh

### **Log Streaming** (event-driven)
1. **File change** → OS file watcher → `LogStream` callback
2. **New content** → subscriber notification → UI widget update  
3. **Live mode** → automatic scrolling → real-time display

## 🎯 **Key Design Decisions**

### **Why SQLite + FTS5**
- **Zero setup** - No database server required
- **Fast search** - Full-text search with ranking built-in
- **Portable** - Single file database, easy backup/sync
- **Reliable** - ACID transactions, battle-tested

### **Why Textual TUI**
- **Rich terminal UI** - Modern widgets, CSS styling, mouse support
- **Cross-platform** - Works on all terminals consistently  
- **Reactive** - Automatic UI updates when data changes
- **Developer-friendly** - Good debugging tools, clear widget model

### **Why Event-Driven Log Streaming**
- **Performance** - No polling overhead, only update when files change
- **Reliability** - OS-level file watching more reliable than timers
- **Simplicity** - Eliminates complex timer/state coordination
- **Scalability** - Can watch multiple files with one watcher

## 🔧 **Development Patterns**

### **Adding CLI Commands**
1. Create function in appropriate `commands/*.py` module
2. Add typer decorators with type hints
3. Use `models/*.py` for data operations
4. Return rich-formatted output

### **Adding TUI Features**  
1. Extend existing browser or create new widget
2. Add key bindings in `BINDINGS` list
3. Implement action methods
4. Use reactive properties for state

### **Database Changes**
1. Add migration in `database/migrations.py`
2. Update models in `models/*.py`  
3. Test with existing data
4. Update related commands/UI

This architecture prioritizes simplicity and directness over abstract patterns, making the codebase easy to understand and modify.