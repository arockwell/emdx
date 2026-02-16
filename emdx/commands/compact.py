"""
Compact command for EMDX - reduce knowledge base redundancy.

Uses TF-IDF clustering for discovery (free, local) and Claude Opus
for synthesis (API call). Documents are archived via `superseded` tag
rather than deleted.
"""

from __future__ import annotations

from dataclasses import dataclass

import typer
from rich.console import Console
from rich.table import Table

from emdx.database import db, save_document
from emdx.models.tags import add_tags_to_document, get_document_tags

app = typer.Typer(help="Reduce knowledge base redundancy through AI-powered synthesis")

console = Console()

# Try to import sklearn for clustering
try:
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
    from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import-untyped]

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


def _require_sklearn() -> None:
    """Raise ImportError with helpful message if sklearn is not installed."""
    if not HAS_SKLEARN:
        raise ImportError(
            "scikit-learn is required for compact features. "
            "Install it with: pip install 'emdx[similarity]'"
        )


@dataclass
class DocumentInfo:
    """Minimal document info for clustering."""

    id: int
    title: str
    content: str
    tags: list[str]


@dataclass
class Cluster:
    """A cluster of similar documents."""

    doc_ids: list[int]
    doc_titles: list[str]
    avg_similarity: float


def _fetch_all_documents() -> list[DocumentInfo]:
    """Fetch all active documents with sufficient content."""
    documents = []
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT d.id, d.title, d.content, GROUP_CONCAT(t.name) as tags
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.document_id
            LEFT JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0 AND LENGTH(d.content) > 100
            GROUP BY d.id
            ORDER BY d.id
            """
        )
        for row in cursor.fetchall():
            tags_str = row[3] or ""
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]
            documents.append(
                DocumentInfo(
                    id=row[0],
                    title=row[1],
                    content=row[2],
                    tags=tags,
                )
            )
    return documents


def _find_clusters(
    documents: list[DocumentInfo],
    threshold: float = 0.5,
    min_cluster_size: int = 2,
) -> list[Cluster]:
    """Find clusters of similar documents using TF-IDF and union-find.

    Args:
        documents: List of documents to cluster
        threshold: Minimum similarity threshold (0.0-1.0)
        min_cluster_size: Minimum documents per cluster

    Returns:
        List of clusters, each containing similar documents
    """
    _require_sklearn()

    if len(documents) < 2:
        return []

    # Build TF-IDF matrix
    corpus = [f"{doc.title} {doc.content}" for doc in documents]
    vectorizer = TfidfVectorizer(
        max_features=5000,
        min_df=1,
        max_df=0.95,
        stop_words="english",
        ngram_range=(1, 2),
    )
    tfidf_matrix = vectorizer.fit_transform(corpus)

    # Compute pairwise similarities
    similarities = cosine_similarity(tfidf_matrix)

    # Union-find for clustering
    parent = list(range(len(documents)))

    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    # Union similar documents
    for i in range(len(documents)):
        for j in range(i + 1, len(documents)):
            if similarities[i, j] >= threshold:
                union(i, j)

    # Group by cluster
    cluster_map: dict[int, list[int]] = {}
    for i in range(len(documents)):
        root = find(i)
        if root not in cluster_map:
            cluster_map[root] = []
        cluster_map[root].append(i)

    # Build cluster objects
    clusters = []
    for members in cluster_map.values():
        if len(members) < min_cluster_size:
            continue

        doc_ids = [documents[i].id for i in members]
        doc_titles = [documents[i].title for i in members]

        # Calculate average similarity within cluster
        cluster_sims = []
        for i, idx1 in enumerate(members):
            for idx2 in members[i + 1 :]:
                cluster_sims.append(float(similarities[idx1, idx2]))

        avg_sim = sum(cluster_sims) / len(cluster_sims) if cluster_sims else 0.0

        clusters.append(
            Cluster(
                doc_ids=doc_ids,
                doc_titles=doc_titles,
                avg_similarity=avg_sim,
            )
        )

    # Sort by average similarity descending
    clusters.sort(key=lambda c: c.avg_similarity, reverse=True)
    return clusters


def _display_clusters(clusters: list[Cluster]) -> None:
    """Display clusters in a nice table format."""
    if not clusters:
        console.print("[yellow]No similar document clusters found.[/yellow]")
        return

    table = Table(title="Similar Document Clusters", show_lines=True)
    table.add_column("Cluster", style="cyan", width=8)
    table.add_column("Similarity", style="green", width=10)
    table.add_column("Documents", style="white")

    for i, cluster in enumerate(clusters, 1):
        docs_display = "\n".join(
            [f"#{doc_id}: {title[:60]}..." if len(title) > 60 else f"#{doc_id}: {title}"
             for doc_id, title in zip(cluster.doc_ids, cluster.doc_titles, strict=False)]
        )
        table.add_row(
            str(i),
            f"{cluster.avg_similarity:.1%}",
            docs_display,
        )

    console.print(table)


def _synthesize_and_archive(
    doc_ids: list[int],
    dry_run: bool = False,
) -> int | None:
    """Synthesize documents and archive originals.

    Args:
        doc_ids: Document IDs to synthesize
        dry_run: If True, only show what would happen

    Returns:
        ID of new synthesized document, or None if dry_run
    """
    # Import here to avoid circular imports and to lazy-load AI dependencies
    from emdx.services.synthesis_service import SynthesisService

    service = SynthesisService()

    # Show cost estimate
    estimate = service.estimate_cost(doc_ids)
    console.print(f"\n[dim]Estimated cost: ${estimate['estimated_cost_usd']:.4f}[/dim]")
    console.print(
        f"[dim]Documents: {estimate['document_count']}, "
        f"~{estimate['estimated_input_tokens']:,} input tokens[/dim]"
    )

    if dry_run:
        console.print("\n[yellow]Dry run - no changes made[/yellow]")
        return None

    # Confirm synthesis
    if not typer.confirm("\nProceed with synthesis?"):
        console.print("[yellow]Cancelled[/yellow]")
        return None

    console.print("\n[cyan]Synthesizing documents...[/cyan]")

    # Perform synthesis
    result = service.synthesize_documents(doc_ids)

    console.print(
        f"[green]Synthesis complete![/green] "
        f"({result.input_tokens:,} input, {result.output_tokens:,} output tokens)"
    )

    # Save synthesized document
    new_doc_id = save_document(
        title=result.title,
        content=result.content,
        tags=["synthesis"],
    )

    console.print(f"[green]Created synthesized document #{new_doc_id}[/green]")

    # Archive original documents
    for doc_id in result.source_doc_ids:
        # Add superseded tag with reference to new doc
        existing_tags = get_document_tags(doc_id)
        if "superseded" not in existing_tags:
            add_tags_to_document(doc_id, ["superseded", f"superseded-by:{new_doc_id}"])
            console.print(f"[dim]Archived document #{doc_id} (tagged as superseded)[/dim]")

    return new_doc_id


@app.callback(invoke_without_command=True)
def compact(
    ctx: typer.Context,
    doc_ids: list[int] = typer.Argument(
        None,
        help="Specific document IDs to compact together",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        "-n",
        help="Show clusters without synthesizing (free, no API calls)",
    ),
    auto: bool = typer.Option(
        False,
        "--auto",
        help="Automatically process all clusters",
    ),
    threshold: float = typer.Option(
        0.5,
        "--threshold",
        "-t",
        help="Similarity threshold for clustering (0.0-1.0)",
    ),
    topic: str | None = typer.Option(
        None,
        "--topic",
        help="Only cluster documents matching this topic (FTS search)",
    ),
) -> None:
    """Reduce knowledge base redundancy through AI-powered synthesis.

    Discovery mode (--dry-run) is free and local - uses TF-IDF clustering.
    Synthesis mode uses Claude Opus API and costs money.

    Examples:

        # Show all similar document clusters (free)
        emdx compact --dry-run

        # Show clusters with higher similarity threshold
        emdx compact --dry-run --threshold 0.7

        # Compact specific documents together
        emdx compact 42 43 44

        # Automatically compact all clusters
        emdx compact --auto

        # Compact documents about a specific topic
        emdx compact --topic "authentication" --auto
    """
    _require_sklearn()

    # If specific doc IDs provided, synthesize them directly
    if doc_ids:
        if len(doc_ids) < 2:
            console.print("[red]Error: Need at least 2 documents to compact[/red]")
            raise typer.Exit(1)

        console.print(f"[cyan]Compacting documents: {doc_ids}[/cyan]")
        _synthesize_and_archive(doc_ids, dry_run=dry_run)
        return

    # Otherwise, find clusters
    console.print("[cyan]Scanning for similar documents...[/cyan]")

    # Fetch documents (optionally filtered by topic)
    if topic:
        documents = _fetch_documents_by_topic(topic)
        if not documents:
            console.print(f"[yellow]No documents found matching topic: {topic}[/yellow]")
            return
        console.print(f"[dim]Found {len(documents)} documents matching '{topic}'[/dim]")
    else:
        documents = _fetch_all_documents()
        console.print(f"[dim]Found {len(documents)} total documents[/dim]")

    # Find clusters
    clusters = _find_clusters(documents, threshold=threshold)

    if not clusters:
        console.print("[green]No redundant document clusters found![/green]")
        return

    _display_clusters(clusters)

    if dry_run:
        console.print("\n[dim]Run without --dry-run to synthesize clusters[/dim]")
        return

    if auto:
        # Process all clusters
        for i, cluster in enumerate(clusters, 1):
            console.print(f"\n[cyan]Processing cluster {i}/{len(clusters)}...[/cyan]")
            _synthesize_and_archive(cluster.doc_ids, dry_run=False)
    else:
        # Interactive mode - let user choose cluster
        console.print(
            "\n[dim]Use 'emdx compact <id1> <id2> ...' to compact specific documents[/dim]"
        )
        console.print("[dim]Use 'emdx compact --auto' to compact all clusters[/dim]")


def _fetch_documents_by_topic(topic: str) -> list[DocumentInfo]:
    """Fetch documents matching a topic via FTS search."""
    from emdx.database.search import search_documents

    results = search_documents(topic, limit=100)

    documents = []
    for result in results:
        # Fetch full content for each result
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT d.id, d.title, d.content, GROUP_CONCAT(t.name) as tags
                FROM documents d
                LEFT JOIN document_tags dt ON d.id = dt.document_id
                LEFT JOIN tags t ON dt.tag_id = t.id
                WHERE d.id = ?
                GROUP BY d.id
                """,
                (result["id"],),
            )
            row = cursor.fetchone()
            if row and len(row[2]) > 100:
                tags_str = row[3] or ""
                tags = [t.strip() for t in tags_str.split(",") if t.strip()]
                documents.append(
                    DocumentInfo(
                        id=row[0],
                        title=row[1],
                        content=row[2],
                        tags=tags,
                    )
                )

    return documents
