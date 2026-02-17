"""Category CLI commands — manage task categories for epic numbering."""

import typer
from rich.table import Table

from emdx.models import categories
from emdx.utils.output import console

app = typer.Typer(help="Manage task categories")


@app.command()
def create(
    key: str = typer.Argument(..., help="Category key (2-8 uppercase letters, e.g. SEC)"),
    name: str = typer.Argument(..., help="Category name (e.g. Security)"),
    description: str | None = typer.Option(
        None, "-D", "--description", help="Category description"
    ),
) -> None:
    """Create a new category.

    Examples:
        emdx task cat create SEC "Security"
        emdx task cat create SEC "Security" -D "All security-related work"
    """
    try:
        result_key = categories.create_category(key, name, description or "")
        console.print(f"[green]Created category {result_key}: {name}[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None
    except Exception as e:
        if "UNIQUE constraint" in str(e):
            console.print(f"[red]Category {key.upper()} already exists[/red]")
            raise typer.Exit(1) from None
        raise


@app.command("list")
def list_cmd() -> None:
    """List all categories with task counts.

    Examples:
        emdx task cat list
    """
    cats = categories.list_categories()

    if not cats:
        console.print("[yellow]No categories[/yellow]")
        return

    table = Table()
    table.add_column("Cat", width=6)
    table.add_column("Name", min_width=15)
    table.add_column("Open", justify="right", width=5)
    table.add_column("Done", justify="right", width=5)
    table.add_column("Epics", justify="right", width=6)
    table.add_column("Total", justify="right", width=6)

    for c in cats:
        table.add_row(
            c["key"],
            c["name"],
            str(c["open_count"]),
            str(c["done_count"]),
            str(c["epic_count"]),
            str(c["total_count"]),
        )

    console.print(table)


@app.command()
def adopt(
    key: str = typer.Argument(..., help="Category key to adopt tasks for"),
    name: str | None = typer.Option(None, "--name", "-n", help="Set category name"),
) -> None:
    """Backfill existing tasks with KEY-N: titles into the category system.

    Scans tasks matching the KEY-N: pattern and sets their epic_key/epic_seq.
    Also detects parent EPIC tasks and marks them.

    Examples:
        emdx task cat adopt SEC
        emdx task cat adopt DEBT --name "Tech Debt"
    """
    try:
        result = categories.adopt_category(key, name)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from None

    console.print(f"[green]Adopted {result['adopted']} task(s) into {key.upper()}[/green]")
    if result["skipped"]:
        console.print(f"[yellow]Skipped {result['skipped']} (seq conflict)[/yellow]")
    if result["epics_found"]:
        console.print(f"[green]Found {result['epics_found']} parent epic(s)[/green]")
