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
let clientInstance: EmdxClient | undefined;

// ---------------------------------------------------------------------------
// Activation
// ---------------------------------------------------------------------------

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const config = vscode.workspace.getConfiguration("emdx");
  const client = new EmdxClient();
  clientInstance = client;

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
          { enableScripts: true },
        );
        panel.webview.html = buildDocumentPreviewHtml(doc.title, doc.content, doc.tags);
        panel.webview.onDidReceiveMessage((msg: { type: string; url: string }) => {
          if (msg.type === "openLink") {
            vscode.env.openExternal(vscode.Uri.parse(msg.url));
          }
        });
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
        { enableScripts: true },
      );
      panel.webview.onDidReceiveMessage((msg: { type: string; url: string }) => {
        if (msg.type === "openLink") {
          vscode.env.openExternal(vscode.Uri.parse(msg.url));
        }
      });
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
  if (clientInstance) {
    clientInstance.dispose();
    clientInstance = undefined;
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
    ? `Agents: ${parts.join(", ")}`
    : "No active agents";
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

/** Simple markdown to HTML converter for static webviews. */
function markdownToHtml(md: string): string {
  let html = "";
  const lines = md.split("\n");
  let inCodeBlock = false;
  let codeBlockContent = "";
  let inList = false;
  let listType: "ul" | "ol" = "ul";
  let inTable = false;
  let tableHeaderDone = false;

  function closeOpenBlocks(): void {
    if (inList) { html += listType === "ul" ? "</ul>\n" : "</ol>\n"; inList = false; }
    if (inTable) { html += "</tbody></table>\n"; inTable = false; tableHeaderDone = false; }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Fenced code blocks
    if (line.trimStart().startsWith("```")) {
      if (inCodeBlock) {
        html += `<pre><code>${escapeHtml(codeBlockContent.trimEnd())}</code></pre>\n`;
        codeBlockContent = "";
        inCodeBlock = false;
      } else {
        closeOpenBlocks();
        inCodeBlock = true;
      }
      continue;
    }
    if (inCodeBlock) {
      codeBlockContent += line + "\n";
      continue;
    }

    // Table separator row (e.g. |---|---|)
    if (/^\s*\|[\s:-]+\|[\s:|-]*$/.test(line)) {
      // This is the separator after the header — mark header done
      tableHeaderDone = true;
      continue;
    }

    // Table rows (lines starting and ending with |)
    const isTableRow = /^\s*\|(.+)\|\s*$/.test(line);
    if (isTableRow) {
      const cells = line.trim().slice(1, -1).split("|").map((c) => c.trim());
      if (!inTable) {
        // Start table — this is the header row
        closeOpenBlocks();
        inTable = true;
        tableHeaderDone = false;
        html += "<table>\n<thead><tr>";
        for (const cell of cells) {
          html += `<th>${inlineMarkdown(escapeHtml(cell))}</th>`;
        }
        html += "</tr></thead>\n<tbody>\n";
        continue;
      }
      // Body row
      html += "<tr>";
      for (const cell of cells) {
        html += `<td>${inlineMarkdown(escapeHtml(cell))}</td>`;
      }
      html += "</tr>\n";
      continue;
    }

    // Close table if we hit a non-table line
    if (inTable) {
      html += "</tbody></table>\n";
      inTable = false;
      tableHeaderDone = false;
    }

    // Close list if current line isn't a list item
    if (inList && !/^\s*[-*+]\s|^\s*\d+\.\s/.test(line)) {
      html += listType === "ul" ? "</ul>\n" : "</ol>\n";
      inList = false;
    }

    // Blank line
    if (line.trim() === "") {
      continue;
    }

    // Headers
    const headerMatch = line.match(/^(#{1,6})\s+(.+)/);
    if (headerMatch) {
      const level = headerMatch[1].length;
      html += `<h${level}>${inlineMarkdown(escapeHtml(headerMatch[2]))}</h${level}>\n`;
      continue;
    }

    // Horizontal rules
    if (/^[-*_]{3,}\s*$/.test(line.trim())) {
      html += "<hr />\n";
      continue;
    }

    // Unordered list items
    const ulMatch = line.match(/^\s*[-*+]\s+(.*)/);
    if (ulMatch) {
      if (!inList || listType !== "ul") {
        if (inList) { html += "</ol>\n"; }
        html += "<ul>\n";
        inList = true;
        listType = "ul";
      }
      html += `<li>${inlineMarkdown(escapeHtml(ulMatch[1]))}</li>\n`;
      continue;
    }

    // Ordered list items
    const olMatch = line.match(/^\s*\d+\.\s+(.*)/);
    if (olMatch) {
      if (!inList || listType !== "ol") {
        if (inList) { html += "</ul>\n"; }
        html += "<ol>\n";
        inList = true;
        listType = "ol";
      }
      html += `<li>${inlineMarkdown(escapeHtml(olMatch[1]))}</li>\n`;
      continue;
    }

    // Regular paragraph
    html += `<p>${inlineMarkdown(escapeHtml(line))}</p>\n`;
  }

  if (inCodeBlock) {
    html += `<pre><code>${escapeHtml(codeBlockContent.trimEnd())}</code></pre>\n`;
  }
  if (inList) {
    html += listType === "ul" ? "</ul>\n" : "</ol>\n";
  }
  if (inTable) {
    html += "</tbody></table>\n";
  }

  return html;
}

/** Convert inline markdown (bold, italic, code, links) in already-escaped HTML. */
function inlineMarkdown(escaped: string): string {
  return escaped
    // inline code (must come before bold/italic to avoid conflicts)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    // bold+italic
    .replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>")
    // bold
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    // italic
    .replace(/\*(.+?)\*/g, "<em>$1</em>")
    // links [text](url)
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>')
    // bare URLs (not already inside an href)
    .replace(/(?<!="|'|&gt;)(https?:\/\/[^\s<)]+)/g, '<a href="$1">$1</a>');
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
    .content a { color: var(--vscode-textLink-foreground); }
    .content p { margin: 4px 0; }
    .content h2 { font-size: 1.2em; margin: 16px 0 8px; }
    .content h3 { font-size: 1.1em; margin: 12px 0 6px; }
    .content ul, .content ol { padding-left: 24px; }
    .content li { margin: 2px 0; }
    table {
      border-collapse: collapse;
      margin: 8px 0;
      width: 100%;
    }
    th, td {
      border: 1px solid var(--vscode-widget-border, rgba(128,128,128,0.3));
      padding: 6px 10px;
      text-align: left;
    }
    th {
      background: var(--vscode-textCodeBlock-background, rgba(128,128,128,0.1));
      font-weight: 600;
    }
  </style>
</head>
<body>
  <h1>${escapeHtml(title)}</h1>
  ${tagsHtml}
  <hr />
  <div class="content">${markdownToHtml(content)}</div>
  <script>
    const vscode = acquireVsCodeApi();
    document.addEventListener('click', (e) => {
      const link = e.target.closest('a');
      if (link && link.href) {
        e.preventDefault();
        vscode.postMessage({ type: 'openLink', url: link.href });
      }
    });
  </script>
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
    ? `<h3>Description</h3>\n<div class="content">${markdownToHtml(task.description)}</div>`
    : `<p style="color: var(--vscode-disabledForeground);">No description</p>`;

  const logHtml = log.length > 0
    ? `<h3>Work Log</h3>\n<div class="work-log">${log.map((entry) =>
        `<div class="log-entry"><div class="log-ts">${escapeHtml(entry.timestamp)}</div><div class="log-msg">${markdownToHtml(entry.message)}</div></div>`
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
    .content p { margin: 4px 0; }
    .content a { color: var(--vscode-textLink-foreground); }
    .work-log { margin-top: 8px; }
    .log-entry {
      padding: 8px 0;
      border-bottom: 1px solid var(--vscode-widget-border, rgba(128,128,128,0.2));
    }
    .log-ts {
      color: var(--vscode-descriptionForeground);
      font-size: 0.85em;
      margin-bottom: 4px;
    }
    .log-msg { margin: 0; }
    .log-msg p { margin: 2px 0; }
    table {
      border-collapse: collapse;
      margin: 8px 0;
      width: 100%;
    }
    th, td {
      border: 1px solid var(--vscode-widget-border, rgba(128,128,128,0.3));
      padding: 6px 10px;
      text-align: left;
    }
    th {
      background: var(--vscode-textCodeBlock-background, rgba(128,128,128,0.1));
      font-weight: 600;
    }
  </style>
</head>
<body>
  <h1>#${task.id}: ${escapeHtml(task.title)}</h1>
  <ul>${meta}</ul>
  <hr />
  ${description}
  ${logHtml}
  <script>
    const vscode = acquireVsCodeApi();
    document.addEventListener('click', (e) => {
      const link = e.target.closest('a');
      if (link && link.href) {
        e.preventDefault();
        vscode.postMessage({ type: 'openLink', url: link.href });
      }
    });
  </script>
</body>
</html>`;
}
