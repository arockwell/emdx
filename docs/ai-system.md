# AI-Powered Knowledge Base

EMDX includes semantic search and Q&A capabilities using local embeddings and optional LLM integration.

## Overview

The AI system provides:
- **Semantic Search**: Find documents by meaning, not just keywords
- **Similar Documents**: Discover related content
- **Q&A**: Ask questions and get synthesized answers
- **Claude CLI Integration**: Use your Claude Max subscription for Q&A

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    emdx ai commands                         │
├─────────────────────────────────────────────────────────────┤
│  index    search    similar    ask    context    stats     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Services Layer                           │
├─────────────────────┬─────────────────────┬─────────────────┤
│  EmbeddingService   │ HybridSearchService │   AskService    │
│  - Index management │ - FTS5 + semantic   │ - Doc retrieval │
│  - Vector search    │ - Score merging     │ - Context build │
│  - Similarity calc  │ - Mode detection    │ - LLM integr.   │
├─────────────────────┴─────────────────────┴─────────────────┤
│  chunk_splitter - Splits docs into ~100-500 token chunks    │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                            │
├────────────────────┬────────────────────┬───────────────────┤
│ document_embeddings│  chunk_embeddings  │    documents      │
│ - document_id      │ - document_id      │ - id, title       │
│ - model_name       │ - chunk_index      │ - content         │
│ - embedding (BLOB) │ - heading_path     │ - project, tags   │
│ - dimension        │ - text, embedding  │ - FTS5 index      │
└────────────────────┴────────────────────┴───────────────────┘
```

## Getting Started

### 1. Build the Embedding Index

```bash
# Index all documents (one-time, ~1-2 minutes for 100+ docs)
emdx ai index

# Check status
emdx ai stats
```

Output:
```
╭─────────────────── AI Index ───────────────────╮
│ Embedding Index Statistics                     │
│                                                │
│ Documents:  126 / 127 indexed                  │
│ Coverage:   99.2%                              │
│ Model:      all-MiniLM-L6-v2                   │
│ Index size: 189.0 KB                           │
╰────────────────────────────────────────────────╯
```

### 2. Search Your Knowledge Base

```bash
# Semantic search
emdx ai search "authentication patterns"

# Find similar documents
emdx ai similar 42
```

### 3. Ask Questions

**Option A: Using Claude API** (requires `ANTHROPIC_API_KEY`):
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
emdx ai ask "How does the delegate system work?"
```

**Option B: Using Claude CLI** (uses Claude Max subscription):
```bash
emdx ai context "How does the delegate system work?" | claude
```

## Commands Reference

### `emdx ai index`

Build or update the embedding index. By default, indexes both document-level and chunk-level embeddings.

```bash
emdx ai index              # Index new documents and chunks
emdx ai index --force      # Reindex everything
emdx ai index --no-chunks  # Only index documents, skip chunk-level
emdx ai index --batch-size 100  # Process in larger batches
```

### `emdx ai search`

Semantic search across documents.

```bash
emdx ai search "query"                    # Basic search
emdx ai search "query" --limit 20         # More results
emdx ai search "query" --threshold 0.5    # Higher similarity required
emdx ai search "query" --project myapp    # Filter by project
```

### `emdx ai similar`

Find documents similar to a given document.

```bash
emdx ai similar 42           # Find docs similar to #42
emdx ai similar 42 --limit 10
```

### `emdx ai ask`

Q&A using Claude API.

```bash
emdx ai ask "What's our caching strategy?"
emdx ai ask "How did we solve AUTH-123?" --project myapp
emdx ai ask "recent changes" --keyword    # Force keyword search
emdx ai ask "question" --no-sources       # Hide source references
```

### `emdx ai context`

Retrieve context for piping to external tools.

```bash
emdx ai context "question" | claude
emdx ai context "topic" --limit 5 | claude "summarize"
emdx ai context "query" --no-question | claude "analyze"
emdx ai context "query" --keyword    # Force keyword search
```

### `emdx ai stats`

Show embedding index statistics.

```bash
emdx ai stats
```

### `emdx ai clear`

Clear all embeddings (requires reindexing).

```bash
emdx ai clear --yes
```

## How It Works

### Embedding Model

EMDX uses `all-MiniLM-L6-v2` from sentence-transformers:
- **Dimensions**: 384
- **Size**: ~90MB (downloaded on first use)
- **Speed**: ~100 docs/second on modern hardware
- **Quality**: Good balance of speed and accuracy
- **Cost**: Free (runs locally)

### Search Algorithm

EMDX uses **hybrid search** that combines keyword and semantic search:

1. **Keyword search** (FTS5): Fast, exact term matching
2. **Semantic search** (chunks): Conceptual similarity via embeddings
3. **Score merging**: Results are combined with weighted scoring:
   - Keyword score weight: **0.4**
   - Semantic score weight: **0.6**
   - Hybrid boost: **+0.15** for documents found by both methods
4. Results are deduplicated and ranked by combined score

The system auto-detects the best mode based on available indexes.

### Chunk-Level Search

Documents are split into **~100-500 token chunks** for more precise semantic search:

- **Splitting strategy**: Chunks are created by markdown headings (##, ###, etc.)
- **Large sections**: Split further by paragraph breaks, then sentences
- **Small sections**: Merged with adjacent content to meet minimum size
- **Heading paths**: Each chunk preserves its location (e.g., "Methods > Data Collection")

Benefits of chunk-level indexing:
- **Precision**: Find the exact section that matches, not just "somewhere in this doc"
- **Context**: Heading paths tell you where the match is
- **Scale**: ~6x more entries than doc-level (chunks per document varies)

The chunk splitter (`emdx/utils/chunk_splitter.py`) handles the splitting logic.

### Fallback Behavior

If embeddings aren't available (not indexed yet), the system automatically falls back to keyword search using SQLite FTS5. This means search always works, even without running `emdx ai index`.

### Context Building

For Q&A commands, the system:
1. Retrieves top-N relevant documents
2. Truncates long documents (4000 chars max per doc)
3. Formats as context with document IDs and titles
4. Sends to Claude (API or CLI) for answering

## Integration Patterns

### With Claude Code

```bash
# Quick Q&A during development
emdx ai context "How does error handling work?" | claude

# Research before implementing
emdx ai search "authentication" --limit 5
# Then read the relevant docs
emdx view 123
```

### With Delegate

```bash
# Analyze documents found by semantic search
emdx ai search "tech debt" --limit 10
# Note the IDs, then delegate analysis
emdx delegate 5350 5351 5352
```

### Periodic Maintenance

```bash
# Reindex after adding many docs
emdx ai index

# Check coverage
emdx ai stats
```

## Troubleshooting

### "No documents indexed"

Run `emdx ai index` to build the embedding index.

### "sentence-transformers not installed"

```bash
poetry install  # In development
# or
pip install sentence-transformers
```

### Slow indexing

- First run downloads the model (~90MB)
- Subsequent runs are faster
- Use `--batch-size` to tune memory usage

### Search returns unexpected results

- Try adjusting `--threshold` (lower = more results, higher = stricter)
- Use `--keyword` flag to compare with keyword search
- Semantic search works best with natural language queries

### Claude API errors

- Check `ANTHROPIC_API_KEY` is set
- Use `emdx ai context | claude` to avoid API costs

## Performance Considerations

| Operation | Time | Notes |
|-----------|------|-------|
| Initial index | 1-2 min | Downloads model on first run |
| Incremental index | Seconds | Only indexes new docs |
| Search | <100ms | Cosine similarity is fast |
| Q&A (API) | 2-5s | Depends on context size |
| Q&A (CLI) | 2-5s | Same, uses Claude Max |

## Storage

Embeddings are stored in SQLite across two tables:

**Document embeddings** (`document_embeddings`):
- ~1.5KB per document (384 floats × 4 bytes)
- 100 docs ≈ 150KB
- 1000 docs ≈ 1.5MB

**Chunk embeddings** (`chunk_embeddings`):
- ~6x more entries than document-level (varies by doc length)
- Each chunk stores: heading_path, text, embedding
- 100 docs with ~5 chunks each ≈ 900KB
- 1000 docs ≈ 9MB

The indexes are stored in your EMDX database alongside documents. Use `emdx ai stats` to see current index sizes.
