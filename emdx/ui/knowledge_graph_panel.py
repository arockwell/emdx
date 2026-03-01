"""Knowledge Graph Panel — shows linked docs, entities, and wiki topics.

Displayed in the ActivityView when toggled with `g`. Lazy-loads data
only when visible and caches the current doc_id to skip redundant reloads.
"""

from __future__ import annotations

import logging
from typing import Any

from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import RichLog, Static

logger = logging.getLogger(__name__)

# Sentinel for "no document loaded yet" (distinct from None = "no selection")
_NOT_LOADED = -1

# Monotonic counter for globally unique widget IDs
_widget_counter = 0


def _next_id(prefix: str) -> str:
    """Generate a globally unique widget ID to avoid DuplicateIds."""
    global _widget_counter
    _widget_counter += 1
    return f"{prefix}-{_widget_counter}"


# Entity type icons for display
ENTITY_TYPE_ICONS: dict[str, str] = {
    "person": "P",
    "organization": "O",
    "technology": "T",
    "concept": "C",
    "location": "L",
    "event": "E",
    "project": "J",
    "tool": "W",
    "library": "B",
    "framework": "F",
    "language": "G",
    "protocol": "R",
    "api": "A",
    "service": "S",
    "database": "D",
}


class KnowledgeGraphPanel(Widget):
    """Panel showing knowledge graph data for a selected document.

    Three sections:
    - Linked Documents: from document_links table, clickable
    - Entities: from document_entities table, grouped by type
    - Wiki Topics: from wiki_topic_members joined to wiki_topics
    """

    DEFAULT_CSS = """
    KnowledgeGraphPanel {
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    .graph-section-header {
        height: 1;
        background: $surface;
        padding: 0 1;
    }

    .graph-section-content {
        height: 1fr;
        min-height: 3;
    }

    .graph-scroll {
        height: 1fr;
    }

    .graph-log {
        padding: 0 1;
    }
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._current_doc_id: int | None = _NOT_LOADED
        self._scroll_id = _next_id("graph-scroll")
        self._log_id = _next_id("graph-log")

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("KNOWLEDGE GRAPH", classes="graph-section-header")
            with ScrollableContainer(id=self._scroll_id, classes="graph-scroll"):
                yield RichLog(
                    id=self._log_id,
                    classes="graph-log",
                    highlight=True,
                    markup=True,
                    wrap=True,
                    auto_scroll=False,
                )

    def _get_log(self) -> RichLog | None:
        """Get the RichLog widget safely."""
        try:
            return self.query_one(f"#{self._log_id}", RichLog)
        except Exception:
            return None

    def load_for_document(self, doc_id: int | None) -> None:
        """Load knowledge graph data for a document.

        Skips reload if doc_id hasn't changed (cache).
        """
        if doc_id == self._current_doc_id:
            return
        self._current_doc_id = doc_id

        log = self._get_log()
        if log is None:
            return

        log.clear()

        if doc_id is None:
            log.write("[dim]Select a document to see its knowledge graph[/dim]")
            return

        self._render_linked_documents(log, doc_id)
        self._render_entities(log, doc_id)
        self._render_wiki_topics(log, doc_id)

    def _render_linked_documents(self, log: RichLog, doc_id: int) -> None:
        """Render linked documents section."""
        try:
            from emdx.database.document_links import get_links_for_document

            links = get_links_for_document(doc_id)
        except ImportError:
            return
        except Exception as e:
            logger.warning(f"Error loading linked docs: {e}")
            return

        log.write("[bold]Linked Documents[/bold]")

        if not links:
            log.write("[dim]  No linked documents[/dim]")
            log.write("")
            return

        for link in links[:10]:
            if link["source_doc_id"] == doc_id:
                other_id = link["target_doc_id"]
                other_title = link["target_title"]
            else:
                other_id = link["source_doc_id"]
                other_title = link["source_title"]

            score = link.get("similarity_score", 0)
            method = link.get("method", "")
            title_trunc = (other_title or "")[:40]

            line = Text("  ")
            click_style = Style(
                bold=True,
                underline=True,
                color="bright_cyan",
                meta={"@click": f"app.select_doc({other_id})"},
            )
            line.append(f"#{other_id}", style=click_style)
            line.append(f" {title_trunc}")
            suffix_parts: list[str] = []
            if score:
                suffix_parts.append(f"{int(score * 100)}%")
            if method:
                suffix_parts.append(method)
            if suffix_parts:
                line.append(f" [{' '.join(suffix_parts)}]", style="dim")
            log.write(line)

        log.write("")

    def _render_entities(self, log: RichLog, doc_id: int) -> None:
        """Render entities section, grouped by type."""
        try:
            from emdx.database.connection import db_connection

            with db_connection.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT entity, entity_type, confidence "
                    "FROM document_entities "
                    "WHERE document_id = ? "
                    "ORDER BY entity_type, confidence DESC",
                    (doc_id,),
                )
                rows = cursor.fetchall()
        except Exception as e:
            logger.warning(f"Error loading entities: {e}")
            return

        log.write("[bold]Entities[/bold]")

        if not rows:
            log.write("[dim]  No entities extracted[/dim]")
            log.write("")
            return

        # Group by entity_type
        grouped: dict[str, list[tuple[str, float]]] = {}
        for row in rows:
            entity_type = str(row[1])
            entity_name = str(row[0])
            confidence = float(row[2]) if row[2] else 1.0
            if entity_type not in grouped:
                grouped[entity_type] = []
            grouped[entity_type].append((entity_name, confidence))

        for entity_type, entities in grouped.items():
            icon = ENTITY_TYPE_ICONS.get(entity_type, "?")
            line = Text(f"  [{icon}] ", style="bold")
            line.append(f"{entity_type}: ", style="dim")
            entity_names = [e[0] for e in entities[:5]]
            line.append(", ".join(entity_names))
            if len(entities) > 5:
                line.append(f" (+{len(entities) - 5})", style="dim")
            log.write(line)

        log.write("")

    def _render_wiki_topics(self, log: RichLog, doc_id: int) -> None:
        """Render wiki topics section."""
        try:
            from emdx.database.connection import db_connection

            with db_connection.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT t.id, t.topic_label, m.relevance_score "
                    "FROM wiki_topic_members m "
                    "JOIN wiki_topics t ON m.topic_id = t.id "
                    "WHERE m.document_id = ? AND t.status = 'active' "
                    "ORDER BY m.relevance_score DESC",
                    (doc_id,),
                )
                rows = cursor.fetchall()
        except Exception as e:
            logger.warning(f"Error loading wiki topics: {e}")
            return

        log.write("[bold]Wiki Topics[/bold]")

        if not rows:
            log.write("[dim]  No wiki topics[/dim]")
            log.write("")
            return

        for row in rows:
            topic_label = str(row[1])
            relevance = float(row[2]) if row[2] else 0.0
            line = Text("  ")
            line.append(topic_label)
            if relevance:
                line.append(f" {int(relevance * 100)}%", style="dim")
            log.write(line)

        log.write("")

    def clear_panel(self) -> None:
        """Clear the panel and reset cached doc_id."""
        self._current_doc_id = _NOT_LOADED
        log = self._get_log()
        if log is not None:
            log.clear()
            log.write("[dim]Press [bold]g[/bold] to toggle graph panel[/dim]")
