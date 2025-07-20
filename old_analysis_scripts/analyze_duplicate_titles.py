#!/usr/bin/env python3
"""
Analyze documents with duplicate titles but different content
"""

import sqlite3
import os
from pathlib import Path
from collections import defaultdict
import difflib

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
    
    print("🔍 Analyzing documents with duplicate titles...\n")
    
    # Get all active documents grouped by title
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
    
    # Group by exact title
    title_groups = defaultdict(list)
    for doc in documents:
        title_groups[doc['title'].strip()].append(doc)
    
    # Filter to only duplicate titles
    duplicate_title_groups = {title: docs for title, docs in title_groups.items() if len(docs) > 1}
    
    # Categorize duplicate title patterns
    categories = {
        'test_documents': [],
        'readme_files': [],
        'analysis_docs': [],
        'gameplan_docs': [],
        'quick_notes': [],
        'command_outputs': [],
        'phase_docs': [],
        'implementation_docs': [],
        'other': []
    }
    
    for title, docs in duplicate_title_groups.items():
        title_lower = title.lower()
        
        if 'test' in title_lower:
            categories['test_documents'].append((title, docs))
        elif title_lower in ['readme', 'readme.md']:
            categories['readme_files'].append((title, docs))
        elif title.startswith('Analysis:'):
            categories['analysis_docs'].append((title, docs))
        elif title.startswith('Gameplan:'):
            categories['gameplan_docs'].append((title, docs))
        elif 'quick note' in title_lower or 'new note' in title_lower:
            categories['quick_notes'].append((title, docs))
        elif 'command:' in title_lower or 'output' in title_lower:
            categories['command_outputs'].append((title, docs))
        elif 'phase' in title_lower:
            categories['phase_docs'].append((title, docs))
        elif 'implementation' in title_lower:
            categories['implementation_docs'].append((title, docs))
        else:
            categories['other'].append((title, docs))
    
    # Display results
    print("="*80)
    print("📊 DUPLICATE TITLE ANALYSIS")
    print("="*80)
    
    total_dupes = sum(len(docs) for docs in duplicate_title_groups.values())
    print(f"\nTotal documents with duplicate titles: {total_dupes}")
    print(f"Unique titles that are duplicated: {len(duplicate_title_groups)}\n")
    
    # Show breakdown by category
    for category, groups in categories.items():
        if groups:
            doc_count = sum(len(docs) for _, docs in groups)
            print(f"\n{'🧪' if category == 'test_documents' else '📄'} {category.replace('_', ' ').upper()}: {doc_count} documents in {len(groups)} groups")
            print("-"*80)
            
            # Show details for each group
            for title, docs in sorted(groups, key=lambda x: len(x[1]), reverse=True)[:5]:
                print(f"\n'{title}' ({len(docs)} copies):")
                
                # Check if content is actually different
                contents = [doc['content'] for doc in docs]
                all_same = all(c == contents[0] for c in contents)
                
                if all_same:
                    print("  ⚠️  SAME CONTENT - These are actual duplicates!")
                else:
                    print("  ✓ Different content")
                
                for doc in sorted(docs, key=lambda x: x['access_count'], reverse=True):
                    project = doc['project'] or '[No Project]'
                    tags = doc['tags'] or 'untagged'
                    print(f"    [{doc['id']:4d}] {project:20s} | {doc['access_count']:3d} views | {doc['content_length']:6d} chars | {tags}")
                
                # If different content, show similarity
                if not all_same and len(docs) == 2:
                    similarity = difflib.SequenceMatcher(None, docs[0]['content'], docs[1]['content']).ratio()
                    print(f"    Similarity: {similarity*100:.1f}%")
    
    # Recommendations
    print("\n\n💡 RECOMMENDATIONS BY CATEGORY")
    print("="*80)
    
    if categories['readme_files']:
        print("\n📚 README Files:")
        print("  - Add project name to title: 'README - [Project]'")
        print("  - Or merge into single comprehensive README")
    
    if categories['test_documents']:
        print("\n🧪 Test Documents:")
        print("  - Add test type/date: 'Test: [Feature] - [Date]'")
        print("  - Consider deleting old test documents")
    
    if categories['analysis_docs']:
        print("\n🔍 Analysis Documents:")
        print("  - Add version or date: 'Analysis: [Topic] v2'")
        print("  - Archive older analyses")
    
    if categories['gameplan_docs']:
        print("\n🎯 Gameplan Documents:")
        print("  - Add status to title: 'Gameplan: [Topic] [ACTIVE/DONE]'")
        print("  - Merge related gameplans")
    
    # Find potentially mergeable documents
    print("\n\n🔀 POTENTIALLY MERGEABLE DOCUMENTS")
    print("="*80)
    
    merge_candidates = []
    for title, docs in duplicate_title_groups.items():
        if len(docs) == 2:
            # Check similarity
            if docs[0]['content'] and docs[1]['content']:
                similarity = difflib.SequenceMatcher(None, docs[0]['content'], docs[1]['content']).ratio()
                if 0.7 < similarity < 1.0:  # Similar but not identical
                    merge_candidates.append((title, docs, similarity))
    
    merge_candidates.sort(key=lambda x: x[2], reverse=True)
    
    for title, docs, similarity in merge_candidates[:10]:
        print(f"\n'{title}' ({similarity*100:.1f}% similar):")
        for doc in docs:
            print(f"  [{doc['id']:4d}] {doc['project'] or '[No Project]':20s} | {doc['access_count']:3d} views | Created: {doc['created_at'][:10]}")
    
    conn.close()

if __name__ == "__main__":
    main()