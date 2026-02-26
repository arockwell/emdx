import * as vscode from "vscode";

import type { EmdxClient } from "../emdx-client";
import type { ExtensionMessage, WebviewMessage } from "../types";

/**
 * ActivityPanel manages the document browser webview panel.
 *
 * Uses a singleton pattern: only one ActivityPanel can be open at a time.
 * Call `ActivityPanel.createOrShow()` to either create a new panel or
 * reveal the existing one.
 */
export class ActivityPanel {
  public static currentPanel: ActivityPanel | undefined;
  public static readonly viewType = "emdx.activityPanel";

  private readonly _panel: vscode.WebviewPanel;
  private readonly _extensionUri: vscode.Uri;
  private readonly _client: EmdxClient;
  private _disposables: vscode.Disposable[] = [];

  /**
   * Create a new ActivityPanel or reveal the existing one.
   */
  public static createOrShow(
    extensionUri: vscode.Uri,
    client: EmdxClient
  ): void {
    // If we already have a panel, reveal it
    if (ActivityPanel.currentPanel) {
      ActivityPanel.currentPanel._panel.reveal(vscode.ViewColumn.One);
      return;
    }

    // Otherwise, create a new panel
    const panel = vscode.window.createWebviewPanel(
      ActivityPanel.viewType,
      "EMDX Documents",
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        localResourceRoots: [
          vscode.Uri.joinPath(extensionUri, "dist", "webview"),
        ],
        retainContextWhenHidden: true,
      }
    );

    ActivityPanel.currentPanel = new ActivityPanel(panel, extensionUri, client);
  }

  private constructor(
    panel: vscode.WebviewPanel,
    extensionUri: vscode.Uri,
    client: EmdxClient
  ) {
    this._panel = panel;
    this._extensionUri = extensionUri;
    this._client = client;

    // Set the webview HTML content
    this._panel.webview.html = this._getWebviewContent(this._panel.webview);

    // Listen for messages from the webview
    this._panel.webview.onDidReceiveMessage(
      (message: WebviewMessage) => this._handleMessage(message),
      null,
      this._disposables
    );

    // Clean up when the panel is disposed
    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

    // Load initial data
    void this._loadDocuments();
  }

  /**
   * Handle messages sent from the webview.
   */
  private async _handleMessage(message: WebviewMessage): Promise<void> {
    try {
      switch (message.type) {
        case "fetchDocuments": {
          await this._loadDocuments(message.limit);
          break;
        }

        case "fetchDocument": {
          this._postMessage({ type: "loading", loading: true });
          const doc = await this._client.getDocument(message.id);
          this._postMessage({ type: "document", data: doc });
          this._postMessage({ type: "loading", loading: false });
          break;
        }

        case "searchDocuments": {
          this._postMessage({ type: "loading", loading: true });
          const results = await this._client.searchDocuments(message.query);
          this._postMessage({ type: "searchResults", data: results });
          this._postMessage({ type: "loading", loading: false });
          break;
        }

        case "saveDocument": {
          this._postMessage({ type: "loading", loading: true });
          await this._client.saveDocument(
            message.title,
            message.content,
            message.tags
          );
          // Refresh the document list after saving
          await this._loadDocuments();
          this._postMessage({ type: "loading", loading: false });
          break;
        }

        case "refresh": {
          await this._loadDocuments();
          break;
        }

        case "openExternal": {
          await vscode.env.openExternal(vscode.Uri.parse(message.url));
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
   * Fetch recent documents from the emdx knowledge base and send them to the webview.
   */
  private async _loadDocuments(limit?: number): Promise<void> {
    this._postMessage({ type: "loading", loading: true });
    try {
      const documents = await this._client.listRecentDocuments(limit);
      this._postMessage({ type: "documents", data: documents });
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
   *
   * Loads the bundled React application with a strict Content-Security-Policy.
   */
  private _getWebviewContent(webview: vscode.Webview): string {
    const scriptUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "dist", "webview", "activity.js")
    );
    const styleUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "dist", "webview", "activity.css")
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
    <title>EMDX Documents</title>
  </head>
  <body>
    <div id="root" data-view="activity"></div>
    <script nonce="${nonce}" src="${scriptUri}"></script>
  </body>
</html>`;
  }

  /**
   * Clean up resources when the panel is closed.
   */
  public dispose(): void {
    ActivityPanel.currentPanel = undefined;

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
