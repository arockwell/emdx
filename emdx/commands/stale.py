"""
Knowledge decay commands for emdx.

Provides staleness tracking to surface documents that need review:
- `emdx stale` - Show documents needing review, prioritized by urgency
- `emdx touch` - Reset staleness timer without incrementing view count
"""

from datetime import datetime
from enum import Enum
from typing import Any

import typer
from rich.table import Table

from emdx.database import db
from emdx.models.tags import get_tags_for_documents
from emdx.ui.formatting import format_tags
from emdx.utils.output import console
from emdx.utils.text_formatting import truncate_title

app = typer.Typer(help="Knowledge decay and staleness tracking")


class StalenessLevel(str, Enum):
    """Staleness urgency levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


# Tag weights for importance scoring
TAG_WEIGHTS: dict[str, float] = {
    "security": 3.0,
    "🔒": 3.0,  # security emoji
    "gameplan": 2.0,
    "🎯": 2.0,  # gameplan emoji
    "active": 2.0,
    "🟢": 2.0,  # active emoji
    "reference": 2.0,
    "📚": 2.0,  # reference emoji
}
DEFAULT_TAG_WEIGHT = 1.0


def _calculate_importance_score(view_count: int, tags: list[str]) -> float:
    """Calculate importance score for a document.

    Importance = (view_count * 1) + (tag_weight * 1.5), normalized 0-10.

    Args:
        view_count: Number of times document has been viewed
        tags: List of tags on the document

    Returns:
        Importance score from 0-10
    """
    # View contribution (cap at 50 views for normalization)
    view_score = min(view_count, 50) * 1.0

    # Tag contribution
    tag_score = 0.0
    for tag in tags:
        tag_lower = tag.lower()
        weight = TAG_WEIGHTS.get(tag, TAG_WEIGHTS.get(tag_lower, DEFAULT_TAG_WEIGHT))
        tag_score += weight * 1.5

    # Combine and normalize to 0-10
    raw_score = view_score + tag_score
    # Normalize: assume max reasonable score is ~60 (50 views + 3 high-weight tags)
    normalized = min(10.0, (raw_score / 60.0) * 10.0)

    return round(normalized, 1)


def _get_staleness_level(
    days_stale: int,
    importance: float,
    critical_days: int,
    warning_days: int,
    info_days: int,
) -> StalenessLevel | None:
    """Determine staleness level based on importance and days since access.

    Args:
        days_stale: Days since last access
        importance: Importance score (0-10)
        critical_days: Days threshold for high-importance docs
        warning_days: Days threshold for medium-importance docs
        info_days: Days threshold for low-importance docs

    Returns:
        StalenessLevel or None if not stale
    """
    # High importance (score >= 5): CRITICAL after critical_days
    if importance >= 5.0 and days_stale > critical_days:
        return StalenessLevel.CRITICAL

    # Medium importance (score 2-5): WARNING after warning_days
    if 2.0 <= importance < 5.0 and days_stale > warning_days:
        return StalenessLevel.WARNING

    # Low importance (score < 2): INFO after info_days (archive candidates)
    if importance < 2.0 and days_stale > info_days:
        return StalenessLevel.INFO

    return None


def _get_stale_documents(
    critical_days: int,
    warning_days: int,
    info_days: int,
    limit: int,
    project: str | None = None,
) -> list[dict[str, Any]]:
    """Query documents and calculate staleness.

    Args:
        critical_days: Days threshold for CRITICAL level
        warning_days: Days threshold for WARNING level
        info_days: Days threshold for INFO level
        limit: Maximum documents to return
        project: Optional project filter

    Returns:
        List of stale documents with staleness metadata
    """
    now = datetime.now()

    with db.get_connection() as conn:
        # Build query
        query = """
            SELECT id, title, project, accessed_at, access_count, created_at
            FROM documents
            WHERE is_deleted = FALSE AND archived_at IS NULL
        """
        params: list[Any] = []

        if project:
            query += " AND project = ?"
            params.append(project)

        # Order by last access (oldest first)
        query += " ORDER BY accessed_at ASC LIMIT ?"
        params.append(limit * 3)  # Get more than needed, filter by staleness

        cursor = conn.execute(query, params)
        rows = cursor.fetchall()

    # Get doc IDs for batch tag fetch
    doc_ids = [row[0] for row in rows]
    all_tags = get_tags_for_documents(doc_ids)

    stale_docs = []
    for row in rows:
        doc_id, title, doc_project, accessed_at, access_count, created_at = row

        # Parse accessed_at
        if isinstance(accessed_at, str):
            from emdx.utils.datetime_utils import parse_datetime
            accessed_at = parse_datetime(accessed_at)

        # Calculate days stale
        if accessed_at:
            days_stale = (now - accessed_at).days
        else:
            # Never accessed - use created_at
            if isinstance(created_at, str):
                from emdx.utils.datetime_utils import parse_datetime
                created_at = parse_datetime(created_at)
            days_stale = (now - created_at).days if created_at else 0

        # Get tags and calculate importance
        tags = all_tags.get(doc_id, [])
        importance = _calculate_importance_score(access_count, tags)

        # Determine staleness level
        level = _get_staleness_level(
            days_stale, importance, critical_days, warning_days, info_days
        )

        if level:
            stale_docs.append({
                "id": doc_id,
                "title": title,
                "project": doc_project,
                "accessed_at": accessed_at,
                "access_count": access_count,
                "tags": tags,
                "days_stale": days_stale,
                "importance": importance,
                "level": level,
            })

    # Sort by urgency: CRITICAL first, then WARNING, then INFO
    # Within level, sort by days_stale descending (oldest first)
    level_order = {StalenessLevel.CRITICAL: 0, StalenessLevel.WARNING: 1, StalenessLevel.INFO: 2}
    stale_docs.sort(key=lambda d: (level_order[d["level"]], -d["days_stale"]))

    return stale_docs[:limit]


@app.command("list")
def stale_list(
    critical_days: int = typer.Option(
        30, "--critical-days", help="Days threshold for high-importance docs"
    ),
    warning_days: int = typer.Option(
        14, "--warning-days", help="Days threshold for medium-importance docs"
    ),
    info_days: int = typer.Option(
        60, "--info-days", help="Days threshold for low-importance docs (archive candidates)"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum documents to show"),
    project: str | None = typer.Option(None, "--project", "-p", help="Filter by project"),
    level: str | None = typer.Option(
        None, "--level", "-l", help="Filter by level: critical, warning, info"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show documents needing review, prioritized by urgency.

    Staleness levels are determined by importance and time since last access:

    - CRITICAL: High importance (security, gameplans, active) stale > 30 days
    - WARNING: Medium importance stale > 14 days
    - INFO: Low importance stale > 60 days (archive candidates)

    Importance score = (view_count * 1) + (tag_weight * 1.5), normalized 0-10.
    Tag weights: security=3, gameplan=2, active=2, reference=2, default=1.

    Examples:
        emdx stale              # Show all stale documents
        emdx stale -l critical  # Show only critical ones
        emdx stale --critical-days 15  # Custom threshold
    """
    try:

        stale_docs = _get_stale_documents(
            critical_days=critical_days,
            warning_days=warning_days,
            info_days=info_days,
            limit=limit,
            project=project,
        )

        # Filter by level if specified
        if level:
            try:
                filter_level = StalenessLevel(level.lower())
                stale_docs = [d for d in stale_docs if d["level"] == filter_level]
            except ValueError:
                console.print(f"[red]Invalid level: {level}. Use: critical, warning, info[/red]")
                raise typer.Exit(1) from None

        if not stale_docs:
            console.print("[green]No stale documents found! Knowledge base is fresh.[/green]")
            return

        if json_output:
            import json
            output = []
            for doc in stale_docs:
                output.append({
                    "id": doc["id"],
                    "title": doc["title"],
                    "project": doc["project"],
                    "days_stale": doc["days_stale"],
                    "importance": doc["importance"],
                    "level": doc["level"].value,
                    "tags": doc["tags"],
                    "accessed_at": doc["accessed_at"].isoformat() if doc["accessed_at"] else None,
                })
            print(json.dumps(output, indent=2))
            return

        # Group by level for display
        by_level: dict[StalenessLevel, list[dict]] = {
            StalenessLevel.CRITICAL: [],
            StalenessLevel.WARNING: [],
            StalenessLevel.INFO: [],
        }
        for doc in stale_docs:
            by_level[doc["level"]].append(doc)

        # Display counts summary
        counts = {k.value: len(v) for k, v in by_level.items() if v}
        console.print(
            "\n[bold]📅 Stale Documents[/bold] - "
            + " | ".join(f"{k.upper()}: {v}" for k, v in counts.items())
        )
        console.print()

        # Create table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Level", width=10)
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="white")
        table.add_column("Days", justify="right", width=6)
        table.add_column("Importance", justify="right", width=10)
        table.add_column("Tags", style="dim")

        level_styles = {
            StalenessLevel.CRITICAL: "[bold red]CRITICAL[/bold red]",
            StalenessLevel.WARNING: "[yellow]WARNING[/yellow]",
            StalenessLevel.INFO: "[dim]INFO[/dim]",
        }

        for doc in stale_docs:
            table.add_row(
                level_styles[doc["level"]],
                str(doc["id"]),
                truncate_title(doc["title"], 40),
                str(doc["days_stale"]),
                f"{doc['importance']:.1f}",
                format_tags(doc["tags"][:3]) if doc["tags"] else "",
            )

        console.print(table)
        console.print()
        console.print("[dim]💡 Use 'emdx touch <id>' to mark as reviewed[/dim]")
        console.print("[dim]💡 Use 'emdx view <id>' to review (also resets staleness)[/dim]")

    except Exception as e:
        console.print(f"[red]Error listing stale documents: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def touch(
    identifiers: list[str] = typer.Argument(help="Document ID(s) to touch"),
) -> None:
    """Reset staleness timer without incrementing view count.

    This marks documents as reviewed without counting as a "view".
    Use this when you've verified a document is still current.

    Examples:
        emdx touch 42           # Touch single document
        emdx touch 42 43 44     # Touch multiple documents
    """
    try:

        touched = []
        not_found = []

        with db.get_connection() as conn:
            for identifier in identifiers:
                identifier_str = str(identifier)

                if identifier_str.isdigit():
                    cursor = conn.execute(
                        """
                        UPDATE documents
                        SET accessed_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND is_deleted = FALSE
                        """,
                        (int(identifier_str),),
                    )
                else:
                    cursor = conn.execute(
                        """
                        UPDATE documents
                        SET accessed_at = CURRENT_TIMESTAMP
                        WHERE LOWER(title) = LOWER(?) AND is_deleted = FALSE
                        """,
                        (identifier_str,),
                    )

                if cursor.rowcount > 0:
                    touched.append(identifier)
                else:
                    not_found.append(identifier)

            conn.commit()

        if touched:
            ids = ", ".join(str(t) for t in touched)
            console.print(f"[green]✅ Touched {len(touched)} document(s):[/green] {ids}")

        if not_found:
            console.print(f"[yellow]⚠ Not found: {', '.join(str(n) for n in not_found)}[/yellow]")

        if not touched and not_found:
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]Error touching documents: {e}[/red]")
        raise typer.Exit(1) from e


def get_top_stale_for_priming(
    limit: int = 3,
    critical_days: int = 30,
    warning_days: int = 14,
    info_days: int = 60,
) -> list[dict[str, Any]]:
    """Get top stale documents for inclusion in prime context.

    This function is designed for integration with `emdx prime --smart`.
    Returns only CRITICAL and WARNING level documents.

    Args:
        limit: Maximum documents to return
        critical_days: Days threshold for CRITICAL level
        warning_days: Days threshold for WARNING level
        info_days: Days threshold for INFO level

    Returns:
        List of stale document dicts with id, title, level, days_stale
    """
    stale_docs = _get_stale_documents(
        critical_days=critical_days,
        warning_days=warning_days,
        info_days=info_days,
        limit=limit * 2,  # Get more, filter to critical/warning
    )

    # Only return CRITICAL and WARNING for priming
    urgent = [
        d for d in stale_docs
        if d["level"] in (StalenessLevel.CRITICAL, StalenessLevel.WARNING)
    ]

    return urgent[:limit]
