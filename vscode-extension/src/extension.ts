import * as vscode from "vscode";
import { EmdxClient } from "./emdx-client";
import { DocumentsTreeProvider } from "./providers/documents-tree";
import { TasksTreeProvider } from "./providers/tasks-tree";
import { TagsTreeProvider } from "./providers/tags-tree";
import { ActivityPanel } from "./panels/activity-panel";
import { TaskPanel } from "./panels/task-panel";
import { QAPanel } from "./panels/qa-panel";
import type { SearchResult, StatusData, Task } from "./types";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let autoRefreshTimer: ReturnType<typeof setInterval> | undefined;
let statusBarItem: vscode.StatusBarItem | undefined;

// ---------------------------------------------------------------------------
// Activation
// ---------------------------------------------------------------------------

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const config = vscode.workspace.getConfiguration("emdx");
  const client = new EmdxClient();

  // Verify emdx is reachable
  const available = await client.isAvailable();
  if (!available) {
    vscode.window.showWarningMessage(
      "emdx CLI not found. Install emdx or set emdx.executablePath in settings."
    );
  }

  // Set context key so keybindings with `when: emdx.active` work
  await vscode.commands.executeCommand("setContext", "emdx.active", available);

  // ------------------------------------------------------------------
  // Sidebar tree views
  // ------------------------------------------------------------------

  const docsTree = new DocumentsTreeProvider(client);
  const tasksTree = new TasksTreeProvider(client);
  const tagsTree = new TagsTreeProvider(client);

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("emdx.recentDocs", docsTree),
    vscode.window.registerTreeDataProvider("emdx.tasks", tasksTree),
    vscode.window.registerTreeDataProvider("emdx.tags", tagsTree),
  );

  // ------------------------------------------------------------------
  // Webview panel commands
  // ------------------------------------------------------------------

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.showActivity", () => {
      ActivityPanel.createOrShow(context.extensionUri, client);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.showTasks", () => {
      TaskPanel.createOrShow(context.extensionUri, client);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.showQA", () => {
      QAPanel.createOrShow(context.extensionUri, client);
    }),
  );

  // ------------------------------------------------------------------
  // Search (QuickPick with debounced results)
  // ------------------------------------------------------------------

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.search", () => {
      showSearchQuickPick(client, context);
    }),
  );

  // ------------------------------------------------------------------
  // Filter by tag
  // ------------------------------------------------------------------

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.filterByTag", async (tagName?: string) => {
      if (!tagName) {
        return;
      }
      try {
        const docs = await client.findByTag(tagName);
        if (docs.length === 0) {
          vscode.window.showInformationMessage(`No documents tagged "${tagName}"`);
          return;
        }
        const items = docs.map((d) => ({
          label: `$(file-text) ${d.title}`,
          description: `#${d.id}`,
          docId: d.id,
        }));
        const selected = await vscode.window.showQuickPick(items, {
          placeHolder: `Documents tagged "${tagName}"`,
        });
        if (selected && selected.docId > 0) {
          await vscode.commands.executeCommand("emdx.viewDocument", selected.docId);
        }
      } catch (err) {
        vscode.window.showErrorMessage(`Failed to filter by tag: ${String(err)}`);
      }
    }),
  );

  // ------------------------------------------------------------------
  // Save commands
  // ------------------------------------------------------------------

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.saveSelection", () => {
      saveSelectionToKB(client);
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.saveFile", () => {
      saveFileToKB(client);
    }),
  );

  // ------------------------------------------------------------------
  // Refresh
  // ------------------------------------------------------------------

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.refresh", () => {
      client.invalidateCache();
      docsTree.refresh();
      tasksTree.refresh();
      tagsTree.refresh();
      updateStatusBar(client);
    }),
  );

  // ------------------------------------------------------------------
  // Task status commands
  // ------------------------------------------------------------------

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.taskDone", () => {
      changeTaskStatus(client, tasksTree, "done");
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.taskActive", () => {
      changeTaskStatus(client, tasksTree, "active");
    }),
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.taskBlocked", () => {
      changeTaskStatus(client, tasksTree, "blocked");
    }),
  );

  // ------------------------------------------------------------------
  // Status
  // ------------------------------------------------------------------

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.status", async () => {
      try {
        const status = await client.getStatus();
        const msg = statusSummary(status);
        vscode.window.showInformationMessage(msg);
      } catch (err) {
        vscode.window.showErrorMessage(`Failed to fetch status: ${String(err)}`);
      }
    }),
  );

  // ------------------------------------------------------------------
  // View document
  // ------------------------------------------------------------------

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.viewDocument", async (docId?: number) => {
      const id = docId ?? await promptForDocumentId();
      if (id === undefined) {
        return;
      }
      try {
        const doc = await client.getDocument(id);
        const panel = vscode.window.createWebviewPanel(
          "emdx.documentPreview",
          `EMDX: ${doc.title}`,
          vscode.ViewColumn.One,
          { enableScripts: false },
        );
        panel.webview.html = buildDocumentPreviewHtml(doc.title, doc.content, doc.tags);
      } catch (err) {
        vscode.window.showErrorMessage(`Failed to load document: ${String(err)}`);
      }
    }),
  );

  // ------------------------------------------------------------------
  // View task
  // ------------------------------------------------------------------

  context.subscriptions.push(
    vscode.commands.registerCommand("emdx.viewTask", async (task?: Task) => {
      if (!task) {
        return;
      }
      const panel = vscode.window.createWebviewPanel(
        "emdx.taskPreview",
        `Task #${task.id}: ${task.title}`,
        vscode.ViewColumn.One,
        { enableScripts: false },
      );
      // Show immediately with description, then enrich with work log
      panel.webview.html = buildTaskPreviewHtml(task, []);
      try {
        const log = await client.getTaskLog(task.id);
        panel.webview.html = buildTaskPreviewHtml(task, log);
      } catch {
        // Work log fetch failed — keep showing description only
      }
    }),
  );

  // ------------------------------------------------------------------
  // Auto-refresh timer
  // ------------------------------------------------------------------

  const refreshInterval = config.get<number>("autoRefreshInterval", 30);
  if (refreshInterval > 0) {
    autoRefreshTimer = setInterval(() => {
      docsTree.refresh();
      tasksTree.refresh();
      tagsTree.refresh();
      updateStatusBar(client);
    }, refreshInterval * 1000);
  }

  // Reconfigure timer when settings change
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration("emdx.autoRefreshInterval")) {
        if (autoRefreshTimer !== undefined) {
          clearInterval(autoRefreshTimer);
          autoRefreshTimer = undefined;
        }
        const newInterval = vscode.workspace
          .getConfiguration("emdx")
          .get<number>("autoRefreshInterval", 30);
        if (newInterval > 0) {
          autoRefreshTimer = setInterval(() => {
            docsTree.refresh();
            tasksTree.refresh();
            tagsTree.refresh();
            updateStatusBar(client);
          }, newInterval * 1000);
        }
      }
    }),
  );

  // ------------------------------------------------------------------
  // Status bar item
  // ------------------------------------------------------------------

  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 0);
  statusBarItem.command = "emdx.status";
  statusBarItem.tooltip = "EMDX Knowledge Base";
  context.subscriptions.push(statusBarItem);

  // Initial update
  if (available) {
    updateStatusBar(client);
  } else {
    statusBarItem.text = "$(database) EMDX: unavailable";
    statusBarItem.show();
  }
}

// ---------------------------------------------------------------------------
// Deactivation
// ---------------------------------------------------------------------------

export function deactivate(): void {
  if (autoRefreshTimer !== undefined) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = undefined;
  }
  if (statusBarItem) {
    statusBarItem.dispose();
    statusBarItem = undefined;
  }
}

// ---------------------------------------------------------------------------
// Search QuickPick
// ---------------------------------------------------------------------------

async function showSearchQuickPick(
  client: EmdxClient,
  context: vscode.ExtensionContext,
): Promise<void> {
  const quickPick = vscode.window.createQuickPick<SearchQuickPickItem>();
  quickPick.placeholder = "Search EMDX knowledge base...";
  quickPick.matchOnDescription = true;
  quickPick.matchOnDetail = true;

  let debounceTimer: ReturnType<typeof setTimeout> | undefined;

  quickPick.onDidChangeValue((value) => {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    if (!value.trim()) {
      quickPick.items = [];
      return;
    }
    quickPick.busy = true;
    debounceTimer = setTimeout(async () => {
      try {
        const results = await client.searchDocuments(value);
        quickPick.items = results.map((r) => ({
          label: `$(file-text) ${r.title}`,
          description: `#${r.id}`,
          detail: r.snippet,
          docId: r.id,
        }));
      } catch {
        quickPick.items = [
          { label: "$(error) Search failed", description: "", detail: "", docId: -1 },
        ];
      } finally {
        quickPick.busy = false;
      }
    }, 300);
  });

  quickPick.onDidAccept(async () => {
    const selected = quickPick.selectedItems[0];
    if (!selected || selected.docId < 0) {
      quickPick.hide();
      return;
    }
    quickPick.hide();
    await vscode.commands.executeCommand("emdx.viewDocument", selected.docId);
  });

  quickPick.onDidHide(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    quickPick.dispose();
  });

  context.subscriptions.push(quickPick);
  quickPick.show();
}

interface SearchQuickPickItem extends vscode.QuickPickItem {
  docId: number;
}

// ---------------------------------------------------------------------------
// Save commands
// ---------------------------------------------------------------------------

async function saveSelectionToKB(client: EmdxClient): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("No active editor.");
    return;
  }

  const selection = editor.selection;
  if (selection.isEmpty) {
    vscode.window.showWarningMessage("No text selected.");
    return;
  }

  const text = editor.document.getText(selection);

  const title = await vscode.window.showInputBox({
    prompt: "Document title",
    placeHolder: "Enter a title for this knowledge base entry",
  });
  if (!title) {
    return;
  }

  const tagsInput = await vscode.window.showInputBox({
    prompt: "Tags (comma-separated)",
    placeHolder: "e.g. notes, analysis, active",
  });
  const tags = tagsInput
    ? tagsInput
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
    : [];

  try {
    const result = await client.saveDocument(title, text, tags);
    vscode.window.showInformationMessage(`Saved as #${result.id}: ${title}`);
  } catch (err) {
    vscode.window.showErrorMessage(`Failed to save: ${String(err)}`);
  }
}

async function saveFileToKB(client: EmdxClient): Promise<void> {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showWarningMessage("No active editor.");
    return;
  }

  const content = editor.document.getText();
  const fileName = editor.document.fileName;
  const defaultTitle = fileName.split(/[\\/]/).pop() ?? "Untitled";

  const title = await vscode.window.showInputBox({
    prompt: "Document title",
    value: defaultTitle,
    placeHolder: "Enter a title for this knowledge base entry",
  });
  if (!title) {
    return;
  }

  const tagsInput = await vscode.window.showInputBox({
    prompt: "Tags (comma-separated)",
    placeHolder: "e.g. notes, reference, code",
  });
  const tags = tagsInput
    ? tagsInput
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
    : [];

  try {
    const result = await client.saveDocument(title, content, tags);
    vscode.window.showInformationMessage(`Saved as #${result.id}: ${result.title}`);
  } catch (err) {
    vscode.window.showErrorMessage(`Failed to save: ${String(err)}`);
  }
}

// ---------------------------------------------------------------------------
// Task status actions
// ---------------------------------------------------------------------------

async function changeTaskStatus(
  client: EmdxClient,
  tasksTree: TasksTreeProvider,
  status: "done" | "active" | "blocked",
): Promise<void> {
  try {
    const tasks = await client.listTasks();
    // Filter to tasks that can transition to the target status
    const eligible = tasks.filter((t: Task) => {
      if (status === "done") return t.status === "active" || t.status === "open";
      if (status === "active") return t.status === "open" || t.status === "blocked";
      if (status === "blocked") return t.status === "open" || t.status === "active";
      return false;
    });

    if (eligible.length === 0) {
      vscode.window.showInformationMessage(`No tasks eligible to mark as ${status}.`);
      return;
    }

    const items = eligible.map((t: Task) => ({
      label: `#${t.id}: ${t.title}`,
      description: t.status,
      taskId: t.id,
    }));

    const selected = await vscode.window.showQuickPick(items, {
      placeHolder: `Select a task to mark as ${status}`,
    });

    if (!selected) {
      return;
    }

    await client.updateTaskStatus(selected.taskId, status);
    vscode.window.showInformationMessage(`Task #${selected.taskId} marked as ${status}.`);
    tasksTree.refresh();
  } catch (err) {
    vscode.window.showErrorMessage(`Failed to update task: ${String(err)}`);
  }
}

// ---------------------------------------------------------------------------
// Status bar
// ---------------------------------------------------------------------------

function statusSummary(status: StatusData): string {
  const activeCount = status.active.length;
  const recentCount = status.recent.length;
  const failedCount = status.failed.length;
  const parts: string[] = [];
  if (activeCount > 0) {
    parts.push(`${activeCount} active`);
  }
  if (recentCount > 0) {
    parts.push(`${recentCount} recent`);
  }
  if (failedCount > 0) {
    parts.push(`${failedCount} failed`);
  }
  return parts.length > 0
    ? `Delegates: ${parts.join(", ")}`
    : "No active delegates";
}

async function updateStatusBar(client: EmdxClient): Promise<void> {
  if (!statusBarItem) {
    return;
  }
  try {
    const status = await client.getStatus();
    const activeCount = status.active.length;
    const failedCount = status.failed.length;
    const parts: string[] = [];
    if (activeCount > 0) {
      parts.push(`${activeCount} active`);
    }
    if (failedCount > 0) {
      parts.push(`${failedCount} failed`);
    }
    const suffix = parts.length > 0 ? `: ${parts.join(", ")}` : "";
    statusBarItem.text = `$(database) EMDX${suffix}`;
    statusBarItem.show();
  } catch {
    statusBarItem.text = "$(database) EMDX";
    statusBarItem.show();
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function promptForDocumentId(): Promise<number | undefined> {
  const input = await vscode.window.showInputBox({
    prompt: "Enter document ID",
    placeHolder: "e.g. 42",
    validateInput: (value) => {
      const n = Number(value);
      if (!Number.isInteger(n) || n < 1) {
        return "Enter a positive integer document ID.";
      }
      return undefined;
    },
  });
  if (!input) {
    return undefined;
  }
  return Number(input);
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildDocumentPreviewHtml(title: string, content: string, tags: string[]): string {
  const tagsHtml = tags.length
    ? `<p style="margin-bottom:12px;">${tags.map((t) => `<code>${escapeHtml(t)}</code>`).join(" ")}</p>`
    : "";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>${escapeHtml(title)}</title>
  <style>
    body {
      font-family: var(--vscode-font-family, sans-serif);
      font-size: var(--vscode-font-size, 14px);
      color: var(--vscode-foreground);
      background: var(--vscode-editor-background);
      padding: 16px 24px;
      line-height: 1.6;
    }
    h1 {
      font-size: 1.4em;
      margin-bottom: 4px;
      color: var(--vscode-editor-foreground);
    }
    code {
      background: var(--vscode-textCodeBlock-background, rgba(128,128,128,0.15));
      padding: 2px 6px;
      border-radius: 3px;
      font-size: 0.85em;
    }
    pre {
      background: var(--vscode-textCodeBlock-background, rgba(128,128,128,0.15));
      padding: 12px;
      border-radius: 4px;
      overflow-x: auto;
    }
    pre code {
      background: none;
      padding: 0;
    }
  </style>
</head>
<body>
  <h1>${escapeHtml(title)}</h1>
  ${tagsHtml}
  <hr />
  <pre><code>${escapeHtml(content)}</code></pre>
</body>
</html>`;
}

function buildTaskPreviewHtml(
  task: Task,
  log: Array<{ timestamp: string; message: string }>
): string {
  const statusIcons: Record<string, string> = {
    open: "\u25CB",
    active: "\u25CF",
    blocked: "\u26A0",
    done: "\u2713",
    failed: "\u2717",
    wontdo: "\u2298",
  };
  const icon = statusIcons[task.status] ?? "\u25CB";

  const meta = [
    `<strong>Status:</strong> ${icon} ${escapeHtml(task.status)}`,
    `<strong>Priority:</strong> ${task.priority}`,
    task.epic_key ? `<strong>Epic:</strong> ${escapeHtml(task.epic_key)}` : null,
    `<strong>Created:</strong> ${escapeHtml(task.created_at)}`,
    `<strong>Updated:</strong> ${escapeHtml(task.updated_at)}`,
    task.completed_at ? `<strong>Completed:</strong> ${escapeHtml(task.completed_at)}` : null,
  ]
    .filter(Boolean)
    .map((m) => `<li>${m}</li>`)
    .join("\n");

  const description = task.description
    ? `<h3>Description</h3>\n<pre><code>${escapeHtml(task.description)}</code></pre>`
    : `<p style="color: var(--vscode-disabledForeground);">No description</p>`;

  const logHtml = log.length > 0
    ? `<h3>Work Log</h3>\n<div class="work-log">${log.map((entry) =>
        `<div class="log-entry"><span class="log-ts">${escapeHtml(entry.timestamp)}</span> ${escapeHtml(entry.message)}</div>`
      ).join("\n")}</div>`
    : "";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Task #${task.id}</title>
  <style>
    body {
      font-family: var(--vscode-font-family, sans-serif);
      font-size: var(--vscode-font-size, 14px);
      color: var(--vscode-foreground);
      background: var(--vscode-editor-background);
      padding: 16px 24px;
      line-height: 1.6;
    }
    h1 { font-size: 1.4em; margin-bottom: 4px; }
    h3 { font-size: 1.1em; margin: 16px 0 8px; }
    ul { list-style: none; padding: 0; }
    li { margin-bottom: 4px; }
    pre {
      background: var(--vscode-textCodeBlock-background, rgba(128,128,128,0.15));
      padding: 12px;
      border-radius: 4px;
      overflow-x: auto;
      white-space: pre-wrap;
    }
    pre code { background: none; padding: 0; }
    .work-log { margin-top: 8px; }
    .log-entry {
      padding: 6px 0;
      border-bottom: 1px solid var(--vscode-widget-border, rgba(128,128,128,0.2));
    }
    .log-ts {
      color: var(--vscode-descriptionForeground);
      font-size: 0.85em;
      margin-right: 8px;
    }
  </style>
</head>
<body>
  <h1>#${task.id}: ${escapeHtml(task.title)}</h1>
  <ul>${meta}</ul>
  <hr />
  ${description}
  ${logHtml}
</body>
</html>`;
}
