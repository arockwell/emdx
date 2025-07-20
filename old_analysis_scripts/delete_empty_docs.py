#!/usr/bin/env python3
"""
Delete empty documents from EMDX knowledge base
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
    for doc in empty_docs[:20]:  # Show first 20
        content_preview = repr(doc['content'][:50]) if doc['content'] else "''"
        print(f"  [{doc['id']:4d}] {doc['title'][:50]:<50} | Length: {doc['length']} | Content: {content_preview}")
    
    if len(empty_docs) > 20:
        print(f"  ... and {len(empty_docs) - 20} more")
    
    # Confirm deletion
    print(f"\n⚠️  Ready to delete {len(empty_docs)} empty documents.")
    response = input("Proceed with deletion? (yes/no): ")
    
    if response.lower() != 'yes':
        print("❌ Deletion cancelled.")
        return
    
    # Perform soft deletion
    print("\n🗑️  Deleting empty documents...")
    
    deleted_count = 0
    for doc in empty_docs:
        cursor.execute("""
            UPDATE documents 
            SET is_deleted = 1, deleted_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), doc['id']))
        deleted_count += 1
        
        if deleted_count % 10 == 0:
            print(f"  Deleted {deleted_count}/{len(empty_docs)} documents...")
    
    # Commit the changes
    conn.commit()
    
    print(f"\n✅ Successfully deleted {deleted_count} empty documents!")
    
    # Verify the deletion
    cursor.execute("""
        SELECT COUNT(*) 
        FROM documents 
        WHERE is_deleted = 0 
        AND LENGTH(content) < 10
    """)
    remaining = cursor.fetchone()[0]
    
    if remaining == 0:
        print("✨ All empty documents have been removed!")
    else:
        print(f"⚠️  Warning: {remaining} empty documents still remain")
    
    # Show updated stats
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN is_deleted = 0 THEN 1 END) as active,
            COUNT(CASE WHEN is_deleted = 1 THEN 1 END) as deleted
        FROM documents
    """)
    stats = cursor.fetchone()
    print(f"\n📊 Updated database stats:")
    print(f"  Active documents: {stats['active']}")
    print(f"  Deleted documents: {stats['deleted']}")
    
    conn.close()

if __name__ == "__main__":
    main()