#!/usr/bin/env python3
"""Direct analysis of EMDX database"""

import sqlite3
import os
from collections import Counter, defaultdict
from datetime import datetime
import json

# Find database
db_path = os.path.expanduser("~/.local/share/emdx/emdx.db")
if not os.path.exists(db_path):
    # Try alternative location
    db_path = os.path.expanduser("~/Library/Application Support/emdx/emdx.db")
    if not os.path.exists(db_path):
        print(f"Database not found at expected locations")
        exit(1)

print(f"Analyzing database at: {db_path}\n")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Basic stats
cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
total_docs = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 1") 
deleted_docs = cursor.fetchone()[0]

cursor.execute("SELECT SUM(access_count) FROM documents WHERE is_deleted = 0")
total_views = cursor.fetchone()[0] or 0

print("# EMDX Knowledge Base Analysis")
print(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("\n## Overview Statistics")
print(f"- Total Documents: {total_docs}")
print(f"- Deleted Documents: {deleted_docs}")
print(f"- Total Views: {total_views:,}")
print(f"- Average Views: {total_views/total_docs:.1f}" if total_docs > 0 else "- Average Views: 0")

# Projects
print("\n### Projects Distribution")
cursor.execute("""
    SELECT project, COUNT(*) as count 
    FROM documents 
    WHERE is_deleted = 0 
    GROUP BY project 
    ORDER BY count DESC
    LIMIT 15
""")
for row in cursor.fetchall():
    print(f"- {row['project'] or 'No Project'}: {row['count']} documents")

# Most viewed
print("\n### Most Viewed Documents")
cursor.execute("""
    SELECT title, access_count, id 
    FROM documents 
    WHERE is_deleted = 0 
    ORDER BY access_count DESC 
    LIMIT 10
""")
for row in cursor.fetchall():
    title = row['title'][:60] + "..." if len(row['title']) > 60 else row['title']
    print(f"- [{row['id']}] {title}: {row['access_count']} views")

# Tags
print("\n## Tag Analysis")
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
print(f"- Total Unique Tags: {len(tags)}")

cursor.execute("""
    SELECT COUNT(*) 
    FROM documents d
    WHERE d.is_deleted = 0 
    AND NOT EXISTS (
        SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
    )
""")
untagged = cursor.fetchone()[0]
print(f"- Untagged Documents: {untagged}")

print("\n### Top 30 Tags")
for tag in tags[:30]:
    if tag['count'] > 0:
        print(f"- {tag['emoji']} {tag['name']}: {tag['count']} documents")

# Content patterns
print("\n## Content Analysis")
cursor.execute("SELECT title FROM documents WHERE is_deleted = 0")
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
    elif title.startswith("Issue"):
        title_patterns["issue"] += 1
    elif title.startswith("PR "):
        title_patterns["pr"] += 1
    else:
        title_patterns["other"] += 1

print("\n### Document Type Distribution")
for pattern, count in sorted(title_patterns.items(), key=lambda x: x[1], reverse=True):
    percentage = (count / total_docs * 100) if total_docs > 0 else 0
    print(f"- {pattern.capitalize()}: {count} ({percentage:.1f}%)")

# Document lengths
cursor.execute("SELECT LENGTH(content) as length FROM documents WHERE is_deleted = 0")
lengths = [row[0] for row in cursor.fetchall()]

print("\n### Document Length Distribution")
length_dist = {
    "Very short (< 100 chars)": sum(1 for l in lengths if l < 100),
    "Short (100-500 chars)": sum(1 for l in lengths if 100 <= l < 500),
    "Medium (500-2K chars)": sum(1 for l in lengths if 500 <= l < 2000),
    "Long (2K-5K chars)": sum(1 for l in lengths if 2000 <= l < 5000),
    "Very long (> 5K chars)": sum(1 for l in lengths if l >= 5000)
}
for size, count in length_dist.items():
    print(f"- {size}: {count}")
print(f"- Average Length: {sum(lengths)/len(lengths):.0f} characters" if lengths else "- Average Length: 0")

# Temporal patterns
print("\n## Temporal Patterns")
cursor.execute("""
    SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
    FROM documents
    WHERE is_deleted = 0
    GROUP BY month
    ORDER BY month DESC
    LIMIT 6
""")
print("\n### Recent Activity (Last 6 Months)")
for row in reversed(cursor.fetchall()):
    print(f"- {row['month']}: {row['count']} documents created")

# Project health
print("\n## Project Health Analysis")

# Gameplan success
cursor.execute("""
    SELECT 
        COUNT(CASE WHEN t2.name = 'success' THEN 1 END) as success_count,
        COUNT(CASE WHEN t2.name = 'failed' THEN 1 END) as failed_count,
        COUNT(CASE WHEN t2.name = 'blocked' THEN 1 END) as blocked_count,
        COUNT(DISTINCT d.id) as total
    FROM documents d
    JOIN document_tags dt1 ON d.id = dt1.document_id
    JOIN tags t1 ON dt1.tag_id = t1.id
    LEFT JOIN document_tags dt2 ON d.id = dt2.document_id
    LEFT JOIN tags t2 ON dt2.tag_id = t2.id AND t2.name IN ('success', 'failed', 'blocked')
    WHERE d.is_deleted = 0 AND t1.name = 'gameplan'
""")
gp = cursor.fetchone()
if gp and gp['total'] > 0:
    success_rate = (gp['success_count'] / gp['total'] * 100)
    print(f"\n### Gameplan Success Rate: {success_rate:.1f}%")
    print(f"- Total Gameplans: {gp['total']}")
    print(f"- Successful: {gp['success_count']}")
    print(f"- Failed: {gp['failed_count']}")
    print(f"- Blocked: {gp['blocked_count']}")

# Success by project
print("\n### Success Rates by Project (>5 docs)")
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
""")
for proj in cursor.fetchall():
    success_rate = (proj['success_count'] / proj['total'] * 100) if proj['total'] > 0 else 0
    print(f"\n**{proj['project'] or 'No Project'}** ({proj['total']} docs)")
    print(f"  - Success: {proj['success_count']} ({success_rate:.1f}%)")
    print(f"  - Failed: {proj['failed_count']}")
    print(f"  - Blocked: {proj['blocked_count']}")
    print(f"  - Active: {proj['active_count']}")

# Tag combinations
print("\n## Popular Tag Combinations")
cursor.execute("""
    SELECT d.id, GROUP_CONCAT(t.emoji || ':' || t.name) as tags
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
        tag_set = ', '.join(tag_list)
        combinations[tag_set] += 1

print("\n### Top 15 Tag Combinations")
for combo, count in combinations.most_common(15):
    print(f"- {combo}: {count} documents")

conn.close()
print("\n✅ Analysis complete!")