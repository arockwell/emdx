# EMDX Command Audit

Comprehensive audit of all top-level commands. For each: justification, verdict, and migration path.

## Current Top-Level Surface (30 commands/groups, ~90 subcommands)

### Tier 1: Core KB (keep as-is)

| Command | Justification | Verdict |
|---------|--------------|---------|
| `save` | Write path. Used constantly. | **Keep** |
| `find` | Read/search path. Used constantly. | **Keep** |
| `view` | Display a single doc. | **Keep** |
| `edit` | Modify doc content/title. | **Keep** |
| `delete` | Remove docs. | **Keep** |
| `tag` | Tag management (add/remove/list/rename/merge/batch). | **Keep** |
| `task` | Work queue (add/list/ready/done/active/blocked/view/log/note/delete + epic/cat subgroups). | **Keep** |

### Tier 2: Agent workflow (keep as-is)

| Command | Justification | Verdict |
|---------|--------------|---------|
| `delegate` | Core agent execution. Complex but irreplaceable. | **Keep** |
| `prime` | Session bootstrap for agents. Unique purpose. | **Keep** |
| `status` | Live delegate monitoring. | **Keep** |

### Tier 3: Cut entirely

| Command | Why cut | Migration |
|---------|---------|-----------|
| `ai` (entire group) | 10 subcommands, most redundant or infrastructure. `ai search` = `find --mode semantic`. `ai ask`/`ai context` are the only unique user features. Index/link management is maintenance. | See "Folding ai" below |
| `review` | Tag-based workflow (`needs-review` → `reviewed`/`rejected`). This is just a specialized `find --tags` + `tag add` workflow. 4 subcommands to replace something tags already do. | `find --tags needs-review` + `tag add 42 reviewed`. Drop the command. |
| `touch` | Resets staleness timer. Alias for `stale touch` that's also a top-level command. Confusing duplication. | Keep only under `stale touch` (already exists as `stale` subcommand in stale.py), remove the top-level alias |
| `gist` | Creates GitHub gist from existing doc. Very niche. `save` already has `--gist` inline. | Use `save --gist` or `view 42 \| gh gist create`. Drop standalone command. |
| `version` | `--version` flag already exists on the main app callback. Redundant. | `emdx --version` already works. Drop the `version` subcommand. |
| `task note` | Docs say it's "shorthand for `task log`." One command shouldn't be a pure alias of another. | Drop. Use `task log`. |
| `distill` | AI-powered audience synthesis. Cool idea but niche. Overlaps with `delegate "summarize docs tagged X for audience Y"`. | Drop. Same result via delegate with a prompt. |

### Tier 4: Fold into other commands

| Command | Fold into | Rationale |
|---------|-----------|-----------|
| `list` | `find --all` or `find --list` | `list` is just `find` with no query. Adding `--all` to `find` removes a top-level command. `list` currently uses `--format json/csv/table` while `find` uses `--json` — this also fixes that inconsistency. |
| `recent` | `find --recent N` | Shows N most recent docs. Already doable with `find --modified-after` but a `--recent 7d` shorthand on `find` is cleaner than a separate command. |
| `stats` (browse) | `status --stats` or `status --detailed` | Browse stats (doc count, project breakdown) is a natural extension of `status`. Not worth its own top-level command. |
| `wrapup` | `briefing --save` | `wrapup` collects recent activity and generates an AI summary. `briefing` already shows recent activity. Adding `--synthesize`/`--save` to `briefing` gives you `wrapup` without a separate command. They share the same time-window concept (`--hours`/`--since`). |
| `explore` | `find --topics` | Topic map via TF-IDF clustering. Unique analysis but could be a mode of `find` since it's searching across docs. Or keep if you value discoverability. Borderline. |
| `compact` | `maintain compact` | AI-powered document merging. This is maintenance/housekeeping, not a daily workflow command. Belongs under `maintain`. |
| `exec` | `status --exec` or fold into `delegate` subgroup | Execution management (list, view, tail, cleanup). These are delegate execution records. Could be `delegate exec list`, `delegate exec view`, etc. |
| `group` | Evaluate usage — possible cut | If groups are lightly used, consider whether tags + epics cover the same need. If heavily used, keep. |
| `stale` | `maintain stale` | Staleness tracking is maintenance work. Could live under `maintain`. Counter-argument: it's queried often enough to justify top-level. |

### Folding `ai` — Specific Plan

| `ai` subcommand | New home | Implementation |
|-----------------|----------|----------------|
| `ai search` | **Drop** | `find --mode semantic` already does this better (has `--json`, `--tags`, date filters) |
| `ai similar` | `find --similar 42` | New flag on `find` — "find docs similar to #42" |
| `ai ask` | `find --ask "question"` | New flag on `find` — retrieves context + LLM answer |
| `ai context` | `find --context "question"` | New flag on `find` — retrieves context for piping to claude |
| `ai index` | `maintain index` | Infrastructure. Belongs in maintenance. |
| `ai stats` | `maintain index --stats` or row in `status` | Infrastructure. |
| `ai clear` | `maintain index --clear` | Infrastructure. |
| `ai links` | `view 42 --links` | Document's links are a property of the document. |
| `ai link` | `maintain link` | Infrastructure — creating links is maintenance. |
| `ai unlink` | `maintain unlink` | Infrastructure. |

---

## API Ergonomic Issues

### 1. `--json` is inconsistent (HIGH PRIORITY)

**Problem:** ~20 commands lack `--json` despite this being an agent-first tool.

Missing `--json`: `save`, `task add`, `task view`, all `group` commands, all `trash` commands, `ai ask`, `ai search`, `ai similar`, `gist`, `recent`, `stats`.

**Fix:** Every command that produces output should support `--json`. Standardize on `--json` as a boolean flag everywhere (not `--format json`).

### 2. `--format json` vs `--json` split

**Problem:** `prime` uses `--format json`. `list` (browse) uses `--format table/json/csv`. Everything else uses `--json`.

**Fix:** Standardize on `--json` everywhere. If CSV is needed, add `--csv` as a separate flag (it's only used in one place).

### 3. `-n` means `--dry-run` in `compact` but `--limit` everywhere else

**Problem:** `-n` = `--limit` in `find`, `tag list`, `task list`, `review list`, `stale list`, `explore`, `browse list`. `-n` = `--dry-run` in `compact`. Muscle-memory trap.

**Fix:** Change `compact --dry-run` short flag to `-D` or remove the short flag. `-n` should always mean `--limit`.

### 4. `--tags` on `save` has no short flag

**Problem:** `--tags` is used on nearly every `save` call. `-t` is taken by `--title`. No short form exists.

**Fix:** Add `--tags` / `-T` (uppercase) on `save`. Already precedent: `recipe create` uses `-T` for `--title`, so swap: `save` gets `-t` for `--tags` and `-T` for `--title` (title is used less often since auto-title exists).

### 5. `-j` for `--json` only in `review` and `briefing`

**Problem:** Two commands give `--json` the `-j` short flag. The other ~15 commands with `--json` don't. Inconsistent.

**Fix:** Either add `-j` everywhere or remove it from review/briefing. Adding everywhere is better — `-j` is natural for `--json`.

### 6. Rich output is default despite documented plain-text convention

**Problem:** CLAUDE.md says "Default CLI output should be plain text. `--rich` flag enables colors." In practice, only `view` and `explore` offer `--rich`. Every other command uses Rich by default.

**Fix:** Two options:
- (a) Accept reality: Rich is the default. Update CLAUDE.md. `--json` is the machine output mode.
- (b) Actually implement the convention: add `--rich` to all commands, default to plain text.

Option (a) is pragmatic. The ship has sailed — rewriting every command's output for plain text is a lot of work for little gain. `--json` already serves the machine-readable need.

### 7. `--force` vs `--yes` for skip-confirmation

**Problem:** `delete`, `tag rename`, `tag merge`, `task delete`, `group delete`, `trash purge` use `--force/-f`. `compact` and `ai clear` use `--yes/-y`.

**Fix:** Pick one. `--force` is more standard for destructive operations. Change `compact` and `ai clear` to `--force`.

### 8. `save` has too many flags (17 parameters)

**Problem:** `save` mixes document creation, gist management, task linking, and auto-tagging.

Current flags: `--file`, `--title`, `--project`, `--tags`, `--group`, `--group-role`, `--auto-tag`, `--suggest-tags`, `--supersede`, `--gist`, `--public`, `--secret`, `--copy`, `--open`, `--auto-link`, `--task`, `--done`.

**Fix:** If `gist` is cut as a standalone command, also remove the inline gist flags from `save` (`--gist`, `--public`, `--secret`, `--copy`, `--open`). That's 5 flags gone. Users can pipe: `emdx view 42 --raw | gh gist create`.

---

## Bugs Found

### 1. `recipe create` uses broken `save` syntax (BUG)

**File:** `emdx/commands/recipe.py:361`

```python
cmd = ["emdx", "save", str(path), "--tags", "recipe"]
```

After 0.18.0, positional arg is always content, not a file path. Should be:
```python
cmd = ["emdx", "save", "--file", str(path), "--tags", "recipe"]
```

### 2. `emdx --help` shows broken example (BUG)

**File:** `emdx/main.py:239`

```
Save a file:
    emdx save README.md
```

Should be `emdx save --file README.md` (post-0.18.0).

---

## Docs Out of Date

| Issue | Location | Fix |
|-------|----------|-----|
| `task epic create` docs omit required `--cat` flag | `docs/cli-api.md:1157` | Add `--cat SEC` to example |
| `task cat create` docs omit required `name` positional arg | `docs/cli-api.md:1183` | Add `"Security"` positional arg to example |
| `recipe show`, `recipe install` not documented | `docs/cli-api.md` | Add sections |
| `prime`, `status` have no dedicated docs sections | `docs/cli-api.md` | Add sections |
| `maintain` wizard, `maintain cleanup-dirs`, `maintain analyze` undocumented | `docs/cli-api.md` | Add sections |
| `wrapup --save` flag undocumented | `docs/cli-api.md` | Add to options list |
| `task list` has `--status`, `--all`, `--done`, `--limit`, `--epic`, `--cat`, `--json` — none documented | `docs/cli-api.md` | Add to options list |
| `task done --note`, `task done --json` undocumented | `docs/cli-api.md` | Add to options list |
| `task blocked --reason` undocumented | `docs/cli-api.md` | Add to options list |
| `stale list` has many options not in docs | `docs/cli-api.md` | Add to options list |
| `emdx tag 42 active` shorthand not documented in cli-api.md | `docs/cli-api.md` | Add note about shorthand |
| `tag list --limit`, `--json` flags undocumented | `docs/cli-api.md` | Add to options list |

---

## Proposed Command Surface (After Audit)

### Top-level commands (target: ~15, down from ~30)

| Command | What it covers |
|---------|---------------|
| `save` | Create documents (minus gist flags) |
| `find` | Search, list, recent, topics, similar, ask, context — the universal read command |
| `view` | Display single doc (with `--links` for link graph) |
| `edit` | Modify docs |
| `delete` | Remove docs |
| `tag` | Tag management (add/remove/list/rename/merge/batch) |
| `task` | Work queue + epics + categories |
| `delegate` | Agent execution (possibly absorbs `exec` as `delegate exec`) |
| `prime` | Session bootstrap |
| `status` | Project overview (absorbs browse `stats`) |
| `briefing` | Activity summary (absorbs `wrapup` via `--save`) |
| `maintain` | All infrastructure (index, compact, stale, link/unlink, cleanup, analyze) |
| `trash` | Deleted doc management |
| `gui` | TUI browser |
| `group` | Document groups (evaluate if needed or if tags+epics suffice) |
| `recipe` | Saved prompts |

### Cut entirely (~10 commands removed)
- `ai` (folded into `find` + `maintain`)
- `review` (workflow achievable with `find --tags` + `tag add`)
- `touch` (keep only as `stale touch` or `maintain touch`)
- `gist` (use `save --gist` or pipe to `gh gist create`)
- `version` (use `--version` flag)
- `task note` (use `task log`)
- `distill` (use `delegate`)
- `list` (folded into `find`)
- `recent` (folded into `find`)
- `stats` (folded into `status`)
- `wrapup` (folded into `briefing`)

### `find` becomes the universal read command

```
emdx find "query"                    # FTS keyword search (existing)
emdx find --all                      # List all docs (replaces `list`)
emdx find --recent 7d               # Recent docs (replaces `recent`)
emdx find --mode semantic "query"    # Semantic search (existing, replaces `ai search`)
emdx find --similar 42              # Similar docs (replaces `ai similar`)
emdx find --ask "question"          # RAG Q&A (replaces `ai ask`)
emdx find --context "question"      # Context for piping (replaces `ai context`)
emdx find --topics                  # Topic map (replaces `explore`)
emdx find --tags "active"           # Tag filter (existing)
emdx find --extract                 # Extract key info (existing)
```
