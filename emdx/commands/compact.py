"""
Compact command for EMDX - AI-powered document synthesis.

Reduces knowledge base redundancy by intelligently merging related documents
using TF-IDF clustering for discovery and Claude for synthesis.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from ..database import db

console = Console()
app = typer.Typer(help="Compact documents by AI-powered synthesis")


# Import guards for optional dependencies
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
            "scikit-learn is required for document clustering. "
            "Install it with: pip install 'emdx[similarity]'"
        )


def _fetch_all_documents() -> list[dict[str, Any]]:
    """Fetch all active documents with their content."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                d.id,
                d.title,
                d.content,
                d.project,
                d.created_at,
                GROUP_CONCAT(t.name) as tags
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.document_id
            LEFT JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = FALSE
            AND LENGTH(d.content) > 50
            GROUP BY d.id
            HAVING COALESCE(GROUP_CONCAT(t.name), '') NOT LIKE '%superseded%'
            ORDER BY d.id
        """)
        return [dict(row) for row in cursor.fetchall()]


def _compute_similarity_matrix(
    documents: list[dict[str, Any]],
) -> tuple[Any, list[int]]:
    """Compute TF-IDF similarity matrix for documents.

    Args:
        documents: List of document dicts with 'content' and 'id' keys

    Returns:
        Tuple of (similarity_matrix, doc_ids)
    """
    _require_sklearn()

    if not documents:
        return None, []

    # Build corpus
    corpus = []
    doc_ids = []
    for doc in documents:
        text = f"{doc['title']} {doc['content']}"
        corpus.append(text)
        doc_ids.append(doc["id"])

    # Compute TF-IDF matrix
    # Adjust min_df and max_df based on corpus size to avoid edge cases
    n_docs = len(corpus)
    min_df = 1 if n_docs < 3 else 2
    max_df = 1.0 if n_docs < 3 else 0.95

    vectorizer = TfidfVectorizer(
        max_features=5000,
        min_df=min_df,
        max_df=max_df,
        stop_words="english",
        ngram_range=(1, 2),
    )

    tfidf_matrix = vectorizer.fit_transform(corpus)
    similarity_matrix = cosine_similarity(tfidf_matrix)

    return similarity_matrix, doc_ids


def _find_clusters(
    similarity_matrix: Any,
    doc_ids: list[int],
    threshold: float = 0.5,
) -> list[list[int]]:
    """Find document clusters using union-find algorithm.

    Groups documents that are similar above the threshold using
    transitive closure (if A~B and B~C, then A,B,C are in same cluster).

    Args:
        similarity_matrix: Pairwise similarity matrix
        doc_ids: List of document IDs corresponding to matrix rows
        threshold: Minimum similarity to consider documents related

    Returns:
        List of clusters, each cluster is a list of document IDs
    """
    n = len(doc_ids)
    if n == 0:
        return []

    # Union-Find data structure
    parent = list(range(n))
    rank = [0] * n

    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])  # Path compression
        return parent[x]

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px == py:
            return
        # Union by rank
        if rank[px] < rank[py]:
            px, py = py, px
        parent[py] = px
        if rank[px] == rank[py]:
            rank[px] += 1

    # Union documents that are similar
    for i in range(n):
        for j in range(i + 1, n):
            if similarity_matrix[i, j] >= threshold:
                union(i, j)

    # Group by root
    clusters_map: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        if root not in clusters_map:
            clusters_map[root] = []
        clusters_map[root].append(doc_ids[i])

    # Return only clusters with more than one document
    return [cluster for cluster in clusters_map.values() if len(cluster) > 1]


def _display_clusters(
    clusters: list[list[int]],
    documents: list[dict[str, Any]],
) -> None:
    """Display discovered clusters in a table format."""
    doc_map = {doc["id"]: doc for doc in documents}

    console.print(f"\n[bold]Found {len(clusters)} cluster(s) of similar documents[/bold]\n")

    for i, cluster in enumerate(clusters, 1):
        console.print(f"[bold cyan]Cluster {i}[/bold cyan] ({len(cluster)} documents)")

        table = Table(show_header=True, header_style="bold")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="white")
        table.add_column("Project", style="green")

        for doc_id in cluster:
            doc = doc_map.get(doc_id, {})
            table.add_row(
                str(doc_id),
                str(doc.get("title", ""))[:60],
                str(doc.get("project", "") or "—"),
            )

        console.print(table)
        console.print()


def _synthesize_cluster(
    cluster: list[int],
    model: str | None = None,
) -> dict[str, Any]:
    """Synthesize a cluster of documents into one.

    Args:
        cluster: List of document IDs to synthesize
        model: Optional model override

    Returns:
        Dict with synthesis result
    """
    from ..services.synthesis_service import SynthesisService

    service = SynthesisService(model=model)
    result = service.synthesize_documents(cluster)

    return {
        "content": result.content,
        "title": result.title,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "source_ids": cluster,
    }


def _save_synthesis(
    synthesis_result: dict[str, Any],
    original_docs: list[dict[str, Any]],
) -> int:
    """Save synthesized document and tag originals as superseded.

    Args:
        synthesis_result: Result from _synthesize_cluster
        original_docs: List of original document dicts

    Returns:
        ID of the new synthesized document
    """
    from ..database.documents import save_document
    from ..models.tags import add_tags_to_document

    # Get common project from original docs
    projects = {doc.get("project") for doc in original_docs if doc.get("project")}
    project = list(projects)[0] if len(projects) == 1 else None

    # Collect all unique tags from original documents
    all_tags: set[str] = set()
    for doc in original_docs:
        if doc.get("tags"):
            tags = doc["tags"].split(",")
            all_tags.update(t.strip() for t in tags if t.strip())

    # Save synthesized document
    doc_id = save_document(
        title=synthesis_result["title"],
        content=synthesis_result["content"],
        project=project,
    )

    # Add collected tags to synthesized document
    if all_tags:
        add_tags_to_document(doc_id, list(all_tags))

    # Tag original documents as superseded
    for orig_doc in original_docs:
        # Add 'superseded' tag and reference to new doc
        add_tags_to_document(
            orig_doc["id"],
            ["superseded", f"superseded-by:{doc_id}"],
        )

    return doc_id


@app.callback(invoke_without_command=True)
def compact(
    ctx: typer.Context,
    doc_ids: list[int] | None = typer.Argument(
        default=None,
        help="Specific document IDs to compact together"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n",
        help="Show clusters without synthesizing (free, no API calls)"
    ),
    auto: bool = typer.Option(
        False, "--auto",
        help="Automatically synthesize all discovered clusters"
    ),
    threshold: float = typer.Option(
        0.5, "--threshold", "-t",
        help="Similarity threshold for clustering (0.0-1.0)"
    ),
    topic: str | None = typer.Option(
        None, "--topic",
        help="Filter to documents matching this topic/query"
    ),
    model: str | None = typer.Option(
        None, "--model", "-m",
        help="Model to use for synthesis (default: claude-opus-4)"
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Skip confirmation prompts"
    ),
) -> None:
    """Compact related documents through AI-powered synthesis.

    DISCOVERY MODE (free, no API calls):
        emdx compact --dry-run              # Show all clusters
        emdx compact --dry-run --threshold 0.6  # Higher similarity required

    SYNTHESIS MODE (uses Claude API):
        emdx compact 42 43 44               # Compact specific docs
        emdx compact --auto                 # Process all clusters
        emdx compact --topic "auth"         # Compact docs about auth

    After synthesis:
        - Creates a new synthesized document
        - Tags original documents with 'superseded' and 'superseded-by:ID'
        - Original documents are NOT deleted (use trash for cleanup)
    """
    # Ensure we have sklearn for clustering
    try:
        _require_sklearn()
    except ImportError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e

    # Ensure database schema
    db.ensure_schema()

    # Fetch all documents
    documents = _fetch_all_documents()
    if not documents:
        console.print("[yellow]No documents found in knowledge base[/yellow]")
        raise typer.Exit(0)

    # Filter by topic if specified
    if topic:
        topic_lower = topic.lower()
        documents = [
            doc for doc in documents
            if topic_lower in doc["title"].lower()
            or topic_lower in doc["content"].lower()
        ]
        if not documents:
            console.print(f"[yellow]No documents found matching '{topic}'[/yellow]")
            raise typer.Exit(0)
        console.print(f"[dim]Filtered to {len(documents)} documents matching '{topic}'[/dim]")

    doc_map = {doc["id"]: doc for doc in documents}

    # Handle specific document IDs
    if doc_ids:
        # Validate all IDs exist
        missing = [doc_id for doc_id in doc_ids if doc_id not in doc_map]
        if missing:
            console.print(f"[red]Error: Documents not found: {missing}[/red]")
            raise typer.Exit(1)

        if len(doc_ids) < 2:
            console.print("[red]Error: Need at least 2 documents to compact[/red]")
            raise typer.Exit(1)

        # Show what we're compacting
        console.print(f"\n[bold]Compacting {len(doc_ids)} documents:[/bold]")
        for doc_id in doc_ids:
            doc = doc_map[doc_id]
            console.print(f"  • #{doc_id}: {doc['title'][:60]}")

        # Estimate cost
        from ..services.synthesis_service import SynthesisService
        service = SynthesisService(model=model)
        cost_est = service.estimate_cost(doc_ids)

        console.print(
            f"\n[dim]Estimated: ~{cost_est['input_tokens']:,} input tokens, "
            f"~{cost_est['output_tokens']:,} output tokens, "
            f"~${cost_est['estimated_cost']:.4f}[/dim]"
        )

        # Confirm
        if not yes and not dry_run:
            if not typer.confirm("Proceed with synthesis?"):
                console.print("[yellow]Cancelled[/yellow]")
                raise typer.Exit(0)

        if dry_run:
            console.print("\n[dim]Dry run - no synthesis performed[/dim]")
            raise typer.Exit(0)

        # Synthesize
        total_chars = sum(
            len(doc_map[did].get("content", "")) for did in doc_ids
        )
        status_msg = (
            f"Synthesizing {len(doc_ids)} documents "
            f"({total_chars:,} chars)"
        )
        with console.status(f"[bold]{status_msg}[/bold]"):
            result = _synthesize_cluster(doc_ids, model=model)

        # Save
        original_docs = [doc_map[doc_id] for doc_id in doc_ids]
        new_id = _save_synthesis(result, original_docs)

        console.print(f"\n[green]✅ Created #{new_id}:[/green] {result['title']}")
        console.print(
            f"[dim]Used {result['input_tokens']:,} input + "
            f"{result['output_tokens']:,} output tokens[/dim]"
        )
        console.print("\n[dim]Original documents tagged with 'superseded'[/dim]")
        console.print(f"[dim]View: emdx view {new_id}[/dim]")
        return

    # Discovery mode: find clusters
    console.print("[dim]Computing document similarity...[/dim]")
    similarity_matrix, matrix_doc_ids = _compute_similarity_matrix(documents)

    if similarity_matrix is None:
        console.print("[yellow]Not enough documents for clustering[/yellow]")
        raise typer.Exit(0)

    # Find clusters
    clusters = _find_clusters(similarity_matrix, matrix_doc_ids, threshold=threshold)

    if not clusters:
        console.print(
            f"[yellow]No clusters found at threshold {threshold}[/yellow]\n"
            "[dim]Try lowering the threshold: emdx compact --dry-run --threshold 0.3[/dim]"
        )
        raise typer.Exit(0)

    # Display clusters
    _display_clusters(clusters, documents)

    # Dry run - just show clusters
    if dry_run:
        console.print("[dim]Dry run - no synthesis performed[/dim]")
        console.print("\n[dim]To synthesize a cluster:[/dim]")
        console.print(f"  emdx compact {' '.join(str(id) for id in clusters[0])}")
        console.print("\n[dim]To synthesize all clusters:[/dim]")
        console.print("  emdx compact --auto")
        raise typer.Exit(0)

    # Auto mode - process all clusters
    if auto:
        from ..services.synthesis_service import SynthesisService
        service = SynthesisService(model=model)

        # Estimate total cost
        total_input = 0
        total_output = 0
        total_cost = 0.0

        for cluster in clusters:
            est = service.estimate_cost(cluster)
            total_input += int(est["input_tokens"])
            total_output += int(est["output_tokens"])
            total_cost += float(est["estimated_cost"])

        console.print(
            f"\n[bold]Auto-synthesis of {len(clusters)} clusters:[/bold]\n"
            f"  Estimated tokens: ~{total_input:,} input + ~{total_output:,} output\n"
            f"  Estimated cost: ~${total_cost:.4f}"
        )

        if not yes:
            if not typer.confirm("Proceed with synthesis?"):
                console.print("[yellow]Cancelled[/yellow]")
                raise typer.Exit(0)

        # Process each cluster
        for i, cluster in enumerate(clusters, 1):
            console.print(f"\n[bold]Processing cluster {i}/{len(clusters)}...[/bold]")
            try:
                result = _synthesize_cluster(cluster, model=model)
                original_docs = [doc_map[doc_id] for doc_id in cluster]
                new_id = _save_synthesis(result, original_docs)
                console.print(f"  [green]✅ Created #{new_id}:[/green] {result['title']}")
            except Exception as e:
                console.print(f"  [red]❌ Failed: {e}[/red]")
                continue

        console.print("\n[green]✅ Compaction complete[/green]")
        console.print("[dim]Original documents tagged with 'superseded'[/dim]")
        return

    # Interactive: prompt for action
    console.print("\n[dim]To synthesize, specify document IDs or use --auto[/dim]")


# Export the app for registration in main.py
__all__ = ["app"]
