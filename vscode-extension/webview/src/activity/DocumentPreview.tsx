import { useCallback } from "react";
import Markdown from "react-markdown";
import { postMessage } from "../hooks/useVscode";
import type { DocumentDetail } from "./ActivityView";

interface DocumentPreviewProps {
  document: DocumentDetail | null;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function DocumentPreview({ document }: DocumentPreviewProps) {
  const handleLinkedDocClick = useCallback((id: number) => {
    postMessage({ type: "fetchDocument", id });
  }, []);

  if (!document) {
    return (
      <div className="empty-state">
        <p>Select a document to preview</p>
      </div>
    );
  }

  return (
    <div className="document-preview">
      <header className="preview-header">
        <h2 className="preview-title">{document.title}</h2>
        <div className="preview-meta">
          <span className="meta-item">
            Created: {formatDate(document.created_at)}
          </span>
          <span className="meta-item">
            {document.word_count.toLocaleString()} words
          </span>
          {document.tags.length > 0 && (
            <span className="meta-tags">
              {document.tags.map((tag) => (
                <span key={tag} className="badge">
                  {tag}
                </span>
              ))}
            </span>
          )}
        </div>
      </header>

      <div className="preview-content">
        <Markdown>{document.content}</Markdown>
      </div>

      {document.linked_docs.length > 0 && (
        <footer className="preview-links">
          <h3 className="links-heading">Linked Documents</h3>
          <div className="link-chips">
            {document.linked_docs.map((linked) => (
              <button
                key={linked.doc_id}
                className="link-chip"
                onClick={() => handleLinkedDocClick(linked.doc_id)}
                title={linked.title}
              >
                #{linked.doc_id} {linked.title}
              </button>
            ))}
          </div>
        </footer>
      )}
    </div>
  );
}
