"""
Tests for graph export functionality.
"""

import pytest
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from emdx.export.graph import GraphExporter
from emdx.models.documents import save_document


@pytest.fixture
def sample_graph_data():
    """Create sample graph data for testing exports."""
    return {
        'nodes': [
            {
                'id': 1,
                'title': 'Node 1',
                'project': 'project_a',
                'tags': ['python', 'test'],
                'access_count': 5,
                'created_at': '2024-01-01T10:00:00',
                'content_length': 100
            },
            {
                'id': 2,
                'title': 'Node 2',
                'project': 'project_a',
                'tags': ['python', 'docs'],
                'access_count': 3,
                'created_at': '2024-01-02T10:00:00',
                'content_length': 200
            },
            {
                'id': 3,
                'title': 'Node 3',
                'project': None,
                'tags': [],
                'access_count': 1,
                'created_at': '2024-01-03T10:00:00',
                'content_length': 50
            }
        ],
        'edges': [
            {
                'source': 1,
                'target': 2,
                'weight': 75.5,
                'type': 'strong_tag_similarity'
            },
            {
                'source': 2,
                'target': 3,
                'weight': 25.0,
                'type': 'weak_relationship'
            }
        ],
        'metadata': {
            'node_count': 3,
            'edge_count': 2,
            'metrics': {
                'density': 0.333,
                'clustering_coefficient': 0.0,
                'connected_components': [[1, 2, 3]],
                'orphan_count': 0,
                'bridge_nodes': [2],
                'centrality': {
                    1: {'degree': 0.5, 'weighted_degree': 0.378, 'neighbor_count': 1},
                    2: {'degree': 1.0, 'weighted_degree': 0.503, 'neighbor_count': 2},
                    3: {'degree': 0.5, 'weighted_degree': 0.125, 'neighbor_count': 1}
                }
            },
            'generated_at': '2024-01-10T15:30:00'
        }
    }


class TestGraphExporter:
    """Test the GraphExporter class."""
    
    def test_export_json(self, sample_graph_data):
        """Test JSON export format."""
        exporter = GraphExporter()
        output = exporter.export(sample_graph_data, format='json')
        
        # Should be valid JSON
        parsed = json.loads(output)
        
        # Should contain all data
        assert len(parsed['nodes']) == 3
        assert len(parsed['edges']) == 2
        assert parsed['metadata']['node_count'] == 3
    
    def test_export_d3(self, sample_graph_data):
        """Test D3.js export format."""
        exporter = GraphExporter()
        output = exporter.export(sample_graph_data, format='d3')
        
        # Should be valid JSON
        parsed = json.loads(output)
        
        # Check D3 format structure
        assert 'nodes' in parsed
        assert 'links' in parsed
        
        # Nodes should have D3 fields
        node = parsed['nodes'][0]
        assert 'id' in node
        assert 'name' in node
        assert 'group' in node
        assert 'value' in node
        
        # Links should have D3 fields
        link = parsed['links'][0]
        assert 'source' in link
        assert 'target' in link
        assert 'value' in link
    
    def test_export_graphml(self, sample_graph_data):
        """Test GraphML export format."""
        exporter = GraphExporter()
        output = exporter.export(sample_graph_data, format='graphml')
        
        # Should be valid XML
        root = ET.fromstring(output)
        
        # Check GraphML structure (handle namespace)
        assert root.tag.endswith('graphml')
        
        # Find graph element
        graph = root.find('.//{http://graphml.graphdrawing.org/xmlns}graph')
        assert graph is not None
        
        # Count nodes and edges
        nodes = graph.findall('.//{http://graphml.graphdrawing.org/xmlns}node')
        edges = graph.findall('.//{http://graphml.graphdrawing.org/xmlns}edge')
        
        assert len(nodes) == 3
        assert len(edges) == 2
    
    def test_export_dot(self, sample_graph_data):
        """Test Graphviz DOT export format."""
        exporter = GraphExporter()
        output = exporter.export(sample_graph_data, format='dot')
        
        # Check DOT format structure
        assert output.startswith('digraph KnowledgeGraph {')
        assert output.endswith('}')
        
        # Should contain nodes
        assert '1 [label=' in output
        assert '2 [label=' in output
        assert '3 [label=' in output
        
        # Should contain edges
        assert '1 -> 2' in output
        assert '2 -> 3' in output
    
    def test_export_mermaid(self, sample_graph_data):
        """Test Mermaid export format."""
        exporter = GraphExporter()
        output = exporter.export(sample_graph_data, format='mermaid')
        
        # Check Mermaid format structure
        assert output.startswith('graph LR')
        
        # Should contain nodes
        assert '1(' in output or '1[' in output
        assert '2(' in output or '2[' in output
        assert '3(' in output or '3[' in output
        
        # Should contain edges with labels
        assert '1 ' in output and ' 2' in output
        assert '2 ' in output and ' 3' in output
        assert '|' in output  # Edge labels
    
    def test_export_to_file(self, sample_graph_data, tmp_path):
        """Test exporting to a file."""
        exporter = GraphExporter()
        output_path = tmp_path / "graph.json"
        
        result = exporter.export(
            sample_graph_data,
            format='json',
            output_path=str(output_path)
        )
        
        # File should exist
        assert output_path.exists()
        
        # Content should be valid
        with open(output_path) as f:
            data = json.load(f)
            assert len(data['nodes']) == 3
    
    def test_html_visualization(self, sample_graph_data):
        """Test HTML visualization generation."""
        exporter = GraphExporter()
        html = exporter.generate_html_visualization(
            sample_graph_data,
            title="Test Graph"
        )
        
        # Should be valid HTML
        assert '<!DOCTYPE html>' in html
        assert '<html' in html
        assert '</html>' in html
        
        # Should contain title
        assert '<title>Test Graph</title>' in html
        
        # Should contain D3.js script
        assert 'd3js.org' in html
        assert 'const data =' in html
        
        # Should contain controls
        assert 'id="distance"' in html
        assert 'id="charge"' in html
        assert 'resetZoom()' in html
    
    def test_unsupported_format(self, sample_graph_data):
        """Test handling of unsupported format."""
        exporter = GraphExporter()
        
        with pytest.raises(ValueError, match="Unsupported format"):
            exporter.export(sample_graph_data, format='invalid')
    
    def test_empty_graph(self):
        """Test exporting empty graph."""
        empty_graph = {
            'nodes': [],
            'edges': [],
            'metadata': {
                'node_count': 0,
                'edge_count': 0,
                'metrics': {},
                'generated_at': '2024-01-10T15:30:00'
            }
        }
        
        exporter = GraphExporter()
        
        # All formats should handle empty graph
        for format in ['json', 'd3', 'graphml', 'dot', 'mermaid']:
            output = exporter.export(empty_graph, format=format)
            assert output is not None
            assert len(output) > 0
    
    def test_special_characters_in_titles(self):
        """Test handling of special characters in node titles."""
        graph_data = {
            'nodes': [
                {
                    'id': 1,
                    'title': 'Node with "quotes"',
                    'project': None,
                    'tags': [],
                    'access_count': 0,
                    'created_at': '2024-01-01T10:00:00',
                    'content_length': 0
                },
                {
                    'id': 2,
                    'title': 'Node with <brackets> & symbols',
                    'project': None,
                    'tags': [],
                    'access_count': 0,
                    'created_at': '2024-01-01T10:00:00',
                    'content_length': 0
                }
            ],
            'edges': [],
            'metadata': {
                'node_count': 2,
                'edge_count': 0,
                'metrics': {},
                'generated_at': '2024-01-10T15:30:00'
            }
        }
        
        exporter = GraphExporter()
        
        # Test DOT format escaping
        dot_output = exporter.export(graph_data, format='dot')
        assert '\\"' in dot_output  # Quotes should be escaped
        
        # Test Mermaid format escaping
        mermaid_output = exporter.export(graph_data, format='mermaid')
        assert '"' not in mermaid_output  # Quotes should be replaced
        
        # Test XML format
        xml_output = exporter.export(graph_data, format='graphml')
        # Should be parseable
        root = ET.fromstring(xml_output)