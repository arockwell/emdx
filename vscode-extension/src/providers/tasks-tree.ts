import * as vscode from "vscode";

import type { Task, TaskStatus } from "../types";
import type { EmdxClient } from "../emdx-client";

const STATUS_ICONS: Record<TaskStatus, string> = {
  open: "\u25CB",     // ○
  active: "\u25CF",   // ●
  blocked: "\u26A0",  // ⚠
  done: "\u2713",     // ✓
  failed: "\u2717",   // ✗
  wontdo: "\u2298",   // ⊘
};

const PRIORITY_INDICATORS: Record<number, string> = {
  1: "\u25B2\u25B2", // ▲▲  critical
  2: "\u25B2",       // ▲   high
  3: "",             //     normal (no indicator)
  4: "\u25BD",       // ▽   low
  5: "\u25BD\u25BD", // ▽▽  minimal
};

interface StatusGroup {
  label: string;
  status: TaskStatus;
}

const STATUS_GROUPS: StatusGroup[] = [
  { label: "Ready", status: "open" },
  { label: "Active", status: "active" },
  { label: "Blocked", status: "blocked" },
  { label: "Done", status: "done" },
];

export class TaskTreeItem extends vscode.TreeItem {
  constructor(
    public readonly task: Task,
    collapsibleState: vscode.TreeItemCollapsibleState = vscode
      .TreeItemCollapsibleState.None
  ) {
    super(task.title, collapsibleState);

    const icon = STATUS_ICONS[task.status] ?? "\u25CB";
    const priority = PRIORITY_INDICATORS[task.priority] ?? "";
    const prioritySuffix = priority ? ` ${priority}` : "";

    this.label = `${icon} ${task.title}${prioritySuffix}`;
    this.description = task.epic_key ?? undefined;
    this.tooltip = new vscode.MarkdownString(
      [
        `**${task.title}**`,
        "",
        `ID: ${task.id}`,
        `Status: ${task.status}`,
        `Priority: ${task.priority}`,
        task.epic_key ? `Epic: ${task.epic_key}` : null,
        task.description ? `\n---\n${task.description}` : null,
      ]
        .filter(Boolean)
        .join("\n\n")
    );

    this.command = {
      command: "emdx.viewTask",
      title: "View Task",
      arguments: [task],
    };

    // Context value enables right-click actions based on current status.
    switch (task.status) {
      case "open":
        this.contextValue = "task.open";
        break;
      case "active":
        this.contextValue = "task.active";
        break;
      case "blocked":
        this.contextValue = "task.blocked";
        break;
      case "done":
        this.contextValue = "task.done";
        break;
      case "failed":
        this.contextValue = "task.failed";
        break;
      case "wontdo":
        this.contextValue = "task.wontdo";
        break;
      default:
        this.contextValue = "task";
    }
  }
}

class StatusGroupItem extends vscode.TreeItem {
  constructor(
    public readonly group: StatusGroup,
    public readonly taskCount: number
  ) {
    super(
      `${group.label} (${taskCount})`,
      taskCount > 0
        ? vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.Collapsed
    );
    this.contextValue = "statusGroup";
    this.iconPath = StatusGroupItem.themeIconForStatus(group.status);
  }

  private static themeIconForStatus(
    status: TaskStatus
  ): vscode.ThemeIcon {
    switch (status) {
      case "open":
        return new vscode.ThemeIcon("circle-outline");
      case "active":
        return new vscode.ThemeIcon("play-circle");
      case "blocked":
        return new vscode.ThemeIcon("warning");
      case "done":
        return new vscode.ThemeIcon("check");
      default:
        return new vscode.ThemeIcon("circle-outline");
    }
  }
}

type TaskTreeElement = TaskTreeItem | StatusGroupItem;

export class TasksTreeProvider
  implements vscode.TreeDataProvider<TaskTreeElement>
{
  private _onDidChangeTreeData = new vscode.EventEmitter<
    TaskTreeElement | undefined | null | void
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private client: EmdxClient;
  private tasksByStatus: Map<TaskStatus, Task[]> = new Map();

  constructor(client: EmdxClient) {
    this.client = client;
  }

  refresh(): void {
    this.tasksByStatus.clear();
    this._onDidChangeTreeData.fire();
  }

  getTreeItem(element: TaskTreeElement): vscode.TreeItem {
    return element;
  }

  async getChildren(
    element?: TaskTreeElement
  ): Promise<TaskTreeElement[]> {
    // Root level: show status groups.
    if (!element) {
      return this.getStatusGroups();
    }

    // Child level: show tasks within a status group.
    if (element instanceof StatusGroupItem) {
      return this.getTasksForStatus(element.group.status);
    }

    // Individual tasks have no children.
    return [];
  }

  private async getStatusGroups(): Promise<StatusGroupItem[]> {
    try {
      const allTasks = await this.client.listTasks();

      // Group tasks by status.
      this.tasksByStatus.clear();
      for (const task of allTasks) {
        const existing = this.tasksByStatus.get(task.status) ?? [];
        existing.push(task);
        this.tasksByStatus.set(task.status, existing);
      }

      return STATUS_GROUPS.map(
        (group) =>
          new StatusGroupItem(
            group,
            this.tasksByStatus.get(group.status)?.length ?? 0
          )
      );
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : String(error);
      const errorItem = new StatusGroupItem(
        { label: `Error loading tasks: ${message}`, status: "open" },
        0
      );
      return [errorItem];
    }
  }

  private getTasksForStatus(status: TaskStatus): TaskTreeItem[] {
    const tasks = this.tasksByStatus.get(status) ?? [];

    // Sort by priority ascending (1 = highest).
    const sorted = [...tasks].sort(
      (a, b) => a.priority - b.priority
    );

    return sorted.map(
      (task) =>
        new TaskTreeItem(task, vscode.TreeItemCollapsibleState.None)
    );
  }
}
