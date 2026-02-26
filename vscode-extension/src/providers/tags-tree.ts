import * as vscode from "vscode";

import type { Tag } from "../types";
import type { EmdxClient } from "../emdx-client";

export class TagTreeItem extends vscode.TreeItem {
  constructor(public readonly tag: Tag) {
    super(
      `${tag.name} (${tag.count})`,
      vscode.TreeItemCollapsibleState.None
    );

    this.description = undefined;
    this.tooltip = new vscode.MarkdownString(
      [
        `**${tag.name}**`,
        "",
        `Documents: ${tag.count}`,
        `Created: ${tag.created_at}`,
      ].join("\n\n")
    );

    this.iconPath = new vscode.ThemeIcon("tag");

    this.command = {
      command: "emdx.filterByTag",
      title: "Filter Documents by Tag",
      arguments: [tag.name],
    };

    this.contextValue = "tag";
  }
}

class ErrorTreeItem extends vscode.TreeItem {
  constructor(message: string) {
    super(message, vscode.TreeItemCollapsibleState.None);
    this.contextValue = "error";
    this.iconPath = new vscode.ThemeIcon("warning");
  }
}

export class TagsTreeProvider
  implements vscode.TreeDataProvider<TagTreeItem | ErrorTreeItem>
{
  private _onDidChangeTreeData = new vscode.EventEmitter<
    TagTreeItem | ErrorTreeItem | undefined | null | void
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
    element: TagTreeItem | ErrorTreeItem
  ): vscode.TreeItem {
    return element;
  }

  async getChildren(
    element?: TagTreeItem | ErrorTreeItem
  ): Promise<(TagTreeItem | ErrorTreeItem)[]> {
    // Tags are flat -- no children.
    if (element) {
      return [];
    }

    try {
      const tags = await this.client.listTags();

      if (tags.length === 0) {
        return [new ErrorTreeItem("No tags found")];
      }

      // Sort by count descending.
      const sorted = [...tags].sort((a, b) => b.count - a.count);

      return sorted.map((tag) => new TagTreeItem(tag));
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : String(error);
      return [new ErrorTreeItem(`Error loading tags: ${message}`)];
    }
  }
}
