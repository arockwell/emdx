#!/usr/bin/env python3
"""
Run the EMDX analyze command directly
"""
import sys
import os
from pathlib import Path

# Add the current directory to Python path so we can import emdx
sys.path.insert(0, str(Path(__file__).parent))

from emdx.commands.analyze import KnowledgeBaseAnalyzer
from emdx.commands.analyze import (
    display_overview, display_tags, display_content, 
    display_temporal, display_health
)
from emdx.config.settings import get_db_path
from rich.console import Console

def main():
    console = Console()
    
    # Get database path using the config function
    db_path = get_db_path()
    
    # Also check old location if needed
    if not db_path.exists():
        db_path = Path.home() / ".local" / "share" / "emdx" / "emdx.db"
        if not db_path.exists():
            console.print(f"[red]Database not found at {db_path}[/red]")
            return 1
    
    console.print(f"[green]Using database at: {db_path}[/green]\n")
    
    with console.status("[bold green]Analyzing knowledge base..."):
        analyzer = KnowledgeBaseAnalyzer(str(db_path))
        
        # Gather all data
        overview = analyzer.get_overview_stats()
        tags = analyzer.analyze_tags()
        content = analyzer.analyze_content_patterns()
        temporal = analyzer.analyze_temporal_patterns()
        health = analyzer.analyze_project_health()
    
    # Display full report
    display_overview(overview)
    display_tags(tags)
    display_content(content)
    display_temporal(temporal)
    display_health(health)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())