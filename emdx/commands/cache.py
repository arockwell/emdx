"""
Cache management commands for emdx.

Provides CLI commands for inspecting and managing the application cache.
"""

from typing import Optional

import typer
from rich.table import Table

from emdx.utils.output import console

app = typer.Typer(help="Cache management commands")


@app.command()
def stats(
    cache_name: Optional[str] = typer.Argument(
        None, help="Specific cache to show (or all if not provided)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show cache statistics and hit rates."""
    import json

    from emdx.services.cache import CacheManager

    cache_manager = CacheManager.instance()

    if cache_name:
        # Show stats for specific cache
        cache = cache_manager.get_cache(cache_name)
        if not cache:
            console.print(f"[red]Cache '{cache_name}' not found[/red]")
            console.print("\n[dim]Available caches:[/dim]")
            for name in cache_manager._caches:
                console.print(f"  • {name}")
            raise typer.Exit(1)

        stats = cache.stats.to_dict()
        stats["name"] = cache_name
        stats["ttl_seconds"] = cache.ttl

        if json_output:
            print(json.dumps(stats, indent=2))
        else:
            _display_cache_stats(cache_name, stats)
    else:
        # Show stats for all caches
        all_stats = cache_manager.get_stats()
        total_stats = cache_manager.get_total_stats()

        if json_output:
            output = {
                "caches": all_stats,
                "totals": total_stats,
                "enabled": cache_manager.enabled,
            }
            print(json.dumps(output, indent=2))
        else:
            console.print("\n[bold]📊 Cache Statistics[/bold]\n")

            # Status
            status = "[green]enabled[/green]" if cache_manager.enabled else "[red]disabled[/red]"
            console.print(f"Status: {status}\n")

            # Individual caches table
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Cache", style="cyan")
            table.add_column("Size", justify="right")
            table.add_column("Max Size", justify="right")
            table.add_column("Hits", justify="right", style="green")
            table.add_column("Misses", justify="right", style="yellow")
            table.add_column("Hit Rate", justify="right")
            table.add_column("Evictions", justify="right", style="red")

            for name, stats in all_stats.items():
                hit_rate = stats.get("hit_rate_percent", 0)
                hit_rate_color = "green" if hit_rate > 70 else "yellow" if hit_rate > 40 else "red"

                table.add_row(
                    name,
                    str(stats.get("current_size", 0)),
                    str(stats.get("max_size", 0)),
                    str(stats.get("hits", 0)),
                    str(stats.get("misses", 0)),
                    f"[{hit_rate_color}]{hit_rate:.1f}%[/{hit_rate_color}]",
                    str(stats.get("evictions", 0)),
                )

            console.print(table)

            # Totals
            console.print("\n[bold]Totals:[/bold]")
            console.print(f"  Total entries: {total_stats.get('total_size', 0)}")
            console.print(f"  Total hits: {total_stats.get('hits', 0)}")
            console.print(f"  Total misses: {total_stats.get('misses', 0)}")
            total_hit_rate = total_stats.get("hit_rate_percent", 0)
            console.print(f"  Overall hit rate: {total_hit_rate:.1f}%")


def _display_cache_stats(name: str, stats: dict) -> None:
    """Display formatted stats for a single cache."""
    console.print(f"\n[bold]📊 Cache: {name}[/bold]\n")

    hit_rate = stats.get("hit_rate_percent", 0)
    hit_rate_color = "green" if hit_rate > 70 else "yellow" if hit_rate > 40 else "red"

    console.print(f"  Size: {stats.get('current_size', 0)} / {stats.get('max_size', 0)}")
    console.print(f"  TTL: {stats.get('ttl_seconds', 0)}s")
    console.print(f"  Hits: [green]{stats.get('hits', 0)}[/green]")
    console.print(f"  Misses: [yellow]{stats.get('misses', 0)}[/yellow]")
    console.print(f"  Hit rate: [{hit_rate_color}]{hit_rate:.1f}%[/{hit_rate_color}]")
    console.print(f"  Evictions: [red]{stats.get('evictions', 0)}[/red]")
    console.print(f"  Expirations: {stats.get('expirations', 0)}")


@app.command()
def clear(
    cache_name: Optional[str] = typer.Argument(
        None, help="Specific cache to clear (clears all if not provided)"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
) -> None:
    """Clear cache entries."""
    from emdx.services.cache import CacheManager

    cache_manager = CacheManager.instance()

    if cache_name:
        # Clear specific cache
        cache = cache_manager.get_cache(cache_name)
        if not cache:
            console.print(f"[red]Cache '{cache_name}' not found[/red]")
            raise typer.Exit(1)

        if not force:
            typer.confirm(f"Clear cache '{cache_name}'?", abort=True)

        count = cache.clear()
        console.print(f"[green]✅ Cleared {count} entries from '{cache_name}'[/green]")
    else:
        # Clear all caches
        if not force:
            typer.confirm("Clear ALL caches?", abort=True)

        results = cache_manager.clear_all()
        total = sum(results.values())
        console.print(f"[green]✅ Cleared {total} entries from {len(results)} caches[/green]")

        for name, count in results.items():
            if count > 0:
                console.print(f"   • {name}: {count} entries")


@app.command()
def cleanup(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be cleaned without doing it"),
) -> None:
    """Remove expired entries from all caches."""
    from emdx.services.cache import CacheManager

    cache_manager = CacheManager.instance()
    results = cache_manager.cleanup_expired()

    total = sum(results.values())

    if dry_run:
        console.print(f"[dim]Would remove {total} expired entries[/dim]")
    else:
        console.print(f"[green]✅ Removed {total} expired entries[/green]")

    for name, count in results.items():
        if count > 0:
            console.print(f"   • {name}: {count} entries")


@app.command()
def enable() -> None:
    """Enable caching globally."""
    from emdx.services.cache import CacheManager

    cache_manager = CacheManager.instance()
    cache_manager.enabled = True
    console.print("[green]✅ Caching enabled[/green]")


@app.command()
def disable() -> None:
    """Disable caching globally (clears all caches)."""
    from emdx.services.cache import CacheManager

    cache_manager = CacheManager.instance()
    cache_manager.enabled = False
    console.print("[yellow]⚠️ Caching disabled (all caches cleared)[/yellow]")


@app.command()
def flush_access() -> None:
    """Flush pending access count updates to the database."""
    from emdx.services.cache import get_access_buffer

    buffer = get_access_buffer()
    pending = buffer.pending_count
    buffered = buffer.buffered_docs

    if pending == 0:
        console.print("[dim]No pending access count updates[/dim]")
        return

    flushed = buffer.flush()
    console.print(f"[green]✅ Flushed {flushed} access count updates ({pending} pending updates)[/green]")
