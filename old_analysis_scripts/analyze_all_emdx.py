#!/usr/bin/env python3
"""
Comprehensive EMDX Knowledge Base Analysis
Generates detailed insights, recommendations, and visualizations
"""

import sqlite3
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import re

# Rich imports for beautiful output
try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.progress import track
    from rich import box
    from rich.columns import Columns
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False
    print("Warning: Rich not installed. Install with: pip install rich")

console = Console() if HAS_RICH else None


class ComprehensiveAnalyzer:
    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = self.find_database()
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.data = {}  # Store all analysis data
        
    def find_database(self) -> str:
        """Find the EMDX database file"""
        possible_paths = [
            "~/.config/emdx/knowledge.db",
            "~/.emdx.db",
            "~/.local/share/emdx/emdx.db",
            "~/Library/Application Support/emdx/emdx.db",
        ]
        
        for path_str in possible_paths:
            path = Path(os.path.expanduser(path_str))
            if path.exists():
                return str(path)
        
        raise FileNotFoundError("Could not find EMDX database!")
    
    def analyze_all(self):
        """Run all analysis modules"""
        if console:
            console.print("\n[bold cyan]🔍 Analyzing EMDX Knowledge Base...[/bold cyan]\n")
        
        # Run all analysis modules
        self.data['overview'] = self.get_overview()
        self.data['projects'] = self.analyze_projects()
        self.data['content'] = self.analyze_content()
        self.data['tags'] = self.analyze_tags()
        self.data['temporal'] = self.analyze_temporal()
        self.data['quality'] = self.analyze_quality()
        self.data['gaps'] = self.identify_gaps()
        self.data['insights'] = self.generate_insights()
        self.data['metadata'] = {
            'generated_at': datetime.now().isoformat(),
            'database_path': self.db_path
        }
    
    def get_overview(self) -> Dict[str, Any]:
        """Get high-level overview statistics"""
        cursor = self.conn.cursor()
        
        # Basic counts
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
        total_docs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 1")
        deleted_docs = cursor.fetchone()[0]
        
        cursor.execute("SELECT SUM(access_count) FROM documents WHERE is_deleted = 0")
        total_views = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(DISTINCT project) FROM documents WHERE is_deleted = 0")
        total_projects = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM tags")
        total_tags = cursor.fetchone()[0]
        
        # Date range
        cursor.execute("""
            SELECT MIN(created_at) as first, MAX(created_at) as last 
            FROM documents WHERE is_deleted = 0
        """)
        dates = cursor.fetchone()
        
        # Most viewed
        cursor.execute("""
            SELECT id, title, access_count 
            FROM documents 
            WHERE is_deleted = 0 
            ORDER BY access_count DESC 
            LIMIT 5
        """)
        most_viewed = [dict(row) for row in cursor.fetchall()]
        
        return {
            'total_documents': total_docs,
            'deleted_documents': deleted_docs,
            'total_views': total_views,
            'average_views': total_views / total_docs if total_docs > 0 else 0,
            'total_projects': total_projects,
            'total_tags': total_tags,
            'date_range': {
                'first': dates['first'],
                'last': dates['last']
            },
            'most_viewed': most_viewed,
            'daily_average': total_docs / 8 if dates else 0  # Hardcoded 8 days for now
        }
    
    def analyze_projects(self) -> Dict[str, Any]:
        """Analyze project health and metrics"""
        cursor = self.conn.cursor()
        
        # Project statistics
        cursor.execute("""
            SELECT 
                d.project,
                COUNT(DISTINCT d.id) as total_docs,
                SUM(d.access_count) as total_views,
                AVG(d.access_count) as avg_views,
                COUNT(DISTINCT CASE WHEN t.name = 'gameplan' THEN d.id END) as gameplans,
                COUNT(DISTINCT CASE WHEN t.name = 'success' THEN d.id END) as successes,
                COUNT(DISTINCT CASE WHEN t.name = 'failed' THEN d.id END) as failures,
                COUNT(DISTINCT CASE WHEN t.name = 'blocked' THEN d.id END) as blocked,
                COUNT(DISTINCT CASE WHEN t.name = 'active' THEN d.id END) as active,
                MAX(d.created_at) as last_activity
            FROM documents d
            LEFT JOIN document_tags dt ON d.id = dt.document_id
            LEFT JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0
            GROUP BY d.project
            ORDER BY total_docs DESC
        """)
        
        projects = []
        for row in cursor.fetchall():
            project = dict(row)
            
            # Calculate health score (0-5 stars)
            score = 0
            if project['total_docs'] > 0:
                score += 1
            if project['avg_views'] > 10:
                score += 1
            if project['gameplans'] > 0:
                score += 1
            if project['successes'] > 0:
                score += 1
            if project['active'] > 0:
                score += 1
            
            project['health_score'] = score
            project['success_rate'] = (project['successes'] / project['gameplans'] * 100) if project['gameplans'] > 0 else 0
            
            projects.append(project)
        
        return {
            'projects': projects,
            'total_projects': len(projects),
            'active_projects': sum(1 for p in projects if p['active'] > 0),
            'healthy_projects': sum(1 for p in projects if p['health_score'] >= 3)
        }
    
    def analyze_content(self) -> Dict[str, Any]:
        """Analyze content patterns and quality"""
        cursor = self.conn.cursor()
        
        # Get all documents
        cursor.execute("""
            SELECT id, title, content, LENGTH(content) as length, access_count
            FROM documents 
            WHERE is_deleted = 0
        """)
        
        docs = cursor.fetchall()
        
        # Document type classification
        doc_types = Counter()
        quality_scores = []
        empty_docs = []
        hot_topics = defaultdict(lambda: {'count': 0, 'views': 0})
        
        for doc in docs:
            # Classify by title
            title = doc['title']
            if title.startswith('Gameplan:'):
                doc_types['gameplan'] += 1
            elif title.startswith('Analysis:'):
                doc_types['analysis'] += 1
            elif title.startswith('Bug:'):
                doc_types['bug'] += 1
            elif title.startswith('Feature:'):
                doc_types['feature'] += 1
            elif title.startswith('Summary:'):
                doc_types['summary'] += 1
            elif title.startswith('Note:') or 'Quick Note' in title:
                doc_types['note'] += 1
            elif title.startswith('Issue'):
                doc_types['issue'] += 1
            elif title.startswith('PR '):
                doc_types['pr'] += 1
            else:
                doc_types['other'] += 1
            
            # Quality scoring
            length = doc['length']
            if length < 100:
                quality_scores.append(1)
                if length < 10:
                    empty_docs.append({'id': doc['id'], 'title': title})
            elif length < 500:
                quality_scores.append(2)
            elif length < 2000:
                quality_scores.append(3)
            elif length < 5000:
                quality_scores.append(4)
            else:
                quality_scores.append(5)
            
            # Extract topics (simple keyword extraction)
            content_lower = (title + ' ' + (doc['content'] or '')).lower()
            topics = ['git', 'vim', 'browser', 'file', 'tag', 'modal', 'tui', 'claude', 'test', 'fix']
            for topic in topics:
                if topic in content_lower:
                    hot_topics[topic]['count'] += 1
                    hot_topics[topic]['views'] += doc['access_count']
        
        # Sort hot topics by views
        hot_topics_list = [
            {'topic': k, 'count': v['count'], 'views': v['views']} 
            for k, v in sorted(hot_topics.items(), key=lambda x: x[1]['views'], reverse=True)
        ]
        
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
        
        return {
            'document_types': dict(doc_types),
            'quality_metrics': {
                'average_score': avg_quality,
                'distribution': Counter(quality_scores),
                'empty_documents': len(empty_docs),
                'empty_list': empty_docs[:10]  # First 10 empty docs
            },
            'hot_topics': hot_topics_list[:10],
            'content_stats': {
                'average_length': sum(d['length'] for d in docs) / len(docs) if docs else 0,
                'total_characters': sum(d['length'] for d in docs)
            }
        }
    
    def analyze_tags(self) -> Dict[str, Any]:
        """Analyze tag usage and workflows"""
        cursor = self.conn.cursor()
        
        # Tag usage
        cursor.execute("""
            SELECT 
                t.name,
                COUNT(dt.document_id) as usage_count,
                GROUP_CONCAT(DISTINCT d.project) as projects
            FROM tags t
            LEFT JOIN document_tags dt ON t.id = dt.tag_id
            LEFT JOIN documents d ON dt.document_id = d.id AND d.is_deleted = 0
            GROUP BY t.id
            ORDER BY usage_count DESC
        """)
        
        tags = [dict(row) for row in cursor.fetchall()]
        
        # Tag combinations
        cursor.execute("""
            SELECT d.id, GROUP_CONCAT(t.name) as tag_combo
            FROM documents d
            JOIN document_tags dt ON d.id = dt.document_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0
            GROUP BY d.id
            HAVING COUNT(dt.tag_id) > 1
        """)
        
        combos = Counter()
        workflows = defaultdict(int)
        
        for row in cursor.fetchall():
            if row['tag_combo']:
                tags_list = sorted(row['tag_combo'].split(','))
                combos[', '.join(tags_list[:3])] += 1
                
                # Detect workflows
                tag_set = set(tags_list)
                if '🎯' in tag_set and '🚀' in tag_set:
                    workflows['gameplan→active'] += 1
                if '🚀' in tag_set and '✅' in tag_set:
                    workflows['active→success'] += 1
                if '🚀' in tag_set and '🚧' in tag_set:
                    workflows['active→blocked'] += 1
                if '🐛' in tag_set and '✅' in tag_set:
                    workflows['bug→fixed'] += 1
        
        # Untagged documents
        cursor.execute("""
            SELECT COUNT(*) 
            FROM documents d
            WHERE d.is_deleted = 0 
            AND NOT EXISTS (
                SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
            )
        """)
        untagged = cursor.fetchone()[0]
        
        return {
            'tags': tags[:30],
            'total_tags': len(tags),
            'untagged_count': untagged,
            'untagged_percentage': (untagged / self.data['overview']['total_documents'] * 100) if self.data.get('overview') else 0,
            'popular_combinations': combos.most_common(15),
            'workflows': dict(workflows),
            'tag_diversity': len([t for t in tags if t['usage_count'] > 5])  # Tags used more than 5 times
        }
    
    def analyze_temporal(self) -> Dict[str, Any]:
        """Analyze temporal patterns"""
        cursor = self.conn.cursor()
        
        # Daily activity
        cursor.execute("""
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as docs_created,
                COUNT(CASE WHEN LENGTH(content) > 1000 THEN 1 END) as quality_docs
            FROM documents
            WHERE is_deleted = 0
            GROUP BY DATE(created_at)
            ORDER BY date
        """)
        
        daily_activity = [dict(row) for row in cursor.fetchall()]
        
        # Hour patterns
        cursor.execute("""
            SELECT 
                strftime('%H', created_at) as hour,
                COUNT(*) as count
            FROM documents
            WHERE is_deleted = 0
            GROUP BY hour
            ORDER BY hour
        """)
        
        hour_pattern = [dict(row) for row in cursor.fetchall()]
        
        # Recent momentum (last 3 days vs previous 3 days)
        cursor.execute("""
            SELECT 
                CASE 
                    WHEN DATE(created_at) >= DATE('now', '-3 days') THEN 'recent'
                    WHEN DATE(created_at) >= DATE('now', '-6 days') THEN 'previous'
                END as period,
                COUNT(*) as count
            FROM documents
            WHERE is_deleted = 0 
            AND DATE(created_at) >= DATE('now', '-6 days')
            GROUP BY period
        """)
        
        momentum = dict(cursor.fetchall())
        momentum_change = 0
        if momentum.get('previous', 0) > 0:
            momentum_change = ((momentum.get('recent', 0) - momentum.get('previous', 0)) / momentum.get('previous', 0) * 100)
        
        return {
            'daily_activity': daily_activity,
            'hour_pattern': hour_pattern,
            'peak_hour': max(hour_pattern, key=lambda x: x['count'])['hour'] if hour_pattern else None,
            'momentum': {
                'recent_3_days': momentum.get('recent', 0),
                'previous_3_days': momentum.get('previous', 0),
                'change_percentage': momentum_change
            }
        }
    
    def analyze_quality(self) -> Dict[str, Any]:
        """Analyze content quality metrics"""
        cursor = self.conn.cursor()
        
        # Documents needing attention
        cursor.execute("""
            SELECT 
                id, 
                title, 
                LENGTH(content) as length,
                access_count,
                created_at,
                project
            FROM documents
            WHERE is_deleted = 0
            AND (
                LENGTH(content) < 100 
                OR (access_count > 50 AND LENGTH(content) < 500)
                OR (project IS NULL)
            )
            ORDER BY access_count DESC
            LIMIT 20
        """)
        
        needs_attention = [dict(row) for row in cursor.fetchall()]
        
        # Stale active items
        cursor.execute("""
            SELECT 
                d.id,
                d.title,
                d.created_at,
                d.project,
                julianday('now') - julianday(d.created_at) as days_old
            FROM documents d
            JOIN document_tags dt ON d.id = dt.document_id
            JOIN tags t ON dt.tag_id = t.id
            WHERE d.is_deleted = 0
            AND t.name = 'active'
            AND julianday('now') - julianday(d.created_at) > 3
            ORDER BY days_old DESC
        """)
        
        stale_active = [dict(row) for row in cursor.fetchall()]
        
        return {
            'needs_attention': needs_attention,
            'stale_active_items': stale_active,
            'quality_issues': {
                'empty_documents': len([d for d in needs_attention if d['length'] < 10]),
                'high_view_low_content': len([d for d in needs_attention if d['access_count'] > 50 and d['length'] < 500]),
                'no_project': len([d for d in needs_attention if not d['project']])
            }
        }
    
    def identify_gaps(self) -> Dict[str, Any]:
        """Identify knowledge gaps and missing elements"""
        gaps = []
        
        # Projects without gameplans
        for project in self.data['projects']['projects']:
            if project['total_docs'] > 5 and project['gameplans'] == 0:
                gaps.append({
                    'type': 'missing_gameplan',
                    'project': project['project'],
                    'severity': 'high',
                    'recommendation': f"Create gameplans for {project['project']} project"
                })
        
        # High untagged percentage
        if self.data['tags']['untagged_percentage'] > 50:
            gaps.append({
                'type': 'poor_tagging',
                'severity': 'high',
                'recommendation': f"Tag {self.data['tags']['untagged_count']} untagged documents"
            })
        
        # Projects with no success tracking
        for project in self.data['projects']['projects']:
            if project['gameplans'] > 3 and project['successes'] == 0:
                gaps.append({
                    'type': 'no_success_tracking',
                    'project': project['project'],
                    'severity': 'medium',
                    'recommendation': f"Add success/failure tags to completed gameplans in {project['project']}"
                })
        
        # Stale active items
        if len(self.data['quality']['stale_active_items']) > 5:
            gaps.append({
                'type': 'stale_work',
                'severity': 'medium',
                'recommendation': f"Review {len(self.data['quality']['stale_active_items'])} stale active items"
            })
        
        return {
            'gaps': gaps,
            'total_gaps': len(gaps),
            'high_severity': len([g for g in gaps if g['severity'] == 'high'])
        }
    
    def generate_insights(self) -> Dict[str, Any]:
        """Generate actionable insights"""
        insights = {
            'immediate_actions': [],
            'improvements': [],
            'achievements': []
        }
        
        # Immediate actions
        if self.data['tags']['untagged_percentage'] > 60:
            insights['immediate_actions'].append({
                'action': 'Tag untagged documents',
                'impact': 'high',
                'effort': 'medium',
                'details': f"{self.data['tags']['untagged_count']} documents need tags"
            })
        
        if self.data['content']['quality_metrics']['empty_documents'] > 10:
            insights['immediate_actions'].append({
                'action': 'Clean up empty documents',
                'impact': 'medium',
                'effort': 'low',
                'details': f"{self.data['content']['quality_metrics']['empty_documents']} empty documents found"
            })
        
        # Improvements
        if self.data['projects']['active_projects'] < self.data['projects']['total_projects'] * 0.3:
            insights['improvements'].append({
                'suggestion': 'Increase project activity',
                'current': f"{self.data['projects']['active_projects']} active projects",
                'target': f"At least {int(self.data['projects']['total_projects'] * 0.5)} active projects"
            })
        
        # Achievements
        if self.data['overview']['average_views'] > 20:
            insights['achievements'].append({
                'achievement': 'High engagement',
                'metric': f"{self.data['overview']['average_views']:.1f} average views per document"
            })
        
        if self.data['overview']['daily_average'] > 50:
            insights['achievements'].append({
                'achievement': 'Prolific documentation',
                'metric': f"{self.data['overview']['daily_average']:.0f} documents per day"
            })
        
        return insights
    
    def display_report(self):
        """Display the analysis report in the terminal"""
        if not console:
            self.display_text_report()
            return
        
        # Executive Summary
        console.print("\n[bold cyan]📊 EMDX Knowledge Base Analysis Report[/bold cyan]")
        console.print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        # Overview Panel
        overview = self.data['overview']
        overview_text = f"""
[bold]Key Metrics:[/bold]
• Documents: {overview['total_documents']:,} active ({overview['deleted_documents']} deleted)
• Total Views: {overview['total_views']:,} ({overview['average_views']:.1f} avg/doc)
• Projects: {overview['total_projects']} | Tags: {overview['total_tags']}
• Daily Average: {overview['daily_average']:.0f} docs/day
• Date Range: {overview['date_range']['first'][:10]} to {overview['date_range']['last'][:10]}
        """
        console.print(Panel(overview_text.strip(), title="Executive Overview", box=box.ROUNDED))
        
        # Project Health
        console.print("\n[bold]Project Health Dashboard[/bold]")
        project_table = Table(show_header=True, header_style="bold magenta")
        project_table.add_column("Project", style="cyan", no_wrap=True)
        project_table.add_column("Docs", justify="right")
        project_table.add_column("Views", justify="right")
        project_table.add_column("Success", justify="right")
        project_table.add_column("Active", justify="right")
        project_table.add_column("Health", justify="center")
        
        for proj in self.data['projects']['projects'][:10]:
            health_stars = "⭐" * proj['health_score']
            project_table.add_row(
                proj['project'] or "[No Project]",
                str(proj['total_docs']),
                str(proj['total_views']),
                f"{proj['success_rate']:.0f}%",
                str(proj['active']),
                health_stars
            )
        console.print(project_table)
        
        # Content Analysis
        console.print("\n[bold]Content Intelligence[/bold]")
        content_cols = []
        
        # Document types
        type_text = "[bold]Document Types:[/bold]\n"
        for dtype, count in sorted(self.data['content']['document_types'].items(), key=lambda x: x[1], reverse=True)[:5]:
            type_text += f"• {dtype.capitalize()}: {count}\n"
        content_cols.append(Panel(type_text.strip(), title="Types", box=box.ROUNDED))
        
        # Hot topics
        topic_text = "[bold]Hot Topics:[/bold]\n"
        for topic in self.data['content']['hot_topics'][:5]:
            topic_text += f"• {topic['topic']}: {topic['views']} views\n"
        content_cols.append(Panel(topic_text.strip(), title="Topics", box=box.ROUNDED))
        
        console.print(Columns(content_cols))
        
        # Insights
        insights = self.data['insights']
        if insights['immediate_actions']:
            console.print("\n[bold red]🚨 Immediate Actions Required[/bold red]")
            for action in insights['immediate_actions']:
                console.print(f"• {action['action']}: {action['details']}")
        
        if insights['achievements']:
            console.print("\n[bold green]🎉 Achievements[/bold green]")
            for achievement in insights['achievements']:
                console.print(f"• {achievement['achievement']}: {achievement['metric']}")
    
    def display_text_report(self):
        """Simple text report for non-Rich environments"""
        print("\n" + "="*60)
        print("EMDX KNOWLEDGE BASE ANALYSIS REPORT")
        print("="*60)
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        overview = self.data['overview']
        print("OVERVIEW:")
        print(f"- Total Documents: {overview['total_documents']:,}")
        print(f"- Total Views: {overview['total_views']:,}")
        print(f"- Average Views: {overview['average_views']:.1f}")
        print(f"- Projects: {overview['total_projects']}")
        print(f"- Tags: {overview['total_tags']}")
        
        print("\nTOP PROJECTS:")
        for proj in self.data['projects']['projects'][:5]:
            print(f"- {proj['project'] or '[No Project]'}: {proj['total_docs']} docs")
        
        print("\nINSIGHTS:")
        for action in self.data['insights']['immediate_actions']:
            print(f"- ACTION: {action['action']} ({action['details']})")
    
    def save_markdown_report(self, filepath: str):
        """Save analysis as markdown report"""
        lines = []
        lines.append("# EMDX Knowledge Base Analysis Report")
        lines.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Database: {self.db_path}")
        
        # Executive Summary
        overview = self.data['overview']
        lines.append("\n## Executive Summary")
        lines.append(f"\n**Period**: {overview['date_range']['first'][:10]} to {overview['date_range']['last'][:10]}")
        lines.append(f"**Documents**: {overview['total_documents']:,} active ({overview['deleted_documents']} deleted)")
        lines.append(f"**Engagement**: {overview['total_views']:,} total views ({overview['average_views']:.1f} avg/doc)")
        lines.append(f"**Organization**: {overview['total_projects']} projects, {overview['total_tags']} tags")
        lines.append(f"**Growth Rate**: {overview['daily_average']:.0f} documents/day")
        
        # Key Insights
        lines.append("\n## Key Insights")
        
        insights = self.data['insights']
        if insights['immediate_actions']:
            lines.append("\n### 🚨 Immediate Actions")
            for action in insights['immediate_actions']:
                lines.append(f"- **{action['action']}**: {action['details']}")
        
        if insights['improvements']:
            lines.append("\n### 📈 Suggested Improvements")
            for imp in insights['improvements']:
                lines.append(f"- **{imp['suggestion']}**: Currently {imp['current']}, target {imp['target']}")
        
        if insights['achievements']:
            lines.append("\n### 🎉 Achievements")
            for ach in insights['achievements']:
                lines.append(f"- **{ach['achievement']}**: {ach['metric']}")
        
        # Project Analysis
        lines.append("\n## Project Analysis")
        lines.append("\n| Project | Documents | Views | Success Rate | Active | Health |")
        lines.append("|---------|-----------|-------|--------------|--------|--------|")
        
        for proj in self.data['projects']['projects'][:10]:
            health = "⭐" * proj['health_score']
            lines.append(f"| {proj['project'] or '[No Project]'} | {proj['total_docs']} | {proj['total_views']} | {proj['success_rate']:.0f}% | {proj['active']} | {health} |")
        
        # Content Analysis
        lines.append("\n## Content Analysis")
        
        lines.append("\n### Document Types")
        for dtype, count in sorted(self.data['content']['document_types'].items(), key=lambda x: x[1], reverse=True):
            percentage = count / overview['total_documents'] * 100
            lines.append(f"- **{dtype.capitalize()}**: {count} ({percentage:.1f}%)")
        
        lines.append("\n### Hot Topics")
        for topic in self.data['content']['hot_topics'][:10]:
            lines.append(f"- **{topic['topic']}**: {topic['count']} documents, {topic['views']} views")
        
        # Tag Analysis
        lines.append("\n## Tag Analysis")
        tags = self.data['tags']
        lines.append(f"\n- **Total Tags**: {tags['total_tags']}")
        lines.append(f"- **Untagged Documents**: {tags['untagged_count']} ({tags['untagged_percentage']:.1f}%)")
        lines.append(f"- **Tag Diversity**: {tags['tag_diversity']} frequently used tags")
        
        lines.append("\n### Top Tags")
        for tag in tags['tags'][:15]:
            lines.append(f"- **{tag['name']}**: {tag['usage_count']} uses")
        
        lines.append("\n### Common Workflows")
        for workflow, count in tags['workflows'].items():
            lines.append(f"- **{workflow}**: {count} occurrences")
        
        # Quality Issues
        lines.append("\n## Quality Analysis")
        quality = self.data['quality']
        lines.append(f"\n- **Empty Documents**: {quality['quality_issues']['empty_documents']}")
        lines.append(f"- **High View but Low Content**: {quality['quality_issues']['high_view_low_content']}")
        lines.append(f"- **Documents without Project**: {quality['quality_issues']['no_project']}")
        lines.append(f"- **Stale Active Items**: {len(quality['stale_active_items'])}")
        
        # Gaps
        lines.append("\n## Knowledge Gaps")
        for gap in self.data['gaps']['gaps']:
            severity_emoji = "🔴" if gap['severity'] == 'high' else "🟡"
            lines.append(f"\n{severity_emoji} **{gap['type'].replace('_', ' ').title()}**")
            lines.append(f"   - {gap['recommendation']}")
        
        # Write to file
        with open(filepath, 'w') as f:
            f.write('\n'.join(lines))
        
        return filepath
    
    def save_json_export(self, filepath: str):
        """Save all analysis data as JSON"""
        with open(filepath, 'w') as f:
            json.dump(self.data, f, indent=2, default=str)
        return filepath


def main():
    """Main entry point"""
    analyzer = ComprehensiveAnalyzer()
    
    # Run analysis
    analyzer.analyze_all()
    
    # Display report
    analyzer.display_report()
    
    # Save outputs
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Markdown report
    md_path = analyzer.save_markdown_report(f"emdx_analysis_{timestamp}.md")
    print(f"\n📄 Markdown report saved to: {md_path}")
    
    # JSON export
    json_path = analyzer.save_json_export(f"emdx_analysis_{timestamp}.json")
    print(f"📊 JSON data exported to: {json_path}")
    
    # Summary
    if console:
        console.print(f"\n[bold green]✅ Analysis complete![/bold green]")
        console.print(f"Analyzed {analyzer.data['overview']['total_documents']} documents across {analyzer.data['overview']['total_projects']} projects")
    else:
        print("\n✅ Analysis complete!")
        print(f"Analyzed {analyzer.data['overview']['total_documents']} documents")


if __name__ == "__main__":
    main()