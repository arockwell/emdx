"""
Graph analysis and visualization commands for EMDX.
Builds and exports knowledge graphs based on document relationships.
"""

import json
import typer
from typing import Optional, List
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from ..analysis.graph import GraphAnalyzer
from ..export.graph import GraphExporter
from ..utils.emoji_aliases import expand_aliases

app = typer.Typer()
console = Console()


@app.command()
def graph(
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path"),
    format: str = typer.Option("json", "--format", "-f", help="Output format: json, graphml, dot, mermaid, d3, html"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Filter by tags (comma-separated)"),
    no_tags: Optional[str] = typer.Option(None, "--no-tags", help="Exclude documents with these tags"),
    min_similarity: float = typer.Option(20.0, "--min-similarity", "-m", help="Minimum relationship score (0-100)"),
    include_orphans: bool = typer.Option(True, "--include-orphans/--no-orphans", help="Include isolated documents"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON to stdout"),
    ids_only: bool = typer.Option(False, "--ids-only", help="Output only node IDs (for pipelines)"),
    recommendations: Optional[int] = typer.Option(None, "--recommendations", "-r", help="Get recommendations for document ID"),
    stats: bool = typer.Option(False, "--stats", "-s", help="Show graph statistics only"),
    web: bool = typer.Option(False, "--web", "-w", help="Generate interactive HTML visualization"),
):
    """
    Build and export knowledge graphs showing document relationships.
    
    This command analyzes relationships between documents based on:
    - Shared tags (weighted by rarity)
    - Content similarity
    - Temporal proximity
    - Project grouping
    - Cross-references
    
    Examples:
        emdx graph                                    # Show graph stats
        emdx graph --format mermaid                   # Output Mermaid diagram
        emdx graph --output graph.json --format d3    # Save D3.js graph
        emdx graph --tags "gameplan,active"           # Filter by tags
        emdx graph --min-similarity 50                # Strong relationships only
        emdx graph --recommendations 123              # Get similar docs for #123
        emdx graph --web --output graph.html          # Interactive visualization
        
    Formats:
        - json: Standard JSON with nodes/edges
        - d3: D3.js force layout format
        - graphml: XML format for Gephi/yEd
        - dot: Graphviz DOT format
        - mermaid: Mermaid diagram syntax
        - html: Complete interactive HTML page (use with --web)
    """
    try:
        analyzer = GraphAnalyzer()
        
        # Handle recommendations mode
        if recommendations is not None:
            show_recommendations(analyzer, recommendations)
            return
        
        # Parse tag filters
        tag_filter = None
        if tags:
            tag_filter = expand_aliases([t.strip() for t in tags.split(",")])
        
        no_tag_filter = None
        if no_tags:
            no_tag_filter = expand_aliases([t.strip() for t in no_tags.split(",")])
        
        # Build the graph
        graph_data = analyzer.get_document_graph(
            project=project,
            tag_filter=tag_filter,
            min_similarity=min_similarity,
            include_orphans=include_orphans
        )
        
        # Filter out documents with excluded tags if specified
        if no_tag_filter:
            filtered_nodes = []
            excluded_ids = set()
            
            for node in graph_data['nodes']:
                node_tags = set(node.get('tags', []))
                if not any(tag in node_tags for tag in no_tag_filter):
                    filtered_nodes.append(node)
                else:
                    excluded_ids.add(node['id'])
            
            # Filter edges to remove those connected to excluded nodes
            filtered_edges = [
                edge for edge in graph_data['edges']
                if edge['source'] not in excluded_ids and edge['target'] not in excluded_ids
            ]
            
            graph_data['nodes'] = filtered_nodes
            graph_data['edges'] = filtered_edges
            
            # Update metadata
            graph_data['metadata']['node_count'] = len(filtered_nodes)
            graph_data['metadata']['edge_count'] = len(filtered_edges)
        
        # Handle different output modes
        if ids_only:
            # Output just node IDs for pipeline integration
            for node in graph_data['nodes']:
                console.print(node['id'])
            return
        
        if json_output:
            # Raw JSON output
            console.print(json.dumps(graph_data, indent=2, default=str))
            return
        
        if stats:
            # Show statistics only
            show_graph_stats(graph_data)
            return
        
        # Export the graph
        exporter = GraphExporter()
        
        # Handle web/HTML generation
        if web or format == "html":
            if not output:
                output = "knowledge_graph.html"
            
            html_content = exporter.generate_html_visualization(
                graph_data,
                title="EMDX Knowledge Graph"
            )
            
            Path(output).write_text(html_content)
            console.print(f"[green]✓[/green] Interactive HTML visualization saved to: {output}")
            console.print(f"[dim]Open in browser: file://{Path(output).absolute()}[/dim]")
            return
        
        # Regular export
        exported = exporter.export(graph_data, format=format, output_path=output)
        
        if output:
            console.print(f"[green]✓[/green] Graph exported to: {output}")
            console.print(f"[dim]Format: {format}, Nodes: {len(graph_data['nodes'])}, "
                         f"Edges: {len(graph_data['edges'])}[/dim]")
        else:
            # Print to console if no output file specified
            console.print(exported)
            
    except Exception as e:
        console.print(f"[red]Error building graph:[/red] {e}")
        raise typer.Exit(1)


def show_graph_stats(graph_data: dict):
    """Display graph statistics and metrics."""
    metadata = graph_data.get('metadata', {})
    metrics = metadata.get('metrics', {})
    
    # Overview panel
    overview = Panel(
        f"[bold]Nodes:[/bold] {metadata.get('node_count', 0)}\n"
        f"[bold]Edges:[/bold] {metadata.get('edge_count', 0)}\n"
        f"[bold]Density:[/bold] {metrics.get('density', 0):.3f}\n"
        f"[bold]Clustering:[/bold] {metrics.get('clustering_coefficient', 0):.3f}\n"
        f"[bold]Orphans:[/bold] {metrics.get('orphan_count', 0)}",
        title="[bold]Graph Overview[/bold]",
        border_style="blue"
    )
    console.print(overview)
    
    # Connected components
    components = metrics.get('connected_components', [])
    if components:
        console.print("\n[bold]Connected Components:[/bold]")
        table = Table(box=box.ROUNDED)
        table.add_column("Component", style="cyan")
        table.add_column("Size", justify="right")
        table.add_column("Document IDs")
        
        for i, component in enumerate(components[:5]):  # Show top 5
            table.add_row(
                f"Component {i+1}",
                str(len(component)),
                ", ".join(str(id) for id in component[:5]) + 
                ("..." if len(component) > 5 else "")
            )
        
        if len(components) > 5:
            table.add_row("[dim]...[/dim]", "[dim]...[/dim]", "[dim]...[/dim]")
        
        console.print(table)
    
    # Bridge nodes
    bridges = metrics.get('bridge_nodes', [])
    if bridges:
        console.print(f"\n[bold]Bridge Nodes:[/bold] {', '.join(str(b) for b in bridges[:10])}")
        if len(bridges) > 10:
            console.print(f"[dim]... and {len(bridges) - 10} more[/dim]")
    
    # Top central nodes
    centrality = metrics.get('centrality', {})
    if centrality:
        console.print("\n[bold]Most Connected Documents:[/bold]")
        
        # Sort by weighted degree centrality
        sorted_nodes = sorted(
            centrality.items(),
            key=lambda x: x[1]['weighted_degree'],
            reverse=True
        )[:10]
        
        table = Table(box=box.ROUNDED)
        table.add_column("ID", style="cyan")
        table.add_column("Connections", justify="right")
        table.add_column("Weighted Score", justify="right")
        
        for node_id, scores in sorted_nodes:
            table.add_row(
                str(node_id),
                str(scores['neighbor_count']),
                f"{scores['weighted_degree']:.2f}"
            )
        
        console.print(table)


def show_recommendations(analyzer: GraphAnalyzer, doc_id: int):
    """Show recommendations for a specific document."""
    try:
        recommendations = analyzer.get_node_recommendations(doc_id, limit=10)
        
        if not recommendations:
            console.print(f"[yellow]No recommendations found for document {doc_id}[/yellow]")
            return
        
        console.print(f"\n[bold]Recommendations for Document #{doc_id}:[/bold]\n")
        
        table = Table(box=box.ROUNDED)
        table.add_column("ID", style="cyan", width=6)
        table.add_column("Title", style="white")
        table.add_column("Score", justify="right", style="green")
        table.add_column("Reason", style="dim")
        
        for rec in recommendations:
            table.add_row(
                str(rec['id']),
                rec['title'][:50] + ("..." if len(rec['title']) > 50 else ""),
                f"{rec['similarity_score']:.1f}",
                rec['reason']
            )
        
        console.print(table)
        
    except Exception as e:
        console.print(f"[red]Error getting recommendations:[/red] {e}")
        raise typer.Exit(1)


# Pipeline support functions
@app.command("nodes")
def graph_nodes(
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Filter by project"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Filter by tags"),
    min_connections: int = typer.Option(0, "--min-connections", help="Minimum number of connections"),
    central: bool = typer.Option(False, "--central", help="Only show most central nodes"),
):
    """
    Output graph node IDs for pipeline integration.
    
    Examples:
        emdx graph nodes --central | emdx view      # View most connected docs
        emdx graph nodes --min-connections 5        # Well-connected docs only
    """
    try:
        analyzer = GraphAnalyzer()
        
        tag_filter = None
        if tags:
            tag_filter = expand_aliases([t.strip() for t in tags.split(",")])
        
        graph_data = analyzer.get_document_graph(
            project=project,
            tag_filter=tag_filter,
            include_orphans=False  # Exclude orphans when looking for connected nodes
        )
        
        # Get centrality scores
        centrality = graph_data['metadata']['metrics'].get('centrality', {})
        
        # Filter nodes
        output_nodes = []
        
        for node in graph_data['nodes']:
            node_id = node['id']
            scores = centrality.get(node_id, {})
            connections = scores.get('neighbor_count', 0)
            
            if connections >= min_connections:
                output_nodes.append((node_id, scores.get('weighted_degree', 0)))
        
        # Sort by centrality if requested
        if central:
            output_nodes.sort(key=lambda x: x[1], reverse=True)
            output_nodes = output_nodes[:20]  # Top 20 most central
        
        # Output IDs
        for node_id, _ in output_nodes:
            console.print(node_id)
            
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)