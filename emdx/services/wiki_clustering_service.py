"""Topic clustering service for auto-wiki generation.

Uses Leiden community detection on a weighted entity co-occurrence graph
to automatically discover topic clusters from the knowledge base.
Documents sharing entities are grouped into topics that become wiki articles.

Requires: python-igraph, leidenalg (optional wiki dependencies).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass

from ..database import db

logger = logging.getLogger(__name__)

# Minimum entity doc frequency to include in the co-occurrence graph.
# Entities appearing in only 1 doc provide no cross-doc signal.
MIN_ENTITY_DF = 2

# Maximum entity doc frequency ratio — skip entities in too many docs.
MAX_ENTITY_DF_RATIO = 0.15

# Minimum edge weight to include in the graph (IDF-weighted Jaccard).
MIN_EDGE_WEIGHT = 0.05

# Minimum cluster size to generate a wiki article.
MIN_CLUSTER_SIZE = 3

# Maximum cluster size before flagging for review.
MAX_CLUSTER_SIZE = 30


@dataclass
class TopicCluster:
    """A discovered topic cluster."""

    cluster_id: int
    label: str
    slug: str
    doc_ids: list[int]
    top_entities: list[tuple[str, float]]  # (entity, score)
    coherence_score: float = 0.0
    resolution_level: str = "medium"


@dataclass
class ClusteringResult:
    """Result from running topic clustering."""

    clusters: list[TopicCluster]
    total_docs: int
    docs_clustered: int
    docs_unclustered: int
    resolution: float = 0.0


def _get_entity_doc_matrix(
    entity_types: list[str] | None = None,
) -> tuple[dict[int, dict[str, float]], dict[str, int]]:
    """Build entity-document matrix with confidence scores.

    Args:
        entity_types: If given, only include entities of these types
            (e.g. ["heading", "proper_noun"]).  ``None`` means all types.

    Returns:
        Tuple of (doc_entities, entity_doc_freq) where:
        - doc_entities: {doc_id: {entity: confidence}}
        - entity_doc_freq: {entity: doc_count}
    """
    with db.get_connection() as conn:
        if entity_types:
            placeholders = ",".join("?" for _ in entity_types)
            cursor = conn.execute(
                "SELECT document_id, entity, confidence "
                "FROM document_entities de "
                "JOIN documents d ON de.document_id = d.id "
                f"WHERE d.is_deleted = 0 AND de.entity_type IN ({placeholders})",
                entity_types,
            )
        else:
            cursor = conn.execute(
                "SELECT document_id, entity, confidence "
                "FROM document_entities de "
                "JOIN documents d ON de.document_id = d.id "
                "WHERE d.is_deleted = 0"
            )
        rows = cursor.fetchall()

    doc_entities: dict[int, dict[str, float]] = {}
    entity_doc_freq: dict[str, int] = {}

    for doc_id, entity, confidence in rows:
        if doc_id not in doc_entities:
            doc_entities[doc_id] = {}
        doc_entities[doc_id][entity] = confidence

        entity_doc_freq[entity] = entity_doc_freq.get(entity, 0) + 1

    return doc_entities, entity_doc_freq


def _compute_idf_weighted_jaccard(
    entities_a: dict[str, float],
    entities_b: dict[str, float],
    entity_idf: dict[str, float],
) -> float:
    """Compute IDF-weighted Jaccard similarity between two entity sets."""
    keys_a = set(entities_a)
    keys_b = set(entities_b)
    shared = keys_a & keys_b

    if not shared:
        return 0.0

    shared_weight = sum(
        entity_idf.get(e, 1.0) * max(entities_a.get(e, 0.5), entities_b.get(e, 0.5)) for e in shared
    )

    union = keys_a | keys_b
    union_weight = sum(entity_idf.get(e, 1.0) for e in union)

    if union_weight <= 0:
        return 0.0

    return shared_weight / union_weight


def _slugify(label: str) -> str:
    """Convert a label to a URL-friendly slug."""
    import re

    slug = label.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug[:80].strip("-")


def _compute_cluster_label(
    doc_ids: list[int],
    doc_entities: dict[int, dict[str, float]],
    entity_idf: dict[str, float],
) -> tuple[str, list[tuple[str, float]]]:
    """Generate a label for a cluster using c-TF-IDF on its entities.

    Returns (label, top_entities) where top_entities is [(entity, score), ...].
    """
    # Count entity frequency within this cluster
    cluster_entity_freq: dict[str, float] = {}
    for doc_id in doc_ids:
        entities = doc_entities.get(doc_id, {})
        for entity, confidence in entities.items():
            cluster_entity_freq[entity] = cluster_entity_freq.get(entity, 0) + confidence

    # Weight by entity type (from DB) and IDF
    entity_type_weights: dict[str, float] = {}
    with db.get_connection() as conn:
        for entity in cluster_entity_freq:
            cursor = conn.execute(
                "SELECT entity_type FROM document_entities WHERE entity = ? LIMIT 1",
                (entity,),
            )
            row = cursor.fetchone()
            if row:
                type_weight = {
                    "proper_noun": 1.0,
                    "tech_term": 0.9,
                    "concept": 0.8,
                    "heading": 0.7,
                }.get(row[0], 0.5)
                entity_type_weights[entity] = type_weight

    # c-TF-IDF: cluster frequency * IDF * type weight
    scored: list[tuple[str, float]] = []
    for entity, freq in cluster_entity_freq.items():
        idf = entity_idf.get(entity, 1.0)
        type_w = entity_type_weights.get(entity, 0.5)
        score = freq * idf * type_w
        scored.append((entity, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    top_entities = scored[:10]

    # Label = top 2-3 entities joined
    label_parts = [e[0] for e in top_entities[:3]]
    label = " / ".join(label_parts) if label_parts else "Uncategorized"

    return label, top_entities


def _entity_fingerprint(doc_ids: list[int], doc_entities: dict[int, dict[str, float]]) -> str:
    """Compute a hash fingerprint of the entity set for a cluster."""
    all_entities: set[str] = set()
    for doc_id in doc_ids:
        all_entities.update(doc_entities.get(doc_id, {}).keys())
    entity_str = ",".join(sorted(all_entities))
    return hashlib.md5(entity_str.encode()).hexdigest()[:16]


def discover_topics(
    resolution: float = 0.05,
    min_cluster_size: int = MIN_CLUSTER_SIZE,
    entity_types: list[str] | None = None,
    min_df: int = MIN_ENTITY_DF,
) -> ClusteringResult:
    """Discover topic clusters using Leiden community detection.

    Builds a weighted graph where:
    - Nodes = documents with entities
    - Edges = IDF-weighted Jaccard similarity between entity sets
    - Weights = similarity score

    Then runs Leiden with CPM (Constant Potts Model) to find communities.

    Args:
        resolution: CPM resolution parameter. Lower = bigger clusters,
            higher = smaller clusters. Default 0.05 gives ~15-40 clusters
            for a 700-doc KB.
        min_cluster_size: Minimum docs in a cluster to keep it.
        entity_types: Entity types to include in clustering. Defaults to
            ``None`` (all types). Pass ``["heading", "proper_noun"]`` to
            avoid noisy tech_term/concept singletons in labels.
        min_df: Minimum document frequency for an entity to be included
            in the co-occurrence graph. Entities below this threshold
            are pruned. Default 2.

    Returns:
        ClusteringResult with discovered clusters.
    """
    try:
        import igraph as ig  # type: ignore[import-untyped]
        import leidenalg  # type: ignore[import-untyped]
    except ImportError as e:
        raise ImportError(
            "Wiki clustering requires python-igraph and leidenalg. "
            "Install with: poetry add python-igraph leidenalg"
        ) from e

    # 1. Build entity-document matrix
    doc_entities, entity_doc_freq = _get_entity_doc_matrix(entity_types=entity_types)
    total_docs = len(doc_entities)

    if total_docs < min_cluster_size:
        return ClusteringResult(
            clusters=[],
            total_docs=total_docs,
            docs_clustered=0,
            docs_unclustered=total_docs,
            resolution=resolution,
        )

    # 2. Filter entities by document frequency
    max_df = max(int(total_docs * MAX_ENTITY_DF_RATIO), 5)
    useful_entities = {e for e, df in entity_doc_freq.items() if min_df <= df <= max_df}

    # Filter doc_entities to only useful entities
    filtered_doc_entities: dict[int, dict[str, float]] = {}
    for doc_id, entities in doc_entities.items():
        filtered = {e: c for e, c in entities.items() if e in useful_entities}
        if filtered:
            filtered_doc_entities[doc_id] = filtered

    # 3. Compute IDF for useful entities
    entity_idf: dict[str, float] = {}
    for entity in useful_entities:
        df = entity_doc_freq.get(entity, 1)
        entity_idf[entity] = math.log(1 + total_docs / max(df, 1))

    # 4. Build similarity graph
    doc_ids = sorted(filtered_doc_entities.keys())
    n = len(doc_ids)

    edges: list[tuple[int, int]] = []
    weights: list[float] = []

    for i in range(n):
        for j in range(i + 1, n):
            sim = _compute_idf_weighted_jaccard(
                filtered_doc_entities[doc_ids[i]],
                filtered_doc_entities[doc_ids[j]],
                entity_idf,
            )
            if sim >= MIN_EDGE_WEIGHT:
                edges.append((i, j))
                weights.append(sim)

    logger.info(
        "Built graph: %d nodes, %d edges (%.1f%% density)",
        n,
        len(edges),
        100 * 2 * len(edges) / (n * (n - 1)) if n > 1 else 0,
    )

    if not edges:
        return ClusteringResult(
            clusters=[],
            total_docs=total_docs,
            docs_clustered=0,
            docs_unclustered=total_docs,
            resolution=resolution,
        )

    # 5. Run Leiden community detection
    g = ig.Graph(n=n, edges=edges, directed=False)
    g.es["weight"] = weights

    partition = leidenalg.find_partition(
        g,
        leidenalg.CPMVertexPartition,
        weights="weight",
        resolution_parameter=resolution,
    )

    # 6. Extract clusters
    cluster_map: dict[int, list[int]] = {}
    for node_idx, cluster_id in enumerate(partition.membership):
        if cluster_id not in cluster_map:
            cluster_map[cluster_id] = []
        cluster_map[cluster_id].append(doc_ids[node_idx])

    # 7. Build TopicCluster objects for clusters meeting size threshold
    clusters: list[TopicCluster] = []
    docs_clustered = 0

    for cid, c_doc_ids in sorted(cluster_map.items()):
        if len(c_doc_ids) < min_cluster_size:
            continue

        label, top_entities = _compute_cluster_label(
            c_doc_ids,
            doc_entities,
            entity_idf,
        )
        slug = _slugify(label)

        # Compute coherence as average pairwise similarity within cluster
        coherence = 0.0
        pair_count = 0
        for i_idx in range(len(c_doc_ids)):
            for j_idx in range(i_idx + 1, len(c_doc_ids)):
                sim = _compute_idf_weighted_jaccard(
                    filtered_doc_entities.get(c_doc_ids[i_idx], {}),
                    filtered_doc_entities.get(c_doc_ids[j_idx], {}),
                    entity_idf,
                )
                coherence += sim
                pair_count += 1
        if pair_count > 0:
            coherence /= pair_count

        cluster = TopicCluster(
            cluster_id=cid,
            label=label,
            slug=slug,
            doc_ids=c_doc_ids,
            top_entities=top_entities,
            coherence_score=coherence,
            resolution_level="medium",
        )
        clusters.append(cluster)
        docs_clustered += len(c_doc_ids)

    # Sort clusters by size descending
    clusters.sort(key=lambda c: len(c.doc_ids), reverse=True)

    # Re-number cluster IDs sequentially
    for i, cluster in enumerate(clusters):
        cluster.cluster_id = i

    docs_unclustered = total_docs - docs_clustered

    logger.info(
        "Found %d clusters covering %d/%d docs (resolution=%.3f)",
        len(clusters),
        docs_clustered,
        total_docs,
        resolution,
    )

    return ClusteringResult(
        clusters=clusters,
        total_docs=total_docs,
        docs_clustered=docs_clustered,
        docs_unclustered=docs_unclustered,
        resolution=resolution,
    )


def save_topics(result: ClusteringResult) -> int:
    """Save discovered topic clusters to the database.

    Clears existing topics and re-creates them from the clustering result.

    Returns:
        Number of topics saved.
    """
    with db.get_connection() as conn:
        cursor = conn.cursor()

        # Clear existing topics
        cursor.execute("DELETE FROM wiki_topic_members")
        cursor.execute("DELETE FROM wiki_topics")

        for cluster in result.clusters:
            doc_entities, _ = _get_entity_doc_matrix()
            fingerprint = _entity_fingerprint(cluster.doc_ids, doc_entities)

            cursor.execute(
                "INSERT INTO wiki_topics "
                "(topic_slug, topic_label, description, entity_fingerprint, "
                "coherence_score, resolution_level, status) "
                "VALUES (?, ?, ?, ?, ?, ?, 'active')",
                (
                    cluster.slug,
                    cluster.label,
                    json.dumps([e[0] for e in cluster.top_entities[:5]]),
                    fingerprint,
                    cluster.coherence_score,
                    cluster.resolution_level,
                ),
            )
            topic_id = cursor.lastrowid

            # Save members
            for doc_id in cluster.doc_ids:
                cursor.execute(
                    "INSERT INTO wiki_topic_members "
                    "(topic_id, document_id, relevance_score, is_primary) "
                    "VALUES (?, ?, 1.0, 1)",
                    (topic_id, doc_id),
                )

        conn.commit()

    return len(result.clusters)


def get_topics() -> list[dict[str, object]]:
    """Get all wiki topics with their member counts.

    Returns list of dicts with topic info.
    """
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT t.id, t.topic_slug, t.topic_label, t.description, "
            "t.coherence_score, t.status, "
            "COUNT(m.document_id) as member_count, "
            "t.model_override "
            "FROM wiki_topics t "
            "LEFT JOIN wiki_topic_members m ON t.id = m.topic_id "
            "GROUP BY t.id "
            "ORDER BY member_count DESC"
        )
        rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "slug": row[1],
            "label": row[2],
            "description": row[3],
            "coherence_score": row[4],
            "status": row[5],
            "member_count": row[6],
            "model_override": row[7],
        }
        for row in rows
    ]


def get_topic_docs(topic_id: int) -> list[int]:
    """Get document IDs for a specific topic (primary members only)."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT document_id FROM wiki_topic_members "
            "WHERE topic_id = ? AND is_primary = 1 "
            "ORDER BY relevance_score DESC",
            (topic_id,),
        )
        return [row[0] for row in cursor.fetchall()]
