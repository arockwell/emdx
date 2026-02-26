import { useState, useCallback, useRef, useEffect } from "react";
import { useVscodeMessage, postMessage } from "../hooks/useVscode";
import { DocumentList } from "./DocumentList";
import { DocumentPreview } from "./DocumentPreview";

export interface DocumentSummary {
  id: number;
  title: string;
  project: string | null;
  access_count: number;
  accessed_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  content: string;
  tags: string[];
  word_count: number;
  created_at: string;
  updated_at: string;
  linked_docs: Array<{ doc_id: number; title: string }>;
}

type IncomingMessage =
  | { type: "documents"; data: DocumentSummary[] }
  | { type: "document"; data: DocumentDetail }
  | { type: "searchResults"; data: DocumentSummary[] }
  | { type: "loading"; data: boolean }
  | { type: "error"; data: string };

export function ActivityView() {
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<DocumentDetail | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Request initial documents on mount
  useEffect(() => {
    postMessage({ type: "fetchDocuments" });
  }, []);

  // Handle messages from the extension host
  const handleMessage = useCallback((msg: IncomingMessage) => {
    switch (msg.type) {
      case "documents":
        setDocuments(msg.data);
        setLoading(false);
        break;
      case "document":
        setSelectedDoc(msg.data);
        setLoading(false);
        break;
      case "searchResults":
        setDocuments(msg.data);
        setLoading(false);
        break;
      case "loading":
        setLoading(msg.data);
        break;
      case "error":
        setError(msg.data);
        setLoading(false);
        break;
    }
  }, []);

  useVscodeMessage(handleMessage);

  const handleSearch = useCallback((value: string) => {
    setSearchQuery(value);
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => {
      if (value.trim()) {
        postMessage({ type: "searchDocuments", query: value.trim() });
      } else {
        postMessage({ type: "fetchDocuments" });
      }
    }, 300);
  }, []);

  const handleSelect = useCallback((id: number) => {
    setLoading(true);
    postMessage({ type: "fetchDocument", id });
  }, []);

  return (
    <div className="panel-container">
      <div className="search-bar">
        <input
          type="text"
          className="search-input"
          placeholder="Search documents..."
          value={searchQuery}
          onChange={(e) => handleSearch(e.target.value)}
          aria-label="Search documents"
        />
        {loading && <span className="search-spinner" aria-label="Loading" />}
      </div>

      {error && (
        <div className="error-banner" role="alert">
          {error}
          <button
            className="error-dismiss"
            onClick={() => setError(null)}
            aria-label="Dismiss error"
          >
            x
          </button>
        </div>
      )}

      <div className="split-layout">
        <div className="list-pane">
          <DocumentList
            documents={documents}
            selectedId={selectedDoc?.id ?? null}
            onSelect={handleSelect}
          />
        </div>
        <div className="preview-pane">
          <DocumentPreview document={selectedDoc} />
        </div>
      </div>
    </div>
  );
}
