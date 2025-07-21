"""
Health monitoring service for EMDX knowledge base.
Analyzes knowledge base health and provides actionable recommendations.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
import statistics

from ..config.settings import get_db_path
from ..services.duplicate_detector import DuplicateDetector
from ..services.auto_tagger import AutoTagger


@dataclass
class HealthMetric:
    """Represents a single health metric."""
    name: str
    value: float  # 0.0 to 1.0
    weight: float  # Importance weight
    status: str  # 'good', 'warning', 'critical'
    details: str
    recommendations: List[str]


@dataclass
class ProjectHealth:
    """Health metrics for a specific project."""
    project: str
    document_count: int
    tag_coverage: float
    avg_document_age: int  # days
    activity_score: float
    organization_score: float
    overall_score: float


class HealthMonitor:
    """Service for monitoring knowledge base health."""
    
    # Health thresholds
    CRITICAL_THRESHOLD = 0.4
    WARNING_THRESHOLD = 0.7
    
    # Metric weights
    WEIGHTS = {
        'tag_coverage': 0.20,
        'duplicate_ratio': 0.15,
        'organization': 0.15,
        'activity': 0.15,
        'quality': 0.10,
        'growth': 0.10,
        'connectivity': 0.15
    }
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_db_path()
    
    def calculate_overall_health(self) -> Dict[str, Any]:
        """
        Calculate comprehensive health score for the knowledge base.
        
        Returns:
            Dictionary with overall health score and breakdown by metrics
        """
        metrics = []
        
        # Calculate individual metrics
        metrics.append(self._calculate_tag_coverage())
        metrics.append(self._calculate_duplicate_health())
        metrics.append(self._calculate_organization_health())
        metrics.append(self._calculate_activity_health())
        metrics.append(self._calculate_quality_health())
        metrics.append(self._calculate_growth_health())
        metrics.append(self._calculate_connectivity_health())
        
        # Calculate weighted overall score
        overall_score = sum(m.value * m.weight for m in metrics)
        
        # Determine overall status
        if overall_score < self.CRITICAL_THRESHOLD:
            overall_status = 'critical'
        elif overall_score < self.WARNING_THRESHOLD:
            overall_status = 'warning'
        else:
            overall_status = 'good'
        
        # Get statistics
        stats = self._get_basic_stats()
        
        return {
            'overall_score': overall_score,
            'overall_status': overall_status,
            'metrics': {m.name: m for m in metrics},
            'statistics': stats,
            'timestamp': datetime.now().isoformat()
        }
    
    def _get_basic_stats(self) -> Dict[str, Any]:
        """Get basic statistics about the knowledge base."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total documents
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
        total_docs = cursor.fetchone()[0]
        
        # Total projects
        cursor.execute("SELECT COUNT(DISTINCT project) FROM documents WHERE is_deleted = 0 AND project IS NOT NULL")
        total_projects = cursor.fetchone()[0]
        
        # Total tags
        cursor.execute("SELECT COUNT(DISTINCT tag_id) FROM document_tags")
        total_tags = cursor.fetchone()[0]
        
        # Database size
        cursor.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
        db_size = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total_documents': total_docs,
            'total_projects': total_projects,
            'total_tags': total_tags,
            'database_size': db_size,
            'database_size_mb': round(db_size / 1024 / 1024, 2)
        }
    
    def _calculate_tag_coverage(self) -> HealthMetric:
        """Calculate tag coverage health metric."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get tagged vs untagged counts
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT d.id) as total,
                COUNT(DISTINCT dt.document_id) as tagged
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.document_id
            WHERE d.is_deleted = 0
        """)
        
        result = cursor.fetchone()
        total = result[0]
        tagged = result[1]
        
        conn.close()
        
        if total == 0:
            coverage = 1.0
        else:
            coverage = tagged / total
        
        # Determine status
        if coverage < 0.5:
            status = 'critical'
        elif coverage < 0.8:
            status = 'warning'
        else:
            status = 'good'
        
        # Generate recommendations
        recommendations = []
        if coverage < 0.8:
            untagged = total - tagged
            recommendations.append(f"Tag {untagged} untagged documents using 'emdx tag batch'")
            recommendations.append("Enable auto-tagging with 'emdx save --auto-tag'")
        
        return HealthMetric(
            name='tag_coverage',
            value=coverage,
            weight=self.WEIGHTS['tag_coverage'],
            status=status,
            details=f"{tagged}/{total} documents tagged ({coverage:.1%})",
            recommendations=recommendations
        )
    
    def _calculate_duplicate_health(self) -> HealthMetric:
        """Calculate duplicate document health metric."""
        detector = DuplicateDetector(self.db_path)
        stats = detector.get_duplicate_stats()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
        total = cursor.fetchone()[0]
        conn.close()
        
        if total == 0:
            duplicate_ratio = 0.0
        else:
            duplicate_ratio = stats['total_duplicates'] / total
        
        # Invert for health score (fewer duplicates = better health)
        health_value = 1.0 - min(duplicate_ratio, 1.0)
        
        # Determine status
        if duplicate_ratio > 0.2:
            status = 'critical'
        elif duplicate_ratio > 0.1:
            status = 'warning'
        else:
            status = 'good'
        
        # Generate recommendations
        recommendations = []
        if stats['total_duplicates'] > 0:
            recommendations.append(f"Remove {stats['total_duplicates']} duplicates with 'emdx clean duplicates'")
            if stats['space_wasted'] > 1024 * 1024:  # 1MB
                mb_wasted = stats['space_wasted'] / 1024 / 1024
                recommendations.append(f"Save {mb_wasted:.1f}MB by removing duplicates")
        
        return HealthMetric(
            name='duplicate_ratio',
            value=health_value,
            weight=self.WEIGHTS['duplicate_ratio'],
            status=status,
            details=f"{stats['total_duplicates']} duplicates found ({duplicate_ratio:.1%} of total)",
            recommendations=recommendations
        )
    
    def _calculate_organization_health(self) -> HealthMetric:
        """Calculate organization health based on project distribution."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get project distribution
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN project IS NOT NULL THEN 1 END) as with_project,
                COUNT(CASE WHEN project IS NULL THEN 1 END) as without_project,
                COUNT(DISTINCT project) as project_count
            FROM documents
            WHERE is_deleted = 0
        """)
        
        result = cursor.fetchone()
        with_project = result[0]
        without_project = result[1]
        project_count = result[2]
        total = with_project + without_project
        
        # Get average docs per project
        if project_count > 0:
            avg_per_project = with_project / project_count
        else:
            avg_per_project = 0
        
        conn.close()
        
        # Calculate organization score
        if total == 0:
            org_score = 1.0
        else:
            # Score based on % with projects
            project_coverage = with_project / total
            
            # Penalize too many or too few projects
            if project_count == 0:
                distribution_score = 0.0
            elif avg_per_project < 5:  # Too many projects
                distribution_score = 0.7
            elif avg_per_project > 100:  # Too few projects
                distribution_score = 0.8
            else:
                distribution_score = 1.0
            
            org_score = (project_coverage * 0.7) + (distribution_score * 0.3)
        
        # Determine status
        if org_score < 0.5:
            status = 'critical'
        elif org_score < 0.7:
            status = 'warning'
        else:
            status = 'good'
        
        # Generate recommendations
        recommendations = []
        if without_project > 0:
            recommendations.append(f"Organize {without_project} documents without projects")
        if avg_per_project > 100:
            recommendations.append("Consider breaking down large projects into smaller ones")
        elif avg_per_project < 5 and project_count > 10:
            recommendations.append("Consider consolidating small projects")
        
        return HealthMetric(
            name='organization',
            value=org_score,
            weight=self.WEIGHTS['organization'],
            status=status,
            details=f"{project_count} projects, {without_project} unorganized docs",
            recommendations=recommendations
        )
    
    def _calculate_activity_health(self) -> HealthMetric:
        """Calculate activity health based on recent usage."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Define time periods
        now = datetime.now()
        last_week = now - timedelta(days=7)
        last_month = now - timedelta(days=30)
        last_quarter = now - timedelta(days=90)
        
        # Get activity counts
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN datetime(accessed_at) > ? THEN 1 END) as week_active,
                COUNT(CASE WHEN datetime(accessed_at) > ? THEN 1 END) as month_active,
                COUNT(CASE WHEN datetime(accessed_at) > ? THEN 1 END) as quarter_active,
                COUNT(*) as total
            FROM documents
            WHERE is_deleted = 0
        """, (last_week.isoformat(), last_month.isoformat(), last_quarter.isoformat()))
        
        result = cursor.fetchone()
        week_active = result[0]
        month_active = result[1]
        quarter_active = result[2]
        total = result[3]
        
        # Get creation trend
        cursor.execute("""
            SELECT COUNT(*) 
            FROM documents 
            WHERE is_deleted = 0 
            AND datetime(created_at) > ?
        """, (last_month.isoformat(),))
        
        new_last_month = cursor.fetchone()[0]
        
        conn.close()
        
        # Calculate activity score
        if total == 0:
            activity_score = 0.5
        else:
            # Weight recent activity more heavily
            week_ratio = week_active / total
            month_ratio = month_active / total
            quarter_ratio = quarter_active / total
            
            activity_score = (
                week_ratio * 0.5 +
                month_ratio * 0.3 +
                quarter_ratio * 0.2
            )
            
            # Boost score if actively creating new docs
            if new_last_month > total * 0.05:  # 5% growth
                activity_score = min(1.0, activity_score * 1.2)
        
        # Determine status
        if activity_score < 0.1:
            status = 'critical'
        elif activity_score < 0.3:
            status = 'warning'
        else:
            status = 'good'
        
        # Generate recommendations
        recommendations = []
        if week_active < total * 0.1:
            recommendations.append("Knowledge base is underutilized - review and update content")
        if new_last_month == 0:
            recommendations.append("No new documents in the last month - consider capturing new knowledge")
        
        stale_count = total - quarter_active
        if stale_count > total * 0.5:
            recommendations.append(f"Review {stale_count} documents not accessed in 90+ days")
        
        return HealthMetric(
            name='activity',
            value=activity_score,
            weight=self.WEIGHTS['activity'],
            status=status,
            details=f"{week_active} docs active this week, {new_last_month} new this month",
            recommendations=recommendations
        )
    
    def _calculate_quality_health(self) -> HealthMetric:
        """Calculate content quality health metric."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get quality indicators
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN LENGTH(content) < 50 THEN 1 END) as very_short,
                COUNT(CASE WHEN LENGTH(content) < 200 THEN 1 END) as short,
                COUNT(CASE WHEN LENGTH(title) < 10 THEN 1 END) as poor_titles,
                COUNT(*) as total,
                AVG(LENGTH(content)) as avg_length
            FROM documents
            WHERE is_deleted = 0
        """)
        
        result = cursor.fetchone()
        very_short = result[0]
        short = result[1]
        poor_titles = result[2]
        total = result[3]
        avg_length = result[4] or 0
        
        conn.close()
        
        if total == 0:
            quality_score = 1.0
        else:
            # Calculate quality factors
            short_ratio = short / total
            very_short_ratio = very_short / total
            poor_title_ratio = poor_titles / total
            
            # Base quality score
            quality_score = 1.0
            quality_score -= very_short_ratio * 0.5  # Heavy penalty for very short
            quality_score -= (short_ratio - very_short_ratio) * 0.2  # Lighter penalty for short
            quality_score -= poor_title_ratio * 0.3  # Penalty for poor titles
            
            quality_score = max(0.0, quality_score)
        
        # Determine status
        if quality_score < 0.5:
            status = 'critical'
        elif quality_score < 0.7:
            status = 'warning'
        else:
            status = 'good'
        
        # Generate recommendations
        recommendations = []
        if very_short > 0:
            recommendations.append(f"Review {very_short} very short documents (<50 chars)")
            recommendations.append(f"Remove empty documents with 'emdx clean empty'")
        if poor_titles > total * 0.1:
            recommendations.append(f"Improve titles for {poor_titles} documents")
        if avg_length < 500:
            recommendations.append("Consider adding more detail to documents")
        
        return HealthMetric(
            name='quality',
            value=quality_score,
            weight=self.WEIGHTS['quality'],
            status=status,
            details=f"Avg length: {int(avg_length)} chars, {very_short} very short docs",
            recommendations=recommendations
        )
    
    def _calculate_growth_health(self) -> HealthMetric:
        """Calculate growth trend health metric."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get growth over different periods
        now = datetime.now()
        periods = [
            ('week', 7),
            ('month', 30),
            ('quarter', 90),
            ('year', 365)
        ]
        
        growth_data = {}
        for period_name, days in periods:
            cutoff = now - timedelta(days=days)
            cursor.execute("""
                SELECT COUNT(*) 
                FROM documents 
                WHERE is_deleted = 0 
                AND datetime(created_at) > ?
            """, (cutoff.isoformat(),))
            growth_data[period_name] = cursor.fetchone()[0]
        
        # Get total for context
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
        total = cursor.fetchone()[0]
        
        conn.close()
        
        # Calculate growth score
        if total == 0:
            growth_score = 0.5
        else:
            # Look at recent growth relative to total
            week_growth = growth_data['week'] / max(total * 0.02, 1)  # Expect 2% weekly
            month_growth = growth_data['month'] / max(total * 0.08, 1)  # Expect 8% monthly
            
            # Combine scores
            growth_score = min(1.0, (week_growth * 0.6 + month_growth * 0.4))
            
            # Penalize if no recent growth
            if growth_data['week'] == 0:
                growth_score *= 0.5
        
        # Determine status
        if growth_score < 0.2:
            status = 'critical'
        elif growth_score < 0.5:
            status = 'warning'
        else:
            status = 'good'
        
        # Generate recommendations
        recommendations = []
        if growth_data['week'] == 0:
            recommendations.append("No new documents this week - capture recent learnings")
        if growth_data['month'] < 5:
            recommendations.append("Low growth rate - consider regular knowledge capture habits")
        if total > 1000 and growth_data['year'] > total * 0.5:
            recommendations.append("Rapid growth detected - ensure proper organization")
        
        return HealthMetric(
            name='growth',
            value=growth_score,
            weight=self.WEIGHTS['growth'],
            status=status,
            details=f"+{growth_data['week']} this week, +{growth_data['month']} this month",
            recommendations=recommendations
        )
    
    def _calculate_connectivity_health(self) -> HealthMetric:
        """
        Calculate health based on document connectivity and knowledge graph structure.
        
        Good connectivity means:
        - Low percentage of orphan documents
        - Reasonable clustering (not too fragmented)
        - Good distribution of connections
        """
        from ..analysis.graph import GraphAnalyzer
        
        # Get graph data
        analyzer = GraphAnalyzer(self.db_path)
        graph_data = analyzer.get_document_graph(
            min_similarity=20.0,  # Include weak connections
            include_orphans=True
        )
        
        metrics = graph_data['metadata']['metrics']
        node_count = graph_data['metadata']['node_count']
        edge_count = graph_data['metadata']['edge_count']
        
        if node_count == 0:
            return HealthMetric(
                name='connectivity',
                value=0.0,
                weight=self.WEIGHTS['connectivity'],
                status='critical',
                details='No documents in knowledge base',
                recommendations=['Start adding documents to build knowledge graph']
            )
        
        # Calculate connectivity metrics
        orphan_ratio = metrics['orphan_count'] / node_count if node_count > 0 else 1.0
        density = metrics['density']
        clustering = metrics['clustering_coefficient']
        components = metrics['connected_components']
        
        # Calculate sub-scores
        
        # 1. Orphan score (fewer orphans is better)
        orphan_score = max(0, 1.0 - orphan_ratio)
        
        # 2. Component score (fewer components relative to nodes is better)
        component_ratio = len(components) / node_count if node_count > 0 else 1.0
        component_score = max(0, 1.0 - component_ratio * 2)  # Penalize fragmentation
        
        # 3. Density score (moderate density is best - not too sparse, not too dense)
        if density < 0.05:  # Too sparse
            density_score = density * 20  # Scale up to 0-1
        elif density > 0.3:  # Too dense
            density_score = max(0, 1.0 - (density - 0.3) * 2)
        else:  # Good range
            density_score = 1.0
        
        # 4. Distribution score (check if connections are well-distributed)
        centrality_values = [c['weighted_degree'] for c in metrics['centrality'].values()]
        if centrality_values:
            # Check standard deviation - lower is better (more even distribution)
            if len(centrality_values) > 1:
                mean_centrality = statistics.mean(centrality_values)
                std_centrality = statistics.stdev(centrality_values)
                cv = std_centrality / mean_centrality if mean_centrality > 0 else 0
                distribution_score = max(0, 1.0 - cv)
            else:
                distribution_score = 0.5
        else:
            distribution_score = 0.0
        
        # Combine scores with weights
        connectivity_score = (
            orphan_score * 0.4 +       # Orphans are most important
            component_score * 0.3 +     # Fragmentation is important
            density_score * 0.2 +       # Density matters less
            distribution_score * 0.1    # Distribution is least important
        )
        
        # Determine status
        if connectivity_score < 0.4:
            status = 'critical'
        elif connectivity_score < 0.7:
            status = 'warning'
        else:
            status = 'good'
        
        # Generate recommendations
        recommendations = []
        
        if orphan_ratio > 0.3:
            recommendations.append(f"High orphan rate ({orphan_ratio:.1%}) - add tags to connect isolated documents")
        
        if len(components) > node_count * 0.2:
            recommendations.append(f"Knowledge is fragmented ({len(components)} clusters) - find connections between topics")
        
        if density < 0.02:
            recommendations.append("Very sparse graph - enrich documents with more tags and cross-references")
        elif density > 0.3:
            recommendations.append("Very dense graph - consider more specific tagging to clarify relationships")
        
        bridge_count = len(metrics.get('bridge_nodes', []))
        if bridge_count > 0 and bridge_count < 5:
            recommendations.append(f"Key bridge documents: {', '.join(str(b) for b in metrics['bridge_nodes'][:3])}")
        
        # Build details string
        details_parts = []
        details_parts.append(f"{orphan_ratio:.0%} orphans")
        details_parts.append(f"{len(components)} clusters")
        details_parts.append(f"{density:.3f} density")
        
        return HealthMetric(
            name='connectivity',
            value=connectivity_score,
            weight=self.WEIGHTS['connectivity'],
            status=status,
            details=', '.join(details_parts),
            recommendations=recommendations
        )
    
    def get_project_health(self, limit: Optional[int] = None) -> List[ProjectHealth]:
        """
        Get health metrics for each project.
        
        Args:
            limit: Maximum number of projects to return
            
        Returns:
            List of ProjectHealth objects sorted by overall score
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get all projects with basic stats
        cursor.execute("""
            SELECT 
                d.project,
                COUNT(*) as doc_count,
                COUNT(DISTINCT dt.document_id) as tagged_count,
                AVG(julianday('now') - julianday(d.created_at)) as avg_age,
                SUM(CASE WHEN julianday('now') - julianday(d.accessed_at) < 30 THEN 1 ELSE 0 END) as recent_access
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.document_id
            WHERE d.is_deleted = 0 AND d.project IS NOT NULL
            GROUP BY d.project
            ORDER BY doc_count DESC
        """)
        
        projects = []
        for row in cursor.fetchall():
            project = row[0]
            doc_count = row[1]
            tagged_count = row[2]
            avg_age = row[3] or 0
            recent_access = row[4]
            
            # Calculate metrics
            tag_coverage = tagged_count / doc_count if doc_count > 0 else 0
            activity_score = recent_access / doc_count if doc_count > 0 else 0
            
            # Simple organization score based on doc count
            if doc_count < 5:
                org_score = 0.5  # Too small
            elif doc_count > 100:
                org_score = 0.7  # Too large
            else:
                org_score = 1.0
            
            # Overall project score
            overall = (
                tag_coverage * 0.4 +
                activity_score * 0.3 +
                org_score * 0.3
            )
            
            projects.append(ProjectHealth(
                project=project,
                document_count=doc_count,
                tag_coverage=tag_coverage,
                avg_document_age=int(avg_age),
                activity_score=activity_score,
                organization_score=org_score,
                overall_score=overall
            ))
        
        conn.close()
        
        # Sort by overall score
        projects.sort(key=lambda p: p.overall_score, reverse=True)
        
        if limit:
            return projects[:limit]
        return projects
    
    def get_maintenance_recommendations(self) -> List[Tuple[str, str, str]]:
        """
        Get prioritized maintenance recommendations.
        
        Returns:
            List of tuples (priority, task, command)
        """
        health = self.calculate_overall_health()
        recommendations = []
        
        # Collect all recommendations with priority
        for metric_name, metric in health['metrics'].items():
            if metric.status in ['warning', 'critical']:
                priority = 'HIGH' if metric.status == 'critical' else 'MEDIUM'
                for rec in metric.recommendations:
                    # Extract command if present
                    if "'" in rec and "emdx" in rec:
                        import re
                        match = re.search(r"'(emdx[^']+)'", rec)
                        command = match.group(1) if match else ""
                    else:
                        command = ""
                    
                    recommendations.append((priority, rec, command))
        
        # Sort by priority
        priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        recommendations.sort(key=lambda x: priority_order.get(x[0], 3))
        
        return recommendations
    
    def generate_health_report(self) -> str:
        """Generate a comprehensive health report in markdown format."""
        health = self.calculate_overall_health()
        stats = health['statistics']
        
        # Build report
        report = []
        report.append("# EMDX Knowledge Base Health Report")
        report.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
        
        # Overall health
        score = health['overall_score']
        status_emoji = "🟢" if score >= 0.7 else "🟡" if score >= 0.4 else "🔴"
        report.append(f"## Overall Health: {status_emoji} {score:.0%}")
        report.append(f"\n**Status**: {health['overall_status'].upper()}\n")
        
        # Statistics
        report.append("## Statistics")
        report.append(f"- **Total Documents**: {stats['total_documents']:,}")
        report.append(f"- **Projects**: {stats['total_projects']}")
        report.append(f"- **Tags**: {stats['total_tags']}")
        report.append(f"- **Database Size**: {stats['database_size_mb']} MB\n")
        
        # Metrics breakdown
        report.append("## Health Metrics")
        for metric_name, metric in health['metrics'].items():
            status_emoji = "🟢" if metric.status == 'good' else "🟡" if metric.status == 'warning' else "🔴"
            report.append(f"\n### {metric_name.replace('_', ' ').title()} {status_emoji}")
            report.append(f"- **Score**: {metric.value:.0%}")
            report.append(f"- **Status**: {metric.status}")
            report.append(f"- **Details**: {metric.details}")
            
            if metric.recommendations:
                report.append("- **Recommendations**:")
                for rec in metric.recommendations:
                    report.append(f"  - {rec}")
        
        # Top projects
        report.append("\n## Project Health (Top 5)")
        projects = self.get_project_health(limit=5)
        if projects:
            report.append("| Project | Docs | Tag Coverage | Activity | Score |")
            report.append("|---------|------|--------------|----------|-------|")
            for p in projects:
                report.append(
                    f"| {p.project} | {p.document_count} | "
                    f"{p.tag_coverage:.0%} | {p.activity_score:.0%} | "
                    f"{p.overall_score:.0%} |"
                )
        
        # Action items
        report.append("\n## Recommended Actions")
        recommendations = self.get_maintenance_recommendations()
        if recommendations:
            for priority, task, command in recommendations[:10]:  # Top 10
                report.append(f"- **[{priority}]** {task}")
                if command:
                    report.append(f"  ```bash\n  {command}\n  ```")
        else:
            report.append("✨ No immediate actions required!")
        
        return "\n".join(report)