# Auto-Wikify Design

## Problem

As an emdx knowledge base grows, documents become isolated islands. A doc about
"auth module refactor" and a doc about "session handling bug" may be deeply
related, but nothing connects them unless the user manually remembers both exist.

Wikipedia solved this decades ago: every article title is a potential link target,
and editors (human or bot) annotate mentions. EMDX should do the same —
automatically, incrementally, and with multiple strategies.

## What Exists Today

EMDX already has substantial infrastructure for cross-linking:

| Component | Location | Status |
|-----------|----------|--------|
| `document_links` table | `database/document_links.py` | Ready |
| Bidirectional link queries | `database/document_links.py` | Ready |
| `method` field on links | migration 043 | Ready |
| Embedding service (MiniLM-L6-v2) | `services/embedding_service.py` | Ready |
| `auto_link_document()` | `services/link_service.py` | Ready |
| Batch link creation | `database/document_links.py` | Ready |
| Dedup checks (`link_exists`) | `database/document_links.py` | Ready |
| `--auto-link` flag on save | `commands/core.py` | Ready |
| Chunk-level embeddings | `services/embedding_service.py` | Ready |
| TF-IDF similarity | `services/similarity.py` | Available |

The existing `auto_link_document` finds semantically similar documents via cosine
similarity on embeddings and records bidirectional links. This is useful but it's
"related articles," not wikification.

## Key Distinction: Similarity vs. Wikification

**Similarity** (what exists): "Doc #87 is globally similar to doc #42"
— embedding cosine > threshold.

**Wikification** (what we're adding): "Doc #87's text *mentions* something that
doc #42 *is about*" — a concept in one doc maps to the identity of another.

Two docs about completely different topics can share a mention of "auth module."
Two very similar docs might never explicitly name each other's concepts. These are
complementary signals.

## Proposed Design: Three Layers

Each layer is independently useful. They compose through the existing
`document_links` table, differentiated by the `method` field.

### Layer 1: Title-Match Wikification

**Method:** `title_match`
**Cost:** Zero (no AI, no embeddings)
**Speed:** O(n * avg_title_length) per document, fast

Build an in-memory set of all document titles (normalized: lowercased, stripped of
punctuation). On save, scan the new document's content for substring matches
against known titles. Create bidirectional links.

This is the Wikipedia model — every article title is a potential wikilink target.

**Algorithm:**
1. Load all `(id, title)` pairs from documents table
2. Normalize titles: lowercase, strip leading/trailing punctuation
3. Filter out very short titles (< 4 chars) to avoid false positives
4. For each title, check if it appears as a word-boundary match in the new
   document's content
5. Create links with `method='title_match'`, score = 1.0 for exact match

**Edge cases:**
- A document shouldn't link to itself
- Very common titles ("Notes", "TODO") should be excluded or deprioritized
- Partial matches within longer words need word-boundary checks
- Already-linked pairs should be skipped (existing dedup handles this)

### Layer 2: Enhanced Semantic Similarity

**Method:** `semantic` (already `auto` in existing code)
**Cost:** Embedding computation (~80ms per doc)
**Speed:** O(n) cosine comparisons

This is the existing `auto_link_document` with enhancements:

1. **Chunk-level linking** — Instead of linking whole documents, identify *which
   section* of doc A relates to doc B. Store chunk IDs in link metadata.
2. **Auto-trigger on save** — Make `--auto-link` the default behavior (currently
   opt-in). Add `--no-auto-link` to suppress.
3. **Project scoping** — By default only match within the same project. Add
   `--cross-project` to match globally.

### Layer 3: Entity-Based Wikification

**Method:** `entity_match`
**Cost:** Moderate (NLP extraction or LLM call)
**Speed:** Depends on extraction method

Extract key entities/concepts from each document and store them. When a new
document is saved, match its entities against existing documents' entities.

**New table:**
```sql
CREATE TABLE document_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    entity TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- 'concept', 'proper_noun', 'tech_term'
    confidence REAL DEFAULT 1.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE INDEX idx_entities_document ON document_entities(document_id);
CREATE INDEX idx_entities_entity ON document_entities(entity);
```

**Extraction options (choose one or combine):**
- **TF-IDF noun phrases** — no AI cost, decent for technical terms
- **LLM extraction** — better quality, costs per call (fits with existing
  `auto_tagger.py` pattern)
- **Simple heuristic** — capitalize words, backtick-wrapped terms, header text

This catches "the auth module refactor broke session handling" linking to docs
about "auth module" AND "session handling" even if titles don't match exactly.

## CLI Interface

```bash
# Wikify a single document (runs all enabled layers)
emdx wikify 87

# Backfill the whole KB
emdx wikify --all

# Only title-matching (fast, no AI)
emdx wikify --all --mode titles

# Only semantic (requires embedding index)
emdx wikify --all --mode semantic

# Dry run — show what would be linked without creating links
emdx wikify --all --dry-run

# Show existing wiki links for a document
emdx show 87              # includes "See also:" section
emdx show 87 --json       # includes "wiki_links" array

# Agent-friendly context
emdx prime --json          # already includes links in doc metadata
```

### JSON output shape

```json
{
  "id": 87,
  "title": "Session Handling Bug",
  "wiki_links": [
    {"id": 42, "title": "Auth Module Refactor", "method": "title_match", "score": 1.0},
    {"id": 55, "title": "Auth Architecture", "method": "semantic", "score": 0.73}
  ]
}
```

## Implementation Plan

### Phase 1: Title-Match Wikification ✅
- ~~Add `wikify` command to CLI~~ → `emdx maintain wikify`
- ~~Implement `services/wikify_service.py`~~ with `title_match_wikify(doc_id)`
- ~~Wire into save command~~ (runs automatically on every save)
- ~~Add `--dry-run` flag~~
- ~~Tests for edge cases~~ (31 tests: short titles, self-links, word boundaries, etc.)

### Phase 2: Enhanced Semantic (improve existing) ✅
- ~~Make `--auto-link` default on save~~ (`--auto-link/--no-auto-link`, default on)
- ~~Add project scoping~~ (`--cross-project` flag, default: same project only)
- Surface links in `emdx show` output (already exists via `--links`)

### Phase 3: Entity Extraction (future)
- Add `document_entities` table via migration
- Implement extraction service
- Cross-reference on save

## Integration Points

| Event | Action |
|-------|--------|
| `emdx save` | Run title-match + semantic wikify on new doc |
| `emdx wikify --all` | Backfill all documents |
| `emdx show <id>` | Display linked documents |
| `emdx prime --json` | Include links in context |
| TUI browse | Show link count, navigate to linked docs |

## Design Principles

1. **Incremental** — Wikify on save, not in batch. Batch is for backfill only.
2. **Cheap by default** — Layer 1 (title match) costs nothing. Don't require
   embeddings for basic wikification.
3. **Composable** — Each layer writes to the same `document_links` table with
   different `method` values. Display code doesn't care how links were created.
4. **Idempotent** — Running wikify twice produces the same result (existing
   dedup handles this).
5. **Agent-friendly** — `--json` output includes links. `prime` includes links.
   Agents can use links to navigate the KB.
