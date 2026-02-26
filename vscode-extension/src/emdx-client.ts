import { execFile } from "child_process";
import { promisify } from "util";
import * as vscode from "vscode";

import type {
  Document,
  DocumentDetail,
  KBStatus,
  SearchResult,
  Tag,
  Task,
} from "./types";

const execFileAsync = promisify(execFile);

const DEFAULT_TIMEOUT_MS = 30_000;

// Commands where --json is not applicable (e.g. status updates that produce no output)
const NO_JSON_COMMANDS = new Set(["task done", "task active", "task blocked"]);

class EmdxClient {
  private outputChannel: vscode.OutputChannel;

  constructor() {
    this.outputChannel = vscode.window.createOutputChannel("EMDX");
  }

  private getExecutablePath(): string {
    const config = vscode.workspace.getConfiguration("emdx");
    return config.get<string>("executablePath", "emdx");
  }

  private async exec<T>(args: string[], parseJson: true): Promise<T>;
  private async exec(args: string[], parseJson: false): Promise<string>;
  private async exec<T>(
    args: string[],
    parseJson: boolean = true
  ): Promise<T | string> {
    const execPath = this.getExecutablePath();
    const parts = execPath.split(/\s+/);
    const command = parts[0];
    const baseArgs = parts.slice(1);

    const shouldAddJson =
      parseJson &&
      !NO_JSON_COMMANDS.has(args.slice(0, 2).join(" "));

    const fullArgs = [
      ...baseArgs,
      ...args,
      ...(shouldAddJson ? ["--json"] : []),
    ];

    try {
      const { stdout } = await execFileAsync(command, fullArgs, {
        timeout: DEFAULT_TIMEOUT_MS,
        maxBuffer: 10 * 1024 * 1024,
        cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
      });

      if (!parseJson) {
        return stdout;
      }

      return JSON.parse(stdout) as T;
    } catch (error: unknown) {
      const message =
        error instanceof Error ? error.message : String(error);
      this.outputChannel.appendLine(
        `[ERROR] emdx ${args.join(" ")}: ${message}`
      );

      if (
        error &&
        typeof error === "object" &&
        "stderr" in error &&
        typeof (error as { stderr: unknown }).stderr === "string"
      ) {
        this.outputChannel.appendLine(
          `[STDERR] ${(error as { stderr: string }).stderr}`
        );
      }

      throw new Error(`emdx command failed: ${message}`);
    }
  }

  // Documents

  async listRecentDocuments(limit: number = 20): Promise<Document[]> {
    return this.exec<Document[]>(["find", "--recent", String(limit)], true);
  }

  async searchDocuments(query: string): Promise<SearchResult[]> {
    return this.exec<SearchResult[]>(["find", query], true);
  }

  async getDocument(id: number): Promise<DocumentDetail> {
    return this.exec<DocumentDetail>(["view", String(id)], true);
  }

  async saveDocument(
    title: string,
    content: string,
    tags?: string[]
  ): Promise<{ id: number }> {
    const args = ["save", content, "--title", title];
    if (tags && tags.length > 0) {
      args.push("--tags", tags.join(","));
    }
    return this.exec<{ id: number }>(args, true);
  }

  // Tasks

  async listTasks(status?: string, epicKey?: string): Promise<Task[]> {
    const args = ["task", "list"];
    if (status) {
      args.push("--status", status);
    }
    if (epicKey) {
      args.push("--epic", epicKey);
    }
    return this.exec<Task[]>(args, true);
  }

  async getReadyTasks(): Promise<Task[]> {
    return this.exec<Task[]>(["task", "ready"], true);
  }

  async updateTaskStatus(
    id: number,
    status: "done" | "active" | "blocked"
  ): Promise<void> {
    await this.exec(["task", status, String(id)], false);
  }

  // Tags

  async listTags(): Promise<Tag[]> {
    return this.exec<Tag[]>(["tag", "list"], true);
  }

  // Status

  async getStatus(): Promise<KBStatus> {
    return this.exec<KBStatus>(["status", "--stats"], true);
  }

  // Q&A

  async askQuestion(question: string): Promise<{ answer: string }> {
    return this.exec<{ answer: string }>(["find", "--ask", question], true);
  }

  // Utility

  async isAvailable(): Promise<boolean> {
    try {
      await this.exec(["--version"], false);
      return true;
    } catch {
      return false;
    }
  }
}

export const emdxClient = new EmdxClient();
export { EmdxClient };
