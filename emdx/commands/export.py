"""Export command for emdx.

This module provides the main export command that transforms and exports
documents using export profiles.
"""

from typing import Optional

import typer
from rich.panel import Panel
from rich.syntax import Syntax

from emdx.database import db
from emdx.models import export_profiles
from emdx.models.documents import get_document
from emdx.services.content_transformer import ContentTransformer
from emdx.services.export_destinations import (
    get_destination,
    execute_post_actions,
    ExportResult,
)
from emdx.utils.output import console

app = typer.Typer(help="Export documents using profiles")


@app.command("export")
def export_document(
    identifier: str = typer.Argument(..., help="Document ID or title"),
    profile: str = typer.Option(..., "--profile", "-p", help="Export profile name"),
    dest: Optional[str] = typer.Option(
        None, "--dest", "-d", help="Override destination (clipboard, file, gdoc, gist)"
    ),
    dest_path: Optional[str] = typer.Option(
        None, "--path", help="Override destination path (for file destination)"
    ),
    preview: bool = typer.Option(
        False, "--preview", help="Show transformed content without exporting"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would happen without exporting"
    ),
):
    """Export a document using an export profile.

    Transforms the document content according to the profile configuration
    and exports to the specified destination.

    Examples:

        # Export to clipboard using blog-post profile
        emdx export 42 --profile blog-post

        # Preview without exporting
        emdx export "My Notes" --profile github-issue --preview

        # Override destination
        emdx export 42 --profile blog-post --dest clipboard

        # Export to specific file
        emdx export 42 --profile share-external --dest file --path ~/export.md
    """
    db.ensure_schema()

    # Get the document
    doc = get_document(identifier)
    if not doc:
        console.print(f"[red]Error: Document '{identifier}' not found[/red]")
        raise typer.Exit(1)

    # Get the profile
    profile_obj = export_profiles.get_profile(profile)
    if not profile_obj:
        console.print(f"[red]Error: Export profile '{profile}' not found[/red]")
        console.print("\nAvailable profiles:")
        profiles = export_profiles.list_profiles()
        for p in profiles:
            console.print(f"  - {p['name']}: {p['display_name']}")
        raise typer.Exit(1)

    # Override destination if specified
    if dest:
        profile_obj = dict(profile_obj)  # Copy to avoid modifying original
        profile_obj["dest_type"] = dest
    if dest_path:
        profile_obj = dict(profile_obj) if not isinstance(profile_obj, dict) else profile_obj
        profile_obj["dest_path"] = dest_path

    # Transform content
    transformer = ContentTransformer(doc, profile_obj)
    ctx = transformer.transform()

    # Preview mode - show transformed content
    if preview:
        console.print(Panel(
            f"[bold]Document:[/bold] #{doc['id']} {doc['title']}\n"
            f"[bold]Profile:[/bold] {profile_obj['display_name']}\n"
            f"[bold]Destination:[/bold] {profile_obj['dest_type']}",
            title="Export Preview",
        ))
        console.print()

        # Show transformed content with syntax highlighting
        syntax = Syntax(
            ctx.transformed_content,
            "markdown",
            theme="monokai",
            line_numbers=True,
            word_wrap=True,
        )
        console.print(Panel(syntax, title="Transformed Content"))
        return

    # Dry run mode - show what would happen
    if dry_run:
        console.print("[bold]Dry Run - No changes will be made[/bold]\n")
        console.print(f"[bold]Document:[/bold] #{doc['id']} {doc['title']}")
        console.print(f"[bold]Profile:[/bold] {profile_obj['display_name']}")
        console.print(f"[bold]Format:[/bold] {profile_obj['format']}")
        console.print(f"[bold]Destination:[/bold] {profile_obj['dest_type']}")

        if profile_obj.get("dest_path"):
            console.print(f"[bold]Path:[/bold] {profile_obj['dest_path']}")

        console.print(f"\n[bold]Transforms applied:[/bold]")
        if profile_obj.get("strip_tags"):
            console.print(f"  - Strip tags: {', '.join(profile_obj['strip_tags'])}")
        if profile_obj.get("tag_to_label"):
            console.print(f"  - Tag to label mapping")
        if profile_obj.get("header_template"):
            console.print(f"  - Header template")
        if profile_obj.get("footer_template"):
            console.print(f"  - Footer template")
        if profile_obj.get("add_frontmatter"):
            console.print(f"  - YAML frontmatter")

        if profile_obj.get("post_actions"):
            console.print(f"\n[bold]Post-actions:[/bold]")
            for action in profile_obj["post_actions"]:
                console.print(f"  - {action}")

        console.print(f"\n[bold]Content length:[/bold] {len(ctx.transformed_content)} chars")
        return

    # Execute export
    dest_type = profile_obj["dest_type"]

    try:
        destination = get_destination(dest_type)
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    console.print(
        f"[yellow]Exporting '{doc['title']}' using profile '{profile_obj['display_name']}'...[/yellow]"
    )

    result = destination.export(ctx.transformed_content, doc, profile_obj)

    if result.success:
        console.print(f"[green]✓ {result.message}[/green]")

        if result.dest_url:
            console.print(f"[blue]URL: {result.dest_url}[/blue]")

        # Record in history
        export_profiles.record_export(
            document_id=doc["id"],
            profile_id=profile_obj["id"],
            dest_type=dest_type,
            dest_url=result.dest_url,
        )

        # Execute post-actions
        post_messages = execute_post_actions(result, profile_obj)
        for msg in post_messages:
            console.print(f"[green]✓ {msg}[/green]")

    else:
        console.print(f"[red]✗ {result.message}[/red]")
        raise typer.Exit(1)


@app.command("quick")
def quick_export(
    identifier: str = typer.Argument(..., help="Document ID or title"),
    profile_number: int = typer.Option(
        1, "--n", "-n", help="Profile number from list (1-9)"
    ),
):
    """Quick export using profile number.

    Exports using one of your most-used profiles by number (1-9).
    Profile #1 is your most-used profile, #2 is second most-used, etc.

    Example:
        emdx export quick 42 -n 1  # Use most-used profile
        emdx export quick 42 -n 2  # Use second most-used profile
    """
    db.ensure_schema()

    # Get profiles sorted by usage
    profiles = export_profiles.list_profiles()
    if not profiles:
        console.print("[red]Error: No export profiles found[/red]")
        raise typer.Exit(1)

    if profile_number < 1 or profile_number > len(profiles):
        console.print(
            f"[red]Error: Profile number must be between 1 and {len(profiles)}[/red]"
        )
        raise typer.Exit(1)

    profile = profiles[profile_number - 1]

    # Delegate to main export command
    export_document(
        identifier=identifier,
        profile=profile["name"],
        dest=None,
        dest_path=None,
        preview=False,
        dry_run=False,
    )


@app.command("list-profiles")
def list_quick_profiles():
    """List profiles with their quick-export numbers.

    Shows profiles sorted by usage, with numbers 1-9 for quick export.
    """
    db.ensure_schema()

    profiles = export_profiles.list_profiles()
    if not profiles:
        console.print("[yellow]No export profiles found[/yellow]")
        return

    console.print("[bold]Quick Export Profiles[/bold]")
    console.print("Use: emdx export quick <doc> -n <number>\n")

    for i, profile in enumerate(profiles[:9], 1):
        marker = f"[{i}]"
        console.print(
            f"  {marker} {profile['name']:<20} "
            f"({profile['dest_type']}) - {profile.get('use_count', 0)} uses"
        )

    if len(profiles) > 9:
        console.print(f"\n  ... and {len(profiles) - 9} more profiles")
