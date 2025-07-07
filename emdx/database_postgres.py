"""
PostgreSQL database connection and operations for emdx
(Preserved for migration purposes)
"""

import os
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

# Load environment variables from multiple sources
# 1. First, try user config directory
user_config = Path.home() / '.config' / 'emdx' / '.env'
if user_config.exists():
    load_dotenv(user_config)

# 2. Then load from current directory (for development)
load_dotenv()


class PostgresDatabase:
    """PostgreSQL database connection manager for emdx"""
    
    def __init__(self, connection_url: Optional[str] = None):
        self.connection_url = connection_url or os.getenv("EMDX_DATABASE_URL") or self._build_default_url()
    
    def _build_default_url(self) -> str:
        """Build default PostgreSQL connection URL"""
        host = os.getenv("PGHOST", "localhost")
        port = os.getenv("PGPORT", "5432")
        user = os.getenv("PGUSER", os.getenv("USER", "postgres"))
        password = os.getenv("PGPASSWORD", "")
        database = os.getenv("PGDATABASE", user)
        
        if password:
            return f"postgresql://{user}:{password}@{host}:{port}/{database}"
        return f"postgresql://{user}@{host}:{port}/{database}"
    
    @contextmanager
    def get_connection(self):
        """Get a database connection with context manager"""
        conn = psycopg.connect(self.connection_url, row_factory=dict_row)
        try:
            yield conn
        finally:
            conn.close()
    
    def ensure_schema(self):
        """Ensure the claude schema and knowledge table exist"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Create schema if not exists
                cur.execute("CREATE SCHEMA IF NOT EXISTS claude")
                
                # Create knowledge table if not exists
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS claude.knowledge (
                        id SERIAL PRIMARY KEY,
                        title TEXT NOT NULL,
                        content TEXT NOT NULL,
                        project TEXT,
                        search_vector tsvector,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        accessed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        access_count INTEGER DEFAULT 0
                    )
                """)
                
                # Create indexes
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_knowledge_search_vector 
                    ON claude.knowledge USING GIN (search_vector)
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_knowledge_project 
                    ON claude.knowledge (project)
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_knowledge_accessed 
                    ON claude.knowledge (accessed_at DESC)
                """)
                
                # Create or replace the trigger function
                cur.execute("""
                    CREATE OR REPLACE FUNCTION claude.update_search_vector()
                    RETURNS trigger AS $$
                    BEGIN
                        NEW.search_vector := 
                            setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
                            setweight(to_tsvector('english', COALESCE(NEW.content, '')), 'B');
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """)
                
                # Create trigger if not exists
                cur.execute("""
                    DROP TRIGGER IF EXISTS update_knowledge_search_vector ON claude.knowledge;
                    CREATE TRIGGER update_knowledge_search_vector
                    BEFORE INSERT OR UPDATE ON claude.knowledge
                    FOR EACH ROW EXECUTE FUNCTION claude.update_search_vector();
                """)
                
                conn.commit()
    
    def save_document(self, title: str, content: str, project: Optional[str] = None) -> int:
        """Save a document to the knowledge base"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO claude.knowledge (title, content, project)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (title, content, project))
                
                result = cur.fetchone()
                conn.commit()
                return result['id']
    
    def get_document(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Get a document by ID or title"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Try as ID first
                if identifier.isdigit():
                    cur.execute("""
                        UPDATE claude.knowledge 
                        SET accessed_at = CURRENT_TIMESTAMP, 
                            access_count = access_count + 1
                        WHERE id = %s
                        RETURNING *
                    """, (int(identifier),))
                else:
                    # Try as title
                    cur.execute("""
                        UPDATE claude.knowledge 
                        SET accessed_at = CURRENT_TIMESTAMP, 
                            access_count = access_count + 1
                        WHERE LOWER(title) = LOWER(%s)
                        RETURNING *
                    """, (identifier,))
                
                result = cur.fetchone()
                if result:
                    conn.commit()
                return result
    
    def list_documents(self, project: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """List documents with optional project filter"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if project:
                    cur.execute("""
                        SELECT id, title, project, created_at, access_count
                        FROM claude.knowledge
                        WHERE project = %s
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (project, limit))
                else:
                    cur.execute("""
                        SELECT id, title, project, created_at, access_count
                        FROM claude.knowledge
                        ORDER BY created_at DESC
                        LIMIT %s
                    """, (limit,))
                
                return cur.fetchall()
    
    def search_documents(self, query: str, project: Optional[str] = None, 
                        limit: int = 10, fuzzy: bool = False) -> List[Dict[str, Any]]:
        """Search documents using full-text search"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Build the search query
                if fuzzy:
                    # Use similarity search for fuzzy matching
                    if project:
                        cur.execute("""
                            SELECT id, title, project, created_at,
                                   ts_headline('english', content, plainto_tsquery('english', %s),
                                             'MaxWords=30, MinWords=10, StartSel=<b>, StopSel=</b>') as snippet,
                                   similarity(title || ' ' || content, %s) as score
                            FROM claude.knowledge
                            WHERE project = %s 
                              AND similarity(title || ' ' || content, %s) > 0.1
                            ORDER BY score DESC
                            LIMIT %s
                        """, (query, query, project, query, limit))
                    else:
                        cur.execute("""
                            SELECT id, title, project, created_at,
                                   ts_headline('english', content, plainto_tsquery('english', %s),
                                             'MaxWords=30, MinWords=10, StartSel=<b>, StopSel=</b>') as snippet,
                                   similarity(title || ' ' || content, %s) as score
                            FROM claude.knowledge
                            WHERE similarity(title || ' ' || content, %s) > 0.1
                            ORDER BY score DESC
                            LIMIT %s
                        """, (query, query, query, limit))
                else:
                    # Use full-text search
                    if project:
                        cur.execute("""
                            SELECT id, title, project, created_at,
                                   ts_headline('english', content, plainto_tsquery('english', %s),
                                             'MaxWords=30, MinWords=10, StartSel=<b>, StopSel=</b>') as snippet,
                                   ts_rank(search_vector, plainto_tsquery('english', %s)) as rank
                            FROM claude.knowledge
                            WHERE project = %s 
                              AND search_vector @@ plainto_tsquery('english', %s)
                            ORDER BY rank DESC
                            LIMIT %s
                        """, (query, query, project, query, limit))
                    else:
                        cur.execute("""
                            SELECT id, title, project, created_at,
                                   ts_headline('english', content, plainto_tsquery('english', %s),
                                             'MaxWords=30, MinWords=10, StartSel=<b>, StopSel=</b>') as snippet,
                                   ts_rank(search_vector, plainto_tsquery('english', %s)) as rank
                            FROM claude.knowledge
                            WHERE search_vector @@ plainto_tsquery('english', %s)
                            ORDER BY rank DESC
                            LIMIT %s
                        """, (query, query, query, limit))
                
                return cur.fetchall()
    
    def update_document(self, doc_id: int, title: str, content: str) -> bool:
        """Update a document"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE claude.knowledge
                    SET title = %s, content = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (title, content, doc_id))
                
                conn.commit()
                return cur.rowcount > 0
    
    def delete_document(self, identifier: str) -> bool:
        """Delete a document by ID or title"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if identifier.isdigit():
                    cur.execute("""
                        DELETE FROM claude.knowledge WHERE id = %s
                    """, (int(identifier),))
                else:
                    cur.execute("""
                        DELETE FROM claude.knowledge WHERE LOWER(title) = LOWER(%s)
                    """, (identifier,))
                
                conn.commit()
                return cur.rowcount > 0
    
    def get_recent_documents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently accessed documents"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, title, project, accessed_at, access_count
                    FROM claude.knowledge
                    ORDER BY accessed_at DESC
                    LIMIT %s
                """, (limit,))
                
                return cur.fetchall()
    
    def get_stats(self, project: Optional[str] = None) -> Dict[str, Any]:
        """Get database statistics"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if project:
                    # Project-specific stats
                    cur.execute("""
                        SELECT 
                            COUNT(*) as total_documents,
                            SUM(access_count) as total_views,
                            AVG(access_count) as avg_views,
                            MAX(created_at) as newest_doc,
                            MAX(accessed_at) as last_accessed
                        FROM claude.knowledge
                        WHERE project = %s
                    """, (project,))
                else:
                    # Overall stats
                    cur.execute("""
                        SELECT 
                            COUNT(*) as total_documents,
                            COUNT(DISTINCT project) as total_projects,
                            SUM(access_count) as total_views,
                            AVG(access_count) as avg_views,
                            MAX(created_at) as newest_doc,
                            MAX(accessed_at) as last_accessed,
                            pg_size_pretty(pg_total_relation_size('claude.knowledge')) as table_size
                        FROM claude.knowledge
                    """)
                
                stats = cur.fetchone()
                
                # Get most viewed document
                if project:
                    cur.execute("""
                        SELECT id, title, access_count
                        FROM claude.knowledge
                        WHERE project = %s
                        ORDER BY access_count DESC
                        LIMIT 1
                    """, (project,))
                else:
                    cur.execute("""
                        SELECT id, title, access_count
                        FROM claude.knowledge
                        ORDER BY access_count DESC
                        LIMIT 1
                    """)
                
                most_viewed = cur.fetchone()
                if most_viewed:
                    stats['most_viewed'] = most_viewed
                
                return stats