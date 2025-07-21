"""
Interactive graph browser for EMDX knowledge base.
Displays document relationships as ASCII art graph.
"""

import logging
import math
from typing import Dict, List, Tuple, Set, Optional, Any
from collections import defaultdict

from textual.app import ComposeResult
from textual.widgets import Static, DataTable, Label
from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.widget import Widget
from textual.reactive import reactive
from textual.binding import Binding
from textual import events
from rich.text import Text
from rich.console import RenderableType

from ..analysis.graph import GraphAnalyzer
from ..models.documents import get_document
from ..ui.formatting import format_tags
from .document_viewer import FullScreenView

logger = logging.getLogger(__name__)


class GraphCanvas(Static):
    """Canvas widget for ASCII art graph rendering."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.graph_data: Optional[Dict[str, Any]] = None
        self.node_positions: Dict[int, Tuple[int, int]] = {}
        self.selected_node: Optional[int] = None
        self.viewport_offset = (0, 0)  # x, y offset for panning
        self.zoom_level = 1.0
        
    def set_graph_data(self, graph_data: Dict[str, Any]) -> None:
        """Set the graph data and calculate layout."""
        self.graph_data = graph_data
        self._calculate_layout()
        self.refresh()
    
    def _calculate_layout(self) -> None:
        """Calculate node positions using force-directed layout simulation."""
        if not self.graph_data:
            return
            
        nodes = self.graph_data['nodes']
        edges = self.graph_data['edges']
        
        if not nodes:
            return
        
        # Initialize positions randomly
        import random
        random.seed(42)  # For consistent layout
        
        positions = {}
        for node in nodes:
            angle = random.uniform(0, 2 * math.pi)
            radius = random.uniform(10, 30)
            positions[node['id']] = [
                radius * math.cos(angle),
                radius * math.sin(angle)
            ]
        
        # Build adjacency for force calculations
        adjacency = defaultdict(list)
        for edge in edges:
            adjacency[edge['source']].append((edge['target'], edge['weight']))
            adjacency[edge['target']].append((edge['source'], edge['weight']))
        
        # Simulate forces
        iterations = 50
        for _ in range(iterations):
            forces = defaultdict(lambda: [0.0, 0.0])
            
            # Repulsive forces between all nodes
            for i, node1 in enumerate(nodes):
                for j, node2 in enumerate(nodes[i+1:], i+1):
                    id1, id2 = node1['id'], node2['id']
                    dx = positions[id2][0] - positions[id1][0]
                    dy = positions[id2][1] - positions[id1][1]
                    
                    dist = math.sqrt(dx*dx + dy*dy) + 0.001
                    if dist < 50:  # Only repel if close
                        force = 20 / (dist * dist)
                        forces[id1][0] -= force * dx / dist
                        forces[id1][1] -= force * dy / dist
                        forces[id2][0] += force * dx / dist
                        forces[id2][1] += force * dy / dist
            
            # Attractive forces along edges
            for edge in edges:
                id1, id2 = edge['source'], edge['target']
                weight = edge['weight'] / 100.0  # Normalize weight
                
                dx = positions[id2][0] - positions[id1][0]
                dy = positions[id2][1] - positions[id1][1]
                dist = math.sqrt(dx*dx + dy*dy) + 0.001
                
                # Spring force
                force = 0.1 * weight * (dist - 20)  # Ideal distance = 20
                forces[id1][0] += force * dx / dist
                forces[id1][1] += force * dy / dist
                forces[id2][0] -= force * dx / dist
                forces[id2][1] -= force * dy / dist
            
            # Apply forces with damping
            damping = 0.8
            for node_id in positions:
                positions[node_id][0] += forces[node_id][0] * damping
                positions[node_id][1] += forces[node_id][1] * damping
        
        # Convert to integer positions for terminal
        # Scale and center
        min_x = min(pos[0] for pos in positions.values())
        max_x = max(pos[0] for pos in positions.values())
        min_y = min(pos[1] for pos in positions.values())
        max_y = max(pos[1] for pos in positions.values())
        
        width = max_x - min_x
        height = max_y - min_y
        
        # Scale to terminal size (leave margins)
        term_width = 100
        term_height = 40
        
        scale_x = (term_width - 20) / width if width > 0 else 1
        scale_y = (term_height - 10) / height if height > 0 else 1
        scale = min(scale_x, scale_y)
        
        self.node_positions = {}
        for node_id, (x, y) in positions.items():
            self.node_positions[node_id] = (
                int((x - min_x) * scale + 10),
                int((y - min_y) * scale + 5)
            )
    
    def render(self) -> RenderableType:
        """Render the graph as ASCII art."""
        if not self.graph_data or not self.node_positions:
            return Text("No graph data to display", style="dim")
        
        # Create canvas
        width = 120
        height = 50
        canvas = [[' ' for _ in range(width)] for _ in range(height)]
        
        # Draw edges first (so they appear behind nodes)
        for edge in self.graph_data['edges']:
            src_pos = self.node_positions.get(edge['source'])
            tgt_pos = self.node_positions.get(edge['target'])
            
            if src_pos and tgt_pos:
                self._draw_edge(canvas, src_pos, tgt_pos, edge['weight'])
        
        # Draw nodes
        node_map = {node['id']: node for node in self.graph_data['nodes']}
        for node_id, (x, y) in self.node_positions.items():
            if 0 <= x < width and 0 <= y < height:
                node = node_map.get(node_id)
                if node:
                    # Determine node character based on tags
                    char = self._get_node_char(node)
                    canvas[y][x] = char
                    
                    # Draw node ID nearby if selected
                    if node_id == self.selected_node:
                        id_str = f"[{node_id}]"
                        for i, c in enumerate(id_str):
                            if x + i + 1 < width:
                                canvas[y][x + i + 1] = c
        
        # Convert canvas to text with styling
        lines = []
        for row in canvas:
            line = ''.join(row)
            # Highlight selected node's row
            if self.selected_node:
                node_pos = self.node_positions.get(self.selected_node)
                if node_pos and row == canvas[node_pos[1]]:
                    lines.append(Text(line, style="bold yellow"))
                else:
                    lines.append(Text(line))
            else:
                lines.append(Text(line))
        
        return Text("\n").join(lines)
    
    def _draw_edge(self, canvas: List[List[str]], start: Tuple[int, int], 
                   end: Tuple[int, int], weight: float) -> None:
        """Draw an edge between two points using ASCII characters."""
        x1, y1 = start
        x2, y2 = end
        
        # Determine edge character based on weight
        if weight >= 70:
            edge_char = '='
        elif weight >= 40:
            edge_char = '-'
        else:
            edge_char = '·'
        
        # Simple line drawing algorithm
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx - dy
        
        x, y = x1, y1
        
        while True:
            if 0 <= x < len(canvas[0]) and 0 <= y < len(canvas):
                if canvas[y][x] == ' ':  # Don't overwrite nodes
                    canvas[y][x] = edge_char
            
            if x == x2 and y == y2:
                break
                
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
    
    def _get_node_char(self, node: Dict[str, Any]) -> str:
        """Get character representation for a node based on its properties."""
        tags = node.get('tags', [])
        
        # Special characters for different node types
        if '🎯' in tags or 'gameplan' in tags:
            return '◎'  # Target/gameplan
        elif '🐛' in tags or 'bug' in tags:
            return '✗'  # Bug
        elif '✨' in tags or 'feature' in tags:
            return '★'  # Feature
        elif '🚀' in tags or 'active' in tags:
            return '▶'  # Active
        elif '✅' in tags or 'done' in tags:
            return '✓'  # Done
        else:
            return '●'  # Default node
    
    def select_node(self, node_id: int) -> None:
        """Select a node for highlighting."""
        self.selected_node = node_id
        self.refresh()
    
    def get_node_at_position(self, x: int, y: int) -> Optional[int]:
        """Get node ID at given canvas position."""
        for node_id, (nx, ny) in self.node_positions.items():
            if abs(nx - x) <= 1 and abs(ny - y) <= 1:
                return node_id
        return None


class GraphBrowser(Widget):
    """Interactive graph browser widget."""
    
    BINDINGS = [
        Binding("h", "move_left", "Left"),
        Binding("j", "move_down", "Down"),  
        Binding("k", "move_up", "Up"),
        Binding("l", "move_right", "Right"),
        Binding("enter", "select_node", "View"),
        Binding("space", "center_selected", "Center"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "quit", "Back"),
        Binding("?", "show_help", "Help"),
    ]
    
    CSS = """
    GraphBrowser {
        layout: horizontal;
        height: 100%;
    }
    
    GraphCanvas {
        width: 70%;
        border: solid $primary;
        padding: 1;
        background: $surface;
    }
    
    #node-details {
        width: 30%;
        border: solid $primary;
        padding: 1;
        margin-left: 1;
    }
    
    #graph-stats {
        height: 3;
        border: solid $primary;
        padding: 0 1;
        margin-bottom: 1;
    }
    """
    
    def __init__(self, project: Optional[str] = None, tags: Optional[List[str]] = None, **kwargs):
        super().__init__(**kwargs)
        self.project = project
        self.tag_filter = tags
        self.analyzer = GraphAnalyzer()
        self.graph_data: Optional[Dict[str, Any]] = None
        self.selected_node_id: Optional[int] = None
        self.cursor_pos = (50, 25)  # Start in center
        
    def compose(self) -> ComposeResult:
        """Create child widgets."""
        with Vertical():
            yield Label("Knowledge Graph", id="graph-stats")
            with Horizontal():
                yield GraphCanvas(id="graph-canvas")
                yield ScrollableContainer(
                    Static("Select a node to view details", id="node-info"),
                    id="node-details"
                )
    
    def on_mount(self) -> None:
        """Load graph data when mounted."""
        self.load_graph()
    
    def load_graph(self) -> None:
        """Load graph data from analyzer."""
        try:
            self.graph_data = self.analyzer.get_document_graph(
                project=self.project,
                tag_filter=self.tag_filter,
                min_similarity=20.0,
                include_orphans=False
            )
            
            # Update canvas
            canvas = self.query_one("#graph-canvas", GraphCanvas)
            canvas.set_graph_data(self.graph_data)
            
            # Update stats
            self.update_stats()
            
            # Select first node if any
            if self.graph_data['nodes']:
                self.selected_node_id = self.graph_data['nodes'][0]['id']
                canvas.select_node(self.selected_node_id)
                self.update_node_details()
                
        except Exception as e:
            logger.error(f"Error loading graph: {e}")
            self.notify(f"Error loading graph: {e}", severity="error")
    
    def update_stats(self) -> None:
        """Update graph statistics display."""
        if not self.graph_data:
            return
            
        metadata = self.graph_data.get('metadata', {})
        metrics = metadata.get('metrics', {})
        
        stats_text = (
            f"Nodes: {metadata.get('node_count', 0)} | "
            f"Edges: {metadata.get('edge_count', 0)} | "
            f"Density: {metrics.get('density', 0):.3f} | "
            f"Clusters: {len(metrics.get('connected_components', []))}"
        )
        
        self.query_one("#graph-stats", Label).update(stats_text)
    
    def update_node_details(self) -> None:
        """Update the details panel for selected node."""
        if not self.selected_node_id or not self.graph_data:
            return
        
        # Find node in graph data
        node = None
        for n in self.graph_data['nodes']:
            if n['id'] == self.selected_node_id:
                node = n
                break
        
        if not node:
            return
        
        # Get full document details
        try:
            doc = get_document(str(self.selected_node_id))
            if not doc:
                return
            
            # Build details text
            details = Text()
            details.append(f"Document #{doc['id']}\n", style="bold cyan")
            details.append(f"\n{doc['title']}\n", style="bold")
            
            if node.get('tags'):
                details.append(f"\nTags: {', '.join(node['tags'])}\n", style="dim")
            
            if doc.get('project'):
                details.append(f"Project: {doc['project']}\n", style="dim")
            
            details.append(f"Access Count: {doc.get('access_count', 0)}\n", style="dim")
            
            # Show connections
            edges = [e for e in self.graph_data['edges'] 
                    if e['source'] == self.selected_node_id or e['target'] == self.selected_node_id]
            
            if edges:
                details.append(f"\nConnections ({len(edges)}):\n", style="bold")
                
                # Get connected nodes
                connected = set()
                for edge in edges:
                    other_id = edge['target'] if edge['source'] == self.selected_node_id else edge['source']
                    connected.add(other_id)
                
                # Show top 5 connections
                node_map = {n['id']: n for n in self.graph_data['nodes']}
                for i, other_id in enumerate(list(connected)[:5]):
                    other = node_map.get(other_id)
                    if other:
                        details.append(f"  → {other['title'][:40]}...\n", style="green")
                
                if len(connected) > 5:
                    details.append(f"  ... and {len(connected) - 5} more\n", style="dim")
            
            # Show content preview
            if doc.get('content'):
                details.append("\nContent Preview:\n", style="bold")
                preview = doc['content'][:200].replace('\n', ' ')
                if len(doc['content']) > 200:
                    preview += "..."
                details.append(preview + "\n", style="dim")
            
            # Update the details panel
            self.query_one("#node-info", Static).update(details)
            
        except Exception as e:
            logger.error(f"Error updating node details: {e}")
    
    def action_move_left(self) -> None:
        """Move cursor left."""
        self.cursor_pos = (max(0, self.cursor_pos[0] - 2), self.cursor_pos[1])
        self._check_node_at_cursor()
    
    def action_move_right(self) -> None:
        """Move cursor right."""
        self.cursor_pos = (min(119, self.cursor_pos[0] + 2), self.cursor_pos[1])
        self._check_node_at_cursor()
    
    def action_move_up(self) -> None:
        """Move cursor up."""
        self.cursor_pos = (self.cursor_pos[0], max(0, self.cursor_pos[1] - 1))
        self._check_node_at_cursor()
    
    def action_move_down(self) -> None:
        """Move cursor down."""
        self.cursor_pos = (self.cursor_pos[0], min(49, self.cursor_pos[1] + 1))
        self._check_node_at_cursor()
    
    def _check_node_at_cursor(self) -> None:
        """Check if there's a node at cursor position and select it."""
        canvas = self.query_one("#graph-canvas", GraphCanvas)
        node_id = canvas.get_node_at_position(self.cursor_pos[0], self.cursor_pos[1])
        
        if node_id and node_id != self.selected_node_id:
            self.selected_node_id = node_id
            canvas.select_node(node_id)
            self.update_node_details()
    
    def action_select_node(self) -> None:
        """Open selected node in document viewer."""
        if self.selected_node_id:
            # Emit event to open document
            self.post_message(self.NodeSelected(self.selected_node_id))
    
    def action_center_selected(self) -> None:
        """Center view on selected node."""
        if self.selected_node_id:
            canvas = self.query_one("#graph-canvas", GraphCanvas)
            pos = canvas.node_positions.get(self.selected_node_id)
            if pos:
                self.cursor_pos = pos
                canvas.refresh()
    
    def action_refresh(self) -> None:
        """Refresh graph data."""
        self.load_graph()
        self.notify("Graph refreshed")
    
    def action_quit(self) -> None:
        """Return to main browser."""
        self.post_message(self.GraphExit())
    
    def action_show_help(self) -> None:
        """Show help for graph navigation."""
        help_text = """
Graph Navigation:
  h/j/k/l - Move cursor
  Enter   - View document  
  Space   - Center on selected
  r       - Refresh graph
  q       - Back to browser
  ?       - This help

Node Symbols:
  ◎ - Gameplan
  ✗ - Bug
  ★ - Feature
  ▶ - Active
  ✓ - Done
  ● - Other
        """
        self.notify(help_text.strip(), title="Graph Help", timeout=10)
    
    class NodeSelected(Widget.Message):
        """Message when a node is selected."""
        def __init__(self, node_id: int) -> None:
            self.node_id = node_id
            super().__init__()
    
    class GraphExit(Widget.Message):
        """Message to exit graph view."""
        pass