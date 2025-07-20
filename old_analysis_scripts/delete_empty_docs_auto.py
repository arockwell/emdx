#!/usr/bin/env python3
"""
Delete empty documents from EMDX knowledge base (automatic mode)
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime

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

def main():
    db_path = find_database()
    print(f"Using database: {db_path}\n")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # First, let's identify empty documents
    print("🔍 Finding empty documents (< 10 characters)...")
    
    cursor.execute("""
        SELECT id, title, LENGTH(content) as length, content, project
        FROM documents
        WHERE is_deleted = 0
        AND LENGTH(content) < 10
        ORDER BY id
    """)
    
    empty_docs = cursor.fetchall()
    print(f"\nFound {len(empty_docs)} empty documents:")
    
    # Display them for review
    print("\nDocuments to be deleted:")
    for i, doc in enumerate(empty_docs):
        content_preview = repr(doc['content'][:50]) if doc['content'] else "''"
        print(f"  [{doc['id']:4d}] {doc['title'][:60]:<60} | Length: {doc['length']}")
        
        # Show all if less than 50, otherwise sample
        if len(empty_docs) > 50 and i >= 20:
            print(f"  ... and {len(empty_docs) - 20} more")
            break
    
    # Perform soft deletion
    print(f"\n🗑️  Deleting {len(empty_docs)} empty documents...")
    
    deleted_count = 0
    doc_ids = []
    
    for doc in empty_docs:
        cursor.execute("""
            UPDATE documents 
            SET is_deleted = 1, deleted_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), doc['id']))
        deleted_count += 1
        doc_ids.append(doc['id'])
        
        if deleted_count % 10 == 0:
            print(f"  Progress: {deleted_count}/{len(empty_docs)} documents deleted...")
    
    # Commit the changes
    conn.commit()
    
    print(f"\n✅ Successfully deleted {deleted_count} empty documents!")
    print(f"   Deleted IDs: {doc_ids[:10]}{'...' if len(doc_ids) > 10 else ''}")
    
    # Verify the deletion
    cursor.execute("""
        SELECT COUNT(*) 
        FROM documents 
        WHERE is_deleted = 0 
        AND LENGTH(content) < 10
    """)
    remaining = cursor.fetchone()[0]
    
    if remaining == 0:
        print("\n✨ All empty documents have been removed!")
    else:
        print(f"\n⚠️  Warning: {remaining} empty documents still remain")
    
    # Show updated stats
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN is_deleted = 0 THEN 1 END) as active,
            COUNT(CASE WHEN is_deleted = 1 THEN 1 END) as deleted
        FROM documents
    """)
    stats = cursor.fetchone()
    print(f"\n📊 Updated database stats:")
    print(f"  Active documents: {stats['active']} (was 569)")
    print(f"  Deleted documents: {stats['deleted']} (was 160)")
    print(f"  Net reduction: {deleted_count} documents")
    
    # Show what types of documents were deleted
    print("\n📝 Deleted document types:")
    deleted_types = {}
    for doc in empty_docs:
        title = doc['title']
        if 'Screenshot' in title:
            doc_type = 'Screenshot'
        elif 'Note -' in title:
            doc_type = 'Empty Note'
        elif 'Analysis:' in title:
            doc_type = 'Empty Analysis'
        elif 'Piped content' in title:
            doc_type = 'Empty Piped Content'
        else:
            doc_type = 'Other'
        
        deleted_types[doc_type] = deleted_types.get(doc_type, 0) + 1
    
    for doc_type, count in sorted(deleted_types.items(), key=lambda x: x[1], reverse=True):
        print(f"  - {doc_type}: {count}")
    
    conn.close()

if __name__ == "__main__":
    main()