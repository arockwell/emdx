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
│   ├── tags.py            # tag add/remove/list/rename/merge/batch
│   ├── trash.py           # trash, restore, purge
│   ├── tasks.py           # task work queue (add/ready/done/view/active/blocked)
│   ├── epics.py           # epic management
│   ├── categories.py      # task category management
│   ├── gist.py            # GitHub gist integration
│   ├── prime.py           # session priming context
│   ├── status.py          # project status overview
│   ├── briefing.py        # recent activity summary
│   ├── compact.py         # AI-powered document synthesis
│   ├── distill.py         # audience-aware summarization
│   ├── stale.py           # knowledge decay tracking
│   ├── explore.py         # interactive codebase exploration
│   ├── history.py         # document version history
│   ├── wiki.py            # wiki system (topics, articles, export)
│   ├── serve.py           # HTTP API server
│   ├── db_manage.py       # database management (status, path, copy-from-prod)
│   ├── code_drift.py      # code drift detection
│   ├── maintain.py        # maintenance operations (index, link, backup, cleanup)
│   ├── maintain_index.py  # embedding index management
│   ├── _freshness.py      # knowledge freshness scoring
│   ├── _gaps.py           # knowledge gap detection
│   ├── _drift.py          # knowledge drift tracking
│   ├── _watch.py          # standing query watch system
│   └── types.py           # command-level type definitions
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
│   ├── document_links.py  # document link graph operations
│   ├── types.py           # database type definitions
│   └── migrations.py      # schema migrations (59 migrations, 0-58)
├── models/                 # Data models
│   ├── documents.py       # document model
│   ├── tags.py            # tag model
│   ├── events.py          # knowledge events model
│   ├── tasks.py           # task model
│   ├── categories.py      # category model
│   └── types.py           # shared type definitions
├── ui/                     # TUI components (Textual)
│   ├── gui.py                 # main GUI entry point
│   ├── browser_container.py   # main app container
│   ├── activity_browser.py    # unified activity display
│   ├── activity/              # activity view components
│   │   ├── activity_view.py   # three-tier dashboard (RUNNING/TASKS/DOCS)
│   │   ├── activity_data.py   # data loading and deduplication
│   │   ├── activity_items.py  # item models for activity rows
│   │   ├── activity_table.py  # flat DataTable with section headers
│   │   └── sparkline.py       # 7-day activity sparkline
│   ├── knowledge_graph_panel.py  # linked docs, entities, wiki topics panel
│   ├── run_browser.py         # execution run browser
│   ├── task_browser.py        # task management browser
│   ├── task_view.py           # task detail view
│   ├── command_palette/       # command palette system
│   ├── keybindings/           # keybinding management
│   ├── search/                # search UI components
│   ├── modals.py              # modal dialogs
│   ├── formatting.py          # output formatting
│   ├── inputs.py              # input widgets
│   ├── text_areas.py          # text area widgets
│   ├── link_helpers.py        # link graph UI helpers
│   ├── markdown_config.py     # markdown rendering configuration
│   ├── protocols.py           # UI protocol definitions
│   ├── types.py               # UI type definitions
│   ├── themes.py              # theme system
│   └── theme_selector.py      # theme selection UI
├── services/               # Business logic
│   ├── ask_service.py         # AI Q&A service
│   ├── auto_tagger.py         # automatic tagging
│   ├── backup_service.py      # database backup and restore
│   ├── clustering.py          # document clustering
│   ├── contradiction_service.py # contradiction detection
│   ├── document_merger.py     # document merging
│   ├── duplicate_detector.py  # duplicate detection
│   ├── embedding_service.py   # semantic search embeddings
│   ├── entity_service.py      # named entity extraction
│   ├── file_watcher.py        # file monitoring
│   ├── health_monitor.py      # system health
│   ├── hybrid_search.py       # canonical search (FTS5, semantic, fuzzy, tags)
│   ├── link_service.py        # document auto-linking
│   ├── log_stream.py          # event-driven log streaming
│   ├── similarity.py          # document similarity
│   ├── synthesis_service.py   # synthesis orchestration
│   ├── wiki_clustering_service.py  # wiki topic clustering
│   ├── wiki_entity_service.py     # wiki entity extraction
│   ├── wiki_export_service.py     # wiki MkDocs export
│   ├── wiki_privacy_service.py    # wiki PII redaction
│   ├── wiki_synthesis_service.py  # wiki article generation
│   ├── wikify_service.py          # wiki orchestration
│   └── types.py               # service type definitions
└── utils/                  # Shared utilities
    ├── git.py             # git operations (worktrees, branches)
    ├── chunk_splitter.py  # document chunking
    ├── output.py          # shared console output
    ├── text_formatting.py # text formatting utilities
    ├── title_normalization.py # title normalization
    ├── datetime_utils.py  # date/time helpers
    ├── environment.py     # environment detection
    ├── lazy_group.py      # lazy-loaded typer groups
    ├── logging_utils.py   # logging utilities
    └── structured_logger.py # structured logging
```

## 🖥️ **TUI Browser Modes**

EMDX has a multi-modal TUI accessible via `emdx gui`:

### **Browser Container** (`browser_container.py`)
- **Activity Mode** (default) - `1`
- **Task Mode** - `2`
- **Quit** - `q` (exits from activity/task; returns to activity from log mode)
- **Theme** - `\` cycle theme, `ctrl+t` toggle dark/light
- **Command Palette** - `ctrl+k` or `ctrl+p`

### **Actual Key Bindings** (from real code):

**Activity View** (`activity/activity_view.py`):
- Three-tier dashboard: RUNNING (active executions), TASKS (ready/active), DOCS (recent history)
- `ActivityDataLoader` loads documents, executions, and tasks, then deduplicates
  (tasks with `execution_id` skip if execution already loaded; task `output_doc_id` removes the duplicate document)
- Items sorted into tiers: running by start time, tasks by priority, recent by timestamp
- `j/k` - move up/down
- `R/T/D` - jump to RUNNING/TASKS/DOCS section (scrolls header to top, selects first item)
- `enter/f` - fullscreen document preview
- `x` - kill/dismiss running execution
- `c` - toggle copy mode (raw markdown vs rendered preview)
- `r` - refresh
- Section headers inserted by `ActivityTable` when tier changes
- Live log streaming for running agent executions via `LogStream`
- Status bar: active count, docs today, cost, errors, 7-day sparkline

**Task Browser** (`task_browser.py` + `task_view.py`):
- Two-pane layout: DataTable (left 40%) + detail RichLog (right 60%)
- `j/k` - move up/down
- `/` - show live filter bar (debounced text search over title, epic, description, tags)
- `escape` - clear filter and refocus table
- `g` - toggle grouping: by status (default) or by epic
- `o` - filter to ready (open) tasks only
- `i` - filter to active tasks only
- `x` - filter to blocked tasks only
- `f` - filter to done/failed/wontdo tasks only
- `*` - clear status filter (show all)
- `d` - mark task done
- `a` - mark task active
- `b` - mark task blocked
- `w` - mark task won't do
- `r` - refresh
- Epic grouping shows progress (done/total) and hides fully-completed epics

## 🗃️ **Database Architecture**

### **Core Tables**
- **`documents`** - Document metadata, content, and indexing
- **`documents_fts`** - Full-text search virtual table (FTS5)
- **`tags`** - Tag definitions with aliases
- **`document_tags`** - Many-to-many document-tag relationships
- **`categories`** - Task category definitions
- **`tasks`** - Agent work queue with epics and categories
- **`task_deps`** - Task dependency edges
- **`task_log`** - Task status change history
- **`executions`** - Execution tracking and lifecycle
- **`document_links`** - Directed links between documents (auto-linked or manual)
- **`document_entities`** - Named entities extracted from documents
- **`document_versions`** - Document version snapshots
- **`knowledge_events`** - Knowledge lifecycle events (freshness, drift, gaps)
- **`standing_queries`** - Saved searches that watch for new matches
- **`chunk_embeddings`** - Chunk-level semantic search vectors
- **`document_groups`** - Hierarchical document organization
- **`wiki_topics`** - Auto-discovered wiki topics from clustering
- **`wiki_topic_members`** - Documents belonging to each topic
- **`wiki_articles`** - Generated wiki articles per topic
- **`wiki_article_sources`** - Source documents used in article generation
- **`wiki_runs`** - Wiki generation run tracking (cost, timing)

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
    ├── ActivityView (default, key '1')
    │   ├── StatusBar (active count, cost, sparkline)
    │   ├── ActivityTable (flat DataTable with section headers: RUNNING/TASKS/DOCS)
    │   ├── ContextPanel (document metadata, tags, word count)
    │   ├── PreviewPanel (rendered markdown, live log stream, or copy mode)
    │   └── KnowledgeGraphPanel (toggle `g`, lazy-loads links/entities/wiki topics)
    └── TaskBrowser (key '2')
        ├── StatusBar (counts by status, filter/group indicators)
        ├── FilterInput (hidden until `/`, debounced text search over title/epic/description)
        ├── DataTable (grouped by status or epic, with section headers)
        └── DetailPanel (description, deps, work log, execution info)
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

## 📚 **Key Subsystems**

### **Wiki System**
Auto-generates a wiki from the knowledge base. The pipeline: extract entities → cluster documents into topics → generate articles via LLM → export as MkDocs site. Key services: `wikify_service.py` (orchestration), `wiki_clustering_service.py` (topic discovery), `wiki_synthesis_service.py` (article generation), `wiki_export_service.py` (MkDocs output), `wiki_privacy_service.py` (PII redaction).

### **Intelligence Layer**
Proactive knowledge health monitoring:
- **Freshness** (`_freshness.py`) — scores documents by age and access patterns, flags stale knowledge
- **Gaps** (`_gaps.py`) — detects coverage holes in the knowledge base
- **Drift** (`_drift.py`, `code_drift.py`) — tracks when code changes invalidate existing documentation
- **Contradictions** (`contradiction_service.py`) — finds conflicting claims across documents
- **Standing queries** (`_watch.py`) — saved searches that notify when new matching docs appear

### **Document Graph**
Documents are connected via auto-linking (`link_service.py`) and entity extraction (`entity_service.py`). The link graph powers related-document suggestions and wiki topic clustering.

### **Backup System**
`backup_service.py` handles compressed daily backups with retention, listing, and point-in-time restore.

### **Version History**
`document_versions` table stores snapshots on edit. `knowledge_events` tracks lifecycle events (creation, updates, freshness changes) for audit and decay analysis.

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