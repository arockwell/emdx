# Data Layer Refactoring Plan

## Overview

This document outlines a plan to simplify and consolidate the EMDX data layer, which currently suffers from multiple code paths, duplicated logic, and inconsistent behavior that has led to bugs.

## Problem Statement

### Current Architecture (Problematic)

```
                    Commands/UI
                    /    |    \
                   /     |     \
    +--------------+   +------------+   +-------------+
    | database.db  |   | database/  |   | models/     |
    | (SQLiteDB)   |   | documents  |   | documents   |
    +--------------+   +------------+   +-------------+
          |                  |               |
          |  (duplicated)    |  (canonical)  |  (wrapper)
          v                  v               v
    +------------------------------------------------+
    |                   SQLite                        |
    +------------------------------------------------+
```

Commands can import from **three different paths** to perform the same operation:

```python
# Example from commands/core.py - all three paths used!
from emdx.database import db                          # Path 1: SQLiteDatabase instance
from emdx.database.documents import (                 # Path 2: Direct module functions
    archive_descendants, archive_document, ...
)
from emdx.models.documents import (                   # Path 3: Model layer (delegates)
    delete_document, get_document, ...
)
```

### Identified Issues

#### 1. Triple-Path Data Access Anti-Pattern

| Operation | Path 1 (SQLiteDB) | Path 2 (DB Module) | Path 3 (Models) |
|-----------|-------------------|-------------------|-----------------|
| `save_document` | Full impl in class | Direct `db_connection` | Delegates to db |
| `get_document` | Full impl with test override | Full impl | Delegates to db |
| `list_documents` | Basic impl | Enhanced with filters | Delegates to db |
| `search_documents` | Different impl, missing features | Full FTS5 impl | Delegates to db |

**Impact**: Bug fixes in one path don't propagate to others. Developers don't know which path is authoritative.

#### 2. Silent Feature Gaps (Active Bugs)

**Date filters silently ignored** (`database/__init__.py:380-402`):
```python
def search_documents(self, query, project=None, limit=10, fuzzy=False,
                    created_after=None, created_before=None,  # IGNORED!
                    modified_after=None, modified_before=None):  # IGNORED!
    if query == "*":
        # Wildcard case - NO date filtering applied
        cursor = conn.execute("""
            SELECT id, title, project, created_at, NULL as snippet, NULL as rank
            FROM documents WHERE is_deleted = FALSE ...
        """)
```

**Inconsistent deleted document check**:
- `database/search.py:43`: `d.deleted_at IS NULL`
- `database/__init__.py:381`: `is_deleted = FALSE`

These should be equivalent but represent fragile coupling to implementation details.

#### 3. Duplicate Logic with Different Behavior

Tag creation in two places with **different behavior**:

**Location 1** (`models/tags.py:11-23`):
```python
def get_or_create_tag(conn, tag_name):
    cursor.execute("INSERT INTO tags (name) VALUES (?)", (tag_name,))
    # Relies on schema default for usage_count
```

**Location 2** (`database/__init__.py:116-127`):
```python
cursor = conn.execute(
    "INSERT INTO tags (name, usage_count) VALUES (?, 0)",  # Explicit 0
    (tag_name,),
)
```

#### 4. Inconsistent Return Types

- `database/documents.py` parses datetimes into Python `datetime` objects
- `database/__init__.py` returns raw strings

Callers receive different types depending on which code path they use.

#### 5. UI Layer Bypasses Models

`ui/file_list.py:236-286` reaches directly into database:
```python
def _get_emdx_document_titles(self) -> set:
    with db.get_connection() as conn:  # DIRECT CONNECTION ACCESS
        cursor = conn.execute("SELECT title FROM documents WHERE is_deleted = 0")
```

Schema changes require hunting through UI code.

#### 6. SQLiteDatabase Dual-Mode Complexity

The wrapper class has complex conditional logic for test isolation:
```python
if tags and not self._uses_custom_path:
    from emdx.models.tags import add_tags_to_document  # Production path
    add_tags_to_document(doc_id, tags)
elif tags and self._uses_custom_path:
    # Test path - DUPLICATES all tag logic inline
    for tag_name in tags:
        ...  # 20+ lines of duplicated SQL
```

---

## Target Architecture

```
                    Commands/UI
                         |
                         v
    +-------------------------------------------+
    | models/*.py  (Business Logic Layer)       |
    | - Single import point for all operations  |
    | - Domain validation                       |
    | - Business rules                          |
    +-------------------------------------------+
                         |
                         v
    +-------------------------------------------+
    | database/*.py (Data Access Layer)         |
    | - Authoritative SQL implementations       |
    | - Datetime parsing at boundary            |
    | - FTS5 complexity hidden here             |
    +-------------------------------------------+
                         |
                         v
    +-------------------------------------------+
    | SQLiteDatabase (Test Isolation Facade)    |
    | - Thin delegation to module functions     |
    | - Minimal test fixture support            |
    +-------------------------------------------+
```

**Key Principles**:
1. Commands/UI import **only** from `models/*`
2. Models delegate to `database/*` module functions
3. `SQLiteDatabase` becomes a thin facade, not a parallel implementation
4. FTS complexity stays in `database/search.py`, hidden behind clean interface

---

## Implementation Plan

### Phase 1: Fix Active Bugs (Low Risk)

**Scope**: 3 files, ~50 lines
**Goal**: Fix bugs without changing architecture

#### 1.1 Fix Silent Date Filter Ignoring

**File**: `emdx/database/__init__.py`

The wildcard query path (lines 380-402) accepts date filter parameters but ignores them. Apply the same date filtering logic used in the FTS path.

**Before**:
```python
if query == "*":
    cursor = conn.execute("""
        SELECT id, title, project, created_at, NULL as snippet, NULL as rank
        FROM documents WHERE is_deleted = FALSE
        ORDER BY created_at DESC LIMIT ?
    """, (limit,))
```

**After**:
```python
if query == "*":
    sql = """
        SELECT id, title, project, created_at, NULL as snippet, NULL as rank
        FROM documents WHERE is_deleted = FALSE
    """
    params = []
    if created_after:
        sql += " AND created_at >= ?"
        params.append(created_after)
    if created_before:
        sql += " AND created_at <= ?"
        params.append(created_before)
    # ... similar for modified_after, modified_before
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    cursor = conn.execute(sql, params)
```

#### 1.2 Fix Inconsistent Deleted Document Check

**File**: `emdx/database/search.py`

Change line 43 from:
```python
WHERE documents_fts MATCH ? AND d.deleted_at IS NULL
```

To:
```python
WHERE documents_fts MATCH ? AND d.is_deleted = FALSE
```

This aligns with all other queries in the codebase.

#### 1.3 Add Missing `include_archived` Parameter to Search

**File**: `emdx/database/search.py`

Add parameter to function signature and apply filter:

```python
def search_documents(
    query: str,
    project: Optional[str] = None,
    limit: int = 10,
    created_after: Optional[str] = None,
    created_before: Optional[str] = None,
    modified_after: Optional[str] = None,
    modified_before: Optional[str] = None,
    include_archived: bool = False,  # NEW
) -> list[dict[str, Any]]:
    ...
    if not include_archived:
        conditions.append("d.archived_at IS NULL")
```

**Testing**: Add regression tests for each bug before fixing.

---

### Phase 2: Fix Datetime Inconsistency (Low Risk)

**Scope**: 1 file, ~30 lines
**Goal**: Consistent return types from SQLiteDatabase

#### 2.1 Add Datetime Parsing to SQLiteDatabase Methods

**File**: `emdx/database/__init__.py`

Import the parsing helper:
```python
from emdx.database.documents import _parse_doc_datetimes
```

Apply to all document-returning methods:
- `get_document()` - parse `created_at`, `updated_at`, `accessed_at`, `archived_at`
- `list_documents()` - parse `created_at`, `accessed_at`, `archived_at`
- `get_recent_documents()` - parse `created_at`, `accessed_at`
- `search_documents()` - parse `created_at`
- `list_deleted_documents()` - parse `created_at`, `deleted_at`

**Testing**: Verify return types in existing tests.

---

### Phase 3: Convert SQLiteDatabase to Delegation (Medium Risk)

**Scope**: 1 file, ~300 lines (mostly deletions)
**Goal**: Eliminate duplicate implementations

#### 3.1 Replace Inline SQL with Delegation

**File**: `emdx/database/__init__.py`

For each method in SQLiteDatabase, replace inline SQL with delegation to module functions.

**Example - save_document**:

**Before** (~40 lines of SQL):
```python
def save_document(self, title, content, project=None, tags=None, parent_id=None):
    with self._get_connection() as conn:
        cursor = conn.execute("""
            INSERT INTO documents (title, content, project, parent_id, ...)
            VALUES (?, ?, ?, ?, ...)
        """, (...))
        doc_id = cursor.lastrowid
        # ... 20+ lines of tag handling
        return doc_id
```

**After** (~5 lines):
```python
def save_document(self, title, content, project=None, tags=None, parent_id=None):
    if self._uses_global_connection:
        from emdx.database import documents
        return documents.save_document(title, content, project, tags, parent_id)
    else:
        # Minimal test isolation implementation
        return self._save_document_isolated(title, content, project, tags, parent_id)
```

#### 3.2 Consolidate Test Isolation Path

For test databases (custom `db_path`), keep a minimal implementation that:
- Uses the isolated connection
- Handles basic CRUD without duplicating complex logic
- Delegates complex operations (like tag management) where possible

**Methods to convert**:
| Method | Current Lines | After Delegation |
|--------|---------------|------------------|
| `save_document` | ~45 | ~10 |
| `get_document` | ~35 | ~8 |
| `update_document` | ~30 | ~8 |
| `delete_document` | ~15 | ~5 |
| `list_documents` | ~25 | ~5 |
| `search_documents` | ~55 | ~10 |
| `get_recent_documents` | ~20 | ~5 |

**Testing**: Full test suite must pass. Compare query results before/after.

---

### Phase 4: Consolidate Command Imports (Low Risk)

**Scope**: 12+ files, ~150 lines
**Goal**: Commands import only from `models/*`

#### 4.1 Add Missing Exports to models/documents.py

**File**: `emdx/models/documents.py`

Add delegation functions for everything commands currently import from `database.documents`:

```python
from emdx.database import documents as doc_db

def archive_document(doc_id: int) -> bool:
    """Archive a document."""
    return doc_db.archive_document(doc_id)

def unarchive_document(doc_id: int) -> bool:
    """Unarchive a document."""
    return doc_db.unarchive_document(doc_id)

def archive_descendants(doc_id: int) -> int:
    """Archive all descendants of a document."""
    return doc_db.archive_descendants(doc_id)

def find_supersede_candidate(title: str) -> Optional[dict]:
    """Find a document that could be superseded by a new one with this title."""
    return doc_db.find_supersede_candidate(title)

def set_parent(doc_id: int, parent_id: Optional[int]) -> bool:
    """Set or clear the parent of a document."""
    return doc_db.set_parent(doc_id, parent_id)

def count_documents(project: Optional[str] = None, include_archived: bool = False) -> int:
    """Count documents, optionally filtered by project."""
    return doc_db.count_documents(project, include_archived)

def get_children_count(doc_id: int) -> int:
    """Get the number of children for a document."""
    return doc_db.get_children_count(doc_id)
```

#### 4.2 Update commands/core.py

**File**: `emdx/commands/core.py`

**Before**:
```python
from emdx.database import db
from emdx.database.documents import (
    archive_descendants,
    archive_document,
    find_supersede_candidate,
    set_parent,
    unarchive_document,
)
from emdx.models.documents import (
    delete_document,
    get_document,
    ...
)
```

**After**:
```python
from emdx.database import db  # Only for ensure_schema
from emdx.models.documents import (
    archive_descendants,
    archive_document,
    delete_document,
    find_supersede_candidate,
    get_document,
    set_parent,
    unarchive_document,
    ...
)
```

#### 4.3 Update All Command Files

Apply same pattern to:
- `emdx/commands/tags.py`
- `emdx/commands/browse.py`
- `emdx/commands/gist.py`
- `emdx/commands/export.py`
- `emdx/commands/groups.py`
- `emdx/commands/export_profiles.py`
- `emdx/commands/gdoc.py`
- `emdx/commands/links.py`
- `emdx/commands/projects.py`
- `emdx/commands/tasks.py`
- `emdx/commands/workflow.py`

**Testing**: Verify each command works via CLI smoke tests.

---

### Phase 5: Consolidate UI Imports (Low Risk)

**Scope**: ~10 files, ~100 lines
**Goal**: UI imports only from `models/*`

#### 5.1 Add UI-Specific Model Functions

**File**: `emdx/models/documents.py`

```python
def get_all_document_titles(include_deleted: bool = False) -> set[str]:
    """Get all document titles for existence checking."""
    return doc_db.get_all_document_titles(include_deleted)

def document_exists_with_title(title: str) -> bool:
    """Check if a document exists with the given title."""
    return doc_db.document_exists_with_title(title)
```

#### 5.2 Update ui/file_list.py

**Before**:
```python
def _get_emdx_document_titles(self) -> set:
    with db.get_connection() as conn:
        cursor = conn.execute(
            "SELECT title FROM documents WHERE is_deleted = 0"
        )
        return {row[0] for row in cursor.fetchall()}
```

**After**:
```python
def _get_emdx_document_titles(self) -> set:
    from emdx.models.documents import get_all_document_titles
    return get_all_document_titles()
```

#### 5.3 Update All UI Files

Apply same pattern to:
- `emdx/ui/file_list.py`
- `emdx/ui/nvim_wrapper.py`
- `emdx/ui/file_browser/actions.py`
- `emdx/ui/activity/activity_view.py`
- `emdx/ui/activity/activity_items.py`
- `emdx/ui/activity/group_picker.py`
- `emdx/ui/presenters/document_browser_presenter.py`
- `emdx/ui/presenters/tag_browser_presenter.py`

**Testing**: TUI smoke tests for each affected screen.

---

### Phase 6: Simplify SQLiteDatabase (Low Risk)

**Scope**: 2 files, ~200 lines deleted
**Goal**: Remove now-unused duplicate code

#### 6.1 Remove Redundant Methods

**File**: `emdx/database/__init__.py`

After Phases 3-5, SQLiteDatabase only needs:
- `__init__()` - connection setup
- `ensure_schema()` - migration runner
- `get_connection()` - for any remaining direct access
- Simple delegation methods

Delete:
- All inline SQL implementations (now delegated)
- Complex search logic (use `database.search`)
- Complex tag logic (use `models.tags`)
- Duplicate datetime parsing

#### 6.2 Update Test Fixtures

**File**: `tests/conftest.py` (or equivalent)

Ensure test fixtures work with simplified SQLiteDatabase. May need to:
- Update fixture creation patterns
- Verify test isolation still works
- Document the test database pattern

**Testing**: Full test suite regression.

---

## Risk Mitigation

### Testing Strategy

| Phase | Test Approach |
|-------|---------------|
| 1 | Add regression tests for each bug BEFORE fixing |
| 2 | Verify datetime types in existing tests |
| 3 | Compare query results before/after; full test suite |
| 4 | CLI smoke test for each command |
| 5 | TUI smoke test for each screen |
| 6 | Full regression test |

### Rollback Points

- Each phase is independently deployable
- Create git tag at each phase completion
- Phases can be reverted independently if issues arise

### Incremental Deployment

Each phase leaves the codebase fully functional:
- Phase 1: Bugs fixed, same architecture
- Phase 2: Better return types, same architecture
- Phase 3: SQLiteDatabase simplified, same external interface
- Phase 4: Commands use single path, same behavior
- Phase 5: UI uses single path, same behavior
- Phase 6: Dead code removed, cleaner codebase

---

## Summary

| Phase | Files | Lines Changed | Risk | Key Outcome |
|-------|-------|---------------|------|-------------|
| 1 | 3 | ~50 | Low | Fix silent bugs |
| 2 | 1 | ~30 | Low | Consistent datetime types |
| 3 | 1 | ~300 | Medium | Eliminate duplicate SQL |
| 4 | 12 | ~150 | Low | Single import path for commands |
| 5 | 10 | ~100 | Low | Single import path for UI |
| 6 | 2 | ~200 (deleted) | Low | Remove dead code |
| **Total** | **~25** | **~830** | **Medium** | **Clean, maintainable data layer** |

---

## Success Criteria

After completing all phases:

1. **Single Code Path**: All database operations have exactly one implementation
2. **Clear Layering**: Commands/UI -> Models -> Database -> SQLite
3. **Consistent Types**: All document queries return parsed datetime objects
4. **No Silent Failures**: Date filters, archive filters work everywhere
5. **Test Isolation**: Tests still run independently with isolated databases
6. **FTS Contained**: FTS5 complexity hidden in `database/search.py`

---

## Appendix: Files to Modify

### Phase 1
- `emdx/database/__init__.py` - Fix date filter bug
- `emdx/database/search.py` - Fix deleted check, add include_archived

### Phase 2
- `emdx/database/__init__.py` - Add datetime parsing

### Phase 3
- `emdx/database/__init__.py` - Convert to delegation

### Phase 4
- `emdx/models/documents.py` - Add missing exports
- `emdx/commands/core.py`
- `emdx/commands/tags.py`
- `emdx/commands/browse.py`
- `emdx/commands/gist.py`
- `emdx/commands/export.py`
- `emdx/commands/groups.py`
- `emdx/commands/export_profiles.py`
- `emdx/commands/gdoc.py`
- `emdx/commands/links.py`
- `emdx/commands/projects.py`
- `emdx/commands/tasks.py`

### Phase 5
- `emdx/models/documents.py` - Add UI helper functions
- `emdx/ui/file_list.py`
- `emdx/ui/nvim_wrapper.py`
- `emdx/ui/file_browser/actions.py`
- `emdx/ui/activity/activity_view.py`
- `emdx/ui/activity/activity_items.py`
- `emdx/ui/activity/group_picker.py`
- `emdx/ui/presenters/document_browser_presenter.py`
- `emdx/ui/presenters/tag_browser_presenter.py`

### Phase 6
- `emdx/database/__init__.py` - Remove dead code
- `tests/conftest.py` - Update fixtures if needed
