"""
EMDX Swarm Command - parallel agent execution with k3d isolation.

This is your battlestation command. Run multiple Claude agents in
parallel, each in isolated k3d pods with their own git worktrees.

Examples:
    # Run 3 tasks in parallel
    emdx swarm "Fix lint errors" "Add tests" "Document API"

    # With synthesis
    emdx swarm --synthesize "Analyze auth" "Analyze api" "Analyze db"

    # From EMDX search (each result becomes a task)
    emdx swarm --from "emdx find --tags bug,active"

    # Local mode (no k3d, just parallel subprocesses)
    emdx swarm --local "task1" "task2"

    # Cluster management
    emdx swarm cluster start
    emdx swarm cluster stop
    emdx swarm cluster status
"""

import subprocess
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from emdx.swarm import Swarm, SwarmConfig
from emdx.swarm.k8s import K3dCluster, ClusterConfig

app = typer.Typer(
    name="swarm",
    help="Parallel agent execution with k3d isolation - your battlestation command",
)
console = Console()


@app.command("run")
def swarm_run(
    tasks: list[str] = typer.Argument(None, help="Tasks/prompts for agents"),
    from_cmd: Optional[str] = typer.Option(
        None, "--from", "-f",
        help="Shell command that outputs tasks (one per line)"
    ),
    synthesize: bool = typer.Option(
        False, "--synthesize", "-s",
        help="Combine results into a synthesis document"
    ),
    max_concurrent: int = typer.Option(
        6, "--jobs", "-j",
        help="Maximum concurrent agents"
    ),
    local: bool = typer.Option(
        False, "--local", "-l",
        help="Run locally without k3d (parallel subprocesses)"
    ),
    tags: Optional[str] = typer.Option(
        None, "--tags", "-t",
        help="Tags for output documents (comma-separated)"
    ),
    timeout: int = typer.Option(
        600, "--timeout",
        help="Timeout per task in seconds"
    ),
    memory: str = typer.Option(
        "3Gi", "--memory", "-m",
        help="Memory per agent pod"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Show detailed output"
    ),
):
    """
    Run multiple tasks in parallel with isolated agents.

    Each task gets its own git worktree and (with k3d) its own pod.
    Results are saved to EMDX automatically.
    """
    # Collect tasks
    task_list = list(tasks) if tasks else []

    # Add tasks from --from command
    if from_cmd:
        result = subprocess.run(
            from_cmd, shell=True,
            capture_output=True, text=True
        )
        if result.returncode == 0:
            task_list.extend(
                line.strip()
                for line in result.stdout.strip().split("\n")
                if line.strip()
            )

    if not task_list:
        console.print("[red]No tasks provided. Use positional args or --from[/red]")
        raise typer.Exit(1)

    # Configure swarm
    config = SwarmConfig(
        max_concurrent=max_concurrent,
        synthesize=synthesize,
        timeout_per_task=timeout,
        memory_per_agent=memory,
        tags=tags.split(",") if tags else ["swarm-output"],
    )

    swarm = Swarm(config=config)
    use_k3d = not local

    # Show what we're about to do
    console.print(Panel(
        f"[bold]Swarm Attack[/bold]\n\n"
        f"Tasks: {len(task_list)}\n"
        f"Concurrent: {max_concurrent}\n"
        f"Mode: {'k3d pods' if use_k3d else 'local processes'}\n"
        f"Synthesize: {synthesize}",
        title="⚔️ Battlestation",
        border_style="blue"
    ))

    if verbose:
        for i, task in enumerate(task_list, 1):
            console.print(f"  {i}. {task[:60]}...")

    # Check cluster if using k3d
    if use_k3d:
        cluster = K3dCluster()
        if not cluster.is_running():
            console.print("[yellow]Starting k3d cluster...[/yellow]")
            if not cluster.start():
                console.print("[red]Failed to start cluster. Use --local for local mode.[/red]")
                raise typer.Exit(1)

    # Run with progress
    completed = []

    def on_progress(task):
        status_icon = "✅" if task.status == "completed" else "❌"
        doc_info = f" → #{task.emdx_doc_id}" if task.emdx_doc_id else ""
        console.print(f"{status_icon} {task.prompt[:50]}... ({task.duration:.1f}s){doc_info}")
        completed.append(task)

    console.print("\n[bold]Deploying agents...[/bold]\n")

    result = swarm.run(
        task_list,
        use_k3d=use_k3d,
        progress_callback=on_progress
    )

    # Summary
    console.print("\n" + "=" * 60)
    console.print(Panel(
        f"[bold green]Completed: {result.successful}[/bold green]\n"
        f"[bold red]Failed: {result.failed}[/bold red]\n"
        f"Total time: {result.total_duration:.1f}s",
        title="📊 Results",
        border_style="green" if result.failed == 0 else "yellow"
    ))

    if result.synthesis_doc_id:
        console.print(f"\n[bold]Synthesis saved as #[cyan]{result.synthesis_doc_id}[/cyan][/bold]")

    # Show saved docs
    saved_docs = [t.emdx_doc_id for t in result.tasks if t.emdx_doc_id]
    if saved_docs:
        console.print(f"\nSaved documents: {', '.join(f'#{d}' for d in saved_docs)}")


@app.command("status")
def swarm_status():
    """Show current swarm/cluster status."""
    swarm = Swarm()
    status = swarm.status()

    if not status["cluster_running"]:
        console.print("[yellow]Cluster is not running[/yellow]")
        console.print("Start with: emdx swarm cluster start")
        return

    console.print(Panel(
        f"[bold]Cluster:[/bold] Running\n"
        f"[bold]Running agents:[/bold] {status['running_agents']}\n"
        f"[bold]Pending:[/bold] {status['pending_agents']}\n"
        f"[bold]Completed:[/bold] {status['completed_agents']}\n"
        f"[bold]Failed:[/bold] {status['failed_agents']}",
        title="⚔️ Battlestation Status",
        border_style="blue"
    ))

    if status["pods"]:
        table = Table(title="Agent Pods")
        table.add_column("Name", style="cyan")
        table.add_column("Phase", style="green")
        table.add_column("Started")

        for pod in status["pods"]:
            phase_style = {
                "Running": "green",
                "Succeeded": "blue",
                "Failed": "red",
                "Pending": "yellow"
            }.get(pod.phase, "white")

            table.add_row(
                pod.name,
                f"[{phase_style}]{pod.phase}[/{phase_style}]",
                pod.start_time or "-"
            )

        console.print(table)


@app.command("logs")
def swarm_logs(
    pod_name: Optional[str] = typer.Argument(
        None, help="Pod name (or 'all' for all pods)"
    ),
    follow: bool = typer.Option(
        False, "--follow", "-f",
        help="Follow log output"
    ),
):
    """View logs from agent pods."""
    cluster = K3dCluster()

    if not cluster.is_running():
        console.print("[red]Cluster is not running[/red]")
        raise typer.Exit(1)

    if pod_name and pod_name != "all":
        logs = cluster.get_pod_logs(pod_name, follow=follow)
        console.print(logs)
    else:
        # Show logs from all pods
        pods = cluster.list_agent_pods()
        for pod in pods:
            console.print(f"\n[bold cyan]== {pod.name} ==[/bold cyan]")
            logs = cluster.get_pod_logs(pod.name)
            console.print(logs[:2000] + "..." if len(logs) > 2000 else logs)


@app.command("cleanup")
def swarm_cleanup():
    """Delete completed/failed agent pods."""
    cluster = K3dCluster()

    if not cluster.is_running():
        console.print("[yellow]Cluster is not running[/yellow]")
        return

    deleted = cluster.cleanup_completed_pods()
    console.print(f"[green]Cleaned up {deleted} pods[/green]")


# Cluster management subcommands
cluster_app = typer.Typer(help="Manage the k3d cluster")
app.add_typer(cluster_app, name="cluster")


@cluster_app.command("start")
def cluster_start():
    """Start (or create) the battlestation cluster."""
    cluster = K3dCluster()

    if cluster.is_running():
        console.print("[green]Cluster is already running[/green]")
        return

    console.print("[yellow]Starting cluster...[/yellow]")
    if cluster.start():
        console.print("[green]✅ Cluster started[/green]")
    else:
        console.print("[red]❌ Failed to start cluster[/red]")
        raise typer.Exit(1)


@cluster_app.command("stop")
def cluster_stop():
    """Stop the cluster (preserves state)."""
    cluster = K3dCluster()

    if not cluster.is_running():
        console.print("[yellow]Cluster is not running[/yellow]")
        return

    console.print("[yellow]Stopping cluster...[/yellow]")
    if cluster.stop():
        console.print("[green]✅ Cluster stopped[/green]")
    else:
        console.print("[red]❌ Failed to stop cluster[/red]")


@cluster_app.command("delete")
def cluster_delete(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation")
):
    """Delete the cluster entirely."""
    cluster = K3dCluster()

    if not cluster.exists():
        console.print("[yellow]Cluster does not exist[/yellow]")
        return

    if not force:
        confirm = typer.confirm("Delete the battlestation cluster?")
        if not confirm:
            return

    console.print("[yellow]Deleting cluster...[/yellow]")
    if cluster.delete():
        console.print("[green]✅ Cluster deleted[/green]")
    else:
        console.print("[red]❌ Failed to delete cluster[/red]")


@cluster_app.command("status")
def cluster_status():
    """Show cluster status."""
    cluster = K3dCluster()

    exists = cluster.exists()
    running = cluster.is_running() if exists else False

    if not exists:
        console.print("[yellow]Cluster does not exist[/yellow]")
        console.print("Create with: emdx swarm cluster start")
    elif running:
        console.print("[green]✅ Cluster is running[/green]")
    else:
        console.print("[yellow]⏸️ Cluster exists but is stopped[/yellow]")
        console.print("Start with: emdx swarm cluster start")
