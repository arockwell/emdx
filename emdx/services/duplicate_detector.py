"""
Duplicate detection service for EMDX.
Finds exact and near-duplicate documents based on content and metadata.
"""

import hashlib
import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config.settings import get_db_path


class DuplicateDetector:
    """Service for detecting and managing duplicate documents."""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_db_path()
    
    def _get_content_hash(self, content: Optional[str]) -> str:
        """Generate hash of content for duplicate detection."""
        if not content:
            return "empty"
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def find_duplicates(self) -> List[List[Dict[str, Any]]]:
        """
        Find all duplicate documents based on content hash.
        
        Returns:
            List of duplicate groups, each group is a list of documents
            with identical content.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all active documents
        cursor.execute("""
            SELECT 
                d.id, 
                d.title, 
                d.content, 
                d.project, 
                d.access_count,
                d.created_at,
                d.updated_at,
                LENGTH(d.content) as content_length,
                GROUP_CONCAT(t.name) as tags
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.document_id
            LEFT JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0
            GROUP BY d.id
        """)
        
        documents = cursor.fetchall()
        conn.close()
        
        # Group by content hash
        hash_groups = defaultdict(list)
        for doc in documents:
            content_hash = self._get_content_hash(doc['content'])
            doc_dict = dict(doc)
            hash_groups[content_hash].append(doc_dict)
        
        # Filter to only groups with duplicates
        duplicate_groups = [
            group for group in hash_groups.values() 
            if len(group) > 1
        ]
        
        # Sort groups by total views (most important first)
        duplicate_groups.sort(
            key=lambda group: sum(doc['access_count'] for doc in group),
            reverse=True
        )
        
        return duplicate_groups
    
    def find_near_duplicates(self, threshold: float = 0.85) -> List[Tuple[Dict, Dict, float]]:
        """
        Find near-duplicate documents based on content similarity.
        
        Args:
            threshold: Minimum similarity ratio (0.0 to 1.0)
            
        Returns:
            List of tuples (doc1, doc2, similarity_score)
        """
        import difflib
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all active documents
        cursor.execute("""
            SELECT 
                d.id, 
                d.title, 
                d.content, 
                d.project, 
                d.access_count,
                d.created_at,
                LENGTH(d.content) as content_length
            FROM documents d
            WHERE d.is_deleted = 0
            AND LENGTH(d.content) > 50  -- Skip very short docs
            ORDER BY LENGTH(d.content) DESC
            LIMIT 200  -- Limit for performance
        """)
        
        documents = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        near_duplicates = []
        
        # Compare each document pair
        for i, doc1 in enumerate(documents):
            # Only compare with subsequent docs to avoid duplicates
            for doc2 in documents[i+1:]:
                # Skip if very different lengths (optimization)
                len1 = doc1['content_length']
                len2 = doc2['content_length']
                if min(len1, len2) / max(len1, len2) < 0.5:
                    continue
                
                # Calculate similarity
                similarity = difflib.SequenceMatcher(
                    None, 
                    doc1['content'], 
                    doc2['content']
                ).ratio()
                
                if similarity >= threshold:
                    near_duplicates.append((doc1, doc2, similarity))
        
        # Sort by similarity
        near_duplicates.sort(key=lambda x: x[2], reverse=True)
        return near_duplicates
    
    def sort_by_strategy(self, group: List[Dict[str, Any]], strategy: str) -> List[Dict[str, Any]]:
        """
        Sort a duplicate group by the given strategy.
        The first document in the sorted list should be kept.
        
        Args:
            group: List of duplicate documents
            strategy: One of 'highest-views', 'newest', 'oldest'
            
        Returns:
            Sorted list with the document to keep first
        """
        if strategy == 'highest-views':
            # Sort by views (descending), then by ID (ascending) for stability
            return sorted(group, key=lambda x: (-x['access_count'], x['id']))
        elif strategy == 'newest':
            # Sort by creation date (descending)
            return sorted(group, key=lambda x: x['created_at'], reverse=True)
        elif strategy == 'oldest':
            # Sort by creation date (ascending)
            return sorted(group, key=lambda x: x['created_at'])
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
    
    def get_documents_to_delete(
        self, 
        duplicate_groups: List[List[Dict[str, Any]]], 
        strategy: str = 'highest-views'
    ) -> List[int]:
        """
        Get list of document IDs to delete based on strategy.
        
        Args:
            duplicate_groups: List of duplicate groups
            strategy: Strategy for choosing which document to keep
            
        Returns:
            List of document IDs to delete
        """
        docs_to_delete = []
        
        for group in duplicate_groups:
            sorted_group = self.sort_by_strategy(group, strategy)
            # Keep the first one, delete the rest
            docs_to_delete.extend([doc['id'] for doc in sorted_group[1:]])
        
        return docs_to_delete
    
    def delete_documents(self, doc_ids: List[int]) -> int:
        """
        Soft delete the specified documents.
        
        Args:
            doc_ids: List of document IDs to delete
            
        Returns:
            Number of documents deleted
        """
        if not doc_ids:
            return 0
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Perform soft delete in batches
        deleted_count = 0
        batch_size = 100
        timestamp = datetime.now().isoformat()
        
        for i in range(0, len(doc_ids), batch_size):
            batch = doc_ids[i:i + batch_size]
            placeholders = ','.join('?' * len(batch))
            
            cursor.execute(f"""
                UPDATE documents 
                SET is_deleted = 1, deleted_at = ?
                WHERE id IN ({placeholders})
                AND is_deleted = 0
            """, [timestamp] + batch)
            
            deleted_count += cursor.rowcount
        
        conn.commit()
        conn.close()
        
        return deleted_count
    
    def get_duplicate_stats(self) -> Dict[str, Any]:
        """
        Get statistics about duplicates in the knowledge base.
        
        Returns:
            Dictionary with duplicate statistics
        """
        duplicate_groups = self.find_duplicates()
        
        total_duplicates = sum(len(group) - 1 for group in duplicate_groups)
        space_wasted = sum(
            sum(doc['content_length'] for doc in group[1:])
            for group in duplicate_groups
        )
        
        # Find most duplicated content
        most_duplicated = None
        if duplicate_groups:
            largest_group = max(duplicate_groups, key=len)
            most_duplicated = {
                'title': largest_group[0]['title'],
                'copies': len(largest_group),
                'total_views': sum(doc['access_count'] for doc in largest_group)
            }
        
        return {
            'duplicate_groups': len(duplicate_groups),
            'total_duplicates': total_duplicates,
            'space_wasted': space_wasted,
            'most_duplicated': most_duplicated
        }
    
    def find_similar_titles(self) -> List[List[Dict[str, Any]]]:
        """
        Find documents with identical titles but different content.
        
        Returns:
            List of title groups with different content
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all active documents
        cursor.execute("""
            SELECT 
                d.id, 
                d.title, 
                d.content,
                d.project,
                d.access_count,
                LENGTH(d.content) as content_length
            FROM documents d
            WHERE d.is_deleted = 0
            ORDER BY d.title, d.id
        """)
        
        documents = cursor.fetchall()
        conn.close()
        
        # Group by title
        title_groups = defaultdict(list)
        for doc in documents:
            title_groups[doc['title'].strip()].append(dict(doc))
        
        # Filter to groups with multiple documents and different content
        similar_title_groups = []
        for title, group in title_groups.items():
            if len(group) > 1:
                # Check if content is different
                hashes = set(self._get_content_hash(doc['content']) for doc in group)
                if len(hashes) > 1:  # Different content
                    similar_title_groups.append(group)
        
        return similar_title_groups
