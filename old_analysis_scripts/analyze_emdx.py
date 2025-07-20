#!/usr/bin/env python3
"""
EMDX Knowledge Base Analysis
Run this script to get comprehensive insights into your knowledge base.
"""

import sqlite3
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime
import json
from pathlib import Path

def find_database():
    """Find the EMDX database file"""
    possible_paths = [
        "~/.config/emdx/knowledge.db",
        "~/.emdx.db",
        "~/.local/share/emdx/emdx.db",
        "~/Library/Application Support/emdx/emdx.db",
        "~/.emdx/emdx.db",
        "~/emdx.db"
    ]
    
    for path_str in possible_paths:
        path = Path(os.path.expanduser(path_str))
        if path.exists():
            return str(path)
    
    print("ERROR: Could not find EMDX database!")
    print("Checked locations:")
    for p in possible_paths:
        print(f"  - {os.path.expanduser(p)}")
    sys.exit(1)

def main():
    db_path = find_database()
    print(f"Found database at: {db_path}")
    print("=" * 80)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get basic stats
    cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
    total_docs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 1")
    deleted_docs = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(access_count) FROM documents WHERE is_deleted = 0")
    total_views = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM tags")
    total_tags = cursor.fetchone()[0]
    
    print("\n🚀 EMDX KNOWLEDGE BASE ANALYSIS REPORT 🚀")
    print(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n" + "=" * 80)
    
    # Overview
    print("\n📊 OVERVIEW STATISTICS")
    print("-" * 40)
    print(f"Total Documents:     {total_docs:,}")
    print(f"Deleted Documents:   {deleted_docs:,}")
    print(f"Total Views:         {total_views:,}")
    print(f"Average Views/Doc:   {total_views/total_docs:.1f}" if total_docs > 0 else "Average Views/Doc:   0")
    print(f"Total Tags:          {total_tags}")
    
    # Projects
    print("\n\n🗂️  PROJECT DISTRIBUTION")
    print("-" * 40)
    cursor.execute("""
        SELECT project, COUNT(*) as count 
        FROM documents 
        WHERE is_deleted = 0 
        GROUP BY project 
        ORDER BY count DESC
        LIMIT 20
    """)
    projects = cursor.fetchall()
    
    for i, row in enumerate(projects, 1):
        project = row['project'] or '[No Project]'
        bar = '█' * min(50, int(row['count'] / total_docs * 200))
        print(f"{i:2d}. {project:40s} {row['count']:4d} {bar}")
    
    # Most viewed
    print("\n\n👁️  MOST VIEWED DOCUMENTS")
    print("-" * 40)
    cursor.execute("""
        SELECT title, access_count, id 
        FROM documents 
        WHERE is_deleted = 0 
        ORDER BY access_count DESC 
        LIMIT 15
    """)
    for i, row in enumerate(cursor.fetchall(), 1):
        title = row['title'][:60] + "..." if len(row['title']) > 60 else row['title']
        print(f"{i:2d}. [{row['id']:4d}] {title:64s} {row['access_count']:4d} views")
    
    # Tags
    print("\n\n🏷️  TAG ANALYSIS")
    print("-" * 40)
    cursor.execute("""
        SELECT COUNT(*) 
        FROM documents d
        WHERE d.is_deleted = 0 
        AND NOT EXISTS (
            SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
        )
    """)
    untagged = cursor.fetchone()[0]
    print(f"Untagged Documents: {untagged} ({untagged/total_docs*100:.1f}%)" if total_docs > 0 else "Untagged: 0")
    
    print("\nTop 40 Tags:")
    cursor.execute("""
        SELECT t.name, COUNT(dt.document_id) as count
        FROM tags t
        LEFT JOIN document_tags dt ON t.id = dt.tag_id
        LEFT JOIN documents d ON dt.document_id = d.id
        WHERE d.is_deleted = 0 OR d.is_deleted IS NULL
        GROUP BY t.id
        ORDER BY count DESC
        LIMIT 40
    """)
    for i, tag in enumerate(cursor.fetchall(), 1):
        if tag['count'] > 0:
            bar = '█' * min(30, int(tag['count'] / total_docs * 100))
            print(f"{i:2d}. {tag['name']:20s} {tag['count']:4d} {bar}")
    
    # Content patterns
    print("\n\n📝 CONTENT ANALYSIS")
    print("-" * 40)
    cursor.execute("SELECT title, LENGTH(content) as length FROM documents WHERE is_deleted = 0")
    titles_and_lengths = cursor.fetchall()
    
    title_patterns = Counter()
    lengths = []
    for row in titles_and_lengths:
        title = row['title']
        lengths.append(row['length'])
        
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
        elif title.startswith("Issue"):
            title_patterns["issue"] += 1
        elif title.startswith("PR "):
            title_patterns["pr"] += 1
        elif "gameplan" in title.lower():
            title_patterns["gameplan-like"] += 1
        else:
            title_patterns["other"] += 1
    
    print("Document Types:")
    for pattern, count in sorted(title_patterns.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_docs * 100) if total_docs > 0 else 0
        bar = '█' * int(percentage / 2)
        print(f"  {pattern:15s} {count:4d} ({percentage:5.1f}%) {bar}")
    
    print("\nDocument Lengths:")
    length_dist = [
        ("Tiny (<100)", sum(1 for l in lengths if l < 100)),
        ("Short (100-500)", sum(1 for l in lengths if 100 <= l < 500)),
        ("Medium (500-2K)", sum(1 for l in lengths if 500 <= l < 2000)),
        ("Long (2K-5K)", sum(1 for l in lengths if 2000 <= l < 5000)),
        ("Very Long (>5K)", sum(1 for l in lengths if l >= 5000))
    ]
    for size, count in length_dist:
        percentage = (count / total_docs * 100) if total_docs > 0 else 0
        bar = '█' * int(percentage / 2)
        print(f"  {size:18s} {count:4d} ({percentage:5.1f}%) {bar}")
    print(f"\n  Average: {sum(lengths)/len(lengths):,.0f} chars" if lengths else "  Average: 0 chars")
    
    # Project health
    print("\n\n💚 PROJECT HEALTH")
    print("-" * 40)
    
    # Gameplan success
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN t2.name = 'success' THEN 1 END) as success_count,
            COUNT(CASE WHEN t2.name = 'failed' THEN 1 END) as failed_count,
            COUNT(CASE WHEN t2.name = 'blocked' THEN 1 END) as blocked_count,
            COUNT(CASE WHEN t2.name = 'active' THEN 1 END) as active_count,
            COUNT(DISTINCT d.id) as total
        FROM documents d
        JOIN document_tags dt1 ON d.id = dt1.document_id
        JOIN tags t1 ON dt1.tag_id = t1.id
        LEFT JOIN document_tags dt2 ON d.id = dt2.document_id
        LEFT JOIN tags t2 ON dt2.tag_id = t2.id AND t2.name IN ('success', 'failed', 'blocked', 'active')
        WHERE d.is_deleted = 0 AND t1.name = 'gameplan'
    """)
    gp = cursor.fetchone()
    if gp and gp['total'] > 0:
        success_rate = (gp['success_count'] / gp['total'] * 100)
        print(f"GAMEPLAN SUCCESS RATE: {success_rate:.1f}% ✨")
        print(f"  Total Gameplans: {gp['total']}")
        print(f"  ✅ Success:      {gp['success_count']} ({gp['success_count']/gp['total']*100:.1f}%)")
        print(f"  ❌ Failed:       {gp['failed_count']} ({gp['failed_count']/gp['total']*100:.1f}%)")
        print(f"  🚧 Blocked:      {gp['blocked_count']} ({gp['blocked_count']/gp['total']*100:.1f}%)")
        print(f"  🚀 Active:       {gp['active_count']} ({gp['active_count']/gp['total']*100:.1f}%)")
    
    # Success by project
    print("\n\nProject Success Rates (projects with >5 docs):")
    cursor.execute("""
        SELECT 
            d.project,
            COUNT(CASE WHEN t.name = 'success' THEN 1 END) as success_count,
            COUNT(CASE WHEN t.name = 'failed' THEN 1 END) as failed_count,
            COUNT(CASE WHEN t.name = 'blocked' THEN 1 END) as blocked_count,
            COUNT(CASE WHEN t.name = 'active' THEN 1 END) as active_count,
            COUNT(DISTINCT d.id) as total
        FROM documents d
        LEFT JOIN document_tags dt ON d.id = dt.document_id
        LEFT JOIN tags t ON dt.tag_id = t.id
        WHERE d.is_deleted = 0
        GROUP BY d.project
        HAVING total > 5
        ORDER BY total DESC
        LIMIT 20
    """)
    
    print(f"\n{'Project':40s} {'Total':>6s} {'Success':>8s} {'Failed':>7s} {'Blocked':>8s} {'Active':>7s}")
    print("-" * 80)
    for proj in cursor.fetchall():
        success_rate = (proj['success_count'] / proj['total'] * 100) if proj['total'] > 0 else 0
        project_name = (proj['project'] or '[No Project]')[:39]
        print(f"{project_name:40s} {proj['total']:6d} {proj['success_count']:6d} ({success_rate:4.1f}%) "
              f"{proj['failed_count']:6d} {proj['blocked_count']:6d} {proj['active_count']:6d}")
    
    # Recent activity
    print("\n\n📅 RECENT ACTIVITY")
    print("-" * 40)
    cursor.execute("""
        SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
        FROM documents
        WHERE is_deleted = 0
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """)
    months = list(reversed(cursor.fetchall()))
    if months:
        max_count = max(m['count'] for m in months)
        for row in months:
            bar = '█' * int(row['count'] / max_count * 50)
            print(f"{row['month']}  {row['count']:4d} {bar}")
    
    # Tag combinations
    print("\n\n🎯 POPULAR TAG COMBINATIONS")
    print("-" * 40)
    cursor.execute("""
        SELECT d.id, GROUP_CONCAT(t.name) as tags
        FROM documents d
        JOIN document_tags dt ON d.id = dt.document_id
        JOIN tags t ON dt.tag_id = t.id
        WHERE d.is_deleted = 0
        GROUP BY d.id
        HAVING COUNT(dt.tag_id) > 1
    """)
    combinations = Counter()
    for row in cursor.fetchall():
        if row[1]:
            tag_list = sorted(row[1].split(','))
            tag_set = ', '.join(tag_list[:3])  # Limit to first 3 tags
            combinations[tag_set] += 1
    
    for i, (combo, count) in enumerate(combinations.most_common(20), 1):
        print(f"{i:2d}. {combo:60s} {count:3d} docs")
    
    conn.close()
    
    print("\n" + "=" * 80)
    print("✅ Analysis complete!")
    print("\nThis analysis was generated by the new 'emdx analyze' command.")
    print("Soon you'll be able to run: emdx analyze --json output.json")

if __name__ == "__main__":
    main()