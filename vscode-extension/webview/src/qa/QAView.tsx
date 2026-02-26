import { useState, useEffect, useRef } from "react";
import { postMessage, useVscodeMessage } from "../hooks/useVscode";
import type { ExtensionMessage } from "../types";

interface HistoryEntry {
  question: string;
  answer: string;
  timestamp: Date;
}

export function QAView() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [selectedHistoryIndex, setSelectedHistoryIndex] = useState(-1);
  const answerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useVscodeMessage<ExtensionMessage>((msg) => {
    switch (msg.type) {
      case "qaAnswer":
        setAnswer(msg.data.answer);
        setHistory((prev) => [
          { question, answer: msg.data.answer, timestamp: new Date() },
          ...prev,
        ]);
        setLoading(false);
        break;
      case "loading":
        setLoading(msg.loading);
        break;
      case "error":
        setError(msg.message);
        setLoading(false);
        break;
    }
  });

  useEffect(() => {
    if (answerRef.current && answer) {
      answerRef.current.scrollTop = 0;
    }
  }, [answer]);

  const handleSubmit = () => {
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    setError(null);
    setAnswer(null);
    postMessage({ type: "askQuestion", question: trimmed });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const selectHistoryItem = (index: number) => {
    setSelectedHistoryIndex(index);
    const entry = history[index];
    if (entry) {
      setAnswer(entry.answer);
      setQuestion(entry.question);
    }
  };

  const linkifyDocRefs = (text: string): string => {
    return text.replace(/#(\d+)/g, '<a href="#" class="doc-ref" data-doc-id="$1">#$1</a>');
  };

  return (
    <div className="qa-view">
      <div className="qa-input-bar">
        <input
          ref={inputRef}
          type="text"
          className="qa-input"
          placeholder="Ask a question about your knowledge base..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
        <button
          className="qa-submit"
          onClick={handleSubmit}
          disabled={loading || !question.trim()}
        >
          {loading ? "..." : "Ask"}
        </button>
      </div>

      {error && <div className="qa-error">{error}</div>}

      <div className="qa-content">
        <div className="qa-answer-area" ref={answerRef}>
          {loading && (
            <div className="qa-loading">
              <span className="spinner" />
              Searching knowledge base...
            </div>
          )}
          {answer && !loading && (
            <div
              className="qa-answer"
              dangerouslySetInnerHTML={{ __html: linkifyDocRefs(answer) }}
            />
          )}
          {!answer && !loading && (
            <div className="qa-empty">
              Ask a question to search your knowledge base using RAG.
            </div>
          )}
        </div>

        {history.length > 0 && (
          <div className="qa-history">
            <div className="qa-history-header">History</div>
            {history.map((entry, i) => (
              <div
                key={i}
                className={`qa-history-item ${i === selectedHistoryIndex ? "selected" : ""}`}
                onClick={() => selectHistoryItem(i)}
              >
                <span className="qa-history-question">{entry.question}</span>
                <span className="qa-history-time">
                  {entry.timestamp.toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
