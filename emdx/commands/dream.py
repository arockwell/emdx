"""
Dream Journal - Overnight KB consolidation for EMDX.

Processes the knowledge base like a brain during sleep:
- Detects duplicate and similar documents
- Identifies patterns across tags and projects
- Flags hygiene issues (untagged, empty, stale docs)
- Generates a concise digest with actionable recommendations
"""

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import typer
from rich import box
from rich.markdown import Markdown
from rich.panel import Panel

from ..database import db
from ..database.documents import save_document
from ..services.similarity import SimilarityService
from ..utils.output import console


@dataclass
class MergeCandidate:
    """A pair of documents that could be merged."""

    doc1_id: int
    doc2_id: int
    doc1_title: str
    doc2_title: str
    similarity: float


@dataclass
class TagPattern:
    """A discovered pattern in tag usage."""

    tag_name: str
    doc_count: int
    projects: List[str]
    insight: str


@dataclass
class HygieneIssue:
    """A KB hygiene issue that needs attention."""

    issue_type: str  # 'untagged', 'no_project', 'empty', 'stale'
    doc_id: int
    doc_title: str
    detail: str


@dataclass
class DreamDigest:
    """The complete dream journal digest."""

    date: datetime
    docs_processed: int
    merge_candidates: List[MergeCandidate] = field(default_factory=list)
    tag_patterns: List[TagPattern] = field(default_factory=list)
    hygiene_issues: List[HygieneIssue] = field(default_factory=list)
    cross_project_patterns: List[str] = field(default_factory=list)


def _find_merge_candidates(
    days: int = 7, threshold: float = 0.8, limit: int = 20
) -> List[MergeCandidate]:
    """Find documents with high similarity that could be merged.

    Args:
        days: Only check docs modified in the last N days
        threshold: Minimum similarity threshold (0.8 = 80%)
        limit: Maximum number of candidates to return

    Returns:
        List of merge candidate pairs
    """
    try:
        service = SimilarityService()

        # Find all duplicate pairs
        pairs = service.find_all_duplicate_pairs(
            min_similarity=threshold,
            exclude_workflow=True,  # Skip workflow outputs
        )

        # Filter to recent documents and limit results
        cutoff = datetime.now() - timedelta(days=days)
        candidates = []

        with db.get_connection() as conn:
            for doc1_id, doc2_id, title1, title2, similarity in pairs[:limit * 2]:
                # Check if at least one doc was modified recently
                cursor = conn.execute(
                    """
                    SELECT MAX(updated_at) as last_update
                    FROM documents
                    WHERE id IN (?, ?) AND is_deleted = 0
                    """,
                    (doc1_id, doc2_id),
                )
                row = cursor.fetchone()
                if row and row["last_update"]:
                    try:
                        last_update = datetime.fromisoformat(
                            row["last_update"].replace("Z", "+00:00")
                        )
                        if last_update.replace(tzinfo=None) < cutoff:
                            continue
                    except (ValueError, AttributeError):
                        pass

                candidates.append(
                    MergeCandidate(
                        doc1_id=doc1_id,
                        doc2_id=doc2_id,
                        doc1_title=title1,
                        doc2_title=title2,
                        similarity=similarity,
                    )
                )

                if len(candidates) >= limit:
                    break

        return candidates

    except ImportError:
        # sklearn not installed
        return []


def _analyze_tag_patterns() -> Tuple[List[TagPattern], List[str]]:
    """Analyze tag usage patterns across the KB.

    Returns:
        Tuple of (tag_patterns, cross_project_patterns)
    """
    patterns = []
    cross_project = []

    with db.get_connection() as conn:
        # Find tags used across multiple projects
        cursor = conn.execute(
            """
            SELECT
                t.name as tag_name,
                COUNT(DISTINCT d.id) as doc_count,
                COUNT(DISTINCT d.project) as project_count,
                GROUP_CONCAT(DISTINCT d.project) as projects
            FROM tags t
            JOIN document_tags dt ON t.id = dt.tag_id
            JOIN documents d ON dt.document_id = d.id
            WHERE d.is_deleted = 0
            GROUP BY t.id, t.name
            HAVING project_count > 1
            ORDER BY doc_count DESC
            LIMIT 10
            """
        )

        for row in cursor.fetchall():
            projects = [p for p in (row["projects"] or "").split(",") if p]
            pattern = TagPattern(
                tag_name=row["tag_name"],
                doc_count=row["doc_count"],
                projects=projects,
                insight=f"Used in {row['project_count']} projects",
            )
            patterns.append(pattern)
            cross_project.append(
                f"'{row['tag_name']}' spans {len(projects)} projects: {', '.join(projects[:3])}"
            )

        # Find "done" gameplans that could be archived
        cursor = conn.execute(
            """
            SELECT COUNT(*) as count
            FROM documents d
            JOIN document_tags dt ON d.id = dt.document_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0
            AND t.name IN ('🎯', 'gameplan')
            AND d.id IN (
                SELECT document_id FROM document_tags dt2
                JOIN tags t2 ON dt2.tag_id = t2.id
                WHERE t2.name IN ('✅', 'done')
            )
            """
        )
        done_gameplans = cursor.fetchone()["count"]
        if done_gameplans > 0:
            cross_project.append(
                f"{done_gameplans} gameplans marked 'done' — consider archiving"
            )

    return patterns, cross_project


def _find_hygiene_issues() -> List[HygieneIssue]:
    """Find documents with hygiene issues.

    Returns:
        List of hygiene issues
    """
    issues = []

    with db.get_connection() as conn:
        # Find untagged documents
        cursor = conn.execute(
            """
            SELECT d.id, d.title
            FROM documents d
            WHERE d.is_deleted = 0
            AND NOT EXISTS (
                SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
            )
            ORDER BY d.updated_at DESC
            LIMIT 20
            """
        )
        for row in cursor.fetchall():
            issues.append(
                HygieneIssue(
                    issue_type="untagged",
                    doc_id=row["id"],
                    doc_title=row["title"] or "(untitled)",
                    detail="No tags — consider adding tags for better organization",
                )
            )

        # Find documents with no project
        cursor = conn.execute(
            """
            SELECT id, title
            FROM documents
            WHERE is_deleted = 0
            AND (project IS NULL OR project = '')
            ORDER BY updated_at DESC
            LIMIT 20
            """
        )
        for row in cursor.fetchall():
            issues.append(
                HygieneIssue(
                    issue_type="no_project",
                    doc_id=row["id"],
                    doc_title=row["title"] or "(untitled)",
                    detail="No project assigned",
                )
            )

        # Find empty/near-empty documents
        cursor = conn.execute(
            """
            SELECT id, title, LENGTH(content) as length
            FROM documents
            WHERE is_deleted = 0
            AND LENGTH(content) < 20
            ORDER BY length ASC
            LIMIT 10
            """
        )
        for row in cursor.fetchall():
            issues.append(
                HygieneIssue(
                    issue_type="empty",
                    doc_id=row["id"],
                    doc_title=row["title"] or "(untitled)",
                    detail=f"Only {row['length']} chars — likely a save error",
                )
            )

        # Find stale documents (never viewed, > 30 days old)
        cursor = conn.execute(
            """
            SELECT id, title, created_at
            FROM documents
            WHERE is_deleted = 0
            AND access_count = 0
            AND created_at < datetime('now', '-30 days')
            ORDER BY created_at ASC
            LIMIT 10
            """
        )
        for row in cursor.fetchall():
            issues.append(
                HygieneIssue(
                    issue_type="stale",
                    doc_id=row["id"],
                    doc_title=row["title"] or "(untitled)",
                    detail="Never viewed, 30+ days old — candidate for archival",
                )
            )

    return issues


def _count_recent_docs(days: int = 7) -> int:
    """Count documents modified in the last N days."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT COUNT(*) as count
            FROM documents
            WHERE is_deleted = 0
            AND updated_at > datetime('now', ? || ' days')
            """,
            (f"-{days}",),
        )
        return cursor.fetchone()["count"]


def _generate_digest_markdown(digest: DreamDigest) -> str:
    """Generate a markdown digest from the dream analysis.

    Args:
        digest: The digest to format

    Returns:
        Markdown-formatted digest string
    """
    lines = []
    date_str = digest.date.strftime("%B %d, %Y")

    lines.append(f"# 🌙 Dream Journal — {date_str}")
    lines.append("")
    lines.append(f"Processed {digest.docs_processed} recent documents.")
    lines.append("")

    # Consolidation section
    if digest.merge_candidates:
        lines.append("## 🔄 Consolidation Candidates")
        lines.append("")
        for mc in digest.merge_candidates[:10]:
            lines.append(
                f"- **#{mc.doc1_id}** + **#{mc.doc2_id}** ({mc.similarity:.0%} similar)"
            )
            lines.append(f"  - `{mc.doc1_title[:40]}...` ↔ `{mc.doc2_title[:40]}...`")
        lines.append("")
        lines.append(
            f"*Use `emdx maintain --merge` or review pairs with `emdx similar <id>`*"
        )
        lines.append("")
    else:
        lines.append("## 🔄 Consolidation")
        lines.append("")
        lines.append("✨ No duplicate documents found!")
        lines.append("")

    # Patterns section
    if digest.cross_project_patterns:
        lines.append("## 🔍 Discovered Patterns")
        lines.append("")
        for pattern in digest.cross_project_patterns:
            lines.append(f"- {pattern}")
        lines.append("")

    # Hygiene section
    if digest.hygiene_issues:
        lines.append("## 🧹 Maintenance Needed")
        lines.append("")

        # Group by type
        by_type = {}
        for issue in digest.hygiene_issues:
            by_type.setdefault(issue.issue_type, []).append(issue)

        issue_labels = {
            "untagged": ("📑 Untagged Documents", "`emdx maintain --tags`"),
            "no_project": ("📂 No Project Assigned", "assign projects manually"),
            "empty": ("📄 Empty Documents", "`emdx maintain --clean`"),
            "stale": ("🕸️ Stale Documents", "consider archiving"),
        }

        for issue_type, issues_list in by_type.items():
            label, action = issue_labels.get(
                issue_type, (issue_type.title(), "review manually")
            )
            lines.append(f"### {label} ({len(issues_list)})")
            lines.append("")
            for issue in issues_list[:5]:
                lines.append(f"- #{issue.doc_id}: {issue.doc_title[:40]}")
            if len(issues_list) > 5:
                lines.append(f"  *...and {len(issues_list) - 5} more*")
            lines.append("")
            lines.append(f"*Action: {action}*")
            lines.append("")
    else:
        lines.append("## 🧹 Maintenance")
        lines.append("")
        lines.append("✨ No hygiene issues found!")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(
        f"*Generated by `emdx dream` at {digest.date.strftime('%H:%M')}. "
        "For detailed analysis, run `emdx maintain analyze --all`.*"
    )

    return "\n".join(lines)


def _save_digest(digest: DreamDigest) -> int:
    """Save the digest as a document in the KB.

    Args:
        digest: The digest to save

    Returns:
        The new document's ID
    """
    date_str = digest.date.strftime("%B %d, %Y")
    title = f"Dream Journal — {date_str}"
    content = _generate_digest_markdown(digest)

    doc_id = save_document(
        title=title,
        content=content,
        project="emdx",
        tags=["dream-journal", "🌙"],
    )

    return doc_id


def _get_latest_digest() -> Optional[dict]:
    """Get the most recent dream journal digest.

    Returns:
        The latest digest document, or None if none exists
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT d.id, d.title, d.content, d.created_at
            FROM documents d
            JOIN document_tags dt ON d.id = dt.document_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE t.name = 'dream-journal'
            AND d.is_deleted = 0
            ORDER BY d.created_at DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
    return None


def _setup_cron(hour: int = 3) -> bool:
    """Set up a cron job to run dream journal daily.

    Args:
        hour: Hour of day to run (0-23, default 3am)

    Returns:
        True if successful, False otherwise
    """
    import shutil

    # Check if crontab is available
    if not shutil.which("crontab"):
        return False

    try:
        # Get existing crontab
        result = subprocess.run(
            ["crontab", "-l"], capture_output=True, text=True, check=False
        )
        existing = result.stdout if result.returncode == 0 else ""

        # Check if already scheduled
        if "emdx dream" in existing:
            return True  # Already scheduled

        # Add new cron entry
        # Format: minute hour * * * command
        cron_entry = f"0 {hour} * * * emdx dream --quiet 2>&1 | logger -t emdx-dream"
        new_crontab = existing.rstrip() + "\n" + cron_entry + "\n"

        # Install new crontab
        result = subprocess.run(
            ["crontab", "-"], input=new_crontab, text=True, capture_output=True
        )
        return result.returncode == 0

    except Exception:
        return False


def dream(
    schedule: bool = typer.Option(
        False, "--schedule", "-s", help="Set up daily cron job at 3am"
    ),
    digest_only: bool = typer.Option(
        False, "--digest", "-d", help="Generate digest without saving"
    ),
    latest: bool = typer.Option(
        False, "--latest", "-l", help="Show the most recent dream journal"
    ),
    days: int = typer.Option(
        7, "--days", help="Process documents from last N days"
    ),
    threshold: float = typer.Option(
        0.8, "--threshold", "-t", help="Similarity threshold for duplicates (0-1)"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress output (for cron)"
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output as JSON"
    ),
):
    """
    🌙 Dream Journal — Overnight KB consolidation.

    Processes your knowledge base like a brain during sleep:
    - Detects duplicate and similar documents
    - Identifies patterns across tags and projects
    - Flags hygiene issues (untagged, empty, stale docs)
    - Generates a concise digest with actionable recommendations

    Examples:
        emdx dream                    # Run analysis and save digest
        emdx dream --digest           # Preview without saving
        emdx dream --latest           # View last dream journal
        emdx dream --schedule         # Set up daily 3am cron job
        emdx dream --days 14          # Process last 2 weeks
    """
    # Handle --schedule flag
    if schedule:
        if _setup_cron():
            console.print("[green]✓[/green] Cron job scheduled for 3am daily")
            console.print("[dim]View with: crontab -l[/dim]")
        else:
            console.print(
                "[yellow]⚠[/yellow] Could not set up cron job. "
                "Add manually: `0 3 * * * emdx dream --quiet`"
            )
        return

    # Handle --latest flag
    if latest:
        latest_digest = _get_latest_digest()
        if latest_digest:
            if json_output:
                print(json.dumps(latest_digest, indent=2, default=str))
            else:
                console.print(Panel(
                    Markdown(latest_digest["content"]),
                    title=f"[bold cyan]#{latest_digest['id']}: {latest_digest['title']}[/bold cyan]",
                    box=box.ROUNDED,
                ))
        else:
            console.print("[yellow]No dream journal found. Run `emdx dream` to create one.[/yellow]")
        return

    # Run the analysis
    # Suppress progress for quiet mode OR JSON output
    show_progress = not quiet and not json_output

    if show_progress:
        console.print(Panel(
            "[bold cyan]🌙 Dream Journal — Processing Knowledge Base...[/bold cyan]",
            box=box.DOUBLE,
        ))

    # Count docs to process
    docs_processed = _count_recent_docs(days)
    if show_progress:
        console.print(f"\nAnalyzing {docs_processed} documents from the last {days} days...\n")

    # Step 1: Find merge candidates
    if show_progress:
        console.print("[bold]Step 1/3:[/bold] Detecting duplicates...")
    merge_candidates = _find_merge_candidates(days=days, threshold=threshold)
    if show_progress:
        console.print(f"  Found {len(merge_candidates)} merge candidates")

    # Step 2: Analyze patterns
    if show_progress:
        console.print("[bold]Step 2/3:[/bold] Analyzing patterns...")
    tag_patterns, cross_project = _analyze_tag_patterns()
    if show_progress:
        console.print(f"  Found {len(cross_project)} cross-project patterns")

    # Step 3: Find hygiene issues
    if show_progress:
        console.print("[bold]Step 3/3:[/bold] Checking hygiene...")
    hygiene_issues = _find_hygiene_issues()
    if show_progress:
        console.print(f"  Found {len(hygiene_issues)} hygiene issues")
        console.print()

    # Build digest
    digest = DreamDigest(
        date=datetime.now(),
        docs_processed=docs_processed,
        merge_candidates=merge_candidates,
        tag_patterns=tag_patterns,
        hygiene_issues=hygiene_issues,
        cross_project_patterns=cross_project,
    )

    # JSON output
    if json_output:
        output = {
            "date": digest.date.isoformat(),
            "docs_processed": digest.docs_processed,
            "merge_candidates": [
                {
                    "doc1_id": mc.doc1_id,
                    "doc2_id": mc.doc2_id,
                    "doc1_title": mc.doc1_title,
                    "doc2_title": mc.doc2_title,
                    "similarity": mc.similarity,
                }
                for mc in digest.merge_candidates
            ],
            "cross_project_patterns": digest.cross_project_patterns,
            "hygiene_issues": [
                {
                    "type": hi.issue_type,
                    "doc_id": hi.doc_id,
                    "title": hi.doc_title,
                    "detail": hi.detail,
                }
                for hi in digest.hygiene_issues
            ],
        }
        print(json.dumps(output, indent=2))
        return

    # Generate and display digest
    digest_md = _generate_digest_markdown(digest)

    if not quiet:
        console.print(Panel(
            Markdown(digest_md),
            title="[bold cyan]Dream Journal Digest[/bold cyan]",
            box=box.ROUNDED,
        ))

    # Save unless digest-only mode
    if digest_only:
        if not quiet:
            console.print("\n[dim]Digest preview only. Run without --digest to save.[/dim]")
    else:
        doc_id = _save_digest(digest)
        if not quiet:
            console.print(f"\n[green]✓[/green] Digest saved as [cyan]#{doc_id}[/cyan]")
            console.print("[dim]View with: emdx dream --latest[/dim]")


