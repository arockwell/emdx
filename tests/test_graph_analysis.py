"""
Tests for graph analysis functionality.
"""

import pytest
from datetime import datetime, timedelta
import sqlite3

from emdx.analysis.graph import GraphAnalyzer
from emdx.models.documents import save_document
from emdx.models.tags import add_tags_to_document
from emdx.database import db
import os


@pytest.fixture(autouse=True)
def setup_db_for_tests(temp_db_file):
    """Set up database connection for all tests."""
    # Set the database path for the models to use
    os.environ['EMDX_DB_PATH'] = temp_db_file.db_path
    yield
    # Clean up
    if 'EMDX_DB_PATH' in os.environ:
        del os.environ['EMDX_DB_PATH']


class TestGraphAnalyzer:
    """Test the GraphAnalyzer class."""
    
    def test_empty_graph(self, temp_db_file):
        """Test graph analysis with no documents."""
        analyzer = GraphAnalyzer(temp_db_file.db_path)
        graph_data = analyzer.get_document_graph()
        
        assert graph_data['nodes'] == []
        assert graph_data['edges'] == []
        assert graph_data['metadata']['node_count'] == 0
        assert graph_data['metadata']['edge_count'] == 0
    
    def test_single_document(self, temp_db_file):
        """Test graph with a single document."""
        # Create a document
        doc_id = save_document("Test Doc", "Test content", tags=["test"])
        
        analyzer = GraphAnalyzer(temp_db_file.db_path)
        graph_data = analyzer.get_document_graph()
        
        assert len(graph_data['nodes']) == 1
        assert graph_data['nodes'][0]['id'] == doc_id
        assert graph_data['nodes'][0]['title'] == "Test Doc"
        assert graph_data['nodes'][0]['tags'] == ["test"]
        assert len(graph_data['edges']) == 0
    
    def test_tag_relationships(self, temp_db_file):
        """Test documents connected by shared tags."""
        # Create documents with shared tags
        doc1 = save_document("Doc 1", "Content 1", tags=["python", "testing"])
        doc2 = save_document("Doc 2", "Content 2", tags=["python", "development"])
        doc3 = save_document("Doc 3", "Content 3", tags=["testing", "qa"])
        doc4 = save_document("Doc 4", "Content 4", tags=["unrelated"])
        
        analyzer = GraphAnalyzer(temp_db_file.db_path)
        graph_data = analyzer.get_document_graph(min_similarity=10.0)
        
        # Should have 4 nodes
        assert len(graph_data['nodes']) == 4
        
        # Should have edges between docs with shared tags
        edges = graph_data['edges']
        edge_pairs = {(e['source'], e['target']) for e in edges}
        
        # Doc1 and Doc2 share "python"
        assert (doc1, doc2) in edge_pairs or (doc2, doc1) in edge_pairs
        
        # Doc1 and Doc3 share "testing"
        assert (doc1, doc3) in edge_pairs or (doc3, doc1) in edge_pairs
        
        # Doc4 should not be connected to others
        doc4_edges = [e for e in edges if doc4 in (e['source'], e['target'])]
        assert len(doc4_edges) == 0
    
    def test_temporal_proximity(self, temp_db_file):
        """Test temporal proximity scoring."""
        # Create documents at different times
        now = datetime.now()
        
        # Manually insert with specific timestamps
        conn = sqlite3.connect(temp_db_file.db_path)
        cursor = conn.cursor()
        
        # Same day documents
        cursor.execute(
            "INSERT INTO documents (title, content, created_at) VALUES (?, ?, ?)",
            ("Same Day 1", "Content", now.isoformat())
        )
        doc1 = cursor.lastrowid
        
        cursor.execute(
            "INSERT INTO documents (title, content, created_at) VALUES (?, ?, ?)",
            ("Same Day 2", "Content", now.isoformat())
        )
        doc2 = cursor.lastrowid
        
        # Week apart
        week_ago = now - timedelta(days=7)
        cursor.execute(
            "INSERT INTO documents (title, content, created_at) VALUES (?, ?, ?)",
            ("Week Old", "Content", week_ago.isoformat())
        )
        doc3 = cursor.lastrowid
        
        # Month apart
        month_ago = now - timedelta(days=30)
        cursor.execute(
            "INSERT INTO documents (title, content, created_at) VALUES (?, ?, ?)",
            ("Month Old", "Content", month_ago.isoformat())
        )
        doc4 = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        analyzer = GraphAnalyzer(temp_db_file.db_path)
        graph_data = analyzer.get_document_graph(min_similarity=5.0)
        
        # Find edge weights
        edges = {(e['source'], e['target']): e['weight'] for e in graph_data['edges']}
        
        # Same day should have higher weight than week apart
        same_day_weight = edges.get((doc1, doc2), 0) or edges.get((doc2, doc1), 0)
        week_weight = edges.get((doc1, doc3), 0) or edges.get((doc3, doc1), 0)
        
        assert same_day_weight > week_weight
    
    def test_project_filtering(self, temp_db_file):
        """Test filtering by project."""
        # Create documents in different projects
        doc1 = save_document("Project A Doc 1", "Content", project="project_a")
        doc2 = save_document("Project A Doc 2", "Content", project="project_a")
        doc3 = save_document("Project B Doc", "Content", project="project_b")
        
        analyzer = GraphAnalyzer(temp_db_file.db_path)
        
        # Filter by project_a
        graph_data = analyzer.get_document_graph(project="project_a")
        
        assert len(graph_data['nodes']) == 2
        node_ids = {n['id'] for n in graph_data['nodes']}
        assert doc1 in node_ids
        assert doc2 in node_ids
        assert doc3 not in node_ids
    
    def test_tag_filtering(self, temp_db_file):
        """Test filtering by tags."""
        # Create documents with different tags
        doc1 = save_document("Python Doc", "Content", tags=["python"])
        doc2 = save_document("Python Test", "Content", tags=["python", "test"])
        doc3 = save_document("Java Doc", "Content", tags=["java"])
        
        analyzer = GraphAnalyzer(temp_db_file.db_path)
        
        # Filter by python tag
        graph_data = analyzer.get_document_graph(tag_filter=["python"])
        
        assert len(graph_data['nodes']) == 2
        node_ids = {n['id'] for n in graph_data['nodes']}
        assert doc1 in node_ids
        assert doc2 in node_ids
        assert doc3 not in node_ids
    
    def test_graph_metrics(self, temp_db_file):
        """Test calculation of graph metrics."""
        # Create a small connected graph
        doc1 = save_document("Hub", "Central document", tags=["core"])
        doc2 = save_document("Spoke 1", "Connected to hub", tags=["core", "feature1"])
        doc3 = save_document("Spoke 2", "Connected to hub", tags=["core", "feature2"])
        doc4 = save_document("Orphan", "Isolated document", tags=["other"])
        
        analyzer = GraphAnalyzer(temp_db_file.db_path)
        graph_data = analyzer.get_document_graph(min_similarity=10.0)
        
        metrics = graph_data['metadata']['metrics']
        
        # Check basic metrics
        assert metrics['orphan_count'] >= 1  # At least doc4
        assert metrics['density'] > 0  # Some connections exist
        assert len(metrics['connected_components']) >= 2  # At least 2 components
        
        # Check centrality
        centrality = metrics['centrality']
        assert doc1 in centrality  # Hub should have centrality
        
        # Hub should have higher centrality than spokes
        if doc2 in centrality and doc3 in centrality:
            hub_centrality = centrality[doc1]['neighbor_count']
            spoke1_centrality = centrality[doc2]['neighbor_count']
            spoke2_centrality = centrality[doc3]['neighbor_count']
            
            assert hub_centrality >= spoke1_centrality
            assert hub_centrality >= spoke2_centrality
    
    def test_minimum_similarity_threshold(self, temp_db_file):
        """Test minimum similarity threshold filtering."""
        # Create weakly connected documents
        doc1 = save_document("Doc 1", "Some content here", tags=["tag1"])
        doc2 = save_document("Doc 2", "Different content", tags=["tag2"])
        
        analyzer = GraphAnalyzer(temp_db_file.db_path)
        
        # High threshold - no edges
        graph_data = analyzer.get_document_graph(min_similarity=80.0)
        assert len(graph_data['edges']) == 0
        
        # Low threshold - might have edges
        graph_data = analyzer.get_document_graph(min_similarity=0.0)
        # May or may not have edges depending on content similarity
    
    def test_orphan_filtering(self, temp_db_file):
        """Test include_orphans parameter."""
        # Create connected and orphan documents
        doc1 = save_document("Connected 1", "Content", tags=["shared"])
        doc2 = save_document("Connected 2", "Content", tags=["shared"])
        doc3 = save_document("Orphan", "Content", tags=["unique"])
        
        analyzer = GraphAnalyzer(temp_db_file.db_path)
        
        # Include orphans
        graph_data = analyzer.get_document_graph(
            min_similarity=10.0,
            include_orphans=True
        )
        assert len(graph_data['nodes']) == 3
        
        # Exclude orphans
        graph_data = analyzer.get_document_graph(
            min_similarity=10.0,
            include_orphans=False
        )
        # Should only have connected documents
        node_ids = {n['id'] for n in graph_data['nodes']}
        assert doc1 in node_ids
        assert doc2 in node_ids
        assert doc3 not in node_ids
    
    def test_cross_references(self, temp_db_file):
        """Test detection of cross-references between documents."""
        # Create documents with cross-references
        doc1 = save_document("Doc 1", "This is the first document")
        doc2 = save_document("Doc 2", f"This references doc {doc1}")
        doc3 = save_document("Doc 3", f"See document #{doc1} for details")
        
        analyzer = GraphAnalyzer(temp_db_file.db_path)
        graph_data = analyzer.get_document_graph(min_similarity=0.0)
        
        # Should have edges due to cross-references
        edges = graph_data['edges']
        edge_pairs = {(e['source'], e['target']) for e in edges}
        
        # Doc2 references Doc1
        assert (doc2, doc1) in edge_pairs or (doc1, doc2) in edge_pairs
        
        # Doc3 references Doc1
        assert (doc3, doc1) in edge_pairs or (doc1, doc3) in edge_pairs
    
    def test_node_recommendations(self, temp_db_file):
        """Test getting recommendations for a specific node."""
        # Create related documents
        doc1 = save_document("Python Tutorial", "Learn Python", tags=["python", "tutorial"])
        doc2 = save_document("Python Advanced", "Advanced Python", tags=["python", "advanced"])
        doc3 = save_document("Django Tutorial", "Learn Django", tags=["python", "django", "tutorial"])
        doc4 = save_document("Java Tutorial", "Learn Java", tags=["java", "tutorial"])
        
        analyzer = GraphAnalyzer(temp_db_file.db_path)
        
        # Get recommendations for doc1
        recommendations = analyzer.get_node_recommendations(doc1, limit=5)
        
        assert len(recommendations) > 0
        
        # Should recommend other Python or tutorial documents
        rec_ids = [r['id'] for r in recommendations]
        assert doc2 in rec_ids or doc3 in rec_ids
        
        # Each recommendation should have required fields
        for rec in recommendations:
            assert 'id' in rec
            assert 'title' in rec
            assert 'similarity_score' in rec
            assert 'reason' in rec
            assert rec['similarity_score'] > 0