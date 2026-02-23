"""Shared TF-IDF clustering utilities for EMDX.

Extracts duplicated clustering code from explore.py and compact.py into
a single shared module. Provides:
- require_sklearn() — import guard for optional scikit-learn dependency
- ClusterDocumentDict — superset TypedDict for clustering document data
- fetch_cluster_documents() — fetch documents for clustering
- compute_tfidf() — TF-IDF matrix computation with TfidfResult
- find_clusters() — union-find document clustering
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, TypedDict

from ..database import db

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt
    from sklearn.feature_extraction.text import TfidfVectorizer as _TfidfVectorizer

# ── Import guard ─────────────────────────────────────────────────────

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity  # noqa: F401

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False


def require_sklearn() -> None:
    """Raise ImportError with helpful message if sklearn is not installed."""
    if not HAS_SKLEARN:
        raise ImportError(
            "scikit-learn is required for clustering/similarity features. "
            "Install it with: pip install 'emdx[similarity]'"
        ) from None


# ── TypedDicts ───────────────────────────────────────────────────────


class ClusterDocumentDict(TypedDict):
    """Document data fetched for clustering.

    Superset of fields needed by both explore and compact commands.
    """

    id: int
    title: str
    content: str
    project: str | None
    created_at: str | None
    accessed_at: str | None
    access_count: int
    tags: str | None


# ── Data fetching ────────────────────────────────────────────────────


def fetch_cluster_documents(
    exclude_superseded: bool = False,
) -> list[ClusterDocumentDict]:
    """Fetch all active documents with metadata for clustering.

    Args:
        exclude_superseded: If True, exclude documents tagged 'superseded'.
            Used by compact to avoid re-clustering already-merged docs.

    Returns:
        List of document dicts suitable for TF-IDF clustering.
    """
    having_clause = (
        "HAVING COALESCE(GROUP_CONCAT(t.name), '') NOT LIKE '%superseded%'"
        if exclude_superseded
        else ""
    )

    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"""
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
            {having_clause}
            ORDER BY d.id
        """)  # noqa: S608
        return [dict(row) for row in cursor.fetchall()]  # type: ignore[misc]


# ── TF-IDF computation ──────────────────────────────────────────────


class TfidfResult(NamedTuple):
    """Result from compute_tfidf()."""

    matrix: npt.NDArray[np.float64]
    doc_ids: list[int]
    vectorizer: _TfidfVectorizer


def compute_tfidf(
    documents: list[ClusterDocumentDict],
    title_boost: int = 1,
) -> TfidfResult:
    """Compute TF-IDF matrix for documents.

    Args:
        documents: List of document dicts with 'title', 'content', and 'id'.
        title_boost: Number of times to repeat the title in the corpus text.
            Higher values give title terms more weight in clustering and
            label extraction. explore uses 3, compact uses 1.

    Returns:
        TfidfResult with (matrix, doc_ids, vectorizer).
    """
    require_sklearn()

    corpus = []
    doc_ids = []
    for doc in documents:
        title = doc["title"]
        title_prefix = " ".join([title] * title_boost) if title_boost > 1 else title
        text = f"{title_prefix} {doc['content']}"
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
    return TfidfResult(matrix=tfidf_matrix, doc_ids=doc_ids, vectorizer=vectorizer)


# ── Union-find clustering ────────────────────────────────────────────


def find_clusters(
    similarity_matrix: npt.NDArray[np.float64],
    doc_ids: list[int],
    threshold: float = 0.5,
    sort_by_size: bool = False,
) -> list[list[int]]:
    """Find document clusters using union-find on the similarity matrix.

    Groups documents that are similar above the threshold using
    transitive closure (if A~B and B~C, then A,B,C are in same cluster).

    Args:
        similarity_matrix: Pairwise similarity matrix (NxN).
        doc_ids: List of document IDs corresponding to matrix rows.
        threshold: Minimum similarity to consider documents related.
        sort_by_size: If True, sort clusters largest-first (explore).
            If False, return in discovery order (compact).

    Returns:
        List of clusters, each cluster is a list of document IDs.
        Only clusters with 2+ documents are returned.
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

    multi_doc_clusters = [c for c in clusters_map.values() if len(c) > 1]

    if sort_by_size:
        multi_doc_clusters.sort(key=len, reverse=True)

    return multi_doc_clusters
