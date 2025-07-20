#!/usr/bin/env python3
"""
Find duplicate and near-duplicate documents in EMDX
"""

import sqlite3
import os
from pathlib import Path
from collections import defaultdict
import difflib
import hashlib
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

def get_content_hash(content):
    """Get hash of content for exact duplicate detection"""
    if not content:
        return "empty"
    return hashlib.md5(content.encode('utf-8')).hexdigest()

def normalize_title(title):
    """Normalize title for comparison"""
    # Remove timestamps, numbers, and common variations
    import re
    normalized = title.lower()
    # Remove dates and timestamps
    normalized = re.sub(r'\d{4}-\d{2}-\d{2}', '', normalized)
    normalized = re.sub(r'\d{2}:\d{2}', '', normalized)
    # Remove common prefixes
    normalized = re.sub(r'^(note|new note|quick note)\s*-?\s*', '', normalized)
    normalized = re.sub(r'^(test|testing)\s*:?\s*', '', normalized)
    # Remove trailing numbers and versions
    normalized = re.sub(r'[\s\-_]+(v?\d+|copy|duplicate|backup)$', '', normalized)
    # Remove extra whitespace
    normalized = ' '.join(normalized.split())
    return normalized

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
               d.created_at, LENGTH(d.content) as content_length,
               GROUP_CONCAT(t.name) as tags
        FROM documents d
        LEFT JOIN document_tags dt ON d.id = dt.document_id
        LEFT JOIN tags t ON dt.tag_id = t.id
        WHERE d.is_deleted = 0
        GROUP BY d.id
        ORDER BY d.title, d.created_at
    """)
    
    documents = cursor.fetchall()
    total_docs = len(documents)
    
    # Track duplicates
    exact_dupes = defaultdict(list)  # content_hash -> [doc_ids]
    title_dupes = defaultdict(list)  # normalized_title -> [doc_ids]
    near_dupes = []  # [(doc1, doc2, similarity)]
    
    # Build lookup structures
    doc_by_id = {doc['id']: doc for doc in documents}
    
    # Find exact content duplicates
    print("📌 Phase 1: Finding exact content duplicates...")
    for doc in documents:
        content_hash = get_content_hash(doc['content'])
        exact_dupes[content_hash].append(doc)
    
    # Count exact duplicates
    exact_dupe_groups = [docs for docs in exact_dupes.values() if len(docs) > 1]
    exact_dupe_count = sum(len(group) - 1 for group in exact_dupe_groups)  # -1 to keep one original
    
    print(f"  Found {len(exact_dupe_groups)} groups with {exact_dupe_count} duplicate documents\n")
    
    # Find title duplicates
    print("📌 Phase 2: Finding title-based duplicates...")
    for doc in documents:
        normalized = normalize_title(doc['title'])
        if normalized:  # Skip empty normalized titles
            title_dupes[normalized].append(doc)
    
    # Count title duplicates
    title_dupe_groups = [docs for docs in title_dupes.values() if len(docs) > 1]
    title_dupe_count = sum(len(group) - 1 for group in title_dupe_groups)
    
    print(f"  Found {len(title_dupe_groups)} groups with {title_dupe_count} similar titles\n")
    
    # Find near-duplicate content (for medium-sized docs)
    print("📌 Phase 3: Finding near-duplicate content...")
    # Only check documents with reasonable content length
    content_docs = [d for d in documents if 100 < (d['content_length'] or 0) < 5000]
    
    checked_pairs = set()
    for i, doc1 in enumerate(content_docs):
        if i % 50 == 0 and i > 0:
            print(f"  Checked {i}/{len(content_docs)} documents...")
        
        for j, doc2 in enumerate(content_docs[i+1:], i+1):
            pair_key = tuple(sorted([doc1['id'], doc2['id']]))
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            
            # Check similarity
            if doc1['content'] and doc2['content']:
                similarity = difflib.SequenceMatcher(None, doc1['content'], doc2['content']).ratio()
                if similarity > 0.85:  # 85% similar
                    near_dupes.append((doc1, doc2, similarity))
    
    print(f"  Found {len(near_dupes)} near-duplicate pairs\n")
    
    # Display results
    print("="*80)
    print("📊 DUPLICATE ANALYSIS RESULTS")
    print("="*80)
    
    # Exact content duplicates
    print(f"\n🔴 EXACT CONTENT DUPLICATES: {exact_dupe_count} documents in {len(exact_dupe_groups)} groups")
    print("-"*80)
    
    for i, group in enumerate(exact_dupe_groups[:10], 1):
        print(f"\nGroup {i} ({len(group)} documents):")
        # Sort by access count to identify primary
        sorted_group = sorted(group, key=lambda x: x['access_count'], reverse=True)
        for j, doc in enumerate(sorted_group):
            status = "PRIMARY" if j == 0 else "DUPLICATE"
            print(f"  [{doc['id']:4d}] {doc['title'][:50]:50s} | {doc['access_count']:3d} views | {status}")
    
    if len(exact_dupe_groups) > 10:
        print(f"\n... and {len(exact_dupe_groups) - 10} more groups")
    
    # Title-based duplicates
    print(f"\n🟡 SIMILAR TITLES: {title_dupe_count} documents in {len(title_dupe_groups)} groups")
    print("-"*80)
    
    interesting_title_groups = [g for g in title_dupe_groups if len(g) > 2 or any(d['access_count'] > 10 for d in g)]
    
    for i, group in enumerate(interesting_title_groups[:10], 1):
        normalized = normalize_title(group[0]['title'])
        print(f"\nGroup {i} - '{normalized}' ({len(group)} documents):")
        sorted_group = sorted(group, key=lambda x: x['access_count'], reverse=True)
        for doc in sorted_group:
            tags = doc['tags'] or 'untagged'
            print(f"  [{doc['id']:4d}] {doc['title'][:40]:40s} | {doc['access_count']:3d} views | {tags}")
    
    # Near-duplicate content
    print(f"\n🟠 NEAR-DUPLICATE CONTENT: {len(near_dupes)} pairs")
    print("-"*80)
    
    for i, (doc1, doc2, similarity) in enumerate(sorted(near_dupes, key=lambda x: x[2], reverse=True)[:10], 1):
        print(f"\nPair {i} ({similarity*100:.1f}% similar):")
        print(f"  [{doc1['id']:4d}] {doc1['title'][:50]:50s} | {doc1['access_count']:3d} views")
        print(f"  [{doc2['id']:4d}] {doc2['title'][:50]:50s} | {doc2['access_count']:3d} views")
    
    # Summary statistics
    print("\n" + "="*80)
    print("📈 SUMMARY STATISTICS")
    print("="*80)
    
    total_duplicates = exact_dupe_count + len(near_dupes)
    duplicate_percentage = (total_duplicates / total_docs * 100) if total_docs > 0 else 0
    
    print(f"\nTotal documents analyzed: {total_docs}")
    print(f"Exact content duplicates: {exact_dupe_count}")
    print(f"Near-duplicate pairs: {len(near_dupes)}")
    print(f"Similar title groups: {len(title_dupe_groups)}")
    print(f"\nEstimated duplicates: {total_duplicates} ({duplicate_percentage:.1f}% of total)")
    
    # Recommendations
    print("\n💡 RECOMMENDATIONS")
    print("="*80)
    
    if exact_dupe_count > 0:
        print(f"\n1. Delete {exact_dupe_count} exact duplicates")
        print("   - Keep the version with highest view count")
        print("   - Merge any unique tags before deletion")
    
    if len(near_dupes) > 5:
        print(f"\n2. Review {len(near_dupes)} near-duplicate pairs")
        print("   - Consider merging similar content")
        print("   - Consolidate related information")
    
    if len(title_dupe_groups) > 10:
        print(f"\n3. Standardize titles for {len(title_dupe_groups)} groups")
        print("   - Use consistent naming conventions")
        print("   - Add version numbers where appropriate")
    
    # Export duplicate IDs for deletion
    duplicate_ids = []
    for group in exact_dupe_groups:
        sorted_group = sorted(group, key=lambda x: x['access_count'], reverse=True)
        duplicate_ids.extend([doc['id'] for doc in sorted_group[1:]])  # Keep first (highest views)
    
    if duplicate_ids:
        with open('duplicate_ids_to_delete.txt', 'w') as f:
            f.write('\n'.join(map(str, duplicate_ids)))
        print(f"\n📄 Exported {len(duplicate_ids)} duplicate IDs to: duplicate_ids_to_delete.txt")
    
    conn.close()

if __name__ == "__main__":
    main()