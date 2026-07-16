"""
Core CRUD operations for emdx
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from rich.panel import Panel
from rich.table import Table

from emdx.config.cli_config import DEFAULT_LLM_MODEL
from emdx.database.documents import (
    find_supersede_candidate,
    set_parent,
)
from emdx.models.document import Document
from emdx.models.documents import (
    delete_document,
    get_document,
    save_document,
    search_documents,
    update_document,
)
from emdx.models.tags import (
    add_tags_to_document,
    get_document_tags,
    get_tags_for_documents,
    search_by_tags,
)
from emdx.services.auto_tagger import AutoTagger
from emdx.ui.formatting import format_tags
from emdx.utils.output import console, is_non_interactive, print_json
from emdx.utils.text_formatting import truncate_title

app = typer.Typer(help="Core CRUD operations for documents")

# Marks the end of the instructional header in `emdx edit` temp files.
# Only lines above (and including) this are stripped on save, so Markdown
# headings in the document body survive round-trips through the editor.
EDIT_PREAMBLE_SENTINEL = "# ---- edit below this line; this marker and lines above are removed ----"


@dataclass
class InputContent:
    """Container for input content and its metadata"""

    content: str
    source_type: str  # 'stdin', 'file', or 'direct'
    source_path: Path | None = None


@dataclass
class DocumentMetadata:
    """Container for document metadata"""

    title: str
    project: str | None = None


# How long to wait for data on an open non-TTY stdin before treating it as
# empty. Only applies when stdin is the sole possible content source; a
# wedged harness that holds stdin open forever gets a clean error instead
# of hanging the process (see #1034).
STDIN_PROBE_TIMEOUT = 5.0


def _stdin_ready(timeout: float) -> bool:
    """Return True if stdin has data (or EOF) available within timeout."""
    import select
    import sys

    try:
        ready, _, _ = select.select([sys.stdin], [], [], timeout)
    except (OSError, ValueError, TypeError):
        # Unprobeable stdin (e.g. Windows non-socket, test doubles):
        # fall back to the blocking read rather than dropping input.
        return True
    return bool(ready)


def _guard_path_like_positional(arg: str) -> None:
    """Refuse a positional arg that is an existing file path (#1051).

    Callers (usually agents) sometimes pass a file path positionally instead
    of via -f/--file. The save "succeeds" with the literal path string as the
    document body, and the real content is lost once the file at that path is
    cleaned up. Fail loudly instead; the literal-string case survives via
    stdin (`printf '%s' "/some/path" | emdx save`).
    """
    if "\n" in arg:
        return
    try:
        is_file = Path(arg).expanduser().is_file()
    except (OSError, ValueError):
        return

    if is_file:
        console.print(f"[red]Error: positional argument is an existing file path: {arg}[/red]")
        console.print(
            "[red]Use -f/--file to save the file's contents, "
            "or pipe via stdin to save the literal string.[/red]"
        )
        raise typer.Exit(1)

    # Path-looking but nonexistent: usually a temp file already cleaned up or
    # a mistyped path. Warn but proceed with the literal string.
    if arg.startswith(("/", "~")) and " " not in arg:
        console.print(
            f"[yellow]Warning: '{arg}' looks like a file path but no such file exists; "
            "saving it as literal content. Use -f/--file to save a file's contents.[/yellow]"
        )


def get_input_content(input_arg: str | None, file_path: str | None = None) -> InputContent:
    """Handle input from stdin, --file, or positional content argument.

    Priority: --file > positional content arg > stdin.

    When --file or a positional argument is provided, stdin is never read:
    probing an open non-TTY stdin that has no data blocks forever under
    backgrounded/tool-invoked callers (see #732, #1034).

    A positional argument that is an existing file path is refused (#1051):
    it almost always means the caller meant -f/--file, and accepting it
    silently records the path string instead of the file's contents.
    """
    import sys

    # Priority 1: Explicit --file flag (skip stdin — user stated intent)
    if file_path:
        fp = Path(file_path)
        if not fp.exists() or not fp.is_file():
            console.print(f"[red]Error: File not found: {file_path}[/red]")
            raise typer.Exit(1)
        try:
            content = fp.read_text(encoding="utf-8")
            return InputContent(content=content, source_type="file", source_path=fp)
        except Exception as e:
            console.print(f"[red]Error reading file: {e}[/red]")
            raise typer.Exit(1) from e

    # Priority 2: Positional argument (skip stdin — content already in hand)
    if input_arg:
        _guard_path_like_positional(input_arg)
        return InputContent(content=input_arg, source_type="direct")

    # Priority 3: stdin, guarded so an open-but-idle stdin can't wedge us
    if not sys.stdin.isatty() and _stdin_ready(STDIN_PROBE_TIMEOUT):
        content = sys.stdin.read()
        if content.strip():  # Only use stdin if it has actual content
            return InputContent(content=content, source_type="stdin")
        # Fall through if stdin is empty

    # No input provided
    console.print(
        "[red]Error: No input provided. Use positional arg, --file, or pipe via stdin[/red]"
    )
    raise typer.Exit(1)


def generate_title(input_content: InputContent, provided_title: str | None) -> str:
    """Generate appropriate title based on source and content"""
    if provided_title:
        return provided_title

    if input_content.source_type == "stdin":
        return f"Piped content - {datetime.now().strftime('%Y-%m-%d %H:%M')}"

    elif input_content.source_type == "file" and input_content.source_path:
        return input_content.source_path.stem  # filename without extension

    else:  # direct content
        # Create title from first line or truncated content
        first_line = input_content.content.split("\n")[0].strip()
        if first_line:
            return truncate_title(first_line)
        else:
            return f"Note - {datetime.now().strftime('%Y-%m-%d %H:%M')}"


def detect_project(input_content: InputContent, provided_project: str | None) -> str | None:
    """Detect project from git repository"""
    if provided_project:
        return provided_project

    # Lazy import - GitPython is slow to import (~135ms)
    from emdx.utils.git import get_git_project

    # Try to detect from file path if it's a file
    if input_content.source_type == "file" and input_content.source_path:
        detected_project = get_git_project(input_content.source_path.parent)
        if detected_project:
            return detected_project

    # Otherwise try current directory
    detected_project = get_git_project(Path.cwd())
    return detected_project


def create_document(title: str, content: str, project: str | None) -> int:
    """Save document to database and return document ID"""
    # Save to database
    try:
        doc_id = save_document(title, content, project)
        return doc_id
    except Exception as e:
        console.print(f"[red]Error saving document: {e}[/red]")
        raise typer.Exit(1) from e


def apply_tags(doc_id: int, tags_str: str | None) -> list[str]:
    """Parse and apply tags to document"""
    if not tags_str:
        return []

    tag_list = [t.strip() for t in tags_str.split(",") if t.strip()]
    if tag_list:
        return add_tags_to_document(doc_id, tag_list)
    return []


def display_save_result(
    doc_id: int,
    metadata: DocumentMetadata,
    applied_tags: list[str],
    supersede_target: Document | None = None,
) -> None:
    """Display save result to user"""
    console.print(f"[green]✅ Saved as #{doc_id}:[/green] [cyan]{metadata.title}[/cyan]")
    if supersede_target:
        console.print(f"   [dim]↳ Superseded #{supersede_target.id}[/dim]")
    if metadata.project:
        console.print(f"   [dim]Project:[/dim] {metadata.project}")
    if applied_tags:
        console.print(f"   [dim]Tags:[/dim] {format_tags(applied_tags)}")


@app.command()
def save(
    input: str | None = typer.Argument(None, help="Text content to save (or pipe via stdin)"),
    file: str | None = typer.Option(None, "--file", "-f", help="Read content from a file path"),
    title: str | None = typer.Option(None, "--title", "-t", help="Document title"),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name (auto-detected from git)"
    ),
    tags: str | None = typer.Option(None, "--tags", help="Comma-separated tags"),
    auto_tag: bool = typer.Option(False, "--auto-tag", help="Automatically apply suggested tags"),
    suggest_tags: bool = typer.Option(
        False, "--suggest-tags", help="Show tag suggestions after saving"
    ),  # noqa: E501
    supersede: bool = typer.Option(
        False, "--supersede", help="Auto-link to existing doc with same title (disabled by default)"
    ),
    auto_link: bool = typer.Option(
        True, "--auto-link/--no-auto-link", help="Auto-link to semantically similar documents"
    ),
    cross_project: bool = typer.Option(
        False, "--cross-project", help="Allow auto-links across projects"
    ),
    task: int | None = typer.Option(
        None, "--task", help="Link saved document to a task as its output"
    ),
    mark_done: bool = typer.Option(
        False, "--done", help="Also mark the linked task as done (requires --task)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Save content to the knowledge base.

    Content sources (in priority order): --file > positional argument > stdin.
    """
    # Validate --done requires --task
    if mark_done and task is None:
        msg = "--done requires --task"
        if json_output:
            print_json({"error": msg})
        else:
            console.print(f"[red]Error: {msg}[/red]")
        raise typer.Exit(1)

    # Validate task exists before doing any work
    if task is not None:
        from emdx.models.tasks import get_task

        linked_task = get_task(task)
        if not linked_task:
            msg = f"Task #{task} not found"
            if json_output:
                print_json({"error": msg})
            else:
                console.print(f"[red]Error: {msg}[/red]")
            raise typer.Exit(1)

    # Step 1: Get input content
    input_content = get_input_content(input, file_path=file)

    # Step 2: Generate title
    final_title = generate_title(input_content, title)

    # Step 3: Detect project
    final_project = detect_project(input_content, project)

    # Step 4: Create metadata object
    metadata = DocumentMetadata(title=final_title, project=final_project)

    # Step 4.5: Check for supersede candidate (before creating new doc)
    supersede_target = None
    if supersede:
        supersede_target = find_supersede_candidate(
            title=metadata.title,
            project=metadata.project,
            content=input_content.content,
        )

    # Step 5: Create document in database
    doc_id = create_document(metadata.title, input_content.content, metadata.project)

    # Step 5.5: If superseding, link the old doc as a child of the new doc
    if supersede_target:
        set_parent(supersede_target.id, doc_id, relationship="supersedes")

    # Step 6: Apply tags
    applied_tags = apply_tags(doc_id, tags)

    # Step 6.5: Title-match wikification (always runs — zero cost)
    try:
        from emdx.services.wikify_service import title_match_wikify

        wikify_result = title_match_wikify(doc_id)
        if wikify_result.links_created > 0 and not json_output:
            console.print(
                f"   [dim]Wiki-linked to {wikify_result.links_created} doc(s) by title match[/dim]"
            )
    except Exception as e:
        if not json_output:
            console.print(f"   [yellow]Wikify skipped: {e}[/yellow]")

    # Step 6.55: Entity extraction + entity-match wikification (zero cost)
    try:
        from emdx.services.entity_service import entity_match_wikify

        entity_result = entity_match_wikify(doc_id)
        if entity_result.links_created > 0 and not json_output:
            console.print(
                f"   [dim]Entity-linked to {entity_result.links_created}"
                " doc(s) by shared concepts[/dim]"
            )
    except Exception as e:
        if not json_output:
            console.print(f"   [yellow]Entity wikify skipped: {e}[/yellow]")
    # Step 6.6: Auto-link to similar documents (default on, use --no-auto-link to skip)
    if auto_link:
        try:
            from emdx.services.link_service import auto_link_document

            # Scope to same project unless --cross-project is set
            scope_project = None if cross_project else final_project
            link_result = auto_link_document(doc_id, project=scope_project)
            if link_result.links_created > 0 and not json_output:
                console.print(f"   [dim]Linked to {link_result.links_created} similar doc(s)[/dim]")
        except ImportError:
            pass  # AI extras not installed — silently skip
        except Exception as e:
            if not json_output:
                console.print(f"   [yellow]Auto-link skipped: {e}[/yellow]")

    # Step 6.7: Link to task if specified
    if task is not None:
        from emdx.models.tasks import update_task

        update_kwargs: dict[str, Any] = {"output_doc_id": doc_id}
        if mark_done:
            update_kwargs["status"] = "done"
        update_task(task, **update_kwargs)

    # Step 7: Auto-tagging if requested
    if auto_tag:
        tagger = AutoTagger()
        auto_applied = tagger.auto_tag_document(doc_id, confidence_threshold=0.7)
        if auto_applied:
            applied_tags.extend(auto_applied)
            if not json_output:
                console.print(f"   [dim]Auto-tagged:[/dim] {format_tags(auto_applied)}")

    # Step 8: Display result
    if json_output:
        result: dict[str, Any] = {
            "id": doc_id,
            "title": metadata.title,
            "project": metadata.project,
            "tags": applied_tags,
        }
        if task is not None:
            result["task_id"] = task
        if supersede_target:
            result["superseded_id"] = supersede_target.id
        print_json(result)
        return

    display_save_result(doc_id, metadata, applied_tags, supersede_target)

    # Step 8.5: Display task link
    if task is not None:
        if mark_done:
            console.print(f"   [dim]Task:[/dim] #{task} [green](done)[/green]")
        else:
            console.print(f"   [dim]Task:[/dim] #{task}")

    # Step 9: Show tag suggestions if requested
    if suggest_tags and not auto_tag:
        tagger = AutoTagger()
        suggestions = tagger.suggest_tags(doc_id, max_suggestions=3)
        if suggestions:
            console.print("\n[dim]Suggested tags:[/dim]")
            for tag, confidence in suggestions:
                console.print(f"   • {tag} [dim]({confidence:.0%})[/dim]")
            console.print(f"\n[dim]Apply with: emdx tag {doc_id} <tags>[/dim]")


@app.command()
def find(
    query: list[str] | None = typer.Argument(
        default=None, help="Search terms (optional if using --tags)"
    ),
    project: str | None = typer.Option(None, "--project", "-p", help="Filter by project"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum results to return"),
    snippets: bool = typer.Option(False, "--snippets", "-s", help="Show content snippets"),
    fuzzy: bool = typer.Option(False, "--fuzzy", "-f", help="Use fuzzy search"),
    tags: str | None = typer.Option(None, "--tags", "-t", help="Filter by tags (comma-separated)"),
    any_tags: bool = typer.Option(False, "--any-tags", help="Match ANY tag instead of ALL tags"),
    no_tags: str | None = typer.Option(None, "--no-tags", help="Exclude documents with these tags"),
    ids_only: bool = typer.Option(
        False, "--ids-only", help="Output only document IDs (for piping)"
    ),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output results as JSON"),
    created_after: str | None = typer.Option(
        None,
        "--created-after",
        help="Show documents created after date (YYYY-MM-DD)",
    ),
    created_before: str | None = typer.Option(
        None,
        "--created-before",
        help="Show documents created before date (YYYY-MM-DD)",
    ),
    modified_after: str | None = typer.Option(
        None,
        "--modified-after",
        help="Show documents modified after date (YYYY-MM-DD)",
    ),
    modified_before: str | None = typer.Option(
        None,
        "--modified-before",
        help="Show documents modified before date (YYYY-MM-DD)",
    ),
    mode: str | None = typer.Option(
        None,
        "--mode",
        "-m",
        help="Search mode: keyword (FTS5), semantic (embeddings), "
        "hybrid (both, default if index exists)",
    ),
    extract: bool = typer.Option(
        False,
        "--extract",
        "-e",
        help="Show matching chunk text instead of document snippets",
    ),
    all_docs: bool = typer.Option(
        False, "--all", "-a", help="List all documents (no search query needed)"
    ),
    recent: int | None = typer.Option(
        None, "--recent", help="Show N most recently accessed documents"
    ),
    similar: int | None = typer.Option(
        None, "--similar", help="Find documents similar to this doc ID"
    ),
    context: bool = typer.Option(
        False, "--context", help="Output retrieved context as plain text (for piping to claude)"
    ),
    recent_days: int | None = typer.Option(
        None,
        "--recent-days",
        help="Filter --context to docs created in the last N days",
    ),
    wiki: bool = typer.Option(False, "--wiki", help="Show only wiki articles (doc_type='wiki')"),
    all_types: bool = typer.Option(
        False, "--all-types", help="Show all document types (user, wiki, etc.)"
    ),
) -> None:
    """Search the knowledge base with full-text search.

    Supports three search modes:
      - keyword: Fast FTS5 full-text search (exact keyword matches)
      - semantic: Embedding-based search (conceptual similarity)
      - hybrid: Both combined (default when index exists)

    Use --extract to see the matching paragraph/section instead of the full document.
    Use --all to list all documents, --recent N to show recently accessed docs.
    Use --similar N to find documents similar to doc #N.
    Use --context to retrieve docs as plain text for piping to claude.
    Use --recent-days N to scope --context to docs from the last N days.

    For AI-powered search, use: emdx labs ask, emdx labs wander, emdx labs watch.

    Examples:
        emdx find "authentication patterns"              # hybrid search
        emdx find "auth" --mode keyword                  # keyword only
        emdx find "how to configure logging" --extract   # show matching chunks
        emdx find --all                                  # list all documents
        emdx find --recent 10                            # recently accessed
        emdx find --similar 42                           # docs similar to #42
        emdx find --context "auth" | claude              # pipe context to claude
    """
    search_query = " ".join(query) if query else ""

    # Record search event (non-critical, best-effort)
    if search_query:
        from emdx.models.events import record_event

        record_event("search", query=search_query)

    # Determine doc_type filter: --wiki -> 'wiki', default -> None (all types)
    if wiki and all_types:
        console.print("[red]Error: --wiki and --all-types are mutually exclusive[/red]")
        raise typer.Exit(1)
    if wiki:
        doc_type: str | None = "wiki"
    else:
        doc_type = None

    try:
        # Handle --all: list all documents
        if all_docs:
            _find_list_all(project, limit, json_output, doc_type=doc_type)
            return

        # Handle --recent: show recently accessed documents
        if recent is not None:
            _find_recent(recent, project, json_output, doc_type=doc_type)
            return

        # Handle --similar: find documents similar to a given one
        if similar is not None:
            _find_similar(similar, limit, json_output)
            return

        # Handle --context: retrieve context for piping
        if context:
            if not search_query:
                console.print("[red]Error: --context requires a query[/red]")
                raise typer.Exit(1)
            _find_context(search_query, limit, project, tags, recent_days)
            return

        # Validate that we have something to search for
        has_date_filters = any([created_after, created_before, modified_after, modified_before])
        if not search_query and not tags and not has_date_filters:
            console.print("[red]Error: Provide search terms, tags, or date filters[/red]")
            raise typer.Exit(1)

        # Determine if we should use hybrid search
        # Use hybrid when: no date filters, no fuzzy, and user wants text search
        use_hybrid = (
            search_query
            and not has_date_filters
            and not fuzzy
            and mode != "keyword"  # Explicit keyword mode skips hybrid
        )

        # For tag-only or date-filtered searches, use the old FTS path
        if not use_hybrid:
            _find_keyword_search(
                search_query,
                project,
                limit,
                snippets,
                fuzzy,
                tags,
                any_tags,
                no_tags,
                ids_only,
                json_output,
                created_after,
                created_before,
                modified_after,
                modified_before,
                doc_type=doc_type,
            )
            return

        # Use hybrid search for text queries
        from emdx.services.hybrid_search import HybridSearchService

        hybrid_service = HybridSearchService()
        hybrid_results = hybrid_service.search(
            query=search_query,
            limit=limit,
            mode=mode,
            extract=extract,
            project=project,
            doc_type=doc_type,
        )

        # Apply tag filters if specified
        if tags:
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]
            tag_mode = "any" if any_tags else "all"

            # Get docs matching tags
            tag_results = search_by_tags(tag_list, mode=tag_mode, project=project, limit=limit * 2)
            tag_doc_ids = {doc["id"] for doc in tag_results}

            # Filter hybrid results to only include docs with matching tags
            hybrid_results = [r for r in hybrid_results if r.doc_id in tag_doc_ids]

        # Apply --no-tags filter
        if no_tags:
            no_tag_list = [t.strip() for t in no_tags.split(",") if t.strip()]
            if no_tag_list:
                hybrid_results = [
                    r for r in hybrid_results if not any(tag in r.tags for tag in no_tag_list)
                ]

        if not hybrid_results:
            console.print(
                f"[yellow]No results found for '[/yellow]{search_query}[yellow]'[/yellow]"
            )
            return

        # Handle output formats
        if ids_only:
            for result in hybrid_results:
                print(result.doc_id)
            return

        if json_output:
            output_results = []
            for result in hybrid_results:
                output_result = {
                    "id": result.doc_id,
                    "title": result.title,
                    "project": result.project,
                    "score": result.score,
                    "source": result.source,
                    "tags": result.tags,
                }
                if result.keyword_score > 0:
                    output_result["keyword_score"] = result.keyword_score
                if result.semantic_score > 0:
                    output_result["semantic_score"] = result.semantic_score
                if result.chunk_heading:
                    output_result["chunk_heading"] = result.chunk_heading
                if snippets or extract:
                    output_result["snippet"] = result.chunk_text or result.snippet
                output_results.append(output_result)
            print(json.dumps(output_results, indent=2))
            return

        # Display human-readable results
        mode_desc = hybrid_service.determine_mode(mode).value
        console.print(
            f"\n[bold]🔍 Found {len(hybrid_results)} results for "
            f"'[cyan]{search_query}[/cyan]' [dim]({mode_desc} search)[/dim][/bold]\n"
        )

        for i, result in enumerate(hybrid_results, 1):
            # Display result header with chunk heading if available
            wiki_badge = " [magenta]\\[wiki][/magenta]" if result.doc_type == "wiki" else ""
            if result.chunk_heading:
                console.print(
                    f"[bold cyan]#{result.doc_id}[/bold cyan] [bold]{result.title}[/bold]"
                    f"{wiki_badge} "
                    f"[dim]{result.chunk_heading}[/dim]"
                )
            else:
                console.print(
                    f"[bold cyan]#{result.doc_id}[/bold cyan] "
                    f"[bold]{result.title}[/bold]{wiki_badge}"
                )

            # Display metadata
            metadata = []
            if result.project:
                metadata.append(f"[green]{result.project}[/green]")
            metadata.append(f"[dim]{result.source}[/dim]")
            metadata.append(f"[dim]score: {result.score:.0%}[/dim]")
            console.print(" • ".join(metadata))

            # Display tags
            if result.tags:
                console.print(f"[dim]Tags: {format_tags(result.tags)}[/dim]")

            # Display snippet/chunk text
            if extract and result.chunk_text:
                # Show the matching chunk (truncated)
                chunk_preview = result.chunk_text[:300]
                if len(result.chunk_text) > 300:
                    chunk_preview += "..."
                console.print(f"[dim]{chunk_preview}[/dim]")
            elif snippets and result.snippet:
                snippet = result.snippet.replace("<b>", "[bold yellow]").replace(
                    "</b>", "[/bold yellow]"
                )
                console.print(f"[dim]...{snippet}...[/dim]")

            if i < len(hybrid_results):
                console.print()

        console.print("\n[dim]💡 Use 'emdx view <id>' to view a document[/dim]")

    except Exception as e:
        console.print(f"[red]Error searching documents: {e}[/red]")
        raise typer.Exit(1) from e


def _find_list_all(
    project: str | None,
    limit: int,
    json_output: bool,
    doc_type: str | None = "user",
) -> None:
    """List all documents (replaces old `list` command)."""
    from emdx.models.documents import list_documents
    from emdx.utils.text_formatting import truncate_title

    docs = list_documents(project=project, limit=limit, doc_type=doc_type)

    if not docs:
        console.print("[yellow]No documents found[/yellow]")
        return

    if json_output:
        json_docs = []
        for doc in docs:
            d = doc.to_dict()
            json_docs.append(d)
        print(json.dumps(json_docs, indent=2))
        return

    from rich.table import Table

    title = "Knowledge Base Documents"
    if project:
        title += f" - Project: {project}"
    table = Table(title=title)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="magenta")
    table.add_column("Project", style="green")
    table.add_column("Created", style="yellow")
    table.add_column("Views", justify="right", style="blue")

    for doc in docs:
        created = doc.created_at.strftime("%Y-%m-%d") if doc.created_at else ""
        table.add_row(
            str(doc.id),
            truncate_title(doc.title),
            doc.project or "None",
            created,
            str(doc.access_count),
        )

    console.print(table)
    console.print(f"\n[dim]Showing {len(docs)} documents[/dim]")


def _find_recent(
    limit: int,
    project: str | None,
    json_output: bool,
    doc_type: str | None = "user",
) -> None:
    """Show recently accessed documents (replaces old `recent` command)."""
    from emdx.models.documents import get_recent_documents
    from emdx.utils.text_formatting import truncate_title

    docs = get_recent_documents(limit=limit, doc_type=doc_type)
    if project:
        docs = [d for d in docs if d.project == project]

    if not docs:
        console.print("[yellow]No recently accessed documents found[/yellow]")
        return

    if json_output:
        json_docs = []
        for doc in docs:
            d = doc.to_dict()
            json_docs.append(d)
        print(json.dumps(json_docs, indent=2))
        return

    from rich.table import Table

    table = Table(title=f"Last {limit} Accessed Documents")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="magenta")
    table.add_column("Project", style="green")
    table.add_column("Last Accessed", style="yellow")
    table.add_column("Views", justify="right", style="blue")

    for doc in docs:
        accessed_str = "Never"
        if doc.accessed_at:
            accessed_str = doc.accessed_at.strftime("%Y-%m-%d %H:%M")
        table.add_row(
            str(doc.id),
            truncate_title(doc.title),
            doc.project or "None",
            accessed_str,
            str(doc.access_count),
        )

    console.print(table)
    console.print(f"\n[dim]Showing {len(docs)} recently accessed documents[/dim]")


def _find_similar(
    doc_id: int,
    limit: int,
    json_output: bool,
) -> None:
    """Find documents similar to a given document."""
    try:
        from ..services.embedding_service import EmbeddingService
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    from ..database import db

    service = EmbeddingService()

    # Get source document title
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM documents WHERE id = ?", (doc_id,))
        row = cursor.fetchone()
        if not row:
            console.print(f"[red]Document {doc_id} not found[/red]")
            raise typer.Exit(1) from None
        source_title = row[0]

    results = service.find_similar(doc_id, limit=limit)
    if not results:
        console.print("[yellow]No similar documents found[/yellow]")
        return

    if json_output:
        items = [
            {"id": r.doc_id, "title": r.title, "similarity": round(r.similarity, 3)}
            for r in results
        ]
        print(json.dumps(items, indent=2))
        return

    console.print(f"[bold]Documents similar to #{doc_id} '{source_title}':[/bold]\n")
    from rich.table import Table as RichTable

    table = RichTable()
    table.add_column("ID", style="cyan", width=6)
    table.add_column("Score", style="green", width=6)
    table.add_column("Title", width=50)

    for r in results:
        table.add_row(str(r.doc_id), f"{r.similarity:.0%}", r.title)

    console.print(table)


def _find_context(
    question: str,
    limit: int,
    project: str | None,
    tags: str | None,
    recent_days: int | None = None,
) -> None:
    """Retrieve context as plain text for piping to claude."""
    import sys

    from ..services.ask_service import AskService

    service = AskService()
    try:
        if not service._has_embeddings():
            docs, method = service._retrieve_keyword(
                question,
                limit,
                project,
                tags=tags,
                recent_days=recent_days,
            )
        else:
            docs, method = service._retrieve_semantic(
                question,
                limit,
                project,
                tags=tags,
                recent_days=recent_days,
            )
    except ImportError as e:
        console.print(f"[red]{e}[/red]", highlight=False)
        raise typer.Exit(1) from None

    if not docs:
        print("No relevant documents found.", file=sys.stderr)
        raise typer.Exit(1) from None

    output_parts = [f"Question: {question}\n", "=" * 60 + "\n"]
    for doc_id, title, content in docs:
        truncated = content[:4000] if len(content) > 4000 else content
        output_parts.append(f"# Document #{doc_id}: {title}\n\n{truncated}\n")
        output_parts.append("-" * 60 + "\n")

    print("\n".join(output_parts))
    print(f"Retrieved {len(docs)} docs via {method} search", file=sys.stderr)


def _find_keyword_search(
    search_query: str,
    project: str | None,
    limit: int,
    snippets: bool,
    fuzzy: bool,
    tags: str | None,
    any_tags: bool,
    no_tags: str | None,
    ids_only: bool,
    json_output: bool,
    created_after: str | None,
    created_before: str | None,
    modified_after: str | None,
    modified_before: str | None,
    doc_type: str | None = "user",
) -> None:
    """Original keyword-based search for tag/date filtered queries."""
    # Handle tag-based search
    if tags:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()]
        tag_mode = "any" if any_tags else "all"

        # If we have both tags and search query, we need to combine results
        if search_query:
            # Get documents matching tags
            tag_results = search_by_tags(tag_list, mode=tag_mode, project=project, limit=limit)
            tag_doc_ids = {doc["id"] for doc in tag_results}

            # Get documents matching search query
            search_results = search_documents(
                search_query,
                project=project,
                limit=limit * 2,
                fuzzy=fuzzy,
                created_after=created_after,
                created_before=created_before,
                modified_after=modified_after,
                modified_before=modified_before,
                doc_type=doc_type,
            )

            # Combine: only show documents that match both criteria
            results: list[dict[str, Any]] = [
                doc.to_dict() for doc in search_results if doc.id in tag_doc_ids
            ][:limit]

            if not results:
                console.print(
                    f"[yellow]No results found matching both '[/yellow]{search_query}[yellow]' "
                    f"and tags: {', '.join(tag_list)}[/yellow]"
                )
                return
        else:
            # Tag-only search
            results = [
                dict(d)
                for d in search_by_tags(
                    tag_list,
                    mode=tag_mode,
                    project=project,
                    limit=limit,
                )
            ]
            if not results:
                mode_desc = "all" if not any_tags else "any"
                console.print(
                    f"[yellow]No results found with {mode_desc} tags: "
                    f"{', '.join(tag_list)}[/yellow]"
                )
                return
            search_query = f"tags: {', '.join(tag_list)}"
    else:
        # Regular search without tags (but might have date filters)
        # If we have no search query but have date filters, use a wildcard
        effective_query = search_query if search_query else "*"

        results = [
            r.to_dict()
            for r in search_documents(
                effective_query,
                project=project,
                limit=limit,
                fuzzy=fuzzy,
                created_after=created_after,
                created_before=created_before,
                modified_after=modified_after,
                modified_before=modified_before,
                doc_type=doc_type,
            )
        ]

        if not results:
            if search_query:
                console.print(
                    f"[yellow]No results found for '[/yellow]{search_query}[yellow]'[/yellow]"
                )
            else:
                console.print("[yellow]No results found matching the date filters[/yellow]")
            return

    # Batch fetch tags for all results to avoid N+1 queries
    doc_ids = [result["id"] for result in results]
    all_tags_map = get_tags_for_documents(doc_ids)

    # Filter out documents with excluded tags if --no-tags is specified
    if no_tags:
        no_tag_list = [t.strip() for t in no_tags.split(",") if t.strip()]

        if no_tag_list:
            # Filter results to exclude documents with any of the no_tags
            filtered_results = []
            for result in results:
                doc_tags = all_tags_map.get(result["id"], [])
                # Check if document has any excluded tags
                has_excluded_tag = any(tag in doc_tags for tag in no_tag_list)
                if not has_excluded_tag:
                    filtered_results.append(result)

            results = filtered_results

            if not results:
                console.print(
                    "[yellow]No results found after excluding tags: "
                    f"{', '.join(no_tag_list)}[/yellow]"
                )
                return

    # Handle different output formats
    if ids_only:
        # Output only IDs, one per line
        for result in results:
            print(result["id"])
        return

    if json_output:
        # Output as JSON with all metadata
        output_results = []
        for result in results:
            # Use batch-fetched tags
            doc_tags = all_tags_map.get(result["id"], [])

            # Build clean result object
            output_result = {
                "id": result["id"],
                "title": result["title"],
                "project": result.get("project"),
                "created_at": str(result["created_at"] or ""),
                "updated_at": str(result.get("updated_at") or result["created_at"] or ""),
                "tags": doc_tags,
                "access_count": result.get("access_count", 0),
            }

            # Add search-specific metadata if available
            if "rank" in result:
                output_result["relevance"] = result["rank"]
            elif "score" in result:
                output_result["similarity"] = result["score"]

            if snippets and result.get("snippet"):
                # Clean snippet of HTML tags
                snippet = result["snippet"]
                if snippet:
                    output_result["snippet"] = snippet.replace("<b>", "").replace("</b>", "")

            output_results.append(output_result)

        # Output as JSON
        print(json.dumps(output_results, indent=2))
        return

    # Display results (default human-readable format)
    # Build search description
    search_desc = []
    if search_query:
        search_desc.append(f"'[cyan]{search_query}[/cyan]'")
    if created_after or created_before:
        date_range = []
        if created_after:
            date_range.append(f"after {created_after}")
        if created_before:
            date_range.append(f"before {created_before}")
        search_desc.append(f"created {' and '.join(date_range)}")
    if modified_after or modified_before:
        date_range = []
        if modified_after:
            date_range.append(f"after {modified_after}")
        if modified_before:
            date_range.append(f"before {modified_before}")
        search_desc.append(f"modified {' and '.join(date_range)}")

    search_description = " ".join(search_desc) if search_desc else "all documents"
    console.print(f"\n[bold]🔍 Found {len(results)} results for {search_description}[/bold]\n")

    for i, result in enumerate(results, 1):
        # Display result header
        wiki_badge = " [magenta]\\[wiki][/magenta]" if result.get("doc_type") == "wiki" else ""
        console.print(
            f"[bold cyan]#{result['id']}[/bold cyan] [bold]{result['title']}[/bold]{wiki_badge}"
        )

        # Display metadata
        metadata = []
        if result["project"]:
            metadata.append(f"[green]{result['project']}[/green]")
        created = result["created_at"]
        if created:
            date_str = str(created)[:10]
            metadata.append(f"[yellow]{date_str}[/yellow]")

        if "rank" in result:
            metadata.append(f"[dim]relevance: {result['rank']:.3f}[/dim]")
        elif "score" in result:
            metadata.append(f"[dim]similarity: {result['score']:.3f}[/dim]")

        console.print(" • ".join(metadata))

        # Display tags (using batch-fetched tags)
        doc_tags = all_tags_map.get(result["id"], [])
        if doc_tags:
            console.print(f"[dim]Tags: {format_tags(doc_tags)}[/dim]")

        # Display snippet if requested
        if snippets and result.get("snippet"):
            # Clean up the snippet (remove HTML tags from highlighting)
            raw_snippet = result["snippet"] or ""
            snippet = raw_snippet.replace("<b>", "[bold yellow]").replace("</b>", "[/bold yellow]")
            console.print(f"[dim]...{snippet}...[/dim]")

        # Add spacing between results
        if i < len(results):
            console.print()

    # Show tip for viewing documents
    if len(results) > 0:
        console.print("\n[dim]💡 Use 'emdx view <id>' to view a document[/dim]")


@app.command()
def view(
    identifier: str = typer.Argument(..., help="Document ID or title"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Show raw markdown without formatting"),
    rich_mode: bool = typer.Option(
        False, "--rich", help="Rich formatted output with colors and panel header"
    ),
    no_pager: bool = typer.Option(False, "--no-pager", help="Disable pager (for piping output)"),
    no_header: bool = typer.Option(False, "--no-header", help="Hide document header information"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    links: bool = typer.Option(False, "--links", help="Show document links (semantic and manual)"),
    review: bool = typer.Option(False, "--review", "-R", help="Adversarial review of the document"),
) -> None:
    """View a document from the knowledge base"""
    if review and raw:
        console.print("[red]Error: --review and --raw are mutually exclusive[/red]")
        raise typer.Exit(1)

    try:
        # Fetch document
        doc = get_document(identifier)

        if not doc:
            console.print(f"[red]Error: Document '{identifier}' not found[/red]")
            raise typer.Exit(1)

        # Handle --review: adversarial document review
        if review:
            _view_review(doc)
            return

        # Record view event (non-critical, best-effort)
        from emdx.models.events import record_event

        record_event("view", doc_id=doc.id)

        doc_tags = get_document_tags(doc.id)

        # Fetch linked documents
        try:
            from emdx.database.document_links import get_links_for_document

            doc_links = get_links_for_document(doc.id)
        except Exception:
            doc_links = []

        # JSON output
        if json_output:
            content = doc.content
            linked_docs = []
            for link in doc_links:
                if link["source_doc_id"] == doc.id:
                    linked_docs.append(
                        {
                            "id": link["target_doc_id"],
                            "title": link["target_title"],
                            "similarity": link["similarity_score"],
                            "method": link["link_type"],
                        }
                    )
                else:
                    linked_docs.append(
                        {
                            "id": link["source_doc_id"],
                            "title": link["source_title"],
                            "similarity": link["similarity_score"],
                            "method": link["link_type"],
                        }
                    )
            output = {
                "id": doc.id,
                "title": doc.title,
                "content": content,
                "project": doc.project,
                "created_at": str(doc.created_at or ""),
                "updated_at": str(doc.updated_at or ""),
                "accessed_at": str(doc.accessed_at or ""),
                "access_count": doc.access_count,
                "parent_id": doc.parent_id,
                "tags": doc_tags,
                "linked_docs": linked_docs,
                "word_count": len(content.split()),
                "char_count": len(content),
                "line_count": content.count("\n") + 1 if content else 0,
            }
            print(json.dumps(output, indent=2))
            return

        # Handle --links: show detailed link information
        if links:
            if not doc_links:
                console.print(f"[yellow]No links found for document #{doc.id}[/yellow]")
                return

            console.print(f"[bold]Links for #{doc.id} '{doc.title}':[/bold]\n")
            from rich.table import Table as LinksTable

            table = LinksTable()
            table.add_column("ID", style="cyan", width=6)
            table.add_column("Score", style="green", width=6)
            table.add_column("Title", width=50)
            table.add_column("Method", style="dim", width=8)

            for link in doc_links:
                if link["source_doc_id"] == doc.id:
                    other_id = link["target_doc_id"]
                    other_title = link["target_title"]
                else:
                    other_id = link["source_doc_id"]
                    other_title = link["source_title"]
                score = f"{link['similarity_score']:.0%}"
                table.add_row(str(other_id), score, other_title, link["link_type"])

            console.print(table)
            return

        def _render_output() -> None:
            if not no_header:
                if rich_mode:
                    _print_view_header_rich(doc, doc_tags)
                else:
                    _print_view_header_plain(doc, doc_tags)
                if doc_links:
                    _print_related_docs(doc.id, doc_links, rich_mode)
                print()

            if raw:
                print(doc.content)
            elif rich_mode:
                from emdx.ui.markdown_config import MarkdownConfig

                console.print(MarkdownConfig.create_markdown(doc.content))
            else:
                print(doc.content)

        if no_pager:
            _render_output()
        else:
            if "LESS" not in os.environ:
                os.environ["LESS"] = "-R"
            if rich_mode:
                with console.pager(styles=True, links=True):
                    _render_output()
            else:
                with console.pager():
                    _render_output()

    except Exception as e:
        console.print(f"[red]Error viewing document: {e}[/red]")
        raise typer.Exit(1) from e


def _view_review(doc: Document) -> None:
    """Run an adversarial review of a document using an LLM.

    Finds similar documents via embeddings (if available) and prompts
    the LLM to check for contradictions, gaps, staleness, and
    missing considerations.
    """
    import shutil

    from rich.markup import escape

    if not shutil.which("claude"):
        console.print(
            "[red]Error: Claude CLI is required for --review.[/red]\n"
            "Install it from: https://docs.anthropic.com/claude-code"
        )
        raise typer.Exit(1)

    doc_id: int = doc.id
    title: str = doc.title
    content: str = doc.content

    console.print(f"[dim]Reviewing #{doc_id} '{escape(title)}'...[/dim]")

    # Try to find similar documents for cross-referencing
    similar_context = ""
    similar_ids: list[int] = []
    try:
        from emdx.services.embedding_service import EmbeddingService

        svc = EmbeddingService()
        matches = svc.find_similar(doc_id, limit=10)
        if matches:
            parts: list[str] = []
            for m in matches:
                similar_ids.append(m.doc_id)
                parts.append(
                    f"## Similar Document #{m.doc_id}: {m.title}"
                    f" (similarity: {m.similarity:.0%})\n"
                    f"{m.snippet}"
                )
            similar_context = "\n\n".join(parts)
    except Exception:
        # No embeddings or import failure -- review in isolation
        pass

    # Build review prompt
    system_prompt = (
        "You are a critical document reviewer. Your job is to find "
        "problems, gaps, and weaknesses in the document under review. "
        "Be specific and cite evidence from the text.\n\n"
        "Check for:\n"
        "1. Internal contradictions within the document\n"
        "2. Assumptions that conflict with the similar/related "
        "documents provided (reference them by #ID)\n"
        "3. Missing considerations or blind spots\n"
        "4. Outdated information — flag temporal language like "
        '"currently", "today", "now", or explicit dates\n'
        "5. Completeness — is anything important about the topic "
        "left unaddressed?\n\n"
        "Format your review as a numbered list of findings. "
        "For each finding, state the issue and quote the relevant "
        "text. End with a brief overall assessment."
    )

    user_parts = [f"# Document Under Review (#{doc_id}: {title})\n\n{content}"]
    if similar_context:
        user_parts.append("# Related Documents for Cross-Reference\n\n" + similar_context)
    else:
        user_parts.append(
            "(No similar documents available for cross-reference. "
            "Review the document in isolation.)"
        )
    user_message = "\n\n---\n\n".join(user_parts)

    try:
        from emdx.services.ask_service import _execute_claude_prompt

        result = _execute_claude_prompt(
            system_prompt=system_prompt,
            user_message=user_message,
            title=f"Review: {title[:50]}",
            model=DEFAULT_LLM_MODEL,
        )
    except RuntimeError as e:
        console.print(f"[red]Review generation failed: {e}[/red]")
        raise typer.Exit(1) from e

    # Display in a Rich panel
    panel = Panel(
        result,
        title=f"Review of #{doc_id}: {escape(title)}",
        border_style="yellow",
        padding=(1, 2),
    )
    console.print(panel)

    if similar_ids:
        id_list = ", ".join(f"#{sid}" for sid in similar_ids)
        console.print(f"\n[dim]Similar docs referenced: {id_list}[/dim]")


def _print_view_header_plain(doc: Document, doc_tags: list[str]) -> None:
    """Print a plain text header for machine-friendly output."""
    print(f"#{doc.id}  {doc.title}")

    meta = []
    if doc.project:
        meta.append(f"Project: {doc.project}")
    created = str(doc.created_at or "")[:16]
    if created:
        meta.append(f"Created: {created}")
    updated = str(doc.updated_at or "")[:16]
    if updated and updated != created:
        meta.append(f"Updated: {updated}")
    if doc_tags:
        meta.append(f"Tags: {format_tags(doc_tags)}")
    if meta:
        print("  ".join(meta))
    print("---")


def _print_view_header_rich(doc: Document, doc_tags: list[str]) -> None:
    """Print a rich panel header for document view, matching the TUI."""
    content = doc.content
    word_count = len(content.split())
    char_count = len(content)
    line_count = content.count("\n") + 1 if content else 0

    lines = []
    lines.append(f"[bold cyan]#{doc.id}[/bold cyan]  [bold]{doc.title}[/bold]")
    lines.append("")

    if doc.project:
        lines.append(f"  [dim]Project:[/dim]   {doc.project}")

    if doc_tags:
        lines.append(f"  [dim]Tags:[/dim]      {format_tags(doc_tags)}")

    created = str(doc.created_at or "")[:16]
    updated = str(doc.updated_at or "")[:16]
    accessed = str(doc.accessed_at or "")[:16]

    if created:
        lines.append(f"  [dim]Created:[/dim]   {created}")
    if updated and updated != created:
        lines.append(f"  [dim]Updated:[/dim]   {updated}")
    if accessed:
        lines.append(f"  [dim]Accessed:[/dim]  {accessed}")

    lines.append(
        f"  [dim]Views:[/dim]     {doc.access_count}   "
        f"[dim]Words:[/dim] {word_count}   "
        f"[dim]Lines:[/dim] {line_count}   "
        f"[dim]Chars:[/dim] {char_count}"
    )

    if doc.parent_id:
        lines.append(f"  [dim]Parent:[/dim]    #{doc.parent_id}")

    panel = Panel(
        "\n".join(lines),
        border_style="cyan",
        padding=(0, 1),
    )
    console.print(panel)


def _print_related_docs(
    doc_id: int,
    links: list[Any],
    rich_mode: bool,
) -> None:
    """Print related documents section for the view command."""
    related: list[tuple[int, str, float]] = []
    for link in links:
        if link["source_doc_id"] == doc_id:
            related.append(
                (
                    link["target_doc_id"],
                    link["target_title"],
                    link["similarity_score"],
                )
            )
        else:
            related.append(
                (
                    link["source_doc_id"],
                    link["source_title"],
                    link["similarity_score"],
                )
            )

    if rich_mode:
        items = [
            f"  [cyan]#{rid}[/cyan] {rtitle} [dim]({score:.0%})[/dim]"
            for rid, rtitle, score in related
        ]
        console.print(f"  [dim]Related:[/dim]   {items[0].strip()}")
        for item in items[1:]:
            console.print(f"             {item.strip()}")
    else:
        parts = [f"#{rid} {rtitle} ({score:.0%})" for rid, rtitle, score in related]
        print(f"Related: {', '.join(parts)}")


def _flag_wiki_staleness(doc_id: int) -> None:
    """Flag wiki articles sourced from this doc as stale (non-critical)."""
    try:
        from emdx.services.wiki_staleness_service import check_doc_staleness

        check_doc_staleness(doc_id)
    except sqlite3.OperationalError:
        pass  # Wiki tables may not exist; non-critical


def _resolve_edit_body(file: str | None, content: str | None) -> str | None:
    """Resolve a non-interactive content source for `edit`, if one was given.

    Sources, mirroring `save`: --file (with '-' meaning stdin), --content,
    or piped stdin. Returns None when no source is present (interactive
    editor should launch).
    """
    import sys

    if file is not None and content is not None:
        console.print("[red]Error: --file and --content are mutually exclusive[/red]")
        raise typer.Exit(1)

    if file == "-":
        return sys.stdin.read()
    if file is not None:
        fp = Path(file)
        if not fp.exists() or not fp.is_file():
            console.print(f"[red]Error: File not found: {file}[/red]")
            raise typer.Exit(1)
        try:
            return fp.read_text(encoding="utf-8")
        except Exception as e:
            console.print(f"[red]Error reading file: {e}[/red]")
            raise typer.Exit(1) from e
    if content is not None:
        return content

    # Piped stdin (guarded like save: never block on an open-but-idle stdin)
    if not sys.stdin.isatty() and _stdin_ready(STDIN_PROBE_TIMEOUT):
        piped = sys.stdin.read()
        if piped.strip():
            return piped

    return None


@app.command()
def edit(
    identifier: str = typer.Argument(..., help="Document ID or title"),
    title: str | None = typer.Option(
        None, "--title", "-t", help="Update title without editing content"
    ),
    file: str | None = typer.Option(
        None, "--file", "-f", help="Replace content from a file path ('-' reads stdin)"
    ),
    content: str | None = typer.Option(None, "--content", help="Replace content from a string"),
    editor: str | None = typer.Option(
        None, "--editor", "-e", help="Editor to use (default: $EDITOR)"
    ),
) -> None:
    """Edit a document in the knowledge base.

    Non-interactive updates: --file PATH, --file - (stdin), --content TEXT,
    or pipe new content via stdin. Combine with --title to update both at
    once. With no content source, opens $EDITOR as before.
    """
    try:
        # Fetch document
        doc = get_document(identifier)

        if not doc:
            console.print(f"[red]Error: Document '{identifier}' not found[/red]")
            raise typer.Exit(1)

        # Non-interactive content update (--file / --content / piped stdin)
        new_body = _resolve_edit_body(file, content)
        if new_body is not None:
            new_title = title or doc.title
            success = update_document(doc.id, new_title, new_body)
            if success:
                console.print(f"[green]✅ Updated #{doc.id}:[/green] [cyan]{new_title}[/cyan]")
                if title and title != doc.title:
                    console.print(f"   [dim]Title changed from:[/dim] {doc.title}")
                console.print("   [dim]Content updated[/dim]")
                _flag_wiki_staleness(doc.id)
            else:
                console.print("[red]Error updating document[/red]")
                raise typer.Exit(1)
            return

        # Quick title update without editing content
        if title:
            success = update_document(doc.id, title, doc.content)
            if success:
                console.print(
                    f"[green]✅ Updated title of #{doc.id} to:[/green] [cyan]{title}[/cyan]"
                )
                _flag_wiki_staleness(doc.id)
            else:
                console.print("[red]Error updating document title[/red]")
                raise typer.Exit(1)
            return

        # Determine editor to use
        if not editor:
            editor = os.environ.get("EDITOR", "nano")

        # Create temporary file with current content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as tmp_file:
            # Write header comment
            tmp_file.write(f"# Editing: {doc.title} (ID: {doc.id})\n")
            tmp_file.write(f"# Project: {doc.project or 'None'}\n")
            tmp_file.write(f"# Created: {str(doc.created_at or '')[:16]}\n")
            tmp_file.write("#\n")
            tmp_file.write("# First line below the marker is the title\n")
            tmp_file.write("# The rest is the content (saved verbatim, headings included)\n")
            tmp_file.write(f"{EDIT_PREAMBLE_SENTINEL}\n")

            # Write title and content
            tmp_file.write(f"{doc.title}\n\n")
            tmp_file.write(doc.content)
            tmp_file_path = tmp_file.name

        try:
            # Open editor
            console.print(f"[dim]Opening {editor}...[/dim]")
            result = subprocess.run([editor, tmp_file_path])

            if result.returncode != 0:
                console.print(f"[red]Editor exited with error code {result.returncode}[/red]")
                raise typer.Exit(1)

            # Read edited content
            with open(tmp_file_path) as f:
                lines = f.readlines()

            # Strip only the instructional preamble, never the body: everything
            # up to and including the sentinel line is discarded. If the user
            # deleted the sentinel, fall back to dropping the leading comment
            # block so Markdown headings in the body survive either way.
            sentinel_idx = next(
                (i for i, line in enumerate(lines) if line.strip() == EDIT_PREAMBLE_SENTINEL),
                None,
            )
            if sentinel_idx is not None:
                lines = lines[sentinel_idx + 1 :]
            else:
                while lines and lines[0].strip().startswith("#"):
                    lines.pop(0)

            # Extract title and content
            if not lines:
                console.print("[yellow]No changes made (empty file)[/yellow]")
                return

            # First non-empty line is the title
            new_title = ""
            content_start = 0
            for i, line in enumerate(lines):
                if line.strip():
                    new_title = line.strip()
                    content_start = i + 1
                    break

            if not new_title:
                console.print("[yellow]No changes made (no title found)[/yellow]")
                return

            # Rest is content
            new_content = "".join(lines[content_start:]).strip()

            # Check if anything changed
            if new_title == doc.title and new_content == doc.content.strip():
                console.print("[yellow]No changes made[/yellow]")
                return

            # Update document
            success = update_document(doc.id, new_title, new_content)

            if success:
                console.print(f"[green]✅ Updated #{doc.id}:[/green] [cyan]{new_title}[/cyan]")
                if new_title != doc.title:
                    console.print(f"   [dim]Title changed from:[/dim] {doc.title}")
                console.print("   [dim]Content updated[/dim]")
                _flag_wiki_staleness(doc.id)
            else:
                console.print("[red]Error updating document[/red]")
                raise typer.Exit(1)

        finally:
            # Clean up temp file
            os.unlink(tmp_file_path)

    except Exception as e:
        console.print(f"[red]Error editing document: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def delete(
    identifiers: list[str] = typer.Argument(help="Document ID(s) or title(s) to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
    hard: bool = typer.Option(False, "--hard", help="Permanently delete (cannot be restored)"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be deleted without deleting"
    ),
) -> None:
    """Delete one or more documents (soft delete by default)"""
    try:
        # Collect documents to delete
        docs_to_delete = []
        not_found = []

        for identifier in identifiers:
            doc = get_document(identifier)
            if doc:
                docs_to_delete.append(doc)
            else:
                not_found.append(identifier)

        # Report not found
        if not_found:
            console.print("[yellow]Warning: The following documents were not found:[/yellow]")
            for nf in not_found:
                console.print(f"  [dim]• {nf}[/dim]")
            console.print()

        if not docs_to_delete:
            console.print("[red]No valid documents to delete[/red]")
            raise typer.Exit(1)

        # Show what will be deleted
        console.print(
            f"\n[bold]{'Would delete' if dry_run else 'Will delete'} "
            f"{len(docs_to_delete)} document(s):[/bold]\n"
        )

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="white")
        table.add_column("Project", style="green")
        table.add_column("Created", style="yellow")
        table.add_column("Type", style="red" if hard else "yellow")

        for doc in docs_to_delete:
            table.add_row(
                str(doc.id),
                doc.title[:50] + "..." if len(doc.title) > 50 else doc.title,
                doc.project or "[dim]None[/dim]",
                str(doc.created_at or "")[:10],
                "[red]PERMANENT[/red]" if hard else "[yellow]Soft delete[/yellow]",
            )

        console.print(table)

        if dry_run:
            console.print("\n[dim]This is a dry run. No documents were deleted.[/dim]")
            return

        # Confirmation (skip when stdin is not a TTY to avoid hanging agents)
        if not force and not is_non_interactive():
            if hard:
                console.print(
                    f"\n[red bold]⚠️  WARNING: This will PERMANENTLY delete "
                    f"{len(docs_to_delete)} document(s)![/red bold]"
                )
                console.print("[red]This action cannot be undone![/red]\n")
                confirm = typer.confirm("Are you absolutely sure?", abort=True)
                if confirm:
                    # Extra confirmation for hard delete
                    typer.confirm("Type 'yes' to confirm permanent deletion", abort=True)
            else:
                console.print(
                    f"\n[yellow]This will move {len(docs_to_delete)} document(s) to trash.[/yellow]"
                )
                console.print("[dim]You can restore them later with 'emdx trash restore'[/dim]\n")
                confirm = typer.confirm("Continue?", abort=True)

        # Perform deletion
        deleted_count = 0
        failed = []

        for doc in docs_to_delete:
            success = delete_document(str(doc.id), hard_delete=hard)
            if success:
                deleted_count += 1
            else:
                failed.append(doc)

        # Report results
        if deleted_count > 0:
            if hard:
                console.print(
                    f"\n[green]✅ Permanently deleted {deleted_count} document(s)[/green]"
                )  # noqa: E501
            else:
                console.print(f"\n[green]✅ Moved {deleted_count} document(s) to trash[/green]")
                console.print("[dim]💡 Use 'emdx trash' to view deleted documents[/dim]")
                console.print("[dim]💡 Use 'emdx trash restore <id>' to restore documents[/dim]")

        if failed:
            console.print(f"\n[red]Failed to delete {len(failed)} document(s):[/red]")
            for doc in failed:
                console.print(f"  [dim]• #{doc.id}: {doc.title}[/dim]")

    except typer.Abort:
        console.print("[yellow]Deletion cancelled[/yellow]")
        raise typer.Exit(0) from None
    except Exception as e:
        console.print(f"[red]Error deleting documents: {e}[/red]")
        raise typer.Exit(1) from e
