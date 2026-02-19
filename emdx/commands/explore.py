"""
Explore command — discover what your knowledge base knows.

Uses TF-IDF clustering to build a topic map of all documents,
showing coverage depth, freshness, and gaps. Optionally generates
answerable questions per topic via LLM.

No API calls by default (pure TF-IDF). Use --questions for LLM-powered
question generation.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypedDict

import typer
from rich.console import Console
from rich.table import Table

from ..database import db

if TYPE_CHECKING:
    import numpy.typing as npt

console = Console()
app = typer.Typer(help="Explore what your knowledge base knows")

# Import guard for sklearn (optional dependency)
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


def _require_sklearn() -> None:
    """Raise ImportError with helpful message if sklearn is not installed."""
    if not HAS_SKLEARN:
        raise ImportError(
            "scikit-learn is required for topic clustering. "
            "Install it with: pip install 'emdx[similarity]'"
        ) from None


# ── TypedDicts ────────────────────────────────────────────────────────


class ExploreDocumentDict(TypedDict):
    """Document data fetched for explore clustering."""

    id: int
    title: str
    content: str
    project: str | None
    created_at: str | None
    accessed_at: str | None
    access_count: int
    tags: str | None


class TopicCluster(TypedDict):
    """A discovered topic cluster with metadata."""

    label: str
    top_terms: list[str]
    doc_count: int
    total_chars: int
    doc_ids: list[int]
    titles: list[str]
    tags: list[str]
    projects: list[str]
    newest: str | None
    oldest: str | None
    avg_views: float
    stale: bool


class ExploreOutput(TypedDict, total=False):
    """Full explore output for JSON mode."""

    total_documents: int
    clustered_documents: int
    unclustered_documents: int
    topic_count: int
    topics: list[TopicCluster]
    singletons: list[SingletonDoc]
    tag_landscape: list[TagCount]
    questions: list[TopicQuestions]


class SingletonDoc(TypedDict):
    """An unclustered singleton document."""

    id: int
    title: str
    project: str | None


class TagCount(TypedDict):
    """Tag with count for landscape view."""

    name: str
    count: int


class TopicQuestions(TypedDict):
    """Generated questions for a topic cluster."""

    topic: str
    questions: list[str]


# ── Data fetching ─────────────────────────────────────────────────────


def _fetch_all_documents() -> list[ExploreDocumentDict]:
    """Fetch all active documents with metadata for clustering."""
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                d.id,
                d.title,
                d.content,
                d.project,
                d.created_at,
                d.accessed_at,
                d.access_count,
                GROUP_CONCAT(t.name) as tags
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.document_id
            LEFT JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = FALSE
            AND LENGTH(d.content) > 50
            GROUP BY d.id
            ORDER BY d.id
        """)
        return [dict(row) for row in cursor.fetchall()]  # type: ignore[misc]


# ── Clustering ────────────────────────────────────────────────────────


def _compute_tfidf(
    documents: list[ExploreDocumentDict],
) -> tuple[Any, list[int], Any]:
    """Compute TF-IDF matrix and return (matrix, doc_ids, vectorizer).

    Returns the vectorizer so we can extract feature names for topic labels.
    """
    _require_sklearn()

    corpus = []
    doc_ids = []
    for doc in documents:
        text = f"{doc['title']} {doc['content']}"
        corpus.append(text)
        doc_ids.append(doc["id"])

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
    return tfidf_matrix, doc_ids, vectorizer


def _find_clusters(
    similarity_matrix: npt.NDArray[Any],
    doc_ids: list[int],
    threshold: float,
) -> list[list[int]]:
    """Find document clusters using union-find on the similarity matrix.

    Returns clusters with 2+ documents. Singletons are excluded.
    """
    n = len(doc_ids)
    if n == 0:
        return []

    parent = list(range(n))
    rank = [0] * n

    def find(x: int) -> int:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(x: int, y: int) -> None:
        px, py = find(x), find(y)
        if px == py:
            return
        if rank[px] < rank[py]:
            px, py = py, px
        parent[py] = px
        if rank[px] == rank[py]:
            rank[px] += 1

    for i in range(n):
        for j in range(i + 1, n):
            if similarity_matrix[i, j] >= threshold:
                union(i, j)

    clusters_map: dict[int, list[int]] = {}
    for i in range(n):
        root = find(i)
        if root not in clusters_map:
            clusters_map[root] = []
        clusters_map[root].append(doc_ids[i])

    return sorted(
        [c for c in clusters_map.values() if len(c) > 1],
        key=len,
        reverse=True,
    )


# ── Topic label extraction ────────────────────────────────────────────


def _extract_topic_labels(
    tfidf_matrix: Any,
    doc_ids: list[int],
    clusters: list[list[int]],
    vectorizer: Any,
    top_n: int = 5,
) -> list[list[str]]:
    """Extract top TF-IDF terms for each cluster as topic labels.

    For each cluster, sum the TF-IDF vectors of its member documents
    and pick the highest-weighted terms.
    """
    import numpy as np

    feature_names = vectorizer.get_feature_names_out()
    id_to_idx = {did: i for i, did in enumerate(doc_ids)}

    labels: list[list[str]] = []
    for cluster in clusters:
        indices = [id_to_idx[did] for did in cluster if did in id_to_idx]
        if not indices:
            labels.append(["unknown"])
            continue

        # Sum TF-IDF vectors for the cluster
        cluster_vector = np.asarray(
            tfidf_matrix[indices].sum(axis=0)
        ).flatten()

        # Get top terms
        top_indices = cluster_vector.argsort()[::-1][:top_n]
        top_terms = [str(feature_names[i]) for i in top_indices if cluster_vector[i] > 0]
        labels.append(top_terms if top_terms else ["misc"])

    return labels


# ── Cluster metadata ──────────────────────────────────────────────────


STALE_THRESHOLD_DAYS = 30


def _build_topic_clusters(
    clusters: list[list[int]],
    labels: list[list[str]],
    documents: list[ExploreDocumentDict],
) -> list[TopicCluster]:
    """Build TopicCluster dicts with coverage metadata."""
    doc_map = {doc["id"]: doc for doc in documents}
    now = datetime.now()
    topics: list[TopicCluster] = []

    for cluster, terms in zip(clusters, labels, strict=True):
        cluster_docs = [doc_map[did] for did in cluster if did in doc_map]
        if not cluster_docs:
            continue

        # Collect tags
        all_tags: list[str] = []
        for doc in cluster_docs:
            if doc["tags"]:
                all_tags.extend(t.strip() for t in doc["tags"].split(",") if t.strip())
        tag_counts = Counter(all_tags)
        top_tags = [t for t, _ in tag_counts.most_common(5)]

        # Collect projects
        projects = sorted({
            doc["project"] for doc in cluster_docs if doc["project"]
        })

        # Date range
        dates = [doc["created_at"] for doc in cluster_docs if doc["created_at"]]
        newest = max(dates) if dates else None
        oldest = min(dates) if dates else None

        # Staleness check
        access_dates = [
            doc["accessed_at"] for doc in cluster_docs if doc["accessed_at"]
        ]
        stale = False
        if access_dates:
            most_recent_access = max(access_dates)
            try:
                last_dt = datetime.fromisoformat(most_recent_access)
                stale = (now - last_dt).days > STALE_THRESHOLD_DAYS
            except (ValueError, TypeError):
                pass

        # Views
        total_views = sum(doc["access_count"] for doc in cluster_docs)
        avg_views = total_views / len(cluster_docs) if cluster_docs else 0

        # Build label string
        label = ", ".join(terms[:3])

        topics.append(TopicCluster(
            label=label,
            top_terms=terms,
            doc_count=len(cluster_docs),
            total_chars=sum(len(doc["content"]) for doc in cluster_docs),
            doc_ids=cluster,
            titles=[doc["title"] for doc in cluster_docs],
            tags=top_tags,
            projects=projects,
            newest=newest,
            oldest=oldest,
            avg_views=round(avg_views, 1),
            stale=stale,
        ))

    return topics


# ── Question generation (LLM) ────────────────────────────────────────


def _generate_questions(topics: list[TopicCluster]) -> list[TopicQuestions]:
    """Generate answerable questions for each topic cluster via Claude CLI."""
    from ..services.unified_executor import ExecutionConfig, UnifiedExecutor

    results: list[TopicQuestions] = []
    executor = UnifiedExecutor()

    for topic in topics:
        titles_str = "\n".join(f"- {t}" for t in topic["titles"][:10])
        tags_str = ", ".join(topic["tags"]) if topic["tags"] else "none"

        prompt = (
            "Given the following documents in a knowledge base cluster, "
            "generate 3-5 specific questions that someone could answer "
            "using these documents. Return ONLY the questions, one per line, "
            "no numbering or bullets.\n\n"
            f"Topic terms: {topic['label']}\n"
            f"Tags: {tags_str}\n"
            f"Document titles:\n{titles_str}\n"
            f"Document count: {topic['doc_count']}"
        )

        config = ExecutionConfig(
            prompt=prompt,
            title=f"explore-questions: {topic['label']}",
            allowed_tools=[],
            timeout_seconds=60,
        )

        try:
            result = executor.execute(config)
            if result.success and result.output_content:
                questions = [
                    line.strip()
                    for line in result.output_content.strip().splitlines()
                    if line.strip() and not line.strip().startswith("#")
                ]
                results.append(TopicQuestions(
                    topic=topic["label"],
                    questions=questions[:5],
                ))
            else:
                results.append(TopicQuestions(
                    topic=topic["label"],
                    questions=[f"(generation failed: {result.output_content or 'no output'})"],
                ))
        except Exception as e:
            results.append(TopicQuestions(
                topic=topic["label"],
                questions=[f"(error: {e})"],
            ))

    return results


# ── Gap detection ─────────────────────────────────────────────────────


def _detect_gaps(
    topics: list[TopicCluster],
    documents: list[ExploreDocumentDict],
) -> list[str]:
    """Detect coverage gaps in the knowledge base.

    Checks for:
    - Topics with only 1-2 docs (thin coverage)
    - Stale topics (all docs old)
    - Epics with no matching document clusters
    - Tags with only 1 document
    """
    gaps: list[str] = []

    # Thin topics
    thin = [t for t in topics if t["doc_count"] <= 2]
    if thin:
        for t in thin:
            gaps.append(f"Thin coverage: \"{t['label']}\" has only {t['doc_count']} doc(s)")

    # Stale topics
    stale = [t for t in topics if t["stale"]]
    if stale:
        for t in stale:
            gaps.append(
                f"Stale topic: \"{t['label']}\" ({t['doc_count']} docs) "
                f"not accessed in >{STALE_THRESHOLD_DAYS} days"
            )

    # Tags with only 1 document
    from ..models.tags import list_all_tags

    all_tags = list_all_tags()
    lonely_tags = [t for t in all_tags if t["count"] == 1]
    if lonely_tags:
        tag_names = ", ".join(t["name"] for t in lonely_tags[:5])
        suffix = f" (+{len(lonely_tags) - 5} more)" if len(lonely_tags) > 5 else ""
        gaps.append(f"Single-doc tags: {tag_names}{suffix}")

    # Epics with no corresponding docs
    try:
        with db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, title FROM tasks "
                "WHERE type = 'epic' AND status IN ('open', 'active')"
            )
            epics = cursor.fetchall()

        for epic in epics:
            epic_title = epic["title"].lower()
            # Check if any topic label overlaps with epic title words
            epic_words = set(epic_title.split())
            matched = any(
                epic_words & set(t["label"].lower().split(", "))
                for t in topics
            )
            if not matched:
                gaps.append(
                    f"Epic without docs: \"{epic['title']}\" "
                    f"(task #{epic['id']}) has no matching topic cluster"
                )
    except Exception:
        pass  # Tasks table might not have epics

    return gaps


# ── Display ───────────────────────────────────────────────────────────


def _display_topic_map(
    topics: list[TopicCluster],
    singletons: list[ExploreDocumentDict],
    total_docs: int,
) -> None:
    """Display the topic map as a rich table."""
    console.print(
        f"\n[bold]Knowledge Map[/bold] — "
        f"{total_docs} docs, {len(topics)} topics, "
        f"{len(singletons)} unclustered\n"
    )

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Topic", min_width=25)
    table.add_column("Docs", justify="right", width=5)
    table.add_column("Size", justify="right", width=8)
    table.add_column("Views", justify="right", width=6)
    table.add_column("Tags", style="dim", max_width=25)
    table.add_column("Status", width=8)

    for i, topic in enumerate(topics, 1):
        size_kb = topic["total_chars"] // 1024
        size_str = f"{size_kb}KB" if size_kb > 0 else f"{topic['total_chars']}B"
        tags_str = ", ".join(topic["tags"][:3]) if topic["tags"] else ""
        status = "[red]stale[/red]" if topic["stale"] else "[green]fresh[/green]"

        table.add_row(
            str(i),
            topic["label"],
            str(topic["doc_count"]),
            size_str,
            str(topic["avg_views"]),
            tags_str,
            status,
        )

    console.print(table)

    if singletons:
        console.print(
            f"\n[dim]{len(singletons)} unclustered document(s) "
            f"(no strong topic grouping)[/dim]"
        )


def _display_gaps(gaps: list[str]) -> None:
    """Display detected coverage gaps."""
    if not gaps:
        console.print("\n[green]No coverage gaps detected[/green]")
        return

    console.print(f"\n[bold yellow]Coverage Gaps ({len(gaps)}):[/bold yellow]")
    for gap in gaps:
        console.print(f"  [yellow]![/yellow] {gap}")


def _display_questions(topic_questions: list[TopicQuestions]) -> None:
    """Display generated questions per topic."""
    console.print("\n[bold]Answerable Questions:[/bold]")
    for tq in topic_questions:
        console.print(f"\n  [cyan]{tq['topic']}[/cyan]")
        for q in tq["questions"]:
            console.print(f"    ? {q}")


def _display_plain_topic_map(
    topics: list[TopicCluster],
    singletons: list[ExploreDocumentDict],
    total_docs: int,
) -> None:
    """Display the topic map as plain text (no Rich markup)."""
    print(
        f"Knowledge Map — {total_docs} docs, {len(topics)} topics, "
        f"{len(singletons)} unclustered"
    )
    print()

    for i, topic in enumerate(topics, 1):
        size_kb = topic["total_chars"] // 1024
        size_str = f"{size_kb}KB" if size_kb > 0 else f"{topic['total_chars']}B"
        tags_str = f" [{', '.join(topic['tags'][:3])}]" if topic["tags"] else ""
        status = " (stale)" if topic["stale"] else ""
        print(
            f"  {i}. {topic['label']} "
            f"({topic['doc_count']} docs, {size_str}, "
            f"avg {topic['avg_views']} views){tags_str}{status}"
        )

    if singletons:
        print(f"\n  {len(singletons)} unclustered document(s)")


def _display_plain_gaps(gaps: list[str]) -> None:
    """Display gaps as plain text."""
    if not gaps:
        print("\nNo coverage gaps detected")
        return
    print(f"\nCoverage Gaps ({len(gaps)}):")
    for gap in gaps:
        print(f"  ! {gap}")


def _display_plain_questions(topic_questions: list[TopicQuestions]) -> None:
    """Display questions as plain text."""
    print("\nAnswerable Questions:")
    for tq in topic_questions:
        print(f"\n  {tq['topic']}")
        for q in tq["questions"]:
            print(f"    ? {q}")


# ── Main command ──────────────────────────────────────────────────────


@app.command()
def explore(
    threshold: float = typer.Option(
        0.3,
        "--threshold",
        "-t",
        help="Similarity threshold for clustering (0.0-1.0, lower = more grouping)",
    ),
    questions: bool = typer.Option(
        False,
        "--questions",
        "-q",
        help="Generate answerable questions per topic (uses Claude API)",
    ),
    gaps: bool = typer.Option(
        False,
        "--gaps",
        "-g",
        help="Detect coverage gaps (thin topics, stale areas, lonely tags)",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON",
    ),
    rich_output: bool = typer.Option(
        False,
        "--rich",
        help="Enable colored Rich output",
    ),
    limit: int = typer.Option(
        0,
        "--limit",
        "-n",
        help="Max topics to show (0 = all)",
    ),
) -> None:
    """Explore what your knowledge base knows.

    Clusters documents by content similarity to build a topic map,
    showing what areas your KB covers and how deep the coverage is.

    TOPIC MAP (free, no API calls):
        emdx explore                     # Show all topics
        emdx explore --threshold 0.5     # Tighter clusters
        emdx explore --gaps              # Show coverage gaps too

    QUESTION GENERATION (uses Claude API):
        emdx explore --questions         # What can my KB answer?

    MACHINE OUTPUT:
        emdx explore --json              # Full JSON output
        emdx explore --json --questions  # JSON with questions
    """
    try:
        _require_sklearn()
    except ImportError as e:
        if json_output:
            print(json.dumps({"error": str(e)}))
        else:
            console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from e

    # Fetch documents
    documents = _fetch_all_documents()
    if not documents:
        if json_output:
            print(json.dumps({
                "total_documents": 0,
                "topic_count": 0,
                "topics": [],
            }))
        else:
            msg = "No documents found in knowledge base"
            if rich_output:
                console.print(f"[yellow]{msg}[/yellow]")
            else:
                print(msg)
        raise typer.Exit(0)

    if len(documents) < 2:
        if json_output:
            print(json.dumps({
                "total_documents": len(documents),
                "topic_count": 0,
                "topics": [],
                "message": "Need at least 2 documents for clustering",
            }))
        else:
            msg = "Need at least 2 documents for topic clustering"
            if rich_output:
                console.print(f"[yellow]{msg}[/yellow]")
            else:
                print(msg)
        raise typer.Exit(0)

    # Compute TF-IDF and similarity
    tfidf_matrix, doc_ids, vectorizer = _compute_tfidf(documents)
    similarity_matrix = cosine_similarity(tfidf_matrix)

    # Find clusters
    clusters = _find_clusters(similarity_matrix, doc_ids, threshold)

    # Extract topic labels
    labels = _extract_topic_labels(tfidf_matrix, doc_ids, clusters, vectorizer)

    # Build topic metadata
    topics = _build_topic_clusters(clusters, labels, documents)

    # Apply limit
    if limit > 0:
        topics = topics[:limit]

    # Find singletons (unclustered docs)
    clustered_ids = {did for c in clusters for did in c}
    singletons = [doc for doc in documents if doc["id"] not in clustered_ids]

    # Optional: generate questions
    topic_questions: list[TopicQuestions] = []
    if questions:
        if not json_output and rich_output:
            with console.status("[bold]Generating questions via Claude...[/bold]"):
                topic_questions = _generate_questions(topics)
        elif not json_output:
            print("Generating questions via Claude...")
            topic_questions = _generate_questions(topics)
        else:
            topic_questions = _generate_questions(topics)

    # Optional: detect gaps
    gap_list: list[str] = []
    if gaps:
        gap_list = _detect_gaps(topics, documents)

    # ── Output ────────────────────────────────────────────────────────

    if json_output:
        output = ExploreOutput(
            total_documents=len(documents),
            clustered_documents=len(documents) - len(singletons),
            unclustered_documents=len(singletons),
            topic_count=len(topics),
            topics=topics,
            singletons=[
                SingletonDoc(
                    id=doc["id"],
                    title=doc["title"],
                    project=doc["project"],
                )
                for doc in singletons
            ],
        )

        # Tag landscape
        from ..models.tags import list_all_tags

        all_tags = list_all_tags()
        output["tag_landscape"] = [
            TagCount(name=t["name"], count=t["count"])
            for t in all_tags[:20]
        ]

        if questions:
            output["questions"] = topic_questions

        print(json.dumps(output, indent=2, default=str))

    elif rich_output:
        _display_topic_map(topics, singletons, len(documents))
        if gaps:
            _display_gaps(gap_list)
        if questions and topic_questions:
            _display_questions(topic_questions)
    else:
        _display_plain_topic_map(topics, singletons, len(documents))
        if gaps:
            _display_plain_gaps(gap_list)
        if questions and topic_questions:
            _display_plain_questions(topic_questions)


__all__ = ["app"]
