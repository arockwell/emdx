"""Standing queries (saved searches) for the find --watch feature."""

from __future__ import annotations

import json
import logging
from typing import cast

from rich.table import Table

from emdx.database.connection import db_connection
from emdx.database.types import StandingQueryMatch, StandingQueryRow
from emdx.utils.datetime_utils import parse_datetime
from emdx.utils.output import console

logger = logging.getLogger(__name__)


# ── CRUD operations ───────────────────────────────────────────────────


def create_standing_query(
    query: str,
    tags: str | None = None,
    project: str | None = None,
) -> int:
    """Save a new standing query and return its ID."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO standing_queries
                (query, tags, project, last_checked_at)
            VALUES (?, ?, ?, datetime('now', '-1 second'))
            """,
            (query, tags, project),
        )
        conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid


def list_standing_queries() -> list[StandingQueryRow]:
    """Return all standing queries ordered by creation date."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, query, tags, project,
                   created_at, last_checked_at, notify_count
            FROM standing_queries
            ORDER BY created_at DESC
            """
        )
        rows: list[StandingQueryRow] = []
        for row in cursor.fetchall():
            item = cast(StandingQueryRow, dict(row))
            for field in ("created_at", "last_checked_at"):
                val = item.get(field)  # type: ignore[arg-overload]
                if isinstance(val, str):
                    item[field] = parse_datetime(val)  # type: ignore[literal-required]
            rows.append(item)
        return rows


def remove_standing_query(query_id: int) -> bool:
    """Remove a standing query by ID. Returns True if deleted."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            "DELETE FROM standing_queries WHERE id = ?",
            (query_id,),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_standing_query(query_id: int) -> StandingQueryRow | None:
    """Get a single standing query by ID."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT id, query, tags, project,
                   created_at, last_checked_at, notify_count
            FROM standing_queries
            WHERE id = ?
            """,
            (query_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        item = cast(StandingQueryRow, dict(row))
        for field in ("created_at", "last_checked_at"):
            val = item.get(field)  # type: ignore[arg-overload]
            if isinstance(val, str):
                item[field] = parse_datetime(val)  # type: ignore[literal-required]
        return item


# ── Check for new matches ────────────────────────────────────────────


def check_standing_queries() -> list[StandingQueryMatch]:
    """Check all standing queries for new documents since last check.

    Updates last_checked_at and notify_count for queries that find
    new matches.  Returns a list of matches found across all queries.
    """
    queries = list_standing_queries()
    all_matches: list[StandingQueryMatch] = []

    with db_connection.get_connection() as conn:
        for sq in queries:
            last_checked = sq["last_checked_at"]
            # Format for SQLite comparison
            if last_checked is not None:
                last_checked_str: str = last_checked.strftime(  # type: ignore[union-attr]
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                last_checked_str = "1970-01-01 00:00:00"

            matches = _find_new_matches(conn, sq, last_checked_str)
            if matches:
                all_matches.extend(matches)
                conn.execute(
                    """
                    UPDATE standing_queries
                    SET last_checked_at = CURRENT_TIMESTAMP,
                        notify_count = notify_count + ?
                    WHERE id = ?
                    """,
                    (len(matches), sq["id"]),
                )
            else:
                conn.execute(
                    """
                    UPDATE standing_queries
                    SET last_checked_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (sq["id"],),
                )

        conn.commit()

    return all_matches


def _find_new_matches(
    conn: object,
    sq: StandingQueryRow,
    last_checked_str: str,
) -> list[StandingQueryMatch]:
    """Find documents created after last_checked_str matching the query."""
    import sqlite3

    assert isinstance(conn, sqlite3.Connection)

    query_text = sq["query"]
    matches: list[StandingQueryMatch] = []

    if query_text:
        from emdx.database.search import escape_fts5_query

        fts_query = escape_fts5_query(query_text)
        sql = """
            SELECT d.id, d.title, d.created_at
            FROM documents d
            JOIN documents_fts fts ON d.id = fts.rowid
            WHERE fts.documents_fts MATCH ?
              AND d.created_at > ?
              AND d.is_deleted = 0
              AND d.doc_type = 'user'
        """
        params: list[str | int] = [fts_query, last_checked_str]

        if sq["project"]:
            sql += " AND d.project = ?"
            params.append(sq["project"])

        sql += " ORDER BY d.created_at DESC LIMIT 50"

        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()

        if sq["tags"]:
            tag_list = [t.strip() for t in sq["tags"].split(",") if t.strip()]
            rows = _filter_rows_by_tags(conn, rows, tag_list)

        for row in rows:
            matches.append(
                StandingQueryMatch(
                    query_id=sq["id"],
                    query=query_text,
                    doc_id=row[0],
                    doc_title=row[1],
                    doc_created_at=row[2],
                )
            )

    elif sq["tags"]:
        tag_list = [t.strip() for t in sq["tags"].split(",") if t.strip()]
        placeholders = ",".join("?" * len(tag_list))
        sql = f"""
            SELECT DISTINCT d.id, d.title, d.created_at
            FROM documents d
            JOIN document_tags dt ON d.id = dt.document_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE t.name IN ({placeholders})
              AND d.created_at > ?
              AND d.is_deleted = 0
              AND d.doc_type = 'user'
        """
        params_tags: list[str | int] = [*tag_list, last_checked_str]

        if sq["project"]:
            sql += " AND d.project = ?"
            params_tags.append(sq["project"])

        sql += " ORDER BY d.created_at DESC LIMIT 50"

        cursor = conn.execute(sql, params_tags)
        for row in cursor.fetchall():
            matches.append(
                StandingQueryMatch(
                    query_id=sq["id"],
                    query=f"[tags: {sq['tags']}]",
                    doc_id=row[0],
                    doc_title=row[1],
                    doc_created_at=row[2],
                )
            )

    return matches


def _filter_rows_by_tags(
    conn: object,
    rows: list[object],
    tag_list: list[str],
) -> list[object]:
    """Filter rows to only include docs that have all specified tags."""
    import sqlite3

    assert isinstance(conn, sqlite3.Connection)

    filtered = []
    for row in rows:
        doc_id = row[0]  # type: ignore[index]
        placeholders = ",".join("?" * len(tag_list))
        cursor = conn.execute(
            f"""
            SELECT COUNT(DISTINCT t.name)
            FROM document_tags dt
            JOIN tags t ON dt.tag_id = t.id
            WHERE dt.document_id = ?
              AND t.name IN ({placeholders})
            """,
            [doc_id, *tag_list],
        )
        count = cursor.fetchone()[0]
        if count == len(tag_list):
            filtered.append(row)
    return filtered


# ── Display helpers ──────────────────────────────────────────────────


def display_standing_queries_list(
    json_output: bool = False,
) -> None:
    """Display all standing queries."""
    queries = list_standing_queries()

    if not queries:
        if json_output:
            print("[]")
        else:
            print("No standing queries. Use 'emdx find --watch \"query\"' to add one.")
        return

    if json_output:
        output = []
        for sq in queries:
            item = {
                "id": sq["id"],
                "query": sq["query"],
                "tags": sq["tags"],
                "project": sq["project"],
                "created_at": (sq["created_at"].isoformat() if sq["created_at"] else None),
                "last_checked_at": (
                    sq["last_checked_at"].isoformat() if sq["last_checked_at"] else None
                ),
                "notify_count": sq["notify_count"],
            }
            output.append(item)
        print(json.dumps(output, indent=2))
        return

    # Rich table output
    table = Table(title="Standing Queries")
    table.add_column("ID", style="cyan", justify="right")
    table.add_column("Query", style="bold")
    table.add_column("Tags", style="dim")
    table.add_column("Project", style="green")
    table.add_column("Last Checked", style="dim")
    table.add_column("Matches", justify="right")

    for sq in queries:
        last_checked = ""
        if sq["last_checked_at"]:
            lc = sq["last_checked_at"]
            last_checked = lc.strftime("%Y-%m-%d %H:%M")  # type: ignore[union-attr]

        table.add_row(
            str(sq["id"]),
            sq["query"] or "",
            sq["tags"] or "",
            sq["project"] or "",
            last_checked,
            str(sq["notify_count"]),
        )

    console.print(table)


def display_check_results(
    matches: list[StandingQueryMatch],
    json_output: bool = False,
) -> None:
    """Display results of checking standing queries."""
    if json_output:
        output = []
        for m in matches:
            output.append(
                {
                    "query_id": m["query_id"],
                    "query": m["query"],
                    "doc_id": m["doc_id"],
                    "doc_title": m["doc_title"],
                    "doc_created_at": m["doc_created_at"],
                }
            )
        print(json.dumps(output, indent=2))
        return

    if not matches:
        print("No new matches found for any standing queries.")
        return

    # Group matches by query
    by_query: dict[int, list[StandingQueryMatch]] = {}
    for m in matches:
        by_query.setdefault(m["query_id"], []).append(m)

    for query_id, query_matches in by_query.items():
        query_text = query_matches[0]["query"]
        print(f"\nQuery #{query_id}: {query_text}")
        print(f"  {len(query_matches)} new match(es):")
        for m in query_matches:
            print(f"    #{m['doc_id']} {m['doc_title']}")
