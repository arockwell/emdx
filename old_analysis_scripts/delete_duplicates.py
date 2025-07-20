#!/usr/bin/env python3
"""
Delete duplicate documents from EMDX based on the duplicate_ids_to_delete.txt file
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
    # Read duplicate IDs
    if not os.path.exists('duplicate_ids_to_delete.txt'):
        print("❌ Error: duplicate_ids_to_delete.txt not found!")
        return
    
    with open('duplicate_ids_to_delete.txt', 'r') as f:
        duplicate_ids = [int(line.strip()) for line in f if line.strip()]
    
    print(f"🗑️  DELETING {len(duplicate_ids)} DUPLICATE DOCUMENTS\n")
    
    db_path = find_database()
    print(f"Using database: {db_path}\n")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get info about documents to be deleted
    print("📋 Documents to be deleted:")
    cursor.execute(f"""
        SELECT id, title, project, access_count, LENGTH(content) as length
        FROM documents
        WHERE id IN ({','.join('?' * len(duplicate_ids))})
        AND is_deleted = 0
        ORDER BY id
    """, duplicate_ids)
    
    docs_to_delete = cursor.fetchall()
    total_space = 0
    
    for doc in docs_to_delete[:20]:  # Show first 20
        total_space += doc['length']
        print(f"  [{doc['id']:4d}] {doc['title'][:50]:50s} | {doc['access_count']:3d} views | {doc['length']:6d} chars")
    
    if len(docs_to_delete) > 20:
        print(f"  ... and {len(docs_to_delete) - 20} more")
        # Calculate total space for all
        for doc in docs_to_delete[20:]:
            total_space += doc['length']
    
    print(f"\n💾 Total space to be freed: {total_space:,} characters")
    
    # Perform deletion
    print(f"\n🔄 Deleting duplicates...")
    
    deleted_count = 0
    batch_size = 50
    
    for i in range(0, len(duplicate_ids), batch_size):
        batch = duplicate_ids[i:i+batch_size]
        
        cursor.execute(f"""
            UPDATE documents 
            SET is_deleted = 1, deleted_at = ?
            WHERE id IN ({','.join('?' * len(batch))})
            AND is_deleted = 0
        """, [datetime.now().isoformat()] + batch)
        
        deleted_count += cursor.rowcount
        
        if deleted_count > 0 and deleted_count % 50 == 0:
            print(f"  Progress: {deleted_count} documents deleted...")
    
    # Commit changes
    conn.commit()
    
    print(f"\n✅ Successfully deleted {deleted_count} duplicate documents!")
    
    # Verify results
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN is_deleted = 0 THEN 1 END) as active,
            COUNT(CASE WHEN is_deleted = 1 THEN 1 END) as deleted
        FROM documents
    """)
    stats = cursor.fetchone()
    
    print(f"\n📊 Updated database statistics:")
    print(f"  Active documents: {stats['active']} (was 514)")
    print(f"  Deleted documents: {stats['deleted']} (was 216)")
    print(f"  Space freed: {total_space:,} characters")
    
    # Check for any remaining duplicates
    cursor.execute("""
        SELECT COUNT(*) as dup_count
        FROM (
            SELECT content, COUNT(*) as cnt
            FROM documents
            WHERE is_deleted = 0
            AND LENGTH(content) > 0
            GROUP BY content
            HAVING COUNT(*) > 1
        )
    """)
    remaining_dupes = cursor.fetchone()['dup_count']
    
    if remaining_dupes == 0:
        print("\n🎉 No more content duplicates remain!")
    else:
        print(f"\n⚠️  {remaining_dupes} duplicate groups still remain")
    
    # Clean up the duplicate IDs file
    os.rename('duplicate_ids_to_delete.txt', 'duplicate_ids_deleted_backup.txt')
    print("\n📄 Renamed duplicate_ids_to_delete.txt to duplicate_ids_deleted_backup.txt")
    
    conn.close()

if __name__ == "__main__":
    main()