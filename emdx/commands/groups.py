"""CLI commands for document groups.

Document groups provide hierarchical organization of related documents
into batches, rounds, and initiatives.
"""

from typing import Optional

import typer
from rich.table import Table
from rich.tree import Tree

from emdx.database import db, groups
from emdx.models.documents import get_document
from emdx.utils.output import console

app = typer.Typer(help="Organize documents into hierarchical groups")


@app.command()
def create(
    name: str = typer.Argument(..., help="Group name"),
    group_type: str = typer.Option(
        "batch", "--type", "-t",
        help="Group type: batch, initiative, round, session, custom"
    ),
    parent: Optional[int] = typer.Option(
        None, "--parent", "-p", help="Parent group ID for nesting"
    ),
    project: Optional[str] = typer.Option(
        None, "--project", help="Associated project name"
    ),
    description: Optional[str] = typer.Option(
        None, "--description", "-d", help="Group description"
    ),
) -> None:
    """Create a new document group."""
    try:
        db.ensure_schema()

        # Validate parent exists if specified
        if parent is not None:
            parent_group = groups.get_group(parent)
            if not parent_group:
                console.print(f"[red]Error: Parent group #{parent} not found[/red]")
                raise typer.Exit(1) from None

        group_id = groups.create_group(
            name=name,
            group_type=group_type,
            parent_group_id=parent,
            project=project,
            description=description,
        )

        console.print(f"[green]✅ Created group #{group_id}:[/green] [cyan]{name}[/cyan]")
        console.print(f"   [dim]Type: {group_type}[/dim]")
        if parent:
            parent_group = groups.get_group(parent)
            console.print(f"   [dim]Parent: #{parent} ({parent_group['name']})[/dim]")
        if project:
            console.print(f"   [dim]Project: {project}[/dim]")

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error creating group: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def add(
    group_id: int = typer.Argument(..., help="Group ID to add documents to"),
    doc_ids: list[int] = typer.Argument(..., help="Document IDs to add"),
    role: str = typer.Option(
        "member", "--role", "-r",
        help="Role in group: primary, exploration, synthesis, variant, member"
    ),
) -> None:
    """Add documents to a group."""
    try:
        db.ensure_schema()

        # Verify group exists
        group = groups.get_group(group_id)
        if not group:
            console.print(f"[red]Error: Group #{group_id} not found[/red]")
            raise typer.Exit(1) from None

        added = []
        already_in = []
        not_found = []

        for doc_id in doc_ids:
            # Verify document exists
            doc = get_document(str(doc_id))
            if not doc:
                not_found.append(doc_id)
                continue

            success = groups.add_document_to_group(group_id, doc_id, role=role)
            if success:
                added.append(doc_id)
            else:
                already_in.append(doc_id)

        # Report results
        if added:
            console.print(
                f"[green]✅ Added {len(added)} document(s) to group "
                f"#{group_id} ({group['name']}):[/green]"
            )
            for doc_id in added:
                doc = get_document(str(doc_id))
                console.print(f"   [dim]#{doc_id}: {doc['title'][:40]} ({role})[/dim]")

        if already_in:
            console.print(f"[yellow]Already in group: {already_in}[/yellow]")

        if not_found:
            console.print(f"[red]Documents not found: {not_found}[/red]")

    except Exception as e:
        console.print(f"[red]Error adding documents: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def remove(
    group_id: int = typer.Argument(..., help="Group ID to remove documents from"),
    doc_ids: list[int] = typer.Argument(..., help="Document IDs to remove"),
) -> None:
    """Remove documents from a group."""
    try:
        db.ensure_schema()

        # Verify group exists
        group = groups.get_group(group_id)
        if not group:
            console.print(f"[red]Error: Group #{group_id} not found[/red]")
            raise typer.Exit(1) from None

        removed = []
        not_in = []

        for doc_id in doc_ids:
            success = groups.remove_document_from_group(group_id, doc_id)
            if success:
                removed.append(doc_id)
            else:
                not_in.append(doc_id)

        # Report results
        if removed:
            console.print(
                f"[green]✅ Removed {len(removed)} document(s) from group "
                f"#{group_id} ({group['name']})[/green]"
            )

        if not_in:
            console.print(f"[yellow]Not in group: {not_in}[/yellow]")

    except Exception as e:
        console.print(f"[red]Error removing documents: {e}[/red]")
        raise typer.Exit(1) from None


@app.command(name="list")
def list_groups_cmd(
    parent: Optional[int] = typer.Option(
        None, "--parent", "-p", help="Filter by parent group ID (-1 for top-level)"
    ),
    project: Optional[str] = typer.Option(
        None, "--project", help="Filter by project"
    ),
    group_type: Optional[str] = typer.Option(
        None, "--type", "-t", help="Filter by type"
    ),
    tree: bool = typer.Option(
        False, "--tree", help="Show as tree structure"
    ),
    include_inactive: bool = typer.Option(
        False, "--all", "-a", help="Include inactive (deleted) groups"
    ),
) -> None:
    """List document groups."""
    try:
        db.ensure_schema()

        if tree:
            _display_groups_tree(project, include_inactive)
            return

        # Determine if filtering for top-level
        top_level_only = parent == -1
        actual_parent = None if top_level_only else parent

        all_groups = groups.list_groups(
            parent_group_id=actual_parent,
            project=project,
            group_type=group_type,
            include_inactive=include_inactive,
            top_level_only=top_level_only,
        )

        if not all_groups:
            console.print("[yellow]No groups found[/yellow]")
            return

        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("ID", style="cyan", width=5)
        table.add_column("Name", style="white")
        table.add_column("Type", style="dim", width=10)
        table.add_column("Parent", style="dim", width=8)
        table.add_column("Docs", style="green", width=5)
        table.add_column("Project", style="dim", width=12)

        for g in all_groups:
            parent_str = f"#{g['parent_group_id']}" if g['parent_group_id'] else "-"
            project_str = g['project'][:12] if g['project'] else "-"

            table.add_row(
                str(g['id']),
                g['name'][:35],
                g['group_type'],
                parent_str,
                str(g['doc_count']),
                project_str,
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error listing groups: {e}[/red]")
        raise typer.Exit(1) from None


def _display_groups_tree(project: Optional[str], include_inactive: bool) -> None:
    """Display groups as a tree structure."""
    # Get top-level groups
    top_groups = groups.list_groups(
        project=project,
        include_inactive=include_inactive,
        top_level_only=True,
    )

    if not top_groups:
        console.print("[yellow]No groups found[/yellow]")
        return

    tree = Tree("📁 [bold]Document Groups[/bold]")

    for g in top_groups:
        _add_group_to_tree(tree, g, include_inactive)

    console.print(tree)


def _add_group_to_tree(parent_tree: Tree, group: dict, include_inactive: bool) -> None:
    """Recursively add a group and its children to the tree."""
    type_icons = {
        'initiative': '📋',
        'round': '🔄',
        'batch': '📦',
        'session': '💾',
        'custom': '🏷️',
    }
    icon = type_icons.get(group['group_type'], '📁')

    label = f"{icon} [cyan]#{group['id']}[/cyan] {group['name']} [dim]({group['doc_count']} docs)[/dim]"
    branch = parent_tree.add(label)

    # Add child groups
    children = groups.get_child_groups(group['id'])
    for child in children:
        if include_inactive or child.get('is_active', True):
            _add_group_to_tree(branch, child, include_inactive)

    # Add member documents (limited to 5)
    members = groups.get_group_members(group['id'])
    if members:
        for m in members[:5]:
            role_icon = {'primary': '★', 'synthesis': '📝', 'exploration': '◇'}.get(m['role'], '•')
            branch.add(f"  {role_icon} [dim]#{m['id']}[/dim] {m['title'][:30]}")
        if len(members) > 5:
            branch.add(f"  [dim]... and {len(members) - 5} more[/dim]")


@app.command()
def show(
    group_id: int = typer.Argument(..., help="Group ID to show"),
) -> None:
    """Show detailed information about a group."""
    try:
        db.ensure_schema()

        group = groups.get_group(group_id)
        if not group:
            console.print(f"[red]Error: Group #{group_id} not found[/red]")
            raise typer.Exit(1) from None

        # Header
        type_icons = {
            'initiative': '📋',
            'round': '🔄',
            'batch': '📦',
            'session': '💾',
            'custom': '🏷️',
        }
        icon = type_icons.get(group['group_type'], '📁')

        console.print(f"\n{icon} [bold cyan]#{group['id']}:[/bold cyan] [bold]{group['name']}[/bold]")
        console.print("=" * 50)

        # Metadata
        console.print(f"[dim]Type:[/dim] {group['group_type']}")
        if group['description']:
            console.print(f"[dim]Description:[/dim] {group['description']}")
        if group['project']:
            console.print(f"[dim]Project:[/dim] {group['project']}")
        if group['parent_group_id']:
            parent = groups.get_group(group['parent_group_id'])
            parent_name = parent['name'] if parent else "Unknown"
            console.print(f"[dim]Parent:[/dim] #{group['parent_group_id']} ({parent_name})")
        console.print(f"[dim]Created:[/dim] {group['created_at']}")
        if group['created_by']:
            console.print(f"[dim]Created by:[/dim] {group['created_by']}")

        # Stats
        console.print("\n[bold]Statistics:[/bold]")
        console.print(f"  Documents: {group['doc_count']}")
        if group['total_tokens']:
            console.print(f"  Total tokens: {group['total_tokens']:,}")
        if group['total_cost_usd']:
            console.print(f"  Total cost: ${group['total_cost_usd']:.4f}")

        # Child groups
        children = groups.get_child_groups(group_id)
        if children:
            console.print(f"\n[bold]Child Groups ({len(children)}):[/bold]")
            for child in children:
                child_icon = type_icons.get(child['group_type'], '📁')
                console.print(f"  {child_icon} #{child['id']} {child['name']} ({child['doc_count']} docs)")

        # Members
        members = groups.get_group_members(group_id)
        if members:
            console.print(f"\n[bold]Documents ({len(members)}):[/bold]")
            for m in members[:20]:
                role_icon = {'primary': '★', 'synthesis': '📝', 'exploration': '◇', 'variant': '≈'}.get(m['role'], '•')
                title = m['title'][:40] if len(m['title']) > 40 else m['title']
                console.print(f"  {role_icon} [cyan]#{m['id']}[/cyan] {title} [dim]({m['role']})[/dim]")
            if len(members) > 20:
                console.print(f"  [dim]... and {len(members) - 20} more documents[/dim]")
        else:
            console.print("\n[dim]No documents in this group[/dim]")

    except Exception as e:
        console.print(f"[red]Error showing group: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def delete(
    group_id: int = typer.Argument(..., help="Group ID to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    hard: bool = typer.Option(False, "--hard", help="Permanently delete (not soft-delete)"),
) -> None:
    """Delete a document group."""
    try:
        db.ensure_schema()

        group = groups.get_group(group_id)
        if not group:
            console.print(f"[red]Error: Group #{group_id} not found[/red]")
            raise typer.Exit(1) from None

        # Check for children
        children = groups.get_child_groups(group_id)
        members = groups.get_group_members(group_id)

        if not force:
            console.print(f"\n[bold]Will delete group:[/bold] #{group_id} ({group['name']})")
            if children:
                console.print(f"[yellow]Warning: This group has {len(children)} child group(s) that will also be deleted[/yellow]")
            if members:
                console.print(f"[dim]Note: {len(members)} document(s) will be removed from group (documents not deleted)[/dim]")

            if not typer.confirm("Continue?"):
                raise typer.Abort()

        success = groups.delete_group(group_id, hard=hard)
        if success:
            action = "Permanently deleted" if hard else "Deleted"
            console.print(f"[green]✅ {action} group #{group_id} ({group['name']})[/green]")
        else:
            console.print("[red]Error: Failed to delete group[/red]")
            raise typer.Exit(1) from None

    except typer.Abort:
        console.print("[yellow]Cancelled[/yellow]")
    except Exception as e:
        console.print(f"[red]Error deleting group: {e}[/red]")
        raise typer.Exit(1) from None


@app.command()
def edit(
    group_id: int = typer.Argument(..., help="Group ID to edit"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="New name"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="New description"),
    parent: Optional[int] = typer.Option(None, "--parent", "-p", help="New parent group ID (0 to remove)"),
    group_type: Optional[str] = typer.Option(None, "--type", "-t", help="New group type"),
) -> None:
    """Edit group properties."""
    try:
        db.ensure_schema()

        group = groups.get_group(group_id)
        if not group:
            console.print(f"[red]Error: Group #{group_id} not found[/red]")
            raise typer.Exit(1) from None

        updates = {}
        if name is not None:
            updates['name'] = name
        if description is not None:
            updates['description'] = description
        if parent is not None:
            updates['parent_group_id'] = None if parent == 0 else parent
        if group_type is not None:
            updates['group_type'] = group_type

        if not updates:
            console.print("[yellow]No changes specified[/yellow]")
            return

        success = groups.update_group(group_id, **updates)
        if success:
            console.print(f"[green]✅ Updated group #{group_id}[/green]")
            for key, value in updates.items():
                console.print(f"   [dim]{key}: {value}[/dim]")
        else:
            console.print("[red]Error: Failed to update group[/red]")
            raise typer.Exit(1) from None

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        console.print(f"[red]Error editing group: {e}[/red]")
        raise typer.Exit(1) from None
