"""Keybinding management commands for emdx."""

from typing import Optional

import typer
from rich.table import Table

from emdx.utils.output import console

app = typer.Typer()


@app.callback(invoke_without_command=True)
def keybindings(
    ctx: typer.Context,
    list_all: bool = typer.Option(
        False, "--list", "-l", help="List all keybindings"
    ),
    conflicts: bool = typer.Option(
        False, "--conflicts", "-c", help="Show keybinding conflicts"
    ),
    context: Optional[str] = typer.Option(
        None, "--context", help="Filter by context (e.g., document:normal)"
    ),
    json_output: bool = typer.Option(
        False, "--json", "-j", help="Output as JSON"
    ),
):
    """
    Manage and inspect keybindings.

    By default, shows a summary of keybindings and any conflicts.
    """
    from emdx.ui.keybindings import KeybindingRegistry, ConflictSeverity, Context
    from emdx.ui.keybindings.extractor import extract_all_keybindings

    # Extract all keybindings
    entries = extract_all_keybindings()

    # Create and populate registry
    registry = KeybindingRegistry()
    registry.register_many(entries)

    # Detect conflicts
    detected_conflicts = registry.detect_conflicts()

    if json_output:
        import json

        print(json.dumps(registry.to_dict(), indent=2))
        return

    if conflicts:
        _show_conflicts(registry, detected_conflicts)
        return

    if list_all:
        _show_all_bindings(registry, context)
        return

    # Default: show summary
    _show_summary(registry, detected_conflicts)


def _show_summary(registry, conflicts):
    """Show keybinding summary."""
    console.print(f"\n[bold]Keybinding Registry Summary[/bold]\n")

    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="bold")

    table.add_row("Total bindings", str(len(registry.bindings)))
    table.add_row("Unique keys", str(len(registry.by_key)))
    table.add_row("Contexts", str(len(registry.by_context)))
    table.add_row("Conflicts", str(len(conflicts)))

    console.print(table)
    console.print()

    # Show conflict breakdown
    from emdx.ui.keybindings import ConflictSeverity

    critical = len(registry.get_conflicts_by_severity(ConflictSeverity.CRITICAL))
    warning = len(registry.get_conflicts_by_severity(ConflictSeverity.WARNING))
    info = len(registry.get_conflicts_by_severity(ConflictSeverity.INFO))

    if conflicts:
        console.print("[bold]Conflict breakdown:[/bold]")
        if critical > 0:
            console.print(f"  [red]Critical: {critical}[/red]")
        if warning > 0:
            console.print(f"  [yellow]Warning: {warning}[/yellow]")
        if info > 0:
            console.print(f"  [dim]Info: {info}[/dim]")

        console.print("\nRun [bold]emdx keybindings --conflicts[/bold] to see details.")
    else:
        console.print("[green]No conflicts detected![/green]")

    console.print()


def _show_conflicts(registry, conflicts):
    """Show keybinding conflicts."""
    from emdx.ui.keybindings import ConflictSeverity

    if not conflicts:
        console.print("[green]No keybinding conflicts detected![/green]")
        return

    console.print(f"\n[bold]Keybinding Conflicts ({len(conflicts)})[/bold]\n")

    # Group by severity
    for severity in [ConflictSeverity.CRITICAL, ConflictSeverity.WARNING, ConflictSeverity.INFO]:
        severity_conflicts = registry.get_conflicts_by_severity(severity)
        if not severity_conflicts:
            continue

        color = {
            ConflictSeverity.CRITICAL: "red",
            ConflictSeverity.WARNING: "yellow",
            ConflictSeverity.INFO: "dim",
        }[severity]

        console.print(f"[{color}][bold]{severity.value.upper()} ({len(severity_conflicts)})[/bold][/{color}]")

        table = Table(show_header=True, box=None)
        table.add_column("Key", style="bold")
        table.add_column("Widget 1")
        table.add_column("Action 1")
        table.add_column("Widget 2")
        table.add_column("Action 2")
        table.add_column("Type", style="dim")

        for conflict in severity_conflicts[:20]:  # Limit to 20 per severity
            table.add_row(
                conflict.key,
                conflict.binding1.widget_class,
                conflict.binding1.action,
                conflict.binding2.widget_class,
                conflict.binding2.action,
                conflict.conflict_type.value,
            )

        console.print(table)

        if len(severity_conflicts) > 20:
            console.print(f"  [dim]... and {len(severity_conflicts) - 20} more[/dim]")

        console.print()


def _show_all_bindings(registry, context_filter):
    """Show all keybindings, optionally filtered by context."""
    from emdx.ui.keybindings import Context

    console.print(f"\n[bold]All Keybindings ({len(registry.bindings)})[/bold]\n")

    # Filter by context if specified
    bindings = registry.bindings
    if context_filter:
        # Find matching context
        target_context = None
        for ctx in Context:
            if ctx.value == context_filter or ctx.value.endswith(context_filter):
                target_context = ctx
                break

        if target_context:
            bindings = [b for b in bindings if b.context == target_context]
            console.print(f"Filtered to context: [bold]{target_context.value}[/bold]\n")
        else:
            console.print(f"[yellow]Unknown context: {context_filter}[/yellow]")
            console.print("Available contexts:")
            for ctx in sorted(set(b.context.value for b in bindings)):
                console.print(f"  {ctx}")
            return

    # Group by context
    by_context = {}
    for binding in bindings:
        ctx = binding.context.value
        if ctx not in by_context:
            by_context[ctx] = []
        by_context[ctx].append(binding)

    # Display each context
    for ctx_name in sorted(by_context.keys()):
        ctx_bindings = by_context[ctx_name]

        console.print(f"[bold]{ctx_name}[/bold] ({len(ctx_bindings)} bindings)")

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("Key", style="bold", width=12)
        table.add_column("Action", width=25)
        table.add_column("Widget", style="dim", width=20)
        table.add_column("Description", style="dim")

        # Sort by key
        for binding in sorted(ctx_bindings, key=lambda b: b.key):
            priority = "[P]" if binding.priority else ""
            table.add_row(
                f"{binding.key} {priority}",
                binding.action,
                binding.widget_class,
                binding.description[:30] if binding.description else "",
            )

        console.print(table)
        console.print()


@app.command()
def init():
    """Create example keybindings config file."""
    from emdx.ui.keybindings.config import save_example_config, get_config_path

    path = get_config_path()

    if path.exists():
        console.print(f"[yellow]Config file already exists at {path}[/yellow]")
        return

    if save_example_config():
        console.print(f"[green]Created keybindings config at {path}[/green]")
    else:
        console.print(f"[red]Failed to create config file[/red]")


@app.command()
def contexts():
    """List all available contexts."""
    from emdx.ui.keybindings import Context

    console.print("\n[bold]Available Keybinding Contexts[/bold]\n")

    # Group by prefix
    groups = {}
    for ctx in Context:
        prefix = ctx.value.split(":")[0] if ":" in ctx.value else "other"
        if prefix not in groups:
            groups[prefix] = []
        groups[prefix].append(ctx)

    for prefix in sorted(groups.keys()):
        console.print(f"[bold]{prefix}[/bold]")
        for ctx in groups[prefix]:
            console.print(f"  {ctx.value}")
        console.print()
