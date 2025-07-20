#!/usr/bin/env python3
"""
Analyze untagged documents in EMDX to understand patterns and categorize them
"""

import sqlite3
import os
from pathlib import Path
from collections import Counter, defaultdict
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

def categorize_by_title(title):
    """Categorize document based on title patterns"""
    title_lower = title.lower()
    
    # Check for specific patterns
    if title.startswith('Gameplan:'):
        return 'gameplan'
    elif title.startswith('Analysis:'):
        return 'analysis'
    elif title.startswith('Bug:'):
        return 'bug'
    elif title.startswith('Feature:'):
        return 'feature'
    elif title.startswith('Issue #'):
        return 'issue'
    elif title.startswith('PR '):
        return 'pr'
    elif title.startswith('Summary:'):
        return 'summary'
    elif 'quick note' in title_lower or title.startswith('Note -'):
        return 'note'
    elif 'test' in title_lower:
        return 'test'
    elif 'fix' in title_lower:
        return 'fix'
    elif 'debug' in title_lower:
        return 'debug'
    elif 'checkpoint' in title_lower:
        return 'checkpoint'
    elif 'implementation' in title_lower:
        return 'implementation'
    elif 'refactor' in title_lower:
        return 'refactor'
    elif 'vim' in title_lower:
        return 'vim-related'
    elif 'tui' in title_lower or 'textual' in title_lower:
        return 'tui-related'
    elif 'browser' in title_lower:
        return 'browser-related'
    elif 'git' in title_lower:
        return 'git-related'
    elif 'claude' in title_lower:
        return 'claude-related'
    else:
        return 'other'

def analyze_content_themes(content):
    """Extract themes from content"""
    if not content:
        return []
    
    content_lower = content.lower()
    themes = []
    
    # Technical themes
    if 'error' in content_lower or 'exception' in content_lower:
        themes.append('error-handling')
    if 'test' in content_lower:
        themes.append('testing')
    if 'implement' in content_lower:
        themes.append('implementation')
    if 'todo' in content_lower or 'task' in content_lower:
        themes.append('todo-list')
    if 'bug' in content_lower or 'fix' in content_lower:
        themes.append('bug-fix')
    if 'refactor' in content_lower:
        themes.append('refactoring')
    
    return themes

def main():
    db_path = find_database()
    print(f"Using database: {db_path}\n")
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all untagged documents
    print("🔍 Analyzing untagged documents...\n")
    
    cursor.execute("""
        SELECT d.id, d.title, d.content, d.project, d.access_count, 
               LENGTH(d.content) as content_length, d.created_at
        FROM documents d
        WHERE d.is_deleted = 0 
        AND NOT EXISTS (
            SELECT 1 FROM document_tags dt WHERE dt.document_id = d.id
        )
        ORDER BY d.access_count DESC
    """)
    
    untagged_docs = cursor.fetchall()
    total_untagged = len(untagged_docs)
    
    print(f"📊 Found {total_untagged} untagged documents\n")
    
    # Analyze by categories
    categories = Counter()
    project_breakdown = defaultdict(list)
    length_categories = {
        'empty': [],
        'short': [],
        'medium': [],
        'long': []
    }
    high_value_untagged = []
    content_themes = Counter()
    
    for doc in untagged_docs:
        # Categorize by title
        category = categorize_by_title(doc['title'])
        categories[category] += 1
        
        # Track by project
        project = doc['project'] or '[No Project]'
        project_breakdown[project].append(doc)
        
        # Categorize by length
        length = doc['content_length']
        if length < 100:
            length_categories['empty'].append(doc)
        elif length < 500:
            length_categories['short'].append(doc)
        elif length < 2000:
            length_categories['medium'].append(doc)
        else:
            length_categories['long'].append(doc)
        
        # Identify high-value untagged (high views)
        if doc['access_count'] > 10:
            high_value_untagged.append(doc)
        
        # Analyze content themes
        themes = analyze_content_themes(doc['content'])
        for theme in themes:
            content_themes[theme] += 1
    
    # Display results
    print("📂 BREAKDOWN BY DOCUMENT TYPE")
    print("=" * 50)
    for category, count in categories.most_common():
        percentage = (count / total_untagged * 100)
        print(f"{category:20s} {count:4d} ({percentage:5.1f}%)")
    
    print("\n🏗️ BREAKDOWN BY PROJECT")
    print("=" * 50)
    for project, docs in sorted(project_breakdown.items(), key=lambda x: len(x[1]), reverse=True)[:10]:
        count = len(docs)
        percentage = (count / total_untagged * 100)
        print(f"{project:30s} {count:4d} ({percentage:5.1f}%)")
    
    print("\n📏 BREAKDOWN BY CONTENT LENGTH")
    print("=" * 50)
    print(f"Empty (<100 chars):    {len(length_categories['empty']):4d} ({len(length_categories['empty'])/total_untagged*100:5.1f}%)")
    print(f"Short (100-500):       {len(length_categories['short']):4d} ({len(length_categories['short'])/total_untagged*100:5.1f}%)")
    print(f"Medium (500-2000):     {len(length_categories['medium']):4d} ({len(length_categories['medium'])/total_untagged*100:5.1f}%)")
    print(f"Long (>2000):          {len(length_categories['long']):4d} ({len(length_categories['long'])/total_untagged*100:5.1f}%)")
    
    print("\n🎯 HIGH-VALUE UNTAGGED (>10 views)")
    print("=" * 50)
    print(f"Total: {len(high_value_untagged)} documents\n")
    for doc in high_value_untagged[:15]:
        print(f"[{doc['id']:4d}] {doc['title'][:50]:50s} | {doc['access_count']:3d} views | {doc['content_length']:6d} chars")
    if len(high_value_untagged) > 15:
        print(f"... and {len(high_value_untagged) - 15} more")
    
    print("\n🎨 CONTENT THEMES DETECTED")
    print("=" * 50)
    for theme, count in content_themes.most_common():
        print(f"{theme:20s} {count:4d} documents")
    
    # Suggest tagging strategy
    print("\n💡 SUGGESTED TAGGING STRATEGY")
    print("=" * 50)
    print("\n1. QUICK WINS (High-value documents):")
    print(f"   - Tag {len(high_value_untagged)} high-view documents first")
    print("   - These have proven value and need organization")
    
    print("\n2. BY DOCUMENT TYPE:")
    gameplan_count = categories.get('gameplan', 0)
    analysis_count = categories.get('analysis', 0)
    if gameplan_count > 0:
        print(f"   - {gameplan_count} gameplans → add 🎯 (gameplan) + 🚀 (active)")
    if analysis_count > 0:
        print(f"   - {analysis_count} analyses → add 🔍 (analysis)")
    
    bug_fix_count = categories.get('bug', 0) + categories.get('fix', 0)
    if bug_fix_count > 0:
        print(f"   - {bug_fix_count} bug/fix docs → add 🐛 (bug)")
    
    print("\n3. BY PROJECT:")
    for project, docs in list(sorted(project_breakdown.items(), key=lambda x: len(x[1]), reverse=True))[:3]:
        if len(docs) > 20:
            print(f"   - {project}: {len(docs)} docs need project-specific tags")
    
    print("\n4. BATCH OPERATIONS:")
    print("   - Test documents: Add 🧪 (test) tag")
    print("   - Implementation docs: Add 🔧 (refactor) or ✨ (feature)")
    print("   - Empty/short docs: Consider deletion instead")
    
    # Sample documents for each category
    print("\n📋 SAMPLE UNTAGGED DOCUMENTS BY TYPE")
    print("=" * 50)
    
    for category in ['gameplan', 'analysis', 'bug', 'test', 'other'][:5]:
        docs_in_category = [d for d in untagged_docs if categorize_by_title(d['title']) == category]
        if docs_in_category:
            print(f"\n{category.upper()} (showing 3):")
            for doc in docs_in_category[:3]:
                print(f"  [{doc['id']:4d}] {doc['title'][:60]}")
    
    conn.close()

if __name__ == "__main__":
    main()