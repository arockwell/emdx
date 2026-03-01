# emdx vs Obsidian: Feature Comparison

A detailed comparison of emdx and [Obsidian](https://obsidian.md), two local-first knowledge management tools with fundamentally different design philosophies.

## TL;DR

| Dimension | emdx | Obsidian |
|-----------|------|----------|
| **Primary user** | AI agents + developers | Humans (writers, researchers, PKM) |
| **Interface** | CLI + TUI | GUI (desktop/mobile) |
| **Storage** | SQLite + FTS5 | Plain markdown files |
| **Extensibility** | Claude Code plugin/hooks | 2,700+ community plugins |
| **AI integration** | Deep, first-class (RAG, synthesis, auto-wiki) | Plugin-based (community) |
| **Collaboration** | Single-user (agent-assisted) | Single-user (Sync add-on for multi-device) |
| **Price** | Free / MIT | Free personal; $10/mo Sync, $10/mo Publish |

## Design Philosophy

**emdx:** "AI agents populate, humans curate." A knowledge base designed for the AI-assisted development workflow. The CLI is the primary interface — same commands, different output modes (`--json` for agents, `--rich` for humans). Documents are opaque blobs in SQLite; structure comes from tags, epics, categories, and computed links.

**Obsidian:** "Your second brain." A personal knowledge management tool for humans who think in linked notes. The editor is the primary interface. Documents are plain markdown files you own forever. Structure comes from folders, links, tags, and the graph view. AI features exist via community plugins but aren't core to the product.

## Feature-by-Feature Comparison

### Document Storage & Format

| Feature | emdx | Obsidian |
|---------|------|----------|
| Storage format | SQLite database | Plain markdown files |
| File ownership | DB file you own | Individual .md files you own |
| Portability | Export via view/gist/wiki-export | Files are already portable |
| Version history | Built-in (SHA-256 snapshots, diff) | Via Git or Sync (plugin) |
| Offline access | Yes (local SQLite) | Yes (local files) |
| Multi-device sync | Manual (cloud backup to Gist/GDrive) | Obsidian Sync ($10/mo) or 3rd-party |

**emdx advantage:** Built-in version history with `emdx history` and `emdx diff` — every edit creates a snapshot automatically. No Git setup required.

**Obsidian advantage:** Plain files mean zero lock-in. Open your vault in any editor, grep it, version it with Git, or migrate to another tool trivially. emdx requires export steps.

### Search

| Feature | emdx | Obsidian |
|---------|------|----------|
| Full-text search | FTS5 with BM25 ranking | Built-in search with regex |
| Semantic search | sentence-transformers (all-MiniLM-L6-v2) | Plugin (e.g., Smart Connections) |
| Hybrid search | RRF fusion of FTS5 + semantic (default) | Not built-in |
| Fuzzy search | `--fuzzy` flag | Built-in fuzzy matching |
| Tag filtering | `--tags`, `--any-tags`, `--no-tags` | Tag search in search bar |
| Date range filtering | `--created-after`, `--modified-before` | Search operators (file:, path:) |
| Similar documents | `--similar <id>` | Plugin-based |
| Standing queries | `--watch` / `--watch-check` | Not built-in |

**emdx advantage:** Hybrid search (keyword + semantic) as the default is genuinely powerful — "how we handle token expiry" finds docs about session refresh, clock skew, and JWT rotation even if those exact words don't appear. Standing queries (`--watch`) alert you to new matches over time. No plugin installation needed.

**Obsidian advantage:** Regex search, path-scoped search, and search operators work well for power users who know exactly what they're looking for. The search UI is more visual and interactive.

### Linking & Graph

| Feature | emdx | Obsidian |
|---------|------|----------|
| Manual links | Via `maintain link` | `[[wikilinks]]` inline |
| Auto-linking on save | Semantic similarity (default) | Not built-in |
| Title-match wikification | `maintain wikify` (automatic on save) | Manual `[[]]` linking |
| Entity extraction | Built-in (headings, concepts, proper nouns) | Plugin-based |
| Backlinks | Tracked in DB, visible via `--links` | Core feature (backlinks pane) |
| Graph view | Knowledge Graph panel in TUI | Core feature (global + local graph) |
| Link types | auto, manual, title_match, entity_match | Untyped (all `[[]]` links) |

**emdx advantage:** Auto-linking is a killer feature — save a document and it automatically discovers related documents via semantic similarity, title matching, and entity co-occurrence. Three different link types provide richer relationship metadata. You don't have to manually maintain a link graph.

**Obsidian advantage:** `[[wikilinks]]` are natural to type while writing. The graph view is visually stunning and interactive — you can zoom, filter, drag nodes, and see temporal patterns. Bidirectional links are a core concept, not a maintenance command. The linking workflow is seamless because it's part of the writing experience.

### Task Management

| Feature | emdx | Obsidian |
|---------|------|----------|
| Task creation | `task add` with categories, epics | `- [ ]` checkboxes in notes |
| Task dependencies | `task dep add` with cycle detection | Not built-in |
| Task states | OPEN → ACTIVE → DONE/BLOCKED/FAILED/WON'T DO | Checkbox (done/not done) |
| Epics | Built-in (`task epic create`) | Not built-in |
| Categories | Built-in (`task cat`) | Not built-in |
| Task queue | `task ready` (unblocked tasks) | Not built-in |
| Work log | `task log` per-task history | Not built-in |
| Kanban view | Task Browser in TUI | Kanban plugin |
| Recurring tasks | Not built-in | Tasks plugin |
| Due dates | Not built-in | Tasks plugin |

**emdx advantage:** Purpose-built task management with dependencies, epics, categories, and a `task ready` queue that only shows unblocked work. The dependency chain (`task chain`) and work log (`task log`) features are unique. This is a real project management system, not checkboxes.

**Obsidian advantage:** Tasks live inside notes alongside context — you write about a problem and add `- [ ] fix the auth bug` right there. The Tasks plugin adds due dates, recurring tasks, and powerful query syntax. The Kanban plugin provides drag-and-drop boards. The ecosystem is more flexible because you can combine plugins to build exactly the workflow you want.

### AI Features

| Feature | emdx | Obsidian |
|---------|------|----------|
| RAG Q&A | `--ask` (built-in) | Plugin-based (Smart Connections, Copilot) |
| Position papers | `--think` (deliberative analysis) | Not available |
| Devil's advocate | `--think --challenge` | Not available |
| Socratic debugging | `--debug` | Not available |
| Cited answers | `--ask --cite` (chunk-level citations) | Plugin-dependent |
| Serendipity mode | `--wander` | Not available |
| Auto-tagging | `tag batch` / `--auto-tag` (ML-based) | AI Tagger plugin |
| Content synthesis | `distill` (audience-aware) | Not built-in |
| Contradiction detection | `maintain contradictions` (NLI model) | Not available |
| Auto-wiki generation | `wiki generate` (Leiden clustering + LLM) | Not available |
| Context assembly | `emdx context` (graph-walk, token-budgeted) | Not available |
| Session priming | `emdx prime` (inject KB context into Claude) | Not available |

**emdx advantage:** AI is deeply integrated, not bolted on. The deliberative search modes (`--think`, `--challenge`, `--debug`, `--wander`) are genuinely novel — they use your own knowledge base to build arguments, find counterevidence, generate diagnostic questions, and surface surprising connections. Auto-wiki generation from topic clustering is unique. Context assembly (`emdx context`) with token budgeting is designed specifically for feeding LLMs.

**Obsidian advantage:** Plugin diversity means you can choose your preferred AI backend (OpenAI, Claude, local models). The Smart Connections plugin provides semantic search and chat. For users who don't want AI, it's completely optional — emdx's design assumes AI as a first-class workflow partner.

### Knowledge Maintenance

| Feature | emdx | Obsidian |
|---------|------|----------|
| Freshness scoring | `maintain freshness` (multi-signal 0-1 score) | Not built-in |
| Staleness tiers | `stale` (critical/warning/info) | Not built-in |
| Knowledge gap detection | `maintain gaps` | Not built-in |
| Contradiction detection | `maintain contradictions` | Not built-in |
| Drift detection | `maintain drift` (abandoned work) | Not built-in |
| Code drift detection | `maintain code-drift` (stale code refs) | Not built-in |
| Document compaction | `compact` (cluster + synthesize) | Not built-in |
| Adversarial review | `view --review` | Not built-in |
| Backup | Built-in with logarithmic retention | Manual / plugin |
| Cloud backup | GitHub Gist + Google Drive | Obsidian Sync |

**emdx advantage:** This is where emdx has no competition. The maintenance suite actively fights knowledge decay — freshness scoring, contradiction detection, gap analysis, drift detection, code drift, and adversarial review are all unique. The `compact` command finds similar documents and synthesizes them, reducing sprawl. These features treat your KB as a living system that needs care, not just a filing cabinet.

**Obsidian advantage:** Simplicity. There's nothing to maintain because there's no database, no embeddings, no freshness scores. Your notes are files. If you want maintenance, you do it yourself or find a plugin.

### Wiki & Publishing

| Feature | emdx | Obsidian |
|---------|------|----------|
| Auto-wiki generation | `wiki setup` + `wiki generate` (Leiden + LLM) | Not built-in |
| Wiki export | MkDocs with Material theme | Obsidian Publish ($10/mo) |
| Static site generation | Via MkDocs export | Via Publish or community tools |
| Entity glossary | Auto-generated in wiki export | Not built-in |
| Topic clustering | Leiden community detection | Not built-in |
| Article quality scoring | `wiki quality`, `wiki rate` | Not built-in |

**emdx advantage:** Auto-wiki generation from your raw notes is remarkable — topic clustering discovers themes, LLM generates articles, and you can export to a full MkDocs site. The editorial workflow (skip, pin, merge, split, weight sources) gives fine-grained control.

**Obsidian advantage:** Obsidian Publish is a one-click publishing solution with custom domains, password protection, and a polished reading experience. Your published content is your actual notes, not AI-generated summaries.

### User Interface

| Feature | emdx | Obsidian |
|---------|------|----------|
| Primary interface | CLI (Typer) | GUI (Electron) |
| Secondary interface | TUI (Textual) | Mobile apps (iOS/Android) |
| Editor | External (`$EDITOR`) | Built-in markdown editor |
| Themes | 5 built-in TUI themes | 100+ community themes |
| Command palette | Ctrl+K in TUI | Ctrl+P (core feature) |
| Split panes | Document list + preview in TUI | Flexible pane layout |
| Mobile | No | Yes (iOS + Android) |
| Canvas/whiteboard | No | Yes (Canvas) |

**Obsidian advantage:** Obsidian is a beautiful, polished GUI application with a built-in markdown editor, mobile apps, Canvas for spatial thinking, and hundreds of community themes. The writing experience is central and refined.

**emdx advantage:** CLI-first means every operation is scriptable, pipeable, and automatable. `echo "findings" | emdx save --title "Analysis"` is faster than opening a GUI. The JSON-RPC server (`emdx serve`) enables IDE integrations. The TUI provides a keyboard-driven browsing experience for when you need visual navigation.

### Extensibility & Ecosystem

| Feature | emdx | Obsidian |
|---------|------|----------|
| Plugin system | Claude Code plugin + hooks | 2,700+ community plugins |
| API | JSON-RPC server, CLI `--json` | Plugin API (JavaScript) |
| Scripting | Bash pipes, `--json` output | Templater, Dataview, QuickAdd |
| Dataview-like queries | `emdx find` with filters | Dataview plugin (SQL-like) |
| Automation | Claude Code hooks (SessionStart, Stop, etc.) | Templates, QuickAdd, Buttons |

**Obsidian advantage:** The plugin ecosystem is enormous and mature. Dataview turns your vault into a queryable database. Templater automates note creation. Calendar, Kanban, Excalidraw, and hundreds of others add capabilities emdx doesn't have. Community themes, CSS snippets, and an active forum make Obsidian infinitely customizable.

**emdx advantage:** Deep Claude Code integration via hooks means your KB participates in every coding session automatically — prime on start, save on stop, backup daily. The plugin skills (`/emdx:bootstrap`, `/emdx:research`, etc.) make the KB an active participant in AI-assisted development.

## Where Each Tool Excels

### Choose emdx if you:
- Work primarily in a terminal with AI coding assistants
- Want AI deeply integrated into knowledge management (RAG, synthesis, auto-wiki)
- Need structured task management with dependencies and epics
- Care about knowledge decay and want automated maintenance
- Value CLI scriptability and `--json` output for automation
- Want your KB to be an active participant in Claude Code sessions

### Choose Obsidian if you:
- Want a beautiful writing and note-taking experience
- Think visually (graph view, Canvas, spatial layouts)
- Need mobile access to your notes
- Want maximum flexibility via a huge plugin ecosystem
- Prefer plain files with zero lock-in
- Don't want or need AI integration
- Value community (themes, plugins, forum, YouTube tutorials)

## Features emdx Has That Obsidian Doesn't

1. **Hybrid search as default** — FTS5 + semantic search fused via Reciprocal Rank Fusion
2. **Deliberative AI modes** — `--think`, `--challenge`, `--debug`, `--wander`
3. **Auto-wiki generation** — Leiden clustering + LLM article synthesis
4. **Contradiction detection** — NLI-powered cross-document conflict finding
5. **Knowledge decay tracking** — freshness scores, staleness tiers, drift detection
6. **Code drift detection** — finds stale code references in your docs
7. **Document compaction** — cluster similar docs and synthesize into one
8. **Context assembly** — token-budgeted graph walks for LLM consumption
9. **Session priming** — automatic KB context injection for AI sessions
10. **Standing queries** — persistent watches that alert on new matches
11. **Task dependencies with cycle detection** — real project DAG
12. **Adversarial document review** — `view --review` checks for contradictions and blind spots

## Features Obsidian Has That emdx Doesn't

1. **Rich WYSIWYG/markdown editor** — write and format inline
2. **Mobile apps** — iOS and Android
3. **Canvas** — infinite spatial workspace for visual thinking
4. **Graph view** — interactive, zoomable, filterable knowledge graph
5. **2,700+ community plugins** — Dataview, Templater, Calendar, Excalidraw, etc.
6. **100+ community themes** — visual customization
7. **Obsidian Publish** — one-click web publishing with custom domains
8. **Obsidian Sync** — end-to-end encrypted cross-device sync
9. **Due dates and recurring tasks** — via Tasks plugin
10. **Inline `[[wikilinks]]`** — linking is part of the writing flow
11. **CSS customization** — fine-grained visual control
12. **Embeds and transclusions** — `![[note]]` to embed content from other notes

## Conclusion

emdx and Obsidian occupy different niches despite both being local-first knowledge management tools. Obsidian is a *writing tool* that happens to manage knowledge. emdx is a *knowledge system* that happens to store documents. Obsidian optimizes for the human experience of creating and connecting notes. emdx optimizes for the machine-assisted workflow of capturing, analyzing, and maintaining knowledge over time.

They can coexist: use Obsidian for personal PKM and long-form writing, and emdx for AI-assisted development workflows where the KB needs to actively participate in your coding sessions.
