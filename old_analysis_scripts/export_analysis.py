#!/usr/bin/env python3
"""Export analysis data to JSON"""
import sqlite3
import json
from pathlib import Path
from collections import Counter
from datetime import datetime

# Database path
db_path = Path.home() / ".config" / "emdx" / "knowledge.db"
if not db_path.exists():
    db_path = Path.home() / ".local" / "share" / "emdx" / "emdx.db"

if not db_path.exists():
    print("No database found!")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Gather all the data
data = {}

# Basic stats
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 0")
data['total_documents'] = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = 1")
data['deleted_documents'] = cursor.fetchone()[0]

cursor.execute("SELECT SUM(access_count) FROM documents WHERE is_deleted = 0")
data['total_views'] = cursor.fetchone()[0] or 0

# Projects
cursor.execute("""
    SELECT project, COUNT(*) as count 
    FROM documents 
    WHERE is_deleted = 0 
    GROUP BY project 
    ORDER BY count DESC
""")
data['projects'] = [dict(row) for row in cursor.fetchall()]

# Tags
cursor.execute("""
    SELECT t.emoji, t.name, COUNT(dt.document_id) as count
    FROM tags t
    LEFT JOIN document_tags dt ON t.id = dt.tag_id
    LEFT JOIN documents d ON dt.document_id = d.id
    WHERE d.is_deleted = 0 OR d.is_deleted IS NULL
    GROUP BY t.id
    ORDER BY count DESC
""")
data['tags'] = [dict(row) for row in cursor.fetchall()]

# Most viewed
cursor.execute("""
    SELECT title, access_count, id 
    FROM documents 
    WHERE is_deleted = 0 
    ORDER BY access_count DESC 
    LIMIT 20
""")
data['most_viewed'] = [dict(row) for row in cursor.fetchall()]

# Most recent
cursor.execute("""
    SELECT title, created_at, id 
    FROM documents 
    WHERE is_deleted = 0 
    ORDER BY created_at DESC 
    LIMIT 20
""")
data['most_recent'] = [dict(row) for row in cursor.fetchall()]

# Title patterns
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
data['title_patterns'] = dict(patterns)

# Gameplan stats
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
data['gameplan_stats'] = dict(cursor.fetchone() or {})

# Temporal patterns
cursor.execute("""
    SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
    FROM documents
    WHERE is_deleted = 0
    GROUP BY month
    ORDER BY month
""")
data['creation_by_month'] = [dict(row) for row in cursor.fetchall()]

conn.close()

# Write to file
output_path = Path("emdx_analysis.json")
with open(output_path, 'w') as f:
    json.dump(data, f, indent=2, default=str)

print(f"Analysis exported to: {output_path}")
print(f"Total documents: {data['total_documents']}")