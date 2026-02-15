"""
Core CRUD operations for emdx
"""

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from rich.markdown import Markdown
from rich.table import Table

from emdx.database import db
from emdx.database.documents import (
    find_supersede_candidate,
    set_parent,
)
from emdx.database.types import SupersedeCandidate
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
from emdx.utils.emoji_aliases import expand_alias_string
from emdx.utils.output import console
from emdx.utils.text_formatting import truncate_title

app = typer.Typer(help="Core CRUD operations for documents")


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
    tags: list[str] | None = None


def get_input_content(input_arg: str | None) -> InputContent:
    """Handle input from stdin, file, or direct text"""
    import sys

    # Priority 1: Check if stdin has data
    if not sys.stdin.isatty():
        content = sys.stdin.read()
        if content.strip():  # Only use stdin if it has actual content
            return InputContent(content=content, source_type="stdin")
        # Fall through to check input_arg if stdin is empty

    # Priority 2: Check if input is provided
    if input_arg:
        # Check if it's a file path
        file_path = Path(input_arg)
        if file_path.exists() and file_path.is_file():
            # It's a file
            try:
                content = file_path.read_text(encoding="utf-8")
                return InputContent(content=content, source_type="file", source_path=file_path)
            except Exception as e:
                console.print(f"[red]Error reading file: {e}[/red]")
                raise typer.Exit(1) from e
        else:
            # Treat as direct content
            return InputContent(content=input_arg, source_type="direct")

    # No input provided
    else:
        console.print(
            "[red]Error: No input provided. Provide a file path, text content, "
            "or pipe data via stdin[/red]"
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
    # Ensure database schema exists
    try:
        db.ensure_schema()
    except Exception as e:
        console.print(f"[red]Database error: {e}[/red]")
        raise typer.Exit(1) from e

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

    # Expand aliases in the tag string before parsing
    expanded_tags_str = expand_alias_string(tags_str)
    tag_list = [t.strip() for t in expanded_tags_str.split(",") if t.strip()]
    if tag_list:
        return add_tags_to_document(doc_id, tag_list)
    return []


def display_save_result(
    doc_id: int,
    metadata: DocumentMetadata,
    applied_tags: list[str],
    supersede_target: SupersedeCandidate | None = None,
) -> None:
    """Display save result to user"""
    console.print(f"[green]✅ Saved as #{doc_id}:[/green] [cyan]{metadata.title}[/cyan]")
    if supersede_target:
        console.print(f"   [dim]↳ Superseded #{supersede_target['id']}[/dim]")
    if metadata.project:
        console.print(f"   [dim]Project:[/dim] {metadata.project}")
    if applied_tags:
        console.print(f"   [dim]Tags:[/dim] {format_tags(applied_tags)}")


@app.command()
def save(
    input: str | None = typer.Argument(
        None, help="File path or content to save (reads from stdin if not provided)"
    ),
    title: str | None = typer.Option(None, "--title", "-t", help="Document title"),
    project: str | None = typer.Option(
        None, "--project", "-p", help="Project name (auto-detected from git)"
    ),
    tags: str | None = typer.Option(None, "--tags", help="Comma-separated tags"),
    group_id: int | None = typer.Option(
        None, "--group", "-g",
        help="Add document to group",
        envvar="EMDX_GROUP_ID"
    ),
    group_role: str = typer.Option(
        "member", "--group-role",
        help="Role in group (primary, exploration, synthesis, variant, member)"
    ),
    auto_tag: bool = typer.Option(False, "--auto-tag", help="Automatically apply suggested tags"),
    suggest_tags: bool = typer.Option(False, "--suggest-tags", help="Show tag suggestions after saving"),  # noqa: E501
    supersede: bool = typer.Option(
        False, "--supersede", help="Auto-link to existing doc with same title (disabled by default)"
    ),
    gist: bool = typer.Option(False, "--gist/--no-gist", "--share", help="Create a GitHub gist after saving"),  # noqa: E501
    public: bool = typer.Option(False, "--public", help="Make gist public (default: secret)"),
    secret: bool = typer.Option(False, "--secret", help="Make gist secret (default, for explicitness)"),  # noqa: E501
    copy_url: bool = typer.Option(False, "--copy", "-c", help="Copy gist URL to clipboard"),
    open_browser: bool = typer.Option(False, "--open", "-o", help="Open gist in browser"),
) -> None:
    """Save content to the knowledge base (from file, stdin, or direct text)"""
    # Step 1: Get input content
    input_content = get_input_content(input)

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
        set_parent(supersede_target["id"], doc_id, relationship="supersedes")

    # Step 6: Apply tags
    applied_tags = apply_tags(doc_id, tags)

    # Step 6.5: Add to group if specified
    if group_id is not None:
        from emdx.database import groups
        group = groups.get_group(group_id)
        if group:
            success = groups.add_document_to_group(group_id, doc_id, role=group_role)
            if success:
                console.print(f"   [dim]Group:[/dim] #{group_id} ({group['name']})")
        else:
            console.print(f"   [yellow]Warning: Group #{group_id} not found[/yellow]")

    # Step 7: Auto-tagging if requested
    if auto_tag:
        tagger = AutoTagger()
        auto_applied = tagger.auto_tag_document(doc_id, confidence_threshold=0.7)
        if auto_applied:
            applied_tags.extend(auto_applied)
            console.print(f"   [dim]Auto-tagged:[/dim] {format_tags(auto_applied)}")

    # Step 8: Display result
    display_save_result(doc_id, metadata, applied_tags, supersede_target)

    # Step 9: Show tag suggestions if requested
    if suggest_tags and not auto_tag:
        tagger = AutoTagger()
        suggestions = tagger.suggest_tags(doc_id, max_suggestions=3)
        if suggestions:
            console.print("\n[dim]Suggested tags:[/dim]")
            for tag, confidence in suggestions:
                console.print(f"   • {tag} [dim]({confidence:.0%})[/dim]")
            console.print(f"\n[dim]Apply with: emdx tag {doc_id} <tags>[/dim]")

    # Step 10: Create gist if requested (--secret or --public imply --gist)
    if secret or public:
        gist = True
    if gist:
        if public and secret:
            console.print("[red]Error: Cannot use both --public and --secret[/red]")
            raise typer.Exit(1)

        import webbrowser as wb

        from emdx.commands.gist import (
            copy_to_clipboard,
            create_gist_with_gh,
            get_github_auth,
            sanitize_filename,
        )

        token = get_github_auth()
        if not token:
            console.print("[yellow]⚠ Gist skipped: GitHub auth not configured (run 'gh auth login')[/yellow]")  # noqa: E501
        else:
            filename = sanitize_filename(metadata.title)
            description = f"{metadata.title} - emdx knowledge base"
            if metadata.project:
                description += f" (Project: {metadata.project})"

            console.print(f"[dim]Creating {'public' if public else 'secret'} gist...[/dim]")

            result = create_gist_with_gh(input_content.content, filename, description, public)

            if result:
                gist_id_str = result["id"]
                gist_url = result["url"]

                # Record in gists table
                try:
                    with db.get_connection() as conn:
                        conn.execute(
                            "INSERT INTO gists (document_id, gist_id, gist_url, is_public) VALUES (?, ?, ?, ?)",  # noqa: E501
                            (doc_id, gist_id_str, gist_url, public),
                        )
                        conn.commit()
                except Exception as e:
                    console.print(f"   [dim]Warning: Failed to record gist in database: {e}[/dim]")

                console.print(f"   [green]Gist:[/green] {gist_url}")

                if copy_url:
                    if copy_to_clipboard(gist_url):
                        console.print("   [green]✓ URL copied to clipboard[/green]")
                    else:
                        console.print("   [yellow]⚠ Could not copy to clipboard[/yellow]")

                if open_browser:
                    wb.open(gist_url)
                    console.print("   [green]✓ Opened in browser[/green]")
            else:
                console.print("[yellow]⚠ Gist creation failed (document was saved successfully)[/yellow]")  # noqa: E501


@app.command()
def find(
    query: list[str] | None = typer.Argument(
        default=None, help="Search terms (optional if using --tags)"
    ),
    project: str | None = typer.Option(None, "--project", "-p", help="Filter by project"),
    limit: int = typer.Option(10, "--limit", "-n", help="Maximum results to return"),
    snippets: bool = typer.Option(False, "--snippets", "-s", help="Show content snippets"),
    fuzzy: bool = typer.Option(False, "--fuzzy", "-f", help="Use fuzzy search"),
    tags: str | None = typer.Option(
        None, "--tags", "-t", help="Filter by tags (comma-separated)"
    ),
    any_tags: bool = typer.Option(False, "--any-tags", help="Match ANY tag instead of ALL tags"),
    no_tags: str | None = typer.Option(None, "--no-tags", help="Exclude documents with these tags"),
    ids_only: bool = typer.Option(False, "--ids-only", help="Output only document IDs (for piping)"),  # noqa: E501
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON"),
    created_after: str | None = typer.Option(None, "--created-after", help="Show documents created after date (YYYY-MM-DD)"),  # noqa: E501
    created_before: str | None = typer.Option(None, "--created-before", help="Show documents created before date (YYYY-MM-DD)"),  # noqa: E501
    modified_after: str | None = typer.Option(None, "--modified-after", help="Show documents modified after date (YYYY-MM-DD)"),  # noqa: E501
    modified_before: str | None = typer.Option(None, "--modified-before", help="Show documents modified before date (YYYY-MM-DD)"),  # noqa: E501
) -> None:
    """Search the knowledge base with full-text search"""
    search_query = " ".join(query) if query else ""

    try:
        # Ensure database schema exists
        db.ensure_schema()

        # Validate that we have something to search for
        has_date_filters = any([created_after, created_before, modified_after, modified_before])
        if not search_query and not tags and not has_date_filters:
            console.print("[red]Error: Provide search terms, tags, or date filters[/red]")
            raise typer.Exit(1)

        # Handle tag-based search
        if tags:
            # Expand aliases in the tag string before parsing
            expanded_tags = expand_alias_string(tags)
            tag_list = [t.strip() for t in expanded_tags.split(",") if t.strip()]
            tag_mode = "any" if any_tags else "all"

            # If we have both tags and search query, we need to combine results
            if search_query:
                # Get documents matching tags
                tag_results = search_by_tags(tag_list, mode=tag_mode, project=project, limit=limit)
                tag_doc_ids = {doc["id"] for doc in tag_results}

                # Get documents matching search query
                search_results = search_documents(
                    search_query, project=project, limit=limit * 2, fuzzy=fuzzy,
                    created_after=created_after, created_before=created_before,
                    modified_after=modified_after, modified_before=modified_before
                )

                # Combine: only show documents that match both criteria
                results: list[dict[str, Any]] = [
                    dict(doc) for doc in search_results if doc["id"] in tag_doc_ids
                ][:limit]

                if not results:
                    console.print(
                        f"[yellow]No results found matching both '[/yellow]{search_query}[yellow]' "
                        f"and tags: {', '.join(tag_list)}[/yellow]"
                    )
                    return
            else:
                # Tag-only search
                results = search_by_tags(tag_list, mode=tag_mode, project=project, limit=limit)
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
                dict(doc) for doc in search_documents(
                    effective_query, project=project, limit=limit, fuzzy=fuzzy,
                    created_after=created_after, created_before=created_before,
                    modified_after=modified_after, modified_before=modified_before,
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
            expanded_no_tags = expand_alias_string(no_tags)
            no_tag_list = [t.strip() for t in expanded_no_tags.split(",") if t.strip()]

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
                        f"[yellow]No results found after excluding tags: {', '.join(no_tag_list)}[/yellow]"  # noqa: E501
                    )
                    return

        # Handle different output formats
        if ids_only:
            # Output only IDs, one per line
            for result in results:
                print(result['id'])
            return

        if json_output:
            # Output as JSON with all metadata
            output_results = []
            for result in results:
                # Use batch-fetched tags
                doc_tags = all_tags_map.get(result["id"], [])

                # Build clean result object
                created = result["created_at"]
                updated = result.get("updated_at") or created
                output_result = {
                    "id": result["id"],
                    "title": result["title"],
                    "project": result.get("project"),
                    "created_at": created.isoformat() if created else None,
                    "updated_at": updated.isoformat() if updated else None,
                    "tags": doc_tags,
                    "access_count": result.get("access_count", 0),
                }

                # Add search-specific metadata if available
                if "rank" in result:
                    output_result["relevance"] = result["rank"]
                elif "score" in result:
                    output_result["similarity"] = result["score"]

                if snippets and "snippet" in result:
                    # Clean snippet of HTML tags
                    output_result["snippet"] = result["snippet"].replace("<b>", "").replace("</b>", "")  # noqa: E501

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
        console.print(
            f"\n[bold]🔍 Found {len(results)} results for {search_description}[/bold]\n"
        )

        for i, result in enumerate(results, 1):
            # Display result header
            console.print(f"[bold cyan]#{result['id']}[/bold cyan] [bold]{result['title']}[/bold]")

            # Display metadata
            metadata = []
            if result["project"]:
                metadata.append(f"[green]{result['project']}[/green]")
            if result["created_at"]:
                metadata.append(f"[yellow]{result['created_at'].strftime('%Y-%m-%d')}[/yellow]")

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
            if snippets and "snippet" in result:
                # Clean up the snippet (remove HTML tags from highlighting)
                snippet = (
                    result["snippet"]
                    .replace("<b>", "[bold yellow]")
                    .replace("</b>", "[/bold yellow]")
                )
                console.print(f"[dim]...{snippet}...[/dim]")

            # Add spacing between results
            if i < len(results):
                console.print()

        # Show tip for viewing documents
        if len(results) > 0:
            console.print("\n[dim]💡 Use 'emdx view <id>' to view a document[/dim]")

    except Exception as e:
        console.print(f"[red]Error searching documents: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def view(
    identifier: str = typer.Argument(..., help="Document ID or title"),
    raw: bool = typer.Option(False, "--raw", "-r", help="Show raw markdown without formatting"),
    no_pager: bool = typer.Option(False, "--no-pager", help="Disable pager (for piping output)"),
    no_header: bool = typer.Option(False, "--no-header", help="Hide document header information"),
) -> None:
    """View a document from the knowledge base"""
    try:
        # Ensure database schema exists
        db.ensure_schema()

        # Fetch document
        doc = get_document(identifier)

        if not doc:
            console.print(f"[red]Error: Document '{identifier}' not found[/red]")
            raise typer.Exit(1)

        # Display document with or without pager
        if no_pager:
            # Direct output without pager
            if not no_header:
                console.print(f"\n[bold cyan]#{doc['id']}:[/bold cyan] [bold]{doc['title']}[/bold]")
                console.print("=" * 60)
                console.print(f"[dim]Project:[/dim] {doc['project'] or 'None'}")
                ca = doc['created_at']
                created_str = ca.strftime('%Y-%m-%d %H:%M') if ca else 'Unknown'
                console.print(f"[dim]Created:[/dim] {created_str}")
                console.print(f"[dim]Views:[/dim] {doc['access_count']}")
                # Show tags
                doc_tags = get_document_tags(doc["id"])
                if doc_tags:
                    console.print(f"[dim]Tags:[/dim] {format_tags(doc_tags)}")
                console.print("=" * 60 + "\n")

            if raw:
                console.print(doc["content"])
            else:
                markdown = Markdown(doc["content"])
                console.print(markdown)
        else:
            # Use Rich's pager with color support
            # Set LESS environment variable if not already set
            if "LESS" not in os.environ:
                os.environ["LESS"] = "-R"
            with console.pager():
                if not no_header:
                    console.print(
                        f"\n[bold cyan]#{doc['id']}:[/bold cyan] [bold]{doc['title']}[/bold]"
                    )
                    console.print("=" * 60)
                    console.print(f"[dim]Project:[/dim] {doc['project'] or 'None'}")
                    ca = doc['created_at']
                    created_str = ca.strftime('%Y-%m-%d %H:%M') if ca else 'Unknown'
                    console.print(f"[dim]Created:[/dim] {created_str}")
                    console.print(f"[dim]Views:[/dim] {doc['access_count']}")
                    # Show tags
                    doc_tags = get_document_tags(doc["id"])
                    if doc_tags:
                        console.print(f"[dim]Tags:[/dim] {format_tags(doc_tags)}")
                    console.print("=" * 60 + "\n")

                if raw:
                    console.print(doc["content"])
                else:
                    markdown = Markdown(doc["content"])
                    console.print(markdown)

    except Exception as e:
        console.print(f"[red]Error viewing document: {e}[/red]")
        raise typer.Exit(1) from e


@app.command()
def edit(
    identifier: str = typer.Argument(..., help="Document ID or title"),
    title: str | None = typer.Option(
        None, "--title", "-t", help="Update title without editing content"
    ),
    editor: str | None = typer.Option(
        None, "--editor", "-e", help="Editor to use (default: $EDITOR)"
    ),
) -> None:
    """Edit a document in the knowledge base"""
    try:
        # Ensure database schema exists
        db.ensure_schema()

        # Fetch document
        doc = get_document(identifier)

        if not doc:
            console.print(f"[red]Error: Document '{identifier}' not found[/red]")
            raise typer.Exit(1)

        # Quick title update without editing content
        if title:
            success = update_document(doc["id"], title, doc["content"])
            if success:
                console.print(
                    f"[green]✅ Updated title of #{doc['id']} to:[/green] [cyan]{title}[/cyan]"
                )
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
            tmp_file.write(f"# Editing: {doc['title']} (ID: {doc['id']})\n")
            tmp_file.write(f"# Project: {doc['project'] or 'None'}\n")
            ca = doc['created_at']
            created_str = ca.strftime('%Y-%m-%d %H:%M') if ca else 'Unknown'
            tmp_file.write(f"# Created: {created_str}\n")
            tmp_file.write("# Lines starting with '#' will be removed\n")
            tmp_file.write("#\n")
            tmp_file.write("# First line (after comments) will be used as the title\n")
            tmp_file.write("# The rest will be the content\n")
            tmp_file.write("#\n")

            # Write title and content
            tmp_file.write(f"{doc['title']}\n\n")
            tmp_file.write(doc["content"])
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

            # Remove comment lines
            lines = [line for line in lines if not line.strip().startswith("#")]

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
            if new_title == doc["title"] and new_content == doc["content"].strip():
                console.print("[yellow]No changes made[/yellow]")
                return

            # Update document
            success = update_document(doc["id"], new_title, new_content)

            if success:
                console.print(f"[green]✅ Updated #{doc['id']}:[/green] [cyan]{new_title}[/cyan]")
                if new_title != doc["title"]:
                    console.print(f"   [dim]Title changed from:[/dim] {doc['title']}")
                console.print("   [dim]Content updated[/dim]")
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
        # Ensure database schema exists
        db.ensure_schema()

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
                str(doc["id"]),
                doc["title"][:50] + "..." if len(doc["title"]) > 50 else doc["title"],
                doc["project"] or "[dim]None[/dim]",
                doc["created_at"].strftime("%Y-%m-%d") if doc["created_at"] else "",
                "[red]PERMANENT[/red]" if hard else "[yellow]Soft delete[/yellow]",
            )

        console.print(table)

        if dry_run:
            console.print("\n[dim]This is a dry run. No documents were deleted.[/dim]")
            return

        # Confirmation
        if not force:
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
            success = delete_document(str(doc["id"]), hard_delete=hard)
            if success:
                deleted_count += 1
            else:
                failed.append(doc)

        # Report results
        if deleted_count > 0:
            if hard:
                console.print(f"\n[green]✅ Permanently deleted {deleted_count} document(s)[/green]")  # noqa: E501
            else:
                console.print(f"\n[green]✅ Moved {deleted_count} document(s) to trash[/green]")
                console.print("[dim]💡 Use 'emdx trash' to view deleted documents[/dim]")
                console.print("[dim]💡 Use 'emdx trash restore <id>' to restore documents[/dim]")

        if failed:
            console.print(f"\n[red]Failed to delete {len(failed)} document(s):[/red]")
            for doc in failed:
                console.print(f"  [dim]• #{doc['id']}: {doc['title']}[/dim]")

    except typer.Abort:
        console.print("[yellow]Deletion cancelled[/yellow]")
        raise typer.Exit(0) from None
    except Exception as e:
        console.print(f"[red]Error deleting documents: {e}[/red]")
        raise typer.Exit(1) from e


