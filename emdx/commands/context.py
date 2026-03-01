"""
Context command — Graph-aware context assembly for agents.

Walks the wiki link graph outward from seed documents, scores
reachable documents by link quality and hop distance, and returns
a token-budgeted context bundle.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import typer
from rich.console import Console

from ..database import db
from ..database.document_links import get_links_for_document
from ..database.types import DocumentLinkDetail, DocumentRow

if TYPE_CHECKING:
    from ..services.hybrid_search import HybridSearchResult

console = Console()

# ── Scoring constants ────────────────────────────────────────────────

# Method weights — how much to trust each link type
METHOD_WEIGHTS: dict[str, float] = {
    "title_match": 1.0,
    "entity_match": 0.85,
    "entity": 0.85,
    "semantic": 0.7,
    "manual": 1.0,
    "auto": 0.75,
}

# Score decays with distance
HOP_DECAY = 0.6

# Default token budget
DEFAULT_MAX_TOKENS = 4000
DEFAULT_DEPTH = 2
DEFAULT_SEED_COUNT = 3


# ── Data structures ──────────────────────────────────────────────────


@dataclass
class ScoredDocument:
    """A document discovered during graph traversal with scoring."""

    doc_id: int
    title: str
    content: str
    tokens: int
    hops: int
    score: float
    path: list[int] = field(default_factory=list)
    link_methods: list[str] = field(default_factory=list)
    reason: str = "seed"


# ── Token estimation ─────────────────────────────────────────────────


def estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ~ 4 characters for English text."""
    return len(text) // 4


# ── Scoring ──────────────────────────────────────────────────────────


def compute_link_score(
    link: DocumentLinkDetail,
    depth: int,
    source_score: float,
) -> float:
    """Score = source_score * method_weight * link_score * decay^depth."""
    method = link["method"]
    method_weight = METHOD_WEIGHTS.get(method, 0.5)
    decay = HOP_DECAY**depth
    return source_score * method_weight * link["similarity_score"] * decay


# ── Document fetching (no access tracking) ───────────────────────────


def _fetch_document(doc_id: int) -> DocumentRow | None:
    """Fetch a document by ID without updating access tracking."""
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT * FROM documents WHERE id = ? AND is_deleted = FALSE",
            (doc_id,),
        )
        row = cursor.fetchone()
        if row:
            return cast(DocumentRow, dict(row))
        return None


# ── Graph traversal ──────────────────────────────────────────────────


def traverse_graph(
    seed_ids: list[int],
    max_depth: int = DEFAULT_DEPTH,
) -> list[ScoredDocument]:
    """BFS from seed documents, scoring each reachable doc.

    Returns all reachable docs sorted by score descending.
    """
    visited: dict[int, ScoredDocument] = {}
    frontier: list[int] = []

    # Initialize seeds
    for sid in seed_ids:
        doc = _fetch_document(sid)
        if doc is None:
            continue
        scored = ScoredDocument(
            doc_id=sid,
            title=doc["title"],
            content=doc["content"],
            tokens=estimate_tokens(doc["content"]),
            hops=0,
            score=1.0,
            path=[sid],
            link_methods=[],
            reason="seed",
        )
        visited[sid] = scored
        frontier.append(sid)

    # BFS by depth level
    for depth in range(1, max_depth + 1):
        next_frontier: list[int] = []
        for source_id in frontier:
            source = visited[source_id]
            links = get_links_for_document(source_id)

            for link in links:
                # Determine target: the "other" end of the link
                if link["source_doc_id"] == source_id:
                    target_id = link["target_doc_id"]
                else:
                    target_id = link["source_doc_id"]

                hop_score = compute_link_score(link, depth, source.score)

                if target_id not in visited or hop_score > visited[target_id].score:
                    doc = _fetch_document(target_id)
                    if doc is None:
                        continue

                    method = link["method"]
                    reason = f"{depth}-hop {method} from #{source_id}"
                    visited[target_id] = ScoredDocument(
                        doc_id=target_id,
                        title=doc["title"],
                        content=doc["content"],
                        tokens=estimate_tokens(doc["content"]),
                        hops=depth,
                        score=hop_score,
                        path=source.path + [target_id],
                        link_methods=(source.link_methods + [method]),
                        reason=reason,
                    )
                    next_frontier.append(target_id)

        frontier = next_frontier

    results = sorted(visited.values(), key=lambda d: d.score, reverse=True)
    return results


# ── Token budget packing ─────────────────────────────────────────────


def pack_context(
    scored_docs: list[ScoredDocument],
    max_tokens: int,
) -> tuple[list[ScoredDocument], list[ScoredDocument]]:
    """Greedily pack highest-scored documents into token budget.

    Returns (included, excluded).
    """
    included: list[ScoredDocument] = []
    excluded: list[ScoredDocument] = []
    remaining = max_tokens

    for doc in scored_docs:
        if doc.tokens <= remaining:
            included.append(doc)
            remaining -= doc.tokens
        else:
            excluded.append(doc)

    return included, excluded


# ── Seed resolution ──────────────────────────────────────────────────


def resolve_seeds(
    query: str,
    count: int = DEFAULT_SEED_COUNT,
) -> list[int]:
    """Resolve a text query into seed document IDs.

    Uses hybrid search (keyword + semantic when available)
    to find the most relevant starting documents.
    """
    from ..services.hybrid_search import HybridSearchService

    service = HybridSearchService()
    results: list[HybridSearchResult] = service.search(
        query=query,
        limit=count,
    )
    return [r.doc_id for r in results]


# ── Output formatting ────────────────────────────────────────────────


def _format_tokens(n: int) -> str:
    """Format token count with comma separator."""
    return f"{n:,}"


def _render_human(
    seed_ids: list[int],
    included: list[ScoredDocument],
    excluded: list[ScoredDocument],
    max_tokens: int,
    depth: int,
    plan_only: bool = False,
) -> str:
    """Render human-readable output."""
    tokens_used = sum(d.tokens for d in included)

    # Header
    seed_titles = []
    for doc in included:
        if doc.doc_id in seed_ids:
            seed_titles.append(f"{doc.title} (#{doc.doc_id})")
    header = ", ".join(seed_titles) if seed_titles else "unknown"

    lines: list[str] = []
    lines.append(f"Context for: {header}")
    lines.append(
        f"Budget: {_format_tokens(max_tokens)} tokens | Depth: {depth} | Documents: {len(included)}"
    )
    lines.append("")

    # Included section
    label = "Would include" if plan_only else "Included"
    lines.append(f"--- {label} " + "-" * (55 - len(label)))
    for doc in included:
        if doc.hops == 0:
            info = "(seed)"
        else:
            info = f"{doc.hops} hop{'s' if doc.hops > 1 else ''}, {doc.score:.2f}"
        lines.append(
            f" #{doc.doc_id:<4} {doc.title:<30} {info:<16} ~{_format_tokens(doc.tokens)} tok"
        )
    lines.append("")

    # Excluded section
    if excluded:
        lines.append("--- Excluded (budget) " + "-" * 37)
        for doc in excluded:
            info = f"{doc.hops} hop{'s' if doc.hops > 1 else ''}, {doc.score:.2f}"
            lines.append(
                f" #{doc.doc_id:<4} {doc.title:<30} {info:<16} ~{_format_tokens(doc.tokens)} tok"
            )
        lines.append("")

    lines.append(f"Total: {_format_tokens(tokens_used)} / {_format_tokens(max_tokens)} tokens")
    return "\n".join(lines)


def _render_json(
    seed_ids: list[int],
    included: list[ScoredDocument],
    excluded: list[ScoredDocument],
    max_tokens: int,
    depth: int,
) -> str:
    """Render JSON output for agent consumption."""
    tokens_used = sum(d.tokens for d in included)

    docs_json: list[dict[str, object]] = []
    for doc in included:
        traversal: dict[str, object] = {
            "hops": doc.hops,
            "score": round(doc.score, 4),
            "reason": doc.reason,
        }
        if doc.hops > 0:
            traversal["path"] = doc.path
            traversal["link_methods"] = doc.link_methods

        docs_json.append(
            {
                "id": doc.doc_id,
                "title": doc.title,
                "content": doc.content,
                "tokens": doc.tokens,
                "traversal": traversal,
            }
        )

    excluded_json: list[dict[str, object]] = []
    for doc in excluded:
        excluded_json.append(
            {
                "id": doc.doc_id,
                "title": doc.title,
                "tokens": doc.tokens,
                "traversal": {
                    "hops": doc.hops,
                    "score": round(doc.score, 4),
                    "reason": "budget_exceeded",
                },
            }
        )

    output: dict[str, object] = {
        "seed_ids": seed_ids,
        "depth": depth,
        "max_tokens": max_tokens,
        "tokens_used": tokens_used,
        "documents": docs_json,
        "excluded": excluded_json,
    }

    return json.dumps(output, indent=2, default=str)


# ── CLI command ──────────────────────────────────────────────────────


def context(
    doc_ids: list[int] | None = typer.Argument(
        None,
        help="Document IDs to use as seeds",
    ),
    seed: str | None = typer.Option(
        None,
        "--seed",
        "-s",
        help="Text query to find seed documents",
    ),
    depth: int = typer.Option(
        DEFAULT_DEPTH,
        "--depth",
        "-d",
        help="Maximum traversal depth (hops from seeds)",
    ),
    max_tokens: int = typer.Option(
        DEFAULT_MAX_TOKENS,
        "--max-tokens",
        "-t",
        help="Token budget for the context bundle",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output as JSON for agent consumption",
    ),
    plan: bool = typer.Option(
        False,
        "--plan",
        help="Dry run: show what would be included",
    ),
) -> None:
    """Walk the wiki link graph and assemble a context bundle.

    Starts from seed documents, traverses outward through wiki
    links, scores each reachable document, and packs them into
    a token-budgeted bundle optimized for agent consumption.

    Examples:

        # Context neighborhood for doc 87
        emdx context 87

        # Control depth and budget
        emdx context 87 --depth 3 --max-tokens 6000

        # Multiple seeds
        emdx context 87 42 63

        # Find seeds from a text query
        emdx context --seed "401 error session middleware"

        # JSON output for agents
        emdx context 87 --json

        # Dry run
        emdx context 87 --plan
    """
    # Resolve seeds
    seed_ids: list[int] = []

    if doc_ids:
        seed_ids = list(doc_ids)

    if seed:
        resolved = resolve_seeds(seed)
        if not resolved:
            console.print(f"[red]No documents found for: {seed}[/red]")
            raise typer.Exit(1)
        seed_ids.extend(resolved)

    if not seed_ids:
        console.print("[red]Provide document IDs or --seed text[/red]")
        raise typer.Exit(1)

    # Validate seed IDs exist
    valid_seeds: list[int] = []
    for sid in seed_ids:
        doc = _fetch_document(sid)
        if doc is None:
            console.print(f"[yellow]Warning: document #{sid} not found, skipping[/yellow]")
        else:
            valid_seeds.append(sid)

    if not valid_seeds:
        console.print("[red]No valid seed documents found[/red]")
        raise typer.Exit(1)

    seed_ids = valid_seeds

    # Traverse graph
    scored = traverse_graph(seed_ids, max_depth=depth)

    # Pack into budget
    included, excluded = pack_context(scored, max_tokens)

    # Output
    if json_output:
        print(_render_json(seed_ids, included, excluded, max_tokens, depth))
    else:
        print(
            _render_human(
                seed_ids,
                included,
                excluded,
                max_tokens,
                depth,
                plan_only=plan,
            )
        )
