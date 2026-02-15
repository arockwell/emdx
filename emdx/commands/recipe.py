"""Recipe management commands for EMDX.

Recipes are emdx documents tagged with 📋 (recipe) that contain
instructions for Claude to follow via `emdx delegate`.

    emdx recipe list              # List all recipes
    emdx recipe run <id> -- args  # Run a recipe via delegate
    emdx recipe create file.md    # Save a file as a recipe
"""

import subprocess
from pathlib import Path
from typing import Any

import typer

from ..database.documents import get_document
from ..database.search import search_documents
from ..models.tags import search_by_tags
from ..utils.output import console

app = typer.Typer(help="Manage and run EMDX recipes")

def _find_recipe(id_or_name: str) -> dict[str, Any] | None:
    """Find a recipe by ID or title search."""
    # Try as numeric ID first
    try:
        doc_id = int(id_or_name)
        doc = get_document(doc_id)
        if doc:
            return dict(doc)
    except ValueError:
        pass

    # Search by recipe tag, then filter by title match
    recipes = search_by_tags(["📋"], limit=50, prefix_match=False)
    for r in recipes:
        if id_or_name.lower() in r.get("title", "").lower():
            return dict(r)
    if recipes:
        # Fall back to text search within recipes
        results = search_documents(id_or_name, limit=20)
        recipe_ids = {r["id"] for r in recipes}
        for result in results:
            if result["id"] in recipe_ids:
                return dict(result)

    return None

@app.command("list")
def list_recipes() -> None:
    """List all recipes (documents tagged 📋)."""
    results = search_by_tags(["📋"], limit=50, prefix_match=False)

    if not results:
        console.print("[dim]No recipes found. Create one with:[/dim]")
        console.print('  [cyan]emdx recipe create recipe.md[/cyan]')
        console.print('  [cyan]echo "instructions" | emdx save --title "My Recipe" --tags "recipe"[/cyan]')  # noqa: E501
        return

    console.print("[bold]Recipes[/bold]\n")
    for result in results:
        doc: dict[str, Any] = dict(result)
        doc_id = doc["id"]
        title = doc.get("title", "Untitled")
        content = str(doc.get("content", ""))
        # Show first line of content as description
        first_line = content.split("\n")[0].strip().lstrip("# ") if content else ""
        if first_line == title:
            # Skip if first line is just the title
            lines = [line.strip() for line in content.split("\n")[1:] if line.strip()]
            first_line = lines[0] if lines else ""
        if len(first_line) > 70:
            first_line = first_line[:67] + "..."

        console.print(f"  [cyan]#{doc_id}[/cyan]  [bold]{title}[/bold]")
        if first_line:
            console.print(f"        [dim]{first_line}[/dim]")

@app.command("run")
def run_recipe(
    id_or_name: str = typer.Argument(..., help="Recipe ID or title search"),
    extra: list[str] | None = typer.Argument(
        None, help="Extra arguments passed to the recipe"
    ),
    quiet: bool = typer.Option(
        False, "--quiet", "-q", help="Suppress metadata on stderr"
    ),
    model: str | None = typer.Option(
        None, "--model", "-m", help="Model to use"
    ),
    pr: bool = typer.Option(
        False, "--pr", help="Instruct agent to create a PR"
    ),
    worktree: bool = typer.Option(
        False, "--worktree", "-w", help="Run in isolated git worktree"
    ),
) -> None:
    """Run a recipe by passing it to emdx delegate.

    The recipe document is loaded as context and the agent executes its
    instructions.

    Examples:
        emdx recipe run 42
        emdx recipe run "Deep Analysis" -- "analyze auth module"
        emdx recipe run 42 --pr --worktree
    """
    recipe = _find_recipe(id_or_name)
    if not recipe:
        console.print(f"[red]Recipe not found: {id_or_name}[/red]")
        raise typer.Exit(1)

    doc_id = recipe["id"]
    title = recipe.get("title", "Untitled")

    # Build the delegate command
    extra_text = " ".join(extra) if extra else ""
    if extra_text:
        prompt = f"Execute this recipe with: {extra_text}"
    else:
        prompt = "Execute this recipe."

    cmd = ["emdx", "delegate", "--doc", str(doc_id), prompt]
    if quiet:
        cmd.append("-q")
    if model:
        cmd.extend(["--model", model])
    if pr:
        cmd.append("--pr")
    if worktree:
        cmd.append("--worktree")

    if not quiet:
        console.print(f"[cyan]Running recipe:[/cyan] {title} (#{doc_id})")

    # Execute delegate as subprocess so stdout/stderr pass through
    result = subprocess.run(cmd)
    raise typer.Exit(result.returncode)

@app.command("create")
def create_recipe(
    file: str = typer.Argument(..., help="Markdown file to save as a recipe"),
    title: str | None = typer.Option(
        None, "--title", "-T", help="Custom title (default: filename)"
    ),
) -> None:
    """Create a recipe from a markdown file.

    Equivalent to: emdx save <file> --tags "recipe"
    """
    path = Path(file)
    if not path.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    cmd = ["emdx", "save", str(path), "--tags", "recipe"]
    if title:
        cmd.extend(["--title", title])

    result = subprocess.run(cmd)
    raise typer.Exit(result.returncode)
