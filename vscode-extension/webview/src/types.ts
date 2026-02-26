// Shared types between extension host and webview.
// Mirrors the types in src/types.ts — keep in sync with actual emdx CLI JSON output.

export interface Document {
  id: number;
  title: string;
  project: string | null;
  access_count: number;
  accessed_at: string;
}

export interface DocumentDetail {
  id: number;
  title: string;
  content: string;
  project: string | null;
  tags: string[];
  linked_docs: Array<{ doc_id: number; title: string; similarity_score: number; method: string }>;
  word_count: number;
  char_count: number;
  line_count: number;
  access_count: number;
  accessed_at: string;
  created_at: string;
  updated_at: string;
  parent_id: number | null;
}

export interface SearchResult {
  id: number;
  title: string;
  project: string | null;
  score: number;
  keyword_score?: number;
  source: string;
  tags: string[];
}

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
  project: string | null;
  type: string;
}

export interface Tag {
  id: number;
  name: string;
  count: number;
  created_at: string;
  last_used: string;
}

export interface QAResult {
  answer: string;
  sources: QASource[];
}

export interface QASource {
  doc_id: number;
  title: string;
  snippet: string;
}

export interface StatusData {
  active: Task[];
  recent: Task[];
  failed: Task[];
}

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
