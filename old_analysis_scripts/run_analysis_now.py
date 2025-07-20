#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from emdx.commands.analyze import KnowledgeBaseAnalyzer, display_overview, display_tags, display_content, display_temporal, display_health
from rich.console import Console

console = Console()

analyzer = KnowledgeBaseAnalyzer()

# Gather all data
console.print("[bold green]Analyzing EMDX Knowledge Base...[/bold green]\n")

overview = analyzer.get_overview_stats()
tags = analyzer.analyze_tags()
content = analyzer.analyze_content_patterns()
temporal = analyzer.analyze_temporal_patterns()
health = analyzer.analyze_project_health()

# Display everything
display_overview(overview)
display_tags(tags)
display_content(content)
display_temporal(temporal)
display_health(health)

# Save JSON export
import json
data = {
    "overview": overview,
    "tags": tags,
    "content": content,
    "temporal": temporal,
    "health": health,
}

with open('emdx_analysis.json', 'w') as f:
    json.dump(data, f, indent=2, default=str)
    
console.print("\n[green]Full analysis saved to emdx_analysis.json[/green]")