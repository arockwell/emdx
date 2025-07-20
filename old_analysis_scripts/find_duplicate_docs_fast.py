#!/usr/bin/env python3
"""
Find duplicate and near-duplicate documents in EMDX (optimized version)
"""

import sqlite3
import os
from pathlib import Path
from collections import defaultdict
import hashlib

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

def get_content_hash(content):
    """Get hash of content for exact duplicate detection"""
    if not content:
        return "empty"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def main():
    db_path = find_database()
    print(f"Using database: {db_path}\n")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("🔍 Analyzing documents for duplicates...\n")
    
    # Get all active documents
    cursor.execute("""
        SELECT d.id, d.title, d.content, d.project, d.access_count, 
               d.created_at, LENGTH(d.content) as content_length
        FROM documents d
        WHERE d.is_deleted = 0
        ORDER BY d.title, d.created_at
    """)
    
    documents = cursor.fetchall()
    total_docs = len(documents)
    
    # Track duplicates
    exact_dupes = defaultdict(list)  # content_hash -> [docs]
    title_groups = defaultdict(list)  # exact_title -> [docs]
    
    # Find exact content duplicates
    print("📌 Finding exact content duplicates...")
    for doc in documents:
        content_hash = get_content_hash(doc['content'])
        exact_dupes[content_hash].append(doc)
        
        # Also group by exact title
        title_groups[doc['title'].strip()].append(doc)
    
    # Filter to only groups with duplicates
    exact_dupe_groups = [docs for docs in exact_dupes.values() if len(docs) > 1]
    exact_dupe_count = sum(len(group) - 1 for group in exact_dupe_groups)
    
    title_dupe_groups = [docs for docs in title_groups.values() if len(docs) > 1]
    title_dupe_count = sum(len(group) - 1 for group in title_dupe_groups)
    
    print(f"  Found {len(exact_dupe_groups)} groups with {exact_dupe_count} duplicate documents")
    print(f"  Found {len(title_dupe_groups)} groups with {title_dupe_count} duplicate titles\n")
    
    # Display results
    print("="*80)
    print("📊 DUPLICATE ANALYSIS RESULTS")
    print("="*80)
    
    # Exact content duplicates
    print(f"\n🔴 EXACT CONTENT DUPLICATES: {exact_dupe_count} documents")
    print("-"*80)
    
    # Show significant duplicate groups
    significant_dupes = sorted(
        [(group, sum(d['access_count'] for d in group)) for group in exact_dupe_groups],
        key=lambda x: x[1],
        reverse=True
    )
    
    for i, (group, total_views) in enumerate(significant_dupes[:15], 1):
        print(f"\nGroup {i} ({len(group)} copies, {total_views} total views):")
        sorted_group = sorted(group, key=lambda x: x['access_count'], reverse=True)
        
        # Show first doc as primary
        primary = sorted_group[0]
        print(f"  PRIMARY [{primary['id']:4d}] {primary['title'][:50]:50s} | {primary['access_count']:3d} views")
        
        # Show duplicates
        for doc in sorted_group[1:]:
            print(f"  DUPE    [{doc['id']:4d}] {doc['title'][:50]:50s} | {doc['access_count']:3d} views")
        
        # Show content preview if not empty
        if primary['content_length'] > 0:
            preview = primary['content'][:100].replace('\n', ' ')
            print(f"  Content: {preview}...")
    
    if len(significant_dupes) > 15:
        print(f"\n... and {len(significant_dupes) - 15} more duplicate groups")
    
    # Title duplicates  
    print(f"\n\n🟡 DUPLICATE TITLES: {title_dupe_count} documents")
    print("-"*80)
    
    significant_titles = sorted(
        [(group, max(d['access_count'] for d in group)) for group in title_dupe_groups if len(group) > 2],
        key=lambda x: len(x[0]),
        reverse=True
    )
    
    for i, (group, max_views) in enumerate(significant_titles[:10], 1):
        print(f"\nTitle: '{group[0]['title']}' ({len(group)} documents)")
        for doc in sorted(group, key=lambda x: x['access_count'], reverse=True):
            print(f"  [{doc['id']:4d}] Project: {doc['project']:20s} | {doc['access_count']:3d} views | {doc['content_length']:6d} chars")
    
    # Summary
    print("\n" + "="*80)
    print("📈 DUPLICATE SUMMARY")
    print("="*80)
    
    print(f"\nTotal documents: {total_docs}")
    print(f"Exact content duplicates: {exact_dupe_count} ({exact_dupe_count/total_docs*100:.1f}%)")
    print(f"Title duplicates: {title_dupe_count} ({title_dupe_count/total_docs*100:.1f}%)")
    
    # Calculate space savings
    space_wasted = sum(
        sum(d['content_length'] for d in group[1:])  # Skip primary
        for group in exact_dupe_groups
    )
    print(f"\nSpace that could be saved: {space_wasted:,} characters")
    
    # Export duplicate IDs
    duplicate_ids = []
    for group in exact_dupe_groups:
        sorted_group = sorted(group, key=lambda x: (x['access_count'], x['id']), reverse=True)
        duplicate_ids.extend([doc['id'] for doc in sorted_group[1:]])
    
    # Most duplicated content
    print("\n🔥 MOST DUPLICATED CONTENT")
    print("-"*80)
    
    most_duped = sorted(exact_dupe_groups, key=len, reverse=True)[:5]
    for i, group in enumerate(most_duped, 1):
        doc = group[0]
        print(f"{i}. {len(group)} copies of: {doc['title'][:60]}")
    
    # Write duplicate IDs to file
    if duplicate_ids:
        with open('duplicate_ids_to_delete.txt', 'w') as f:
            f.write('\n'.join(map(str, sorted(duplicate_ids))))
        print(f"\n📄 Exported {len(duplicate_ids)} duplicate IDs to: duplicate_ids_to_delete.txt")
    
    # Recommendations
    print("\n💡 RECOMMENDATIONS")
    print("="*80)
    print(f"\n1. Delete {exact_dupe_count} exact content duplicates")
    print("   - This will save {space_wasted:,} characters")
    print("   - Keep versions with highest view counts")
    print("\n2. Review title duplicates")
    print("   - Some may be intentional (different projects)")
    print("   - Consider renaming or consolidating")
    
    conn.close()

if __name__ == "__main__":
    main()