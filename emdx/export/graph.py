"""
Graph export functionality for EMDX.
Supports multiple output formats: GraphML, DOT, JSON, and Mermaid.
"""

import json
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path


class GraphExporter:
    """Export knowledge graphs in various formats."""
    
    def __init__(self):
        pass
    
    def export(
        self,
        graph_data: Dict[str, Any],
        format: str = "json",
        output_path: Optional[str] = None
    ) -> str:
        """
        Export graph data in specified format.
        
        Args:
            graph_data: Graph data from GraphAnalyzer
            format: Output format (json, graphml, dot, mermaid)
            output_path: Optional file path to save output
            
        Returns:
            Exported graph as string
        """
        format = format.lower()
        
        if format == "json":
            output = self._export_json(graph_data)
        elif format == "graphml":
            output = self._export_graphml(graph_data)
        elif format == "dot":
            output = self._export_dot(graph_data)
        elif format == "mermaid":
            output = self._export_mermaid(graph_data)
        elif format == "d3":
            output = self._export_d3(graph_data)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        # Save to file if path provided
        if output_path:
            Path(output_path).write_text(output)
        
        return output
    
    def _export_json(self, graph_data: Dict[str, Any]) -> str:
        """Export as standard JSON format."""
        return json.dumps(graph_data, indent=2, default=str)
    
    def _export_d3(self, graph_data: Dict[str, Any]) -> str:
        """Export in D3.js force layout format."""
        # Transform to D3's expected format
        d3_data = {
            "nodes": [
                {
                    "id": node["id"],
                    "name": node["title"],
                    "group": node["project"] or "default",
                    "tags": node["tags"],
                    "value": node["access_count"]
                }
                for node in graph_data["nodes"]
            ],
            "links": [
                {
                    "source": edge["source"],
                    "target": edge["target"],
                    "value": edge["weight"],
                    "type": edge["type"]
                }
                for edge in graph_data["edges"]
            ]
        }
        
        return json.dumps(d3_data, indent=2)
    
    def _export_graphml(self, graph_data: Dict[str, Any]) -> str:
        """Export as GraphML format (XML-based)."""
        # Create root element
        graphml = ET.Element("graphml", {
            "xmlns": "http://graphml.graphdrawing.org/xmlns",
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": "http://graphml.graphdrawing.org/xmlns "
                                  "http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd"
        })
        
        # Define attributes
        self._add_graphml_key(graphml, "title", "node", "string")
        self._add_graphml_key(graphml, "project", "node", "string")
        self._add_graphml_key(graphml, "tags", "node", "string")
        self._add_graphml_key(graphml, "access_count", "node", "int")
        self._add_graphml_key(graphml, "created_at", "node", "string")
        self._add_graphml_key(graphml, "weight", "edge", "double")
        self._add_graphml_key(graphml, "type", "edge", "string")
        
        # Create graph
        graph = ET.SubElement(graphml, "graph", {
            "id": "G",
            "edgedefault": "undirected"
        })
        
        # Add nodes
        for node in graph_data["nodes"]:
            n = ET.SubElement(graph, "node", {"id": str(node["id"])})
            self._add_graphml_data(n, "title", node["title"])
            self._add_graphml_data(n, "project", node.get("project", ""))
            self._add_graphml_data(n, "tags", ",".join(node.get("tags", [])))
            self._add_graphml_data(n, "access_count", str(node.get("access_count", 0)))
            self._add_graphml_data(n, "created_at", node.get("created_at", ""))
        
        # Add edges
        edge_id = 0
        for edge in graph_data["edges"]:
            e = ET.SubElement(graph, "edge", {
                "id": f"e{edge_id}",
                "source": str(edge["source"]),
                "target": str(edge["target"])
            })
            self._add_graphml_data(e, "weight", str(edge["weight"]))
            self._add_graphml_data(e, "type", edge.get("type", ""))
            edge_id += 1
        
        # Convert to string
        return ET.tostring(graphml, encoding="unicode", method="xml")
    
    def _add_graphml_key(self, root: ET.Element, id: str, for_type: str, attr_type: str):
        """Add key definition to GraphML."""
        ET.SubElement(root, "key", {
            "id": id,
            "for": for_type,
            "attr.name": id,
            "attr.type": attr_type
        })
    
    def _add_graphml_data(self, parent: ET.Element, key: str, value: str):
        """Add data element to GraphML node or edge."""
        data = ET.SubElement(parent, "data", {"key": key})
        data.text = value
    
    def _export_dot(self, graph_data: Dict[str, Any]) -> str:
        """Export as Graphviz DOT format."""
        lines = ["digraph KnowledgeGraph {"]
        lines.append('    rankdir=LR;')
        lines.append('    node [shape=box, style=rounded];')
        lines.append('')
        
        # Add nodes with attributes
        for node in graph_data["nodes"]:
            node_id = node["id"]
            title = self._escape_dot_label(node["title"])
            tags = ", ".join(node.get("tags", []))
            
            # Create label with title and tags
            label = f"{title}"
            if tags:
                label += f"\\n[{tags}]"
            
            # Color by project
            color = self._get_project_color(node.get("project"))
            
            lines.append(f'    {node_id} [label="{label}", fillcolor="{color}", style="rounded,filled"];')
        
        lines.append('')
        
        # Add edges
        for edge in graph_data["edges"]:
            source = edge["source"]
            target = edge["target"]
            weight = edge["weight"]
            edge_type = edge.get("type", "")
            
            # Style based on weight
            if weight >= 70:
                style = "bold"
                color = "black"
            elif weight >= 40:
                style = "solid"
                color = "gray40"
            else:
                style = "dashed"
                color = "gray70"
            
            lines.append(f'    {source} -> {target} [weight={weight:.1f}, '
                        f'style={style}, color={color}, label="{weight:.0f}"];')
        
        lines.append("}")
        
        return "\n".join(lines)
    
    def _export_mermaid(self, graph_data: Dict[str, Any]) -> str:
        """Export as Mermaid diagram syntax."""
        lines = ["graph LR"]
        
        # Add nodes
        for node in graph_data["nodes"]:
            node_id = node["id"]
            title = self._escape_mermaid_label(node["title"])
            tags = node.get("tags", [])
            
            # Determine node shape based on tags
            if "🎯" in tags or "gameplan" in tags:
                shape_start, shape_end = "((", "))"  # Circle for gameplans
            elif "🐛" in tags or "bug" in tags:
                shape_start, shape_end = "{{", "}}"  # Hexagon for bugs
            elif "✨" in tags or "feature" in tags:
                shape_start, shape_end = "[", "]"  # Rectangle for features
            else:
                shape_start, shape_end = "(", ")"  # Rounded rectangle default
            
            lines.append(f"    {node_id}{shape_start}{title}{shape_end}")
        
        lines.append("")
        
        # Add edges with relationship labels
        for edge in graph_data["edges"]:
            source = edge["source"]
            target = edge["target"]
            weight = edge["weight"]
            edge_type = edge.get("type", "related")
            
            # Simplify edge type for display
            edge_label = edge_type.replace("_", " ").title()
            if weight >= 70:
                arrow = "==>"
            elif weight >= 40:
                arrow = "-->"
            else:
                arrow = "-.->"
            
            lines.append(f"    {source} {arrow}|{edge_label}| {target}")
        
        # Add styling
        lines.extend([
            "",
            "    %% Styling",
            "    classDef gameplan fill:#f96,stroke:#333,stroke-width:2px;",
            "    classDef bug fill:#f66,stroke:#333,stroke-width:2px;",
            "    classDef feature fill:#6f6,stroke:#333,stroke-width:2px;",
            "    classDef default fill:#99f,stroke:#333,stroke-width:2px;"
        ])
        
        # Apply styles based on tags
        gameplan_nodes = []
        bug_nodes = []
        feature_nodes = []
        
        for node in graph_data["nodes"]:
            tags = node.get("tags", [])
            if "🎯" in tags or "gameplan" in tags:
                gameplan_nodes.append(str(node["id"]))
            elif "🐛" in tags or "bug" in tags:
                bug_nodes.append(str(node["id"]))
            elif "✨" in tags or "feature" in tags:
                feature_nodes.append(str(node["id"]))
        
        if gameplan_nodes:
            lines.append(f"    class {','.join(gameplan_nodes)} gameplan;")
        if bug_nodes:
            lines.append(f"    class {','.join(bug_nodes)} bug;")
        if feature_nodes:
            lines.append(f"    class {','.join(feature_nodes)} feature;")
        
        return "\n".join(lines)
    
    def _escape_dot_label(self, text: str) -> str:
        """Escape text for DOT format labels."""
        # Escape special characters
        text = text.replace('"', '\\"')
        text = text.replace('\n', '\\n')
        text = text.replace('\r', '\\r')
        # Limit length
        if len(text) > 50:
            text = text[:47] + "..."
        return text
    
    def _escape_mermaid_label(self, text: str) -> str:
        """Escape text for Mermaid labels."""
        # Remove special characters that break Mermaid
        text = text.replace('"', "'")
        text = text.replace('(', '[')
        text = text.replace(')', ']')
        text = text.replace('{', '[')
        text = text.replace('}', ']')
        text = text.replace('|', '/')
        text = text.replace('\n', ' ')
        # Limit length
        if len(text) > 40:
            text = text[:37] + "..."
        return text
    
    def _get_project_color(self, project: Optional[str]) -> str:
        """Get consistent color for project."""
        if not project:
            return "#e0e0e0"
        
        # Simple hash-based color assignment
        colors = [
            "#ffcccc", "#ccffcc", "#ccccff", "#ffffcc",
            "#ffccff", "#ccffff", "#ffd9b3", "#d9b3ff",
            "#b3ffd9", "#ffb3d9"
        ]
        
        hash_val = sum(ord(c) for c in project)
        return colors[hash_val % len(colors)]
    
    def generate_html_visualization(
        self,
        graph_data: Dict[str, Any],
        title: str = "EMDX Knowledge Graph"
    ) -> str:
        """
        Generate a complete HTML page with embedded D3.js visualization.
        """
        d3_data = self._export_d3(graph_data)
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }}
        #header {{
            background-color: #333;
            color: white;
            padding: 1rem;
            text-align: center;
        }}
        #controls {{
            padding: 1rem;
            background-color: white;
            border-bottom: 1px solid #ddd;
        }}
        #graph {{
            width: 100%;
            height: calc(100vh - 150px);
        }}
        .node {{
            cursor: pointer;
        }}
        .node circle {{
            stroke: #333;
            stroke-width: 1.5px;
        }}
        .node text {{
            font: 12px sans-serif;
            pointer-events: none;
        }}
        .link {{
            fill: none;
            stroke: #999;
            stroke-opacity: 0.6;
        }}
        .tooltip {{
            position: absolute;
            text-align: left;
            padding: 10px;
            font: 12px sans-serif;
            background: rgba(0, 0, 0, 0.8);
            color: white;
            border-radius: 5px;
            pointer-events: none;
            opacity: 0;
        }}
        #info {{
            position: absolute;
            top: 120px;
            right: 20px;
            width: 300px;
            background: white;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }}
    </style>
</head>
<body>
    <div id="header">
        <h1>{title}</h1>
        <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    <div id="controls">
        <label>Link Distance: <input type="range" id="distance" min="50" max="300" value="100"></label>
        <label>Charge Strength: <input type="range" id="charge" min="-500" max="0" value="-200"></label>
        <button onclick="resetZoom()">Reset Zoom</button>
    </div>
    <div id="graph"></div>
    <div id="info" style="display: none;">
        <h3>Node Details</h3>
        <div id="node-details"></div>
    </div>
    <div class="tooltip"></div>

    <script>
        const data = {d3_data};
        
        const width = document.getElementById('graph').clientWidth;
        const height = document.getElementById('graph').clientHeight;
        
        const color = d3.scaleOrdinal(d3.schemeCategory10);
        
        const svg = d3.select("#graph")
            .append("svg")
            .attr("width", width)
            .attr("height", height);
        
        const g = svg.append("g");
        
        const zoom = d3.zoom()
            .scaleExtent([0.1, 10])
            .on("zoom", (event) => {{
                g.attr("transform", event.transform);
            }});
        
        svg.call(zoom);
        
        const simulation = d3.forceSimulation(data.nodes)
            .force("link", d3.forceLink(data.links).id(d => d.id).distance(100))
            .force("charge", d3.forceManyBody().strength(-200))
            .force("center", d3.forceCenter(width / 2, height / 2));
        
        const link = g.append("g")
            .attr("class", "links")
            .selectAll("line")
            .data(data.links)
            .enter().append("line")
            .attr("class", "link")
            .attr("stroke-width", d => Math.sqrt(d.value / 10));
        
        const node = g.append("g")
            .attr("class", "nodes")
            .selectAll("g")
            .data(data.nodes)
            .enter().append("g")
            .attr("class", "node")
            .call(d3.drag()
                .on("start", dragstarted)
                .on("drag", dragged)
                .on("end", dragended));
        
        node.append("circle")
            .attr("r", d => 5 + Math.sqrt(d.value))
            .attr("fill", d => color(d.group));
        
        node.append("text")
            .attr("dx", 12)
            .attr("dy", ".35em")
            .text(d => d.name);
        
        const tooltip = d3.select(".tooltip");
        
        node.on("mouseover", function(event, d) {{
            tooltip.transition().duration(200).style("opacity", .9);
            tooltip.html(`<strong>${{d.name}}</strong><br/>
                         Project: ${{d.group}}<br/>
                         Tags: ${{d.tags.join(", ")}}<br/>
                         Access Count: ${{d.value}}`)
                .style("left", (event.pageX + 10) + "px")
                .style("top", (event.pageY - 28) + "px");
        }})
        .on("mouseout", function(d) {{
            tooltip.transition().duration(500).style("opacity", 0);
        }})
        .on("click", function(event, d) {{
            showNodeDetails(d);
        }});
        
        simulation.on("tick", () => {{
            link
                .attr("x1", d => d.source.x)
                .attr("y1", d => d.source.y)
                .attr("x2", d => d.target.x)
                .attr("y2", d => d.target.y);
            
            node.attr("transform", d => `translate(${{d.x}},${{d.y}})`);
        }});
        
        function dragstarted(event, d) {{
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }}
        
        function dragged(event, d) {{
            d.fx = event.x;
            d.fy = event.y;
        }}
        
        function dragended(event, d) {{
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }}
        
        function showNodeDetails(node) {{
            const info = document.getElementById('info');
            const details = document.getElementById('node-details');
            
            details.innerHTML = `
                <p><strong>ID:</strong> ${{node.id}}</p>
                <p><strong>Title:</strong> ${{node.name}}</p>
                <p><strong>Project:</strong> ${{node.group}}</p>
                <p><strong>Tags:</strong> ${{node.tags.join(", ")}}</p>
                <p><strong>Access Count:</strong> ${{node.value}}</p>
                <p><strong>Connections:</strong> ${{
                    data.links.filter(l => l.source.id === node.id || l.target.id === node.id).length
                }}</p>
            `;
            
            info.style.display = 'block';
        }}
        
        function resetZoom() {{
            svg.transition().duration(750).call(
                zoom.transform,
                d3.zoomIdentity,
                d3.zoomTransform(svg.node()).invert([width / 2, height / 2])
            );
        }}
        
        // Update simulation parameters
        document.getElementById('distance').addEventListener('input', function(e) {{
            simulation.force("link").distance(+e.target.value);
            simulation.alpha(0.3).restart();
        }});
        
        document.getElementById('charge').addEventListener('input', function(e) {{
            simulation.force("charge").strength(+e.target.value);
            simulation.alpha(0.3).restart();
        }});
    </script>
</body>
</html>"""
        
        return html