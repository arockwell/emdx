# EMDX - Knowledge Base CLI Tool

## ⚠️ CRITICAL: Interactive Commands

**NEVER run `emdx gui`** - This launches an interactive TUI that will hang Claude Code sessions.

**WORKAROUND**: Do not ask Claude to run the GUI command. Use CLI commands instead.

## 📖 Project Overview

EMDX is a command-line knowledge base and documentation management system built in Python. It provides full-text search, tagging, project organization, and multiple interfaces for managing and accessing your knowledge base.

**For detailed information, see: [📚 Complete Documentation](docs/)**

## 🏗️ Architecture Summary

**Core Technologies:**
- **Python 3.11+** (minimum requirement)
- **SQLite + FTS5** - Local database with full-text search
- **Textual TUI** - Modern terminal interface framework
- **Typer CLI** - Type-safe command-line interface

**Key Components:**
- `commands/` - CLI command implementations
- `database/` - SQLite operations and migrations  
- `ui/` - TUI components (Textual widgets)
- `services/` - Business logic (log streaming, file watching, etc.)
- `models/` - Data models and operations
- `utils/` - Shared utilities (git, emoji aliases, Claude integration)

**For complete architecture details, see: [🏗️ Architecture Guide](docs/architecture.md)**

## 🔧 Development Setup

### Quick Setup
```bash
# Install with poetry (for development)
poetry install
poetry run emdx --help

# Or with pip in a virtual environment  
python3.11 -m venv venv
source venv/bin/activate
pip install -e .
emdx --help
```

### Important: Development vs Global Installation

In the EMDX project directory, always use `poetry run emdx` instead of the global `emdx` command:

```bash
# ✅ Correct (in project directory)
poetry run emdx save README.md
poetry run emdx find "search terms"

# ❌ May cause issues (global installation may be outdated)
emdx save README.md
```

**For complete setup guide, see: [⚙️ Development Setup](docs/development-setup.md)**

## 💡 Essential Commands

### Save Content (Multiple Options)
```bash
# Save files
poetry run emdx save document.md
poetry run emdx save file.md --title "Custom Title"

# Save text directly (this WORKS - treats non-file args as content)
poetry run emdx save "My document content" --title "Doc"
poetry run emdx save "Remember to fix the API" --title "API Note"

# Save text via stdin (also works)
echo "My document content" | poetry run emdx save --title "Doc"
cat notes.txt | poetry run emdx save --title "Notes"

# Save and create a gist in one step
poetry run emdx save "share this" --title "Shared Note" --gist
poetry run emdx save notes.md --secret --copy   # --secret implies --gist
poetry run emdx save notes.md --public --open    # --public implies --gist
```

### Search and Browse
```bash
# Search content
poetry run emdx find "search terms"
poetry run emdx find --tags "gameplan,active"

# List and view
poetry run emdx list
poetry run emdx view 42
poetry run emdx recent
```

### Tag Management (using text aliases)
```bash
# Add tags using intuitive aliases (auto-converts to emojis)
poetry run emdx tag 42 gameplan active urgent
poetry run emdx tag list  # List all tags
poetry run emdx tag legend  # View emoji legend and aliases
```

## 🎯 Claude Code Integration - MANDATORY INSTRUCTIONS

**⚠️ YOU MUST FOLLOW THESE RULES WHEN WORKING IN THIS CODEBASE:**

### Session Start Protocol
At the start of every session, run `emdx prime` to get current work context. This shows:
- Ready tasks you can work on immediately
- In-progress work that may need attention
- Recent documents for context

```bash
# Run this first to understand the current state
emdx prime

# Or for a quick overview
emdx status
```

### Mandatory Behaviors

1. **ALWAYS check ready tasks before starting work:**
   ```bash
   emdx task ready
   ```

2. **ALWAYS save significant outputs to emdx:**
   ```bash
   echo "analysis results" | emdx save --title "Title" --tags "analysis,active"
   ```

3. **ALWAYS create tasks for discovered work:**
   ```bash
   emdx task create "Title" --description "Details"
   ```

4. **NEVER end session without:**
   - Updating task status (complete/in-progress)
   - Creating tasks for remaining work
   - Running `emdx prime` to verify state

### CRITICAL: Use `emdx delegate` Instead of Task Tool Sub-Agents

**NEVER use the Task tool to spawn sub-agents.** Use `emdx delegate` instead:

```bash
# Single task (replaces Task tool)
emdx delegate "analyze the auth module for security issues"

# Parallel tasks (replaces multiple Task tool calls)
emdx delegate "check auth" "review tests" "scan for XSS"

# Parallel with synthesis
emdx delegate --synthesize "task1" "task2" "task3" --tags analysis
```

**Why**: `emdx delegate` prints results to stdout (so you read them inline) AND
saves them to the knowledge base. Task tool sub-agents lose their output when
the conversation ends.

### Decision Tree: Which EMDX Command to Use

```
┌─────────────────────────────────────────────────────────────┐
│                   What are you doing?                        │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
       One-shot AI task? Idea → code?   Reusable pattern?
              │               │               │
              ▼               ▼               ▼
        emdx delegate    emdx cascade   emdx recipe run
        (all execution)  (autonomous)   (saved instructions)
```

**`emdx delegate` handles everything:**
- Single task: `emdx delegate "analyze auth"`
- Parallel: `emdx delegate "t1" "t2" "t3"`
- Doc IDs as tasks: `emdx delegate 42 43 44`
- Sequential pipeline: `emdx delegate --chain "analyze" "plan" "implement"`
- Dynamic discovery: `emdx delegate --each "fd -e py src/" --do "Review {{item}}"`
- With doc context: `emdx delegate --doc 42 "implement this"`
- With PR creation: `emdx delegate --pr "fix the bug"`
- With worktree isolation: `emdx delegate --worktree "fix X"`
- Combined: `emdx delegate --doc 42 --pr --worktree --chain "analyze" "implement"`

### Quick Reference

| Situation | Command | Why |
|-----------|---------|-----|
| Research/analysis (read results inline) | `emdx delegate "task" --tags ...` | Results on stdout + persisted |
| Parallel research (2-10 tasks) | `emdx delegate "t1" "t2" "t3"` | Parallel, stdout, persisted |
| Parallel with combined summary | `emdx delegate --synthesize "t1" "t2"` | Auto-synthesis of results |
| Sequential pipeline (output chains) | `emdx delegate --chain "analyze" "plan" "implement"` | Each step gets previous output |
| Dynamic discovery (for each X, do Y) | `emdx delegate --each "fd -e py" --do "Review {{item}}"` | Discovers items, processes each |
| Use doc as input context | `emdx delegate --doc 42 "implement this"` | Doc content prepended to prompt |
| Code changes with PR | `emdx delegate --pr "fix the auth bug"` | Agent creates PR automatically |
| Isolated git environment | `emdx delegate --worktree "fix X"` | Worktree created/cleaned up |
| Transform an idea to a PR autonomously | `emdx cascade add "idea"` | Full autonomous pipeline |
| Run a saved recipe | `emdx recipe run 42` | Reusable instructions via delegate |

### When Claude Should Use EMDX Automatically

**Delegate instead of using Task tool sub-agents:**
```bash
# Instead of: Task tool with subagent_type=Explore
emdx delegate "analyze the auth module for security issues"

# Instead of: multiple parallel Task tool calls
emdx delegate "check auth" "review tests" "analyze docs" --synthesize

# Results print to stdout — read them and continue the conversation
```

**Use worktree isolation when tasks might conflict:**
```bash
# User asks: "Fix these three bugs"
emdx delegate --worktree "fix X" "fix Y" "fix Z"
```

**Use chain for multi-step workflows:**
```bash
# Analyze, then plan, then implement — each step sees previous output
emdx delegate --chain "analyze the auth module" "create implementation plan" "implement the plan" --pr
```

**Use cascade for ideas that need full implementation:**
```bash
# User describes a feature idea
emdx cascade add "Add a dark mode toggle to settings"
# Then let cascade run: idea → prompt → analyzed → planned → done (PR)
```

### Auto-Tagging Guidelines

When saving outputs, apply tags based on content:

| Content Type | Tags to Apply |
|--------------|---------------|
| Strategic plans, gameplans | `gameplan, active` |
| Investigation results | `analysis` |
| General notes | `notes` |
| Bug fixes | `bugfix` |
| Security-related | `security` |

**Workflow status tags:**
- `active` → 🚀 Currently working on
- `done` → ✅ Completed
- `blocked` → 🚧 Stuck/waiting

**Outcome tags (add when work completes):**
- `success` → 🎉 Worked as intended
- `failed` → ❌ Didn't work
- `partial` → ⚡ Mixed results

### Delegating Work (Replaces Task Tool Sub-Agents)

Use `emdx delegate` instead of the Task tool. Results print to stdout AND persist:

```bash
# Single research task — results come back inline
emdx delegate "Investigate memory leak in worker pool" --tags analysis,performance

# Parallel research — up to 10 concurrent tasks
emdx delegate \
  "Check auth module for SQL injection" \
  "Review input validation in API endpoints" \
  "Scan for hardcoded secrets" \
  --tags security --synthesize

# With document context
emdx delegate --doc 42 "implement the plan described in this document"

# Sequential pipeline — each step sees previous output
emdx delegate --chain "analyze the problem" "design a solution" "implement it"

# Quiet mode — just content, no metadata
emdx delegate -q "quick analysis of error rates"
```

Metadata (doc_id, tokens, cost, duration) prints to stderr. Content prints to stdout.

### PR Creation Flow

When implementing code changes:

```bash
# Single implementation with PR
emdx delegate --pr "fix the auth bug"

# Implementation from a doc with PR
emdx delegate --doc 123 --pr "implement this plan"

# Worktree-isolated fix with PR (worktree kept for the PR branch)
emdx delegate --worktree --pr "fix the null pointer in auth"

# Multi-step pipeline ending with PR
emdx delegate --chain --pr "analyze the issue" "implement the fix"

# For idea-to-PR pipeline (fully autonomous)
emdx cascade add "Add user preferences page"
emdx cascade run  # Runs through all stages to PR
```

## 🌊 Cascade - Ideas to Code (`emdx cascade`)

Transform raw ideas into working code through autonomous stage transformations. Cascade takes an idea and flows it through: **idea → prompt → analyzed → planned → done** — with the final stage creating an actual PR.

```bash
# Add an idea to the cascade
emdx cascade add "Add dark mode toggle to the settings page"

# Check cascade status
emdx cascade status

# Process the next item at a stage (sync waits for completion)
emdx cascade process idea --sync
emdx cascade process prompt --sync
emdx cascade process analyzed --sync
emdx cascade process planned --sync  # This creates actual code and PR!

# Or run continuously
emdx cascade run
```

### Stage Flow

| Stage | What Happens |
|-------|--------------|
| `idea` | Raw idea text enters the cascade |
| `prompt` | Claude transforms idea into a well-formed prompt |
| `analyzed` | Claude analyzes the prompt thoroughly |
| `planned` | Claude creates a detailed implementation gameplan |
| `done` | Claude implements the code and creates a PR |

### Key Commands

| Command | Description |
|---------|-------------|
| `emdx cascade add "idea"` | Add new idea to cascade |
| `emdx cascade status` | Show documents at each stage |
| `emdx cascade process <stage> --sync` | Process next doc at stage |
| `emdx cascade advance <id>` | Manually advance a document |
| `emdx cascade remove <id>` | Remove from cascade (keeps doc) |
| `emdx cascade synthesize <stage>` | Combine multiple docs into one |

### TUI Access

Press `4` in the GUI to access the Cascade browser. Navigate with:
- `h/l` - Switch stages
- `j/k` - Navigate documents
- `a` - Advance document
- `p` - Process through Claude
- `s` - Synthesize selected docs
- `Space` - Toggle selection (for synthesis)

## 📡 Delegate — The Single Execution Command (`emdx delegate`)

`emdx delegate` is the **one command for all one-shot AI execution**. Results print to
stdout (so Claude reads them inline) AND persist to emdx.

```bash
# Single task
emdx delegate "analyze the auth module"

# Parallel (up to 10 concurrent)
emdx delegate "check auth" "review tests" "scan for XSS"

# Parallel with synthesis
emdx delegate --synthesize "task1" "task2" "task3"

# With document context (prepends doc content to prompt)
emdx delegate --doc 42 "implement the plan described here"

# Sequential pipeline (each step sees previous output)
emdx delegate --chain "analyze the problem" "design solution" "implement it"

# With PR creation (agent creates branch + PR)
emdx delegate --pr "fix the auth bug"

# With worktree isolation (clean git environment)
emdx delegate --worktree --pr "fix X"

# All flags compose together
emdx delegate --doc 42 --chain --worktree --pr "analyze" "implement"

# With tags and title
emdx delegate "deep analysis" --tags analysis,security --title "Security Audit"

# Quiet mode (suppress metadata, just content)
emdx delegate -q "quick analysis"
```

**Options:**
- `--tags, -t` — Tags to apply to output documents
- `--title, -T` — Title for the output document(s)
- `--synthesize, -s` — Combine parallel outputs into one summary
- `-j, --jobs` — Max parallel tasks (default: auto)
- `--model, -m` — Override default model
- `--quiet, -q` — Suppress metadata on stderr
- `--doc, -d` — Document ID to use as input context
- `--pr` — Instruct agent to create a PR after code changes
- `--worktree, -w` — Run in isolated git worktree
- `--base-branch` — Base branch for worktree (default: main)
- `--chain` — Run tasks sequentially, piping output forward
- `--each` — Shell command to discover items (one per line)
- `--do` — Template for each discovered item (use `{{item}}`)

**Output format:**
- stdout: Full content of the result (for Claude to read inline)
- stderr: `doc_id:XXXX tokens:N cost:$X.XX duration:Xs`

**Note:** `--chain` and `--synthesize` are mutually exclusive. `--each` requires `--do`.

## 📋 Recipes — Reusable Instruction Templates (`emdx recipe`)

Recipes are emdx documents tagged with `recipe` (📋) that contain reusable instructions for Claude via `emdx delegate`.

```bash
# List all recipes
emdx recipe list

# Run a recipe by ID or title
emdx recipe run 42
emdx recipe run "Security Audit" -- "analyze auth module"

# Create a recipe from a markdown file
emdx recipe create instructions.md --title "My Recipe"

# Or manually: save + tag
echo "Instructions here" | emdx save --title "My Recipe" --tags "recipe"
```

### When to Use Which Command

| Use `emdx delegate` when... | Use `emdx cascade` when... | Use `emdx recipe` when... |
|------------------------------|---------------------------|--------------------------|
| Any one-shot AI execution | Idea-to-PR autonomous pipeline | Reusable saved instructions |
| Single, parallel, or chain | Persistent stage tracking | Repeatable patterns |
| PR creation, worktree, doc context | Full idea → prompt → plan → code flow | Pre-defined analysis templates |

## ✨ AI-Powered Search & Q&A (`emdx ai`)

Semantic search and Q&A over your knowledge base:

```bash
# Build embedding index (one-time setup)
emdx ai index

# Semantic search - finds conceptually related docs
emdx ai search "authentication patterns"
emdx ai similar 42  # Find docs similar to #42

# Q&A with Claude API (needs ANTHROPIC_API_KEY)
emdx ai ask "How does the cascade system work?"

# Q&A with Claude CLI (uses Claude Max subscription - no API cost!)
emdx ai context "How does the cascade system work?" | claude
emdx ai context "error handling" --limit 5 | claude "summarize"
```

### AI Commands Quick Reference

| Command | Description | Needs API Key? |
|---------|-------------|----------------|
| `emdx ai index` | Build embeddings | No |
| `emdx ai search "query"` | Semantic search | No |
| `emdx ai similar <id>` | Find similar docs | No |
| `emdx ai ask "question"` | Q&A with Claude API | **Yes** |
| `emdx ai context "q" \| claude` | Q&A with Claude CLI | No |
| `emdx ai stats` | Show index status | No |

## 📊 Key Features for Claude Integration

### Event-Driven Log Streaming
- **Real-time updates** without polling overhead
- **OS-level file watching** for reliable change detection
- **Clean resource management** with automatic cleanup
- **Cross-platform support** with fallback strategies

### Emoji Tag System
- **Text aliases** for easy typing (`gameplan` → 🎯, `active` → 🚀)
- **Visual organization** space-efficient in GUI
- **Flexible search** with all/any tag modes
- **Usage analytics** for optimization

### Git Integration
- **Auto-project detection** from git repositories
- **Diff browser** for visual change review
- **Worktree support** for managing multiple branches

## 🔍 Common Development Tasks

For detailed guides on these topics, see the comprehensive documentation:

- **Adding CLI Commands** → [Development Setup](docs/development-setup.md)
- **UI Development** → [UI Architecture](docs/ui-architecture.md)
- **Database Changes** → [Database Design](docs/database-design.md)
- **Testing Patterns** → [Development Setup](docs/development-setup.md)

## 🎯 Success Analytics

Track gameplan success rates with tag-based queries:
```bash
# Find successful plans
poetry run emdx find --tags "gameplan,success"

# Find failed plans  
poetry run emdx find --tags "gameplan,failed"

# Current active work
poetry run emdx find --tags "active"

# Blocked items needing attention
poetry run emdx find --tags "blocked"
```

This enables powerful project management and success tracking while keeping the tag system simple and space-efficient.

## 🚢 Release Process

Use the release tooling in `scripts/release.py` (via `just`) to prepare releases.

### Quick Release Checklist

```bash
# 1. Preview what changed since last release
just changelog

# 2. Bump version in pyproject.toml AND emdx/__init__.py
just bump 0.X.Y

# 3. Write a polished changelog entry in CHANGELOG.md
#    - The auto-generated one from `just release` is mechanical;
#      prefer hand-writing with proper feature descriptions
#    - Add comparison link at bottom of CHANGELOG.md

# 4. Create docs for any new features
#    - Update docs/README.md index
#    - Update docs/cli-api.md with new commands

# 5. Branch, commit, PR
git checkout -b release/vX.Y.Z
git add -A && git commit -m "chore: release vX.Y.Z"
git push -u origin release/vX.Y.Z
gh pr create --title "chore: Release vX.Y.Z"

# 6. After merge, tag and push
git tag vX.Y.Z
git push --tags
```

### Release Script Commands

| Command | What it does |
|---------|-------------|
| `just changelog` | Preview categorized commits since last release |
| `just bump <version>` | Bump version in `pyproject.toml` and `emdx/__init__.py` |
| `just release <version>` | Bump + auto-generate changelog (prefer manual changelog) |

### Version Files

Both of these must stay in sync:
- `pyproject.toml` — `version = "X.Y.Z"` (used by Poetry/pip)
- `emdx/__init__.py` — `__version__ = "X.Y.Z"` (used at runtime)

The `just bump` and `just release` commands update both automatically.

---

**Documentation Links:**
- [📚 Complete Documentation](docs/) - Full project guides
- [🏗️ Architecture](docs/architecture.md) - System design and code structure  
- [⚙️ Development Setup](docs/development-setup.md) - Contributing guide
- [📋 CLI Reference](docs/cli-api.md) - Complete command documentation