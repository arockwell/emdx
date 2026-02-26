# EMDX VSCode Extension

Browse and manage your EMDX knowledge base from VSCode.

## Prerequisites

- **Node.js 18+** and **npm**
- **emdx CLI** installed and accessible (either `emdx` on PATH or `poetry run emdx` from the project dir)
- **VSCode 1.85+**

## Quick Start

```bash
# 1. Install dependencies
cd vscode-extension
npm install

# 2. Build the extension + webviews
npm run build

# 3. Open in VSCode for development
code .
```

Then press **F5** to launch the Extension Development Host with the extension loaded.

## Development

### Watch Mode (Recommended)

```bash
npm run watch
```

This rebuilds both the extension host and webview bundles on every file change. In VSCode:

1. Press **F5** to launch the Extension Development Host
2. Edit files — esbuild rebuilds in milliseconds
3. Press **Ctrl+R** in the dev host window to reload the extension
4. For webview changes, close and reopen the panel (or run "Developer: Reload Webviews")

### Debug Webviews

In the Extension Development Host, open the Command Palette and run:
```
Developer: Open Webview Developer Tools
```
This opens Chrome DevTools for the webview where you can inspect elements and debug React.

### Build for Production

```bash
npm run build
```

This creates minified bundles without sourcemaps in `dist/`.

## Install as VSIX

```bash
# Package into a .vsix file
npx vsce package

# Install the .vsix in VSCode
code --install-extension emdx-0.1.0.vsix
```

Or from VSCode: **Extensions** > **...** menu > **Install from VSIX...**

## Configuration

After installing, configure the extension in VSCode Settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `emdx.executablePath` | `"emdx"` | Path to the emdx CLI. Use `"poetry run emdx"` if installed via Poetry. |
| `emdx.recentDocumentLimit` | `50` | Number of recent documents shown in Activity view |
| `emdx.autoRefreshInterval` | `30` | Auto-refresh interval in seconds (0 to disable) |

## Features

### Sidebar (Activity Bar)

Click the EMDX icon in the Activity Bar to see:

- **Recent Documents** — tree view of your latest KB documents
- **Tasks** — tasks grouped by status (Ready, Active, Blocked, Done)
- **Tags** — all tags with document counts

### Webview Panels

| Command | Shortcut | Description |
|---------|----------|-------------|
| `EMDX: Documents` | `Ctrl+Shift+1` | Document browser with search and preview |
| `EMDX: Tasks` | `Ctrl+Shift+2` | Task browser with status actions |
| `EMDX: Ask` | `Ctrl+Shift+3` | RAG Q&A over your knowledge base |
| `EMDX: Search Knowledge Base` | `Ctrl+Shift+K` | Quick search via Command Palette |

### Editor Integration

- **Right-click** selected text > **EMDX: Save Selection to KB** — saves the selection as a new document
- **Command Palette** > **EMDX: Save File to KB** — saves the current file

### Task Management

From the Tasks tree view or panel, you can:
- Mark tasks as Done / Active / Blocked
- View task details, description, and dependencies
- Filter by status or epic

### Status Bar

The bottom status bar shows KB stats (document count, active/open tasks). Click it for full status.

## Architecture

```
VSCode Extension Host (TypeScript)
  │
  ├── emdx-client.ts ──── spawns ──── emdx CLI (--json)
  │                                      │
  ├── Tree Providers (sidebar)           SQLite + FTS5
  │     ├── Documents                    Python business logic
  │     ├── Tasks                        Semantic search
  │     └── Tags
  │
  └── Webview Panels (React)
        ├── Activity (documents)
        ├── Tasks
        └── Q&A
```

The extension calls the existing `emdx` CLI with `--json` flags. All business logic
(hybrid search, embeddings, auto-linking, task dependencies) stays in Python. The
extension is a thin TypeScript UI layer.

See [docs/architecture.md](docs/architecture.md) for full details.

## Project Structure

```
vscode-extension/
├── package.json              # Extension manifest + contributes
├── tsconfig.json             # Extension host TypeScript config
├── esbuild.config.mjs        # Dual-target build (Node + browser)
├── src/                      # Extension host (runs in Node.js)
│   ├── extension.ts          # Entry point, commands, status bar
│   ├── emdx-client.ts        # CLI subprocess bridge
│   ├── types.ts              # TypeScript interfaces
│   ├── providers/            # Sidebar tree views
│   └── panels/               # Webview panel managers
├── webview/                  # Webview UI (runs in browser iframe)
│   ├── tsconfig.json         # Webview TypeScript config (DOM libs)
│   └── src/
│       ├── activity/         # Document browser React components
│       ├── tasks/            # Task browser React components
│       ├── qa/               # Q&A React components
│       ├── hooks/            # VSCode API bridge hook
│       ├── styles/           # CSS with VSCode theme variables
│       └── types.ts          # Shared types (mirrored from src/)
├── resources/                # Icons
└── docs/                     # Architecture documentation
```

## Troubleshooting

### "emdx not found"

Set `emdx.executablePath` in VSCode Settings to the full path:
```json
{
  "emdx.executablePath": "/home/you/.local/bin/emdx"
}
```

Or if using Poetry:
```json
{
  "emdx.executablePath": "poetry run emdx"
}
```

### Extension loads but no data appears

1. Check the **Output** panel (View > Output) and select **EMDX** from the dropdown
2. Verify emdx works from terminal: `emdx status --json`
3. Check the working directory — emdx needs to find its database at `~/.config/emdx/knowledge.db`

### Webview is blank

1. Open **Developer: Open Webview Developer Tools** in the dev host
2. Check the console for JavaScript errors
3. Verify the build ran successfully: `npm run build`
