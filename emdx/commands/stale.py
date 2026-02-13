"""
Knowledge Decay command - Surface stale documents that need review.

Uses heuristic scoring to identify important documents that haven't been
viewed recently, prioritizing them for review.

Scoring:
- Importance = (view_count × 1) + (tag_weight × 1.5)
- Tag weights: security=3, gameplan=2, active=2, reference=2, default=1
- Staleness = days since last viewed
- Urgency tiers based on importance × staleness
"""

from datetime import datetime
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from ..database import db
from ..models.tags import get_tags_for_documents

console = Console()

# Tag weights for importance scoring (emoji → weight)
# Higher weight = more important to review regularly
TAG_WEIGHTS: dict[str, float] = {
    "🔐": 3.0,  # security
    "🛡️": 3.0,  # security alias
    "🎯": 2.0,  # gameplan
    "🚀": 2.0,  # active
    "📚": 2.0,  # reference
    "📖": 2.0,  # documentation
    "🏗️": 1.5,  # architecture
    "⚠️": 1.5,  # warning/important
}

# Text aliases that map to the same weights
TAG_WEIGHT_ALIASES: dict[str, float] = {
    "security": 3.0,
    "gameplan": 2.0,
    "active": 2.0,
    "reference": 2.0,
    "documentation": 2.0,
    "architecture": 1.5,
    "important": 1.5,
}

# Thresholds for urgency tiers
# CRITICAL: importance > 6 AND staleness > 30 days
# WARNING: importance > 4 AND staleness > 14 days
# INFO: importance < 3 AND staleness > 60 days (archive candidates)
CRITICAL_IMPORTANCE_THRESHOLD = 6.0
CRITICAL_STALENESS_DAYS = 30
WARNING_IMPORTANCE_THRESHOLD = 4.0
WARNING_STALENESS_DAYS = 14
INFO_IMPORTANCE_THRESHOLD = 3.0
INFO_STALENESS_DAYS = 60


def get_tag_weight(tag: str) -> float:
    """Get the weight for a tag (emoji or text alias)."""
    # Check emoji weights first
    if tag in TAG_WEIGHTS:
        return TAG_WEIGHTS[tag]
    # Check text aliases
    tag_lower = tag.lower()
    if tag_lower in TAG_WEIGHT_ALIASES:
        return TAG_WEIGHT_ALIASES[tag_lower]
    return 1.0  # default weight


def calculate_importance(view_count: int, tags: list[str]) -> float:
    """Calculate importance score for a document.

    Score = (view_count × 1) + (sum of tag weights × 1.5)
    Normalized to 0-10 scale.
    """
    view_score = min(view_count, 20)  # Cap view contribution at 20
    tag_score = sum(get_tag_weight(tag) for tag in tags) * 1.5

    raw_score = view_score + tag_score
    # Normalize to 0-10 scale (assuming max of ~35 raw score)
    normalized = min(raw_score / 3.5, 10.0)
    return round(normalized, 1)


def calculate_staleness(last_accessed: Optional[datetime]) -> int:
    """Calculate staleness in days since last access."""
    if last_accessed is None:
        return 999  # Very stale if never accessed
    now = datetime.utcnow()
    # Handle both aware and naive datetimes
    if last_accessed.tzinfo is not None:
        last_accessed = last_accessed.replace(tzinfo=None)
    delta = now - last_accessed
    return max(0, delta.days)


def get_urgency_tier(importance: float, staleness_days: int) -> str:
    """Determine urgency tier based on importance and staleness."""
    if importance > CRITICAL_IMPORTANCE_THRESHOLD and staleness_days > CRITICAL_STALENESS_DAYS:
        return "CRITICAL"
    elif importance > WARNING_IMPORTANCE_THRESHOLD and staleness_days > WARNING_STALENESS_DAYS:
        return "WARNING"
    elif importance < INFO_IMPORTANCE_THRESHOLD and staleness_days > INFO_STALENESS_DAYS:
        return "INFO"
    return "OK"


def get_stale_documents(
    project: Optional[str] = None,
    limit: int = 50,
    min_staleness_days: int = 7,
) -> list[dict]:
    """Get documents sorted by urgency (importance × staleness).

    Returns documents with their importance score, staleness, and urgency tier.
    """
    with db.get_connection() as conn:
        # Build query
        conditions = ["is_deleted = FALSE", "archived_at IS NULL"]
        params: list = []

        if project:
            conditions.append("project = ?")
            params.append(project)

        where_clause = " AND ".join(conditions)
        params.append(limit * 3)  # Fetch more to filter

        cursor = conn.execute(
            f"""
            SELECT id, title, project, accessed_at, access_count, created_at
            FROM documents
            WHERE {where_clause}
            ORDER BY accessed_at ASC NULLS FIRST
            LIMIT ?
            """,
            params,
        )

        rows = cursor.fetchall()

    # Get tags for all documents
    doc_ids = [row["id"] for row in rows]
    tags_map = get_tags_for_documents(doc_ids)

    # Calculate scores and filter
    results = []
    for row in rows:
        doc_id = row["id"]
        tags = tags_map.get(doc_id, [])
        view_count = row["access_count"] or 0

        # Parse accessed_at
        accessed_at = row["accessed_at"]
        if isinstance(accessed_at, str):
            try:
                accessed_at = datetime.fromisoformat(accessed_at.replace("Z", "+00:00"))
            except Exception:
                accessed_at = None

        staleness_days = calculate_staleness(accessed_at)
        importance = calculate_importance(view_count, tags)
        urgency = get_urgency_tier(importance, staleness_days)

        # Only include if stale enough
        if staleness_days < min_staleness_days:
            continue

        # Skip "OK" documents unless they're very stale
        if urgency == "OK" and staleness_days < 30:
            continue

        results.append({
            "id": doc_id,
            "title": row["title"],
            "project": row["project"],
            "staleness_days": staleness_days,
            "importance": importance,
            "urgency": urgency,
            "view_count": view_count,
            "tags": tags,
        })

    # Sort by urgency priority, then by staleness × importance
    urgency_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2, "OK": 3}
    results.sort(
        key=lambda x: (
            urgency_order.get(x["urgency"], 3),
            -(x["staleness_days"] * x["importance"]),
        )
    )

    return results[:limit]


def stale(
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Filter by project"
    ),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum results to show"),
    min_days: int = typer.Option(
        7, "--min-days", "-d", help="Minimum staleness in days"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show stale documents that need review.

    Uses importance scoring (views + tags) and staleness (days since access)
    to identify documents that may need attention.

    Urgency tiers:
    - CRITICAL: High importance docs (security, gameplans) stale > 30 days
    - WARNING: Medium importance docs stale > 14 days
    - INFO: Low importance docs stale > 60 days (archive candidates)

    Examples:
        emdx stale
        emdx stale --project myproject
        emdx stale --min-days 30
    """
    docs = get_stale_documents(project=project, limit=limit, min_staleness_days=min_days)

    if not docs:
        console.print("[green]✨ No stale documents found![/green]")
        console.print("[dim]All important documents have been recently reviewed.[/dim]")
        return

    if json_output:
        import json
        print(json.dumps(docs, indent=2, default=str))
        return

    # Group by urgency tier
    critical = [d for d in docs if d["urgency"] == "CRITICAL"]
    warning = [d for d in docs if d["urgency"] == "WARNING"]
    info = [d for d in docs if d["urgency"] == "INFO"]

    console.print()
    console.print("[bold]📚 Docs needing review:[/bold]")
    console.print()

    if critical:
        console.print("[bold red]🚨 CRITICAL[/bold red] (high importance, long stale):")
        for doc in critical:
            _print_doc_row(doc, "red")
        console.print()

    if warning:
        console.print("[bold yellow]⚠️  WARNING[/bold yellow] (medium importance, getting stale):")
        for doc in warning:
            _print_doc_row(doc, "yellow")
        console.print()

    if info:
        console.print("[bold blue]ℹ️  INFO[/bold blue] (low importance, very stale — archive candidates):")
        for doc in info:
            _print_doc_row(doc, "blue")
        console.print()

    # Summary
    total = len(docs)
    console.print(f"[dim]Found {total} stale document(s)[/dim]")
    console.print()
    console.print("[dim]Commands:[/dim]")
    console.print("  [cyan]emdx view <id>[/cyan]    — Review a document (resets staleness)")
    console.print("  [cyan]emdx touch <id>[/cyan]   — Mark as reviewed without opening")
    console.print("  [cyan]emdx archive <id>[/cyan] — Archive low-value documents")
    console.print()


def _print_doc_row(doc: dict, color: str):
    """Print a single document row with metadata."""
    doc_id = doc["id"]
    title = doc["title"][:50]
    if len(doc["title"]) > 50:
        title += "..."
    staleness = doc["staleness_days"]
    importance = doc["importance"]
    view_count = doc["view_count"]
    tags = doc["tags"]

    # Format tags (show first few)
    tags_str = " ".join(tags[:3]) if tags else ""
    if len(tags) > 3:
        tags_str += f" +{len(tags) - 3}"

    console.print(
        f"  [cyan]#{doc_id}[/cyan] [bold]{title}[/bold] "
        f"[dim]— {staleness}d stale, {view_count} views, importance: {importance}[/dim]"
    )
    if tags_str:
        console.print(f"       [dim]Tags: {tags_str}[/dim]")
    console.print(f"       [dim]Action: [cyan]emdx view {doc_id}[/cyan][/dim]")


# Create typer app for the command
app = typer.Typer()
app.command(name="stale")(stale)
