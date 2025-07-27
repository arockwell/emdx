# EMDX Architecture Overview

## 🏗️ **System Design**

EMDX is a modular, SQLite-based knowledge management system designed for scalability, maintainability, and user experience.

### **Core Principles**
- **Modular Architecture** - Clean separation of concerns across layers
- **Event-Driven Design** - Reactive components with minimal coupling
- **Performance First** - Optimized for real-time responsiveness
- **User-Centric** - Multiple interfaces (CLI, TUI, API) for different workflows

## 📦 **Component Architecture**

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interfaces                          │
├─────────────────┬─────────────────┬─────────────────────────┤
│   CLI Commands  │   TUI Browser   │    Future: Web API      │
│                 │                 │                         │
│ • save/find     │ • Document      │ • REST endpoints        │
│ • tag/search    │   browser       │ • GraphQL API          │
│ • exec/logs     │ • Log browser   │ • WebSocket events      │
│ • lifecycle     │ • File browser  │                         │
└─────────────────┴─────────────────┴─────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────────┐
│                   Service Layer                             │
├─────────────────────────────────────────────────────────────┤
│ Business Logic & Coordination                               │
│                                                             │
│ • DocumentService    • ExecutionService                     │
│ • TagService         • LogStreamService                     │
│ • SearchService      • HealthMonitor                        │
│ • LifecycleTracker   • AutoTagger                          │
└─────────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────────┐
│                    Data Layer                               │
├─────────────────────────────────────────────────────────────┤
│ Storage & Persistence                                       │
│                                                             │
│ • SQLite Database    • FTS5 Search                         │
│ • Document Storage   • Tag Management                       │
│ • Execution Logs     • Migration System                     │
│ • Git Integration    • File System                          │
└─────────────────────────────────────────────────────────────┘
                           │
┌─────────────────────────────────────────────────────────────┐
│                 External Systems                            │
├─────────────────────────────────────────────────────────────┤
│ • Git Repositories   • Claude Code Integration             │
│ • File System        • GitHub API (Gists)                  │
│ • Process Execution   • External Editors                    │
└─────────────────────────────────────────────────────────────┘
```

## 🔄 **Event-Driven Architecture**

### **Core Event Patterns**

```python
# Document Events
DocumentCreated(doc_id, title, content)
DocumentUpdated(doc_id, changes)
DocumentTagged(doc_id, tags)

# Execution Events  
ExecutionStarted(exec_id, command, doc_id)
ExecutionCompleted(exec_id, exit_code, duration)
LogContentAdded(exec_id, new_content)

# System Events
SearchIndexUpdated(doc_ids)
HealthCheckCompleted(status, metrics)
```

### **Event Flow Example: Log Streaming**

```
1. File changes → OS notification
2. FileWatcher → LogStream.on_file_changed()
3. LogStream → reads new content
4. LogStream → notifies subscribers
5. LogBrowser → updates UI display
6. Multiple subscribers can listen simultaneously
```

## 🗃️ **Database Architecture**

### **Core Tables**
- **`documents`** - Document metadata, content, and indexing
- **`tags`** - Tag definitions with emoji and aliases  
- **`document_tags`** - Many-to-many document-tag relationships
- **`executions`** - Execution tracking and lifecycle
- **`documents_fts`** - Full-text search virtual table

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
    └── FileBrowser (press 'f')
        ├── FileTree
        └── FilePreview
```

### **Key Patterns**
- **Widget Composition** - Complex UIs built from simple, reusable widgets
- **Event Bubbling** - Key presses bubble up through widget hierarchy
- **Reactive Updates** - UI automatically updates when data changes
- **Modal Editing** - Vim-like editing modes for power users

## 🔧 **Service Layer Design**

### **Service Responsibilities**

#### **DocumentService**
- CRUD operations for documents
- Content processing and normalization
- Search coordination with FTS5
- Git integration for project detection

#### **ExecutionService** 
- Process lifecycle management
- Log file coordination
- Status tracking and health monitoring
- Integration with Claude Code wrapper

#### **LogStreamService** (New!)
- Event-driven file watching
- Real-time content streaming  
- Subscription management
- Cross-platform file monitoring

#### **TagService**
- Tag CRUD with emoji aliases
- Auto-tagging based on content patterns
- Tag-based search and filtering
- Usage analytics and optimization

## 📊 **Data Flow Patterns**

### **Document Lifecycle**
```
1. Content Input → DocumentService.save()
2. Auto-tagging → TagService.analyze_content()
3. FTS Indexing → SearchService.index_document()
4. Git Detection → DocumentService.detect_project()
5. UI Update → EventBus.document_created()
```

### **Execution Lifecycle**
```
1. Command Start → ExecutionService.start()
2. Log Creation → LogStreamService.create_stream()
3. Real-time Updates → LogStream.subscribe()
4. Health Monitoring → ExecutionMonitor.check_health()
5. Completion → ExecutionService.complete()
```

## 🎯 **Performance Architecture**

### **Optimization Strategies**
- **Lazy Loading** - Load documents/logs only when needed
- **Event-Driven Updates** - No polling, only reactive changes
- **FTS5 Indexing** - Fast search across large document collections
- **Connection Pooling** - Efficient SQLite connection management
- **Incremental Operations** - Update only what changed

### **Scalability Considerations**
- **SQLite WAL Mode** - Concurrent reads during writes
- **Chunked Processing** - Handle large files efficiently  
- **Memory Management** - Stream processing for large logs
- **Background Tasks** - Non-blocking operations for UI responsiveness

## 🔐 **Security & Reliability**

### **Data Security**
- **Local-first** - All data stored locally, no cloud dependencies
- **Process Isolation** - Execution monitoring without interference
- **Safe Parsing** - Robust handling of malformed log files
- **Input Validation** - SQL injection prevention

### **Error Handling**
- **Graceful Degradation** - Fallback modes when components fail
- **Comprehensive Logging** - Debug information for troubleshooting
- **Resource Cleanup** - Automatic cleanup of streams and connections
- **Transaction Safety** - Database consistency during failures

## 🚀 **Extension Points**

### **Adding New UI Components**
1. Extend `Widget` base class
2. Implement compose() method for layout
3. Add to BrowserContainer routing
4. Define keybindings and actions

### **Adding New Services**
1. Create service class with clear interface
2. Add to service layer dependency injection
3. Implement event publishing/subscription
4. Add comprehensive error handling

### **Adding New Data Types**
1. Create database migration
2. Add data models in `models/` directory
3. Implement service layer operations
4. Add UI components for management

This architecture enables rapid development while maintaining code quality and user experience. The modular design allows components to be modified, tested, and deployed independently.