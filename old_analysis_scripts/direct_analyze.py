#!/usr/bin/env python3
"""Direct database analysis without imports"""
import sqlite3
from pathlib import Path
from collections import Counter
from datetime import datetime

# Check database locations
db_paths = [
    Path.home() / ".config" / "emdx" / "knowledge.db",
    Path.home() / ".local" / "share" / "emdx" / "emdx.db"
]

db_path = None
for p in db_paths:
    if p.exists():
        db_path = p
        break

if not db_path:
    print("No database found!")
    exit(1)

print(f"Using database at: {db_path}")
print("=" * 80)

# Connect to database
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Basic stats
cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
total_docs = cursor.fetchone()[0]
print(f"\nTotal Documents: {total_docs}")

cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 1")
deleted_docs = cursor.fetchone()[0]
print(f"Deleted Documents: {deleted_docs}")

# Project distribution
print("\nProject Distribution:")
cursor.execute("""
    SELECT project, COUNT(*) as count 
    FROM documents 
    WHERE is_deleted = 0 
    GROUP BY project 
    ORDER BY count DESC
    LIMIT 15
""")
for row in cursor.fetchall():
    project = row['project'] or '[No Project]'
    print(f"  {project}: {row['count']}")

# Tag analysis
print("\nTop Tags:")
cursor.execute("""
    SELECT t.emoji, t.name, COUNT(dt.document_id) as count
    FROM tags t
    LEFT JOIN document_tags dt ON t.id = dt.tag_id
    LEFT JOIN documents d ON dt.document_id = d.id
    WHERE d.is_deleted = 0 OR d.is_deleted IS NULL
    GROUP BY t.id
    ORDER BY count DESC
    LIMIT 20
""")
for row in cursor.fetchall():
    if row['count'] > 0:
        print(f"  {row['emoji']} {row['name']}: {row['count']}")

# Recent documents
print("\nMost Recent Documents:")
cursor.execute("""
    SELECT title, created_at, id 
    FROM documents 
    WHERE is_deleted = 0 
    ORDER BY created_at DESC 
    LIMIT 10
""")
for row in cursor.fetchall():
    created = datetime.fromisoformat(row['created_at']).strftime("%Y-%m-%d %H:%M")
    title = row['title'][:60] + "..." if len(row['title']) > 60 else row['title']
    print(f"  [{row['id']}] {created} - {title}")

# Most viewed
print("\nMost Viewed Documents:")
cursor.execute("""
    SELECT title, access_count, id 
    FROM documents 
    WHERE is_deleted = 0 
    ORDER BY access_count DESC 
    LIMIT 10
""")
for row in cursor.fetchall():
    title = row['title'][:60] + "..." if len(row['title']) > 60 else row['title']
    print(f"  [{row['id']}] {row['access_count']} views - {title}")

# Title patterns
print("\nDocument Type Patterns:")
cursor.execute("SELECT title FROM documents WHERE is_deleted = 0")
titles = [row[0] for row in cursor.fetchall()]
patterns = Counter()
for title in titles:
    if title.startswith("Gameplan:"):
        patterns["gameplan"] += 1
    elif title.startswith("Analysis:"):
        patterns["analysis"] += 1
    elif title.startswith("Bug:"):
        patterns["bug"] += 1
    elif title.startswith("Feature:"):
        patterns["feature"] += 1
    elif title.startswith("Note:"):
        patterns["note"] += 1
    elif title.startswith("Issue"):
        patterns["issue"] += 1
    elif title.startswith("PR "):
        patterns["pr"] += 1
    else:
        patterns["other"] += 1

for pattern, count in patterns.most_common():
    print(f"  {pattern}: {count}")

# Gameplan success analysis
print("\nGameplan Analysis:")
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
gameplan_stats = cursor.fetchone()
if gameplan_stats and gameplan_stats['total'] > 0:
    total = gameplan_stats['total']
    success = gameplan_stats['success_count']
    failed = gameplan_stats['failed_count'] 
    blocked = gameplan_stats['blocked_count']
    success_rate = (success / total * 100) if total > 0 else 0
    print(f"  Total gameplans: {total}")
    print(f"  Success: {success} ({success_rate:.1f}%)")
    print(f"  Failed: {failed}")
    print(f"  Blocked: {blocked}")

conn.close()