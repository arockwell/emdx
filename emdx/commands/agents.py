"""Agent management commands for EMDX."""

import typer
import asyncio
import json
import os
from typing import Optional, List
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax

from ..agents.registry import agent_registry
from ..agents.executor import agent_executor
from ..database.connection import db_connection
from ..utils.emoji_aliases import EMOJI_ALIASES
from ..utils.logging import get_logger
from ..utils.text_formatting import truncate_title

app = typer.Typer(help="Manage and run EMDX agents")
console = Console()
logger = get_logger(__name__)


@app.command("list")
def list_agents(
    category: Optional[str] = typer.Option(None, "--category", "-c", 
        help="Filter by category: research, generation, analysis, maintenance"),
    format: str = typer.Option("table", "--format", "-f",
        help="Output format: table, json, simple"),
    all: bool = typer.Option(False, "--all", "-a",
        help="Include inactive agents")
):
    """List all available agents."""
    try:
        agents = agent_registry.list_agents(category=category, include_inactive=all)
        
        if format == "json":
            console.print(json.dumps(agents, indent=2, default=str))
        elif format == "simple":
            for agent in agents:
                status = "" if agent['is_active'] else " [INACTIVE]"
                console.print(f"{agent['name']}: {agent['description']}{status}")
        else:
            if not agents:
                console.print("[yellow]No agents found[/yellow]")
                return
                
            table = Table(title="EMDX Agents", show_header=True, header_style="bold magenta")
            table.add_column("ID", style="cyan", no_wrap=True, width=4)
            table.add_column("Name", style="green", no_wrap=True)
            table.add_column("Category", style="yellow")
            table.add_column("Description", style="white")
            table.add_column("Tools", style="blue")
            table.add_column("Usage", justify="right", style="cyan")
            table.add_column("Status", style="red")
            
            for agent in agents:
                # Format tools list
                tools = ", ".join(agent['allowed_tools'][:3])
                if len(agent['allowed_tools']) > 3:
                    tools += f" +{len(agent['allowed_tools']) - 3}"
                
                # Format status
                status = "✓" if agent['is_active'] else "✗"
                if agent['is_builtin']:
                    status += " 🏛️"
                
                table.add_row(
                    str(agent['id']),
                    agent['display_name'],
                    agent['category'],
                    truncate_title(agent['description']),
                    tools,
                    str(agent['usage_count']),
                    status
                )
            
            console.print(table)
            
            # Show legend
            console.print("\n[dim]Status: ✓=active ✗=inactive 🏛️=builtin[/dim]")
            
    except Exception as e:
        console.print(f"[red]Error listing agents: {e}[/red]")
        raise typer.Exit(1)


@app.command("run")
def run_agent(
    agent_name: str = typer.Argument(..., help="Agent name or ID"),
    doc_id: Optional[int] = typer.Option(None, "--doc", "-d",
        help="Input document ID"),
    query: Optional[str] = typer.Option(None, "--query", "-q",
        help="Input query string"),
    vars: Optional[List[str]] = typer.Option(None, "--var", "-v",
        help="Template variables as key=value pairs"),
    background: bool = typer.Option(True, "--background/--foreground", "-b",
        help="Run in background (default: True)"),
    yes: bool = typer.Option(False, "--yes", "-y",
        help="Skip confirmation prompts")
):
    """Run an agent on a document or with a query."""
    try:
        # Parse agent name/ID
        try:
            agent_id = int(agent_name)
            agent = agent_registry.get_agent(agent_id)
        except ValueError:
            # Try by name
            agent = agent_registry.get_agent_by_name(agent_name)
            if agent:
                agent_id = agent.config.id
        
        if not agent:
            console.print(f"[red]Agent '{agent_name}' not found[/red]")
            raise typer.Exit(1)
        
        # Validate input
        if not doc_id and not query:
            console.print("[red]Must provide either --doc or --query[/red]")
            raise typer.Exit(1)
        
        if doc_id and query:
            console.print("[red]Cannot provide both --doc and --query[/red]")
            raise typer.Exit(1)
        
        # Parse variables
        variables = {}
        if vars:
            for var in vars:
                if '=' not in var:
                    console.print(f"[red]Invalid variable format: {var} (expected key=value)[/red]")
                    raise typer.Exit(1)
                key, value = var.split('=', 1)
                variables[key] = value
        
        # Show agent info and confirm
        if not yes and agent.config.requires_confirmation:
            console.print(Panel(
                f"[bold yellow]Agent:[/bold yellow] {agent.config.display_name}\n"
                f"[bold yellow]Category:[/bold yellow] {agent.config.category}\n"
                f"[bold yellow]Description:[/bold yellow] {agent.config.description}\n"
                f"[bold yellow]Allowed Tools:[/bold yellow] {', '.join(agent.config.allowed_tools)}\n"
                f"[bold yellow]Max Iterations:[/bold yellow] {agent.config.max_iterations}\n"
                f"[bold yellow]Timeout:[/bold yellow] {agent.config.timeout_seconds}s",
                title="Agent Details",
                border_style="yellow"
            ))
            
            if doc_id:
                console.print(f"\n[yellow]Input:[/yellow] Document #{doc_id}")
            else:
                console.print(f"\n[yellow]Input:[/yellow] Query: {query}")
            
            if variables:
                console.print(f"[yellow]Variables:[/yellow] {variables}")
            
            if not Confirm.ask("\nProceed with execution?"):
                raise typer.Exit(0)
        
        # Execute agent
        console.print(f"\n[cyan]Executing agent '{agent.config.display_name}'...[/cyan]")
        
        execution_id = asyncio.run(agent_executor.execute_agent(
            agent_id=agent_id,
            input_type='document' if doc_id else 'query',
            input_doc_id=doc_id,
            input_query=query,
            variables=variables,
            background=background
        ))
        
        if background:
            console.print(f"[green]✓[/green] Agent started in background (execution #{execution_id})")
            console.print("Use [cyan]emdx log[/cyan] to monitor progress")
        else:
            console.print(f"[green]✓[/green] Agent completed (execution #{execution_id})")
            
            # Show output documents if any
            with db_connection.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT output_doc_ids FROM agent_executions
                    WHERE execution_id = ?
                """, (execution_id,))
                row = cursor.fetchone()
                
                if row and row['output_doc_ids']:
                    doc_ids = json.loads(row['output_doc_ids'])
                    if doc_ids:
                        console.print(f"\n[green]Output documents:[/green]")
                        for doc_id in doc_ids:
                            console.print(f"  • Document #{doc_id}")
    
    except Exception as e:
        console.print(f"[red]Error running agent: {e}[/red]")
        raise typer.Exit(1)


@app.command("create")
def create_agent(
    name: str = typer.Option(..., "--name", "-n", help="Unique agent name (no spaces)"),
    display_name: str = typer.Option(..., "--display-name", help="Display name"),
    description: str = typer.Option(..., "--description", "-d", help="Agent description"),
    category: str = typer.Option(..., "--category", "-c", 
        help="Category: research, generation, analysis, maintenance"),
    prompt_file: Optional[str] = typer.Option(None, "--prompt", "-p",
        help="Path to prompt template file"),
    system_prompt: Optional[str] = typer.Option(None, "--system-prompt",
        help="System prompt (if not using file)"),
    user_prompt: Optional[str] = typer.Option(None, "--user-prompt",
        help="User prompt template (if not using file)"),
    tools: List[str] = typer.Option(None, "--tool", "-t",
        help="Allowed tools (can be specified multiple times)"),
    max_context: int = typer.Option(5, "--max-context",
        help="Maximum context documents"),
    timeout: int = typer.Option(3600, "--timeout",
        help="Timeout in seconds"),
    output_tags: List[str] = typer.Option(None, "--tag",
        help="Tags to apply to outputs"),
    requires_confirmation: bool = typer.Option(False, "--confirm",
        help="Require confirmation before running")
):
    """Create a new agent."""
    try:
        # Validate category
        valid_categories = ['research', 'generation', 'analysis', 'maintenance']
        if category not in valid_categories:
            console.print(f"[red]Invalid category. Must be one of: {', '.join(valid_categories)}[/red]")
            raise typer.Exit(1)
        
        # Validate name (no spaces)
        if ' ' in name:
            console.print("[red]Agent name cannot contain spaces[/red]")
            raise typer.Exit(1)
        
        # Get prompts
        if prompt_file:
            # Read from file
            try:
                with open(prompt_file, 'r') as f:
                    content = f.read()
                
                # Parse for system/user sections
                if "---" in content:
                    parts = content.split("---", 1)
                    system_prompt = parts[0].strip()
                    user_prompt = parts[1].strip()
                else:
                    system_prompt = "You are a helpful AI assistant."
                    user_prompt = content.strip()
            except Exception as e:
                console.print(f"[red]Error reading prompt file: {e}[/red]")
                raise typer.Exit(1)
        elif system_prompt and user_prompt:
            # Use provided prompts
            pass
        else:
            console.print("[red]Must provide either --prompt file or both --system-prompt and --user-prompt[/red]")
            raise typer.Exit(1)
        
        # Default tools if none specified
        if not tools:
            tools = ["Read", "Grep", "Glob"]
        
        # Convert text tags to emojis
        emoji_tags = []
        if output_tags:
            for tag in output_tags:
                if tag in EMOJI_ALIASES:
                    emoji_tags.append(EMOJI_ALIASES[tag])
                else:
                    # Keep as-is if not a known text tag
                    emoji_tags.append(tag)
        
        # Create agent config
        config = {
            'name': name,
            'display_name': display_name,
            'description': description,
            'category': category,
            'system_prompt': system_prompt,
            'user_prompt_template': user_prompt,
            'allowed_tools': tools,
            'max_context_docs': max_context,
            'timeout_seconds': timeout,
            'output_tags': emoji_tags,
            'requires_confirmation': requires_confirmation,
            'created_by': os.environ.get('USER', 'unknown')
        }
        
        # Show preview
        console.print("\n[bold]Agent Configuration:[/bold]")
        console.print(Panel(
            f"[yellow]Name:[/yellow] {name}\n"
            f"[yellow]Display Name:[/yellow] {display_name}\n"
            f"[yellow]Category:[/yellow] {category}\n"
            f"[yellow]Description:[/yellow] {description}\n"
            f"[yellow]Allowed Tools:[/yellow] {', '.join(tools)}\n"
            f"[yellow]Output Tags:[/yellow] {', '.join(emoji_tags) if emoji_tags else 'None'}",
            title="Basic Info"
        ))
        
        console.print("\n[bold]System Prompt:[/bold]")
        console.print(Syntax(system_prompt, "markdown", theme="monokai", line_numbers=False))
        
        console.print("\n[bold]User Prompt Template:[/bold]")
        console.print(Syntax(user_prompt, "markdown", theme="monokai", line_numbers=False))
        
        if not Confirm.ask("\nCreate this agent?"):
            raise typer.Exit(0)
        
        # Create agent
        agent_id = agent_registry.create_agent(config)
        
        console.print(f"\n[green]✓[/green] Created agent '{name}' (ID: {agent_id})")
        console.print(f"\nRun with: [cyan]emdx agent run {name} --doc <ID>[/cyan]")
        
    except Exception as e:
        console.print(f"[red]Error creating agent: {e}[/red]")
        raise typer.Exit(1)


@app.command("info")
def agent_info(
    agent_name: str = typer.Argument(..., help="Agent name or ID")
):
    """Show detailed information about an agent."""
    try:
        # Parse agent name/ID
        try:
            agent_id = int(agent_name)
            agent = agent_registry.get_agent(agent_id)
        except ValueError:
            agent = agent_registry.get_agent_by_name(agent_name)
        
        if not agent:
            console.print(f"[red]Agent '{agent_name}' not found[/red]")
            raise typer.Exit(1)
        
        config = agent.config
        
        # Basic info
        console.print(Panel(
            f"[bold yellow]ID:[/bold yellow] {config.id}\n"
            f"[bold yellow]Name:[/bold yellow] {config.name}\n"
            f"[bold yellow]Display Name:[/bold yellow] {config.display_name}\n"
            f"[bold yellow]Category:[/bold yellow] {config.category}\n"
            f"[bold yellow]Description:[/bold yellow] {config.description}\n"
            f"[bold yellow]Version:[/bold yellow] {config.version}\n"
            f"[bold yellow]Status:[/bold yellow] {'Active' if config.is_active else 'Inactive'}\n"
            f"[bold yellow]Type:[/bold yellow] {'Built-in' if config.is_builtin else 'User-created'}\n"
            f"[bold yellow]Created By:[/bold yellow] {config.created_by or 'Unknown'}\n"
            f"[bold yellow]Created At:[/bold yellow] {config.created_at}",
            title=f"Agent: {config.display_name}",
            border_style="yellow"
        ))
        
        # Configuration
        console.print("\n[bold]Configuration:[/bold]")
        console.print(f"  [yellow]Allowed Tools:[/yellow] {', '.join(config.allowed_tools)}")
        console.print(f"  [yellow]Max Iterations:[/yellow] {config.max_iterations}")
        console.print(f"  [yellow]Timeout:[/yellow] {config.timeout_seconds}s")
        console.print(f"  [yellow]Requires Confirmation:[/yellow] {'Yes' if config.requires_confirmation else 'No'}")
        console.print(f"  [yellow]Max Context Docs:[/yellow] {config.max_context_docs}")
        console.print(f"  [yellow]Output Format:[/yellow] {config.output_format}")
        console.print(f"  [yellow]Save Outputs:[/yellow] {'Yes' if config.save_outputs else 'No'}")
        if config.output_tags:
            console.print(f"  [yellow]Output Tags:[/yellow] {', '.join(config.output_tags)}")
        
        # Usage statistics
        console.print("\n[bold]Usage Statistics:[/bold]")
        console.print(f"  [yellow]Total Runs:[/yellow] {config.usage_count}")
        console.print(f"  [yellow]Successful:[/yellow] {config.success_count}")
        console.print(f"  [yellow]Failed:[/yellow] {config.failure_count}")
        if config.usage_count > 0:
            success_rate = (config.success_count / config.usage_count) * 100
            console.print(f"  [yellow]Success Rate:[/yellow] {success_rate:.1f}%")
        if config.last_used_at:
            console.print(f"  [yellow]Last Used:[/yellow] {config.last_used_at}")
        
        # Prompts
        console.print("\n[bold]System Prompt:[/bold]")
        console.print(Syntax(config.system_prompt, "markdown", theme="monokai", line_numbers=True))
        
        console.print("\n[bold]User Prompt Template:[/bold]")
        console.print(Syntax(config.user_prompt_template, "markdown", theme="monokai", line_numbers=True))
        
        # Tool restrictions if any
        if config.tool_restrictions:
            console.print("\n[bold]Tool Restrictions:[/bold]")
            console.print(json.dumps(config.tool_restrictions, indent=2))
        
    except Exception as e:
        console.print(f"[red]Error showing agent info: {e}[/red]")
        raise typer.Exit(1)


@app.command("edit")
def edit_agent(
    agent_name: str = typer.Argument(..., help="Agent name or ID"),
    display_name: Optional[str] = typer.Option(None, "--display-name",
        help="Update display name"),
    description: Optional[str] = typer.Option(None, "--description", "-d",
        help="Update description"),
    prompt_file: Optional[str] = typer.Option(None, "--prompt", "-p",
        help="Update prompts from file"),
    tools: Optional[List[str]] = typer.Option(None, "--tool", "-t",
        help="Update allowed tools"),
    max_context: Optional[int] = typer.Option(None, "--max-context",
        help="Update max context documents"),
    timeout: Optional[int] = typer.Option(None, "--timeout",
        help="Update timeout in seconds"),
    output_tags: Optional[List[str]] = typer.Option(None, "--tag",
        help="Update output tags"),
    requires_confirmation: Optional[bool] = typer.Option(None, "--confirm/--no-confirm",
        help="Update confirmation requirement")
):
    """Edit an existing agent."""
    try:
        # Parse agent name/ID
        try:
            agent_id = int(agent_name)
            agent = agent_registry.get_agent(agent_id)
        except ValueError:
            agent = agent_registry.get_agent_by_name(agent_name)
            if agent:
                agent_id = agent.config.id
        
        if not agent:
            console.print(f"[red]Agent '{agent_name}' not found[/red]")
            raise typer.Exit(1)
        
        if agent.config.is_builtin:
            console.print("[red]Cannot edit built-in agents[/red]")
            raise typer.Exit(1)
        
        # Build updates
        updates = {}
        
        if display_name:
            updates['display_name'] = display_name
        
        if description:
            updates['description'] = description
        
        if prompt_file:
            try:
                with open(prompt_file, 'r') as f:
                    content = f.read()
                
                if "---" in content:
                    parts = content.split("---", 1)
                    updates['system_prompt'] = parts[0].strip()
                    updates['user_prompt_template'] = parts[1].strip()
                else:
                    updates['user_prompt_template'] = content.strip()
            except Exception as e:
                console.print(f"[red]Error reading prompt file: {e}[/red]")
                raise typer.Exit(1)
        
        if tools is not None:
            updates['allowed_tools'] = tools
        
        if max_context is not None:
            updates['max_context_docs'] = max_context
        
        if timeout is not None:
            updates['timeout_seconds'] = timeout
        
        if output_tags is not None:
            # Convert text tags to emojis
            emoji_tags = []
            for tag in output_tags:
                if tag in EMOJI_ALIASES:
                    emoji_tags.append(EMOJI_ALIASES[tag])
                else:
                    emoji_tags.append(tag)
            updates['output_tags'] = emoji_tags
        
        if requires_confirmation is not None:
            updates['requires_confirmation'] = requires_confirmation
        
        if not updates:
            console.print("[yellow]No updates specified[/yellow]")
            raise typer.Exit(0)
        
        # Show updates
        console.print(f"\n[bold]Updating agent '{agent.config.display_name}':[/bold]")
        for key, value in updates.items():
            console.print(f"  [yellow]{key}:[/yellow] {value}")
        
        if not Confirm.ask("\nApply these updates?"):
            raise typer.Exit(0)
        
        # Apply updates
        if agent_registry.update_agent(agent_id, updates):
            console.print(f"\n[green]✓[/green] Updated agent '{agent.config.name}'")
        else:
            console.print(f"\n[red]Failed to update agent[/red]")
            raise typer.Exit(1)
        
    except Exception as e:
        console.print(f"[red]Error editing agent: {e}[/red]")
        raise typer.Exit(1)


@app.command("delete")
def delete_agent(
    agent_name: str = typer.Argument(..., help="Agent name or ID"),
    force: bool = typer.Option(False, "--force", "-f",
        help="Skip confirmation"),
    hard: bool = typer.Option(False, "--hard",
        help="Permanently delete (default is soft delete)")
):
    """Delete an agent."""
    try:
        # Parse agent name/ID
        try:
            agent_id = int(agent_name)
            agent = agent_registry.get_agent(agent_id)
        except ValueError:
            agent = agent_registry.get_agent_by_name(agent_name)
            if agent:
                agent_id = agent.config.id
        
        if not agent:
            console.print(f"[red]Agent '{agent_name}' not found[/red]")
            raise typer.Exit(1)
        
        if agent.config.is_builtin:
            console.print("[red]Cannot delete built-in agents[/red]")
            raise typer.Exit(1)
        
        # Confirm deletion
        if not force:
            delete_type = "permanently delete" if hard else "deactivate"
            console.print(f"\n[yellow]About to {delete_type} agent:[/yellow]")
            console.print(f"  Name: {agent.config.display_name}")
            console.print(f"  Usage: {agent.config.usage_count} runs")
            
            if not Confirm.ask(f"\n{delete_type.capitalize()} this agent?"):
                raise typer.Exit(0)
        
        # Delete agent
        if agent_registry.delete_agent(agent_id, hard_delete=hard):
            action = "deleted" if hard else "deactivated"
            console.print(f"\n[green]✓[/green] Agent '{agent.config.name}' {action}")
        else:
            console.print(f"\n[red]Failed to delete agent[/red]")
            raise typer.Exit(1)
        
    except Exception as e:
        console.print(f"[red]Error deleting agent: {e}[/red]")
        raise typer.Exit(1)


@app.command("stats")
def agent_stats(
    agent_name: Optional[str] = typer.Argument(None, help="Agent name or ID (all if not specified)"),
    days: int = typer.Option(7, "--days", "-d", help="Number of days to show")
):
    """Show agent usage statistics."""
    try:
        if agent_name:
            # Show stats for specific agent
            try:
                agent_id = int(agent_name)
                agent = agent_registry.get_agent(agent_id)
            except ValueError:
                agent = agent_registry.get_agent_by_name(agent_name)
                if agent:
                    agent_id = agent.config.id
            
            if not agent:
                console.print(f"[red]Agent '{agent_name}' not found[/red]")
                raise typer.Exit(1)
            
            # Get execution history
            with db_connection.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        DATE(started_at) as date,
                        COUNT(*) as runs,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful,
                        AVG(execution_time_ms) as avg_time_ms
                    FROM agent_executions
                    WHERE agent_id = ?
                        AND started_at >= datetime('now', '-' || ? || ' days')
                    GROUP BY DATE(started_at)
                    ORDER BY date DESC
                """, (agent_id, days))
                
                rows = cursor.fetchall()
                
                console.print(Panel(
                    f"[bold]{agent.config.display_name}[/bold]\n"
                    f"Total Runs: {agent.config.usage_count}\n"
                    f"Success Rate: {(agent.config.success_count / agent.config.usage_count * 100) if agent.config.usage_count > 0 else 0:.1f}%",
                    title=f"Agent Statistics (Last {days} Days)",
                    border_style="cyan"
                ))
                
                if rows:
                    table = Table(show_header=True, header_style="bold magenta")
                    table.add_column("Date", style="cyan")
                    table.add_column("Runs", justify="right")
                    table.add_column("Successful", justify="right", style="green")
                    table.add_column("Failed", justify="right", style="red")
                    table.add_column("Avg Time", justify="right")
                    
                    for row in rows:
                        failed = row['runs'] - row['successful']
                        avg_time = f"{row['avg_time_ms'] / 1000:.1f}s" if row['avg_time_ms'] else "N/A"
                        table.add_row(
                            row['date'],
                            str(row['runs']),
                            str(row['successful']),
                            str(failed),
                            avg_time
                        )
                    
                    console.print("\n", table)
                else:
                    console.print("\n[yellow]No executions in the specified period[/yellow]")
        else:
            # Show overall statistics
            with db_connection.get_connection() as conn:
                cursor = conn.cursor()
                
                # Get top agents by usage
                cursor.execute("""
                    SELECT 
                        id, display_name, category,
                        usage_count, success_count, failure_count,
                        ROUND(CAST(success_count AS FLOAT) / NULLIF(usage_count, 0) * 100, 1) as success_rate
                    FROM agents
                    WHERE is_active = TRUE
                    ORDER BY usage_count DESC
                    LIMIT 10
                """)
                
                top_agents = cursor.fetchall()
                
                # Get category statistics
                cursor.execute("""
                    SELECT 
                        category,
                        COUNT(*) as agent_count,
                        SUM(usage_count) as total_runs,
                        SUM(success_count) as total_success
                    FROM agents
                    WHERE is_active = TRUE
                    GROUP BY category
                """)
                
                category_stats = cursor.fetchall()
                
                console.print(Panel(
                    "[bold]Agent System Overview[/bold]",
                    title=f"Statistics (Last {days} Days)",
                    border_style="cyan"
                ))
                
                # Category breakdown
                if category_stats:
                    console.print("\n[bold]By Category:[/bold]")
                    cat_table = Table(show_header=True, header_style="bold magenta")
                    cat_table.add_column("Category", style="yellow")
                    cat_table.add_column("Agents", justify="right")
                    cat_table.add_column("Total Runs", justify="right")
                    cat_table.add_column("Success Rate", justify="right")
                    
                    for row in category_stats:
                        success_rate = (row['total_success'] / row['total_runs'] * 100) if row['total_runs'] > 0 else 0
                        cat_table.add_row(
                            row['category'].capitalize(),
                            str(row['agent_count']),
                            str(row['total_runs']),
                            f"{success_rate:.1f}%"
                        )
                    
                    console.print(cat_table)
                
                # Top agents
                if top_agents:
                    console.print("\n[bold]Most Used Agents:[/bold]")
                    top_table = Table(show_header=True, header_style="bold magenta")
                    top_table.add_column("Agent", style="green")
                    top_table.add_column("Category", style="yellow")
                    top_table.add_column("Runs", justify="right")
                    top_table.add_column("Success Rate", justify="right")
                    
                    for row in top_agents:
                        if row['usage_count'] > 0:
                            top_table.add_row(
                                row['display_name'],
                                row['category'],
                                str(row['usage_count']),
                                f"{row['success_rate'] or 0}%"
                            )
                    
                    console.print(top_table)
        
    except Exception as e:
        console.print(f"[red]Error showing statistics: {e}[/red]")
        raise typer.Exit(1)


# Add help command that shows examples
@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """EMDX Agent System - AI-powered task automation."""
    if ctx.invoked_subcommand is None:
        console.print("[bold]EMDX Agent System[/bold]")
        console.print("\nUse [cyan]emdx agent --help[/cyan] to see available commands")
        console.print("\n[bold]Quick Examples:[/bold]")
        console.print("  List agents:     [cyan]emdx agent list[/cyan]")
        console.print("  Run agent:       [cyan]emdx agent run doc-generator --doc 123[/cyan]")
        console.print("  Create agent:    [cyan]emdx agent create --name my-agent --prompt file.md[/cyan]")
        console.print("  View agent:      [cyan]emdx agent info doc-generator[/cyan]")


if __name__ == "__main__":
    app()