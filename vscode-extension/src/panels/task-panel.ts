import * as vscode from "vscode";

import type { EmdxClient } from "../emdx-client";
import type { ExtensionMessage, WebviewMessage } from "../types";

/**
 * TaskPanel manages the task browser webview panel.
 *
 * Uses a singleton pattern: only one TaskPanel can be open at a time.
 * Call `TaskPanel.createOrShow()` to either create a new panel or
 * reveal the existing one.
 */
export class TaskPanel {
  public static currentPanel: TaskPanel | undefined;
  public static readonly viewType = "emdx.taskPanel";

  private readonly _panel: vscode.WebviewPanel;
  private readonly _extensionUri: vscode.Uri;
  private readonly _client: EmdxClient;
  private _disposables: vscode.Disposable[] = [];

  /**
   * Tracks the most recent filter parameters so that refreshes preserve them.
   */
  private _lastStatus: string | undefined;
  private _lastEpicKey: string | undefined;

  /**
   * Create a new TaskPanel or reveal the existing one.
   */
  public static createOrShow(
    extensionUri: vscode.Uri,
    client: EmdxClient
  ): void {
    if (TaskPanel.currentPanel) {
      TaskPanel.currentPanel._panel.reveal(vscode.ViewColumn.One);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      TaskPanel.viewType,
      "EMDX Tasks",
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        localResourceRoots: [
          vscode.Uri.joinPath(extensionUri, "dist", "webview"),
        ],
        retainContextWhenHidden: true,
      }
    );

    TaskPanel.currentPanel = new TaskPanel(panel, extensionUri, client);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    client: EmdxClient
  ) {
    this._panel = panel;
    this._extensionUri = extensionUri;
    this._client = client;

    this._panel.webview.html = this._getWebviewContent(this._panel.webview);

    this._panel.webview.onDidReceiveMessage(
      (message: WebviewMessage) => this._handleMessage(message),
      null,
      this._disposables
    );

    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

    // Load initial task list
    void this._loadTasks();
  }

  /**
   * Handle messages sent from the webview.
   */
  private async _handleMessage(message: WebviewMessage): Promise<void> {
    try {
      switch (message.type) {
        case "fetchTasks": {
          this._lastStatus = message.status;
          this._lastEpicKey = message.epicKey;
          await this._loadTasks(message.status, message.epicKey);
          break;
        }

        case "updateTaskStatus": {
          this._postMessage({ type: "loading", loading: true });
          const status = message.status as "done" | "active" | "blocked";
          await this._client.updateTaskStatus(message.id, status);
          // Refresh tasks with the same filters after the status update
          await this._loadTasks(this._lastStatus, this._lastEpicKey);
          this._postMessage({ type: "loading", loading: false });
          break;
        }

        case "refresh": {
          await this._loadTasks(this._lastStatus, this._lastEpicKey);
          break;
        }

        default:
          break;
      }
    } catch (err: unknown) {
      const errorMessage =
        err instanceof Error ? err.message : "An unknown error occurred";
      this._postMessage({ type: "error", message: errorMessage });
      this._postMessage({ type: "loading", loading: false });
    }
  }

  /**
   * Fetch tasks from the emdx knowledge base and send them to the webview.
   */
  private async _loadTasks(
    status?: string,
    epicKey?: string
  ): Promise<void> {
    this._postMessage({ type: "loading", loading: true });
    try {
      const tasks = await this._client.listTasks(status, epicKey);
      this._postMessage({ type: "tasks", data: tasks });
    } finally {
      this._postMessage({ type: "loading", loading: false });
    }
  }

  /**
   * Post a typed message to the webview.
   */
  private _postMessage(message: ExtensionMessage): void {
    void this._panel.webview.postMessage(message);
  }

  /**
   * Generate the HTML content for the webview.
   */
  private _getWebviewContent(webview: vscode.Webview): string {
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "dist", "webview", "tasks.js")
    );
    const styleUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "dist", "webview", "tasks.css")
    );

    const nonce = getNonce();

    return /* html */ `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta
      http-equiv="Content-Security-Policy"
      content="default-src 'none'; style-src ${webview.cspSource} 'nonce-${nonce}'; script-src 'nonce-${nonce}'; font-src ${webview.cspSource};"
    />
    <link rel="stylesheet" href="${styleUri}" />
    <title>EMDX Tasks</title>
  </head>
  <body>
    <div id="root" data-view="tasks"></div>
    <script nonce="${nonce}" src="${scriptUri}"></script>
  </body>
</html>`;
  }

  /**
   * Clean up resources when the panel is closed.
   */
  public dispose(): void {
    TaskPanel.currentPanel = undefined;

    this._panel.dispose();

    while (this._disposables.length) {
      const disposable = this._disposables.pop();
      if (disposable) {
        disposable.dispose();
      }
    }
  }
}

/**
 * Generate a random nonce string for Content-Security-Policy.
 */
function getNonce(): string {
  let text = "";
  const possible =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length));
  }
  return text;
}
