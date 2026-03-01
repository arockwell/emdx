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

# Standing queries — save a search and check for new matches
emdx find --watch "deployment"
emdx find --watch-list
emdx find --watch-check
emdx find --watch-remove 3

# Machine-readable ask output (pipe-friendly)
emdx find --ask --machine "What's our caching strategy?"

# Scope ask/context to recent documents only
emdx find --ask --recent-days 7 "latest deployment issues"

# Combine filters
emdx find --ask --tags "security" --recent-days 30 "auth vulnerabilities"

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
- `--watch` - Save query as a standing query (alerts on new matches)
- `--watch-list` - List all standing queries
- `--watch-check` - Check all standing queries for new matches
- `--watch-remove INTEGER` - Remove a standing query by ID
- `--context` - Output retrieved context as plain text (for piping to claude)
- `--machine` - Pipe-friendly ask output: `ANSWER:`, `SOURCES:`, `CONFIDENCE:` on stdout, metadata on stderr
- `--recent-days INTEGER` - Scope `--ask`/`--context` retrieval to documents created in the last N days
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

> **Tip:** Backups can be triggered automatically via Claude Code hooks (e.g., on session start). Use `--quiet` for silent hook-driven backups.

#### **emdx maintain cloud-backup**
Upload, list, and download knowledge base backups to cloud providers (GitHub Gists or Google Drive).

```bash
# Upload to GitHub Gists (default)
emdx maintain cloud-backup upload

# Upload to Google Drive
emdx maintain cloud-backup upload --provider gdrive

# Upload with description
emdx maintain cloud-backup upload -d "Before migration"

# List cloud backups
emdx maintain cloud-backup list
emdx maintain cloud-backup list --provider gdrive --json

# Download a backup
emdx maintain cloud-backup download <backup_id>

# Set up authentication for a provider
emdx maintain cloud-backup auth github
emdx maintain cloud-backup auth gdrive
```

**Subcommands:**
- `upload` - Upload current database as a cloud backup
  - `--provider, -p TEXT` - Cloud provider: `github` or `gdrive` (default: github)
  - `--description, -d TEXT` - Description for this backup
  - `--json` - Output as JSON
- `list` - List cloud backups
  - `--provider, -p TEXT` - Cloud provider (default: github)
  - `--json` - Output as JSON
- `download` - Download a cloud backup by ID
  - `--provider, -p TEXT` - Cloud provider (default: github)
- `auth` - Set up authentication for a cloud backup provider

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

#### **emdx maintain stale**
Track knowledge decay and identify documents needing review.

```bash
# Show stale documents prioritized by urgency
emdx maintain stale list

# Touch single document (reset staleness timer without incrementing views)
emdx maintain stale touch 42

# Touch multiple documents
emdx maintain stale touch 42 43 44
```

**Subcommands:**
- `list` - Show stale documents prioritized by urgency
- `touch` - Reset a document's staleness timer without incrementing the view count

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

#### **emdx maintain freshness**
Score document freshness and identify stale documents. Combines multiple signals into a 0–1 freshness score: age decay, view recency, link health, content length, and tag signals.

```bash
# Score all documents
emdx maintain freshness

# Show only stale documents
emdx maintain freshness --stale

# Custom staleness threshold
emdx maintain freshness --stale --threshold 0.5

# JSON output
emdx maintain freshness --json
```

**Options:**
- `--stale` - Show only documents below the freshness threshold
- `--threshold, -t FLOAT` - Staleness threshold (0–1, default: 0.3)
- `--json` - Output as JSON

#### **emdx maintain gaps**
Detect knowledge gaps and areas with sparse coverage. Analyzes the KB for tags with few documents, dead-end documents, orphaned knowledge, stale topics, and projects with high task counts but low documentation.

```bash
# Show knowledge gaps
emdx maintain gaps

# Show more gaps per category
emdx maintain gaps --top 20

# Custom stale threshold
emdx maintain gaps --stale-days 30

# JSON output
emdx maintain gaps --json
```

**Options:**
- `--top, -n INTEGER` - Number of gaps to show per category (default: 10)
- `--stale-days, -s INTEGER` - Days threshold for stale topics (default: 60)
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
- `--json, -j` - Output as JSON

#### **emdx maintain compact**
AI-powered document synthesis to reduce knowledge base sprawl. Also available as top-level `emdx compact`.

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

# JSON output
emdx maintain compact --dry-run --json
```

**Options:**
- `--dry-run, -n` - Show clusters without synthesizing
- `--auto` - Automatically synthesize all clusters
- `--threshold, -t FLOAT` - Similarity threshold (0.0-1.0, default: 0.5)
- `--topic TEXT` - Filter to documents matching this topic
- `--model, -m TEXT` - Model to use for synthesis
- `--yes, -y` - Skip confirmation prompts
- `--json, -j` - Output as JSON

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

Backward-compatible alias for `emdx wiki`. Use `emdx wiki` as the primary interface — all subcommands are identical. See the [Wiki section](#-wiki-emdx-wiki) for full documentation.

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
- `--smart, -s` - Context-aware priming: recent activity, key docs, knowledge map, stale detection (~500 tokens, no AI calls)
- `--verbose, -v` - Include execution guidance, recent docs, stale docs
- `--json` - Output as JSON
- `--quiet, -q` - Minimal output: just ready tasks

### **emdx context**
Walk the wiki link graph and assemble a token-budgeted context bundle for agent consumption.

```bash
# Context neighborhood for doc 87
emdx context 87

# Control depth and budget
emdx context 87 --depth 3 --max-tokens 6000

# Multiple seeds
emdx context 87 42 63

# Find seeds from a text query
emdx context --seed "401 error session middleware"

# JSON output for agents
emdx context 87 --json

# Dry run: show what would be included
emdx context 87 --plan
```

**Options:**
- `--seed, -s TEXT` - Text query to find seed documents
- `--depth, -d INTEGER` - Maximum traversal depth (default: 2)
- `--max-tokens, -t INTEGER` - Token budget for the context bundle (default: 4000)
- `--json, -j` - Output as JSON for agent consumption
- `--plan` - Dry run: show what would be included

### **emdx stale**
Show documents needing review, grouped by urgency tier (critical, warning, info).

```bash
# Show all stale documents
emdx stale

# Show only critical tier
emdx stale --tier critical

# Custom thresholds
emdx stale --critical-days 15 --warning-days 7

# Machine-readable output
emdx stale --json
```

**Options:**
- `--critical-days INTEGER` - Days threshold for high-importance docs (default: 30)
- `--warning-days INTEGER` - Days threshold for medium-importance docs (default: 14)
- `--info-days INTEGER` - Days threshold for low-importance docs (default: 60)
- `--limit, -n INTEGER` - Maximum documents to show (default: 20)
- `--project, -p TEXT` - Filter by project
- `--tier, -t TEXT` - Filter by tier: critical, warning, info
- `--json` - Output as JSON

### **emdx touch**
Mark documents as reviewed without incrementing view count. Updates `accessed_at` without changing `access_count`.

```bash
# Touch single document
emdx touch 42

# Touch multiple documents
emdx touch 42 43 44

# JSON output
emdx touch 42 --json
```

**Options:**
- `--json` - Output as JSON

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

### **emdx serve**
Start a JSON-RPC server over stdin/stdout for IDE integrations. Avoids the ~700ms Python cold-start overhead per CLI invocation by keeping a persistent process.

```bash
# Start the server (reads JSON requests from stdin, writes responses to stdout)
emdx serve
```

**Protocol:**
```json
// Request (one per line on stdin)
{"id": 1, "method": "find.recent", "params": {"limit": 20}}

// Response (one per line on stdout)
{"id": 1, "result": [...]}

// Error
{"id": 1, "error": {"code": -1, "message": "..."}}
```

**Available methods:**

| Method | Description |
|--------|-------------|
| `find.recent` | Get recent documents (`limit`) |
| `find.search` | Full-text search (`query`, `limit`) |
| `find.by_tags` | Search by tags (`tags`, `mode`, `limit`) |
| `view` | Get full document by ID (`id`) |
| `save` | Save a document (`title`, `content`, `tags`) |
| `tag.list` | List all tags (`sort_by`) |
| `task.list` | List tasks (`status`, `epic_key`, `limit`) |
| `task.log` | Get task progress log (`id`, `limit`) |
| `task.update` | Update task status (`id`, `status`) |
| `task.log_progress` | Log progress on a task (`id`, `message`) |
| `status` | Get overall status |

The server emits `{"ready": true}` on startup and runs until stdin is closed (EOF).

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
- `EMDX_DB` - Override database path (e.g., `EMDX_DB=/tmp/test.db emdx status`)
- `EMDX_TEST_DB` - Test isolation database (set by pytest fixtures)
- `GITHUB_TOKEN` - For Gist integration
- `EDITOR` - Default editor for `emdx edit`

### **Default Locations**
- **Database**: `~/.config/emdx/knowledge.db` (production), `.emdx/dev.db` (dev checkout)
- **Logs**: `~/.config/emdx/emdx.log` (CLI), `~/.config/emdx/tui_debug.log` (TUI)
- **Backups**: `~/.config/emdx/backups/`

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

