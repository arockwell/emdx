"""Export profile management commands for emdx.

This module provides CLI commands for managing export profiles:
- create: Create a new export profile
- list: List all export profiles
- show: Show details of a profile
- edit: Edit a profile in your editor
- delete: Delete a profile
- export-json: Export profile as JSON
- import-json: Import profile from JSON
"""

import json
import logging
import os
import subprocess
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

import typer
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from emdx.database import db
from emdx.models import export_profiles
from emdx.utils.output import console

app = typer.Typer(help="Manage export profiles")


@app.command("create")
def create_profile(
    name: str = typer.Argument(..., help="Profile name (e.g., 'blog-post')"),
    display_name: Optional[str] = typer.Option(
        None, "--display", "-D", help="Human-readable name"
    ),
    format: str = typer.Option(
        "markdown", "--format", "-f", help="Output format (markdown, gdoc, gist)"
    ),
    dest_type: str = typer.Option(
        "clipboard", "--dest", "-d", help="Destination type (clipboard, file, gdoc, gist)"
    ),
    dest_path: Optional[str] = typer.Option(
        None, "--path", help="File path (for file dest, supports {{title}}, {{date}})"
    ),
    strip_tags: Optional[str] = typer.Option(
        None, "--strip-tags", help="Comma-separated emoji tags to strip"
    ),
    add_frontmatter: bool = typer.Option(
        False, "--frontmatter", help="Add YAML frontmatter"
    ),
    frontmatter_fields: Optional[str] = typer.Option(
        None, "--fm-fields", help="Comma-separated frontmatter fields (title,date,tags,author)"
    ),
    header: Optional[str] = typer.Option(
        None, "--header", help="Header template (supports {{title}}, {{date}}, etc.)"
    ),
    footer: Optional[str] = typer.Option(
        None, "--footer", help="Footer template"
    ),
    tag_labels: Optional[str] = typer.Option(
        None, "--tag-labels", help="Tag to label mapping as JSON (e.g., '{\"🐛\": \"bug\"}')"
    ),
    description: Optional[str] = typer.Option(
        None, "--desc", help="Profile description"
    ),
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Project scope (default: global)"
    ),
):
    """Create a new export profile.

    Examples:

        # Basic clipboard profile
        emdx export-profile create my-profile

        # Blog post with frontmatter
        emdx export-profile create blog-post --frontmatter --fm-fields title,date,tags \\
            --dest file --path ~/blog/drafts/{{title}}.md

        # GitHub issue format
        emdx export-profile create github-issue --strip-tags 🚧,🚨 \\
            --tag-labels '{"🐛": "bug", "✨": "enhancement"}'
    """
    db.ensure_schema()

    # Check if profile already exists
    existing = export_profiles.get_profile(name)
    if existing:
        console.print(f"[red]Error: Profile '{name}' already exists[/red]")
        raise typer.Exit(1)

    # Parse comma-separated values
    strip_tags_list = None
    if strip_tags:
        strip_tags_list = [t.strip() for t in strip_tags.split(",")]

    fm_fields_list = None
    if frontmatter_fields:
        fm_fields_list = [f.strip() for f in frontmatter_fields.split(",")]

    tag_to_label = None
    if tag_labels:
        try:
            tag_to_label = json.loads(tag_labels)
        except json.JSONDecodeError as e:
            console.print(f"[red]Error parsing tag-labels JSON: {e}[/red]")
            raise typer.Exit(1)

    try:
        profile_id = export_profiles.create_profile(
            name=name,
            display_name=display_name or name.replace("-", " ").title(),
            description=description,
            format=format,
            strip_tags=strip_tags_list,
            add_frontmatter=add_frontmatter,
            frontmatter_fields=fm_fields_list,
            header_template=header,
            footer_template=footer,
            tag_to_label=tag_to_label,
            dest_type=dest_type,
            dest_path=dest_path,
            project=project,
        )

        console.print(f"[green]✓ Created export profile '{name}' (ID: {profile_id})[/green]")

    except Exception as e:
        logger.warning("Failed to create export profile: %s", e, exc_info=True)
        console.print(f"[red]Error creating profile: {e}[/red]")
        raise typer.Exit(1)


@app.command("list")
def list_profiles(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    output_format: str = typer.Option(
        "table", "--format", "-f", help="Output format: table, json"
    ),
    include_inactive: bool = typer.Option(
        False, "--all", "-a", help="Include inactive profiles"
    ),
):
    """List all export profiles."""
    db.ensure_schema()

    profiles = export_profiles.list_profiles(
        project=project,
        include_builtin=True,
        include_inactive=include_inactive,
    )

    if not profiles:
        console.print("[yellow]No export profiles found[/yellow]")
        return

    if output_format == "json":
        console.print(json.dumps(profiles, indent=2, default=str))
        return

    # Table output
    table = Table(title="Export Profiles")
    table.add_column("Name", style="cyan")
    table.add_column("Display Name", style="white")
    table.add_column("Format", style="blue")
    table.add_column("Destination", style="green")
    table.add_column("Uses", style="yellow", justify="right")
    table.add_column("Type", style="dim")

    for profile in profiles:
        profile_type = "Built-in" if profile.get("is_builtin") else "Custom"
        if not profile.get("is_active"):
            profile_type = "[dim]Inactive[/dim]"

        table.add_row(
            profile["name"],
            profile["display_name"],
            profile["format"],
            profile["dest_type"],
            str(profile.get("use_count", 0)),
            profile_type,
        )

    console.print(table)


@app.command("show")
def show_profile(
    name: str = typer.Argument(..., help="Profile name or ID"),
):
    """Show details of an export profile."""
    db.ensure_schema()

    profile = export_profiles.get_profile(name)
    if not profile:
        console.print(f"[red]Error: Profile '{name}' not found[/red]")
        raise typer.Exit(1)

    # Build profile display
    lines = [
        f"[bold cyan]Name:[/bold cyan] {profile['name']}",
        f"[bold]Display Name:[/bold] {profile['display_name']}",
        f"[bold]Description:[/bold] {profile.get('description') or 'N/A'}",
        "",
        f"[bold]Format:[/bold] {profile['format']}",
        f"[bold]Destination:[/bold] {profile['dest_type']}",
    ]

    if profile.get("dest_path"):
        lines.append(f"[bold]Destination Path:[/bold] {profile['dest_path']}")
    if profile.get("gdoc_folder"):
        lines.append(f"[bold]Google Drive Folder:[/bold] {profile['gdoc_folder']}")
    if profile.get("gist_public"):
        lines.append("[bold]Gist Visibility:[/bold] Public")

    lines.append("")
    lines.append("[bold cyan]Transforms:[/bold cyan]")

    if profile.get("strip_tags"):
        lines.append(f"  Strip tags: {', '.join(profile['strip_tags'])}")
    if profile.get("tag_to_label"):
        tag_map = profile["tag_to_label"]
        if isinstance(tag_map, dict):
            mappings = [f"{k}→{v}" for k, v in tag_map.items()]
            lines.append(f"  Tag labels: {', '.join(mappings)}")
    if profile.get("add_frontmatter"):
        fields = profile.get("frontmatter_fields") or ["title", "date"]
        lines.append(f"  Frontmatter: {', '.join(fields)}")
    if profile.get("header_template"):
        lines.append(f"  Header: {profile['header_template'][:50]}...")
    if profile.get("footer_template"):
        lines.append(f"  Footer: {profile['footer_template'][:50]}...")

    if profile.get("post_actions"):
        lines.append("")
        lines.append(f"[bold]Post-actions:[/bold] {', '.join(profile['post_actions'])}")

    lines.append("")
    lines.append("[bold dim]Stats:[/bold dim]")
    lines.append(f"  Uses: {profile.get('use_count', 0)}")
    if profile.get("last_used_at"):
        lines.append(f"  Last used: {profile['last_used_at']}")
    lines.append(f"  Type: {'Built-in' if profile.get('is_builtin') else 'Custom'}")
    lines.append(f"  Active: {'Yes' if profile.get('is_active') else 'No'}")

    panel = Panel("\n".join(lines), title=f"Export Profile: {profile['name']}")
    console.print(panel)


@app.command("edit")
def edit_profile(
    name: str = typer.Argument(..., help="Profile name or ID"),
):
    """Edit an export profile in your editor.

    Opens the profile configuration as JSON in your default editor.
    Changes are saved when you close the editor.
    """
    db.ensure_schema()

    profile = export_profiles.get_profile(name)
    if not profile:
        console.print(f"[red]Error: Profile '{name}' not found[/red]")
        raise typer.Exit(1)

    if profile.get("is_builtin"):
        console.print("[red]Error: Cannot edit built-in profiles[/red]")
        raise typer.Exit(1)

    # Create editable version of profile
    editable = {
        "name": profile["name"],
        "display_name": profile["display_name"],
        "description": profile.get("description"),
        "format": profile["format"],
        "dest_type": profile["dest_type"],
        "dest_path": profile.get("dest_path"),
        "gdoc_folder": profile.get("gdoc_folder"),
        "gist_public": profile.get("gist_public", False),
        "strip_tags": profile.get("strip_tags"),
        "add_frontmatter": profile.get("add_frontmatter", False),
        "frontmatter_fields": profile.get("frontmatter_fields"),
        "header_template": profile.get("header_template"),
        "footer_template": profile.get("footer_template"),
        "tag_to_label": profile.get("tag_to_label"),
        "post_actions": profile.get("post_actions"),
        "project": profile.get("project"),
    }

    # Write to temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as f:
        json.dump(editable, f, indent=2)
        temp_path = f.name

    try:
        # Get editor
        editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vim"))

        # Open editor
        subprocess.run([editor, temp_path], check=True)

        # Read updated content
        with open(temp_path, "r") as f:
            updated = json.load(f)

        # Update profile
        export_profiles.update_profile(
            profile["id"],
            display_name=updated.get("display_name"),
            description=updated.get("description"),
            format=updated.get("format"),
            dest_type=updated.get("dest_type"),
            dest_path=updated.get("dest_path"),
            gdoc_folder=updated.get("gdoc_folder"),
            gist_public=updated.get("gist_public"),
            strip_tags=updated.get("strip_tags"),
            add_frontmatter=updated.get("add_frontmatter"),
            frontmatter_fields=updated.get("frontmatter_fields"),
            header_template=updated.get("header_template"),
            footer_template=updated.get("footer_template"),
            tag_to_label=updated.get("tag_to_label"),
            post_actions=updated.get("post_actions"),
            project=updated.get("project"),
        )

        console.print(f"[green]✓ Updated profile '{name}'[/green]")

    except subprocess.CalledProcessError:
        console.print("[red]Editor exited with error[/red]")
        raise typer.Exit(1)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        logger.warning("Failed to update export profile: %s", e, exc_info=True)
        console.print(f"[red]Error updating profile: {e}[/red]")
        raise typer.Exit(1)
    finally:
        # Clean up temp file
        try:
            os.unlink(temp_path)
        except OSError as e:
            logger.debug("Failed to clean up temp file %s: %s", temp_path, e)


@app.command("delete")
def delete_profile(
    name: str = typer.Argument(..., help="Profile name or ID"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    hard: bool = typer.Option(False, "--hard", help="Permanently delete (not just deactivate)"),
):
    """Delete an export profile."""
    db.ensure_schema()

    profile = export_profiles.get_profile(name)
    if not profile:
        console.print(f"[red]Error: Profile '{name}' not found[/red]")
        raise typer.Exit(1)

    if profile.get("is_builtin"):
        console.print("[red]Error: Cannot delete built-in profiles[/red]")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(
            f"Delete profile '{profile['name']}'?"
        )
        if not confirm:
            console.print("Cancelled")
            raise typer.Exit(0)

    try:
        export_profiles.delete_profile(profile["id"], hard_delete=hard)
        action = "Deleted" if hard else "Deactivated"
        console.print(f"[green]✓ {action} profile '{name}'[/green]")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command("export-json")
def export_profile_json(
    name: str = typer.Argument(..., help="Profile name or ID"),
):
    """Export a profile as JSON for sharing.

    Example:
        emdx export-profile export-json my-profile > my-profile.json
    """
    db.ensure_schema()

    profile = export_profiles.get_profile(name)
    if not profile:
        console.print(f"[red]Error: Profile '{name}' not found[/red]", err=True)
        raise typer.Exit(1)

    # Remove internal fields
    exportable = {
        "name": profile["name"],
        "display_name": profile["display_name"],
        "description": profile.get("description"),
        "format": profile["format"],
        "dest_type": profile["dest_type"],
        "dest_path": profile.get("dest_path"),
        "gdoc_folder": profile.get("gdoc_folder"),
        "gist_public": profile.get("gist_public", False),
        "strip_tags": profile.get("strip_tags"),
        "add_frontmatter": profile.get("add_frontmatter", False),
        "frontmatter_fields": profile.get("frontmatter_fields"),
        "header_template": profile.get("header_template"),
        "footer_template": profile.get("footer_template"),
        "tag_to_label": profile.get("tag_to_label"),
        "post_actions": profile.get("post_actions"),
    }

    # Remove None values
    exportable = {k: v for k, v in exportable.items() if v is not None}

    print(json.dumps(exportable, indent=2))


@app.command("import-json")
def import_profile_json(
    file: typer.FileText = typer.Argument(..., help="JSON file to import"),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing profile"),
):
    """Import a profile from a JSON file.

    Example:
        emdx export-profile import-json my-profile.json
    """
    db.ensure_schema()

    try:
        data = json.load(file)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON: {e}[/red]")
        raise typer.Exit(1)

    if "name" not in data:
        console.print("[red]Error: Profile must have a 'name' field[/red]")
        raise typer.Exit(1)

    # Check if profile exists
    existing = export_profiles.get_profile(data["name"])
    if existing:
        if existing.get("is_builtin"):
            console.print("[red]Error: Cannot overwrite built-in profiles[/red]")
            raise typer.Exit(1)

        if not overwrite:
            console.print(
                f"[red]Error: Profile '{data['name']}' already exists. "
                "Use --overwrite to replace.[/red]"
            )
            raise typer.Exit(1)

        # Delete existing profile
        export_profiles.delete_profile(existing["id"], hard_delete=True)

    try:
        profile_id = export_profiles.create_profile(
            name=data["name"],
            display_name=data.get("display_name", data["name"]),
            description=data.get("description"),
            format=data.get("format", "markdown"),
            strip_tags=data.get("strip_tags"),
            add_frontmatter=data.get("add_frontmatter", False),
            frontmatter_fields=data.get("frontmatter_fields"),
            header_template=data.get("header_template"),
            footer_template=data.get("footer_template"),
            tag_to_label=data.get("tag_to_label"),
            dest_type=data.get("dest_type", "clipboard"),
            dest_path=data.get("dest_path"),
            gdoc_folder=data.get("gdoc_folder"),
            gist_public=data.get("gist_public", False),
            post_actions=data.get("post_actions"),
        )

        console.print(f"[green]✓ Imported profile '{data['name']}' (ID: {profile_id})[/green]")

    except Exception as e:
        logger.warning("Failed to import export profile: %s", e, exc_info=True)
        console.print(f"[red]Error importing profile: {e}[/red]")
        raise typer.Exit(1)


@app.command("history")
def show_history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of records to show"),
    profile: Optional[str] = typer.Option(
        None, "--profile", "-p", help="Filter by profile name"
    ),
):
    """Show export history."""
    db.ensure_schema()

    profile_id = None
    if profile:
        profile_obj = export_profiles.get_profile(profile)
        if not profile_obj:
            console.print(f"[red]Error: Profile '{profile}' not found[/red]")
            raise typer.Exit(1)
        profile_id = profile_obj["id"]

    history = export_profiles.get_export_history(
        profile_id=profile_id,
        limit=limit,
    )

    if not history:
        console.print("[yellow]No export history found[/yellow]")
        return

    table = Table(title="Export History")
    table.add_column("Document", style="cyan")
    table.add_column("Profile", style="green")
    table.add_column("Destination", style="blue")
    table.add_column("URL", style="dim")
    table.add_column("Date", style="dim")

    for record in history:
        url = record.get("dest_url") or "-"
        if len(url) > 40:
            url = url[:37] + "..."

        exported_at = record.get("exported_at")
        if exported_at:
            if hasattr(exported_at, "strftime"):
                date_str = exported_at.strftime("%Y-%m-%d %H:%M")
            else:
                date_str = str(exported_at)[:16]
        else:
            date_str = "-"

        table.add_row(
            f"#{record['document_id']} {record.get('document_title', '')[:30]}",
            record.get("profile_name", "?"),
            record.get("dest_type", "?"),
            url,
            date_str,
        )

    console.print(table)
