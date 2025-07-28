"""
Document merging service for EMDX.
Intelligently merges related documents while preserving important information.
"""

import difflib
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config.settings import get_db_path
from ..models.documents import delete_document, get_document, update_document
from ..models.tags import add_tags_to_document, get_document_tags


@dataclass
class MergeCandidate:
    """Represents a pair of documents that could be merged."""
    doc1_id: int
    doc2_id: int
    doc1_title: str
    doc2_title: str
    similarity_score: float
    merge_reason: str
    recommended_action: str


@dataclass
class MergeStrategy:
    """Strategy for merging two documents."""
    keep_doc_id: int
    merge_doc_id: int
    merged_title: str
    merged_content: str
    merged_tags: List[str]
    preserve_metadata: Dict[str, Any]


class DocumentMerger:
    """Service for intelligently merging related documents."""
    
    SIMILARITY_THRESHOLD = 0.7  # Minimum similarity for merge candidates
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_db_path()
    
    def find_merge_candidates(
        self, 
        project: Optional[str] = None,
        similarity_threshold: float = None
    ) -> List[MergeCandidate]:
        """
        Find documents that are candidates for merging.
        
        Args:
            project: Filter by specific project
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of merge candidates sorted by similarity
        """
        threshold = similarity_threshold or self.SIMILARITY_THRESHOLD
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get all active documents
        query = """
            SELECT id, title, content, project, access_count
            FROM documents
            WHERE is_deleted = 0
        """
        params = []
        
        if project:
            query += " AND project = ?"
            params.append(project)
        
        cursor.execute(query, params)
        documents = cursor.fetchall()
        conn.close()
        
        candidates = []
        
        # Compare all document pairs
        for i, doc1 in enumerate(documents):
            for doc2 in documents[i+1:]:
                # Skip if both have high access counts (likely both important)
                if doc1['access_count'] > 50 and doc2['access_count'] > 50:
                    continue
                
                # Check title similarity
                title_sim = self._calculate_similarity(doc1['title'], doc2['title'])
                
                # Check content similarity (expensive, so only if titles are somewhat similar)
                if title_sim > 0.3:
                    content_sim = self._calculate_similarity(
                        doc1['content'] or '', 
                        doc2['content'] or ''
                    )
                    
                    # Weighted similarity
                    overall_sim = (title_sim * 0.4) + (content_sim * 0.6)
                    
                    if overall_sim >= threshold:
                        # Determine merge reason
                        if title_sim > 0.8:
                            reason = "Nearly identical titles"
                        elif content_sim > 0.9:
                            reason = "Nearly identical content"
                        elif title_sim > 0.6 and content_sim > 0.7:
                            reason = "Similar title and content"
                        else:
                            reason = "Related content"
                        
                        # Recommend which to keep
                        if doc1['access_count'] > doc2['access_count']:
                            action = f"Merge into #{doc1['id']} (more views)"
                        elif len(doc1['content'] or '') > len(doc2['content'] or ''):
                            action = f"Merge into #{doc1['id']} (more content)"
                        else:
                            action = f"Merge into #{doc2['id']}"
                        
                        candidates.append(MergeCandidate(
                            doc1_id=doc1['id'],
                            doc2_id=doc2['id'],
                            doc1_title=doc1['title'],
                            doc2_title=doc2['title'],
                            similarity_score=overall_sim,
                            merge_reason=reason,
                            recommended_action=action
                        ))
        
        # Sort by similarity score
        candidates.sort(key=lambda c: c.similarity_score, reverse=True)
        return candidates
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts using SequenceMatcher."""
        if not text1 or not text2:
            return 0.0
        
        # Quick check for exact match
        if text1 == text2:
            return 1.0
        
        # Use SequenceMatcher for similarity
        return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    
    def suggest_merge_strategy(
        self, 
        doc1_id: int, 
        doc2_id: int
    ) -> MergeStrategy:
        """
        Suggest the best strategy for merging two documents.
        
        Args:
            doc1_id: First document ID
            doc2_id: Second document ID
            
        Returns:
            MergeStrategy with recommended approach
        """
        # Get both documents
        doc1 = get_document(str(doc1_id))
        doc2 = get_document(str(doc2_id))
        
        if not doc1 or not doc2:
            raise ValueError("One or both documents not found")
        
        # Get tags for both
        tags1 = get_document_tags(doc1_id)
        tags2 = get_document_tags(doc2_id)
        
        # Determine which document to keep (higher score wins)
        doc1_score = self._calculate_document_score(doc1, tags1)
        doc2_score = self._calculate_document_score(doc2, tags2)
        
        if doc1_score >= doc2_score:
            keep_doc = doc1
            keep_id = doc1_id
            merge_doc = doc2
            merge_id = doc2_id
        else:
            keep_doc = doc2
            keep_id = doc2_id
            merge_doc = doc1
            merge_id = doc1_id
        
        # Merge titles
        if keep_doc['title'] == merge_doc['title']:
            merged_title = keep_doc['title']
        else:
            # Use the more descriptive title
            if len(keep_doc['title']) >= len(merge_doc['title']):
                merged_title = keep_doc['title']
            else:
                merged_title = merge_doc['title']
        
        # Merge content
        merged_content = self._merge_content(
            keep_doc['content'] or '', 
            merge_doc['content'] or '',
            keep_doc['title'],
            merge_doc['title']
        )
        
        # Combine tags (union)
        merged_tags = list(set(tags1 + tags2))
        
        # Preserve important metadata
        preserve_metadata = {
            'original_ids': [doc1_id, doc2_id],
            'original_titles': [doc1['title'], doc2['title']],
            'merge_date': datetime.now().isoformat(),
            'combined_access_count': doc1['access_count'] + doc2['access_count']
        }
        
        return MergeStrategy(
            keep_doc_id=keep_id,
            merge_doc_id=merge_id,
            merged_title=merged_title,
            merged_content=merged_content,
            merged_tags=merged_tags,
            preserve_metadata=preserve_metadata
        )
    
    def _calculate_document_score(self, doc: Dict[str, Any], tags: List[str]) -> float:
        """Calculate a quality score for a document."""
        score = 0.0
        
        # Access count (popularity)
        score += min(doc['access_count'] / 10, 10)  # Cap at 10 points
        
        # Content length (comprehensiveness)
        content_length = len(doc['content'] or '')
        score += min(content_length / 1000, 5)  # Cap at 5 points
        
        # Has tags
        score += len(tags) * 0.5  # 0.5 points per tag
        
        # Title quality
        if len(doc['title']) > 10:
            score += 1
        
        # Recent access
        if doc.get('accessed_at'):
            days_since_access = (datetime.now() - datetime.fromisoformat(doc['accessed_at'])).days
            if days_since_access < 7:
                score += 2
            elif days_since_access < 30:
                score += 1
        
        return score
    
    def _merge_content(
        self, 
        content1: str, 
        content2: str,
        title1: str,
        title2: str
    ) -> str:
        """
        Intelligently merge two document contents.
        
        Args:
            content1: Content of first document
            content2: Content of second document
            title1: Title of first document
            title2: Title of second document
            
        Returns:
            Merged content
        """
        # If one is empty, use the other
        if not content1:
            return content2
        if not content2:
            return content1
        
        # If identical, return one
        if content1 == content2:
            return content1
        
        # Check if one contains the other
        if content1 in content2:
            return content2
        if content2 in content1:
            return content1
        
        # Otherwise, combine with clear separation
        merged = []
        
        # Add primary content
        merged.append(content1)
        
        # Add separator
        merged.append("\n\n---\n")
        
        # Add note about merge
        if title1 != title2:
            merged.append(f"\n_Merged from: {title2}_\n")
        else:
            merged.append("\n_Additional content from duplicate:_\n")
        
        merged.append("\n" + content2)
        
        return "".join(merged)
    
    def execute_merge(
        self, 
        strategy: MergeStrategy,
        delete_source: bool = True
    ) -> bool:
        """
        Execute a document merge based on the strategy.
        
        Args:
            strategy: The merge strategy to execute
            delete_source: Whether to delete the source document
            
        Returns:
            True if successful
        """
        try:
            # Update the target document
            update_document(
                doc_id=strategy.keep_doc_id,
                title=strategy.merged_title,
                content=strategy.merged_content
            )
            
            # Add merged tags
            if strategy.merged_tags:
                # Get existing tags to avoid duplicates
                existing = set(get_document_tags(strategy.keep_doc_id))
                new_tags = [tag for tag in strategy.merged_tags if tag not in existing]
                if new_tags:
                    add_tags_to_document(strategy.keep_doc_id, new_tags)
            
            # Delete or mark the source document
            if delete_source:
                delete_document(strategy.merge_doc_id)
            
            # Log the merge (could be stored in a merge history table)
            # For now, we'll just return success
            
            return True
            
        except Exception as e:
            # Log error
            print(f"Merge failed: {e}")
            return False
    
    def find_related_documents(
        self, 
        doc_id: int, 
        limit: int = 5
    ) -> List[Tuple[int, str, float]]:
        """
        Find documents related to a specific document.
        
        Args:
            doc_id: Document ID to find related docs for
            limit: Maximum number of related docs
            
        Returns:
            List of tuples (doc_id, title, similarity_score)
        """
        doc = get_document(str(doc_id))
        if not doc:
            return []
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get other documents in same project first
        cursor.execute("""
            SELECT id, title, content
            FROM documents
            WHERE is_deleted = 0 
            AND id != ?
            AND project = ?
            LIMIT 50
        """, (doc_id, doc['project']))
        
        candidates = cursor.fetchall()
        conn.close()
        
        # Calculate similarities
        related = []
        for candidate in candidates:
            # Title similarity
            title_sim = self._calculate_similarity(doc['title'], candidate['title'])
            
            # Content similarity (sample for performance)
            content_sim = self._calculate_similarity(
                (doc['content'] or '')[:500], 
                (candidate['content'] or '')[:500]
            )
            
            # Combined score
            score = (title_sim * 0.3) + (content_sim * 0.7)
            
            if score > 0.3:  # Minimum threshold
                related.append((candidate['id'], candidate['title'], score))
        
        # Sort by score and return top N
        related.sort(key=lambda x: x[2], reverse=True)
        return related[:limit]
