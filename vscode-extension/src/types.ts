// EMDX VSCode Extension Types
// TypeScript interfaces mirroring the actual emdx CLI --json output.

// ---------------------------------------------------------------------------
// Document types
// ---------------------------------------------------------------------------

/** Returned by `emdx find --recent --json` */
export interface Document {
  id: number;
  title: string;
  project: string | null;
  access_count: number;
  accessed_at: string;
}

/** Returned by `emdx view <id> --json` */
export interface DocumentDetail {
  id: number;
  title: string;
  content: string;
  project: string | null;
  tags: string[];
  linked_docs: DocumentLink[];
  word_count: number;
  char_count: number;
  line_count: number;
  access_count: number;
  accessed_at: string;
  created_at: string;
  updated_at: string;
  parent_id: number | null;
}

export interface DocumentLink {
  doc_id: number;
  title: string;
  similarity_score: number;
  method: string;
}

/** Returned by `emdx find <query> --json` */
export interface SearchResult {
  id: number;
  title: string;
  project: string | null;
  score: number;
  keyword_score?: number;
  source: string;
  tags: string[];
}

// ---------------------------------------------------------------------------
// Task types
// ---------------------------------------------------------------------------

export type TaskStatus = "open" | "active" | "blocked" | "done" | "failed" | "wontdo";

/** Returned by `emdx task list --json` */
export interface Task {
  id: number;
  title: string;
  description: string | null;
  status: TaskStatus;
  priority: number;
  epic_key: string | null;
  epic_seq: number | null;
  source_doc_id: number | null;
  parent_task_id: number | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  project: string | null;
  type: string;
}

// ---------------------------------------------------------------------------
// Tag types
// ---------------------------------------------------------------------------

/** Returned by `emdx tag list --json` */
export interface Tag {
  id: number;
  name: string;
  count: number;
  created_at: string;
  last_used: string;
}

// ---------------------------------------------------------------------------
// Status types
// ---------------------------------------------------------------------------

/** Returned by `emdx status --json` */
export interface StatusData {
  active: Task[];
  recent: Task[];
  failed: Task[];
}

// ---------------------------------------------------------------------------
// Q&A types
// ---------------------------------------------------------------------------

export interface QAResult {
  answer: string;
  sources: QASource[];
}

export interface QASource {
  doc_id: number;
  title: string;
  snippet: string;
}

// ---------------------------------------------------------------------------
// Message types for extension <-> webview communication
// ---------------------------------------------------------------------------

export type ExtensionMessage =
  | { type: "documents"; data: Document[] }
  | { type: "document"; data: DocumentDetail }
  | { type: "tasks"; data: Task[] }
  | { type: "searchResults"; data: SearchResult[] }
  | { type: "qaAnswer"; data: QAResult }
  | { type: "status"; data: StatusData }
  | { type: "tags"; data: Tag[] }
  | { type: "error"; message: string }
  | { type: "loading"; loading: boolean };

export type WebviewMessage =
  | { type: "fetchDocuments"; limit?: number }
  | { type: "fetchDocument"; id: number }
  | { type: "searchDocuments"; query: string }
  | { type: "fetchTasks"; status?: string; epicKey?: string }
  | { type: "updateTaskStatus"; id: number; status: string }
  | { type: "askQuestion"; question: string }
  | { type: "saveDocument"; title: string; content: string; tags: string[] }
  | { type: "refresh" }
  | { type: "openExternal"; url: string };
