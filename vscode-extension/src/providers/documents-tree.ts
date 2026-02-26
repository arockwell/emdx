import * as vscode from "vscode";

import type { Document } from "../types";
import type { EmdxClient } from "../emdx-client";

export class DocTreeItem extends vscode.TreeItem {
  constructor(
    public readonly doc: Document,
    collapsibleState: vscode.TreeItemCollapsibleState = vscode
      .TreeItemCollapsibleState.None
  ) {
    super(doc.title, collapsibleState);

    this.label = `\u{1F4C4} ${doc.title}`;
    this.description = doc.project ?? undefined;
    this.tooltip = new vscode.MarkdownString(
      [
        `**${doc.title}**`,
        "",
        `ID: ${doc.id}`,
        doc.project ? `Project: ${doc.project}` : null,
        `Views: ${doc.access_count}`,
        `Last accessed: ${doc.accessed_at}`,
      ]
        .filter(Boolean)
        .join("\n\n")
    );

    this.command = {
      command: "emdx.viewDocument",
      title: "View Document",
      arguments: [doc.id],
    };

    this.contextValue = "document";
  }
}

class ErrorTreeItem extends vscode.TreeItem {
  constructor(message: string) {
    super(message, vscode.TreeItemCollapsibleState.None);
    this.contextValue = "error";
    this.iconPath = new vscode.ThemeIcon("warning");
  }
}

export class DocumentsTreeProvider
  implements vscode.TreeDataProvider<DocTreeItem | ErrorTreeItem>
{
  private _onDidChangeTreeData = new vscode.EventEmitter<
    DocTreeItem | ErrorTreeItem | undefined | null | void
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private client: EmdxClient;

  constructor(client: EmdxClient) {
    this.client = client;
  }

  refresh(): void {
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(
    element: DocTreeItem | ErrorTreeItem
  ): vscode.TreeItem {
    return element;
  }

  async getChildren(
    element?: DocTreeItem | ErrorTreeItem
  ): Promise<(DocTreeItem | ErrorTreeItem)[]> {
    // Documents are flat -- no children for individual items.
    if (element) {
      return [];
    }

    try {
      const documents = await this.client.listRecentDocuments();
      if (documents.length === 0) {
        return [new ErrorTreeItem("No documents found")];
      }
      return documents.map(
        (doc) =>
          new DocTreeItem(doc, vscode.TreeItemCollapsibleState.None)
      );
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : String(error);
      return [new ErrorTreeItem(`Error loading documents: ${message}`)];
    }
  }
}
