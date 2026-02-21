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
│   ├── tags.py            # tag add/remove/list/rename/merge/batch
│   ├── trash.py           # trash, restore, purge
│   ├── tasks.py           # task work queue (add/ready/done/view/active/blocked)
│   ├── gist.py            # GitHub gist integration
│   ├── executions.py      # execution monitoring
│   ├── delegate.py        # one-shot AI execution (parallel, worktree, PR)
│   ├── recipe.py          # reusable recipe management
│   ├── ask.py             # AI Q&A over knowledge base
│   ├── prime.py           # session priming context
│   ├── status.py          # project status overview
│   ├── briefing.py        # recent activity summary
│   ├── compact.py         # AI-powered document synthesis
│   ├── distill.py         # audience-aware summarization
│   ├── epics.py           # epic management
│   ├── categories.py      # task category management
│   ├── review.py          # triage agent-produced documents
│   ├── stale.py           # knowledge decay tracking
│   ├── analyze.py         # database analysis
│   └── maintain.py        # maintenance operations
├── config/                 # Configuration management
│   ├── cli_config.py      # CLI configuration
│   ├── constants.py       # shared constants
│   ├── settings.py        # application settings
│   ├── tagging_rules.py   # auto-tagging rules
│   └── ui_config.py       # UI configuration
├── database/               # SQLite operations
│   ├── connection.py      # database connection
│   ├── documents.py       # document CRUD
│   ├── search.py          # FTS5 search
│   ├── types.py           # database type definitions
│   └── migrations.py      # schema migrations (41 migrations, 0-40)
├── models/                 # Data models
│   ├── documents.py       # document model
│   ├── tags.py            # tag model
│   ├── executions.py      # execution model
│   ├── tasks.py           # task model
│   ├── categories.py      # category model
│   └── types.py           # shared type definitions
├── ui/                     # TUI components (Textual)
│   ├── gui.py                 # main GUI entry point
│   ├── browser_container.py   # main app container
│   ├── activity_browser.py    # unified activity display
│   ├── activity/              # activity view components
│   ├── log_browser.py         # execution logs
│   ├── run_browser.py         # execution run browser
│   ├── task_browser.py        # task management browser
│   ├── task_view.py           # task detail view
│   ├── command_palette/       # command palette system
│   ├── keybindings/           # keybinding management
│   ├── search/                # search UI components
│   ├── qa/                    # Q&A UI components
│   ├── modals.py              # modal dialogs
│   ├── formatting.py          # output formatting
│   ├── inputs.py              # input widgets
│   ├── text_areas.py          # text area widgets
│   ├── themes.py              # theme system
│   └── theme_selector.py      # theme selection UI
├── services/               # Business logic
│   ├── unified_executor.py    # CLI execution (Claude)
│   ├── cli_executor/          # CLI executor components
│   ├── log_stream.py         # event-driven log streaming
│   ├── file_watcher.py       # file monitoring
│   ├── auto_tagger.py        # automatic tagging
│   ├── embedding_service.py   # semantic search embeddings
│   ├── hybrid_search.py      # combined keyword + semantic search
│   ├── unified_search.py     # unified search interface
│   ├── similarity.py         # document similarity
│   ├── duplicate_detector.py  # duplicate detection
│   ├── ask_service.py        # AI Q&A service
│   ├── claude_executor.py    # Claude API executor
│   ├── document_service.py   # document operations
│   ├── document_merger.py    # document merging
│   ├── synthesis_service.py  # synthesis orchestration
│   ├── tag_service.py        # tag operations
│   ├── execution_service.py  # execution management
│   ├── execution_monitor.py  # execution health monitoring
│   └── health_monitor.py     # system health
└── utils/                  # Shared utilities
    ├── git.py             # git operations (worktrees, branches)
    ├── git_ops.py         # additional git utilities
    ├── emoji_aliases.py   # tag utilities
    ├── claude_wrapper.py  # Claude Code integration
    ├── chunk_splitter.py  # document chunking
    ├── output.py          # shared console output
    ├── output_parser.py   # execution output parsing
    ├── text_formatting.py # text formatting utilities
    ├── title_normalization.py # title normalization
    ├── datetime_utils.py  # date/time helpers
    ├── file_size.py       # file size utilities
    ├── environment.py     # environment detection
    ├── lazy_group.py      # lazy-loaded typer groups
    ├── retry.py           # retry logic
    ├── logging_utils.py   # logging utilities
    └── structured_logger.py # structured logging
```

## 🖥️ **TUI Browser Modes**

EMDX has a multi-modal TUI accessible via `emdx gui`:

### **Browser Container** (`browser_container.py`)
- **Document Mode** (default) - `d` or start here
- **Log Mode** - `l` to switch from document mode
- **Activity Mode** - `a` to view execution activity
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
- Filter by executions and documents

## 🗃️ **Database Architecture**

### **Core Tables**
- **`documents`** - Document metadata, content, and indexing
- **`tags`** - Tag definitions with emoji and aliases
- **`document_tags`** - Many-to-many document-tag relationships
- **`executions`** - Execution tracking and lifecycle
- **`documents_fts`** - Full-text search virtual table
- **`tasks`** - Agent work queue with epics and categories
- **`chunk_embeddings`** - Chunk-level semantic search vectors

### **Key Design Decisions**
- **SQLite with FTS5** - Fast full-text search with simple deployment
- **Plain text tags** - Simple, readable tag organization
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
    ├── ActivityView (press 'a')
    │   ├── ActivityTree (executions and documents)
    │   └── ContextPanel (details for selected item)
    └── TaskBrowser (press 't')
        ├── Task list with status indicators
        └── Task detail view
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