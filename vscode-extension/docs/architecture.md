# EMDX VSCode Extension — Architecture Plan

## Overview

Convert the EMDX Textual TUI into a VSCode extension with webview panels. The extension
wraps the existing `emdx` CLI (via `--json` output) so all business logic stays in Python.
The UI is rebuilt in React inside VSCode webview panels.

## Architecture

```
┌─────────────────────────────────────────────────┐
│ VSCode Extension Host (TypeScript)              │
│                                                 │
│  ┌──────────────┐  ┌────────────────────────┐   │
│  │ EmdxProvider  │  │ Webview Panels (React) │   │
│  │ (CLI bridge)  │  │                        │   │
│  │              │  │ ┌──────────────────┐   │   │
│  │ spawn emdx   │◄─┤ │ Activity View    │   │   │
│  │ --json       │  │ │ (documents)      │   │   │
│  │              │  │ └──────────────────┘   │   │
│  │ parse JSON   │  │ ┌──────────────────┐   │   │
│  │ results      │◄─┤ │ Task View        │   │   │
│  │              │  │ │ (epics/tasks)    │   │   │
│  └──────┬───────┘  │ └──────────────────┘   │   │
│         │          │ ┌──────────────────┐   │   │
│         │          │ │ Q&A View         │   │   │
│         │          │ │ (RAG search)     │   │   │
│         ▼          │ └──────────────────┘   │   │
│  ┌──────────────┐  │ ┌──────────────────┐   │   │
│  │ Tree Views   │  │ │ Document Preview │   │   │
│  │ (sidebar)    │  │ │ (markdown)       │   │   │
│  └──────────────┘  └────────────────────────┘   │
└───────────────────────┬─────────────────────────┘
                        │ subprocess
                        ▼
              ┌──────────────────┐
              │ emdx CLI (Python)│
              │ --json output    │
              │ SQLite + FTS5    │
              └──────────────────┘
```

## Communication: CLI Subprocess (--json)

**Why subprocess over HTTP/LSP/direct-sqlite:**
- Zero new infrastructure — `emdx --json` already exists for 18+ commands
- All business logic (search ranking, embeddings, auto-linking) stays in Python
- No daemon to manage, no port conflicts, no auth
- Same interface agents use — proven and maintained
- Extension just needs to parse JSON, not reimplement logic

**Commands the extension calls:**

| Feature | Command | JSON Shape |
|---------|---------|------------|
| List documents | `emdx find --recent N --json` | `[{id, title, tags, created_at, ...}]` |
| Search docs | `emdx find "query" --json` | `[{id, title, snippet, ...}]` |
| View document | `emdx view ID --json` | `{id, title, content, tags, links}` |
| Save document | `emdx save --title T --tags "t1,t2" --json` | `{id, title}` |
| List tasks | `emdx task list --json` | `[{id, title, status, priority, ...}]` |
| Ready tasks | `emdx task ready --json` | `[{id, title, ...}]` |
| Task status | `emdx task done/active/blocked ID --json` | `{id, status}` |
| Search tags | `emdx tag list --json` | `[{name, count}]` |
| KB status | `emdx status --json` | `{documents, tasks, ...}` |
| Health | `emdx status --health --json` | `{overall_score, metrics}` |
| Q&A | `emdx find --ask "question" --json` | `{answer, sources}` |

## Extension Structure

```
vscode-extension/
├── package.json              # Extension manifest + contributes
├── tsconfig.json             # TypeScript config
├── esbuild.config.mjs        # Build config
├── src/
│   ├── extension.ts          # Activation, command registration
│   ├── emdx-client.ts        # CLI subprocess wrapper
│   ├── types.ts              # TypeScript interfaces (mirror Python TypedDicts)
│   ├── providers/
│   │   ├── documents-tree.ts # Sidebar tree: recent docs, tags
│   │   └── tasks-tree.ts     # Sidebar tree: tasks by status/epic
│   ├── panels/
│   │   ├── activity-panel.ts # Activity/document browser webview
│   │   ├── task-panel.ts     # Task browser webview
│   │   ├── qa-panel.ts       # Q&A webview
│   │   └── preview-panel.ts  # Document preview webview
│   └── commands/
│       ├── save.ts           # Save selection/file to KB
│       ├── search.ts         # Quick search (command palette)
│       └── task-actions.ts   # Mark done/active/blocked
├── webview/
│   ├── src/
│   │   ├── index.tsx         # React entry
│   │   ├── App.tsx           # Router between views
│   │   ├── hooks/
│   │   │   ├── useEmdx.ts    # Message bridge to extension host
│   │   │   └── useTheme.ts   # VSCode theme integration
│   │   ├── views/
│   │   │   ├── ActivityView.tsx
│   │   │   ├── TaskView.tsx
│   │   │   ├── QAView.tsx
│   │   │   └── PreviewView.tsx
│   │   ├── components/
│   │   │   ├── DocumentList.tsx
│   │   │   ├── DocumentPreview.tsx
│   │   │   ├── TaskList.tsx
│   │   │   ├── TaskDetail.tsx
│   │   │   ├── SearchBar.tsx
│   │   │   ├── TagBadge.tsx
│   │   │   ├── StatusBadge.tsx
│   │   │   └── MarkdownRenderer.tsx
│   │   └── styles/
│   │       └── vscode-theme.css  # Uses VSCode CSS variables
│   └── tsconfig.json
├── test/
│   └── emdx-client.test.ts
└── docs/
    └── architecture.md       # This file
```

## TUI → VSCode Mapping

### Screens → Views

| TUI Screen | VSCode Equivalent |
|------------|-------------------|
| Activity Browser | Webview panel + sidebar tree view |
| Task Browser | Webview panel + sidebar tree view |
| Q&A Screen | Webview panel (chat-style) |
| Log Browser | Output channel + webview |
| Command Palette | VSCode Quick Pick (native) |
| Theme Selector | Automatic (follows VSCode theme) |
| Document Preview | Webview panel or editor tab |
| Keybindings Help | Native VSCode keybindings UI |

### Widgets → Components

| Textual Widget | React/VSCode Equivalent |
|---------------|------------------------|
| DataTable | `<table>` with virtual scroll (or VSCode TreeView) |
| RichLog | `<div>` with markdown rendering |
| OptionList | VSCode QuickPick or `<ul>` with keyboard nav |
| TabbedContent | VSCode tab groups or React tabs |
| Static | `<span>` / `<div>` |
| Input | `<vscode-text-field>` (webview-ui-toolkit) |
| Header/Footer | Panel title + status bar items |
| Screen push/pop | React Router or state-based view switching |

### Keybindings

| TUI Key | VSCode Command |
|---------|---------------|
| `1/2/3` | `emdx.showActivity` / `emdx.showTasks` / `emdx.showQA` |
| `j/k` | List navigation (handled in webview) |
| `Enter` | Open document / expand task |
| `Ctrl+K` | VSCode Command Palette with `emdx` prefix |
| `r` | `emdx.refresh` |
| `d/a/b` (tasks) | `emdx.taskDone` / `emdx.taskActive` / `emdx.taskBlocked` |
| `z` | Toggle zoom (webview panel maximize) |
| `?` | `emdx.showKeybindings` |

## VSCode Contributions (package.json)

### Views Container (Sidebar)
```json
{
  "viewsContainers": {
    "activitybar": [{
      "id": "emdx",
      "title": "EMDX",
      "icon": "resources/emdx-icon.svg"
    }]
  },
  "views": {
    "emdx": [
      { "id": "emdx.recentDocs", "name": "Recent Documents" },
      { "id": "emdx.tasks", "name": "Tasks" },
      { "id": "emdx.tags", "name": "Tags" }
    ]
  }
}
```

### Commands
```json
{
  "commands": [
    { "command": "emdx.showActivity", "title": "EMDX: Documents" },
    { "command": "emdx.showTasks", "title": "EMDX: Tasks" },
    { "command": "emdx.showQA", "title": "EMDX: Ask" },
    { "command": "emdx.search", "title": "EMDX: Search Knowledge Base" },
    { "command": "emdx.saveSelection", "title": "EMDX: Save Selection to KB" },
    { "command": "emdx.saveFile", "title": "EMDX: Save File to KB" },
    { "command": "emdx.refresh", "title": "EMDX: Refresh" },
    { "command": "emdx.taskDone", "title": "EMDX: Mark Task Done" },
    { "command": "emdx.taskActive", "title": "EMDX: Mark Task Active" },
    { "command": "emdx.taskBlocked", "title": "EMDX: Mark Task Blocked" },
    { "command": "emdx.status", "title": "EMDX: Show Status" },
    { "command": "emdx.viewDocument", "title": "EMDX: View Document" }
  ]
}
```

### Keybindings
```json
{
  "keybindings": [
    { "command": "emdx.search", "key": "ctrl+shift+k", "when": "emdx.active" },
    { "command": "emdx.showActivity", "key": "ctrl+shift+1", "when": "emdx.active" },
    { "command": "emdx.showTasks", "key": "ctrl+shift+2", "when": "emdx.active" },
    { "command": "emdx.showQA", "key": "ctrl+shift+3", "when": "emdx.active" }
  ]
}
```

## Message Protocol (Extension ↔ Webview)

```typescript
// Extension → Webview
type ExtensionMessage =
  | { type: 'documents'; data: Document[] }
  | { type: 'document'; data: DocumentDetail }
  | { type: 'tasks'; data: Task[] }
  | { type: 'searchResults'; data: SearchResult[] }
  | { type: 'qaAnswer'; data: { answer: string; sources: Source[] } }
  | { type: 'status'; data: KBStatus }
  | { type: 'error'; message: string }
  | { type: 'loading'; loading: boolean }

// Webview → Extension
type WebviewMessage =
  | { type: 'fetchDocuments'; limit?: number }
  | { type: 'fetchDocument'; id: number }
  | { type: 'searchDocuments'; query: string }
  | { type: 'fetchTasks'; status?: string; epicKey?: string }
  | { type: 'updateTaskStatus'; id: number; status: string }
  | { type: 'askQuestion'; question: string }
  | { type: 'saveDocument'; title: string; content: string; tags: string[] }
  | { type: 'refresh' }
  | { type: 'openExternal'; url: string }
```

## Theming

The webview uses VSCode CSS variables for automatic theme matching:

```css
body {
  color: var(--vscode-foreground);
  background: var(--vscode-editor-background);
  font-family: var(--vscode-font-family);
  font-size: var(--vscode-font-size);
}

.panel { background: var(--vscode-panel-background); }
.badge-success { color: var(--vscode-testing-iconPassed); }
.badge-error { color: var(--vscode-testing-iconFailed); }
.badge-warning { color: var(--vscode-editorWarning-foreground); }
```

No custom themes needed — follows whatever VSCode theme the user has.

## Implementation Phases

### Phase 1: Core Infrastructure
- Extension activation, CLI bridge (`emdx-client.ts`)
- Verify `emdx` is installed and accessible
- Basic error handling and timeout management

### Phase 2: Sidebar Tree Views
- Recent documents tree (native VSCode TreeView — fast, no webview overhead)
- Tasks tree grouped by status
- Tags tree with document counts

### Phase 3: Activity Panel (Webview)
- Document list with search
- Document preview with markdown rendering
- Tag filtering

### Phase 4: Task Panel (Webview)
- Task list grouped by status/epic
- Task detail view
- Status actions (done/active/blocked)
- Dependency visualization

### Phase 5: Q&A Panel (Webview)
- Question input
- Streaming answer display
- Source document links

### Phase 6: Integration Commands
- Save selection to KB
- Search from command palette
- Status bar item with KB stats

## Dependencies

### Extension Host
- `@types/vscode` — VSCode API types
- `esbuild` — Bundle for production

### Webview
- `react`, `react-dom` — UI framework
- `react-markdown` — Markdown rendering
- `@vscode/webview-ui-toolkit` — Native-looking form controls
- `esbuild` — Bundle webview code

### Dev
- `typescript` — Both host and webview
- `@vscode/test-electron` — Integration testing
- `@vscode/vsce` — Packaging

## Build & Development

```bash
# Install
cd vscode-extension && npm install

# Development (watch mode)
npm run watch          # Rebuilds on change

# Build for production
npm run build          # Bundles extension + webview

# Package
npx vsce package       # Creates .vsix

# Test
npm test               # Runs extension tests
```
