// EMDX VSCode Extension Types
// TypeScript interfaces mirroring the EMDX Python TypedDicts for CLI --json output.

// ---------------------------------------------------------------------------
// Document types
// ---------------------------------------------------------------------------

export interface Document {
  id: number;
  title: string;
  project: string | null;
  created_at: string;
  updated_at: string;
  accessed_at: string;
  access_count: number;
  doc_type: string; // "user" | "wiki"
  tags: string[];
}

export interface DocumentDetail extends Document {
  content: string;
  links: DocumentLink[];
  word_count?: number;
  parent_id: number | null;
}

export interface DocumentLink {
  doc_id: number;
  title: string;
  similarity_score: number;
  method: string;
}

export interface SearchResult {
  id: number;
  title: string;
  project: string | null;
  snippet: string;
  rank: number;
  tags: string[];
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Task types
// ---------------------------------------------------------------------------

export type TaskStatus = "open" | "active" | "blocked" | "done" | "failed" | "wontdo";

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
}

export interface TaskDependency {
  id: number;
  title: string;
  status: TaskStatus;
}

// ---------------------------------------------------------------------------
// Tag types
// ---------------------------------------------------------------------------

export interface Tag {
  name: string;
  count: number;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Status types
// ---------------------------------------------------------------------------

export interface KBStatus {
  documents: {
    total: number;
    user_created: number;
    delegate_created: number;
  };
  tasks: {
    open: number;
    active: number;
    done: number;
    blocked: number;
    failed: number;
  };
  delegate_activity: {
    total_executions: number;
    success_count: number;
    failure_count: number;
  };
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
  | { type: "status"; data: KBStatus }
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
