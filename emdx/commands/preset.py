"""Preset management commands for EMDX."""

from typing import Optional

import typer
from rich.table import Table

from ..presets import (
    create_preset,
    get_preset,
    list_presets,
    update_preset,
    delete_preset,
)
from ..utils.output import console

app = typer.Typer(help="Manage run presets")


@app.command("list")
def list_cmd(
    all: bool = typer.Option(False, "--all", "-a", help="Include inactive"),
):
    """List all presets."""
    presets = list_presets(include_inactive=all)

    if not presets:
        console.print("[dim]No presets found. Create one with:[/dim]")
        console.print('  emdx preset create my-preset --template "Do {{task}}"')
        return

    table = Table(title="Run Presets")
    table.add_column("Name", style="cyan")
    table.add_column("Discovery", style="green")
    table.add_column("Template", style="yellow")
    table.add_column("Synth", style="magenta")
    table.add_column("Uses", style="blue")

    for p in presets:
        table.add_row(
            p.name,
            "✓" if p.has_discovery else "-",
            "✓" if p.has_template else "-",
            "✓" if p.synthesize else "-",
            str(p.usage_count),
        )

    console.print(table)


@app.command("show")
def show_cmd(name: str):
    """Show preset details."""
    preset = get_preset(name)

    if not preset:
        console.print(f"[red]Preset '{name}' not found[/red]")
        raise typer.Exit(1)

    console.print(f"[bold cyan]{preset.display_name}[/bold cyan]")
    console.print(f"[dim]Name: {preset.name}[/dim]")

    if preset.description:
        console.print(f"\n{preset.description}")

    console.print("\n[bold]Configuration:[/bold]")

    if preset.discover_command:
        console.print(f"  Discovery: [green]{preset.discover_command}[/green]")
    else:
        console.print("  Discovery: [dim](none - provide tasks manually)[/dim]")

    if preset.task_template:
        console.print(f"  Template: [yellow]{preset.task_template}[/yellow]")
    else:
        console.print("  Template: [dim](none - tasks used directly)[/dim]")

    console.print(f"  Synthesize: {'Yes' if preset.synthesize else 'No'}")
    console.print(f"  Max jobs: {preset.max_jobs or 'auto'}")

    console.print("\n[bold]Usage:[/bold]")
    console.print(f"  Count: {preset.usage_count}")
    if preset.last_used_at:
        console.print(f"  Last used: {preset.last_used_at}")


@app.command("create")
def create_cmd(
    name: str,
    display_name: str = typer.Option(None, "--display-name", "-n"),
    description: str = typer.Option(None, "--description", "-D"),
    discover: str = typer.Option(None, "--discover", "-d"),
    template: str = typer.Option(None, "--template", "-t"),
    synthesize: bool = typer.Option(False, "--synthesize", "-s"),
    jobs: int = typer.Option(None, "--jobs", "-j"),
):
    """Create a new preset."""
    try:
        preset = create_preset(
            name=name,
            display_name=display_name,
            description=description,
            discover_command=discover,
            task_template=template,
            synthesize=synthesize,
            max_jobs=jobs,
        )
        console.print(f"[green]✓ Created preset: {preset.name}[/green]")
    except Exception as e:
        console.print(f"[red]Error creating preset: {e}[/red]")
        raise typer.Exit(1)


@app.command("edit")
def edit_cmd(
    name: str,
    display_name: str = typer.Option(None, "--display-name", "-n"),
    description: str = typer.Option(None, "--description", "-D"),
    discover: str = typer.Option(None, "--discover", "-d"),
    template: str = typer.Option(None, "--template", "-t"),
    synthesize: bool = typer.Option(None, "--synthesize", "-s"),
    jobs: int = typer.Option(None, "--jobs", "-j"),
):
    """Edit an existing preset."""
    preset = update_preset(
        name=name,
        display_name=display_name,
        description=description,
        discover_command=discover,
        task_template=template,
        synthesize=synthesize,
        max_jobs=jobs,
    )

    if preset:
        console.print(f"[green]✓ Updated preset: {preset.name}[/green]")
    else:
        console.print(f"[red]Preset '{name}' not found[/red]")
        raise typer.Exit(1)


@app.command("delete")
def delete_cmd(
    name: str,
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
):
    """Delete a preset."""
    preset = get_preset(name)

    if not preset:
        console.print(f"[red]Preset '{name}' not found[/red]")
        raise typer.Exit(1)

    if not yes:
        from rich.prompt import Confirm
        if not Confirm.ask(f"Delete preset '{name}'?"):
            raise typer.Abort()

    if delete_preset(name):
        console.print(f"[green]✓ Deleted preset: {name}[/green]")
    else:
        console.print("[red]Error deleting preset[/red]")
        raise typer.Exit(1)
