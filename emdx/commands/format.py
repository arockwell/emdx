"""Document formatting commands for emdx."""

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from emdx.models.documents import get_document, update_document
from emdx.utils.format_helpers import (
    apply_auto_fixes,
    format_issue_table,
    format_summary,
    suggest_fixes,
)
from emdx.utils.formatter import DocumentFormatter

app = typer.Typer()
console = Console(force_terminal=True)


@app.command()
def validate(
    doc_id: int = typer.Argument(..., help="Document ID to validate"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed suggestions"),
) -> None:
    """Validate document formatting without making changes."""
    # Get document
    doc = get_document(doc_id)
    if not doc:
        console.print(f"[red]Document #{doc_id} not found[/red]")
        raise typer.Exit(1)

    # Validate formatting
    formatter = DocumentFormatter()
    result = formatter.validate(doc.content)

    # Display results
    console.print(f"\n[cyan]Validating document #{doc_id}:[/cyan] {doc.title}\n")
    console.print(format_summary(result))

    if result.issues:
        console.print()
        console.print(format_issue_table(result))

        if verbose:
            console.print("\n[yellow]Suggestions:[/yellow]")
            shown_rules = set()
            for issue in result.issues:
                if issue.rule not in shown_rules:
                    suggestion = suggest_fixes(doc.content, issue.rule)
                    if suggestion:
                        console.print(f"\n[blue]{issue.rule}:[/blue]")
                        console.print(f"  {suggestion}")
                        shown_rules.add(issue.rule)

    # Exit with error code if invalid
    if not result.valid:
        raise typer.Exit(1)


@app.command()
def format(
    doc_id: int = typer.Argument(..., help="Document ID to format"),
    check: bool = typer.Option(False, "--check", help="Check only, don't modify"),
    diff: bool = typer.Option(False, "--diff", help="Show differences"),
) -> None:
    """Format document to fix auto-fixable issues."""
    # Get document
    doc = get_document(doc_id)
    if not doc:
        console.print(f"[red]Document #{doc_id} not found[/red]")
        raise typer.Exit(1)

    # Apply formatting
    formatter = DocumentFormatter()
    result = formatter.validate(doc.content, auto_fix=True)

    if not result.fixed_content or result.fixed_content == doc.content:
        console.print(f"[green]✅ Document #{doc_id} is already properly formatted[/green]")
        return

    # Show what would be fixed
    _, applied_fixes = apply_auto_fixes(doc.content)
    console.print(f"\n[cyan]Formatting document #{doc_id}:[/cyan] {doc.title}\n")
    console.print("[yellow]Applied fixes:[/yellow]")
    for fix in applied_fixes:
        console.print(f"  • {fix}")

    # Show diff if requested
    if diff:
        import difflib
        diff_lines = difflib.unified_diff(
            doc.content.splitlines(keepends=True),
            result.fixed_content.splitlines(keepends=True),
            fromfile=f"Document #{doc_id} (original)",
            tofile=f"Document #{doc_id} (formatted)",
        )
        console.print("\n[yellow]Diff:[/yellow]")
        for line in diff_lines:
            if line.startswith('+'):
                console.print(f"[green]{line.rstrip()}[/green]")
            elif line.startswith('-'):
                console.print(f"[red]{line.rstrip()}[/red]")
            else:
                console.print(line.rstrip())

    # Apply changes if not in check mode
    if check:
        console.print("\n[yellow]No changes made (--check mode)[/yellow]")
        if result.fixed_content != doc.content:
            raise typer.Exit(1)
    else:
        try:
            update_document(doc_id, content=result.fixed_content)
            console.print(f"\n[green]✅ Document #{doc_id} formatted successfully[/green]")
        except Exception as e:
            console.print(f"[red]Error updating document: {e}[/red]")
            raise typer.Exit(1) from e


@app.command()
def format_all(
    project: Optional[str] = typer.Option(
        None, "--project", "-p", help="Format all docs in project"
    ),
    check: bool = typer.Option(False, "--check", help="Check only, don't modify"),
    limit: int = typer.Option(None, "--limit", help="Limit number of documents to process"),
) -> None:
    """Format multiple documents at once."""
    from emdx.models.documents import search_documents

    # Get documents to format
    if project:
        results = search_documents("", project=project, limit=limit or 1000)
    else:
        # Format all documents (with reasonable limit)
        results = search_documents("", limit=limit or 100)

    if not results:
        console.print("[yellow]No documents found[/yellow]")
        return

    formatter = DocumentFormatter()
    fixed_count = 0
    error_count = 0

    console.print(f"[cyan]Checking {len(results)} documents...[/cyan]\n")

    for doc in results:
        result = formatter.validate(doc.content, auto_fix=True)

        if result.fixed_content and result.fixed_content != doc.content:
            console.print(f"Document #{doc.id}: [yellow]{doc.title}[/yellow]")
            _, applied = apply_auto_fixes(doc.content)
            for fix in applied:
                console.print(f"  • {fix}")

            if not check:
                try:
                    update_document(doc.id, content=result.fixed_content)
                    fixed_count += 1
                except Exception as e:
                    console.print(f"  [red]Error: {e}[/red]")
                    error_count += 1
            else:
                fixed_count += 1

    # Summary
    console.print("\n[green]Summary:[/green]")
    console.print(f"  • Checked: {len(results)} documents")
    console.print(f"  • Needs formatting: {fixed_count} documents")
    if not check:
        console.print(f"  • Fixed: {fixed_count} documents")
        if error_count:
            console.print(f"  • Errors: {error_count} documents")
    else:
        console.print("  • [yellow]No changes made (--check mode)[/yellow]")


@app.command()
def check_file(
    file_path: Path = typer.Argument(..., help="Markdown file to check"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> None:
    """Check formatting of a markdown file without saving to database."""
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)

    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/red]")
        raise typer.Exit(1) from e

    # Validate formatting
    formatter = DocumentFormatter()
    result = formatter.validate(content)

    # Display results
    console.print(f"\n[cyan]Checking:[/cyan] {file_path}\n")
    console.print(format_summary(result))

    if result.issues:
        console.print()
        console.print(format_issue_table(result))

        if verbose and result.stats["fixable"] > 0:
            msg = f"\n[yellow]Run with --fix to auto-fix {result.stats['fixable']} issues[/yellow]"
            console.print(msg)

    # Exit with error code if invalid
    if not result.valid:
        raise typer.Exit(1)


@app.command()
def fix_file(
    file_path: Path = typer.Argument(..., help="Markdown file to fix"),
    backup: bool = typer.Option(True, "--backup/--no-backup", help="Create backup file"),
) -> None:
    """Fix formatting issues in a markdown file."""
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)

    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        console.print(f"[red]Error reading file: {e}[/red]")
        raise typer.Exit(1) from e

    # Apply formatting
    formatter = DocumentFormatter()
    result = formatter.validate(content, auto_fix=True)

    if not result.fixed_content or result.fixed_content == content:
        console.print("[green]✅ File is already properly formatted[/green]")
        return

    # Create backup if requested
    if backup:
        backup_path = file_path.with_suffix(file_path.suffix + '.bak')
        try:
            backup_path.write_text(content, encoding='utf-8')
            console.print(f"[dim]Created backup: {backup_path}[/dim]")
        except Exception as e:
            console.print(f"[red]Error creating backup: {e}[/red]")
            raise typer.Exit(1) from e

    # Write fixed content
    try:
        file_path.write_text(result.fixed_content, encoding='utf-8')
    except Exception as e:
        console.print(f"[red]Error writing file: {e}[/red]")
        raise typer.Exit(1) from e

    # Show what was fixed
    _, applied_fixes = apply_auto_fixes(content)
    console.print(f"\n[green]✅ Fixed {len(applied_fixes)} issues:[/green]")
    for fix in applied_fixes:
        console.print(f"  • {fix}")
