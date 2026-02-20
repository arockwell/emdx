"""Recipe management commands for EMDX.

Recipes are emdx documents tagged with 'recipe' that contain
instructions for Claude to follow. Recipes can be simple (single-step,
run via delegate) or structured (multi-step with frontmatter and
numbered step headers).

Simple recipe (no steps):
    emdx recipe run 42                    # Run via delegate
    emdx recipe run "Security" -- args    # With extra args

Structured recipe (with ## Step N: headers):
    emdx recipe run 42                    # Steps execute sequentially
    emdx recipe run 42 --input target=api # Pass declared inputs

    emdx recipe list                      # List all recipes
    emdx recipe create file.md            # Save a file as a recipe
    emdx recipe show 42                   # Show recipe structure
"""

import subprocess
from pathlib import Path
from typing import Any

import typer

from ..database.documents import get_document
from ..database.search import search_documents
from ..models.tags import search_by_tags
from ..services.recipe_parser import RecipeParseError, is_structured_recipe, parse_recipe
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
    recipes = search_by_tags(["recipe"], limit=50, prefix_match=False)
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
    """List all recipes (documents tagged 'recipe')."""
    results = search_by_tags(["recipe"], limit=50, prefix_match=False)

    if not results:
        console.print("[dim]No recipes found. Create one with:[/dim]")
        console.print("  [cyan]emdx recipe create recipe.md[/cyan]")
        console.print(
            '  [cyan]echo "instructions" | emdx save --title "My Recipe" --tags "recipe"[/cyan]'
        )
        return

    console.print("[bold]Recipes[/bold]\n")
    for result in results:
        doc: dict[str, Any] = dict(result)
        doc_id = doc["id"]
        title = doc.get("title", "Untitled")
        content = str(doc.get("content", ""))

        # Detect structured recipes
        structured = is_structured_recipe(content)
        badge = " [dim](steps)[/dim]" if structured else ""

        # Show first line of content as description
        first_line = content.split("\n")[0].strip().lstrip("# ") if content else ""
        if first_line == title:
            lines = [line.strip() for line in content.split("\n")[1:] if line.strip()]
            first_line = lines[0] if lines else ""
        if len(first_line) > 70:
            first_line = first_line[:67] + "..."

        console.print(f"  [cyan]#{doc_id}[/cyan]  [bold]{title}[/bold]{badge}")
        if first_line:
            console.print(f"        [dim]{first_line}[/dim]")


@app.command("run")
def run_recipe(
    id_or_name: str = typer.Argument(..., help="Recipe ID or title search"),
    extra: list[str] | None = typer.Argument(
        None,
        help="Extra arguments passed to the recipe",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress metadata on stderr",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Model to use",
    ),
    pr: bool = typer.Option(
        False,
        "--pr",
        help="Instruct agent to create a PR",
    ),
    worktree: bool = typer.Option(
        False,
        "--worktree",
        "-w",
        help="Run in isolated git worktree",
    ),
    input_vals: list[str] | None = typer.Option(
        None,
        "--input",
        "-i",
        help="Input values as key=value",
    ),
) -> None:
    """Run a recipe by ID or title.

    Simple recipes (no step headers) are run via emdx delegate.
    Structured recipes (with ## Step N: headers) execute steps sequentially,
    piping each step's output to the next.

    Examples:
        emdx recipe run 42
        emdx recipe run "Security Audit" --input target=api
        emdx recipe run 42 --pr --worktree
        emdx recipe run "Deep Analysis" -- "analyze auth module"
    """
    recipe_doc = _find_recipe(id_or_name)
    if not recipe_doc:
        console.print(f"[red]Recipe not found: {id_or_name}[/red]")
        raise typer.Exit(1)

    doc_id = recipe_doc["id"]
    title = recipe_doc.get("title", "Untitled")
    content = recipe_doc.get("content", "")

    # Parse input values
    inputs: dict[str, str] = {}
    if input_vals:
        for val in input_vals:
            if "=" not in val:
                console.print(f"[red]Invalid input format: {val} (expected key=value)[/red]")
                raise typer.Exit(1)
            key, value = val.split("=", 1)
            inputs[key.strip()] = value.strip()

    # Add extra args as the 'args' input
    extra_text = " ".join(extra) if extra else ""
    if extra_text:
        inputs["args"] = extra_text

    # Check if this is a structured recipe
    if is_structured_recipe(content):
        _run_structured(
            content=content,
            doc_id=doc_id,
            title=title,
            inputs=inputs,
            model=model,
            quiet=quiet,
            pr=pr,
            worktree=worktree,
        )
    else:
        _run_simple(
            doc_id=doc_id,
            title=title,
            extra_text=extra_text,
            model=model,
            quiet=quiet,
            pr=pr,
            worktree=worktree,
        )


def _run_structured(
    content: str,
    doc_id: int,
    title: str,
    inputs: dict[str, str],
    model: str | None,
    quiet: bool,
    pr: bool,
    worktree: bool,
) -> None:
    """Run a structured multi-step recipe."""
    from ..services.recipe_executor import execute_recipe

    try:
        recipe = parse_recipe(content)
    except RecipeParseError as e:
        console.print(f"[red]Failed to parse recipe: {e}[/red]")
        raise typer.Exit(1) from e

    # If --pr passed at CLI level but no step has [--pr], add it to last step
    if pr and not any(s.flags.get("pr") for s in recipe.steps):
        recipe.steps[-1].flags["pr"] = True

    if not quiet:
        step_names = [s.name for s in recipe.steps]
        console.print(f"[cyan]Running recipe:[/cyan] {title} (#{doc_id})")
        console.print(f"[dim]Steps: {' → '.join(step_names)}[/dim]")
        if inputs:
            console.print(f"[dim]Inputs: {inputs}[/dim]")

    result = execute_recipe(
        recipe=recipe,
        inputs=inputs,
        model=model,
        quiet=quiet,
        worktree=worktree,
        parent_doc_id=doc_id,
    )

    if result.success:
        if not quiet:
            console.print(f"\n[bold green]Recipe completed: {len(result.steps)} steps[/bold green]")
            if result.pr_url:
                console.print(f"[green]PR: {result.pr_url}[/green]")
    else:
        if not quiet:
            console.print(f"\n[bold red]Recipe failed at step {result.failed_at}[/bold red]")
            if result.error:
                console.print(f"[red]{result.error}[/red]")
        raise typer.Exit(1)


def _run_simple(
    doc_id: int,
    title: str,
    extra_text: str,
    model: str | None,
    quiet: bool,
    pr: bool,
    worktree: bool,
) -> None:
    """Run a simple (non-structured) recipe via delegate subprocess."""
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

    result = subprocess.run(cmd)
    raise typer.Exit(result.returncode)


@app.command("show")
def show_recipe(
    id_or_name: str = typer.Argument(..., help="Recipe ID or title search"),
) -> None:
    """Show recipe structure (inputs, steps, annotations).

    Examples:
        emdx recipe show 42
        emdx recipe show "Security Audit"
    """
    recipe_doc = _find_recipe(id_or_name)
    if not recipe_doc:
        console.print(f"[red]Recipe not found: {id_or_name}[/red]")
        raise typer.Exit(1)

    content = recipe_doc.get("content", "")
    doc_id = recipe_doc["id"]

    if not is_structured_recipe(content):
        console.print(f"[dim]Recipe #{doc_id} is a simple (unstructured) recipe.[/dim]")
        console.print("[dim]It will be executed as a single delegate call.[/dim]")
        return

    try:
        recipe = parse_recipe(content)
    except RecipeParseError as e:
        console.print(f"[red]Failed to parse recipe: {e}[/red]")
        raise typer.Exit(1) from e

    console.print(f"[bold]{recipe.title}[/bold] (#{doc_id})\n")

    if recipe.inputs:
        console.print("[bold]Inputs:[/bold]")
        for inp in recipe.inputs:
            req = " [red](required)[/red]" if inp.required else ""
            default = f" [dim](default: {inp.default})[/dim]" if inp.default else ""
            desc = f" - {inp.description}" if inp.description else ""
            console.print(f"  {{{{[cyan]{inp.name}[/cyan]}}}}{req}{default}{desc}")
        console.print()

    console.print("[bold]Steps:[/bold]")
    for step in recipe.steps:
        flags_str = ""
        if step.flags:
            flag_parts = []
            for k, v in step.flags.items():
                if v is True:
                    flag_parts.append(f"--{k}")
                else:
                    flag_parts.append(f"--{k} {v}")
            flags_str = f" [yellow][{', '.join(flag_parts)}][/yellow]"

        console.print(f"  {step.number}. [bold]{step.name}[/bold]{flags_str}")
        # Show first line of prompt
        first_line = step.prompt.split("\n")[0].strip()
        if len(first_line) > 70:
            first_line = first_line[:67] + "..."
        if first_line:
            console.print(f"     [dim]{first_line}[/dim]")


@app.command("create")
def create_recipe(
    file: str = typer.Argument(..., help="Markdown file to save as a recipe"),
    title: str | None = typer.Option(
        None,
        "--title",
        "-T",
        help="Custom title (default: filename)",
    ),
) -> None:
    """Create a recipe from a markdown file.

    Equivalent to: emdx save <file> --tags "recipe"
    """
    path = Path(file)
    if not path.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    cmd = ["emdx", "save", "--file", str(path), "--tags", "recipe"]
    if title:
        cmd.extend(["--title", title])

    result = subprocess.run(cmd)
    raise typer.Exit(result.returncode)


@app.command("install")
def install_recipe(
    name: str = typer.Argument(
        None,
        help="Built-in recipe name (or 'all' to install all)",
    ),
) -> None:
    """Install a built-in recipe into your knowledge base.

    Examples:
        emdx recipe install idea-to-pr
        emdx recipe install security-audit
        emdx recipe install all
    """
    from ..recipes import get_builtin_recipe, list_builtin_recipes

    if name == "all":
        recipes = list_builtin_recipes()
        if not recipes:
            console.print("[dim]No built-in recipes found.[/dim]")
            return
        for rpath in recipes:
            _install_builtin(rpath)
        return

    if not name:
        # List available built-in recipes
        recipes = list_builtin_recipes()
        if not recipes:
            console.print("[dim]No built-in recipes found.[/dim]")
            return
        console.print("[bold]Available built-in recipes:[/bold]\n")
        for rpath in recipes:
            console.print(f"  [cyan]{rpath.stem}[/cyan]")
        console.print("\nInstall with: [cyan]emdx recipe install <name>[/cyan]")
        return

    recipe_path = get_builtin_recipe(name)
    if not recipe_path:
        console.print(f"[red]Built-in recipe not found: {name}[/red]")
        available = list_builtin_recipes()
        if available:
            names = ", ".join(p.stem for p in available)
            console.print(f"[dim]Available: {names}[/dim]")
        raise typer.Exit(1)

    _install_builtin(recipe_path)


def _install_builtin(rpath: Path) -> None:
    """Install a built-in recipe file into the knowledge base."""
    cmd = ["emdx", "save", str(rpath), "--tags", "recipe", "--title", rpath.stem]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        console.print(f"  [green]Installed:[/green] {rpath.stem}")
    else:
        console.print(f"  [red]Failed:[/red] {rpath.stem}: {result.stderr.strip()}")
