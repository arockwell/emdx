#!/usr/bin/env python3
"""
Comprehensive analysis tool for EMDX knowledge base.
Provides insights into document patterns, tag usage, project distribution, and more.
"""

import sqlite3
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
import json
from typing import Dict, List, Tuple, Any

class KnowledgeBaseAnalyzer:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.expanduser("~/.local/share/emdx/emdx.db")
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
    
    def get_overview_stats(self) -> Dict[str, Any]:
        """Get basic statistics about the knowledge base"""
        cursor = self.conn.cursor()
        
        # Total documents
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
        total_docs = cursor.fetchone()[0]
        
        # Total deleted
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 1")
        deleted_docs = cursor.fetchone()[0]
        
        # Total views
        cursor.execute("SELECT SUM(access_count) FROM documents WHERE is_deleted = 0")
        total_views = cursor.fetchone()[0] or 0
        
        # Most viewed
        cursor.execute("""
            SELECT title, access_count, id 
            FROM documents 
            WHERE is_deleted = 0 
            ORDER BY access_count DESC 
            LIMIT 10
        """)
        most_viewed = cursor.fetchall()
        
        # Most recent
        cursor.execute("""
            SELECT title, created_at, id 
            FROM documents 
            WHERE is_deleted = 0 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        most_recent = cursor.fetchall()
        
        # Projects
        cursor.execute("""
            SELECT project, COUNT(*) as count 
            FROM documents 
            WHERE is_deleted = 0 
            GROUP BY project 
            ORDER BY count DESC
        """)
        projects = cursor.fetchall()
        
        return {
            "total_documents": total_docs,
            "deleted_documents": deleted_docs,
            "total_views": total_views,
            "average_views": total_views / total_docs if total_docs > 0 else 0,
            "most_viewed": [dict(row) for row in most_viewed],
            "most_recent": [dict(row) for row in most_recent],
            "projects": [dict(row) for row in projects]
        }
    
    def analyze_tags(self) -> Dict[str, Any]:
        """Analyze tag usage patterns"""
        cursor = self.conn.cursor()
        
        # Get all tags with counts
        cursor.execute("""
            SELECT t.emoji, t.name, COUNT(dt.document_id) as count
            FROM tags t
            LEFT JOIN document_tags dt ON t.id = dt.tag_id
            LEFT JOIN documents d ON dt.document_id = d.id
            WHERE d.is_deleted = 0 OR d.is_deleted IS NULL
            GROUP BY t.id
            ORDER BY count DESC
        """)
        tags = cursor.fetchall()
        
        # Documents without tags
        cursor.execute("""
            SELECT COUNT(*) 
            FROM documents d
            WHERE d.is_deleted = 0 
            AND NOT EXISTS (
                SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
            )
        """)
        untagged = cursor.fetchone()[0]
        
        # Tag combinations
        cursor.execute("""
            SELECT d.id, GROUP_CONCAT(t.emoji || ':' || t.name) as tags
            FROM documents d
            JOIN document_tags dt ON d.id = dt.document_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0
            GROUP BY d.id
        """)
        combinations = Counter()
        for row in cursor.fetchall():
            tag_set = frozenset(row[1].split(','))
            if len(tag_set) > 1:
                combinations[tag_set] += 1
        
        return {
            "tags": [dict(row) for row in tags],
            "total_tags": len(tags),
            "untagged_documents": untagged,
            "top_combinations": combinations.most_common(20)
        }
    
    def analyze_content_patterns(self) -> Dict[str, Any]:
        """Analyze content patterns and document types"""
        cursor = self.conn.cursor()
        
        # Title patterns
        cursor.execute("""
            SELECT title FROM documents WHERE is_deleted = 0
        """)
        titles = [row[0] for row in cursor.fetchall()]
        
        title_patterns = Counter()
        for title in titles:
            if title.startswith("Gameplan:"):
                title_patterns["gameplan"] += 1
            elif title.startswith("Analysis:"):
                title_patterns["analysis"] += 1
            elif title.startswith("Bug:"):
                title_patterns["bug"] += 1
            elif title.startswith("Feature:"):
                title_patterns["feature"] += 1
            elif title.startswith("Note:"):
                title_patterns["note"] += 1
            else:
                title_patterns["other"] += 1
        
        # Content length distribution
        cursor.execute("""
            SELECT LENGTH(content) as length
            FROM documents 
            WHERE is_deleted = 0
        """)
        lengths = [row[0] for row in cursor.fetchall()]
        
        length_dist = {
            "very_short": sum(1 for l in lengths if l < 100),
            "short": sum(1 for l in lengths if 100 <= l < 500),
            "medium": sum(1 for l in lengths if 500 <= l < 2000),
            "long": sum(1 for l in lengths if 2000 <= l < 5000),
            "very_long": sum(1 for l in lengths if l >= 5000)
        }
        
        return {
            "title_patterns": dict(title_patterns),
            "length_distribution": length_dist,
            "average_length": sum(lengths) / len(lengths) if lengths else 0
        }
    
    def analyze_temporal_patterns(self) -> Dict[str, Any]:
        """Analyze when documents are created and accessed"""
        cursor = self.conn.cursor()
        
        # Creation patterns by month
        cursor.execute("""
            SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
            FROM documents
            WHERE is_deleted = 0
            GROUP BY month
            ORDER BY month
        """)
        creation_by_month = cursor.fetchall()
        
        # Access patterns
        cursor.execute("""
            SELECT strftime('%Y-%m', accessed_at) as month, COUNT(*) as count
            FROM documents
            WHERE is_deleted = 0 AND accessed_at IS NOT NULL
            GROUP BY month
            ORDER BY month
        """)
        access_by_month = cursor.fetchall()
        
        # Hour of day patterns
        cursor.execute("""
            SELECT strftime('%H', created_at) as hour, COUNT(*) as count
            FROM documents
            WHERE is_deleted = 0
            GROUP BY hour
            ORDER BY hour
        """)
        creation_by_hour = cursor.fetchall()
        
        return {
            "creation_by_month": [dict(row) for row in creation_by_month],
            "access_by_month": [dict(row) for row in access_by_month],
            "creation_by_hour": [dict(row) for row in creation_by_hour]
        }
    
    def analyze_project_health(self) -> Dict[str, Any]:
        """Analyze project success rates and patterns"""
        cursor = self.conn.cursor()
        
        # Success rate by project
        cursor.execute("""
            SELECT 
                d.project,
                COUNT(CASE WHEN t.name = 'success' THEN 1 END) as success_count,
                COUNT(CASE WHEN t.name = 'failed' THEN 1 END) as failed_count,
                COUNT(CASE WHEN t.name = 'blocked' THEN 1 END) as blocked_count,
                COUNT(CASE WHEN t.name = 'active' THEN 1 END) as active_count,
                COUNT(*) as total
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.document_id
            LEFT JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0
            GROUP BY d.project
        """)
        project_health = cursor.fetchall()
        
        return {
            "project_health": [dict(row) for row in project_health]
        }
    
    def generate_report(self) -> str:
        """Generate comprehensive analysis report"""
        overview = self.get_overview_stats()
        tags = self.analyze_tags()
        content = self.analyze_content_patterns()
        temporal = self.analyze_temporal_patterns()
        health = self.analyze_project_health()
        
        report = []
        report.append("# EMDX Knowledge Base Analysis Report")
        report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("\n## Overview Statistics")
        report.append(f"- Total Documents: {overview['total_documents']}")
        report.append(f"- Deleted Documents: {overview['deleted_documents']}")
        report.append(f"- Total Views: {overview['total_views']}")
        report.append(f"- Average Views per Document: {overview['average_views']:.1f}")
        
        report.append("\n### Projects Distribution")
        for proj in overview['projects'][:10]:
            report.append(f"- {proj['project'] or 'No Project'}: {proj['count']} documents")
        
        report.append("\n### Most Viewed Documents")
        for doc in overview['most_viewed'][:5]:
            report.append(f"- [{doc['id']}] {doc['title']}: {doc['access_count']} views")
        
        report.append("\n## Tag Analysis")
        report.append(f"- Total Unique Tags: {tags['total_tags']}")
        report.append(f"- Untagged Documents: {tags['untagged_documents']}")
        
        report.append("\n### Top Tags")
        for tag in tags['tags'][:20]:
            if tag['count'] > 0:
                report.append(f"- {tag['emoji']} {tag['name']}: {tag['count']} documents")
        
        report.append("\n## Content Analysis")
        report.append("\n### Document Type Distribution")
        for pattern, count in content['title_patterns'].items():
            report.append(f"- {pattern.capitalize()}: {count}")
        
        report.append("\n### Document Length Distribution")
        for size, count in content['length_distribution'].items():
            report.append(f"- {size.replace('_', ' ').capitalize()}: {count}")
        report.append(f"- Average Length: {content['average_length']:.0f} characters")
        
        report.append("\n## Temporal Patterns")
        report.append("\n### Recent Activity (Last 3 Months)")
        recent_months = temporal['creation_by_month'][-3:] if temporal['creation_by_month'] else []
        for month in recent_months:
            report.append(f"- {month['month']}: {month['count']} documents created")
        
        report.append("\n## Project Health Analysis")
        report.append("\n### Success Rates by Project")
        for proj in health['project_health']:
            if proj['total'] > 5:  # Only show projects with meaningful data
                success_rate = (proj['success_count'] / proj['total'] * 100) if proj['total'] > 0 else 0
                report.append(f"\n**{proj['project'] or 'No Project'}** ({proj['total']} docs)")
                report.append(f"  - Success: {proj['success_count']} ({success_rate:.1f}%)")
                report.append(f"  - Failed: {proj['failed_count']}")
                report.append(f"  - Blocked: {proj['blocked_count']}")
                report.append(f"  - Active: {proj['active_count']}")
        
        return "\n".join(report)
    
    def save_json_export(self, filepath: str):
        """Export all analysis data as JSON"""
        data = {
            "overview": self.get_overview_stats(),
            "tags": self.analyze_tags(),
            "content": self.analyze_content_patterns(),
            "temporal": self.analyze_temporal_patterns(),
            "health": self.analyze_project_health(),
            "generated_at": datetime.now().isoformat()
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)

if __name__ == "__main__":
    analyzer = KnowledgeBaseAnalyzer()
    
    # Generate and print report
    report = analyzer.generate_report()
    print(report)
    
    # Save JSON export
    json_path = "emdx_analysis_export.json"
    analyzer.save_json_export(json_path)
    print(f"\n\nDetailed JSON export saved to: {json_path}")