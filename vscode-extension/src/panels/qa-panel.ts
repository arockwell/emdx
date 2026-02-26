import * as vscode from "vscode";

import type { EmdxClient } from "../emdx-client";
import type { ExtensionMessage, WebviewMessage } from "../types";

/**
 * QAPanel manages the Q&A webview panel.
 *
 * Uses a singleton pattern: only one QAPanel can be open at a time.
 * Call `QAPanel.createOrShow()` to either create a new panel or
 * reveal the existing one.
 */
export class QAPanel {
  public static currentPanel: QAPanel | undefined;
  public static readonly viewType = "emdx.qaPanel";

  private readonly _panel: vscode.WebviewPanel;
  private readonly _extensionUri: vscode.Uri;
  private readonly _client: EmdxClient;
  private _disposables: vscode.Disposable[] = [];

  /**
   * Create a new QAPanel or reveal the existing one.
   */
  public static createOrShow(
    extensionUri: vscode.Uri,
    client: EmdxClient
  ): void {
    if (QAPanel.currentPanel) {
      QAPanel.currentPanel._panel.reveal(vscode.ViewColumn.One);
      return;
    }

    const panel = vscode.window.createWebviewPanel(
      QAPanel.viewType,
      "EMDX Q&A",
      vscode.ViewColumn.One,
      {
        enableScripts: true,
        localResourceRoots: [
          vscode.Uri.joinPath(extensionUri, "dist", "webview"),
        ],
        retainContextWhenHidden: true,
      }
    );

    QAPanel.currentPanel = new QAPanel(panel, extensionUri, client);
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
  }

  /**
   * Handle messages sent from the webview.
   */
  private async _handleMessage(message: WebviewMessage): Promise<void> {
    try {
      switch (message.type) {
        case "askQuestion": {
          this._postMessage({ type: "loading", loading: true });
          const result = await this._client.askQuestion(message.question);
          // The client returns { answer: string }; wrap it into the QAResult
          // shape expected by the webview. The CLI --json may or may not
          // include sources depending on configuration, so default to an
          // empty array when absent.
          const qaResult = {
            answer: result.answer,
            sources: "sources" in result
              ? (result as unknown as { sources: { doc_id: number; title: string; snippet: string }[] }).sources
              : [],
          };
          this._postMessage({ type: "qaAnswer", data: qaResult });
          this._postMessage({ type: "loading", loading: false });
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
      vscode.Uri.joinPath(this._extensionUri, "dist", "webview", "qa.js")
    );
    const styleUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this._extensionUri, "dist", "webview", "qa.css")
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
    <title>EMDX Q&amp;A</title>
  </head>
  <body>
    <div id="root" data-view="qa"></div>
    <script nonce="${nonce}" src="${scriptUri}"></script>
  </body>
</html>`;
  }

  /**
   * Clean up resources when the panel is closed.
   */
  public dispose(): void {
    QAPanel.currentPanel = undefined;

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
