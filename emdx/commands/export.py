"""Export commands — export emdx data to external formats.

Currently supports Obsidian vault export.
"""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="Export knowledge base to external formats")


@app.command(name="obsidian")
def export_obsidian(
    output_dir: Path = typer.Argument(..., help="Directory to write Obsidian vault files into"),
    project: str | None = typer.Option(None, "--project", "-p", help="Filter to a single project"),
    tags: list[str] | None = typer.Option(None, "--tags", "-t", help="Filter by tags (AND)"),
    incremental: bool = typer.Option(
        False,
        "--incremental",
        "-i",
        help="Only re-export changed docs (uses SHA256 manifest)",
    ),
    no_tasks: bool = typer.Option(False, "--no-tasks", help="Skip exporting task files"),
    by_project: bool = typer.Option(
        False,
        "--by-project",
        help="Organize into subdirectories by project",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Preview without writing files"),
) -> None:
    """Export documents as Obsidian-compatible markdown files.

    Each document becomes a .md file with YAML frontmatter (title, tags,
    emdx_id, project, dates) and [[wikilinks]] to related documents so
    Obsidian's graph view lights up.

    Tasks are exported as checklist files grouped by epic under a tasks/
    subdirectory.

    Use --incremental to only re-export changed documents (tracked via
    a .emdx-export.json manifest).

    Examples:

        emdx export obsidian ~/obsidian-vault/emdx/

        emdx export obsidian ./vault --project myapp --incremental

        emdx export obsidian ./vault --tags security,active --dry-run
    """
    from ..services.obsidian_export_service import export_obsidian as do_export

    # Parse comma-separated tags if provided as a single string
    parsed_tags: list[str] | None = None
    if tags:
        parsed_tags = []
        for tag_arg in tags:
            parsed_tags.extend(t.strip() for t in tag_arg.split(",") if t.strip())

    if dry_run:
        print("Dry run — no files will be written.\n")

    result = do_export(
        output_dir=output_dir,
        project=project,
        tags=parsed_tags,
        incremental=incremental,
        include_tasks=not no_tasks,
        organize_by_project=by_project,
        dry_run=dry_run,
    )

    # Print results
    print(f"Export directory: {result.output_dir}/")
    print(f"  Documents exported: {result.docs_exported}")
    if result.docs_skipped:
        print(f"  Documents skipped (unchanged): {result.docs_skipped}")
    if not no_tasks:
        print(f"  Task files exported: {result.task_files_exported}")

    if result.errors:
        print(f"\n  Errors: {len(result.errors)}")
        for err in result.errors:
            print(f"    - {err}")

    if result.docs_exported == 0 and result.docs_skipped == 0:
        print("\nNo documents matched the filters.")
