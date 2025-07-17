"""
Comprehensive analysis commands for EMDX knowledge base.
Provides insights into document patterns, tag usage, project distribution, and more.
"""

import sqlite3
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import json
from typing import Dict, List, Tuple, Any, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from rich.progress import track

from ..database import Database
from ..config.settings import get_db_path

app = typer.Typer()
console = Console()


class KnowledgeBaseAnalyzer:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = get_db_path()
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
    
    def get_overview_stats(self) -> Dict[str, Any]:
        """Get basic statistics about the knowledge base"""
        cursor = self.conn.cursor()
        
        # Total documents
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
        total_docs = cursor.fetchone()[0]
        
        # Total deleted
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 1")
        deleted_docs = cursor.fetchone()[0]
        
        # Total views
        cursor.execute("SELECT SUM(access_count) FROM documents WHERE is_deleted = 0")
        total_views = cursor.fetchone()[0] or 0
        
        # Most viewed
        cursor.execute("""
            SELECT title, access_count, id 
            FROM documents 
            WHERE is_deleted = 0 
            ORDER BY access_count DESC 
            LIMIT 10
        """)
        most_viewed = cursor.fetchall()
        
        # Most recent
        cursor.execute("""
            SELECT title, created_at, id 
            FROM documents 
            WHERE is_deleted = 0 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        most_recent = cursor.fetchall()
        
        # Projects
        cursor.execute("""
            SELECT project, COUNT(*) as count 
            FROM documents 
            WHERE is_deleted = 0 
            GROUP BY project 
            ORDER BY count DESC
        """)
        projects = cursor.fetchall()
        
        return {
            "total_documents": total_docs,
            "deleted_documents": deleted_docs,
            "total_views": total_views,
            "average_views": total_views / total_docs if total_docs > 0 else 0,
            "most_viewed": [dict(row) for row in most_viewed],
            "most_recent": [dict(row) for row in most_recent],
            "projects": [dict(row) for row in projects]
        }
    
    def analyze_tags(self) -> Dict[str, Any]:
        """Analyze tag usage patterns"""
        cursor = self.conn.cursor()
        
        # Get all tags with counts
        cursor.execute("""
            SELECT t.emoji, t.name, COUNT(dt.document_id) as count
            FROM tags t
            LEFT JOIN document_tags dt ON t.id = dt.tag_id
            LEFT JOIN documents d ON dt.document_id = d.id
            WHERE d.is_deleted = 0 OR d.is_deleted IS NULL
            GROUP BY t.id
            ORDER BY count DESC
        """)
        tags = cursor.fetchall()
        
        # Documents without tags
        cursor.execute("""
            SELECT COUNT(*) 
            FROM documents d
            WHERE d.is_deleted = 0 
            AND NOT EXISTS (
                SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
            )
        """)
        untagged = cursor.fetchone()[0]
        
        # Tag combinations
        cursor.execute("""
            SELECT d.id, GROUP_CONCAT(t.emoji || ':' || t.name) as tags
            FROM documents d
            JOIN document_tags dt ON d.id = dt.document_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0
            GROUP BY d.id
        """)
        combinations = Counter()
        for row in cursor.fetchall():
            if row[1]:
                tag_set = frozenset(row[1].split(','))
                if len(tag_set) > 1:
                    combinations[tag_set] += 1
        
        return {
            "tags": [dict(row) for row in tags],
            "total_tags": len(tags),
            "untagged_documents": untagged,
            "top_combinations": combinations.most_common(20)
        }
    
    def analyze_content_patterns(self) -> Dict[str, Any]:
        """Analyze content patterns and document types"""
        cursor = self.conn.cursor()
        
        # Title patterns
        cursor.execute("""
            SELECT title FROM documents WHERE is_deleted = 0
        """)
        titles = [row[0] for row in cursor.fetchall()]
        
        title_patterns = Counter()
        for title in titles:
            if title.startswith("Gameplan:"):
                title_patterns["gameplan"] += 1
            elif title.startswith("Analysis:"):
                title_patterns["analysis"] += 1
            elif title.startswith("Bug:"):
                title_patterns["bug"] += 1
            elif title.startswith("Feature:"):
                title_patterns["feature"] += 1
            elif title.startswith("Note:"):
                title_patterns["note"] += 1
            elif title.startswith("Issue"):
                title_patterns["issue"] += 1
            elif title.startswith("PR "):
                title_patterns["pr"] += 1
            else:
                title_patterns["other"] += 1
        
        # Content length distribution
        cursor.execute("""
            SELECT LENGTH(content) as length
            FROM documents 
            WHERE is_deleted = 0
        """)
        lengths = [row[0] for row in cursor.fetchall()]
        
        length_dist = {
            "very_short": sum(1 for l in lengths if l < 100),
            "short": sum(1 for l in lengths if 100 <= l < 500),
            "medium": sum(1 for l in lengths if 500 <= l < 2000),
            "long": sum(1 for l in lengths if 2000 <= l < 5000),
            "very_long": sum(1 for l in lengths if l >= 5000)
        }
        
        return {
            "title_patterns": dict(title_patterns),
            "length_distribution": length_dist,
            "average_length": sum(lengths) / len(lengths) if lengths else 0
        }
    
    def analyze_temporal_patterns(self) -> Dict[str, Any]:
        """Analyze when documents are created and accessed"""
        cursor = self.conn.cursor()
        
        # Creation patterns by month
        cursor.execute("""
            SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
            FROM documents
            WHERE is_deleted = 0
            GROUP BY month
            ORDER BY month
        """)
        creation_by_month = cursor.fetchall()
        
        # Access patterns
        cursor.execute("""
            SELECT strftime('%Y-%m', accessed_at) as month, COUNT(*) as count
            FROM documents
            WHERE is_deleted = 0 AND accessed_at IS NOT NULL
            GROUP BY month
            ORDER BY month
        """)
        access_by_month = cursor.fetchall()
        
        # Hour of day patterns
        cursor.execute("""
            SELECT strftime('%H', created_at) as hour, COUNT(*) as count
            FROM documents
            WHERE is_deleted = 0
            GROUP BY hour
            ORDER BY hour
        """)
        creation_by_hour = cursor.fetchall()
        
        return {
            "creation_by_month": [dict(row) for row in creation_by_month],
            "access_by_month": [dict(row) for row in access_by_month],
            "creation_by_hour": [dict(row) for row in creation_by_hour]
        }
    
    def analyze_project_health(self) -> Dict[str, Any]:
        """Analyze project success rates and patterns"""
        cursor = self.conn.cursor()
        
        # Success rate by project
        cursor.execute("""
            SELECT 
                d.project,
                COUNT(CASE WHEN t.name = 'success' THEN 1 END) as success_count,
                COUNT(CASE WHEN t.name = 'failed' THEN 1 END) as failed_count,
                COUNT(CASE WHEN t.name = 'blocked' THEN 1 END) as blocked_count,
                COUNT(CASE WHEN t.name = 'active' THEN 1 END) as active_count,
                COUNT(DISTINCT d.id) as total
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.document_id
            LEFT JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0
            GROUP BY d.project
        """)
        project_health = cursor.fetchall()
        
        # Gameplan success analysis
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN t2.name = 'success' THEN 1 END) as success_count,
                COUNT(CASE WHEN t2.name = 'failed' THEN 1 END) as failed_count,
                COUNT(CASE WHEN t2.name = 'blocked' THEN 1 END) as blocked_count,
                COUNT(DISTINCT d.id) as total
            FROM documents d
            JOIN document_tags dt1 ON d.id = dt1.document_id
            JOIN tags t1 ON dt1.tag_id = t1.id
            LEFT JOIN document_tags dt2 ON d.id = dt2.document_id
            LEFT JOIN tags t2 ON dt2.tag_id = t2.id AND t2.name IN ('success', 'failed', 'blocked')
            WHERE d.is_deleted = 0 AND t1.name = 'gameplan'
        """)
        gameplan_stats = cursor.fetchone()
        
        return {
            "project_health": [dict(row) for row in project_health],
            "gameplan_stats": dict(gameplan_stats) if gameplan_stats else {}
        }


@app.command()
def analyze(
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Save report to file"),
    json_export: Optional[Path] = typer.Option(None, "--json", help="Export raw data as JSON"),
    section: Optional[str] = typer.Option(None, "--section", "-s", help="Show specific section: overview, tags, content, temporal, health")
):
    """Analyze your EMDX knowledge base and generate insights."""
    with console.status("[bold green]Analyzing knowledge base..."):
        analyzer = KnowledgeBaseAnalyzer()
        
        # Gather all data
        overview = analyzer.get_overview_stats()
        tags = analyzer.analyze_tags()
        content = analyzer.analyze_content_patterns()
        temporal = analyzer.analyze_temporal_patterns()
        health = analyzer.analyze_project_health()
    
    # If specific section requested
    if section:
        if section == "overview":
            display_overview(overview)
        elif section == "tags":
            display_tags(tags)
        elif section == "content":
            display_content(content)
        elif section == "temporal":
            display_temporal(temporal)
        elif section == "health":
            display_health(health)
        else:
            console.print(f"[red]Unknown section: {section}[/red]")
            raise typer.Exit(1)
    else:
        # Display full report
        display_overview(overview)
        display_tags(tags)
        display_content(content)
        display_temporal(temporal)
        display_health(health)
    
    # Save outputs if requested
    if output:
        report = generate_text_report(overview, tags, content, temporal, health)
        output.write_text(report)
        console.print(f"\n[green]Report saved to: {output}[/green]")
    
    if json_export:
        data = {
            "overview": overview,
            "tags": tags,
            "content": content,
            "temporal": temporal,
            "health": health,
            "generated_at": datetime.now().isoformat()
        }
        json_export.write_text(json.dumps(data, indent=2, default=str))
        console.print(f"[green]JSON export saved to: {json_export}[/green]")


def display_overview(overview: Dict[str, Any]):
    """Display overview statistics"""
    console.print("\n[bold cyan]📊 Knowledge Base Overview[/bold cyan]\n")
    
    # Stats table
    stats_table = Table(show_header=False, box=box.ROUNDED)
    stats_table.add_row("Total Documents", f"[bold]{overview['total_documents']}[/bold]")
    stats_table.add_row("Total Views", f"{overview['total_views']:,}")
    stats_table.add_row("Average Views/Doc", f"{overview['average_views']:.1f}")
    stats_table.add_row("Deleted Documents", f"{overview['deleted_documents']}")
    console.print(stats_table)
    
    # Projects
    if overview['projects']:
        console.print("\n[bold]Projects Distribution:[/bold]")
        proj_table = Table(show_header=True, header_style="bold magenta")
        proj_table.add_column("Project", style="cyan")
        proj_table.add_column("Documents", justify="right")
        
        for proj in overview['projects'][:10]:
            proj_table.add_row(
                proj['project'] or "[dim]No Project[/dim]",
                str(proj['count'])
            )
        console.print(proj_table)
    
    # Most viewed
    if overview['most_viewed']:
        console.print("\n[bold]Most Viewed Documents:[/bold]")
        view_table = Table(show_header=True, header_style="bold magenta")
        view_table.add_column("ID", style="dim", width=6)
        view_table.add_column("Title", no_wrap=False)
        view_table.add_column("Views", justify="right")
        
        for doc in overview['most_viewed'][:5]:
            view_table.add_row(
                str(doc['id']),
                doc['title'][:60] + "..." if len(doc['title']) > 60 else doc['title'],
                str(doc['access_count'])
            )
        console.print(view_table)


def display_tags(tags: Dict[str, Any]):
    """Display tag analysis"""
    console.print("\n[bold cyan]🏷️  Tag Analysis[/bold cyan]\n")
    
    stats = f"Total Tags: [bold]{tags['total_tags']}[/bold] | Untagged Documents: [bold]{tags['untagged_documents']}[/bold]"
    console.print(Panel(stats, box=box.ROUNDED))
    
    if tags['tags']:
        console.print("\n[bold]Top Tags:[/bold]")
        tag_table = Table(show_header=True, header_style="bold magenta")
        tag_table.add_column("Emoji", width=4)
        tag_table.add_column("Name", style="cyan")
        tag_table.add_column("Count", justify="right")
        tag_table.add_column("Usage", width=20)
        
        max_count = tags['tags'][0]['count'] if tags['tags'] else 1
        for tag in tags['tags'][:20]:
            if tag['count'] > 0:
                bar_length = int((tag['count'] / max_count) * 20)
                bar = "█" * bar_length + "░" * (20 - bar_length)
                tag_table.add_row(
                    tag['emoji'],
                    tag['name'],
                    str(tag['count']),
                    f"[green]{bar}[/green]"
                )
        console.print(tag_table)


def display_content(content: Dict[str, Any]):
    """Display content analysis"""
    console.print("\n[bold cyan]📝 Content Analysis[/bold cyan]\n")
    
    # Document types
    console.print("[bold]Document Type Distribution:[/bold]")
    type_table = Table(show_header=True, header_style="bold magenta")
    type_table.add_column("Type", style="cyan")
    type_table.add_column("Count", justify="right")
    type_table.add_column("Percentage", justify="right")
    
    total = sum(content['title_patterns'].values())
    for pattern, count in sorted(content['title_patterns'].items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total * 100) if total > 0 else 0
        type_table.add_row(
            pattern.capitalize(),
            str(count),
            f"{percentage:.1f}%"
        )
    console.print(type_table)
    
    # Length distribution
    console.print("\n[bold]Document Length Distribution:[/bold]")
    length_table = Table(show_header=True, header_style="bold magenta")
    length_table.add_column("Category", style="cyan")
    length_table.add_column("Count", justify="right")
    length_table.add_column("Characters", justify="right", style="dim")
    
    length_ranges = {
        "very_short": "< 100",
        "short": "100-500",
        "medium": "500-2K",
        "long": "2K-5K",
        "very_long": "> 5K"
    }
    
    for size, count in content['length_distribution'].items():
        length_table.add_row(
            size.replace('_', ' ').capitalize(),
            str(count),
            length_ranges.get(size, "")
        )
    console.print(length_table)
    console.print(f"\nAverage document length: [bold]{content['average_length']:.0f}[/bold] characters")


def display_temporal(temporal: Dict[str, Any]):
    """Display temporal patterns"""
    console.print("\n[bold cyan]📅 Temporal Patterns[/bold cyan]\n")
    
    # Recent activity
    if temporal['creation_by_month']:
        console.print("[bold]Recent Activity (Last 6 Months):[/bold]")
        recent_table = Table(show_header=True, header_style="bold magenta")
        recent_table.add_column("Month", style="cyan")
        recent_table.add_column("Created", justify="right")
        recent_table.add_column("Activity", width=30)
        
        recent_months = temporal['creation_by_month'][-6:]
        max_count = max(m['count'] for m in recent_months) if recent_months else 1
        
        for month in recent_months:
            bar_length = int((month['count'] / max_count) * 30)
            bar = "█" * bar_length + "░" * (30 - bar_length)
            recent_table.add_row(
                month['month'],
                str(month['count']),
                f"[green]{bar}[/green]"
            )
        console.print(recent_table)


def display_health(health: Dict[str, Any]):
    """Display project health analysis"""
    console.print("\n[bold cyan]💚 Project Health Analysis[/bold cyan]\n")
    
    # Gameplan success rate
    if health.get('gameplan_stats'):
        stats = health['gameplan_stats']
        total = stats.get('total', 0)
        if total > 0:
            success_rate = (stats.get('success_count', 0) / total * 100)
            console.print(Panel(
                f"[bold]Gameplan Success Rate:[/bold] [green]{success_rate:.1f}%[/green] "
                f"({stats.get('success_count', 0)}/{total} gameplans)",
                box=box.ROUNDED
            ))
    
    # Project health
    if health['project_health']:
        console.print("\n[bold]Success Rates by Project:[/bold]")
        health_table = Table(show_header=True, header_style="bold magenta")
        health_table.add_column("Project", style="cyan")
        health_table.add_column("Total", justify="right")
        health_table.add_column("Success", justify="right", style="green")
        health_table.add_column("Failed", justify="right", style="red")
        health_table.add_column("Blocked", justify="right", style="yellow")
        health_table.add_column("Active", justify="right", style="blue")
        health_table.add_column("Success %", justify="right")
        
        for proj in health['project_health']:
            if proj['total'] > 5:  # Only show projects with meaningful data
                success_rate = (proj['success_count'] / proj['total'] * 100) if proj['total'] > 0 else 0
                health_table.add_row(
                    proj['project'] or "[dim]No Project[/dim]",
                    str(proj['total']),
                    str(proj['success_count']),
                    str(proj['failed_count']),
                    str(proj['blocked_count']),
                    str(proj['active_count']),
                    f"{success_rate:.1f}%"
                )
        console.print(health_table)


def generate_text_report(overview, tags, content, temporal, health) -> str:
    """Generate a text report for file output"""
    report = []
    report.append("# EMDX Knowledge Base Analysis Report")
    report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Overview
    report.append("\n## Overview Statistics")
    report.append(f"- Total Documents: {overview['total_documents']}")
    report.append(f"- Total Views: {overview['total_views']}")
    report.append(f"- Average Views per Document: {overview['average_views']:.1f}")
    report.append(f"- Deleted Documents: {overview['deleted_documents']}")
    
    # Projects
    report.append("\n### Projects Distribution")
    for proj in overview['projects'][:10]:
        report.append(f"- {proj['project'] or 'No Project'}: {proj['count']} documents")
    
    # Tags
    report.append("\n## Tag Analysis")
    report.append(f"- Total Unique Tags: {tags['total_tags']}")
    report.append(f"- Untagged Documents: {tags['untagged_documents']}")
    
    report.append("\n### Top Tags")
    for tag in tags['tags'][:20]:
        if tag['count'] > 0:
            report.append(f"- {tag['emoji']} {tag['name']}: {tag['count']} documents")
    
    # Content
    report.append("\n## Content Analysis")
    report.append("\n### Document Type Distribution")
    for pattern, count in sorted(content['title_patterns'].items(), key=lambda x: x[1], reverse=True):
        report.append(f"- {pattern.capitalize()}: {count}")
    
    # Project Health
    if health.get('gameplan_stats'):
        stats = health['gameplan_stats']
        total = stats.get('total', 0)
        if total > 0:
            success_rate = (stats.get('success_count', 0) / total * 100)
            report.append(f"\n## Gameplan Success Rate")
            report.append(f"- Overall: {success_rate:.1f}% ({stats.get('success_count', 0)}/{total})")
    
    return "\n".join(report)