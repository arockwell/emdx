# Option B: Extract Cascade Metadata from Documents Table

## Executive Summary

This document analyzes the extraction of cascade-specific metadata (stage, pr_url) from the `documents` table into a dedicated `document_cascade_metadata` table. After exploring wild architectural ideas and evaluating trade-offs, we recommend a straightforward extraction approach that maintains backward compatibility while enabling future system separation.

## Current State Analysis

### Schema Overview

The `documents` table currently has two cascade-specific columns added by migrations 028 and 029:

```sql
-- Migration 028: Add document stage for cascade
ALTER TABLE documents ADD COLUMN stage TEXT DEFAULT NULL

-- Migration 029: Add document PR URL for cascade
ALTER TABLE documents ADD COLUMN pr_url TEXT DEFAULT NULL
```

### Coupling Points Identified

**1. Database Functions (emdx/database/documents.py)**
- `get_oldest_at_stage(stage)` - Queue-like access for cascade processing
- `update_document_stage(doc_id, stage)` - State transitions
- `update_document_pr_url(doc_id, pr_url)` - PR linking
- `get_document_pr_url(doc_id)` - PR retrieval
- `list_documents_at_stage(stage, limit)` - Stage listings
- `count_documents_at_stage(stage)` - Stage counts
- `get_cascade_stats()` - Aggregate counts per stage
- `save_document_to_cascade(...)` - Direct cascade insertion

**2. Cascade Command (emdx/commands/cascade.py)**
All cascade operations use these database functions:
- `add` command → `save_document_to_cascade()`
- `process` command → `get_oldest_at_stage()`, `update_document_stage()`
- `advance` command → `update_document_stage()`
- `remove` command → `update_document_stage(doc_id, None)`
- `status` command → `get_cascade_stats()`
- `show` command → `list_documents_at_stage()`
- `_process_stage()` → `update_document_stage()`, `update_document_pr_url()`

**3. UI Components**
- `emdx/ui/cascade_browser.py` - Full cascade TUI
- `emdx/ui/activity/activity_view.py` - Shows stage/pr_url in activity items

**4. Related Tables**
- `cascade_runs` - Tracks end-to-end cascade executions
- `executions.cascade_run_id` - Links executions to cascade runs

---

## Wild Ideas Exploration

### Wild Idea 1: Event-Sourced Document History

**Concept**: Every change to a document is an immutable event. State is derived by replaying events.

```sql
CREATE TABLE document_events (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,  -- 'stage_changed', 'pr_linked', 'content_updated'
    event_data TEXT NOT NULL,  -- JSON payload
    actor TEXT,                -- 'claude', 'user', 'system'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Current state computed via:
SELECT * FROM document_events
WHERE document_id = ?
ORDER BY created_at DESC;
```

**Pros**:
- Complete audit trail of all changes
- Time-travel debugging ("what stage was doc #123 at 2pm?")
- Enables replay for testing and recovery
- Perfect for multi-agent coordination (who changed what?)

**Cons**:
- Significant complexity increase
- All reads become aggregations (performance penalty)
- Requires event replay logic everywhere
- Overkill for current use case
- Would need to refactor ALL document operations

**Verdict**: REJECTED - Too much complexity for the current need. Document changes are already implicitly logged through parent_id chains and the documents_fts trigger system. Could revisit if multi-agent coordination becomes critical.

---

### Wild Idea 2: Separate "Execution Context" Database

**Concept**: Split EMDX into two databases - one for content (documents, tags, groups) and one for execution context (cascade state, workflow runs, executions).

```
~/.config/emdx/
├── knowledge.db        # documents, tags, document_groups, etc.
└── execution.db        # cascade_metadata, cascade_runs, executions, workflows
```

**Pros**:
- Clean separation of concerns
- Can backup/restore content independently
- Execution data can be ephemeral/purgeable
- Different retention policies per database
- Could eventually be in different locations (local vs. cloud)

**Cons**:
- Cross-database joins become complex
- Transaction boundaries are tricky
- Migration path is involved
- UI code needs to handle two connections
- "Which database is this query against?"

**Verdict**: DEFER - Interesting for future but overcomplicates the extraction. Worth noting as a potential phase 2 if EMDX evolves into a distributed system.

---

### Wild Idea 3: Generic Metadata JSON Blob

**Concept**: Instead of typed columns, store all metadata as a single JSON blob.

```sql
CREATE TABLE document_metadata (
    document_id INTEGER PRIMARY KEY,
    metadata TEXT NOT NULL DEFAULT '{}',  -- JSON
    updated_at TIMESTAMP
);

-- Usage:
UPDATE document_metadata
SET metadata = json_set(metadata, '$.stage', 'analyzed')
WHERE document_id = 123;

SELECT json_extract(metadata, '$.stage') FROM document_metadata;
```

**Pros**:
- Infinitely extensible without migrations
- No schema changes needed for new metadata types
- Works well for sparse data
- SQLite's JSON1 extension is powerful

**Cons**:
- Loses type safety and constraints
- No proper indexing (would need generated columns)
- Harder to query efficiently
- Validation moves to application layer
- Schema discovery requires documentation

**Verdict**: PARTIAL KEEP - The flexibility is appealing for future extensibility. Hybrid approach possible: typed columns for indexed/common fields, JSON for rarely-queried extras.

---

### Wild Idea 4: Graph Database for Document Relationships

**Concept**: Model cascade flow as a graph with documents as nodes and transitions as edges.

```
Document #1 (idea)
    |
    v [stage_transition: idea→prompt]
Document #2 (prompt, parent_id=1)
    |
    v [stage_transition: prompt→analyzed]
Document #3 (analyzed, parent_id=2)
```

**Implementation Options**:
- SQLite recursive CTEs (already possible!)
- Dedicated graph DB (DuckDB, Neo4j)
- In-memory graph structure

**Pros**:
- Natural model for cascade transformations
- Enables complex queries ("all descendants of idea #1")
- Relationship types are explicit
- Could visualize cascade as true DAG

**Cons**:
- SQLite is not a graph database (CTEs are workarounds)
- External graph DB adds operational complexity
- Current parent_id + stage is sufficient for current needs
- Overkill for linear cascade flow

**Verdict**: REJECTED - The cascade is fundamentally a linear transformation pipeline, not a graph. Parent_id already captures the lineage. Graph modeling adds complexity without benefit.

---

## Practical Recommendation: Extract to document_cascade_metadata

### Design

```sql
-- New table: document_cascade_metadata
CREATE TABLE document_cascade_metadata (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL UNIQUE,
    stage TEXT,
    pr_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);

CREATE INDEX idx_cascade_meta_stage ON document_cascade_metadata(stage) WHERE stage IS NOT NULL;
CREATE INDEX idx_cascade_meta_pr_url ON document_cascade_metadata(pr_url) WHERE pr_url IS NOT NULL;
```

### Why This Approach

1. **Minimal disruption**: Same data model, just different location
2. **Clear ownership**: Cascade operations own this table
3. **Backward compatible**: Can keep old columns during transition
4. **Sparse storage**: Only ~1% of documents are in cascade
5. **Clean separation**: `documents` stays "pure content"
6. **Future-ready**: Easy to move to separate database later

---

## Migration Plan

### Phase 1: Create New Table + Backfill (Migration 032)

```python
def migration_032_extract_cascade_metadata(conn: sqlite3.Connection):
    """Extract cascade metadata to dedicated table."""
    cursor = conn.cursor()

    # Create the new table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_cascade_metadata (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL UNIQUE,
            stage TEXT,
            pr_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        )
    """)

    # Create indexes
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cascade_meta_stage
        ON document_cascade_metadata(stage) WHERE stage IS NOT NULL
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_cascade_meta_pr_url
        ON document_cascade_metadata(pr_url) WHERE pr_url IS NOT NULL
    """)

    # Backfill from existing data
    cursor.execute("""
        INSERT INTO document_cascade_metadata (document_id, stage, pr_url, created_at, updated_at)
        SELECT id, stage, pr_url, updated_at, updated_at
        FROM documents
        WHERE stage IS NOT NULL OR pr_url IS NOT NULL
    """)

    conn.commit()
```

### Phase 2: Dual-Write (Transition Period)

Update database functions to write to both locations:

```python
def update_document_stage(doc_id: int, stage: str | None) -> bool:
    """Update a document's cascade stage."""
    with db_connection.get_connection() as conn:
        # Write to new table (upsert)
        conn.execute("""
            INSERT INTO document_cascade_metadata (document_id, stage, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(document_id) DO UPDATE SET
                stage = excluded.stage,
                updated_at = CURRENT_TIMESTAMP
        """, (doc_id, stage))

        # Also update old column (for backward compat)
        conn.execute("""
            UPDATE documents
            SET stage = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND is_deleted = FALSE
        """, (stage, doc_id))

        conn.commit()
        return True
```

### Phase 3: Switch Reads to New Table

Update all read operations:

```python
def get_oldest_at_stage(stage: str) -> dict[str, Any] | None:
    """Get the oldest document at a given cascade stage."""
    with db_connection.get_connection() as conn:
        cursor = conn.execute("""
            SELECT d.* FROM documents d
            JOIN document_cascade_metadata cm ON d.id = cm.document_id
            WHERE cm.stage = ? AND d.is_deleted = FALSE
            ORDER BY d.created_at ASC
            LIMIT 1
        """, (stage,))
        row = cursor.fetchone()
        return _parse_doc_datetimes(dict(row)) if row else None
```

### Phase 4: Remove Old Columns (Future Migration)

After sufficient testing period:

```python
def migration_033_drop_old_cascade_columns(conn: sqlite3.Connection):
    """Remove cascade columns from documents table."""
    # SQLite doesn't support DROP COLUMN directly before 3.35
    # Need to recreate table
    cursor = conn.cursor()

    # This is a major migration - defer until confident
    # For now, just remove indexes on old columns
    cursor.execute("DROP INDEX IF EXISTS idx_documents_stage")
    cursor.execute("DROP INDEX IF EXISTS idx_documents_pr_url")

    conn.commit()
```

---

## What Breaks During Transition?

### Immediate Compatibility
- **Nothing breaks immediately** - Phase 1-2 maintain full backward compatibility
- Old code still works because documents table still has columns
- New code writes to both locations

### After Phase 3 (Switch Reads)
- Code reading directly from documents.stage/pr_url needs update
- This includes:
  - `emdx/ui/activity/activity_view.py` lines 814, 864-865
  - `emdx/ui/cascade_browser.py` line 590, 831
  - Any direct SQL queries in tests

### After Phase 4 (Column Removal)
- Raw SQL queries against documents.stage fail
- Need to search codebase for literal "d.stage" or "documents.stage"

---

## Performance Impact

### Current (columns in documents table)
```sql
-- Simple single-table scan
SELECT * FROM documents WHERE stage = 'idea' ORDER BY created_at LIMIT 1;
-- Index scan on idx_documents_stage
```

### After (join with metadata table)
```sql
-- Join required
SELECT d.* FROM documents d
JOIN document_cascade_metadata cm ON d.id = cm.document_id
WHERE cm.stage = 'idea' AND d.is_deleted = FALSE
ORDER BY d.created_at LIMIT 1;
```

**Expected Impact**:
- ~1-2ms overhead per query (index nested loop join)
- Negligible for cascade operations (typically 1-5 docs per stage)
- No impact on non-cascade document operations (majority of usage)

**Mitigation**: Can add covering index if needed:
```sql
CREATE INDEX idx_cascade_meta_stage_doc
ON document_cascade_metadata(stage, document_id);
```

---

## How This Enables Future Separation

### Path to Separate Database

Once cascade metadata is in its own table, moving to a separate database becomes mechanical:

1. **Create execution.db** with cascade tables
2. **Add connection abstraction** that routes queries
3. **Move tables** (cascade_metadata, cascade_runs) to execution.db
4. **Update imports** in cascade command and UI

### Path to Microservice

If EMDX ever becomes distributed:

1. Cascade metadata table → Cascade service
2. Document content → Content service
3. Clear API boundary at the table level
4. Each service owns its data

---

## Recommendations

### Immediate Actions
1. Create migration 032 with new table + backfill
2. Add cascade-specific functions to new `emdx/database/cascade.py` module
3. Update cascade command to use new module
4. Update UI components

### Transition Period (2-4 weeks)
1. Dual-write to maintain compatibility
2. Monitor for any direct SQL access to old columns
3. Add deprecation warnings in old functions

### Cleanup (After confidence)
1. Switch all reads to new table
2. Remove dual-write
3. Drop old columns (Phase 4)

---

## Files to Modify

| File | Changes |
|------|---------|
| `emdx/database/migrations.py` | Add migration 032 |
| `emdx/database/cascade.py` | NEW - cascade-specific operations |
| `emdx/database/documents.py` | Deprecate/redirect cascade functions |
| `emdx/commands/cascade.py` | Update imports to use cascade.py |
| `emdx/ui/cascade_browser.py` | Update queries to join new table |
| `emdx/ui/activity/activity_view.py` | Update queries for stage/pr_url |
| `tests/test_cascade.py` | NEW - tests for extraction |

---

## Conclusion

The extraction of cascade metadata is a clean architectural improvement that:
1. **Reduces coupling** between document storage and cascade processing
2. **Maintains compatibility** through a phased migration
3. **Enables future separation** without requiring it now
4. **Has minimal performance impact** for the cascade use case

The wild ideas explored (event sourcing, separate databases, graphs) are interesting but overkill for the current need. They serve as potential future directions if EMDX evolves to require them.

**Recommended approach**: Simple table extraction with phased migration.
