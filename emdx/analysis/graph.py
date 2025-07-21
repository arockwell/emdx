"""
Knowledge graph analysis for EMDX.
Builds document relationships based on tags, content similarity, and temporal proximity.
"""

import sqlite3
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Set, Any, Optional
import math
import re
import difflib
from pathlib import Path

from ..config.settings import get_db_path


class GraphAnalyzer:
    """Analyzes document relationships and builds knowledge graphs."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_db_path()
        self._tag_weights_cache: Optional[Dict[str, float]] = None
    
    def get_document_graph(
        self,
        project: Optional[str] = None,
        tag_filter: Optional[List[str]] = None,
        min_similarity: float = 0.0,
        include_orphans: bool = True
    ) -> Dict[str, Any]:
        """
        Build a complete document graph with nodes and edges.
        
        Args:
            project: Filter by project
            tag_filter: Only include documents with these tags
            min_similarity: Minimum relationship score to include edge
            include_orphans: Include documents with no relationships
            
        Returns:
            Graph data structure with nodes and edges
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            # Get documents
            documents = self._get_filtered_documents(conn, project, tag_filter)
            if not documents:
                return {
                    "nodes": [], 
                    "edges": [], 
                    "metadata": {
                        'node_count': 0,
                        'edge_count': 0,
                        'metrics': {
                            'density': 0.0,
                            'clustering_coefficient': 0.0,
                            'connected_components': [],
                            'orphan_count': 0,
                            'bridge_nodes': [],
                            'centrality': {}
                        },
                        'generated_at': datetime.now().isoformat()
                    }
                }
            
            # Build graph
            nodes = []
            edges = []
            doc_map = {}
            
            # Create nodes
            for doc in documents:
                doc_id = doc['id']
                doc_map[doc_id] = doc
                nodes.append({
                    'id': doc_id,
                    'title': doc['title'],
                    'project': doc['project'],
                    'tags': doc['tags'].split(',') if doc['tags'] else [],
                    'access_count': doc['access_count'],
                    'created_at': doc['created_at'],
                    'content_length': len(doc['content'] or '')
                })
            
            # Calculate relationships and create edges
            relationships = self._calculate_all_relationships(documents)
            
            for (doc1_id, doc2_id), score in relationships.items():
                if score >= min_similarity:
                    edges.append({
                        'source': doc1_id,
                        'target': doc2_id,
                        'weight': score,
                        'type': self._classify_relationship(
                            doc_map[doc1_id], 
                            doc_map[doc2_id], 
                            score
                        )
                    })
            
            # Filter out orphans if requested
            if not include_orphans:
                connected_ids = set()
                for edge in edges:
                    connected_ids.add(edge['source'])
                    connected_ids.add(edge['target'])
                nodes = [n for n in nodes if n['id'] in connected_ids]
            
            # Calculate graph metrics
            metrics = self._calculate_graph_metrics(nodes, edges)
            
            return {
                'nodes': nodes,
                'edges': edges,
                'metadata': {
                    'node_count': len(nodes),
                    'edge_count': len(edges),
                    'metrics': metrics,
                    'generated_at': datetime.now().isoformat()
                }
            }
            
        finally:
            conn.close()
    
    def _get_filtered_documents(
        self, 
        conn: sqlite3.Connection,
        project: Optional[str] = None,
        tag_filter: Optional[List[str]] = None
    ) -> List[sqlite3.Row]:
        """Get documents filtered by project and tags."""
        query = """
            SELECT 
                d.id,
                d.title,
                d.content,
                d.project,
                d.created_at,
                d.updated_at,
                d.access_count,
                GROUP_CONCAT(t.name) as tags
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.document_id
            LEFT JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0
        """
        
        params = []
        
        if project:
            query += " AND d.project = ?"
            params.append(project)
        
        if tag_filter:
            # Documents must have at least one of the specified tags
            placeholders = ','.join(['?' for _ in tag_filter])
            query += f"""
                AND d.id IN (
                    SELECT DISTINCT document_id 
                    FROM document_tags dt
                    JOIN tags t ON dt.tag_id = t.id
                    WHERE t.name IN ({placeholders})
                )
            """
            params.extend(tag_filter)
        
        query += " GROUP BY d.id"
        
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()
    
    def _calculate_all_relationships(
        self, 
        documents: List[sqlite3.Row]
    ) -> Dict[Tuple[int, int], float]:
        """Calculate relationship scores between all document pairs."""
        relationships = {}
        doc_list = list(documents)
        
        # Pre-calculate tag weights
        self._calculate_tag_weights(documents)
        
        for i in range(len(doc_list)):
            for j in range(i + 1, len(doc_list)):
                doc1 = doc_list[i]
                doc2 = doc_list[j]
                
                score = self._calculate_relationship_score(doc1, doc2)
                
                if score > 0:
                    # Store bidirectional relationship
                    relationships[(doc1['id'], doc2['id'])] = score
                    relationships[(doc2['id'], doc1['id'])] = score
        
        return relationships
    
    def _calculate_relationship_score(
        self,
        doc1: sqlite3.Row,
        doc2: sqlite3.Row
    ) -> float:
        """
        Calculate relationship score between two documents.
        
        Factors:
        - Tag overlap (weighted by tag rarity)
        - Content similarity
        - Temporal proximity
        - Project match
        - Cross-references
        """
        score = 0.0
        
        # 1. Tag overlap score (0-40 points)
        tags1 = set(doc1['tags'].split(',')) if doc1['tags'] else set()
        tags2 = set(doc2['tags'].split(',')) if doc2['tags'] else set()
        
        if tags1 and tags2:
            common_tags = tags1 & tags2
            if common_tags:
                # Weight by tag rarity
                tag_score = sum(self._tag_weights_cache.get(tag, 1.0) 
                               for tag in common_tags)
                # Normalize by total possible score
                max_score = sum(self._tag_weights_cache.get(tag, 1.0) 
                               for tag in tags1 | tags2)
                if max_score > 0:
                    score += 40 * (tag_score / max_score)
        
        # 2. Content similarity (0-30 points)
        if doc1['content'] and doc2['content']:
            content_score = self._calculate_content_similarity(
                doc1['content'], 
                doc2['content']
            )
            score += 30 * content_score
        
        # 3. Temporal proximity (0-15 points)
        temporal_score = self._calculate_temporal_proximity(
            doc1['created_at'],
            doc2['created_at']
        )
        score += 15 * temporal_score
        
        # 4. Project match (0-10 points)
        if doc1['project'] and doc2['project'] and doc1['project'] == doc2['project']:
            score += 10
        
        # 5. Cross-references (0-5 points)
        if self._has_cross_reference(doc1, doc2):
            score += 5
        
        return min(score, 100.0)  # Cap at 100
    
    def _calculate_tag_weights(self, documents: List[sqlite3.Row]) -> None:
        """Calculate inverse document frequency weights for tags."""
        # Count tag occurrences
        tag_counts = Counter()
        total_docs = len(documents)
        
        for doc in documents:
            if doc['tags']:
                tags = set(doc['tags'].split(','))
                for tag in tags:
                    tag_counts[tag] += 1
        
        # Calculate IDF weights
        self._tag_weights_cache = {}
        for tag, count in tag_counts.items():
            # IDF = log(total_docs / doc_frequency)
            # Higher weight for rarer tags
            idf = math.log(total_docs / count) + 1
            self._tag_weights_cache[tag] = idf
    
    def _calculate_content_similarity(self, content1: str, content2: str) -> float:
        """Calculate content similarity using sequence matching."""
        if not content1 or not content2:
            return 0.0
        
        # Normalize content
        content1_lower = content1.lower().strip()
        content2_lower = content2.lower().strip()
        
        # Use SequenceMatcher for similarity
        return difflib.SequenceMatcher(None, content1_lower, content2_lower).ratio()
    
    def _calculate_temporal_proximity(self, date1_str: str, date2_str: str) -> float:
        """
        Calculate temporal proximity score (0-1).
        Documents created closer in time get higher scores.
        """
        try:
            date1 = datetime.fromisoformat(date1_str)
            date2 = datetime.fromisoformat(date2_str)
            
            # Calculate days between documents
            days_apart = abs((date2 - date1).days)
            
            # Scoring function: exponential decay
            # Same day = 1.0, 7 days = 0.5, 30 days = 0.1
            if days_apart == 0:
                return 1.0
            elif days_apart <= 7:
                return 0.5 + 0.5 * (7 - days_apart) / 7
            elif days_apart <= 30:
                return 0.1 + 0.4 * (30 - days_apart) / 23
            else:
                return 0.1 * math.exp(-days_apart / 365)
                
        except (ValueError, TypeError):
            return 0.0
    
    def _has_cross_reference(self, doc1: sqlite3.Row, doc2: sqlite3.Row) -> bool:
        """Check if documents reference each other by ID."""
        if not doc1['content'] or not doc2['content']:
            return False
        
        # Look for document ID references
        id_pattern = r'\b(?:doc|document|id|#)\s*(\d+)\b'
        
        # Check if doc1 references doc2
        doc1_refs = re.findall(id_pattern, doc1['content'], re.IGNORECASE)
        if str(doc2['id']) in doc1_refs:
            return True
        
        # Check if doc2 references doc1
        doc2_refs = re.findall(id_pattern, doc2['content'], re.IGNORECASE)
        if str(doc1['id']) in doc2_refs:
            return True
        
        return False
    
    def _classify_relationship(
        self,
        doc1: Dict[str, Any],
        doc2: Dict[str, Any],
        score: float
    ) -> str:
        """Classify the type of relationship between documents."""
        # Check for strong tag overlap
        tags1 = set(doc1['tags'].split(',')) if doc1['tags'] else set()
        tags2 = set(doc2['tags'].split(',')) if doc2['tags'] else set()
        
        if tags1 and tags2:
            overlap_ratio = len(tags1 & tags2) / min(len(tags1), len(tags2))
            if overlap_ratio > 0.7:
                return "strong_tag_similarity"
            elif overlap_ratio > 0.3:
                return "moderate_tag_similarity"
        
        # Check for temporal relationship
        try:
            date1 = datetime.fromisoformat(doc1['created_at'])
            date2 = datetime.fromisoformat(doc2['created_at'])
            days_apart = abs((date2 - date1).days)
            
            if days_apart <= 1:
                return "temporal_cluster"
            elif days_apart <= 7:
                return "temporal_proximity"
        except:
            pass
        
        # Check for project relationship
        if doc1['project'] == doc2['project'] and doc1['project']:
            return "same_project"
        
        # Default based on score
        if score >= 70:
            return "strong_relationship"
        elif score >= 40:
            return "moderate_relationship"
        else:
            return "weak_relationship"
    
    def _calculate_graph_metrics(
        self,
        nodes: List[Dict[str, Any]],
        edges: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Calculate various graph metrics."""
        if not nodes:
            return {}
        
        # Build adjacency structures
        adjacency = defaultdict(set)
        edge_weights = defaultdict(float)
        
        for edge in edges:
            adjacency[edge['source']].add(edge['target'])
            adjacency[edge['target']].add(edge['source'])
            edge_weights[(edge['source'], edge['target'])] = edge['weight']
            edge_weights[(edge['target'], edge['source'])] = edge['weight']
        
        # Calculate metrics
        metrics = {
            'density': self._calculate_density(len(nodes), len(edges)),
            'clustering_coefficient': self._calculate_clustering_coefficient(adjacency),
            'connected_components': self._find_connected_components(nodes, adjacency),
            'orphan_count': sum(1 for n in nodes if n['id'] not in adjacency),
            'bridge_nodes': self._find_bridge_nodes(adjacency),
            'centrality': self._calculate_centrality_scores(nodes, adjacency, edge_weights)
        }
        
        return metrics
    
    def _calculate_density(self, node_count: int, edge_count: int) -> float:
        """Calculate graph density (0-1)."""
        if node_count <= 1:
            return 0.0
        max_edges = node_count * (node_count - 1) / 2
        return edge_count / max_edges if max_edges > 0 else 0.0
    
    def _calculate_clustering_coefficient(
        self,
        adjacency: Dict[int, Set[int]]
    ) -> float:
        """
        Calculate average clustering coefficient.
        Measures how much nodes tend to cluster together.
        """
        if not adjacency:
            return 0.0
        
        coefficients = []
        
        for node, neighbors in adjacency.items():
            if len(neighbors) < 2:
                coefficients.append(0.0)
                continue
            
            # Count edges between neighbors
            neighbor_edges = 0
            neighbor_list = list(neighbors)
            
            for i in range(len(neighbor_list)):
                for j in range(i + 1, len(neighbor_list)):
                    if neighbor_list[j] in adjacency.get(neighbor_list[i], set()):
                        neighbor_edges += 1
            
            # Calculate local clustering coefficient
            max_edges = len(neighbors) * (len(neighbors) - 1) / 2
            coefficient = neighbor_edges / max_edges if max_edges > 0 else 0.0
            coefficients.append(coefficient)
        
        return sum(coefficients) / len(coefficients) if coefficients else 0.0
    
    def _find_connected_components(
        self,
        nodes: List[Dict[str, Any]],
        adjacency: Dict[int, Set[int]]
    ) -> List[List[int]]:
        """Find connected components using DFS."""
        visited = set()
        components = []
        
        def dfs(node_id: int, component: List[int]):
            visited.add(node_id)
            component.append(node_id)
            
            for neighbor in adjacency.get(node_id, set()):
                if neighbor not in visited:
                    dfs(neighbor, component)
        
        for node in nodes:
            node_id = node['id']
            if node_id not in visited:
                component = []
                dfs(node_id, component)
                components.append(component)
        
        # Sort components by size (largest first)
        components.sort(key=len, reverse=True)
        return components
    
    def _find_bridge_nodes(self, adjacency: Dict[int, Set[int]]) -> List[int]:
        """
        Find bridge nodes (articulation points) in the graph.
        These are nodes whose removal would increase connected components.
        """
        if not adjacency:
            return []
        
        bridges = []
        visited = set()
        discovery_time = {}
        low_time = {}
        parent = {}
        time_counter = [0]
        
        def dfs(node: int):
            children = 0
            visited.add(node)
            discovery_time[node] = low_time[node] = time_counter[0]
            time_counter[0] += 1
            
            for neighbor in adjacency.get(node, set()):
                if neighbor not in visited:
                    children += 1
                    parent[neighbor] = node
                    dfs(neighbor)
                    
                    # Update low time
                    low_time[node] = min(low_time[node], low_time[neighbor])
                    
                    # Check if node is articulation point
                    if parent.get(node) is None and children > 1:
                        # Root with multiple children
                        if node not in bridges:
                            bridges.append(node)
                    elif parent.get(node) is not None and low_time[neighbor] >= discovery_time[node]:
                        # Non-root with child that can't reach ancestors
                        if node not in bridges:
                            bridges.append(node)
                
                elif neighbor != parent.get(node):
                    # Back edge
                    low_time[node] = min(low_time[node], discovery_time[neighbor])
        
        # Run DFS from all unvisited nodes
        for node in adjacency:
            if node not in visited:
                parent[node] = None
                dfs(node)
        
        return bridges
    
    def _calculate_centrality_scores(
        self,
        nodes: List[Dict[str, Any]],
        adjacency: Dict[int, Set[int]],
        edge_weights: Dict[Tuple[int, int], float]
    ) -> Dict[int, Dict[str, float]]:
        """
        Calculate various centrality measures for nodes.
        Returns dict mapping node_id to centrality scores.
        """
        centrality = {}
        
        for node in nodes:
            node_id = node['id']
            neighbors = adjacency.get(node_id, set())
            
            # Degree centrality (normalized by max possible degree)
            degree_centrality = len(neighbors) / (len(nodes) - 1) if len(nodes) > 1 else 0.0
            
            # Weighted degree centrality
            weighted_degree = sum(
                edge_weights.get((node_id, neighbor), 0) 
                for neighbor in neighbors
            )
            max_weighted = (len(nodes) - 1) * 100  # Max edge weight is 100
            weighted_centrality = weighted_degree / max_weighted if max_weighted > 0 else 0.0
            
            centrality[node_id] = {
                'degree': degree_centrality,
                'weighted_degree': weighted_centrality,
                'neighbor_count': len(neighbors)
            }
        
        return centrality
    
    def get_node_recommendations(
        self,
        doc_id: int,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get recommendations for a specific document based on graph analysis.
        
        Returns similar documents that aren't yet connected.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        try:
            # Get the target document
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    d.id, d.title, d.content, d.project,
                    GROUP_CONCAT(t.name) as tags
                FROM documents d
                LEFT JOIN document_tags dt ON d.id = dt.document_id
                LEFT JOIN tags t ON dt.tag_id = t.id
                WHERE d.id = ? AND d.is_deleted = 0
                GROUP BY d.id
            """, (doc_id,))
            
            target_doc = cursor.fetchone()
            if not target_doc:
                return []
            
            # Get all other documents
            all_docs = self._get_filtered_documents(conn)
            
            # Calculate relationships
            recommendations = []
            
            for doc in all_docs:
                if doc['id'] == doc_id:
                    continue
                
                score = self._calculate_relationship_score(target_doc, doc)
                
                if score > 20:  # Minimum threshold for recommendation
                    recommendations.append({
                        'id': doc['id'],
                        'title': doc['title'],
                        'project': doc['project'],
                        'tags': doc['tags'].split(',') if doc['tags'] else [],
                        'similarity_score': score,
                        'reason': self._explain_relationship(target_doc, doc, score)
                    })
            
            # Sort by score and return top N
            recommendations.sort(key=lambda x: x['similarity_score'], reverse=True)
            return recommendations[:limit]
            
        finally:
            conn.close()
    
    def _explain_relationship(
        self,
        doc1: sqlite3.Row,
        doc2: sqlite3.Row,
        score: float
    ) -> str:
        """Generate human-readable explanation for document relationship."""
        reasons = []
        
        # Check tag overlap
        tags1 = set(doc1['tags'].split(',')) if doc1['tags'] else set()
        tags2 = set(doc2['tags'].split(',')) if doc2['tags'] else set()
        common_tags = tags1 & tags2
        
        if common_tags:
            reasons.append(f"shares tags: {', '.join(sorted(common_tags))}")
        
        # Check project
        if doc1['project'] == doc2['project'] and doc1['project']:
            reasons.append(f"same project: {doc1['project']}")
        
        # Check temporal proximity
        try:
            date1 = datetime.fromisoformat(doc1['created_at'])
            date2 = datetime.fromisoformat(doc2['created_at'])
            days_apart = abs((date2 - date1).days)
            
            if days_apart <= 1:
                reasons.append("created on same day")
            elif days_apart <= 7:
                reasons.append(f"created {days_apart} days apart")
        except:
            pass
        
        # Default reason based on score
        if not reasons:
            if score >= 50:
                reasons.append("high content similarity")
            else:
                reasons.append("moderate similarity")
        
        return "; ".join(reasons)