"""Reusable parallel commands for EMDX.

The `emdx each` command provides a simple way to create and run
reusable commands that discover items and process them in parallel.

Example:
    # Create a saved command
    emdx each create fix-conflicts \
        --from "gh pr list ... | jq ..." \
        --do "Merge main into {{item}}, resolve conflicts"

    # Run it anytime
    emdx each fix-conflicts
"""

import asyncio
import json
import re
import subprocess
from typing import List, Optional

import typer
from rich.panel import Panel
from rich.table import Table

from ..workflows.registry import workflow_registry
from ..workflows.executor import workflow_executor
from ..utils.output import console

app = typer.Typer(help="Create and run reusable parallel commands")


# =============================================================================
# Helper functions
# =============================================================================


def _should_auto_enable_worktree(from_cmd: str) -> bool:
    """Check if worktree should be auto-enabled based on discovery command."""
    git_patterns = ['git ', 'gh ', 'branch', 'pr ', 'checkout', 'merge']
    return any(p in from_cmd.lower() for p in git_patterns)


def _run_discovery(command: str) -> List[str]:
    """Run a discovery command and return items."""
    console.print(f"[dim]Discovering items: {command}[/dim]")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            console.print(f"[red]Discovery failed: {result.stderr}[/red]")
            raise typer.Exit(1)

        lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
        console.print(f"[cyan]Found {len(lines)} item(s)[/cyan]")
        return lines

    except subprocess.TimeoutExpired:
        console.print("[red]Discovery command timed out after 30s[/red]")
        raise typer.Exit(1)


def _get_each_workflows() -> List:
    """Get all workflows created via `emdx each`.

    Each commands are stored as workflows with names prefixed by 'each-'.
    """
    all_workflows = workflow_registry.list_workflows(category='custom', include_inactive=False)
    return [wf for wf in all_workflows if wf.name.startswith('each-')]


def _workflow_name_to_each_name(workflow_name: str) -> str:
    """Convert workflow name (each-foo) to each name (foo)."""
    if workflow_name.startswith('each-'):
        return workflow_name[5:]
    return workflow_name


def _each_name_to_workflow_name(each_name: str) -> str:
    """Convert each name (foo) to workflow name (each-foo)."""
    if each_name.startswith('each-'):
        return each_name
    return f'each-{each_name}'


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '-', text)
    text = text.strip('-')
    return text


# =============================================================================
# Commands
# =============================================================================


@app.command("create")
def create(
    name: str = typer.Argument(..., help="Name for this command"),
    from_cmd: str = typer.Option(
        ..., "--from",
        help="Shell command that outputs items (one per line)"
    ),
    do_prompt: str = typer.Option(
        ..., "--do",
        help="What to do with each {{item}}"
    ),
    parallel: int = typer.Option(
        3, "-j", "--jobs", "-P", "--parallel",
        help="Max concurrent executions"
    ),
    synthesize: Optional[str] = typer.Option(
        None, "-s", "--synthesize",
        help="Enable synthesis (optional custom prompt)"
    ),
    description: Optional[str] = typer.Option(
        None, "--description",
        help="Human description of what this command does"
    ),
):
    """Create a new reusable parallel command.

    Examples:
        emdx each create fix-conflicts \\
            --from "gh pr list ... | jq ..." \\
            --do "Merge main into {{item}}, resolve conflicts"

        emdx each create audit-python \\
            --from "fd -e py -d 2 src/" \\
            --do "Review {{item}} for security issues" \\
            --synthesize "Summarize findings across all {{count}} files"
    """
    workflow_name = _each_name_to_workflow_name(name)

    # Check if already exists
    existing = workflow_registry.get_workflow(workflow_name)
    if existing:
        console.print(f"[red]Command '{name}' already exists[/red]")
        console.print(f"Use [cyan]emdx each edit {name}[/cyan] to modify it")
        raise typer.Exit(1)

    # Build the stage configuration
    stage = {
        "name": "main",
        "mode": "dynamic",
        "discovery_command": from_cmd,
        "item_variable": "item",
        "max_concurrent": parallel,
        "continue_on_failure": True,
        "prompt": do_prompt,
    }

    # Add synthesis if specified
    if synthesize is not None:
        if synthesize == "":
            # Default synthesis prompt
            stage["synthesis_prompt"] = (
                "Synthesize findings from all {{output_count}} items:\n\n{{outputs}}"
            )
        else:
            stage["synthesis_prompt"] = synthesize

    # Build description
    if not description:
        description = f"Discovers items via: {from_cmd[:50]}..."

    # Create the workflow
    try:
        workflow = workflow_registry.create_workflow(
            name=workflow_name,
            display_name=name,
            stages=[stage],
            variables={},
            description=description,
            category='custom',
        )
        console.print(f"[green]Created command:[/green] [cyan]{name}[/cyan]")
        console.print(f"  [dim]Run with:[/dim] emdx each {name}")

        if _should_auto_enable_worktree(from_cmd):
            console.print(f"  [dim]Note: Worktree isolation will be auto-enabled[/dim]")

    except Exception as e:
        console.print(f"[red]Failed to create command: {e}[/red]")
        raise typer.Exit(1)


@app.command("list")
def list_commands():
    """List all saved parallel commands."""
    workflows = _get_each_workflows()

    if not workflows:
        console.print("[yellow]No saved commands yet[/yellow]")
        console.print("Create one with: [cyan]emdx each create <name> --from <cmd> --do <prompt>[/cyan]")
        return

    table = Table(title="Saved Commands", show_header=True, header_style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Discovery", style="dim")
    table.add_column("Parallel", justify="center")
    table.add_column("Usage", justify="right")

    for wf in workflows:
        # Get stage info from workflow object
        if wf.stages:
            stage = wf.stages[0]
            discovery = getattr(stage, 'discovery_command', '')[:40]
            parallel = getattr(stage, 'max_concurrent', 3)
        else:
            discovery = ''
            parallel = 3

        table.add_row(
            _workflow_name_to_each_name(wf.name),
            discovery + ('...' if len(discovery) == 40 else ''),
            str(parallel),
            str(wf.usage_count),
        )

    console.print(table)


@app.command("show")
def show(
    name: str = typer.Argument(..., help="Command name to show"),
):
    """Show details of a saved command."""
    workflow_name = _each_name_to_workflow_name(name)
    workflow = workflow_registry.get_workflow(workflow_name)

    if not workflow:
        console.print(f"[red]Command '{name}' not found[/red]")
        raise typer.Exit(1)

    # Get stage from workflow object
    stage = workflow.stages[0] if workflow.stages else None

    if stage:
        discovery = getattr(stage, 'discovery_command', 'N/A')
        prompt = getattr(stage, 'prompt', 'N/A')
        max_concurrent = getattr(stage, 'max_concurrent', 3)
        synthesis = getattr(stage, 'synthesis_prompt', None)
    else:
        discovery = prompt = 'N/A'
        max_concurrent = 3
        synthesis = None

    console.print(Panel(
        f"[bold]{name}[/bold]\n\n"
        f"[dim]Discovery:[/dim]\n  {discovery}\n\n"
        f"[dim]Prompt:[/dim]\n  {prompt}\n\n"
        f"[dim]Parallel:[/dim] {max_concurrent}\n"
        f"[dim]Synthesis:[/dim] {'Yes' if synthesis else 'No'}\n"
        f"[dim]Usage count:[/dim] {workflow.usage_count}",
        title=f"emdx each {name}",
        border_style="cyan"
    ))


@app.command("delete")
def delete(
    name: str = typer.Argument(..., help="Command name to delete"),
    yes: bool = typer.Option(False, "-y", "--yes", help="Skip confirmation"),
):
    """Delete a saved command."""
    workflow_name = _each_name_to_workflow_name(name)
    workflow = workflow_registry.get_workflow(workflow_name)

    if not workflow:
        console.print(f"[red]Command '{name}' not found[/red]")
        raise typer.Exit(1)

    if not yes:
        from rich.prompt import Confirm
        if not Confirm.ask(f"Delete command '{name}'?"):
            console.print("[dim]Cancelled[/dim]")
            return

    try:
        workflow_registry.delete_workflow(workflow_name)
        console.print(f"[green]Deleted command:[/green] {name}")
    except Exception as e:
        console.print(f"[red]Failed to delete: {e}[/red]")
        raise typer.Exit(1)


@app.command("edit")
def edit(
    name: str = typer.Argument(..., help="Command name to edit"),
):
    """Edit a saved command in your $EDITOR."""
    import os
    import tempfile

    workflow_name = _each_name_to_workflow_name(name)
    workflow = workflow_registry.get_workflow(workflow_name)

    if not workflow:
        console.print(f"[red]Command '{name}' not found[/red]")
        raise typer.Exit(1)

    # Get current stage configuration
    stage = workflow.stages[0] if workflow.stages else None
    if stage:
        discovery_cmd = getattr(stage, 'discovery_command', '')
        prompt = getattr(stage, 'prompt', '')
        max_concurrent = getattr(stage, 'max_concurrent', 3)
        synthesis_prompt = getattr(stage, 'synthesis_prompt', '') or ''
    else:
        discovery_cmd = prompt = synthesis_prompt = ''
        max_concurrent = 3

    # Create a simple editable format
    content = f"""# Edit command: {name}
# Lines starting with # are ignored
# Save and close to apply changes

# Discovery command (outputs items, one per line)
from: {discovery_cmd}

# What to do with each {{{{item}}}}
do: {prompt}

# Max parallel executions
parallel: {max_concurrent}

# Synthesis prompt (optional, leave empty to disable)
synthesize: {synthesis_prompt}
"""

    editor = os.environ.get('EDITOR', 'vim')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        temp_path = f.name

    try:
        subprocess.run([editor, temp_path])

        # Parse the edited file
        with open(temp_path, 'r') as f:
            edited = f.read()

        new_values = {}
        for line in edited.split('\n'):
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            if ':' in line:
                key, value = line.split(':', 1)
                new_values[key.strip()] = value.strip()

        # Update the workflow
        new_stage = {
            "name": "main",
            "mode": "dynamic",
            "discovery_command": new_values.get('from', discovery_cmd),
            "item_variable": "item",
            "max_concurrent": int(new_values.get('parallel', max_concurrent)),
            "continue_on_failure": True,
            "prompt": new_values.get('do', prompt),
        }

        synth = new_values.get('synthesize', '')
        if synth:
            new_stage["synthesis_prompt"] = synth

        workflow_registry.update_workflow(
            workflow_name,
            stages=[new_stage],
        )

        console.print(f"[green]Updated command:[/green] {name}")

    finally:
        os.unlink(temp_path)


@app.command("run")
def run_command(
    name: str = typer.Argument(..., help="Command name to run"),
    items: Optional[List[str]] = typer.Argument(
        None,
        help="Explicit items (skip discovery)"
    ),
    from_cmd: Optional[str] = typer.Option(
        None, "--from",
        help="Override discovery command"
    ),
    parallel: int = typer.Option(
        3, "-j", "--jobs", "-P", "--parallel",
        help="Max concurrent executions"
    ),
    synthesize: Optional[str] = typer.Option(
        None, "-s", "--synthesize",
        help="Enable synthesis (optional custom prompt)"
    ),
    pr: bool = typer.Option(
        False, "--pr",
        help="Create a PR for each item processed"
    ),
    pr_single: bool = typer.Option(
        False, "--pr-single",
        help="Create one combined PR for all items"
    ),
    pr_base: str = typer.Option(
        "main", "--pr-base",
        help="Base branch for PRs (default: main)"
    ),
):
    """Run a saved command.

    Examples:
        # Run a saved command
        emdx each run fix-conflicts

        # Run with explicit items (skip discovery)
        emdx each run fix-conflicts feature-a feature-b

        # Override discovery command
        emdx each run fix-conflicts --from "echo specific-branch"

        # Create a PR for each item processed
        emdx each run fix-conflicts --pr

        # Create one combined PR for all items
        emdx each run fix-conflicts --pr-single

        # Specify base branch for PRs
        emdx each run fix-conflicts --pr --pr-base develop
    """
    _run_saved_command(name, items, from_cmd, parallel, synthesize, pr, pr_single, pr_base)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    from_cmd: Optional[str] = typer.Option(
        None, "--from",
        help="Discovery command for one-off execution"
    ),
    do_prompt: Optional[str] = typer.Option(
        None, "--do",
        help="Prompt for one-off execution"
    ),
    parallel: int = typer.Option(
        3, "-j", "--jobs", "-P", "--parallel",
        help="Max concurrent executions"
    ),
    synthesize: Optional[str] = typer.Option(
        None, "-s", "--synthesize",
        help="Enable synthesis (optional custom prompt)"
    ),
):
    """Create and run reusable parallel commands.

    Examples:
        # Create a saved command
        emdx each create fix-conflicts --from "gh pr list ..." --do "Fix {{item}}"

        # Run a saved command
        emdx each run fix-conflicts

        # One-off (no saved command)
        emdx each --from "fd -e md docs/" --do "Check {{item}} for broken links"

        # List saved commands
        emdx each list
    """
    # If a subcommand was invoked, skip this
    if ctx.invoked_subcommand is not None:
        return

    # Handle one-off execution
    if from_cmd and do_prompt:
        item_list = _run_discovery(from_cmd)
        asyncio.run(_execute_each(
            from_cmd=from_cmd,
            do_prompt=do_prompt,
            item_list=item_list,
            parallel=parallel,
            synthesize=synthesize,
        ))
        return

    # If no one-off args, show help
    console.print("[yellow]Usage:[/yellow]")
    console.print("  emdx each run <name>                Run a saved command")
    console.print("  emdx each --from <cmd> --do <prompt>  One-off execution")
    console.print("  emdx each create <name> ...         Create a saved command")
    console.print("  emdx each list                      List saved commands")


def _run_saved_command(
    name: str,
    items: Optional[List[str]],
    from_cmd: Optional[str],
    parallel: int,
    synthesize: Optional[str],
    pr: bool = False,
    pr_single: bool = False,
    pr_base: str = "main",
):
    """Run a saved each command."""
    workflow_name = _each_name_to_workflow_name(name)
    workflow = workflow_registry.get_workflow(workflow_name)

    if not workflow:
        console.print(f"[red]Command '{name}' not found[/red]")
        console.print(f"Create it with: [cyan]emdx each create {name} --from <cmd> --do <prompt>[/cyan]")
        raise typer.Exit(1)

    # Get stage configuration from workflow object
    if not workflow.stages:
        console.print(f"[red]Command '{name}' has no stages configured[/red]")
        raise typer.Exit(1)

    stage = workflow.stages[0]

    # Get discovery command (allow override)
    discovery_cmd = from_cmd or getattr(stage, 'discovery_command', '')
    prompt = getattr(stage, 'prompt', '')
    max_concurrent = getattr(stage, 'max_concurrent', parallel)
    synth_prompt = getattr(stage, 'synthesis_prompt', None)

    # Handle synthesize override
    if synthesize is not None:
        synth_prompt = synthesize if synthesize else (
            "Synthesize findings from all {{output_count}} items:\n\n{{outputs}}"
        )

    # Get items - explicit args or discovery
    if items:
        item_list = list(items)
    else:
        item_list = _run_discovery(discovery_cmd)

    if not item_list:
        console.print("[yellow]No items to process[/yellow]")
        return

    # Execute
    asyncio.run(_execute_each(
        from_cmd=discovery_cmd,
        do_prompt=prompt,
        item_list=item_list,
        parallel=max_concurrent,
        synthesize=synth_prompt,
        workflow_id=workflow.id,
        pr=pr,
        pr_single=pr_single,
        pr_base=pr_base,
    ))


def _create_pr(
    branch: str,
    base: str,
    title: str,
    body: str,
    working_dir: Optional[str] = None,
) -> Optional[str]:
    """Create a PR using gh CLI.

    Args:
        branch: The head branch for the PR
        base: The base branch for the PR
        title: PR title
        body: PR body
        working_dir: Working directory for the command

    Returns:
        PR URL if successful, None otherwise
    """
    try:
        # First, push the branch
        push_result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            capture_output=True,
            text=True,
            cwd=working_dir,
        )
        if push_result.returncode != 0:
            console.print(f"[yellow]Warning: Failed to push branch: {push_result.stderr}[/yellow]")
            return None

        # Create the PR
        result = subprocess.run(
            [
                "gh", "pr", "create",
                "--head", branch,
                "--base", base,
                "--title", title,
                "--body", body,
            ],
            capture_output=True,
            text=True,
            cwd=working_dir,
        )

        if result.returncode == 0:
            pr_url = result.stdout.strip()
            return pr_url
        else:
            console.print(f"[yellow]Warning: Failed to create PR: {result.stderr}[/yellow]")
            return None

    except FileNotFoundError:
        console.print("[red]Error: gh CLI not found. Install it with: brew install gh[/red]")
        return None
    except Exception as e:
        console.print(f"[yellow]Warning: PR creation failed: {e}[/yellow]")
        return None


def _has_changes(working_dir: Optional[str] = None) -> bool:
    """Check if there are any uncommitted changes in the working directory."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=working_dir,
    )
    return bool(result.stdout.strip())


async def _execute_each(
    from_cmd: str,
    do_prompt: str,
    item_list: List[str],
    parallel: int,
    synthesize: Optional[str] = None,
    workflow_id: Optional[int] = None,
    pr: bool = False,
    pr_single: bool = False,
    pr_base: str = "main",
):
    """Execute the each operation using workflow executor."""
    from ..workflows import database as wf_db
    from .workflows import create_worktree_for_workflow, cleanup_worktree

    # Auto-enable worktree when PR flags are used
    use_worktree = _should_auto_enable_worktree(from_cmd) or pr or pr_single

    # Validate PR flag usage
    if pr and pr_single:
        console.print("[red]Error: Cannot use both --pr and --pr-single[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Processing {len(item_list)} item(s) ({parallel} parallel)[/cyan]")
    if pr:
        console.print(f"[dim]Will create a PR for each item[/dim]")
    elif pr_single:
        console.print(f"[dim]Will create a combined PR for all items[/dim]")

    working_dir = None
    worktree_path = None
    worktree_branch = None

    if use_worktree:
        try:
            worktree_path, worktree_branch = create_worktree_for_workflow(pr_base)
            working_dir = worktree_path
            console.print(f"[dim]Using worktree: {worktree_path}[/dim]")
            console.print(f"[dim]Branch: {worktree_branch}[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not create worktree: {e}[/yellow]")
            if pr or pr_single:
                console.print("[red]Error: Worktree required for PR creation[/red]")
                raise typer.Exit(1)
            console.print("[dim]Continuing without worktree isolation[/dim]")

    # Convert to task-based execution
    # Replace {{item}} in prompt with actual items
    tasks = [do_prompt.replace("{{item}}", item) for item in item_list]

    # Prepare input variables
    variables = {
        "tasks": tasks,
        "_max_concurrent_override": parallel,
    }

    pr_urls = []

    try:
        result = await workflow_executor.execute_workflow(
            workflow_name_or_id="task_parallel",
            input_variables=variables,
            working_dir=working_dir,
        )

        if result.status == "completed":
            console.print(f"[green]Completed successfully[/green]")
            console.print(f"  Run ID: #{result.id}")
            console.print(f"  Tokens: {result.total_tokens_used:,}")
            if result.output_doc_ids:
                console.print(f"  Outputs: {result.output_doc_ids}")

            # Update usage count if this was a saved command
            if workflow_id:
                wf_db.increment_workflow_usage(workflow_id, success=True)

            # Handle PR creation for --pr-single (combined PR)
            if pr_single and worktree_path and worktree_branch:
                if _has_changes(worktree_path):
                    console.print(f"[cyan]Creating combined PR...[/cyan]")

                    # Generate PR title and body
                    item_summary = ", ".join(item_list[:3])
                    if len(item_list) > 3:
                        item_summary += f" (+{len(item_list) - 3} more)"
                    pr_title = f"emdx each: Process {len(item_list)} items ({item_summary})"
                    pr_body = f"""## Summary

This PR was created by `emdx each` processing {len(item_list)} items.

### Items processed:
{chr(10).join(f"- {item}" for item in item_list)}

### Run details:
- Run ID: #{result.id}
- Tokens used: {result.total_tokens_used:,}
"""

                    pr_url = _create_pr(
                        branch=worktree_branch,
                        base=pr_base,
                        title=pr_title,
                        body=pr_body,
                        working_dir=worktree_path,
                    )

                    if pr_url:
                        pr_urls.append(pr_url)
                        console.print(f"[green]Created PR:[/green] {pr_url}")
                else:
                    console.print("[yellow]No changes to create PR for[/yellow]")

            # Handle PR creation for --pr (per-item PRs)
            # Note: For per-item PRs, we would need to process items sequentially
            # and create a PR after each. This is a simplified implementation.
            if pr and worktree_path and worktree_branch:
                if _has_changes(worktree_path):
                    console.print(f"[cyan]Creating PR for all processed items...[/cyan]")

                    # For now, create a single PR with all changes
                    # A more sophisticated implementation would use separate worktrees per item
                    item_summary = ", ".join(item_list[:3])
                    if len(item_list) > 3:
                        item_summary += f" (+{len(item_list) - 3} more)"
                    pr_title = f"emdx each: {item_summary}"
                    pr_body = f"""## Summary

This PR was created by `emdx each --pr` processing items.

### Items processed:
{chr(10).join(f"- {item}" for item in item_list)}

### Run details:
- Run ID: #{result.id}
- Tokens used: {result.total_tokens_used:,}

---
*Note: Each item was processed with its own task, but changes are combined in this PR.*
"""

                    pr_url = _create_pr(
                        branch=worktree_branch,
                        base=pr_base,
                        title=pr_title,
                        body=pr_body,
                        working_dir=worktree_path,
                    )

                    if pr_url:
                        pr_urls.append(pr_url)
                        console.print(f"[green]Created PR:[/green] {pr_url}")
                else:
                    console.print("[yellow]No changes to create PR for[/yellow]")

        else:
            console.print(f"[red]Failed[/red]")
            if result.error_message:
                console.print(f"  Error: {result.error_message}")
            raise typer.Exit(1)

    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    finally:
        # Clean up worktree if we created one (unless PRs were created)
        if worktree_path:
            if pr_urls:
                console.print(f"[dim]Keeping worktree for PR: {worktree_path}[/dim]")
            else:
                console.print(f"[dim]Cleaning up worktree: {worktree_path}[/dim]")
                cleanup_worktree(worktree_path)
