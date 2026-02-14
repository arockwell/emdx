# ADR-001: SQLite + FTS5 as Storage Layer

## Status

Accepted

## Context

EMDX is a knowledge base CLI tool designed for developers. It needs to store documents, tags, executions, and other metadata with the following requirements:

- **Local-first**: No cloud dependencies or database server setup required
- **Fast full-text search**: Users need to quickly find documents by content
- **Portable**: Easy backup, sync, and transfer of the knowledge base
- **Reliable**: ACID transactions with data integrity guarantees
- **Simple deployment**: Single-file distribution, no external services

We considered several alternatives:

1. **PostgreSQL/MySQL**: Full-featured RDBMS with excellent search capabilities
2. **Elasticsearch**: Purpose-built for full-text search
3. **File-based storage** (JSON/YAML): Simple but limited query capabilities
4. **SQLite without FTS**: Simpler but LIKE queries are slow for full-text search
5. **SQLite with FTS5**: Embedded database with built-in full-text search

## Decision

We chose **SQLite with FTS5** (Full-Text Search version 5) as the storage layer.

### Key implementation details:

- **Single database file** at `~/.emdx/emdx.db`
- **FTS5 virtual table** (`documents_fts`) synchronized with the main `documents` table
- **WAL mode** for better concurrency during read-heavy workloads
- **Foreign key constraints** for referential integrity
- **Versioned migrations** for safe schema evolution (currently 36+ migrations)

### Schema highlights:

```sql
-- Core document storage
CREATE TABLE documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    project TEXT,
    created_at TEXT NOT NULL,
    -- ... additional fields
);

-- Full-text search virtual table
CREATE VIRTUAL TABLE documents_fts USING fts5(
    title,
    content,
    project,
    content='documents',
    content_rowid='id'
);
```

## Consequences

### Positive

- **Zero setup**: Users install EMDX and immediately have a working database
- **Fast search**: FTS5 provides ranked full-text search with BM25 scoring
- **Portable**: Single file can be backed up with `cp` or synced via cloud storage
- **Reliable**: SQLite is battle-tested; ACID transactions prevent data corruption
- **No dependencies**: No need to install or run a database server
- **Good tooling**: SQLite has excellent ecosystem (DB Browser, CLI tools, libraries)

### Negative

- **Single-user**: SQLite doesn't support multiple writers efficiently (not a concern for EMDX's use case)
- **Size limitations**: Very large knowledge bases (100k+ documents) may need different approach
- **No replication**: Built-in replication requires external tools (also not a concern for local-first design)

### Mitigations

- **Concurrency**: WAL mode provides good read concurrency; EMDX's workload is read-heavy
- **Performance**: Proper indexing and connection pooling keep queries fast
- **Scaling**: If users outgrow SQLite, future versions could support PostgreSQL as an optional backend

## References

- [SQLite FTS5 Documentation](https://www.sqlite.org/fts5.html)
- [SQLite is not a toy database](https://antonz.org/sqlite-is-not-a-toy-database/)
- [EMDX Database Design](../database-design.md)
