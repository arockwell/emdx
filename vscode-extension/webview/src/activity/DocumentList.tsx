import { useCallback, useRef, useEffect, useState } from "react";
import type { DocumentSummary } from "./ActivityView";

interface DocumentListProps {
  documents: DocumentSummary[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

function relativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;

  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;

  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;

  const diffMonths = Math.floor(diffDays / 30);
  if (diffMonths < 12) return `${diffMonths}mo ago`;

  const diffYears = Math.floor(diffDays / 365);
  return `${diffYears}y ago`;
}

function docTypeIcon(docType: string): string {
  switch (docType) {
    case "epic":
      return "\u{1F4DA}"; // books
    case "task":
      return "\u{2611}\u{FE0F}"; // ballot box with check
    default:
      return "\u{1F4C4}"; // page facing up
  }
}

export function DocumentList({ documents, selectedId, onSelect }: DocumentListProps) {
  const [focusIndex, setFocusIndex] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);
  const rowRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  // Reset focus index when document list changes
  useEffect(() => {
    setFocusIndex(0);
  }, [documents]);

  // Scroll focused row into view
  useEffect(() => {
    if (documents.length > 0 && documents[focusIndex]) {
      const row = rowRefs.current.get(documents[focusIndex].id);
      row?.scrollIntoView({ block: "nearest" });
    }
  }, [focusIndex, documents]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (documents.length === 0) return;

      switch (e.key) {
        case "ArrowDown":
        case "j":
          e.preventDefault();
          setFocusIndex((prev) => Math.min(prev + 1, documents.length - 1));
          break;
        case "ArrowUp":
        case "k":
          e.preventDefault();
          setFocusIndex((prev) => Math.max(prev - 1, 0));
          break;
        case "Enter":
          e.preventDefault();
          if (documents[focusIndex]) {
            onSelect(documents[focusIndex].id);
          }
          break;
      }
    },
    [documents, focusIndex, onSelect]
  );

  if (documents.length === 0) {
    return (
      <div className="empty-state">
        <p>No documents found</p>
      </div>
    );
  }

  return (
    <div
      ref={listRef}
      className="document-list"
      tabIndex={0}
      onKeyDown={handleKeyDown}
      role="listbox"
      aria-label="Documents"
    >
      {documents.map((doc, index) => (
        <div
          key={doc.id}
          ref={(el) => {
            if (el) rowRefs.current.set(doc.id, el);
          }}
          className={[
            "document-row",
            doc.id === selectedId ? "selected" : "",
            index === focusIndex ? "focused" : "",
          ]
            .filter(Boolean)
            .join(" ")}
          onClick={() => onSelect(doc.id)}
          role="option"
          aria-selected={doc.id === selectedId}
        >
          <span className="doc-icon">{docTypeIcon(doc.doc_type)}</span>
          <div className="doc-info">
            <span className="doc-title">{doc.title}</span>
            <span className="doc-meta">
              <span className="doc-time">{relativeTime(doc.updated_at)}</span>
              {doc.tags.length > 0 && (
                <span className="doc-tags">
                  {doc.tags.map((tag) => (
                    <span key={tag} className="badge">
                      {tag}
                    </span>
                  ))}
                </span>
              )}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
