#!/usr/bin/env python3
"""
Batch tag untagged documents in EMDX based on patterns
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime
import re

def find_database():
    """Find the EMDX database file"""
    possible_paths = [
        "~/.config/emdx/knowledge.db",
        "~/.emdx.db",
        "~/.local/share/emdx/emdx.db",
    ]
    
    for path_str in possible_paths:
        path = Path(os.path.expanduser(path_str))
        if path.exists():
            return str(path)
    
    raise FileNotFoundError("Could not find EMDX database!")

def get_or_create_tag(cursor, emoji, name):
    """Get tag ID, creating if necessary"""
    cursor.execute("SELECT id FROM tags WHERE name = ?", (name,))
    result = cursor.fetchone()
    
    if result:
        return result[0]
    else:
        cursor.execute("INSERT INTO tags (name) VALUES (?)", (name,))
        return cursor.lastrowid

def add_tag_to_document(cursor, doc_id, tag_id):
    """Add tag to document if not already tagged"""
    cursor.execute("""
        INSERT OR IGNORE INTO document_tags (document_id, tag_id)
        VALUES (?, ?)
    """, (doc_id, tag_id))

def categorize_document(title, content):
    """Determine appropriate tags for a document"""
    tags = []
    title_lower = title.lower()
    content_lower = (content or '').lower()
    combined = title_lower + ' ' + content_lower
    
    # Title-based categorization
    if title.startswith('Gameplan:'):
        tags.extend(['🎯', '🚀'])  # gameplan + active
    elif title.startswith('Analysis:'):
        tags.append('🔍')  # analysis
    elif title.startswith('Bug:') or 'bug' in title_lower:
        tags.append('🐛')  # bug
    elif title.startswith('Feature:'):
        tags.append('✨')  # feature
    elif title.startswith('Summary:'):
        tags.append('📝')  # notes
    
    # Content-based categorization
    if 'test' in combined and not any(t in tags for t in ['🎯', '🔍']):
        tags.append('🧪')  # test
    
    if ('implement' in combined or 'implementation' in combined) and '✨' not in tags:
        tags.append('🔧')  # refactor/implementation
    
    if ('fix' in combined or 'fixed' in combined) and '🐛' not in tags:
        tags.append('🐛')  # bug
    
    # Special cases
    if 'vim' in combined:
        tags.append('vim')
    if 'tui' in combined or 'textual' in combined:
        tags.append('tui')
    if 'browser' in combined and ('file' in combined or 'git' in combined):
        tags.append('file-browser')
    
    return tags

def main():
    db_path = find_database()
    print(f"Using database: {db_path}\n")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("🏷️  BATCH TAGGING UNTAGGED DOCUMENTS\n")
    
    # Get all untagged documents
    cursor.execute("""
        SELECT d.id, d.title, d.content, d.project, d.access_count, 
               LENGTH(d.content) as content_length
        FROM documents d
        WHERE d.is_deleted = 0 
        AND NOT EXISTS (
            SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
        )
        ORDER BY d.access_count DESC
    """)
    
    untagged_docs = cursor.fetchall()
    total_untagged = len(untagged_docs)
    print(f"Found {total_untagged} untagged documents\n")
    
    # Track operations
    tagged_count = 0
    deleted_count = 0
    tag_summary = {}
    
    # First, handle high-value documents (>10 views)
    print("📌 Phase 1: Tagging high-value documents (>10 views)...")
    high_value_tagged = 0
    
    for doc in untagged_docs:
        if doc['access_count'] > 10:
            tags = categorize_document(doc['title'], doc['content'])
            
            if tags:
                for tag in tags:
                    tag_id = get_or_create_tag(cursor, tag, tag)
                    add_tag_to_document(cursor, doc['id'], tag_id)
                    tag_summary[tag] = tag_summary.get(tag, 0) + 1
                
                tagged_count += 1
                high_value_tagged += 1
                
                if high_value_tagged % 10 == 0:
                    print(f"  Tagged {high_value_tagged} high-value documents...")
    
    print(f"  ✅ Tagged {high_value_tagged} high-value documents\n")
    
    # Phase 2: Batch tag by patterns
    print("📌 Phase 2: Batch tagging by document type...")
    
    pattern_rules = [
        {
            'name': 'Test Documents',
            'pattern': lambda t, c: 'test' in t.lower() or 'test' in (c or '').lower(),
            'tags': ['🧪'],
            'exclude_if_has': ['🎯', '🔍']
        },
        {
            'name': 'Gameplans',
            'pattern': lambda t, c: t.startswith('Gameplan:'),
            'tags': ['🎯', '🚀']
        },
        {
            'name': 'Analyses',
            'pattern': lambda t, c: t.startswith('Analysis:'),
            'tags': ['🔍']
        },
        {
            'name': 'Bug/Fix Documents',
            'pattern': lambda t, c: 'bug' in t.lower() or 'fix' in t.lower(),
            'tags': ['🐛']
        },
        {
            'name': 'Implementation Documents',
            'pattern': lambda t, c: 'implementation' in t.lower() or 'implement' in (c or '').lower()[:500],
            'tags': ['🔧']
        },
        {
            'name': 'Feature Documents',
            'pattern': lambda t, c: t.startswith('Feature:') or 'feature' in t.lower(),
            'tags': ['✨']
        }
    ]
    
    for rule in pattern_rules:
        rule_count = 0
        print(f"\n  Tagging {rule['name']}...")
        
        for doc in untagged_docs:
            # Skip if already tagged in phase 1
            cursor.execute("""
                SELECT COUNT(*) FROM document_tags WHERE document_id = ?
            """, (doc['id'],))
            if cursor.fetchone()[0] > 0:
                continue
            
            if rule['pattern'](doc['title'], doc['content']):
                # Check exclusions
                if 'exclude_if_has' in rule:
                    existing_tags = categorize_document(doc['title'], doc['content'])
                    if any(tag in existing_tags for tag in rule['exclude_if_has']):
                        continue
                
                for tag in rule['tags']:
                    tag_id = get_or_create_tag(cursor, tag, tag)
                    add_tag_to_document(cursor, doc['id'], tag_id)
                    tag_summary[tag] = tag_summary.get(tag, 0) + 1
                
                tagged_count += 1
                rule_count += 1
        
        print(f"    ✅ Tagged {rule_count} documents")
    
    # Phase 3: Delete empty untagged documents
    print("\n📌 Phase 3: Deleting empty untagged documents (<100 chars)...")
    
    cursor.execute("""
        SELECT d.id, d.title, LENGTH(d.content) as length
        FROM documents d
        WHERE d.is_deleted = 0 
        AND LENGTH(d.content) < 100
        AND NOT EXISTS (
            SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
        )
    """)
    
    empty_docs = cursor.fetchall()
    
    for doc in empty_docs:
        cursor.execute("""
            UPDATE documents 
            SET is_deleted = 1, deleted_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), doc['id']))
        deleted_count += 1
    
    print(f"  ✅ Deleted {deleted_count} empty documents\n")
    
    # Phase 4: Tag by project for remaining high-volume projects
    print("📌 Phase 4: Project-specific tagging...")
    
    project_tags = {
        'clauding': ['claude', '🏗️'],
        'emdx': ['📚'],
        'improve-docs': ['📚']
    }
    
    for project, tags in project_tags.items():
        project_count = 0
        cursor.execute("""
            SELECT d.id
            FROM documents d
            WHERE d.is_deleted = 0 
            AND d.project = ?
            AND NOT EXISTS (
                SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
            )
        """, (project,))
        
        for doc in cursor.fetchall():
            for tag in tags:
                tag_id = get_or_create_tag(cursor, tag, tag)
                add_tag_to_document(cursor, doc['id'], tag_id)
                tag_summary[tag] = tag_summary.get(tag, 0) + 1
            project_count += 1
            tagged_count += 1
        
        print(f"  ✅ Tagged {project_count} {project} documents")
    
    # Commit all changes
    conn.commit()
    
    # Final summary
    print("\n" + "="*60)
    print("📊 TAGGING SUMMARY")
    print("="*60)
    print(f"\n✅ Total documents tagged: {tagged_count}")
    print(f"🗑️  Empty documents deleted: {deleted_count}")
    
    print("\n📈 Tags Applied:")
    for tag, count in sorted(tag_summary.items(), key=lambda x: x[1], reverse=True):
        print(f"  {tag}: {count} documents")
    
    # Check remaining untagged
    cursor.execute("""
        SELECT COUNT(*) 
        FROM documents d
        WHERE d.is_deleted = 0 
        AND NOT EXISTS (
            SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
        )
    """)
    remaining = cursor.fetchone()[0]
    
    print(f"\n📌 Remaining untagged: {remaining} documents")
    print(f"   Reduction: {total_untagged} → {remaining} ({(total_untagged-remaining)/total_untagged*100:.1f}% improvement)")
    
    # Show updated tag distribution
    print("\n🏷️  UPDATED TAG DISTRIBUTION")
    cursor.execute("""
        SELECT t.name, COUNT(dt.document_id) as count
        FROM tags t
        JOIN document_tags dt ON t.id = dt.tag_id
        JOIN documents d ON dt.document_id = d.id
        WHERE d.is_deleted = 0
        GROUP BY t.id
        ORDER BY count DESC
        LIMIT 20
    """)
    
    for row in cursor.fetchall():
        print(f"  {row['name']}: {row['count']} documents")
    
    conn.close()

if __name__ == "__main__":
    main()