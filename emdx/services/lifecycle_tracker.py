"""
Lifecycle tracking service for EMDX.
Tracks document lifecycle, especially for gameplans and projects.
"""

import sqlite3
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..config.settings import get_db_path
from ..models.documents import get_document, update_document
from ..models.tags import add_tags_to_document, get_document_tags, remove_tags_from_document


class LifecycleTracker:
    """Tracks and manages document lifecycles, especially gameplans."""
    
    # Lifecycle stages
    STAGES = {
        'planning': ['🎯', '📝'],           # Gameplan, planning stage
        'active': ['🚀'],                   # Actively working
        'blocked': ['🚧'],                  # Blocked/stuck
        'completed': ['✅'],                # Done
        'success': ['🎉'],                  # Successful outcome
        'failed': ['❌'],                   # Failed outcome
        'archived': ['📦']                  # Archived
    }
    
    # Lifecycle transitions
    TRANSITIONS = {
        'planning': ['active', 'blocked', 'archived'],
        'active': ['blocked', 'completed', 'archived'],
        'blocked': ['active', 'failed', 'archived'],
        'completed': ['success', 'failed', 'archived'],
        'success': ['archived'],
        'failed': ['archived'],
        'archived': []  # Terminal state
    }
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_db_path()
    
    def get_document_stage(self, doc_id: int) -> Optional[str]:
        """
        Determine the current lifecycle stage of a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Current stage name or None
        """
        tags = set(get_document_tags(doc_id))
        
        # Check stages in reverse order (later stages take precedence)
        for stage in reversed(list(self.STAGES.keys())):
            if any(tag in tags for tag in self.STAGES[stage]):
                return stage
        
        return None
    
    def get_gameplans(self, stage: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all gameplans, optionally filtered by stage.
        
        Args:
            stage: Filter by specific lifecycle stage
            
        Returns:
            List of gameplan documents with stage info
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Find all documents with gameplan tag
        cursor.execute("""
            SELECT DISTINCT d.id, d.title, d.project, d.created_at, d.updated_at, d.access_count
            FROM documents d
            JOIN document_tags dt ON d.id = dt.document_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0 AND t.name = '🎯'
            ORDER BY d.updated_at DESC
        """)
        
        gameplans = []
        for row in cursor.fetchall():
            doc = dict(row)
            doc['stage'] = self.get_document_stage(doc['id'])
            doc['tags'] = get_document_tags(doc['id'])
            
            # Calculate age
            created = datetime.fromisoformat(doc['created_at'])
            doc['age_days'] = (datetime.now() - created).days
            
            if stage is None or doc['stage'] == stage:
                gameplans.append(doc)
        
        conn.close()
        return gameplans
    
    def analyze_lifecycle_patterns(self) -> Dict[str, Any]:
        """
        Analyze patterns in gameplan lifecycles.
        
        Returns:
            Analysis of success rates, average durations, etc.
        """
        gameplans = self.get_gameplans()
        
        if not gameplans:
            return {
                'total_gameplans': 0,
                'success_rate': 0,
                'average_duration': 0,
                'stage_distribution': {},
                'insights': []
            }
        
        # Stage distribution
        stage_counts = defaultdict(int)
        for gp in gameplans:
            if gp['stage']:
                stage_counts[gp['stage']] += 1
        
        # Success metrics
        completed = [gp for gp in gameplans if gp['stage'] in ['success', 'failed']]
        success_count = sum(1 for gp in completed if gp['stage'] == 'success')
        success_rate = (success_count / len(completed) * 100) if completed else 0
        
        # Duration analysis
        completed_durations = []
        for gp in completed:
            created = datetime.fromisoformat(gp['created_at'])
            updated = datetime.fromisoformat(gp['updated_at'])
            duration = (updated - created).days
            completed_durations.append(duration)
        
        avg_duration = sum(completed_durations) / len(completed_durations) if completed_durations else 0
        
        # Generate insights
        insights = []
        
        # Stale gameplans
        stale_active = [gp for gp in gameplans 
                       if gp['stage'] == 'active' and gp['age_days'] > 30]
        if stale_active:
            insights.append(f"{len(stale_active)} gameplans have been active for >30 days")
        
        # Blocked gameplans
        blocked = [gp for gp in gameplans if gp['stage'] == 'blocked']
        if blocked:
            insights.append(f"{len(blocked)} gameplans are currently blocked")
        
        # Success rate insight
        if completed and success_rate < 50:
            insights.append(f"Low success rate ({success_rate:.0f}%) - consider reviewing failed gameplans")
        
        return {
            'total_gameplans': len(gameplans),
            'success_rate': success_rate,
            'average_duration': avg_duration,
            'stage_distribution': dict(stage_counts),
            'insights': insights,
            'stale_active': len(stale_active),
            'blocked_count': len(blocked)
        }
    
    def suggest_transitions(self, doc_id: int) -> List[Tuple[str, str]]:
        """
        Suggest valid lifecycle transitions for a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            List of tuples (new_stage, recommendation)
        """
        current_stage = self.get_document_stage(doc_id)
        if not current_stage:
            return [('planning', 'Start tracking this as a gameplan')]
        
        suggestions = []
        doc = get_document(str(doc_id))
        
        # Get valid transitions
        valid_stages = self.TRANSITIONS.get(current_stage, [])
        
        for stage in valid_stages:
            # Generate context-aware recommendations
            if stage == 'active' and current_stage == 'planning':
                suggestions.append((stage, "Ready to start implementation"))
            elif stage == 'blocked':
                suggestions.append((stage, "Mark as blocked if waiting on dependencies"))
            elif stage == 'completed':
                suggestions.append((stage, "Mark as completed when finished"))
            elif stage == 'success':
                suggestions.append((stage, "Mark as successful if goals were achieved"))
            elif stage == 'failed':
                suggestions.append((stage, "Mark as failed if goals were not met"))
            elif stage == 'archived':
                suggestions.append((stage, "Archive if no longer relevant"))
        
        return suggestions
    
    def transition_document(self, doc_id: int, new_stage: str, notes: Optional[str] = None) -> bool:
        """
        Transition a document to a new lifecycle stage.
        
        Args:
            doc_id: Document ID
            new_stage: Target stage
            notes: Optional transition notes
            
        Returns:
            True if successful
        """
        current_stage = self.get_document_stage(doc_id)
        
        # Validate transition
        if current_stage and new_stage not in self.TRANSITIONS.get(current_stage, []):
            return False
        
        # Remove old stage tags
        if current_stage:
            for tag in self.STAGES[current_stage]:
                try:
                    remove_tags_from_document(doc_id, [tag])
                except Exception as e:
                    # Log but continue - tag removal is not critical
                    import logging
                    logging.getLogger(__name__).debug(f"Failed to remove tag {tag} from document {doc_id}: {e}")
        
        # Add new stage tags
        if new_stage in self.STAGES:
            add_tags_to_document(doc_id, self.STAGES[new_stage])
        
        # Add transition note to document if provided
        if notes:
            doc = get_document(str(doc_id))
            if doc:
                new_content = doc['content'] or ''
                transition_note = f"\n\n---\n_Lifecycle transition: {current_stage or 'untracked'} → {new_stage}_\n"
                if notes:
                    transition_note += f"_Note: {notes}_\n"
                transition_note += f"_Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"
                
                update_document(doc_id, content=new_content + transition_note)
        
        return True
    
    def auto_detect_transitions(self) -> List[Dict[str, Any]]:
        """
        Automatically detect documents that should transition stages.
        
        Returns:
            List of suggested transitions
        """
        suggestions = []
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Find active gameplans not updated in 30+ days
        cursor.execute("""
            SELECT DISTINCT d.id, d.title, d.updated_at
            FROM documents d
            JOIN document_tags dt ON d.id = dt.document_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0 
            AND t.name = '🚀'
            AND julianday('now') - julianday(d.updated_at) > 30
        """)
        
        for row in cursor.fetchall():
            suggestions.append({
                'doc_id': row['id'],
                'title': row['title'],
                'current_stage': 'active',
                'suggested_stage': 'blocked',
                'reason': 'No updates in 30+ days'
            })
        
        # Find completed docs without outcome
        cursor.execute("""
            SELECT DISTINCT d.id, d.title, d.content
            FROM documents d
            JOIN document_tags dt ON d.id = dt.document_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0 
            AND t.name = '✅'
            AND NOT EXISTS (
                SELECT 1 FROM document_tags dt2
                JOIN tags t2 ON dt2.tag_id = t2.id
                WHERE dt2.document_id = d.id
                AND t2.name IN ('🎉', '❌')
            )
        """)
        
        for row in cursor.fetchall():
            # Try to detect success/failure from content
            content = (row['content'] or '').lower()
            if any(word in content for word in ['success', 'achieved', 'completed successfully']):
                suggested = 'success'
            elif any(word in content for word in ['failed', 'abandoned', 'cancelled']):
                suggested = 'failed'
            else:
                suggested = 'success'  # Default to success
            
            suggestions.append({
                'doc_id': row['id'],
                'title': row['title'],
                'current_stage': 'completed',
                'suggested_stage': suggested,
                'reason': 'Completed without outcome specified'
            })
        
        conn.close()
        return suggestions
    
    def get_stage_duration_stats(self) -> Dict[str, Dict[str, float]]:
        """
        Get statistics on how long documents spend in each stage.
        
        Returns:
            Dictionary mapping stages to duration statistics
        """
        # This would require tracking stage transitions over time
        # For now, return placeholder data
        return {
            'planning': {'avg_days': 3, 'min_days': 1, 'max_days': 7},
            'active': {'avg_days': 14, 'min_days': 3, 'max_days': 60},
            'blocked': {'avg_days': 7, 'min_days': 1, 'max_days': 30},
            'completed': {'avg_days': 1, 'min_days': 0, 'max_days': 3}
        }
