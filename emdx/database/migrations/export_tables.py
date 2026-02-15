"""Export system migrations.

These migrations establish export functionality:
- Google Docs exports
- Export profiles and history
"""

import sqlite3


def migration_012_add_gdocs(conn: sqlite3.Connection):
    """Add gdocs table for tracking Google Docs exports."""
    cursor = conn.cursor()

    # Create gdocs table for tracking document-gdoc relationships
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gdocs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            gdoc_id TEXT NOT NULL,
            gdoc_url TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(document_id, gdoc_id),
            FOREIGN KEY (document_id) REFERENCES documents (id)
        )
    """)

    # Create indexes for gdocs table
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gdocs_document ON gdocs(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_gdocs_gdoc_id ON gdocs(gdoc_id)")

    conn.commit()


def migration_015_add_export_profiles(conn: sqlite3.Connection):
    """Add export profiles and export history tables.

    Export profiles provide reusable, configurable export configurations
    for transforming and exporting EMDX documents to various formats and
    destinations (clipboard, file, Google Docs, GitHub Gist).
    """
    cursor = conn.cursor()

    # Create export_profiles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS export_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT,
            format TEXT NOT NULL DEFAULT 'markdown',
            strip_tags TEXT,  -- JSON array of emoji tags to strip
            add_frontmatter BOOLEAN DEFAULT FALSE,
            frontmatter_fields TEXT,  -- JSON array: ['title', 'date', 'tags']
            header_template TEXT,
            footer_template TEXT,
            tag_to_label TEXT,  -- JSON object: {'🔧': 'refactor', '🐛': 'bug'}
            dest_type TEXT NOT NULL DEFAULT 'clipboard',
            dest_path TEXT,
            gdoc_folder TEXT,
            gist_public BOOLEAN DEFAULT FALSE,
            post_actions TEXT,  -- JSON array: ['copy_url', 'open_browser']
            project TEXT,  -- NULL = global profile
            is_active BOOLEAN DEFAULT TRUE,
            is_builtin BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            use_count INTEGER DEFAULT 0,
            last_used_at TIMESTAMP
        )
    """)

    # Create export_history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS export_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            profile_id INTEGER NOT NULL,
            dest_type TEXT NOT NULL,
            dest_url TEXT,
            exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id),
            FOREIGN KEY (profile_id) REFERENCES export_profiles(id)
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_profiles_name ON export_profiles(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_profiles_project ON export_profiles(project)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_profiles_is_active ON export_profiles(is_active)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_history_document ON export_history(document_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_export_history_profile ON export_history(profile_id)")

    # Insert built-in profiles
    builtin_profiles = [
        {
            'name': 'blog-post',
            'display_name': 'Blog Post',
            'description': 'Export as blog post with YAML frontmatter',
            'format': 'markdown',
            'add_frontmatter': True,
            'frontmatter_fields': '["title", "date", "tags"]',
            'strip_tags': '["🚧", "🚨", "🐛"]',
            'dest_type': 'file',
            'dest_path': '~/blog/drafts/{{title}}.md',
            'is_builtin': True,
        },
        {
            'name': 'gdoc-meeting',
            'display_name': 'Google Doc (Meeting)',
            'description': 'Export meeting notes to Google Docs',
            'format': 'gdoc',
            'header_template': '# Meeting Notes: {{title}}\n\nDate: {{date}}\n',
            'dest_type': 'gdoc',
            'gdoc_folder': 'EMDX Meetings',
            'is_builtin': True,
        },
        {
            'name': 'github-issue',
            'display_name': 'GitHub Issue',
            'description': 'Format for GitHub issue creation',
            'format': 'markdown',
            'tag_to_label': '{"🐛": "bug", "✨": "enhancement", "🔧": "refactor"}',
            'strip_tags': '["🚧", "🚨"]',
            'dest_type': 'clipboard',
            'is_builtin': True,
        },
        {
            'name': 'share-external',
            'display_name': 'Share External',
            'description': 'Clean version for external sharing',
            'format': 'markdown',
            'strip_tags': '["🚧", "🚨", "🐛", "🎯", "🔍"]',
            'dest_type': 'clipboard',
            'is_builtin': True,
        },
        {
            'name': 'quick-gist',
            'display_name': 'Quick Gist',
            'description': 'Create secret GitHub gist',
            'format': 'gist',
            'dest_type': 'gist',
            'gist_public': False,
            'post_actions': '["copy_url", "open_browser"]',
            'is_builtin': True,
        },
    ]

    for profile in builtin_profiles:
        cursor.execute("""
            INSERT OR IGNORE INTO export_profiles (
                name, display_name, description, format,
                add_frontmatter, frontmatter_fields, strip_tags,
                header_template, footer_template, tag_to_label,
                dest_type, dest_path, gdoc_folder, gist_public,
                post_actions, is_builtin
            ) VALUES (
                :name, :display_name, :description, :format,
                :add_frontmatter, :frontmatter_fields, :strip_tags,
                :header_template, :footer_template, :tag_to_label,
                :dest_type, :dest_path, :gdoc_folder, :gist_public,
                :post_actions, :is_builtin
            )
        """, {
            'name': profile.get('name'),
            'display_name': profile.get('display_name'),
            'description': profile.get('description'),
            'format': profile.get('format', 'markdown'),
            'add_frontmatter': profile.get('add_frontmatter', False),
            'frontmatter_fields': profile.get('frontmatter_fields'),
            'strip_tags': profile.get('strip_tags'),
            'header_template': profile.get('header_template'),
            'footer_template': profile.get('footer_template'),
            'tag_to_label': profile.get('tag_to_label'),
            'dest_type': profile.get('dest_type', 'clipboard'),
            'dest_path': profile.get('dest_path'),
            'gdoc_folder': profile.get('gdoc_folder'),
            'gist_public': profile.get('gist_public', False),
            'post_actions': profile.get('post_actions'),
            'is_builtin': profile.get('is_builtin', False),
        })

    conn.commit()
