# EMDX CLI API Reference

## 📋 **Command Overview**

EMDX provides a comprehensive CLI for knowledge base management and system maintenance.

```bash
emdx [OPTIONS] COMMAND [ARGS]...
```

## 📚 **Document Management**

### **emdx save**
Save content to the knowledge base. Content sources in priority order: stdin > `--file` > positional argument.

```bash
# Save inline content (positional arg is always content, never a file path)
emdx save "Quick note about the auth module"

# Save from file (explicit --file flag)
emdx save --file document.md
emdx save --file document.md --title "Custom Title"

# Save from stdin
echo "Content here" | emdx save --title "My Note"

# Save with tags
echo "Gameplan content" | emdx save --title "Auth Gameplan" --tags "gameplan,active"

# Save from command output
ls -la | emdx save --title "Directory Listing"

# Save and auto-link to related documents
emdx save --file notes.md --auto-link

```

**Options:**
- `--file, -f TEXT` - Read content from a file path
- `--title, -t TEXT` - Custom title (auto-detected from filename if not provided)
- `--tags TEXT` - Comma-separated tags
- `--project, -p TEXT` - Override project detection
- `--auto-link/--no-auto-link` - Auto-link to semantically similar documents (default: auto-link)
- `--cross-project` - Allow auto-links across projects
- `--auto-tag` - Automatically apply suggested tags
- `--suggest-tags` - Show tag suggestions after saving
- `--supersede` - Auto-link to existing doc with same title
- `--task INTEGER` - Link saved document to a task as its output
- `--done` - Also mark the linked task as done (requires `--task`)

### **emdx find**
Search documents with hybrid (default when index exists), keyword, or semantic search. Also supports listing, similar-doc lookup, RAG Q&A, and context retrieval.

```bash
# Full-text search (keyword mode)
emdx find "docker compose"
emdx find "kubernetes deployment"

# Tag-based search
emdx find --tags "gameplan,active"      # Active gameplans
emdx find --tags "bug,urgent"           # Urgent bugs
emdx find --tags "feature,done"         # Completed features

# Combined search
emdx find "authentication" --tags "gameplan"

# Project-scoped search
emdx find "config" --project "emdx"

# Hybrid search (combines keyword + semantic)
emdx find "how to handle errors" --mode hybrid

# Semantic search (meaning-based, requires embeddings)
emdx find "authentication patterns" --mode semantic

# Force keyword-only search
emdx find "docker" --mode keyword

# Show matching chunk text instead of document snippets
emdx find "error handling" --mode hybrid --extract

# Exclude documents with specific tags
emdx find "api" --no-tags "archived,draft"

# Output as JSON
emdx find "config" --json

# Show snippet previews (default behavior, explicit)
emdx find "database" --snippets

# List all documents (replaces old `emdx list` command)
emdx find --all
emdx find --all --project "emdx"

# Show recently accessed documents (replaces old `emdx recent` command)
emdx find --recent 10

# Find similar documents (replaces old `emdx ai similar` command)
emdx find --similar 42

# RAG Q&A: retrieve context + LLM answer (replaces old `emdx ai ask`)
emdx find --ask "What's our caching strategy?"

# Context retrieval for piping to claude (replaces old `emdx ai context`)
emdx find --context "How does auth work?" | claude

# Deliberative search — build a position paper
emdx find --think "Should we use JWT or sessions?"

# Devil's advocate — challenge a position
emdx find --think --challenge "JWT is better than sessions"

# Socratic debugger — diagnostic questions from bug history
emdx find --debug "auth token expiry"

# Inline citations — chunk-level [#ID] references
emdx find --ask --cite "What's our caching strategy?"

# Serendipity — surface surprising related documents
emdx find --wander "authentication"

# Show only wiki articles
emdx find "authentication" --wiki

# Show all document types (user docs + wiki articles)
emdx find "auth" --all-types
```

**Options:**
- `--tags, -t TEXT` - Search by tags
- `--any-tags` - Match ANY tag instead of ALL tags
- `--no-tags TEXT` - Exclude documents with specified tags (comma-separated)
- `--project, -p TEXT` - Limit search to specific project
- `--limit, -n INTEGER` - Maximum results to return (default: 10)
- `--mode, -m [keyword|semantic|hybrid]` - Search mode (hybrid default when index exists)
- `--extract, -e` - Show matching chunk text instead of document snippets
- `--snippets, -s` - Show snippet previews in results
- `--fuzzy, -f` - Use fuzzy search
- `--ids-only` - Output only document IDs (for piping)
- `--created-after TEXT` - Filter by creation date (YYYY-MM-DD)
- `--created-before TEXT` - Filter by creation date (YYYY-MM-DD)
- `--modified-after TEXT` - Filter by modification date (YYYY-MM-DD)
- `--modified-before TEXT` - Filter by modification date (YYYY-MM-DD)
- `--json, -j` - Output results as JSON
- `--all, -a` - List all documents (no search query needed)
- `--recent INTEGER` - Show N most recently accessed documents
- `--similar INTEGER` - Find documents similar to this doc ID
- `--ask` - Answer the query using RAG (retrieves context + LLM)
- `--think` - Deliberative search: build a position paper with arguments for/against
- `--challenge` - Devil's advocate: find evidence AGAINST the queried position (use with `--think`)
- `--debug` - Socratic debugger: diagnostic questions from your bug history
- `--cite` - Add inline `[#ID]` citations using chunk-level retrieval
- `--wander` - Serendipity mode: surface surprising but related documents
- `--context` - Output retrieved context as plain text (for piping to claude)
- `--wiki` - Show only wiki articles (`doc_type='wiki'`)
- `--all-types` - Show all document types (user, wiki, etc.)

### **emdx view**
View document content.

```bash
# View by ID
emdx view 42

# View with rich formatting (colors, panel header)
emdx view 42 --rich

# View raw content (no formatting)
emdx view 42 --raw

# Output as JSON
emdx view 42 --json

# Disable pager (for piping)
emdx view 42 --no-pager

# Hide document header
emdx view 42 --no-header

# Show document's link graph (replaces old `emdx ai links`)
emdx view 42 --links

# Adversarial review — check for staleness, contradictions, missing context
emdx view 42 --review
```

### **emdx edit**
Edit document in your default editor.

```bash
# Edit by ID
emdx edit 42

# Edit with specific editor
EDITOR=vim emdx edit 42
```

### **emdx delete**
Soft delete documents (moves to trash).

```bash
# Delete by ID
emdx delete 42

# Delete multiple documents
emdx delete 42 43 44
```

### **emdx history**
Show version history for a document. Every edit creates a version snapshot with SHA-256 hashes and character deltas.

```bash
# Show version history
emdx history 42

# JSON output
emdx history 42 --json
```

**Options:**
- `--json, -j` - Output as JSON

### **emdx diff**
Show diff between current content and a previous version.

```bash
# Diff against the most recent version
emdx diff 42

# Diff against a specific version
emdx diff 42 3

# Plain output (no color)
emdx diff 42 --no-color
```

**Arguments:**
- `DOC_ID` - Document ID (required)
- `VERSION` - Version to compare against (optional, defaults to most recent)

**Options:**
- `--no-color` - Disable colored output

## 🗄️ **Database Management**

### **emdx db**
Database path management and dev/prod isolation.

```bash
# Show which database is active and why
emdx db status

# Print just the active database path (for scripts)
emdx db path

# Copy production database to dev database
emdx db copy-from-prod
```

**Subcommands:**

| Command | Description |
|---------|-------------|
| `status` | Show active DB path and reason (env var, dev checkout, or production) |
| `path` | Print just the path (machine-friendly, for scripts) |
| `copy-from-prod` | Copy production DB to dev DB for local development |

## 🏷️ **Tag Management**

### **emdx tag add**
Add tags to a document.

```bash
# Add tags
emdx tag add 42 gameplan active urgent

# Add tags with auto-tagging
emdx tag add 42 --auto

# Show tag suggestions
emdx tag add 42 --suggest
```

### **emdx tag remove**
Remove tags from documents.

```bash
# Remove specific tags
emdx tag remove 42 urgent active

# Remove multiple tags
emdx tag remove 42 old-tag another-tag
```

### **emdx tag list**
List all tags with usage statistics.

```bash
# Show all tags with counts
emdx tag list

# Sort by name
emdx tag list --sort name
```

### **emdx tag rename**
Rename tags globally across all documents.

```bash
# Rename a tag across all documents
emdx tag rename "old-tag" "gameplan" --force

# Standardize tag names
emdx tag rename "todo" "active" --force
```

### **emdx tag merge**
Merge multiple tags into a single target tag.

```bash
# Merge several tags into one
emdx tag merge "old-tag1" "old-tag2" --into "new-tag" --force

# Skip confirmation prompt
emdx tag merge "todo" "task" --into "active" --force
```

**Options:**
- `--into, -i TEXT` - Target tag to merge into (required)
- `--force, -f` - Skip confirmation

### **emdx tag batch**
Batch auto-tag multiple documents using content analysis.

```bash
# Dry run: preview what would be tagged (default)
emdx tag batch

# Actually apply auto-tags
emdx tag batch --execute

# Only process untagged documents (default)
emdx tag batch --untagged

# Process all documents including already-tagged
emdx tag batch --all

# Filter by project
emdx tag batch --project myapp --execute

# Custom confidence threshold and max tags
emdx tag batch --confidence 0.8 --max-tags 2 --execute

# Limit number of documents to process
emdx tag batch --limit 50 --execute
```

**Options:**
- `--untagged/--all` - Only process untagged documents (default: untagged only)
- `--project, -p TEXT` - Filter by project
- `--confidence, -c FLOAT` - Minimum confidence threshold (default: 0.7)
- `--max-tags, -m INTEGER` - Maximum tags per document (default: 3)
- `--dry-run/--execute` - Preview or execute tagging (default: dry run)
- `--limit, -l INTEGER` - Maximum documents to process

## 🧹 **Maintenance Commands**

### **emdx maintain**
System maintenance, cleanup, embedding index, and document linking.

#### **emdx maintain cleanup**
Clean up old worktree branches and system resources.

```bash
# Show what cleanup would do (dry run)
emdx maintain cleanup --all

# Actually perform cleanup
emdx maintain cleanup --all --execute

# Clean old worktree branches only
emdx maintain cleanup --branches --execute

# Force delete unmerged branches too
emdx maintain cleanup --branches --force --execute

# Custom age threshold for branches (default: 7 days)
emdx maintain cleanup --branches --age 14 --execute
```

**Options:**
- `--branches, -b` - Clean up old worktree branches
- `--all, -a` - Clean up everything
- `--force, -f` - Force delete unmerged branches
- `--execute / --dry-run` - Execute actions (default: dry run)
- `--age INTEGER` - Only clean branches older than N days (default: 7)

#### **emdx maintain backup**
Create, list, or restore knowledge base backups. Uses SQLite's backup API for atomic, WAL-safe copies with optional gzip compression and logarithmic retention (~19 backups covering 2 years).

```bash
# Create compressed backup (default)
emdx maintain backup

# Create uncompressed backup
emdx maintain backup --no-compress

# List existing backups
emdx maintain backup --list

# Restore from a backup
emdx maintain backup --restore emdx-backup-2026-02-28_143022.db.gz

# Silent mode (for hooks)
emdx maintain backup --quiet

# JSON output
emdx maintain backup --json
```

**Options:**
- `--list, -l` - List existing backups
- `--restore, -r TEXT` - Restore from a backup file (filename or full path)
- `--no-compress` - Skip gzip compression
- `--no-retention` - Disable automatic pruning (keep all backups)
- `--quiet, -q` - Suppress output (for hook use)
- `--json` - Structured JSON output

#### **emdx maintain drift**
Detect abandoned or forgotten work in your knowledge base. Analyzes task and epic timestamps to surface stale epics, orphaned active tasks, and documents linked to stale work.

```bash
# Show stale work items (default: 30 day threshold)
emdx maintain drift

# Custom staleness threshold
emdx maintain drift --days 14

# JSON output
emdx maintain drift --json
```

**Options:**
- `--days, -d INTEGER` - Staleness threshold in days (default: 30)
- `--json` - Output as JSON

#### **emdx maintain code-drift**
Detect stale code references in knowledge base documents. Scans for backtick-wrapped identifiers (function names, class names, file paths) and cross-references them against the codebase to find references that no longer exist.

```bash
# Check all documents for stale code references
emdx maintain code-drift

# Scope to a specific project
emdx maintain code-drift --project emdx

# Show suggested replacements
emdx maintain code-drift --fix

# Limit documents checked
emdx maintain code-drift --limit 50

# JSON output
emdx maintain code-drift --json
```

**Options:**
- `--project, -p TEXT` - Scope to a specific project's documents
- `--limit, -l INTEGER` - Maximum number of documents to check
- `--fix` - Show suggested replacements when available
- `--json, -j` - Output as JSON

#### **emdx maintain contradictions**
Detect conflicting information across documents using a 3-stage funnel: embedding similarity for candidate pairs, NLI model (or heuristic fallback) for contradiction screening, and excerpt reporting with confidence levels.

```bash
# Find contradictions across the KB
emdx maintain contradictions

# Scope to a project
emdx maintain contradictions --project emdx

# Adjust similarity threshold for candidate pairs
emdx maintain contradictions --threshold 0.8

# Limit number of pairs to check
emdx maintain contradictions --limit 50

# JSON output
emdx maintain contradictions --json
```

**Options:**
- `--limit, -n INTEGER` - Max pairs to check (default: 100)
- `--project, -p TEXT` - Scope to project
- `--threshold FLOAT` - Similarity threshold for candidate pairs (default: 0.7)
- `--json` - Output as JSON

#### **emdx maintain wikify**
Create title-match links between documents (auto-wikification). Scans document content for mentions of other documents' titles and creates links. No AI or embeddings required.

```bash
# Wikify a single document
emdx maintain wikify 42

# Backfill all documents
emdx maintain wikify --all

# Preview matches without creating links
emdx maintain wikify 42 --dry-run
emdx maintain wikify --all --dry-run
```

**Options:**
- `--all` - Wikify all documents
- `--dry-run` - Show matches without creating links

#### **emdx maintain entities**
Extract entities (key concepts, technical terms, proper nouns) from markdown structure and cross-reference them across documents to create links. No AI required.

```bash
# Extract entities + create links for one document
emdx maintain entities 42

# Backfill all documents
emdx maintain entities --all

# Extract only, no cross-linking
emdx maintain entities 42 --no-wikify

# Clean noisy entities and re-extract with current filters
emdx maintain entities --cleanup

# Clear entity-match links before regenerating
emdx maintain entities --all --rebuild
```

**Options:**
- `--all` - Extract entities for all documents
- `--wikify / --no-wikify` - Also create entity-match links (default: wikify)
- `--rebuild` - Clear entity-match links before regenerating
- `--cleanup` - Remove noisy entities and re-extract with current filters

#### **emdx maintain compact**
AI-powered document synthesis to reduce knowledge base sprawl (moved from top-level `compact`).

```bash
# Dry run: show clusters without synthesizing (no API calls)
emdx maintain compact --dry-run

# Automatically synthesize all discovered clusters
emdx maintain compact --auto

# Compact specific documents together
emdx maintain compact 42 43 44

# Filter to a specific topic
emdx maintain compact --topic "authentication"

# Adjust similarity threshold
emdx maintain compact --threshold 0.7

# Skip confirmation prompts
emdx maintain compact --yes
```

**Options:**
- `--dry-run, -n` - Show clusters without synthesizing
- `--auto` - Automatically synthesize all clusters
- `--threshold, -t FLOAT` - Similarity threshold (0.0-1.0, default: 0.5)
- `--topic TEXT` - Filter to documents matching this topic
- `--model, -m TEXT` - Model to use for synthesis
- `--yes, -y` - Skip confirmation prompts

#### **emdx maintain index**
Build and manage the embedding index (moved from `emdx ai index`).

```bash
# Build index for new documents only
emdx maintain index

# Force reindex everything
emdx maintain index --force

# Check index statistics
emdx maintain index --stats

# Clear all embeddings (requires reindexing)
emdx maintain index --clear
```

**Options:**
- `--force` - Reindex all documents
- `--batch-size INTEGER` - Batch size for indexing
- `--chunks` - Use chunk-level embeddings
- `--stats` - Show index statistics
- `--clear` - Clear all embeddings

#### **emdx maintain link**
Create semantic links between related documents (moved from `emdx ai link`).

```bash
# Create links for a specific document
emdx maintain link 42

# Backfill links for all indexed documents
emdx maintain link --all

# Adjust similarity threshold and max links
emdx maintain link 42 --threshold 0.6 --max 3
```

**Options:**
- `--all` - Backfill links for all indexed documents
- `--threshold, -t FLOAT` - Minimum similarity (0-1, default: 0.5)
- `--max, -m INTEGER` - Maximum links per document (default: 5)

#### **emdx maintain unlink**
Remove a link between two documents (moved from `emdx ai unlink`).

```bash
emdx maintain unlink 42 57
```

#### **emdx maintain wiki**
Alias for `emdx wiki` — kept for backward compatibility. See the [Wiki section](#-wiki-emdx-wiki) for full documentation.

**Subcommands:**

| Command | Description |
|---------|-------------|
| `setup` | Run the full wiki bootstrap sequence (index → entities → topics → auto-label) |
| `topics` | Discover topic clusters using Leiden community detection |
| `triage` | Bulk triage saved topics: skip low-coherence, auto-label via LLM |
| `progress` | Show wiki generation progress: topics generated vs pending, costs |
| `status` | Show wiki generation status and statistics |
| `generate` | Generate wiki articles from topic clusters |
| `entities` | Browse entity index pages |
| `list` | List generated wiki articles |
| `runs` | List recent wiki generation runs |
| `coverage` | Show which documents are NOT covered by any topic cluster |
| `diff` | Show unified diff between previous and current article content |
| `rate` | Rate a wiki article's quality (1-5 scale) |
| `export` | Export wiki articles as a MkDocs site |
| `rename` | Rename a wiki topic (label, slug, and associated document title) |
| `retitle` | Batch-update topic labels from article H1 headings |
| `skip` | Skip a topic during wiki generation |
| `unskip` | Reset a skipped topic back to active |
| `pin` | Pin a topic so it always regenerates during wiki generation |
| `unpin` | Reset a pinned topic back to active |
| `model` | Set or clear a per-topic model override for wiki generation |
| `prompt` | Set or clear an editorial prompt for a wiki topic |
| `merge` | Merge two wiki topics into one |
| `split` | Split a wiki topic by extracting docs that mention an entity |
| `sources` | List source documents for a wiki topic with weights and status |
| `weight` | Set relevance weight for a source document within a topic |
| `exclude` | Exclude a source document from a wiki topic's synthesis |
| `include` | Re-include a previously excluded source document in a topic |

```bash
# Full bootstrap: index → entities → topics → auto-label
emdx maintain wiki setup

# Discover topic clusters (defaults to heading + proper_noun entities)
emdx maintain wiki topics
emdx maintain wiki topics --save --auto-label    # Save with LLM-generated names
emdx maintain wiki topics -e heading -e concept  # Custom entity types
emdx maintain wiki topics --min-df 3             # Prune rare entities

# Bulk triage saved topics
emdx maintain wiki triage --skip-below 0.05              # Skip low coherence
emdx maintain wiki triage --auto-label                    # LLM-label all topics
emdx maintain wiki triage --skip-below 0.03 --auto-label  # Both
emdx maintain wiki triage --skip-below 0.05 --dry-run    # Preview only

# Show generation progress
emdx maintain wiki progress          # Rich output with progress bar
emdx maintain wiki progress --json   # Machine-readable

# Generate wiki articles
emdx maintain wiki generate                  # Sequential (default)
emdx maintain wiki generate -c 3             # 3 concurrent generations
emdx maintain wiki generate --all --dry-run  # Preview costs

# Export to MkDocs
emdx maintain wiki export ./wiki-site              # All articles
emdx maintain wiki export ./wiki-site --topic 42   # Single article
emdx maintain wiki export ./wiki-site --build      # Build static site
emdx maintain wiki export ./wiki-site --deploy     # Deploy to GitHub Pages

# Show wiki generation status
emdx maintain wiki status

# List generated wiki articles
emdx maintain wiki list

# Show which docs aren't covered by any topic
emdx maintain wiki coverage

# Show diff between previous and current article content
emdx maintain wiki diff

# Rate a wiki article (1-5 scale)
emdx maintain wiki rate

# Topic management
emdx maintain wiki rename    # Rename a topic
emdx maintain wiki retitle   # Batch-update labels from article H1s
emdx maintain wiki skip      # Skip topic during generation
emdx maintain wiki unskip    # Reset skipped topic
emdx maintain wiki pin       # Force regeneration
emdx maintain wiki unpin     # Reset pinned topic
emdx maintain wiki model     # Set per-topic model override
emdx maintain wiki prompt    # Set editorial prompt

# Topic splitting and merging
emdx maintain wiki merge     # Merge two topics into one
emdx maintain wiki split     # Split topic by entity

# Source document control
emdx maintain wiki sources   # List sources with weights
emdx maintain wiki weight    # Set source relevance weight
emdx maintain wiki exclude   # Exclude a source from synthesis
emdx maintain wiki include   # Re-include an excluded source

# Browse entity index pages
emdx maintain wiki entities

# List recent wiki generation runs
emdx maintain wiki runs
```

## 📖 **Wiki** (`emdx wiki`)

Auto-wiki generation from your knowledge base. Uses Leiden community detection for topic clustering and AI for article generation.

> **Note:** `emdx maintain wiki` still works as an alias for backward compatibility.

### **emdx wiki** (no subcommand)

Show a compact wiki overview: topic count, articles generated, stale count, cost, and recent articles.

```bash
emdx wiki
```

### **emdx wiki view**

View a wiki article by topic ID.

```bash
emdx wiki view 42            # View article for topic 42
emdx wiki view 42 --raw      # Raw markdown
emdx wiki view 42 --json     # JSON output
```

### **emdx wiki search**

Search wiki articles (wiki-only full-text search).

```bash
emdx wiki search "authentication"
emdx wiki search "API design" --snippets
emdx wiki search "caching" --json
```

### **emdx wiki setup / topics / triage / generate / ...**

All existing wiki subcommands are available at `emdx wiki <subcommand>`. See the full subcommand table below.

**Subcommands:**

| Command | Description |
|---------|-------------|
| `setup` | Run the full wiki bootstrap sequence (index → entities → topics → auto-label) |
| `topics` | Discover topic clusters using Leiden community detection |
| `triage` | Bulk triage saved topics: skip low-coherence, auto-label via LLM |
| `progress` | Show wiki generation progress: topics generated vs pending, costs |
| `status` | Show wiki generation status and statistics |
| `generate` | Generate wiki articles from topic clusters |
| `view` | View a wiki article by topic ID |
| `search` | Search wiki articles |
| `entities` | Browse entity index pages |
| `list` | List generated wiki articles |
| `runs` | List recent wiki generation runs |
| `coverage` | Show which documents are NOT covered by any topic cluster |
| `diff` | Show unified diff between previous and current article content |
| `rate` | Rate a wiki article's quality (1-5 scale) |
| `export` | Export wiki articles as a MkDocs site |
| `rename` | Rename a wiki topic (label, slug, and associated document title) |
| `retitle` | Batch-update topic labels from article H1 headings |
| `skip` | Skip a topic during wiki generation |
| `unskip` | Reset a skipped topic back to active |
| `pin` | Pin a topic so it always regenerates during wiki generation |
| `unpin` | Reset a pinned topic back to active |
| `model` | Set or clear a per-topic model override for wiki generation |
| `prompt` | Set or clear an editorial prompt for a wiki topic |
| `merge` | Merge two wiki topics into one |
| `split` | Split a wiki topic by extracting docs that mention an entity |
| `sources` | List source documents for a wiki topic with weights and status |
| `weight` | Set relevance weight for a source document within a topic |
| `exclude` | Exclude a source document from a wiki topic's synthesis |
| `include` | Re-include a previously excluded source document in a topic |

```bash
# Full bootstrap: index → entities → topics → auto-label
emdx wiki setup

# Discover topic clusters
emdx wiki topics --save --auto-label

# Generate wiki articles
emdx wiki generate                  # Sequential (default)
emdx wiki generate -c 3             # 3 concurrent generations

# Export to MkDocs
emdx wiki export ./wiki-site
emdx wiki export ./wiki-site --build
```

## 📊 **Information Commands**

### **emdx trash**
Manage deleted documents.

```bash
# Show deleted documents
emdx trash

# Restore document from trash
emdx trash restore 42

# Permanently delete all trash (careful!)
emdx trash purge --force
```

### **emdx status**
Knowledge base overview with optional health and narrative modes.

```bash
# Quick overview
emdx status

# Detailed statistics
emdx status --stats
emdx status --stats --detailed

# KB vitals dashboard (health metrics)
emdx status --vitals

# Reflective narrative summary
emdx status --mirror

# JSON output (works with all modes)
emdx status --json
```

**Options:**
- `--stats` - Show KB statistics
- `--detailed` - Include project breakdown (with `--stats`)
- `--vitals` - Show KB vitals dashboard
- `--mirror` - Reflective KB summary (narrative)
- `--json` - Output as JSON
- `--rich` - Enable colored Rich output

### **emdx prime**
Inject knowledge base context for Claude Code sessions. Shows ready tasks, in-progress work, recent documents, and git context.

```bash
# Full context injection
emdx prime

# Compact output (tasks + epics only, no git/docs)
emdx prime --brief

# JSON output (for agent consumption)
emdx prime --json

# Quiet mode (errors only)
emdx prime --quiet
```

**Options:**
- `--brief, -b` - Compact output: tasks + epics, no git/docs
- `--json` - Output as JSON
- `--quiet, -q` - Suppress output (errors only)

## 🎨 **Interactive Interface**

### **emdx gui**
Launch interactive TUI browser.

```bash
# Launch full TUI interface
emdx gui

# Launch with a specific theme
emdx gui --theme emdx-dark
```

**TUI Key Bindings:**

*Global:*
- `1` - Switch to activity view (Docs)
- `2` - Switch to task browser
- `\` - Cycle theme
- `Ctrl+t` - Toggle dark/light mode
- `Ctrl+k` / `Ctrl+p` - Command palette
- `q` - Quit

*Activity View:*
- `j/k` - Navigate up/down
- `Enter` - Open fullscreen preview
- `/` - Filter
- `r` - Refresh
- `?` - Help

*Task Browser:*
- `j/k` - Navigate up/down
- `/` - Live filter bar
- `Escape` - Clear filter
- `g` - Toggle epic grouping
- `o` - Filter: open tasks
- `i` - Filter: active tasks
- `x` - Filter: blocked tasks
- `f` - Filter: done/failed/wontdo
- `*` - Show all (clear status filter)
- `d` - Mark done
- `a` - Mark active
- `w` - Mark won't do
- `r` - Refresh
- `?` - Help

## 🔗 **Integration Commands**

### **emdx gist**
Create or update a GitHub Gist from a document.

```bash
# Create secret gist from document (default)
emdx gist 42

# Create public gist
emdx gist 42 --public

# Create gist with description
emdx gist 42 --desc "Auth module analysis"

# Create gist and copy URL to clipboard
emdx gist 42 --copy

# Create gist and open in browser
emdx gist 42 --open

# Update an existing gist
emdx gist 42 --update abc123def456
```

**Options:**
- `--public` - Create public gist
- `--secret` - Create secret gist (default)
- `--desc, -d TEXT` - Gist description
- `--copy, -c` - Copy gist URL to clipboard
- `--open, -o` - Open gist in browser
- `--update, -u TEXT` - Update existing gist ID

## ⚙️ **Configuration**

### **Environment Variables**
- `EMDX_DATABASE_URL` - Custom database connection URL
- `GITHUB_TOKEN` - For Gist integration
- `EDITOR` - Default editor for `emdx edit`

### **Default Locations**
- **Database**: `~/.emdx/emdx.db`
- **Logs**: `~/.emdx/logs/`
- **Config**: `~/.emdx/config.json` (if used)

## 🎯 **Common Workflows**

### **Quick Note Capture**
```bash
# Save a quick thought
echo "Remember to update documentation" | emdx save --title "Todo: Docs"

# Save with tags
echo "Bug in auth system" | emdx save --title "Auth Bug" --tags "bug,urgent"
```

### **Research Documentation**
```bash
# Save research findings
emdx save --file research.md --tags "analysis,done"

# Find related research later
emdx find --tags "analysis"
```

### **Project Management**
```bash
# Track project gameplan
echo "Phase 1: Setup infrastructure" | emdx save --title "Project Gameplan" --tags "gameplan,active"

# Mark phases complete
emdx tag add 123 done success
emdx tag remove 123 active

# Review project progress
emdx find --tags "gameplan" --project "myproject"
```

---

## 📋 Task Management (`emdx task`)

Agent work queue for tracking tasks with status, epics, and categories.

### Display IDs

Tasks assigned to a category show a `KEY-N` display ID (e.g. `FEAT-12`, `SEC-3`) instead of the raw `#id`. This ID is auto-assigned when a task is added with `--cat` and appears throughout command output. You can use either format to reference tasks:

```bash
emdx task view FEAT-12      # By display ID
emdx task view 42           # By raw ID
emdx task done SEC-3        # Display IDs work with all commands
```

### Adding Tasks

```bash
# Add a basic task
emdx task add "Implement user authentication"

# Add with description
emdx task add "Refactor API" --description "Improve performance and add caching"

# Add linked to a document
emdx task add "Implement this plan" --doc 42

# Add to an epic
emdx task add "Setup database" --epic 510

# Add with category key
emdx task add "Fix auth bug" --cat SEC
```

**Options:**
- `--doc, -d INTEGER` - Link to document ID
- `--description, -D TEXT` - Task description
- `--epic, -e INTEGER` - Add to epic (task ID)
- `--cat, -c TEXT` - Category key (e.g. SEC)

### Finding Ready Tasks

```bash
# Show tasks ready to work on
emdx task ready
```

### Viewing Tasks

```bash
# View full task details
emdx task view 1
```

### Listing Tasks

```bash
# List all tasks
emdx task list

# List by status or category
emdx task list --done
emdx task list --cat FEAT

# Filter completed tasks by date
emdx task list --done --today
emdx task list --done --since 2026-02-15
```

### Updating Task Status

```bash
# Mark task as in-progress
emdx task active 1

# Mark task as done
emdx task done 1

# Mark task as blocked
emdx task blocked 1

# Mark task as won't do (closed without completing)
emdx task wontdo 42
emdx task wontdo TOOL-12
emdx task wontdo 42 --note "Superseded by #55"
```

**`wontdo` Options:**
- `--note, -n TEXT` - Reason for closing (logged to task work log)
- `--json` - Output as JSON

### Setting Priority

```bash
# Show current priority
emdx task priority 42

# Set to highest priority (1=highest, 5=lowest)
emdx task priority 42 1

# Set priority using KEY-N display ID
emdx task priority FEAT-5 2
```

**Options:**
- `--json` - Output as JSON

### Work Log

```bash
# View task work log
emdx task log 1

# Add entry to task log
emdx task log 1 "Started implementation"
```

### Progress Notes

Log a progress note on a task without changing its status. Shorthand for `emdx task log <id> "message"`.

```bash
emdx task note 42 "Root cause is in auth middleware"
emdx task note TOOL-12 "Tried approach X, didn't work — switching to Y"
```

### Dependencies (`emdx task dep`)

Manage task dependencies to control execution order. A task with unresolved dependencies is considered blocked and won't appear in `emdx task ready`.

#### **emdx task dep add**

```bash
# Task 5 depends on task 3 (task 5 is blocked until task 3 is done)
emdx task dep add 5 3

# Works with display IDs
emdx task dep add FEAT-5 3
```

#### **emdx task dep rm**

```bash
# Remove a dependency
emdx task dep rm 5 3
emdx task dep rm FEAT-5 3
```

#### **emdx task dep list**

```bash
# Show what a task depends on and what depends on it
emdx task dep list 5
emdx task dep list FEAT-5

# Output as JSON
emdx task dep list 5 --json
```

**Options:**
- `--json` - Output as JSON

### Dependency Chain (`emdx task chain`)

Show the full dependency chain for a task. Traces upward through blockers and downward through dependents to show the complete dependency graph.

```bash
emdx task chain 5
emdx task chain FEAT-5

# Output as JSON
emdx task chain 5 --json
```

**Options:**
- `--json` - Output as JSON

### Deleting Tasks

```bash
# Delete a task
emdx task delete 1
```

### Deleting Categories and Epics

```bash
# Delete a category (unlinks tasks, doesn't delete them)
emdx task cat delete SEC

# Force delete even if open/active tasks exist
emdx task cat delete SEC --force

# Delete an epic (unlinks child tasks, doesn't delete them)
emdx task epic delete 510

# Force delete even if open/active children exist
emdx task epic delete 510 --force
```

### Task Statuses

| Status | Icon | Description |
|--------|------|-------------|
| `open` | ○ | Not yet started |
| `active` | ● | Currently being worked on |
| `blocked` | ⚠ | Waiting on dependencies or external factors |
| `done` | ✓ | Completed successfully |
| `wontdo` | ⊘ | Closed without completing (terminal, unblocks dependents) |

---

## 🏔️ Epic Management (`emdx task epic`)

Organize tasks into epics for larger initiatives.

```bash
# Create an epic
emdx task epic create "Auth System Overhaul"

# List all epics with task counts
emdx task epic list

# View an epic and its tasks
emdx task epic view 510

# Mark epic as active
emdx task epic active 510

# Mark epic as done
emdx task epic done 510

# Delete an epic (unlinks child tasks)
emdx task epic delete 510
```

---

## 🏷️ Category Management (`emdx task cat`)

Manage task categories for auto-numbered task titles (e.g., SEC-1, SEC-2).

```bash
# Create a category
emdx task cat create SEC --description "Security tasks"

# List all categories with task counts
emdx task cat list

# Backfill existing tasks into the category system
emdx task cat adopt SEC

# Rename/merge a category
emdx task cat rename SEC SECURITY          # Rename SEC → SECURITY
emdx task cat rename OLD NEW               # Merge OLD into NEW (if NEW exists)

# Delete a category (unlinks tasks)
emdx task cat delete SEC
```

---

## 🔭 Explore (`emdx explore`)

Explore what your knowledge base knows. Clusters documents by content similarity to build a topic map, showing what areas your KB covers and how deep the coverage is.

Topic map generation is free (no API calls). Question generation uses the Claude API.

### Topic Map

```bash
# Show all topics (free, no API calls)
emdx explore

# Tighter clusters (higher threshold = fewer, more focused topics)
emdx explore --threshold 0.5

# Show coverage gaps (thin topics, stale areas, lonely tags)
emdx explore --gaps
```

### Question Generation

```bash
# What questions can my KB answer? (uses Claude API)
emdx explore --questions

# Limit to top N topics
emdx explore --limit 5 --questions
```

### Machine Output

```bash
# Full JSON output
emdx explore --json

# JSON with questions
emdx explore --json --questions
```

**Options:**
- `--threshold, -t FLOAT` - Similarity threshold for clustering (0.0-1.0, lower = more grouping, default: 0.5)
- `--questions, -q` - Generate answerable questions per topic (uses Claude API)
- `--gaps, -g` - Detect coverage gaps (thin topics, stale areas, lonely tags)
- `--json` - Output results as JSON
- `--rich` - Enable colored Rich output
- `--limit, -n INTEGER` - Max topics to show (0 = all, default: 0)

---

## 🧪 Distill (`emdx distill`)

Surface and synthesize KB content into audience-aware summaries. Finds documents matching a topic or tags, then uses AI to produce a coherent synthesis tailored for the target audience.

```bash
# Distill all docs matching a topic
emdx distill "authentication"

# Distill docs matching tags
emdx distill --tags "security,active"

# Target a specific audience
emdx distill --for docs "API design"
emdx distill --for coworkers "sprint progress"

# Save the distilled output to KB
emdx distill "auth" --save --title "Auth Summary"

# Quiet mode — output only the distilled content (no headers/stats)
emdx distill "auth" --quiet

# Limit number of source documents
emdx distill "auth" --limit 10
```

**Options:**
- `TOPIC` - Topic or search query to find and distill documents (positional)
- `--tags, -t TEXT` - Comma-separated tags to filter documents
- `--for, -f TEXT` - Target audience: `me` (personal, default), `docs` (documentation), `coworkers`/`team` (team briefing)
- `--limit, -l INTEGER` - Maximum number of documents to include (default: 20)
- `--save, -s` - Save the distilled output to the knowledge base
- `--title TEXT` - Title for saved document (defaults to "Distilled: <topic>")
- `--quiet, -q` - Output only the distilled content (no headers/stats)

**Notes:**
- Requires either a topic or `--tags` (or both)
- When both topic and tags are provided, results are merged (tag matches first, then topic matches)
- Saved documents are auto-tagged with `distilled` and `for-<audience>`

---

## 📰 Briefing (`emdx briefing`)

Show recent emdx activity summary. Use `--save` to generate and persist a session wrapup (replaces old `wrapup` command).

```bash
# Show activity from the last 24 hours (default)
emdx briefing

# Show activity since a specific time
emdx briefing --since "2 days ago"
emdx briefing --since 2026-02-14
emdx briefing --since yesterday

# Output as JSON for agent consumption
emdx briefing --json

# Generate session wrapup and save to KB (replaces old `emdx wrapup`)
emdx briefing --save
emdx briefing --save --hours 8
emdx briefing --save --model sonnet
```

---

## ⏳ Staleness Tracking (`emdx maintain stale`)

Track knowledge decay and identify documents needing review.

```bash
# Show stale documents prioritized by urgency
emdx maintain stale list
```

### **emdx maintain stale touch**

Reset a document's staleness timer without incrementing the view count.

```bash
# Touch single document
emdx maintain stale touch 42

# Touch multiple documents
emdx maintain stale touch 42 43 44
```
