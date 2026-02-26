import { execFile, spawn } from "child_process";
import { promisify } from "util";
import * as vscode from "vscode";

import type {
  Document,
  DocumentDetail,
  SearchResult,
  StatusData,
  Tag,
  Task,
} from "./types";

const execFileAsync = promisify(execFile);

const DEFAULT_TIMEOUT_MS = 30_000;

/** Default cache TTL in milliseconds (10 seconds). */
const CACHE_TTL_MS = 10_000;

// Commands where --json is not applicable (e.g. status updates that produce no output)
const NO_JSON_COMMANDS = new Set(["task done", "task active", "task blocked"]);

interface CacheEntry<T> {
  data: T;
  expiresAt: number;
}

class EmdxClient {
  private outputChannel: vscode.OutputChannel;
  private cache = new Map<string, CacheEntry<unknown>>();

  constructor() {
    this.outputChannel = vscode.window.createOutputChannel("EMDX");
  }

  private getExecutablePath(): string {
    const config = vscode.workspace.getConfiguration("emdx");
    return config.get<string>("executablePath", "emdx");
  }

  private getExecParts(): { command: string; baseArgs: string[] } {
    const execPath = this.getExecutablePath();
    const parts = execPath.split(/\s+/);
    return { command: parts[0], baseArgs: parts.slice(1) };
  }

  /** Get a cached value if it exists and hasn't expired. */
  private getCached<T>(key: string): T | undefined {
    const entry = this.cache.get(key);
    if (entry && Date.now() < entry.expiresAt) {
      return entry.data as T;
    }
    if (entry) {
      this.cache.delete(key);
    }
    return undefined;
  }

  /** Store a value in cache with TTL. */
  private setCache<T>(key: string, data: T, ttlMs: number = CACHE_TTL_MS): void {
    this.cache.set(key, { data, expiresAt: Date.now() + ttlMs });
  }

  /** Invalidate all cache entries (call after mutations). */
  invalidateCache(): void {
    this.cache.clear();
  }

  private async exec<T>(args: string[], parseJson: true): Promise<T>;
  private async exec(args: string[], parseJson: false): Promise<string>;
  private async exec<T>(
    args: string[],
    parseJson: boolean = true
  ): Promise<T | string> {
    const { command, baseArgs } = this.getExecParts();

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

  /** Execute with caching. Reuses result within TTL window. */
  private async execCached<T>(
    cacheKey: string,
    args: string[],
    ttlMs: number = CACHE_TTL_MS
  ): Promise<T> {
    const cached = this.getCached<T>(cacheKey);
    if (cached !== undefined) {
      return cached;
    }
    const result = await this.exec<T>(args, true);
    this.setCache(cacheKey, result, ttlMs);
    return result;
  }

  /** Execute a command with content piped to stdin. Returns stdout text. */
  private execWithStdin(args: string[], stdin: string): Promise<string> {
    const { command, baseArgs } = this.getExecParts();
    const fullArgs = [...baseArgs, ...args];

    return new Promise((resolve, reject) => {
      const proc = spawn(command, fullArgs, {
        timeout: DEFAULT_TIMEOUT_MS,
        cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
      });

      let stdout = "";
      let stderr = "";

      proc.stdout.on("data", (data: Buffer) => {
        stdout += data.toString();
      });
      proc.stderr.on("data", (data: Buffer) => {
        stderr += data.toString();
      });

      proc.on("close", (code) => {
        if (code === 0) {
          resolve(stdout);
        } else {
          this.outputChannel.appendLine(
            `[ERROR] emdx ${args.join(" ")}: exit code ${code}`
          );
          if (stderr) {
            this.outputChannel.appendLine(`[STDERR] ${stderr}`);
          }
          reject(new Error(`emdx save failed (exit ${code}): ${stderr}`));
        }
      });

      proc.on("error", (err) => {
        reject(err);
      });

      proc.stdin.write(stdin);
      proc.stdin.end();
    });
  }

  // Documents

  async listRecentDocuments(limit: number = 20): Promise<Document[]> {
    return this.execCached<Document[]>(
      `recent:${limit}`,
      ["find", "--recent", String(limit)]
    );
  }

  async searchDocuments(query: string): Promise<SearchResult[]> {
    // Don't cache searches — user expects fresh results per keystroke
    return this.exec<SearchResult[]>(["find", query], true);
  }

  async getDocument(id: number): Promise<DocumentDetail> {
    return this.execCached<DocumentDetail>(
      `doc:${id}`,
      ["view", String(id)]
    );
  }

  async saveDocument(
    title: string,
    content: string,
    tags?: string[]
  ): Promise<{ id: number; title: string }> {
    // emdx save does not support --json. Pipe content via stdin.
    const args = ["save", "--title", title];
    if (tags && tags.length > 0) {
      args.push("--tags", tags.join(","));
    }

    const output = await this.execWithStdin(args, content);
    this.invalidateCache(); // New doc — bust all caches

    // Parse "✅ Saved as #18: title" from output (with ANSI codes stripped)
    const clean = output.replace(/\x1b\[[0-9;]*m/g, "");
    const match = clean.match(/Saved as #(\d+)/);
    const id = match ? parseInt(match[1], 10) : 0;
    return { id, title };
  }

  // Tasks

  async listTasks(status?: string, epicKey?: string): Promise<Task[]> {
    const key = `tasks:${status ?? "all"}:${epicKey ?? "all"}`;
    const args = ["task", "list"];
    if (status) {
      args.push("--status", status);
    }
    if (epicKey) {
      args.push("--epic", epicKey);
    }
    return this.execCached<Task[]>(key, args);
  }

  async getReadyTasks(): Promise<Task[]> {
    return this.execCached<Task[]>("tasks:ready", ["task", "ready"]);
  }

  async updateTaskStatus(
    id: number,
    status: "done" | "active" | "blocked"
  ): Promise<void> {
    await this.exec(["task", status, String(id)], false);
    this.invalidateCache(); // Status changed — bust caches
  }

  // Tags

  async listTags(): Promise<Tag[]> {
    return this.execCached<Tag[]>("tags", ["tag", "list"]);
  }

  // Status

  async getStatus(): Promise<StatusData> {
    return this.execCached<StatusData>("status", ["status"]);
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
