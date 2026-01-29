# Option E: Full Split Planning - Deep Dive Analysis

## Executive Summary

This analysis explores splitting EMDX into separate packages: a core knowledge base (emdx-kb) and a workflow/automation layer (emdx-flow). The goal is to provide a clean separation between document management and AI-powered execution orchestration.

## Current Architecture Analysis

### Package Dependencies (pyproject.toml)

**Core/Shared:**
- `typer` - CLI framework
- `rich` - Terminal formatting
- `python-dotenv` - Environment config
- `gitpython` - Git operations

**KB-Heavy:**
- `textual` - TUI framework (document browser)
- `scikit-learn` - TF-IDF similarity
- `datasketch` - MinHash/LSH duplicate detection
- `sentence-transformers` - Local embeddings for semantic search
- `anthropic` - Claude API for RAG Q&A
- `numpy` - Vector operations

**Flow-Heavy:**
- `psutil` - Process management (execution monitoring)
- Google API libs - Export destinations (could be optional)
- `PyGithub` - Gist integration

### Module Import Analysis

**Knowledge Base Core (emdx-kb):**
```
emdx/
├── commands/
│   ├── core.py           # save, find, view, edit, delete
│   ├── browse.py         # list, stats, recent
│   ├── tags.py           # tag management
│   ├── similarity.py     # duplicate detection
│   ├── ask.py            # AI Q&A (RAG)
│   ├── export.py         # export profiles
│   ├── export_profiles.py
│   ├── gist.py           # GitHub gist
│   ├── gdoc.py           # Google Docs
│   └── groups.py         # document grouping
├── database/
│   ├── connection.py     # DB connection
│   ├── documents.py      # document CRUD (includes cascade stage ops)
│   ├── search.py         # FTS5 search
│   ├── groups.py         # group management
│   └── migrations.py     # schema migrations (ALL tables)
├── models/
│   ├── documents.py      # document model
│   ├── tags.py           # tag model
│   └── export_profiles.py
├── services/
│   ├── auto_tagger.py    # automatic tagging
│   ├── similarity.py     # content similarity
│   ├── embedding_service.py  # semantic embeddings
│   ├── duplicate_detector.py
│   └── github_service.py
├── ui/
│   ├── document_browser.py
│   ├── document_viewer.py
│   ├── file_browser/
│   ├── git_browser.py
│   └── search/
└── utils/
    ├── emoji_aliases.py
    ├── git.py
    └── text_formatting.py
```

**Workflow/Flow Layer (emdx-flow):**
```
emdx/
├── commands/
│   ├── cascade.py        # idea → prompt → analyzed → planned → done
│   ├── run.py            # quick task execution
│   ├── each.py           # reusable parallel commands
│   ├── agent.py          # sub-agent execution
│   ├── workflows.py      # workflow orchestration
│   ├── executions.py     # execution monitoring
│   ├── claude_execute.py # direct Claude execution
│   ├── prime.py          # session priming
│   ├── status.py         # status overview
│   └── tasks.py          # task management
├── each/
│   ├── database.py       # saved command storage
│   └── discoveries.py    # built-in discoveries
├── models/
│   ├── executions.py     # execution model
│   ├── tasks.py          # task model
│   └── task_executions.py
├── services/
│   ├── claude_executor.py      # Claude CLI execution
│   ├── unified_executor.py     # multi-CLI execution
│   ├── task_runner.py          # task execution
│   ├── execution_monitor.py    # health monitoring
│   ├── file_watcher.py         # log streaming
│   ├── log_stream.py
│   ├── lifecycle_tracker.py
│   └── cli_executor/           # CLI abstraction
│       ├── base.py
│       ├── claude.py
│       ├── cursor.py
│       └── factory.py
├── workflows/
│   ├── executor.py       # workflow execution engine
│   ├── registry.py       # workflow management
│   ├── database.py       # workflow DB operations
│   ├── base.py           # data models
│   ├── agent_runner.py   # agent execution
│   ├── output_parser.py
│   ├── synthesis.py      # output synthesis
│   ├── worktree_pool.py  # git worktree isolation
│   └── template.py       # prompt templates
└── ui/
    ├── cascade_browser.py
    ├── workflow_browser.py
    ├── log_browser.py
    ├── activity_browser.py
    ├── activity/
    ├── pulse/
    ├── execution/
    └── run_browser.py
```

## Split Architecture Options

### Option A: Two Packages (emdx-kb + emdx-flow)

```
emdx-kb/                     emdx-flow/
├── pyproject.toml           ├── pyproject.toml
├── emdx_kb/                  ├── emdx_flow/
│   ├── commands/            │   ├── commands/
│   ├── database/            │   ├── workflows/
│   ├── models/              │   ├── services/
│   ├── services/            │   ├── ui/
│   ├── ui/                  │   └── ...
│   └── utils/               └── ...
└── ...

Dependencies:
- emdx-flow depends on emdx-kb (for document storage)
- emdx-kb is standalone (no flow dependency)
```

**Pros:**
- Clear conceptual split (storage vs. execution)
- KB can be used independently
- Simpler than 3+ packages

**Cons:**
- Database migrations are shared (entangled)
- Some UI components need both
- Cascade operations touch KB tables directly

### Option B: Three Packages (emdx-core + emdx-kb + emdx-flow)

```
emdx-core/                   emdx-kb/                    emdx-flow/
├── database/                ├── commands/               ├── commands/
│   ├── connection.py        │   (KB commands)           │   (flow commands)
│   └── migrations.py        ├── services/               ├── workflows/
├── models/                  │   (KB services)           ├── services/
│   ├── base.py              ├── ui/                     │   (flow services)
│   └── ...                  │   (doc browser)           ├── ui/
├── config/                  └── ...                     │   (activity, logs)
└── utils/                                               └── ...

Dependencies:
- emdx-kb depends on emdx-core
- emdx-flow depends on emdx-core AND emdx-kb
```

**Pros:**
- Clean shared foundation
- Migrations live in core
- Better separation of concerns

**Cons:**
- More packages to maintain
- Version compatibility matrix complexity
- Still has KB ↔ Flow coupling at DB level

### Option C: Five Packages (Micro-services style)

```
emdx-core/      - database, config, utils
emdx-kb/        - document storage, search, tags
emdx-cascade/   - idea → PR pipeline
emdx-parallel/  - run, each, workflows
emdx-ai/        - embeddings, RAG, semantic search
```

**Pros:**
- Maximum flexibility
- Independent versioning
- Can install only what you need

**Cons:**
- Maintenance overhead
- Complex dependency management
- Overkill for the problem size

### Option D: Mono-repo with Workspace (Recommended for Development)

```
emdx/
├── pyproject.toml          # workspace root
├── packages/
│   ├── core/
│   │   └── pyproject.toml  # emdx-core
│   ├── kb/
│   │   └── pyproject.toml  # emdx-kb
│   └── flow/
│       └── pyproject.toml  # emdx-flow
└── ...
```

**Pros:**
- Single repo, multiple packages
- Shared development tooling
- Coordinated releases
- Poetry/PDM/Hatch workspace support

**Cons:**
- Learning curve for workspace tools
- CI/CD complexity

## Database Split Analysis

### Current Tables (32 total)

**KB-Owned (13 tables):**
```sql
documents           -- Core content storage
documents_fts       -- Full-text search
tags                -- Tag definitions
document_tags       -- Document-tag junction
document_embeddings -- Semantic search vectors
document_groups     -- Grouping system
document_group_members
gists               -- GitHub gist exports
gdocs               -- Google Docs exports
export_profiles
export_history
schema_version      -- Migration tracking
```

**Flow-Owned (11 tables):**
```sql
executions          -- Claude execution tracking
workflows           -- Workflow definitions
workflow_runs       -- Workflow execution history
workflow_stage_runs
workflow_individual_runs
workflow_presets    -- Saved variable configs
cascade_runs        -- Cascade pipeline tracking
tasks               -- Task management
task_deps           -- Task dependencies
task_log            -- Task work log
task_executions     -- Task-workflow join
```

**Shared/Bridge (4 tables):**
```sql
document_sources    -- Links docs to workflow runs
-- Note: documents.stage, documents.pr_url are used by cascade
-- Note: documents.parent_id links exploration/synthesis outputs
```

### Database Communication Problem

The core issue: **Flow creates documents, KB stores them**

```python
# In cascade.py (flow)
new_doc_id = save_document(...)  # Calls KB function
update_document_stage(new_doc_id, next_stage)  # KB function

# In workflows/executor.py (flow)
result = await run_agent(...)
# Agent saves output: echo "OUTPUT" | emdx save
# This creates a document in KB database
```

### Solutions:

#### Solution 1: Shared Database File
Both packages use same SQLite file. Each package owns its tables.

**Migration Strategy:**
- `emdx-kb` runs migrations 0-N (KB tables)
- `emdx-flow` runs migrations N+1-M (flow tables)
- Version file tracks which package ran which migrations

```python
# emdx-core/database/migrations.py
MIGRATIONS = {
    "kb": [(0, "documents"), (1, "tags"), ...],
    "flow": [(100, "executions"), (101, "workflows"), ...],
}
```

#### Solution 2: Separate Databases with Cross-Refs
```
~/.config/emdx/emdx-kb.db       # documents, tags
~/.config/emdx/emdx-flow.db     # workflows, executions
```

Cross-reference via IDs only. Requires API calls for document content.

#### Solution 3: Core Package Owns Database
`emdx-core` owns all migrations and DB connection.
KB and Flow only add domain-specific operations.

## Versioning Strategy

### Semantic Versioning with Compatibility Matrix

```
emdx-core   0.1.x   0.2.x   0.3.x
emdx-kb     0.1.x   0.2.x   0.3.x   (tracks core)
emdx-flow   0.1.x   0.2.x   0.3.x   (tracks core)
```

### Dependency Specification
```toml
# emdx-kb/pyproject.toml
[tool.poetry.dependencies]
emdx-core = "^0.2.0"  # Compatible with 0.2.x

# emdx-flow/pyproject.toml
[tool.poetry.dependencies]
emdx-core = "^0.2.0"
emdx-kb = "^0.2.0"    # Same major.minor as core
```

### Breaking Changes
- Core version bump → bump KB and Flow
- KB-only change → bump KB, not Flow
- Flow-only change → bump Flow, not KB

## Migration Checklist

### Phase 1: Extract Core
- [ ] Create `emdx-core` package
- [ ] Move database connection, config, utils
- [ ] Move base migrations
- [ ] Set up package publishing

### Phase 2: Create KB Package
- [ ] Create `emdx-kb` package
- [ ] Move document commands
- [ ] Move tag system
- [ ] Move search/similarity services
- [ ] Move document browser UI
- [ ] Set up KB-specific migrations

### Phase 3: Create Flow Package
- [ ] Create `emdx-flow` package
- [ ] Move workflow system
- [ ] Move cascade pipeline
- [ ] Move execution services
- [ ] Move activity UI components
- [ ] Set up flow-specific migrations

### Phase 4: Integration
- [ ] Create `emdx` meta-package (installs all)
- [ ] Update CLAUDE.md for new structure
- [ ] Update documentation
- [ ] Test cross-package operations

## Risk Analysis

### High Risk
1. **Database migration conflicts** - Two packages updating same DB
2. **Breaking existing installations** - Need migration path
3. **Import path changes** - `emdx.` → `emdx_kb.` breaks everything

### Medium Risk
1. **Development velocity** - More packages = more PRs
2. **Testing complexity** - Cross-package integration tests
3. **Documentation drift** - Multiple READMEs to maintain

### Low Risk
1. **Performance** - SQLite is local, no network overhead
2. **Security** - Same trust model, just split code

## Recommendation

**Start with Option D (Mono-repo Workspace)** because:

1. **Iterative splitting** - Can start with core, add packages gradually
2. **Atomic commits** - Cross-package changes in single PR
3. **Shared CI/CD** - One pipeline for all packages
4. **Easy rollback** - Can always recombine if it doesn't work

**Database Strategy: Solution 1 (Shared DB)** because:
- SQLite performs fine with single file
- No cross-process issues (CLI is single-threaded)
- Simplest migration path

**Migration Numbering:**
- KB: 0-99
- Flow: 100-199
- AI/Semantic: 200-299

## Dependency Graph

```
┌─────────────────────────────────────────────────────────────────┐
│                        emdx (meta-package)                       │
│                     Installs all packages                        │
└─────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│    emdx-flow    │  │    emdx-kb      │  │    emdx-ai      │
│                 │  │                 │  │   (optional)    │
│ workflows/      │  │ documents/      │  │ embeddings/     │
│ cascade/        │  │ tags/           │  │ semantic/       │
│ run/each/       │  │ search/         │  │ RAG Q&A/        │
│ executions/     │  │ export/         │  │                 │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         │                    ▼                    │
         │           ┌─────────────────┐           │
         └──────────►│   emdx-core     │◄──────────┘
                     │                 │
                     │ database/       │
                     │ config/         │
                     │ utils/          │
                     │ migrations/     │
                     └─────────────────┘
```

## Questions to Resolve

1. **Who owns the TUI (gui command)?**
   - Currently: single App with multiple browsers
   - Could: KB owns doc browser, Flow owns activity browser
   - Or: Keep unified GUI in meta-package

2. **Who owns `emdx save`?**
   - KB owns document storage
   - But Flow calls it to save agent outputs
   - Answer: KB owns it, Flow imports from KB

3. **What about `prime` and `status`?**
   - These aggregate across KB and Flow
   - Answer: Put in meta-package or Flow (since Flow needs KB anyway)

4. **CLI entry points?**
   - `emdx` - full CLI (meta-package)
   - `emdx-kb` - KB-only CLI
   - `emdx-flow` - Flow-only CLI (requires KB installed)

## Wild Ideas Explored

### Idea 1: Single Binary with Lazy Loading
Like `git` - subcommands load modules on demand.
```python
# emdx/main.py
if subcommand in KB_COMMANDS:
    from emdx_kb import handle_command
elif subcommand in FLOW_COMMANDS:
    from emdx_flow import handle_command
```
**Verdict:** Good for performance, doesn't solve the split problem.

### Idea 2: Compile to Different Binaries
```bash
emdx-kb      # KB-only binary
emdx-flow    # Flow binary (includes KB)
emdx         # Full binary
```
**Verdict:** Increases build complexity, some redundancy.

### Idea 3: Plugin Architecture
KB and Flow as plugins to a tiny core.
```python
# emdx-core discovers plugins
for plugin in discover_plugins():
    register_commands(plugin.commands)
    run_migrations(plugin.migrations)
```
**Verdict:** Elegant but over-engineered for 2-3 packages.

## Practical Package Structure (Recommended)

```
emdx-monorepo/
├── pyproject.toml              # Workspace config
├── README.md
├── CLAUDE.md                   # Shared instructions
│
├── packages/
│   ├── core/
│   │   ├── pyproject.toml
│   │   └── emdx_core/
│   │       ├── __init__.py
│   │       ├── database/
│   │       │   ├── __init__.py
│   │       │   ├── connection.py
│   │       │   └── base_migrations.py  # schema_version only
│   │       ├── config/
│   │       │   ├── __init__.py
│   │       │   ├── settings.py
│   │       │   └── constants.py
│   │       └── utils/
│   │           ├── __init__.py
│   │           ├── git.py
│   │           ├── datetime_utils.py
│   │           └── output.py
│   │
│   ├── kb/
│   │   ├── pyproject.toml
│   │   └── emdx_kb/
│   │       ├── __init__.py
│   │       ├── commands/          # save, find, view, edit, tags
│   │       ├── database/          # documents, search
│   │       ├── models/            # document, tag models
│   │       ├── services/          # auto_tagger, similarity
│   │       ├── ui/                # document_browser
│   │       └── migrations/        # KB-specific (0-99)
│   │
│   ├── flow/
│   │   ├── pyproject.toml
│   │   └── emdx_flow/
│   │       ├── __init__.py
│   │       ├── commands/          # cascade, run, each, workflow
│   │       ├── workflows/         # executor, registry
│   │       ├── services/          # claude_executor, task_runner
│   │       ├── ui/                # activity, logs
│   │       └── migrations/        # Flow-specific (100-199)
│   │
│   └── ai/                        # Optional package
│       ├── pyproject.toml
│       └── emdx_ai/
│           ├── __init__.py
│           ├── commands/          # ai ask, ai search
│           ├── services/          # embedding_service, ask_service
│           └── migrations/        # AI-specific (200-299)
│
├── apps/
│   └── emdx/                      # Meta-package / unified CLI
│       ├── pyproject.toml
│       └── emdx/
│           ├── __init__.py
│           └── main.py            # Unified entry point
│
└── tests/
    ├── core/
    ├── kb/
    ├── flow/
    ├── ai/
    └── integration/               # Cross-package tests
```

## Next Steps

1. Create proof-of-concept with `emdx-core` extraction
2. Validate imports work across package boundary
3. Test migration system with split ownership
4. Get user feedback on package granularity preference

---

*Analysis created: 2026-01-29*
*Tags: analysis, architecture, gameplan*
