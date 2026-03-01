# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.27.0] - 2026-03-01

**Agent-ready knowledge base.** This release focuses on making emdx a better substrate for AI agents — cloud backups to GitHub Gists and Google Drive, graph-aware context assembly for token-budgeted retrieval, smart session priming with activity summaries and staleness detection, machine-readable search output for piping, and a first-run onboarding experience that populates an empty KB with tutorial content. Several maintenance commands gained `--json` output, and ~1,500 lines of dead TUI code were removed.

### 🚀 Major Features

#### Cloud Backup: GitHub Gists and Google Drive (#954)
A protocol-based cloud backup system with pluggable providers. `emdx maintain cloud-backup upload` pushes encrypted backups to GitHub Gists (via `gh`) or Google Drive (via google-api-python-client). `cloud-backup list` shows remote backups; `cloud-backup download` restores them. Each provider implements a `BackupProvider` protocol, making new providers straightforward to add.

#### Graph-Aware Context Assembly: `emdx context` (#916)
New command that walks the wiki link graph outward from seed documents, scores reachable documents by link quality and hop distance, and packs them into a token-budgeted context bundle. `--seed "query"` resolves seeds from text, `--depth` controls BFS traversal, `--max-tokens` sets the budget, and `--plan` shows what would be included without fetching content. Designed for feeding rich, connected context to AI agents.

#### First-Run Onboarding (#917)
New users now see a Things-style welcome experience instead of a blank screen. On first launch with an empty database, emdx seeds two tutorial documents (Welcome + Keyboard Shortcuts) and five getting-started tasks under a START epic. A `schema_flags` table tracks one-time operations so content is never re-seeded. Empty-state placeholders guide users who delete the tutorial content.

#### Smart Session Priming: `prime --smart` (#946)
The `--smart` flag adds context-aware sections to `emdx prime`: recent activity with relative timestamps and view counts, most-accessed key documents, a knowledge map showing tag distribution, and staleness detection — all from pure database queries with no AI calls. Outputs under 500 tokens, works with `--json`, and avoids duplicating sections when combined with `--verbose`.

### 🔧 Improvements

- **Knowledge Health: Freshness and Gap Detection** — `maintain freshness` scores documents 0–1 by combining age decay, view recency, link health, and content signals; `maintain gaps` finds sparse coverage, orphaned docs, and under-documented projects (#933, #934)
- **Standing Queries** — `emdx find --watch` saves a search and `--watch-check` reports new matches since last check; manage with `--watch-list` and `--watch-remove` (#935)
- **Machine-readable ask output** — `emdx find --ask --machine` produces pipe-friendly output with `ANSWER:`, `SOURCES:`, and `CONFIDENCE:` on stdout, metadata on stderr. `--recent-days N` scopes retrieval to recent documents; `--tags` filtering now properly wired through (#948)
- **Top-level convenience commands** — `emdx stale` and `emdx touch` provide quick access to freshness scoring and timestamp updates; `emdx compact` registered as a top-level command (#6, #951)
- **JSON output for maintenance commands** — `emdx compact --json` and `emdx maintain entities --json` now produce structured output (#955)
- **Skills moved to project level** — emdx-specific skills relocated from `skills/` to `.claude/skills/` with a `marketplace.json` manifest for plugin discovery (#941, #944)
- **Documentation refresh** — fixed drift across 12 files after the 0.26.0 release, updated CLI reference, and removed deprecated env vars (#949, #950)

### 🐛 Bug Fixes

- Fixed `type: ignore` needed for googleapiclient TYPE_CHECKING import (#954)
- Fixed delegate assertion in `test_event_types_constant` that broke after delegate removal
- Fixed ANSI escape codes in `test_stale.py` help text assertions (#947)
- Fixed `plugin.json` not being updated by version bump script (#943)
- Fixed marketplace.json location for plugin discoverability

### 🗑️ Removed

- **~1,500 lines of dead TUI code** — unreachable `SearchScreen` package, orphaned editor widgets, delegate system ghosts in help bars and key contexts, dead methods and stubs (#953)
- **`pr-check` and `merge-chain` commands** — removed unused CLI commands (#952)

[0.27.0]: https://github.com/arockwell/emdx/compare/v0.26.0...v0.27.0

## [0.26.0] - 2026-03-01

**Knowledge intelligence and infrastructure overhaul.** This release adds a suite of "thinking" modes to search — deliberative reasoning, devil's advocate challenges, Socratic debugging, and inline citations — plus three new `maintain` subcommands for detecting stale work, code drift, and contradictions. The delegate system (~13,000 lines) has been removed in favor of native Claude Code agents, document versioning and event history are now tracked automatically, and the migration engine was rewritten to use set-based tracking that survives branch divergence. Daily backups now happen automatically with logarithmic retention.

### 🚀 Major Features

#### Knowledge Intelligence: Ask Modes and Confidence (#926)
New flags on `emdx find` transform search into structured reasoning. `--think` builds a position paper with arguments for and against, citing doc IDs. `--challenge` (requires `--think`) plays devil's advocate, surfacing evidence against a position. `--debug` generates Socratic diagnostic questions drawing on past bug fixes. `--cite` adds inline `[#ID]` citations using chunk-level retrieval. Confidence scoring was replaced with a 6-signal multi-factor assessment (retrieval score distribution, source count, query coverage, topic coherence, recency).

#### Knowledge Health: Drift, Code-Drift, and Contradictions (#921, #922, #923)
Three new `maintain` subcommands for KB hygiene. `maintain drift` detects stale work items — tasks and documents that haven't been touched in configurable time windows. `maintain code-drift` cross-references code paths mentioned in KB documents against the actual codebase, flagging references to files, functions, or classes that no longer exist. `maintain contradictions` uses NLI (natural language inference) to find documents that make conflicting claims.

#### Document Versioning and Event History (#927)
Every document edit now creates a version snapshot with SHA-256 hashes and character deltas. `emdx history <id>` shows the version timeline; `emdx diff <id>` renders unified diffs between versions. A new `knowledge_events` table provides an append-only audit log of all KB interactions — saves, edits, searches, views — with session correlation and metadata.

#### Delegate System Removed (#931)
The custom `emdx delegate` subprocess launcher — worktree isolation, PR creation, execution tracking, output persistence — has been replaced by native Claude Code Agent tool and SubagentStop hooks. Removed ~13,000 lines (~15% of the codebase) across 37 deleted files. Services that previously used `UnifiedExecutor` now call `subprocess.run(["claude", "--print", ...])` directly.

#### Set-Based Migration Tracking and Dev DB Isolation (#940)
Migration tracking switched from sequential integers to string-based sets, preventing branch-divergence collisions where a feature branch's migration ID could shadow a different migration on main. New `emdx db` subcommand (`status`, `path`, `copy-from-prod`) for database path management. Running via `poetry run emdx` now auto-isolates to a local `.emdx/dev.db` so dev work never touches production.

### 🔧 Improvements

- **Wiki promoted to top-level command** — `emdx wiki` now works directly instead of requiring `emdx maintain wiki`, with all subcommands (`setup`, `topics`, `triage`, `generate`, `view`, `search`, `export`, `progress`) available at the top level (#928)
- **Automatic daily backups** — a SessionStart hook creates a compressed daily backup via SQLite's `Connection.backup()` API, with logarithmic retention keeping ~19 backups spanning 2 years (#938)
- **Serendipity search** — `emdx find --wander` retrieves results then randomly selects a subset, surfacing forgotten documents for re-discovery (#924)
- **Adversarial document review** — `emdx view --review` runs an LLM adversarial review of a document, checking for staleness, contradictions, and missing context (#920)
- **Compact prime output** — `emdx prime --brief` outputs a condensed context injection suitable for constrained token budgets (#919)
- **Status vitals and mirror** — `emdx status --vitals` shows KB health metrics; `emdx status --mirror` reflects the current session's activity back as a summary (#925)
- **Clean JSON output** — Rich spinners and Progress bars are now suppressed in `--json` mode across all commands, producing reliably parseable output

### 🐛 Bug Fixes

- Fixed SubagentStop hook falsely marking agents as errored when they completed successfully (#942)
- Fixed CLI commands in gameplan-review skill pointing to removed delegate subcommands (#929)
- Fixed `--json` output for ask modes (`--think`, `--challenge`, `--debug`, `--cite`) producing Rich markup instead of JSON (#926)
- Fixed OSError crash when loading NLI model in contradiction service on systems without the model cached
- Fixed missing `migration_053_remove_delegate_system` function that broke fresh database creation after delegate removal
- Stripped ANSI escape codes in test assertions for reliable CI (#932)

### 🗑️ Removed

- **`emdx delegate` command** and all supporting infrastructure — `UnifiedExecutor`, `cli_executor/`, execution monitoring, worktree management, output parsing, delegate browser TUI, delegate skills (#931)

[0.26.0]: https://github.com/arockwell/emdx/compare/v0.25.1...v0.26.0

## [0.25.1] - 2026-02-28

**TUI interaction polish + SubagentStop hook.** Fixed several rough edges in mouse and keyboard behavior: clicking a document row no longer accidentally opens the fullscreen preview (only Enter and double-click do), pressing `q` inside a document preview now closes the modal instead of quitting the entire app, and the task screen gained a `u` key to reopen tasks with all action keys clearly labeled in the help bar. Task descriptions now render as markdown. The SubagentStop hook was rewritten to reliably capture native Claude Code agent output into the knowledge base.

### 🚀 Features

- **SubagentStop hook for native agent auto-save** — rewrote the SubagentStop hook to use temp files instead of env vars (fixing silent failure on large payloads), added agent-type tagging (`agent:explore`, `agent:general-purpose`, `agent:plan`), PR URL auto-detection, and enrichment pipeline integration. Foundation for replacing `emdx delegate` with native Claude Code agents (#918)

### 🔧 Improvements

- **Explicit task action keys in help bar** — replaced cryptic `o/i/x/f Status` with clear labels: `d Done  a Active  b Blocked  w Won't do  u Reopen` (#911)
- **Reopen tasks with `u`** — new keybinding to mark a done/blocked/failed task back to open/ready (#911)
- **Task notes render as markdown** — task descriptions now display as rendered markdown in both CLI (`task view`) and TUI detail pane, matching document and work log formatting (#914)

### 🐛 Bug Fixes

- **Single click no longer opens fullscreen** — clicking an already-highlighted document row fired DataTable's `RowSelected`, which triggered fullscreen. Replaced with a custom `EnterPressed` message so only keyboard Enter opens fullscreen (#911)
- **`q` in document preview closes modal, not app** — `BrowserContainer.on_key()` intercepted `q` globally even when a modal screen was active. Now skips `q` handling when `screen_stack > 1` (#911)

[0.25.1]: https://github.com/arockwell/emdx/compare/v0.25.0...v0.25.1

## [0.25.0] - 2026-02-27

**Delegate Browser and streamlined TUI.** A new Delegate Browser (key `3`) gives real-time visibility into delegate activity — active, recently completed, and failed tasks with a detail pane showing prompts, subtask trees, and clickable links to PRs and output documents. The save pipeline was rewritten to bypass the hook-based Rube Goldberg flow, saving output directly in Python after `subprocess.run()`. The Q&A screen was retired (replaced by `emdx find --ask` and Claude Code), and the remaining TUI chrome was simplified with cleaner help bars and a working Enter-to-fullscreen shortcut.

### 🚀 Major Features

#### Delegate Browser TUI (#905)
New TUI screen on key `3` with a DataTable showing ACTIVE, RECENT, and FAILED delegate sections, plus a RichLog detail pane. The detail pane shows the delegate's prompt (with linkified URLs), subtask tree with status icons, and a Links section with clickable PR URLs and output document references. Auto-refreshes every 5 seconds with cursor position preserved across refreshes.

#### Inline save for delegates (#905)
Replaced the hook-based save flow (`save-output.sh` → `emdx save` CLI → parse doc ID from stdout → temp batch file) with a direct `save_document()` call in Python, followed by post-save enrichment (title-match wikify, entity wikify, auto-link). Removed execution tracking — delegates no longer create empty execution rows with no log file or PID.

### 🔧 Improvements

- **Simplified TUI chrome** — help bars across all screens now use a consistent compact format with double-space separators instead of `│` pipes, and show essential hints only (#907)
- **Enter opens fullscreen preview** — Enter key on a document row now correctly opens the fullscreen document preview instead of being consumed by DataTable's built-in cursor action (#907)
- **Stronger delegate subtask tracking** — `prime.sh` now uses REQUIRED Progress Tracking with concrete `emdx task add` examples instead of a soft suggestion (#905)
- **Clickable PR links in delegate detail** — delegates that create PRs store the URL in the task description, rendered as a clickable link in the Delegate Browser (#905)

### 🐛 Bug Fixes

- **Doc link click no longer freezes TUI** — `action_select_doc` was async, but Textual dispatches `@click` meta actions synchronously; async DOM mutations during a click handler deadlocked the message loop. Made it sync with `run_worker` to defer navigation (#905)
- **Delegate tasks now visible under epics** — queries filtered by `parent_task_id IS NULL`, missing tasks nested under epics; changed to filter by `prompt IS NOT NULL` (#905)
- **Cursor preserved across delegate refreshes** — `table.clear()` was resetting cursor to row 0 on every 5s auto-refresh; now saves and restores the selected row key (#905)

### 🗑️ Removed

- **Q&A screen** — removed the Q&A TUI screen (key `3`), presenter, and 1,147 lines of tests. The 5s minimum latency floor from Claude CLI overhead made it impractical; `emdx find --ask` and Claude Code serve the use case better (#906)

[0.25.0]: https://github.com/arockwell/emdx/compare/v0.24.2...v0.25.0

## [0.24.2] - 2026-02-26

**Title columns fill available width.** The Docs and Tasks DataTable title columns now expand to fill horizontal space instead of auto-sizing to content width. Previously titles were double-truncated — once at the text level during populate (using a width calculated before layout finalized) and again by the column width constraint — leaving visible empty space on the right. Now full title text is stored in cells with `auto_width` disabled from mount, and column width syncs on every resize. This also eliminates the "pop-in" where titles would briefly appear truncated then expand.

### 🔧 Improvements

- **Title columns fill available space** — ActivityTable and TaskView DataTables now set explicit title column widths on mount and sync them on resize, replacing the previous auto-width behavior that left empty space (#902)
- **Updated demo GIF** — re-recorded at 900x700 (83 cols) for a clean narrow layout without sidebar

[0.24.2]: https://github.com/arockwell/emdx/compare/v0.24.1...v0.24.2

## [0.24.1] - 2026-02-26

**Clickable doc refs in the activity pane.** The `#42`-style document IDs in "Related:" sections are now clickable — clicking navigates directly to that document without remounting the widget tree, which previously broke mouse event routing.

### 🔧 Improvements

- **Clickable related doc refs** — `#N` document references in the activity detail pane's "Related:" section now render as clickable Rich Text. Clicking navigates in-place via `select_document_by_id()` instead of `switch_browser()`, avoiding widget tree destruction that broke mouse events (#900)

### 🐛 Bug Fixes

- **Title truncation test** — adapted `test_title_truncation` to dynamic width calculation introduced in #898 (#899)

[0.24.1]: https://github.com/arockwell/emdx/compare/v0.24.0...v0.24.1

## [0.24.0] - 2026-02-26

**Clickable URLs and adaptive layouts.** The TUI now renders URLs as clickable cyan links across all screens — click to open in your browser, or press Shift+O to open the first link from the selected item. The layout became responsive: a metadata sidebar appears at wide terminals (120+ cols) and collapses to inline content at narrow widths. Zoom got a three-state cycle (normal → content fullscreen → list fullscreen). On the CLI side, `delegate --task` and `--epic` now accept category-prefixed keys like `FEAT-77`, and delegates are prompted to create subtasks for progress visibility.

### 🚀 Major Features

#### Clickable URLs across all TUI screens (#893, Issue #875)
URLs in task descriptions, QA answers, log entries, and delegate output are now rendered as underlined cyan links. Clicking opens in the default browser via Textual's `@click` meta dispatch. Shift+O keyboard shortcut opens the first URL from the currently selected item. A shared `link_helpers.py` module provides `linkify_text()` and `extract_urls()` for consistent URL handling.

#### Adaptive sidebar layout (#894)
All TUI screens now have a responsive metadata sidebar that appears at 120+ column widths and collapses to inline content at narrower terminals. Document metadata surfaces knowledge graph links, timestamps, word count, and tags. Task metadata shows status badges, epic progress, dependencies, and execution info. The zoom key (`z`) now cycles through three states: normal split → content fullscreen → list fullscreen → back to normal.

### 🔧 Improvements

- **`delegate --task` accepts category keys** — `--task FEAT-77` and `--epic SEC-1` now resolve correctly instead of requiring raw database IDs. Added `TaskRef` type alias to document task identifier params throughout the codebase (#895)
- **Delegate subtask tracking** — delegates with a `--task` flag are now prompted to break work into 3-5 subtasks under the parent task, giving visibility into progress from the outside (#896)

[0.24.0]: https://github.com/arockwell/emdx/compare/v0.23.1...v0.24.0

## [0.23.1] - 2026-02-25

**TUI polish and delegate improvements.** The QA screen got a visual overhaul — answers now render in structured sections with metadata badges, and the history table shows timestamps, elapsed time, source counts, and retrieval method. Clickable `#N` document references now work in QA answers. The task list gained date filters, and delegates can now grant extra tool permissions.

### 🔧 Improvements

- **QA screen visual polish** — answer panel renders with `### ❓ Question`, `### 📚 Sources`, `### ✅ Answer` section headers and a footer badge line showing elapsed time, retrieval method, and source count. History table now has columns for time, elapsed, sources, and mode (#886, Issue #TUI-14)
- **Clickable doc refs in QA answers** — `#N` references in QA answers are now clickable, opening a fullscreen document preview (#887, Issue #FEAT-55)
- **`delegate --tool`** — grant extra tool permissions to delegates beyond the defaults (repeatable, e.g. `--tool 'Bash(gh:*)'`) (#878, Issue #869)
- **`task list --since` and `--today`** — filter completed tasks by date, useful for daily standups and progress reviews (#877, Issue #874)
- **Task work log as markdown** — work log entries in the task detail pane now render as markdown instead of plain text (#890)

### 🐛 Bug Fixes

- **QA answer panel rewrite** — replaced RichLog-based answer rendering with VerticalScroll+Markdown pattern, fixing sizing issues and improving scroll behavior (#885, Issue #844)
- **Zoom toggle regression** — `z` key now correctly unzooms on all three TUI screens. The bug was caused by Textual dropping focus when the DataTable was hidden (#884, Issue #TUI-35)
- **Unified task/epic ID resolution** — task commands now consistently resolve both numeric IDs and `CAT-N` keys, and `task epic attach` works correctly (#879, Issues #870-#873)
- **TUI long line wrapping** — pre-wrap long lines in detail panes to prevent terminal gutter corruption (#881, Issue #868)
- **Epic clustering in status view** — cross-group epic children now cluster correctly instead of appearing as orphans (#880, Issue #866)
- **Delegate stderr progress** — parallel delegates now emit `starting` and `done` progress lines to stderr, making execution visible even when stdout is buffered (#888, Issue #FIX-19)

[0.23.1]: https://github.com/arockwell/emdx/compare/v0.23.0...v0.23.1

## [0.23.0] - 2026-02-24

**The wiki quality release.** Seven GitHub issues closed in one session — the entire Wiki Quality & Workflow Improvements epic (FEAT-73). Topic clustering now produces readable labels instead of raw code identifiers, a new `wiki setup` command bootstraps the full pipeline in one shot, and `wiki triage` lets you bulk-skip or auto-label topics without 70+ individual commands. Generation got backpressure support and a progress dashboard.

### 🚀 Major Features

#### Wiki setup and triage workflow (#863, Issue #846)
The wiki bootstrap experience went from a 5-command sequence to one:

- **`wiki setup`** — runs the full bootstrap: build embedding index, extract entities, discover topics with auto-labeling, and show a summary. One command replaces `maintain index` → `maintain entities --all` → `wiki topics --save`.
- **`wiki triage`** — non-interactive batch cleanup for saved topics. `--skip-below 0.05` skips low-coherence clusters, `--auto-label` uses Claude CLI to generate human-readable names. Both flags compose.
- **`wiki topics --auto-label`** — when used with `--save`, passes discovered clusters through Claude CLI to generate topic names before persisting.

#### Wiki generation progress and backpressure (#859, #861, Issues #850, #851)
- **`wiki progress`** — new command showing generation status: topic counts, a color-coded progress bar, cost breakdown, and token usage. Supports `--json` for pipelines (#859).
- **`wiki generate --concurrency N`** — sequential processing by default (memory-efficient), with `-c N` for parallel generations. Per-topic streaming progress shows cost and timing as each article completes (#861).

#### TUI top/bottom split layout (#865)
All three TUI screens (Docs, Tasks, Q&A) switched from left/right to top/bottom split — detail panes now render at full terminal width for much better markdown readability. Press `z` to zoom the detail pane to 100% height (hiding the list), and `z` again to restore the split. `j`/`k` navigation still works while zoomed.

### 🔧 Improvements

- **Entity type filtering for topic clustering** — `wiki topics` now defaults to `heading` and `proper_noun` entities, excluding noisy `tech_term` code identifiers. Override with `-e tech_term` if needed. Also adds `--min-df` to prune singleton entities (#854, Issue #845)
- **`wiki export --topic <id>`** — export a single article instead of dumping all 50+ files every time (#858, Issue #849)
- **`task cat rename`** — rename or merge task categories (#856, Issue #842)
- **Task work log display** — TUI detail pane now shows work logs with better formatting (#857, Issue #852)
- **Typer 0.24.1** — dependency bump (#843)

### 🐛 Bug Fixes

- `wiki generate --dry-run` summary now shows correct article counts instead of "Estimated 0 articles (skipped N)" (#853, Issue #847)
- Wiki article timing columns (`prepare_ms`, `outline_ms`, etc.) now use float precision — sub-millisecond phases no longer truncate to 0 (#855, Issue #848)
- Release script changelog detection hardened with strict semver tag filtering (#860)

### 🧹 Maintenance

- Wire orphaned commands, delete dead `browse`/`review` modules (#839)
- Add non-interactive auto-confirm tests for all confirmation prompts (#862)

[0.23.0]: https://github.com/arockwell/emdx/compare/v0.22.1...v0.23.0

## [0.22.1] - 2026-02-23

**Cleanup and performance patch.** The TUI now launches instantly — the ~2.5s sentence-transformers import moved from app startup to QA screen load, where it runs in a background thread with a loading indicator. Six refactoring PRs removed ~2,400 lines of dead code and consolidated duplicated modules.

### ⚡ Performance

- Defer sentence-transformers import to QA screen load — TUI launches ~2.5s faster (#840)

### 🐛 Bug Fixes

- `--done` flag on `task list` now shows only done tasks instead of everything (#838)
- Fix release changelog script to auto-detect latest tag instead of showing all commits

### 🔧 Improvements

- Consolidate `UnifiedSearch` into `HybridSearch` — one canonical search service (#836)
- Fold `analyze.py` into `status --health`, delete redundant command (#835)
- Extract shared clustering module from explore/compact duplication (#834)
- Split `maintain.py` god file into `maintain` + `wiki` + `maintain_index` (#833)
- Delete dead `claude_executor.py` — zero callers (#831)
- Delete dead `commands/ask.py` — never registered, all features duplicated (#830)
- Add TUI demo GIF to README (#837)

[0.22.1]: https://github.com/arockwell/emdx/compare/v0.22.0...v0.22.1

## [0.22.0] - 2026-02-23

**The plugin + QA redesign release.** EMDX ships as a Claude Code plugin with a marketplace manifest, lifecycle hooks, and a setup skill. The QA screen was rebuilt from scratch — a left-side history panel replaces the old source panel, answers persist to the database across sessions, and clickable `#N` document references open fullscreen previews. The task browser's epic grouping got several fixes so standalone tasks no longer masquerade as epic children.

### 🚀 Major Features

#### Claude Code plugin system (#821, #823, #820)
EMDX is now installable as a Claude Code plugin. A `marketplace.json` manifest (#821) enables discovery, and two lifecycle hooks integrate with the Claude Code session:

- **SessionStart hook** (#823) — primes the session with ready tasks, in-progress work, and recent docs. Includes `/emdx:setup` skill for first-time plugin configuration.
- **SubagentStop hook** (#820) — auto-saves subagent output to the knowledge base when a delegate finishes, so nothing is lost when conversations end.

#### QA screen redesign (#828, #826)
The QA screen was rebuilt with a persistent history panel and inline sources:

- **History panel** — a left-side DataTable shows past Q&A exchanges. Navigate with `j`/`k`, and answers load instantly from the database.
- **Persistent Q&A** — every answer auto-saves as a `doc_type="qa"` document, surviving across sessions without cluttering search results or the activity screen.
- **Inline sources** — sources appear as clickable bulleted lists at the top and bottom of each answer. Clicking a `#N` reference opens the fullscreen `DocumentPreviewScreen` modal.
- **Shared markdown rendering** (#826) — the preview pane and fullscreen modal now share a single `render_markdown_to_richlog()` function, eliminating duplicate rendering code.

#### Streaming delegate output (#822)
Parallel delegate results now stream to stdout as each task completes, instead of waiting for all tasks to finish. You see progress immediately when running `emdx delegate "task1" "task2" "task3"`.

### 🐛 Bug Fixes

- Fix terminal corruption when sentence-transformers loads in a background thread — save/restore terminal state around threaded calls (#827)
- Hide fully-done epics in task browser epic group view (#825)
- Fix non-epic tasks showing tree connectors and epic group headers in epic view — tasks with `epic_key` but no `parent_task_id` now go to UNGROUPED (#829)
- Show `KEY-N` badge instead of `#id` for epics that have a sequence number (#829)

[0.22.0]: https://github.com/arockwell/emdx/compare/v0.21.0...v0.22.0

## [0.21.0] - 2026-02-22

**The auto-wiki release.** EMDX can now generate a full wiki from your knowledge base — topic clustering groups documents by theme, an LLM synthesizes each cluster into a polished article, and the whole thing exports to MkDocs for static site hosting. A suite of curation commands (`skip`, `pin`, `rename`, `merge`, `split`) lets you shape topics before generation, and per-topic controls let you override models, inject editorial prompts, and weight source documents. The TUI gained two-pane QA with source references, epic-child tree connectors in the task browser, and streaming answer tokens.

### 🚀 Major Features

#### Auto-wiki system (#773, #774, #775)
The auto-wiki pipeline turns your knowledge base into a structured wiki in three steps:

1. **Topic clustering** — documents are grouped into coherent topics using embedding similarity, with privacy filtering to exclude sensitive content.
2. **LLM synthesis** — each topic cluster is fed to an LLM that writes a wiki article, citing source documents.
3. **Wiki runs** — `emdx wiki runs` tracks generation history with per-article timing, quality ratings, and diffs on regeneration.

A new `doc_type` column (`kb` vs `wiki`) separates wiki articles from source documents in search and browsing (#774). `emdx find --doc-type wiki` filters to wiki content only (#783), and the TUI browser shows doc type badges (#778).

#### Wiki topic curation (#795, #796, #798, #797, #804, #805)
Six new commands give you full control over topics before generating articles:

- **`wiki topic skip/pin`** (#796) — exclude topics from generation or lock them in.
- **`wiki topic rename`** (#795) — change a topic's display name.
- **`wiki topic merge/split`** (#804) — combine related topics or break apart overly broad ones.
- **`wiki source weight/exclude/include`** (#805) — control which documents contribute to each topic and how much.
- **Editorial prompts** (#798) — inject per-topic instructions like "focus on architecture decisions" that guide the LLM during generation.
- **Per-topic model override** (#797) — use a different model for specific topics (e.g., opus for the overview article, haiku for appendices).

#### Wiki observability (#786, #787, #788, #789)
Instrumentation to understand what the wiki pipeline is doing:

- **Coverage report** (#786) — `emdx wiki coverage` shows which KB documents aren't covered by any topic.
- **Article diffs** (#787) — regenerating a topic shows what changed from the previous version.
- **Step-level timing** (#788) — each article records how long clustering, retrieval, and synthesis took.
- **Quality ratings** (#789) — rate articles 1–5 to track which topics need attention.

#### MkDocs wiki export (#807, #815)
`emdx wiki export` dumps all wiki articles and entity pages into a directory structure ready for MkDocs. Generates `mkdocs.yml` with a nav tree built from topic clusters, and can build or deploy to GitHub Pages.

New in #815: `--remote` deploys to a separate repo's gh-pages (so your work wiki doesn't push to your source repo). `--init-repo` bootstraps the output dir as a git repo — combine with `--github-repo` to create a private GitHub repo in one shot. `--site-url` and `--repo-url` configure the generated `mkdocs.yml` for custom domains and edit links.

#### TUI epic/task display improvements (#799)
The task browser now shows the relationship between epics and their child tasks visually:

- **📋 icon and `#id` badge** on epic rows to distinguish them from regular tasks.
- **Tree connectors** (`├─` / `└─`) on child tasks showing they belong to the epic above.
- **Epic detail pane** with progress bar, done/open/total counts, and child task listing.
- **`e` key** to filter the view to a single epic, `*` to clear all filters.
- Consistent visual treatment across both status grouping (default) and epic grouping (`g` key) modes.

#### Two-pane QA with source panel (#806, #808)
The QA screen gained a right-side source panel. When an answer references a KB document, clicking or navigating to the reference shows the source content alongside the answer. Document references are clickable — selecting one loads the source document into the panel (#808). Answers stream token-by-token for real-time feedback (#785).

### 🔧 Improvements

#### Delegate improvements (#777, #780, #784, #790, #792, #794)
- **`--task` flag** (#780) — `emdx delegate --task 42 "do the work"` associates a delegate session with a task, auto-updating its status on completion.
- **Subcommand routing** (#777) — `emdx delegate list` and `emdx delegate show` now work correctly instead of being swallowed as task arguments.
- **Command aliases** (#790) — common commands have short aliases via Click's `get_command()` pattern.
- **Epic IDs in PR titles** (#784) — delegate-created PRs include the epic identifier when the task belongs to one.
- **AllowedTools fix** (#792) — switched to comma-separated `--allowedTools` so patterns with spaces (like `Bash(gh pr:*)`) parse correctly.
- Removed premature `--limit` flag (#794) that shipped before the backing query was ready.

#### CLI cleanup (#781, #782)
- **Removed recipe feature** (#782) — the experiment didn't stick; recipes were removed entirely to reduce surface area.
- **Folded `stale` into `maintain`** (#781) — `emdx maintain stale` replaces the top-level `stale` command, continuing the consolidation from v0.19.

#### Wiki topic auto-retitling (#814)
When an article is generated, its H1 heading is often a better title than the original cluster label. Topic titles now auto-update from the article's H1 on generation, keeping navigation and search in sync with the actual content.

#### Dead code removal (#809, #811, #812, #813)
Four cleanup PRs removed ~1,900 lines of dead code across `config/`, `models/`, `database/`, `services/`, and `utils/` — unused constants, orphaned functions, and vestigial services left behind by earlier refactors.

#### Epic sequence numbers (#776)
Epics now get `KEY-N` sequence numbers just like tasks. The first `FEAT` epic is `FEAT-1`, the second `FEAT-2`, etc.

### 🐛 Bug Fixes

- Fix `_epics` dict keyed by category string instead of epic task ID, causing all epics to appear "done" when multiple shared the same category (#799)
- Hide done/failed/wontdo tasks from epic grouping in task browser (#793)
- Fix `--allowedTools` parsing so `Bash(gh:*)` works in delegate subprocess (#792)
- Fix delegate subcommand routing — `delegate list` no longer treated as a task argument (#777)
- Pass `--allowedTools` to delegate subprocess so `--pr` flag works
- Remove premature `--limit` flag that was wired to a non-existent query (#794)

### 📖 Documentation

- Full CLI reference update — added missing commands, removed stale group system docs (#800, #802, #803)
- Added `explore` command documentation (#802)
- Updated development-setup.md with current paths and deps (#801)
- Updated architecture.md for v0.20.0 TUI changes
- Added task `wontdo`, priority, and KEY-N display ID docs (#DOC-6)
- Documented `--json` flag for delegate (#DOC-7)
- Updated TUI keyboard shortcuts (#DOC-8)
- Documented `maintain.auto_link_on_save` config (#DOC-10)

[0.21.0]: https://github.com/arockwell/emdx/compare/v0.20.0...v0.21.0

## [0.20.0] - 2026-02-22

**The TUI release.** The activity screen became a unified dashboard — tasks, running delegates, and documents share a single tiered view with section jump navigation. The task browser gained live filtering, epic grouping, and status filter keys. Auto-wikify shipped all three layers, automatically linking documents by title matches, semantic similarity, and named entity extraction. Under the hood, Claude Code hooks replaced the delegate monolith's lifecycle management, and `emdx delegate` got structured JSON output for programmatic consumption.

### 🚀 Major Features

#### Unified activity dashboard (#759)
The activity screen was rebuilt as a three-tier dashboard. Running executions sit at the top, active/open tasks in the middle, and completed documents at the bottom. Section headers (RUNNING / TASKS / DOCS) divide the tiers, and `shift+R`/`shift+T`/`shift+D` jump directly to each section, scrolling the header to the top of the screen. Tasks with matching execution or output document IDs are deduplicated so nothing shows up twice.

#### Auto-wikify — three-layer document linking (#748, #749, #751)
Documents now self-organize into a knowledge graph through three complementary strategies:

- **Layer 1 — Title match** (#748): Scans document text for exact title mentions and creates links. Fast and precise.
- **Layer 2 — Semantic similarity** (#749): Uses embedding similarity to surface non-obvious connections. Runs automatically on `emdx save` by default, configurable via `maintain.auto_link_on_save`.
- **Layer 3 — Entity extraction** (#751): Extracts named entities (people, projects, tools) from documents and links those sharing entities. Adds entity-based metadata for richer graph traversal.

#### Claude Code hooks (#746, #747)
The delegate lifecycle shifted from a monolithic executor to three Claude Code hooks:

- `prime.sh` (SessionStart) — injects KB context into every session automatically
- `save-output.sh` (Stop) — auto-saves delegate output to the KB
- `session-end.sh` (SessionEnd) — updates task status on completion

Hooks are ambient — `prime.sh` runs for all sessions, the others only activate when delegate sets env vars. Human sessions are unaffected.

#### Task browser TUI overhaul (#745, #755, #757)
The task browser got three rounds of upgrades:

- **Live filter bar** (#755): Type to filter tasks in real-time with `shift+/`, matching against title, status, and category.
- **Epic grouping** (#757): `shift+G` toggles grouping tasks by epic. Status filter keys (`o`/`a`/`d`/`f`) cycle through task states.
- **Foundation** (#745): Rich detail pane, dependency visualization, vim-style navigation, and direct task status actions.

### 🔧 Improvements

#### QA presenter extraction (#765)
QA screen internals were refactored to separate the presenter (answer formatting, source rendering) from the screen widget, making the Q&A pipeline testable without mounting a full TUI.

#### Structured delegate output (#761)
`emdx delegate --json` outputs structured JSON with `task_id`, `doc_id`, `exit_code`, `duration`, and `execution_id`. Without `--json`, a clean summary line prints to stderr: `delegate: done task_id:42 doc_id:100 exit:0 duration:3m12s`. The `--help` output was reorganized into grouped panels (Git & PRs, Organization).

#### Task management additions (#762, #763, #764)
- **`wontdo` status** (#762): Discard tasks without marking them done — `emdx task wontdo 42`.
- **`task priority`** (#763): Set task priority with `emdx task priority 42 1` and a new `/emdx:prioritize` skill for bulk triage.
- **Display IDs** (#764): Task command output shows `KEY-N` prefixed IDs (e.g., `FEAT-12`) when a category is assigned.

#### Context-aware prime (#750)
`emdx prime` detects whether it's running in a delegate session (via `EMDX_TASK_ID`) or a human session and adjusts its output — delegates get focused task context, humans get the full ready-tasks overview.

### 🐛 Bug Fixes

- Auto-confirm destructive commands (`delete`, `restore`) when stdin is not a TTY, fixing delegate sessions that would hang waiting for confirmation (#754)
- Strip `CLAUDECODE` env var from delegate subprocess environment so spawned `claude` processes don't inherit stale state (#747)
- Strip ANSI codes from `emdx save` output before parsing doc ID, fixing delegate save failures in colored terminals (#747)
- Remove priority indicator column from task browser that was taking space without adding value (#756)

### 📖 Documentation

- Restructured CLAUDE.md with separate human vs delegate session guidance (#752)
- ActivityTable widget test suite — 22 pilot-based tests (#758)

[0.20.0]: https://github.com/arockwell/emdx/compare/v0.19.0...v0.20.0

## [0.19.0] - 2026-02-21

**The consolidation release.** EMDX's CLI surface shrank from ~30 commands to 19, folding related commands under unified namespaces (`briefing` absorbed `wrapup` and `activity`, `find` absorbed `recent`, `maintain` absorbed `compact` and `stale`). Task management gained dependency tracking — tasks can now block each other, and `chain` wires up sequential pipelines in one shot. Category-prefixed IDs (`FEAT-12`, `FIX-7`) work everywhere task IDs are accepted. The activity screen got a flat-table redesign, and EMDX shipped as a Claude Code skills plugin.

### 🚀 Major Features

#### CLI consolidation — ~30 commands to 19 (#731)
Related commands were folded under shared namespaces to reduce cognitive overhead:

```bash
# Before → After
emdx wrapup        → emdx briefing --save
emdx activity      → emdx briefing
emdx recent        → emdx find --recent
emdx compact       → emdx maintain compact
emdx stale         → emdx maintain stale
emdx distill       → emdx maintain distill
```

Commands that moved are gone — no aliases. The `maintain` group houses all KB housekeeping. `briefing` owns both interactive and saved summaries.

#### Task dependencies (#735, #736)
Tasks can now express ordering constraints. A task blocked by another won't appear in `task ready` until its dependency completes:

```bash
emdx task dep add 12 7          # Task 12 depends on task 7
emdx task dep list 12           # Show what blocks task 12
emdx task dep rm 12 7           # Remove dependency
emdx task chain 1 2 3 4         # Wire up: 1→2→3→4 (each blocks the next)
```

Dependencies surface in `task list`, `task ready`, and the TUI.

#### Category-prefixed IDs (#720, #736)
Task IDs can now be written as `FEAT-12` or `FIX-7` instead of bare numbers. Prefixed IDs work everywhere — `task done FEAT-12`, `task dep add FEAT-12 FIX-7`, `task view ARCH-3`. The prefix is validated against assigned categories.

### 🔧 Improvements

#### Claude Code skills plugin (#727)
EMDX ships as a Claude Code skills plugin. Drop `emdx` into your `~/.claude/plugins/` and get `/emdx:save`, `/emdx:research`, `/emdx:wrapup` skills inside Claude Code sessions.

#### Activity screen redesign (#730)
The TUI activity screen was redesigned from a grouped layout to a flat table, making it easier to scan recent executions at a glance.

### 🐛 Bug Fixes

- Prevent `emdx save --file` from hanging on non-TTY stdin (#732, #733)
- Fix CI test failure from ANSI codes in typer help output (#740)
- Update plugin skills to match post-consolidation CLI (#741)
- Fix briefing.py mypy errors from untyped activity dict (#740)

### 📖 Documentation
- Auto-wikify design document (#739)
- Task TUI research findings and recommendations (#738)
- QA screen improvement plan (#737)
- README version badge update (#729)

### 💥 Breaking Changes

#### CLI commands removed/moved (#731)
The following top-level commands no longer exist:

| Removed | Replacement |
|---------|-------------|
| `emdx wrapup` | `emdx briefing --save` |
| `emdx activity` | `emdx briefing` |
| `emdx recent` | `emdx find --recent` |
| `emdx compact` | `emdx maintain compact` |
| `emdx stale` | `emdx maintain stale` |
| `emdx distill` | `emdx maintain distill` |

## [0.18.0] - 2026-02-20

**The knowledge graph release.** EMDX gained the ability to discover connections between documents automatically — save a document and it finds related ones, building a self-organizing knowledge graph. Search got smarter with Reciprocal Rank Fusion replacing the old weighted-average hybrid scoring. A new `explore` command maps the KB's topic landscape, showing coverage depth and gaps. On the CLI side, `emdx save` was simplified — the positional argument is now always content (no more path-guessing), and delegate gained `--sonnet`/`--opus` shortcuts with automatic model tagging.

### 🚀 Major Features

#### Auto-linking — self-organizing knowledge graph (#577, #725)
Documents now automatically discover related content. When you save a document with `--auto-link`, EMDX uses semantic similarity to find and link related documents, building a navigable knowledge graph:

```bash
emdx save --file notes.md --auto-link     # Save and auto-link to similar docs
emdx ai links 42                           # Explore connections (--depth 2 for 2 hops)
emdx ai link 42                            # Create links for existing doc (--all to backfill)
emdx ai unlink 42 57                       # Remove a link
emdx view 42                               # Related docs shown in header
```

Backed by a new `document_links` table (migration 043) with bidirectional links and similarity scores. Links surface in `emdx view` headers automatically.

#### Reciprocal Rank Fusion for hybrid search (#578, #724)
Hybrid search (keyword + semantic) now uses Reciprocal Rank Fusion instead of a weighted average. RRF merges ranked lists using `RRF(d) = Σ 1/(k + rank_i(d))`, producing better relevance when combining FTS5 BM25 keyword scores with chunk-level embedding scores. Also adds min-max normalization for FTS5 scores and preserves both `keyword_score` and `semantic_score` on results for observability.

#### `emdx explore` — KB topic discovery (#716)
Maps the knowledge base by clustering documents using TF-IDF content similarity:

```bash
emdx explore                    # Topic map with cluster labels, doc counts, freshness
emdx explore --gaps             # Coverage gap detection (thin topics, stale areas)
emdx explore --questions        # LLM-generated answerable questions per topic
emdx explore --json             # Structured output for agents
```

Lazy-loads sklearn only when invoked. 21 tests.

### 🔧 Improvements

#### Model shortcuts and tagging for delegate (#717)
New `--sonnet` and `--opus` flags as shortcuts for `--model sonnet` and `--model opus`. Documents created by delegate are automatically tagged with `model:<name>` (e.g., `model:opus`) recording which model produced them.

#### `emdx task cat delete` and `emdx task epic delete` (#722)
Delete commands for categories and epics. Both refuse to delete when open tasks exist unless `--force` is used. Tasks are unlinked (not deleted) when their parent is removed.

#### Delegate prompts piped via stdin (#718)
Delegate now pipes task prompts through stdin instead of CLI arguments, fixing issues with very long prompts that exceeded OS argument limits.

### 🐛 Bug Fixes

- Demote hybrid search fallback warnings to debug level (#708)
- Fix delegate save instruction to use `--file` flag (#721)
- Fix `mypy` `no-any-return` in `get_link_count` (#725)

### 📖 Documentation
- Reworked README around Save/Delegate/Track narrative structure (#713, #726)
- Bundled all dependencies into the main install (#726)

### 💥 Breaking Changes

#### `emdx save` positional argument is always content (#714, #721)
Previously, `emdx save "text"` would check if `"text"` was a file path first, causing crashes on long strings (#714) and confusing agents. Now:

```bash
emdx save "content"             # positional = always content
emdx save --file document.md    # explicit file read (new --file/-f flag)
echo "x" | emdx save            # stdin still works
```

## [0.17.0] - 2026-02-17

**The simplification release.** EMDX dropped the emoji alias system entirely — tags are now plain text, with a migration to convert existing emoji tags. The `--each/--do` dynamic discovery feature was removed from delegate. The Q&A screen got a ground-up rewrite fixing terminal corruption. Task management tightened — `epic` and `cat` commands moved under `emdx task`, and `db.ensure_schema()` was centralized into a single app callback. Textual upgraded to v8.0, and the TUI gained its first pilot-based test suite (36 tests).

### 🔧 Improvements

#### Q&A screen rewrite (#694)
The TUI Q&A screen was rewritten to fix terminal corruption caused by importing torch/sentence-transformers in background threads. The new implementation runs Claude CLI directly via `subprocess.Popen`, bypassing `UnifiedExecutor`. Terminal state is saved/restored around `asyncio.to_thread` calls as a safety net. Also adds: Escape to cancel in-flight questions, progress indicators with timing, markdown rendering for answers, and conversation survival across screen switches.

#### Pilot-based TUI tests (#702)
First comprehensive test suite for the TUI using Textual's Pilot API — 36 tests covering rendering, keyboard navigation, detail pane content, mouse interaction, screen switching, and edge cases. Establishes reusable patterns (factories, fixtures, assertion helpers) for testing other TUI screens.

#### Textual 8.0 upgrade (#692)
Updated from Textual ^7.5.0 to ^8.0.0. The major version bump in Textual was primarily a `Select.BLANK` → `Select.NULL` rename.

#### Typing improvements (#697, #698, #701)
Added `ExecutionResultDict` TypedDict for `ExecutionResult.to_dict()` return values, replacing `dict[str, Any]`. Fixed duplicate TypedDict definition that crept in during parallel development.

#### Centralized `db.ensure_schema()` (#693)
Moved `db.ensure_schema()` from 23+ scattered calls in individual command files to a single call in the main app callback. Net -242 lines across 18 files.

#### Cleanup
- Added missing `__all__` exports to `emdx/services/__init__.py` (#688)
- Removed remaining Cursor IDE references and dead code (#689)

### 📖 Documentation
- Rewrote README and updated project positioning (#690)
- Clarified task vs document organization in CLAUDE.md (#691)
- Streamlined README — removed legend, dynamic discovery, consolidated sections (#704)
- Removed emoji alias references from documentation (#706)

### 💥 Breaking Changes

#### Emoji alias system removed (#707)
The entire emoji alias system (`emoji_aliases.py`, 284 lines) has been removed. Tags are now plain text everywhere. A database migration (042) automatically converts existing emoji tags to their text equivalents (e.g., `🎯` → `gameplan`, `🚀` → `active`), merging duplicates where both forms exist.

#### `--each/--do` removed from delegate (#705)
The dynamic discovery feature (`emdx delegate --each "cmd" --do "template"`) has been removed. Use explicit task lists instead.

#### `emdx cat` and `emdx epic` moved under `emdx task` (#700)
Categories and epics are task-specific concepts and now live under the task namespace:

```bash
# Old
emdx cat list
emdx epic list

# New
emdx task cat list
emdx task epic list
```

## [0.16.0] - 2026-02-16

**The cleanup release.** EMDX shed its last API key dependency and removed the cascade system entirely (~5,500 lines) — everything now runs through the Claude CLI. New session-aware commands (`wrapup`, git-enriched `prime`, `save --task`) help agents and humans track what happened. The Q&A system got a conversational TUI redesign and tag/recent filters. Under the hood, type safety tightened with Protocols, TypedDicts, and concrete generics.

### 🚀 Major Features

#### `emdx wrapup` — session summaries (#664)
End-of-session command that gathers recent tasks, documents, and delegate executions from a configurable time window and synthesizes them into a coherent summary:

```bash
emdx wrapup                    # Summarize last 4 hours
emdx wrapup --hours 8          # Wider window
emdx wrapup --dry-run          # Preview what would be summarized
emdx wrapup --json             # Raw activity data without synthesis
```

Summaries are auto-saved with `session-summary,active` tags.

#### Structured multi-step recipes
Recipes gained frontmatter and step-by-step execution. Write a recipe as a markdown document with YAML frontmatter defining steps, then run it — each step executes in sequence through delegate:

```bash
emdx recipe run <id>           # Execute a multi-step recipe
```

#### Conversational Q&A in TUI (#650)
The TUI search screen (position 3) was redesigned as a conversational Q&A interface. Type natural-language questions, get streaming answers from Claude with source citations. Supports saving exchanges to the KB and clearing conversation history.

#### `ask` command upgraded (#648, #661)
- **Tag and recent filters** — `--tags` and `--recent` narrow the document set before retrieval (#648)
- **Enhanced output** — source titles in citations, confidence indicator, context budget enforcement
- **Claude CLI backend** — replaced the Anthropic Python SDK with Claude CLI, removing the last `anthropic` package dependency (#661)

### 🔧 Improvements

#### `emdx prime` with git context (#647)
`emdx prime` now includes current branch, recent commits, and open PRs. Verbose mode shows most-accessed documents (key docs).

#### `emdx save --task` and `--done` (#649)
Link saved documents to tasks at save time, closing the task-to-document gap:

```bash
emdx save findings.md --task 42          # Link as task output
emdx save findings.md --task 42 --done   # Link + mark task done
```

#### Anthropic SDK fully removed (#661)
The `ask` service and TUI Q&A presenter were the last consumers of the `anthropic` Python package. Both now use the Claude CLI via `UnifiedExecutor`, matching `delegate`, `compact`, and `distill`. No API key needed — just a Claude CLI installation.

#### Copy mode for document previews (#682)
Toggle copy mode in the preview pane to select and copy text from document previews.

#### Typing hardening (Phases 1–5)
A comprehensive multi-phase refactor replacing `dict[str, Any]` with concrete TypedDicts across the entire codebase:
- **Protocols** for UI callbacks — type-safe event handling without concrete coupling (#646)
- **TypedDicts** across compact, distill, unified search, and UI layers — replacing `dict[str, Any]` with named shapes
- **Concrete generics** — `App[None]`, `Queue[str | None]`, `ModalScreen[str]`, reducing strict mypy `type-arg` errors from 64 to 51 (#671)
- **Services layer** — TypedDicts for execution, log streaming, synthesis, and hybrid search results (#678)
- **Ask service** — concrete return types replacing `dict[str, Any]` in ask_service.py (#679)
- **Commands layer** — TypedDicts for browse, groups, tags, stale, and task commands (#681)
- **CLI executor** — `StreamMessage` union type (6 TypedDicts) for stream-json parsing, `EnvironmentInfo` for validation; `parse_stream_line()` now handles all message types (#684)

#### Dead code removal
- **VimEditor and vim_line_numbers** — removed unused VimEditor class and related dead code (#680)
- **CursorCliExecutor** — removed entire Cursor CLI executor and all Cursor references (unused dead code, -271 lines) (#684)

#### Stream refactor (#684)
`format_stream_line()` in `unified_executor.py` previously re-parsed JSON inline. Replaced with `format_stream_message()` that accepts pre-parsed `StreamMessage` dicts from `parse_stream_line()`, eliminating duplicated `json.loads` calls.

#### Q&A screen renamed (#683)
The TUI search browser (screen position 3) renamed from "Search" to "Q&A" to better reflect its conversational purpose. Screen-switching keybindings centralized.

#### Activity view improvements
- Execution output text persisted to database for richer preview display
- Completed executions that produced a document are hidden from Activity (reduces noise)
- Completed cascade-stage duplicates hidden (#646)

#### TUI interaction fix (#653)
Single-click now highlights items; double-click opens fullscreen — fixing the previous behavior where any click triggered fullscreen navigation.

### 🐛 Bug Fixes
- **qa**: FTS query used `documents_fts` as a column instead of JOINing the virtual table — Q&A silently returned 0 sources (#672)
- **typing**: `TYPE_CHECKING` guards added for optional dependencies to prevent import-time crashes
- **cli**: Typer type mismatches fixed, dead code removed
- **recipes**: mypy errors in recipe parser and command resolved; git worktree mocked in recipe executor tests
- **activity**: Broadened execution query to include all non-cascade executions (was filtering too aggressively)

### 📖 Documentation
- Added delegate debugging guide and batch-delegate command docs (#675)
- Added FTS5 virtual table query gotcha to CLAUDE.md (#677)
- Added test mock gotcha to CLAUDE.md (#674)

### 💥 Breaking Changes

#### Cursor CLI executor removed (#684)
The `CursorCliExecutor` and all Cursor-related configuration have been removed. Only the Claude CLI is supported. If you were using `EMDX_CLI_TOOL=cursor`, switch to `claude` (the default).

#### Cascade system removed (#651)
The cascade pipeline (`emdx cascade` commands) and the `--chain` flag on `emdx delegate` have been removed (~5,500 lines). The recipe system provides a simpler, more flexible alternative.

**Removed:**
- `emdx cascade` command group (new, list, advance, auto, status)
- `--chain` flag from `emdx delegate`
- Cascade-related database tables and TUI screens

**Migration:** Use the recipe system instead:
```bash
# Old: emdx cascade new "idea" --auto
# New: Save instructions as a recipe, run with delegate
echo "Your multi-step instructions..." | emdx save --title "My Workflow" --tags recipe
emdx recipe run <id>
```

#### `anthropic` package no longer used anywhere
The optional `[ai]` extra no longer includes the `anthropic` package. All AI features use the Claude CLI.

## [0.15.0] - 2026-02-15

**The intelligence release.** EMDX gained the ability to synthesize its own knowledge base — compact duplicates, distill topics for different audiences, and search semantically across chunks. The delegate command grew new modes for branch-only workflows and draft PRs. Under the hood, 2,800+ lint and type errors were resolved, the TUI was reorganized, and the document browser was replaced by a focused task browser.

### 🚀 Major Features

#### `emdx compact` — AI-powered document deduplication (#621, #631)
Finds clusters of similar documents using TF-IDF similarity and merges them into single coherent documents via Claude. Originals are tagged `superseded` (not deleted). Works in discovery mode or with explicit doc IDs:

```bash
emdx compact --dry-run                    # Show clusters without merging
emdx compact --dry-run --threshold 0.7    # Tighter similarity threshold
emdx compact 32 33                        # Merge specific documents
emdx compact --auto                       # Merge all discovered clusters
emdx compact --topic "delegate"           # Only cluster docs matching a topic
```

Documents tagged `superseded` are automatically excluded from future clustering. The synthesis runs through the Claude CLI (same auth as `delegate`) — no `ANTHROPIC_API_KEY` needed.

#### `emdx distill` — audience-aware KB synthesis (#618, #631)
Searches the knowledge base and synthesizes matching documents into a coherent summary, tailored for a specific audience:

```bash
emdx distill "authentication"                    # Personal summary (default)
emdx distill --for docs "API design"             # Documentation style
emdx distill --for coworkers "sprint progress"   # Team briefing
emdx distill --tags "security,active" --save     # Save result to KB
```

Three audience modes — `me` (dense, technical), `docs` (formal documentation), `coworkers` (accessible team briefing) — each with distinct prompting.

#### Hybrid search with semantic matching (#604)
`emdx find` now supports chunk-level semantic search alongside the existing full-text search:

```bash
emdx find "concept" --mode semantic    # Conceptual/semantic search
emdx find "query" --extract            # Extract key info from results
```

Documents are split into chunks and indexed with sentence-transformer embeddings. Semantic mode finds conceptually related content even when keywords don't match.

#### `emdx review` and `emdx briefing` (#597, #600)
Two new commands for staying on top of agent activity:
- **`emdx review`** — Triage agent outputs: review, approve, tag, or dismiss delegate results
- **`emdx briefing`** — Generate an activity summary of recent delegate work

#### Knowledge decay — stale docs and `touch` (#583)
Documents now track freshness. `emdx maintain stale list` identifies documents that haven't been accessed recently. `emdx maintain stale touch <id>` marks a document as still relevant, resetting its decay clock.

#### Task system overhaul (#576, #582, #609)
Tasks gained structure and visibility:
- **Categories and epics** — organize tasks into larger units of work (#576)
- **Introspection commands** — `task view`, `task active`, `task log`, `task note`, `task blocked` (#582)
- **Grouped list output** — tasks display in sections with age and blocker info (#609)

### 🔧 Improvements

#### Delegate enhancements (#596, #601, #623, #629, #631)
- **`--draft` flag** — Create draft PRs by default for safety; `--no-draft` for ready-to-review (#601)
- **`--branch` flag** — Push-only mode without PR creation; `-b` alias for `--base-branch` (#623)
- **Structured PR instructions** — Parallel `--pr` tasks get proper summaries (#596)
- **Auto-save fallback** — File-based output fallback when agents skip `emdx save` (#610, #622)
- **Worktree cleanup** — `--cleanup` flag, worktrees always cleaned up after execution (#624, #629)
- **Synthesis uses Claude CLI** — `compact` and `distill` use the same auth path as `delegate`, no API key required (#631)
- **`--synthesize` resilience** — synthesis no longer fails if one agent in a parallel batch errors; partial results are still combined (#634)
- **Unified branch naming** — delegate-created branches now follow `delegate/{slug}-{hash}` pattern instead of inconsistent prefixes; PR validation checks for commits and pushed changes before creating PRs (#637)

#### TUI reorganization (#626)
- Screens reordered: **1=Activity, 2=Tasks, 3=Search, 4=Cascade**
- Document browser replaced by a focused **task browser** with grouped status view and detail pane
- ~2,100 lines of dead UI code removed (document browser, preview manager, presenters, viewmodels)

#### `emdx view` output modes (#625)
- Default output is now **plain text** (no Rich formatting) — pipes cleanly to other tools
- `--rich` flag for formatted terminal output
- `--json` flag for structured output
- Systematic `--json` support added across multiple CLI commands (#595)

#### Code quality blitz
- **2,343 ruff lint errors** resolved across the entire codebase (#581, #586)
- **528 mypy type errors** resolved — full strict type checking (#588)
- **Pre-commit hooks** added: ruff lint, ruff format, mypy on staged files (#585)
- **TypedDict definitions** added across database, models, groups, and cascade layers (#602, #603, #606, #607)
- **CI expanded** — lint, type-check, and multi-Python test matrix (#515)

#### Test coverage: 780 → 1,170+ tests
- Comprehensive tests for task commands, cascade, delegate, execution system, and async UI (#528, #534, #542, #543, #557)
- Weak assertions tightened (#533), test sleeps reduced (#531)
- Foreign key handling consolidated (#532)

#### Dependency upgrades
- **Textual** 4.x → 6.2.x (#587)
- **numpy** 1.26 → 2.4, **sentence-transformers** 3.x → 5.x, **typer** 0.15 → 0.23 (#547, #552, #554, #608)
- Dependabot and Renovate configured for automated updates (#523)
- Release automation workflow added (#527)

### 🐛 Bug Fixes
- **security**: Command injection in `--each` flag patched (#518)
- **db**: SQL injection prevention, atomicity fixes, null checks (#594)
- **similarity**: Pickle replaced with safe JSON serialization in cache (#592)
- **ui**: Race conditions in document browser and search presenter (#591)
- **cascade**: Stage update race condition (#589)
- **migrations**: Rollback handling and UnboundLocalError (#590)
- **delegate**: Flag-as-task parsing bug (#580), auto-save when agent skips `emdx save` (#610)
- **delegate**: Draft default mismatch between CLI and internal functions (#615)
- **db**: Foreign key cascade on 6 tables, LOWER(title) index (#520)
- **deps**: Missing pyyaml dependency (#475)
- **delegate**: Replace `select.select()` with threaded reader for macOS pipe reliability (#632)

### 💥 Breaking Changes
- **Document browser removed** — replaced by task browser. Screen 2 is now Tasks, not Documents (#626)
- **`emdx view` default changed** — output is plain text by default. Use `--rich` for formatted output (#625)
- **`anthropic` SDK no longer required** for `compact`/`distill` — uses Claude CLI instead (#631)

## [0.14.0] - 2026-02-13

**The simplification release.** EMDX went from 6 execution commands and a complex workflow engine down to one command that does everything: `emdx delegate`. The codebase shed ~15,000 lines of dead code while gaining 250 new tests. Every doc, every help string, every architecture diagram has been rewritten to match reality.

### 🚀 Major Features

#### Recipes replace workflows (#444)
The workflow orchestration engine — with its presets, stage runs, individual runs, and 5-table DB schema — has been replaced by **recipes**: plain markdown documents tagged with 📋. A recipe is just a saved set of instructions that `emdx delegate` follows. Same power, zero complexity.

```bash
# Old way: configure workflow preset, run workflow, monitor stages
emdx workflow create "Security Audit" --stages analyze,report
emdx workflow run 1

# New way: save instructions once, run them anywhere
echo "Run a security audit..." | emdx save --title "Security Audit" --tags recipe
emdx recipe run 42
```

#### `emdx delegate` — one command for all AI execution (#427, #445, #455, #458)
Six separate execution commands (`agent`, `run`, `each`, `workflow run`, `claude execute`, `task run`) have been consolidated into `emdx delegate`. Everything composes:

- **Parallel execution** — `emdx delegate "task1" "task2" "task3"` runs up to 10 concurrent tasks
- **Doc IDs as tasks** — `emdx delegate 42 43 44` loads doc content and executes each (#455)
- **Worktree isolation** — `--worktree` gives each parallel task a clean git environment (#445)
- **PR creation** — `--pr` creates branches and PRs; implies `--worktree` automatically (#458)
- **Sequential chains** — `--chain` pipes output from one step to the next
- **Dynamic discovery** — `--each "fd -e py" --do "Review {{item}}"` finds items and processes each
- **Auto branch names** — doc IDs with `--pr` generate branch names from document titles (#455)

#### Simplified command surface (#438, #440)
Commands have been reorganized into logical groups:
- `emdx trash list/restore/purge` — trash management as a subcommand group
- `emdx maintain cleanup/analyze` — maintenance tools nested under one parent
- `emdx task add/ready/done/list/delete` — streamlined agent work queue (#459)
- Tag commands consolidated under `emdx tag` with shorthand support (`emdx tag 42 active`)

#### Activity browser: proper delegate tracking (#470)
The activity browser now correctly displays delegate execution results. Executions link to their output documents (instead of showing raw logs), and token usage and cost metrics are persisted to the database and visible in the activity view.

### 🔧 Improvements

#### Leaner dependency tree (#436, #468)
- Dropped `gitpython` and `PyGithub` — git operations use subprocess, GitHub uses `gh` CLI
- Removed `gdoc` and `similar` commands and their heavy optional dependencies
- Core install pulls in fewer packages for faster `pip install`

#### Documentation rewritten from scratch
Every documentation file has been updated to match the current codebase:
- CLAUDE.md trimmed from 577 → 138 lines — focused instructions, no duplication (#467)
- README restructured for onboarding — knowledge base features first (#434)
- Architecture, UI, database, testing, and dev-setup docs all rewritten (#450, #460, #465)
- CLI reference cleaned of 10+ nonexistent commands (#460)

#### Test coverage: 532 → 780 tests
- 57 new tests for trash, status, delegate, and recipe commands (#471)
- Comprehensive audit added 213 tests in 0.12.0 cycle (#425)
- Weak assertions tightened in execution system tests (#461)

#### Codebase cleanup (~15,000 LOC removed)
A sustained cleanup across 10+ PRs deleted dead code from every layer — unused services, orphaned models, no-op database functions, stale migration helpers, dead CLI commands, and empty UI scaffolding. The codebase is now ~35,000 lines (down from ~50,000).

#### Other improvements
- `emdx --version` / `-V` flag for quick version checking
- `uv` install instructions added alongside pip/poetry (#424)
- Claude Code slash commands and custom agents for common workflows (#424)
- Cascade service layer refactor — clean import boundary for UI code (#428)
- Database layer: eliminated duplicate SQL patterns (#423)

### 🐛 Bug Fixes
- **delegate**: Fix NameError crashing synthesis in parallel runs (#421)
- **delegate**: Race condition in parallel log filenames produces wrong doc IDs (#442)
- **delegate**: `--pr` now implies `--worktree` to prevent dirty-tree failures (#458)
- **activity**: Delegate executions link to output docs instead of raw logs (#470)
- **activity**: 32x performance improvement in auto-refresh cycle (#439)
- **activity**: Auto-refresh no longer blocked by uncached service calls (#437)
- **tui**: Workflow references removed from activity screen (#447)
- **cli**: Nested Claude Code sessions work in all execution paths (#441)

### 💥 Breaking Changes
- **Workflow system replaced by recipes** — `emdx workflow` commands no longer exist. Use `emdx recipe run <id>` or `emdx delegate --doc <id>` instead.
- **Mail system removed** — `emdx mail` replaced by GitHub Issues for agent communication.
- **Commands removed**: `emdx legend` (merged into `emdx tag list`), `emdx gdoc`, `emdx similar`, `emdx agent`, `emdx run`, `emdx each`, archive/unarchive (use trash/restore).
- **6 execution commands → 1** — everything is `emdx delegate` now.

## [0.12.0] - 2026-02-10

### 🚀 Major Features

#### `emdx delegate` — stdout-friendly parallel execution (#410)
- New command designed for Claude Code to call instead of Task tool sub-agents
- Results print to **stdout** (so the calling session reads them inline) AND persist to the knowledge base
- Supports parallel execution, synthesis, tags, and title options
- Updated CLAUDE.md decision tree to prefer `delegate` over Task tool

#### Optional dependencies and Python 3.11+ support (#408)
- **Core install is now lightweight** — `pip install emdx` no longer pulls in ML/AI packages
- Heavy deps (sklearn, datasketch, anthropic, numpy, sentence-transformers, google-*) moved to optional extras: `[ai]`, `[similarity]`, `[google]`, `[all]`
- Import guards with clear error messages when optional features are used without their extras
- **Python requirement relaxed from ^3.13 to ^3.11**

#### `emdx save --gist` — save and share in one step (#416)
- `--gist`/`--share` flag creates a GitHub gist after saving
- `--secret` and `--public` imply `--gist` so `emdx save "content" --secret` just works
- `--copy`/`-c` copies gist URL to clipboard, `--open`/`-o` opens in browser
- Gist failure is non-fatal — the save always succeeds

### 🔧 Improvements

#### Activity view overhaul
- **Tree widget migration** — replaced DataTable with Tree[ActivityItem] to fix scroll jumping (#406)
- **Column-aligned rows** — activity tree renders as aligned table columns (#413)
- **Descriptive execution titles** — delegate/workflow executions show meaningful names (#411)
- **Deduplication** — synthesis docs no longer appear twice in activity feed (#412)
- **Clean RHS preview** — fixed context panel rendering (#415)

#### Codebase audit (#414)
- Deleted ~4,982 lines of dead code (unused swarm module, orphaned scripts, archived docs)
- Fixed `DEFAULT_ALLOWED_TOOLS` config bug where `TodoRead` was silently lost
- Updated stale model reference to claude-sonnet-4-5-20250929
- Extracted hardcoded config paths into `EMDX_CONFIG_DIR`/`EMDX_LOG_DIR` constants
- Added 532 new tests covering documents, emoji aliases, JSON parsing, title normalization, export destinations, lifecycle tracking, and CLI commands
- Removed ~8,400 LOC of unused TUI components (#405)

### 🐛 Bug Fixes
- **activity**: Restore auto-refresh in activity TUI — async callback was silently never awaited (#417)
- **activity**: Record document source for synthesis docs to prevent duplicates (#412)
- **delegate**: Clean execution titles, deduplicate activity entries (#415)
- **config**: Fix undefined variable `pid` → `execution.pid` in execution monitor
- **db**: Replace blanket `except Exception: pass` with specific types + logging in cascade fallbacks
- **db**: Narrow exception handling in groups.py to `sqlite3.IntegrityError`
- **activity**: Protect against single bad item killing entire activity data load

## [0.10.0] - 2026-02-07

### 🚀 Major Features

#### Agent-to-Agent Mail (`emdx mail`)
- **`emdx mail`** - Point-to-point messaging between teammates' Claude Code agents via GitHub Issues
- `emdx mail setup <org/repo>` - One-time setup: configure mail repo and create labels
- `emdx mail send` - Send messages to GitHub users with optional emdx doc attachments
- `emdx mail inbox` - Check inbox with unread/sender filtering
- `emdx mail read` - Read message threads with auto-save to knowledge base
- `emdx mail reply` - Reply to messages with optional doc attachments and thread closing
- `emdx mail status` - Show mail configuration and unread count
- Label-based routing (`from:user`, `to:user`, `status:unread`/`status:read`)
- Local read receipt tracking via SQLite
- Activity screen integration for mail messages in TUI

### 🔧 Improvements

#### CLI Enhancements
- **Lazy loading** for heavy CLI commands - faster startup time
- **`emdx help`** command as alternative to `--help`
- **Safe mode** with strategic architecture analysis
- Pass `include_archived` param through model layer for list command

#### Cascade & Execution
- Extract cascade metadata to dedicated table for better organization
- Multi-line TextArea for cascade new idea input in TUI

#### Code Quality
- Migrate remaining files to shared Console module
- Update CLI documentation with missing commands

### 🐛 Bug Fixes
- **ui**: Prevent activity view from jumping to cursor on refresh
- **cli**: Pass include_archived param through model layer for list command
- **test**: Remove gui from lazy loading test expectations
- **scripts**: Only update poetry version in release script

### 🗑️ Housekeeping
- Remove completed TECH_DEBT_TASKS.md from repo root

## [0.8.0] - 2025-01-29

### 🚀 Major Features

#### Cascade - Autonomous Idea-to-Code Pipeline
- **`emdx cascade`** - Transform raw ideas into working code through autonomous stages
- Stage flow: idea → prompt → analyzed → planned → done (with PR creation)
- `--auto` flag for continuous processing without manual intervention
- `--analyze` and `--plan` shortcuts for common operations
- New Idea modal in TUI for quick idea capture
- Activity grouping for cascade-related documents

#### Execution System Enhancements
- **`emdx agent`** - Sub-agent execution with automatic EMDX tracking and metadata
- **`emdx each`** - Reusable parallel operations with discovery patterns
- **`emdx run`** - Quick parallel task execution with `--worktree` isolation
- **`emdx prime`** and **`emdx status`** - Native Claude Code integration commands
- `--pr` and `--pr-single` flags for automatic PR creation
- Cursor CLI support with live log streaming
- UnifiedExecutor for consistent execution across all commands

#### AI-Powered Features
- **Semantic search** with local embeddings (sentence-transformers)
- **RAG Q&A system** - Ask questions about your knowledge base
- **`emdx ai context`** - Pipe relevant docs to Claude CLI (uses Max subscription, no API cost!)
- TF-IDF similarity scoring for document relationships

#### TUI Improvements
- **GitHub PR browser** with diff viewer
- **Search screen** with Google-style command palette results
- **Synthesis phase indicator** in workflow execution
- Document titles shown in workflow task queue
- Central keybinding registry with conflict detection
- `?` help modal across all views
- `i` keybinding for quick gist/copy operations
- `d` key for single task deletion in workflow browser

### 🐛 Bug Fixes
- **search**: Escape hyphenated queries in FTS5 search
- **ui**: Prevent Activity Browser flicker when scrolling
- **ui**: Fix GUI keybindings, search selection, and semantic search
- **cascade**: Use detached execution for reliable process management
- **cli**: Add missing DEFAULT_ALLOWED_TOOLS constant
- **db**: Calculate total_tokens and total_cost_usd in group metrics
- **types**: Replace List[Any] with proper GitWorktree type annotations
- **logging**: Add logging to silent exception handlers
- Reduce default max concurrent from 10 to 5
- Replace cryptic mode icons with clearer symbols
- Correct task count display in workflow browser

### ⚡ Performance
- **Fast merge path** in maintenance operations
- Optimized Activity layout rendering

### 🔧 Technical Changes
- Standardized parallelism flag (`-j`) across all CLI commands
- Backward-compatible template aliases (`{{task}}` → `{{item}}`)
- Removed deprecated agent system
- Cleaned up unused tables and dead code
- Removed `--pattern` flag for clearer language

### 📚 Documentation
- Updated CLAUDE.md with execution methods decision tree
- Added documentation for `emdx run` and `emdx ai` commands
- Added examples to `emdx workflow run --help`
- Documented auto-loaded doc variables

## [0.7.0] - 2025-01-28

### 🔥 Major Features Added

#### Execution System Overhaul
- **Event-driven Log Streaming** - Real-time log updates without polling overhead
- **Comprehensive Process Management** - Heartbeat tracking, PID management, and lifecycle monitoring
- **Database Cleanup Tools** - New `emdx maintain cleanup` commands for branches, processes, and executions
- **Enhanced Execution Environment** - Comprehensive validation and better error handling
- **Unique Execution ID Generation** - Better collision detection with UUID components and microsecond precision

#### Test Suite Achievement
- **100% Test Passing Rate** - Complete test suite restoration from broken state
- **Comprehensive Test Coverage** - 172 tests now passing, up from ~50% pass rate
- **Robust Testing Framework** - Fixed auto-tagger, browse, migration, and smart execution tests

### 🏗️ Architecture Improvements

#### Process & Execution Management
- **Heartbeat Mechanism** - 30-second heartbeat updates for execution tracking
- **ExecutionMonitor Service** - Real-time process monitoring and health checks
- **Cleanup Commands** - Automated cleanup of zombie processes, stuck executions, and old branches
- **Enhanced Branch Management** - Better collision detection and unique branch naming

#### Database Enhancements
- **State Consistency** - Fixed 94 stuck 'running' executions in database
- **Execution Lifecycle** - Proper status tracking with timeout handling
- **Directory Management** - Improved temp directory cleanup and collision avoidance

### 🐛 Critical Bug Fixes

#### TUI Stability
- **Delete Key Crash** - Fixed parameter mismatch in DeleteConfirmScreen constructor
- **Git Branch Conflicts** - Resolved branch creation collisions and cleanup issues
- **Process Zombies** - Fixed zombie process accumulation and resource leaks
- **Database Corruption** - Cleaned up inconsistent execution states

#### Log System Improvements
- **Timestamp Preservation** - Maintain original timestamps during real-time streaming
- **Log Browser Performance** - Eliminated polling overhead with event-driven updates
- **Wrapper Coordination** - Fixed log coordination issues by making wrapper sole writer

### 🎨 User Experience Improvements

#### Enhanced Delete Behavior
- **Immediate Deletion** - Removed confirmation modal for faster workflow
- **Cursor Preservation** - Maintain cursor position after document deletion
- **Smart Positioning** - Intelligent cursor adjustment when deleting final document

#### Interface Improvements
- **Better Status Messages** - Clearer feedback for operations and errors
- **Header Visibility** - Restored and improved document browser headers
- **Tab Navigation** - Enhanced Tab navigation in edit mode between title and content
- **Refresh Command** - Restored 'r' key refresh functionality

#### Editor Enhancements
- **Markdown Headers** - Use clean markdown headers instead of unicode boxes
- **Document Creation** - Improved new document experience with better UI flow
- **Edit Mode Stability** - Fixed mounting errors and improved editor lifecycle

### 🔧 Technical Improvements

#### Environment & Tooling
- **Sonnet 4 Upgrade** - Default to claude-sonnet-4-20250514 model
- **Tool Display** - Improved visualization of allowed tools during execution
- **Python Environment** - Better detection and handling of pipx/venv environments
- **Error Recovery** - Enhanced error handling throughout the system

#### Documentation
- **Comprehensive Guides** - Updated testing guide and development documentation
- **Architecture Documentation** - Clean documentation structure in docs/ folder
- **Installation Instructions** - Fixed dependency management and setup process

### 💥 Breaking Changes
- **Delete Behavior** - 'd' key now immediately deletes without confirmation
- **Git Browser** - Moved to 'g' key (from 'd' key which now deletes)
- **Python Requirement** - Requires Python 3.13+ (was 3.9+)

### 🎯 Success Metrics
- **Test Success Rate**: 172/172 tests passing (100%)
- **Performance**: Event-driven log streaming eliminates polling overhead
- **Reliability**: Zero zombie processes and stuck executions after cleanup
- **User Experience**: Immediate delete response with cursor preservation

## [0.6.1] - 2025-07-27

### 🚨 Critical Documentation Fixes

#### Version Consistency
- **Fixed version badge** - Updated README.md badge from 0.6.0 to 0.6.1
- **Fixed Python requirement** - Updated from 3.9+ to 3.13+ (matches pyproject.toml)
- **Updated Black config** - Target version updated from py39 to py313
- **Updated MyPy config** - Python version updated from 3.9 to 3.13

#### Missing Command Documentation
- **Added missing command documentation** for new commands:
  - `emdx delegate list/show/kill/...` - Execution management (formerly `emdx exec`)
  - `emdx claude` - Claude execution subcommands  
  - `emdx lifecycle` - Document lifecycle tracking
  - `emdx analyze` - Document analysis command
  - `emdx maintain` - Database maintenance command

#### Installation Process
- **Updated development setup** - Reflects Poetry + Just workflow
- **Added Just installation instructions** - Comprehensive setup guide
- **Fixed dependency installation** - Clarified Poetry vs pip usage

#### Architecture Documentation
- **Updated project structure** - Reflects new modular architecture with 27 UI files
- **Added UI component descriptions** - Complete documentation of modular UI system
- **Updated command module structure** - Documents all 11 command modules

### 🎯 Documentation Accuracy
- **Critical fix**: Documentation now accurately reflects actual codebase
- **User experience**: Installation instructions now work correctly
- **Contributor onboarding**: Development setup properly documented

## [0.6.0] - 2025-07-14

### 🔥 Major Features Added

#### File System Integration
- **Yazi-Inspired File Browser** - Built-in file system navigation with vim keybindings
- **File Preview** - Real-time file content preview in file browser
- **Seamless File Editing** - Edit files directly from browser with vim integration

#### Git Integration Enhancements  
- **Git Diff Browser** - Visual git diff viewer with syntax highlighting
- **Worktree Support** - Switch between git worktrees interactively with 'w' key
- **Git Operations** - Enhanced git project detection and repository management

#### Advanced TUI Features
- **Complete Vim Editor** - Full modal editing (NORMAL/INSERT/VISUAL/VISUAL LINE modes)
- **Vim Line Numbers** - Relative line numbers with proper cursor positioning
- **Enhanced Text Selection** - Robust text selection mode with copy/paste
- **Modal Navigation** - Multiple browser modes (documents, files, git diffs)

#### Execution System
- **Claude Execution Integration** - Execute prompts directly from TUI with 'x' key
- **Live Streaming Logs** - Real-time execution log viewer with 'l' key  
- **Execution History** - Track and view all execution attempts
- **Contextual Prompts** - Smart prompt selection based on document content

### 🏗️ Architecture Improvements

#### Modular Refactoring
- **Split Monolithic Browser** - Broke 3,097-line textual_browser.py into focused modules
- **Clean Component Architecture** - Separate modules for file browser, git browser, vim editor
- **Mixin Pattern** - Reusable GitBrowserMixin for git functionality across components

#### Database Enhancements  
- **Modular Database Layer** - Split database operations into focused modules
- **Migration System** - Robust schema migration support
- **Performance Optimizations** - Improved query performance and indexing

### 🐛 Critical Bug Fixes

#### TUI Stability
- **Keyboard Crash Fixes** - Resolved crashes with Ctrl+C, ESC, and modal key handling
- **Selection Mode Stability** - Fixed text selection mode crashes and escape handling
- **Widget Lifecycle** - Proper widget mounting/unmounting to prevent ID conflicts

#### Data Integrity  
- **Empty Documents Bug** - Fixed critical save command bug creating empty documents
- **Tag Display Issues** - Resolved tag formatting and display problems in TUI
- **Database Consistency** - Fixed schema migration issues and data corruption

#### Editor Improvements
- **Vim Line Numbers** - Fixed alignment and positioning issues with relative line numbers
- **Cursor Positioning** - Accurate cursor tracking across edit modes
- **Text Area Integration** - Seamless vim editor integration with Textual framework

### 🎨 User Experience

#### Enhanced UI/UX
- **Clean Mode Indicators** - Minimal, vim-style mode indicators
- **Better Error Handling** - Comprehensive error messages and recovery
- **Responsive Design** - Improved layout and spacing across all modes
- **Visual Feedback** - Real-time status updates and operation confirmation

#### Workflow Improvements
- **Quick Actions** - Fast gist creation with 'g' key in TUI
- **Smart Defaults** - Intelligent mode switching and content detection
- **Keyboard Efficiency** - Comprehensive vim-style keybindings throughout

### 🔧 Developer Experience

#### Code Quality
- **Python 3.9+ Modernization** - Full type annotations using built-in generics
- **Comprehensive Testing** - Expanded test suite with vim editor testing
- **Code Formatting** - Consistent black/ruff formatting throughout codebase
- **Documentation Updates** - Enhanced inline documentation and examples

#### Development Tools
- **justfile Integration** - Streamlined development workflow commands
- **Pre-commit Hooks** - Automated code quality checks
- **CI/CD Improvements** - Enhanced testing and release automation

## [0.5.0] - Previous Release

### Added
- **Vim-like Editing Mode** - Full vim modal editing directly in the TUI preview pane
  - Complete modal system: NORMAL, INSERT, VISUAL, and VISUAL LINE modes
  - Core vim navigation: h/j/k/l, w/b/e (word motions), 0/$ (line), gg/G (document)
  - Mode switching commands: i/a/I/A/o/O (insert variants), v/V (visual modes)
  - Editing operations: x (delete char), dd (delete line), yy (yank), p/P (paste)
  - Repeat count support: 3j, 5w, 2dd etc.
  - Smart dual ESC behavior: INSERT→NORMAL→EXIT edit mode
  - Color-coded status bar showing current vim mode and pending commands
  - Backward compatibility: EditTextArea alias maintains existing functionality

### Changed
- **TUI Edit Mode Enhanced** - Press 'e' now enters vim editing mode instead of external nvim
  - Starts in INSERT mode for immediate text editing
  - Full vim command set available in NORMAL mode
  - Visual feedback with mode indicators in status bar
  - Seamless integration with existing width constraint fixes

## [0.5.0] - 2025-01-10

### Added
- **Seamless nvim Integration** - Zero terminal flash when editing documents
  - External wrapper approach using proper terminal state management
  - Clean exit/restart cycle with signal-based process coordination
  - nvim gets full terminal control without visual artifacts
- **Modern Textual-based GUI** - Complete rewrite of the interactive browser
  - True modal behavior with NORMAL/SEARCH modes (like vim)
  - Vim-style navigation: j/k (up/down), g/G (top/bottom), / (search)
  - Live search with instant document filtering
  - Mouse support with modern textual widgets
  - Modal delete confirmation dialog with y/n shortcuts
  - Full-screen document viewer with vim navigation (j/k, ctrl+d/u, g/G)

### Changed
- **BREAKING**: `emdx gui` now uses textual browser instead of FZF
- **Clean markdown rendering** - Documents show only title + content
  - Removed project/created/views metadata headers
  - Matches mdcat behavior for clean reading experience
  - Both preview pane and full-screen view show consistent formatting

### Removed
- **FZF browser completely removed** - All FZF-related code and dependencies
- **Experimental commands removed**: modal, textual, markdown, seamless, wrapper
- All preview script helpers and leader key implementations

### Technical Details
- New `nvim_wrapper.py` handles terminal state management
- `textual_browser_minimal.py` provides the modal TUI interface
- Uses Textual library for modern terminal UI components
- Rich markdown rendering with syntax highlighting

## [0.4.0] - 2025-01-09

### Added
- **Comprehensive Tag System** - Organize documents with tags
  - Add tags when saving: `emdx save file.md --tags "python,tutorial"`
  - Search by tags: `emdx find --tags "python,api" --any-tags`
  - Tag management commands:
    - `emdx tag <id> [tags...]` - Add/view tags for a document
    - `emdx untag <id> <tags...>` - Remove tags from a document
    - `emdx tags` - List all tags with usage statistics
    - `emdx retag <old> <new>` - Rename a tag globally
    - `emdx merge-tags <tags...> --into <target>` - Merge multiple tags
  - Tags displayed in document view and search results
  - Tag autocomplete and suggestions
  - Database migration system for schema updates

### Changed
- **Simplified Input Interface** - Consolidated 5 capture commands into 1
  - Removed separate commands: `note`, `clip`, `pipe`, `cmd`, `direct`
  - Single `save` command now handles all input methods:
    - Files: `emdx save README.md`
    - Direct text: `emdx save "Quick note"`
    - Stdin: `echo "content" | emdx save --title "My Note"`
    - Clipboard: `pbpaste | emdx save --title "Clipboard"`
    - Command output: `ls -la | emdx save --title "Directory"`
- Improved GUI viewing experience with better markdown rendering
- Enhanced color output support in terminal

### Fixed
- GUI preview pane shell compatibility issues
- Command execution in interactive browser

### Removed
- `emdx/capture.py` module (functionality merged into core.py)

## [0.3.2] - 2025-01-09

### Fixed
- Fix GUI preview pane and command execution
- Make GUI commands shell-agnostic for better compatibility

## [0.3.1] - 2025-01-09

### Added
- GitHub Gist integration for sharing knowledge base entries
  - Create public/private gists from documents
  - Update existing gists
  - List all created gists
  - Copy gist URL to clipboard
  - Open gist in browser
- Edit and delete keybindings in GUI
  - `Ctrl-e` to edit documents
  - `Ctrl-d` to delete documents
  - `Ctrl-r` to restore from trash
  - `Ctrl-t` to toggle trash view

### Fixed
- Database migration order for soft delete columns

## [0.2.1] - 2025-01-08

### Added
- Edit and delete functionality with soft delete support
  - Documents are moved to trash before permanent deletion
  - Restore documents from trash
  - Purge to permanently delete

## [0.2.0] - 2025-01-07

### Added
- Rich pager support for `emdx view` command
- mdcat integration for markdown viewing with automatic pagination
- SQLite migration command for PostgreSQL to SQLite transition

### Changed
- **BREAKING**: Switched from PostgreSQL to SQLite for zero-setup installation
- Database now stored at `~/.config/emdx/knowledge.db`
- Removed all PostgreSQL dependencies

### Fixed
- SQLite datetime parsing

## [0.1.0] - 2025-01-07

### Added
- Initial release
- Core commands: save, find, view, list
- Quick capture: note, clip, pipe, cmd, direct
- Interactive FZF browser (gui)
- Full-text search with FTS5
- Git repository detection
- Project-based organization
- Recent documents tracking
- Statistics command
- JSON/CSV export
- User config file support at `~/.config/emdx/.env`

[0.19.0]: https://github.com/arockwell/emdx/compare/v0.18.0...v0.19.0
[0.18.0]: https://github.com/arockwell/emdx/compare/v0.17.0...v0.18.0
[0.17.0]: https://github.com/arockwell/emdx/compare/v0.16.0...v0.17.0
[0.16.0]: https://github.com/arockwell/emdx/compare/v0.15.0...v0.16.0
[0.15.0]: https://github.com/arockwell/emdx/compare/v0.14.0...v0.15.0
[0.14.0]: https://github.com/arockwell/emdx/compare/v0.12.0...v0.14.0
[0.12.0]: https://github.com/arockwell/emdx/compare/v0.10.0...v0.12.0
[0.10.0]: https://github.com/arockwell/emdx/compare/v0.8.0...v0.10.0
[0.8.0]: https://github.com/arockwell/emdx/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/arockwell/emdx/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/arockwell/emdx/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/arockwell/emdx/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/arockwell/emdx/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/arockwell/emdx/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/arockwell/emdx/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/arockwell/emdx/compare/v0.2.1...v0.3.1
[0.2.1]: https://github.com/arockwell/emdx/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/arockwell/emdx/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/arockwell/emdx/releases/tag/v0.1.0