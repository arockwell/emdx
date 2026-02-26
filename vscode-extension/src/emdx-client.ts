import { execFile, spawn, type ChildProcess } from "child_process";
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

/** Timeout for RPC requests in milliseconds. */
const RPC_TIMEOUT_MS = 15_000;

// Commands where --json is not applicable (e.g. status updates that produce no output)
const NO_JSON_COMMANDS = new Set(["task done", "task active", "task blocked"]);

interface CacheEntry<T> {
  data: T;
  expiresAt: number;
}

interface RpcRequest {
  id: number;
  method: string;
  params: Record<string, unknown>;
}

interface RpcResponse {
  id: number | null;
  result?: unknown;
  error?: { code: number; message: string };
  ready?: boolean;
}

interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
}

class EmdxClient {
  private outputChannel: vscode.OutputChannel;
  private cache = new Map<string, CacheEntry<unknown>>();

  // Persistent server process
  private serverProc: ChildProcess | null = null;
  private serverReady = false;
  private serverStarting: Promise<void> | null = null;
  private nextRequestId = 1;
  private pendingRequests = new Map<number, PendingRequest>();
  private lineBuffer = "";

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

  // ---------------------------------------------------------------------------
  // Persistent server management
  // ---------------------------------------------------------------------------

  /** Ensure the `emdx serve` process is running and ready. */
  private async ensureServer(): Promise<void> {
    if (this.serverReady && this.serverProc && !this.serverProc.killed) {
      return;
    }
    if (this.serverStarting) {
      return this.serverStarting;
    }

    this.serverStarting = this.startServer();
    try {
      await this.serverStarting;
    } finally {
      this.serverStarting = null;
    }
  }

  private startServer(): Promise<void> {
    return new Promise((resolve, reject) => {
      const { command, baseArgs } = this.getExecParts();
      const fullArgs = [...baseArgs, "serve"];

      this.outputChannel.appendLine(`[INFO] Starting emdx serve: ${command} ${fullArgs.join(" ")}`);

      const proc = spawn(command, fullArgs, {
        cwd: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath,
        stdio: ["pipe", "pipe", "pipe"],
      });

      this.serverProc = proc;
      this.serverReady = false;
      this.lineBuffer = "";

      proc.stdout!.on("data", (data: Buffer) => {
        this.lineBuffer += data.toString();
        const lines = this.lineBuffer.split("\n");
        // Keep the last incomplete line in the buffer
        this.lineBuffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const msg: RpcResponse = JSON.parse(line);
            if (msg.ready) {
              this.serverReady = true;
              this.outputChannel.appendLine("[INFO] emdx serve ready");
              resolve();
              continue;
            }
            if (msg.id != null) {
              const pending = this.pendingRequests.get(msg.id);
              if (pending) {
                this.pendingRequests.delete(msg.id);
                clearTimeout(pending.timer);
                if (msg.error) {
                  pending.reject(new Error(msg.error.message));
                } else {
                  pending.resolve(msg.result);
                }
              }
            }
          } catch (err) {
            this.outputChannel.appendLine(`[WARN] Failed to parse server output: ${line}`);
          }
        }
      });

      proc.stderr!.on("data", (data: Buffer) => {
        this.outputChannel.appendLine(`[SERVE STDERR] ${data.toString().trimEnd()}`);
      });

      proc.on("close", (code) => {
        this.outputChannel.appendLine(`[INFO] emdx serve exited with code ${code}`);
        this.serverReady = false;
        this.serverProc = null;
        // Reject all pending requests
        for (const [id, pending] of this.pendingRequests) {
          clearTimeout(pending.timer);
          pending.reject(new Error("Server process exited"));
          this.pendingRequests.delete(id);
        }
        // If we haven't resolved the startup yet, reject it
        if (!this.serverReady) {
          reject(new Error(`emdx serve exited with code ${code}`));
        }
      });

      proc.on("error", (err) => {
        this.outputChannel.appendLine(`[ERROR] emdx serve spawn error: ${err.message}`);
        this.serverReady = false;
        this.serverProc = null;
        reject(err);
      });

      // Timeout for startup
      setTimeout(() => {
        if (!this.serverReady) {
          reject(new Error("emdx serve startup timed out"));
          proc.kill();
        }
      }, DEFAULT_TIMEOUT_MS);
    });
  }

  /** Send an RPC request to the persistent server. */
  private async rpc<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
    await this.ensureServer();

    const id = this.nextRequestId++;
    const request: RpcRequest = { id, method, params };

    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pendingRequests.delete(id);
        reject(new Error(`RPC timeout for ${method}`));
      }, RPC_TIMEOUT_MS);

      this.pendingRequests.set(id, {
        resolve: resolve as (value: unknown) => void,
        reject,
        timer,
      });

      const line = JSON.stringify(request) + "\n";
      this.serverProc!.stdin!.write(line);
    });
  }

  /** Send RPC with caching. */
  private async rpcCached<T>(
    cacheKey: string,
    method: string,
    params: Record<string, unknown> = {},
    ttlMs: number = CACHE_TTL_MS,
  ): Promise<T> {
    const cached = this.getCached<T>(cacheKey);
    if (cached !== undefined) {
      return cached;
    }
    const result = await this.rpc<T>(method, params);
    this.setCache(cacheKey, result, ttlMs);
    return result;
  }

  /** Shut down the persistent server process. */
  dispose(): void {
    if (this.serverProc && !this.serverProc.killed) {
      this.serverProc.stdin!.end();
      this.serverProc.kill();
      this.serverProc = null;
      this.serverReady = false;
    }
  }

  // ---------------------------------------------------------------------------
  // Cache
  // ---------------------------------------------------------------------------

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

  // ---------------------------------------------------------------------------
  // Subprocess fallback (for commands not supported by serve)
  // ---------------------------------------------------------------------------

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

  // ---------------------------------------------------------------------------
  // Public API — uses persistent server where available, subprocess fallback
  // ---------------------------------------------------------------------------

  // Documents

  async listRecentDocuments(limit: number = 20): Promise<Document[]> {
    return this.rpcCached<Document[]>("recent:" + limit, "find.recent", { limit });
  }

  async searchDocuments(query: string): Promise<SearchResult[]> {
    // Don't cache searches — user expects fresh results per keystroke
    return this.rpc<SearchResult[]>("find.search", { query });
  }

  async findByTag(tag: string): Promise<Document[]> {
    return this.rpcCached<Document[]>("tag:" + tag, "find.by_tags", { tags: tag });
  }

  async getDocument(id: number): Promise<DocumentDetail> {
    return this.rpcCached<DocumentDetail>("doc:" + id, "view", { id });
  }

  async saveDocument(
    title: string,
    content: string,
    tags?: string[]
  ): Promise<{ id: number; title: string }> {
    const result = await this.rpc<{ id: number; title: string }>("save", {
      title,
      content,
      tags: tags ?? [],
    });
    this.invalidateCache();
    return result;
  }

  // Tasks

  async listTasks(status?: string, epicKey?: string): Promise<Task[]> {
    const key = `tasks:${status ?? "all"}:${epicKey ?? "all"}`;
    const params: Record<string, unknown> = {};
    if (status) params.status = status;
    if (epicKey) params.epic_key = epicKey;
    return this.rpcCached<Task[]>(key, "task.list", params);
  }

  async getReadyTasks(): Promise<Task[]> {
    return this.rpcCached<Task[]>("tasks:ready", "task.list", { status: "open" });
  }

  async updateTaskStatus(
    id: number,
    status: "done" | "active" | "blocked"
  ): Promise<void> {
    await this.rpc("task.update", { id, status });
    this.invalidateCache();
  }

  async getTaskLog(id: number): Promise<Array<{ timestamp: string; message: string }>> {
    const cacheKey = `tasklog:${id}`;
    const cached = this.getCached<Array<{ timestamp: string; message: string }>>(cacheKey);
    if (cached !== undefined) {
      return cached;
    }

    const entries = await this.rpc<Array<{ id: number; task_id: number; message: string; created_at: string }>>(
      "task.log", { id }
    );

    // Map server format to extension format
    const result = entries.map((e) => ({
      timestamp: e.created_at ?? "",
      message: e.message,
    }));

    this.setCache(cacheKey, result);
    return result;
  }

  // Tags

  async listTags(): Promise<Tag[]> {
    return this.rpcCached<Tag[]>("tags", "tag.list");
  }

  // Status

  async getStatus(): Promise<StatusData> {
    return this.rpcCached<StatusData>("status", "status");
  }

  // Q&A (falls back to subprocess — requires LLM call, not suited for RPC)

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
