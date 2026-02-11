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
poetry run emdx tags  # List all tags
poetry run emdx legend  # View emoji legend and aliases
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
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
   Need results        Multiple tasks?      Idea → working code?
   inline?                   │                     │
        │                     ▼                     ▼
        ▼              emdx delegate           emdx cascade add
   emdx delegate       (parallel, stdout)     (autonomous pipeline)
   (stdout + saved)          │
        │              Need to repeat?
        │                     │
        │              ┌──────┴──────┐
        │              ▼             ▼
        │          One-off?    Save for later?
        │              │             │
        │              ▼             ▼
        │        emdx delegate  emdx each create
        │
   Need worktree     Need custom stages
   isolation?        or adversarial mode?
        │                     │
        ▼                     ▼
   emdx run --worktree   emdx workflow run
```

### Quick Reference

| Situation | Command | Why |
|-----------|---------|-----|
| Delegating research/analysis (read results inline) | `emdx delegate "task" --tags ...` | Results on stdout + persisted |
| Parallel research (2-10 tasks) | `emdx delegate "t1" "t2" "t3"` | Parallel, stdout, persisted |
| Parallel with combined summary | `emdx delegate --synthesize "t1" "t2"` | Auto-synthesis of results |
| Same operation on many discovered items | `emdx each --from "discovery" --do "action"` | Discovery + parallel action |
| Repeatable "for each X do Y" pattern | `emdx each create name --from ... --do ...` | Save it, run it anytime |
| Parallel code fixes (may touch same files) | `emdx run --worktree "fix1" "fix2"` | Git isolation per task |
| Transform an idea to a PR autonomously | `emdx cascade add "idea"` | Full autonomous pipeline |
| Complex multi-stage with synthesis | `emdx workflow run task_parallel -t ...` | Full workflow system |

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
emdx run --worktree "Fix null pointer in auth" "Fix race condition in cache" "Fix validation bug"
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

# Quiet mode — just content, no metadata
emdx delegate -q "quick analysis of error rates"
```

Metadata (doc_id, tokens, cost, duration) prints to stderr. Content prints to stdout.

### PR Creation Flow

When implementing code changes:

```bash
# For single implementation tasks with PR
emdx agent "Implement the feature from doc #123" --tags feature --pr

# For parallel fixes with individual PRs
emdx each --from "emdx find --tags bugfix,active | head -5" \
  --do "Fix {{item}}" --pr

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

## 🚀 Quick Task Execution (`emdx run`)

The fastest way to run parallel tasks. This is the first rung on EMDX's "execution ladder" - start here and graduate to `emdx each` or `emdx workflow` only when you need more power.

```bash
# Run a single task
emdx run "analyze the auth module"

# Run multiple tasks in parallel
emdx run "analyze auth" "review tests" "check docs"

# With synthesis to combine outputs
emdx run --synthesize "task1" "task2" "task3"

# Dynamic discovery from shell commands
emdx run -d "git branch -r | grep feature" -t "Review {{item}}"

# Control concurrency
emdx run -j 3 "task1" "task2" "task3" "task4"

# With worktree isolation (for parallel code fixes)
emdx run --worktree "fix X" "fix Y"
```

For the full execution ladder (run → each → workflow → cascade), see [docs/workflows.md](docs/workflows.md#when-to-use-what).

## 🤖 Sub-Agent Execution (`emdx agent`)

Run Claude Code sub-agents with automatic EMDX tracking. The agent is instructed to save its output with the specified metadata (tags, title, group).

Works the same whether called by a human or another AI agent.

```bash
# Basic usage - agent saves output with specified tags
emdx agent "Analyze the auth module for security issues" --tags analysis,security

# With title and group
emdx agent "Review error handling in api/" -t refactor -T "API Error Review" -g 456

# Verbose mode to see agent output in real-time
emdx agent "Deep dive on caching strategy" -t analysis -v

# Have the agent create a PR if it makes code changes
emdx agent "Fix the null pointer bug in auth" -t bugfix --pr
```

**Options:**
- `--tags, -t` - Tags to apply to output (comma-separated or multiple flags)
- `--title, -T` - Title for the output document
- `--group, -g` - Group ID to add output to
- `--group-role` - Role in group (default: `exploration`)
- `--verbose, -v` - Show agent output in real-time
- `--pr` - Instruct agent to create a PR if it makes code changes

**How it works:**
1. Takes your prompt and appends instructions telling the agent how to save its output
2. The agent receives: `echo "OUTPUT" | emdx save --title "..." --tags "..." --group N`
3. Runs Claude Code and streams output to a log file
4. Extracts the created document ID and prints `doc_id:123` for easy parsing

**Use cases:**
- Humans kicking off analysis tasks with proper tracking
- AI agents spawning sub-agents that need to save results to EMDX
- Ensuring consistent metadata across human and AI-initiated work

## 📡 Delegate — stdout-friendly parallel execution (`emdx delegate`)

Designed for Claude Code to call via Bash instead of the Task tool. Results
print to stdout (so Claude reads them inline) AND persist to emdx.

```bash
# Single task
emdx delegate "analyze the auth module"

# Parallel (up to 10 concurrent)
emdx delegate "check auth" "review tests" "scan for XSS"

# Parallel with synthesis
emdx delegate --synthesize "task1" "task2" "task3"

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

**Output format:**
- stdout: Full content of the result (for Claude to read inline)
- stderr: `doc_id:XXXX tokens:N cost:$X.XX duration:Xs`

**vs other commands:**

| | `delegate` | `agent` | `run` |
|---|---|---|---|
| Content on stdout | Yes | No | No |
| Persists to emdx | Yes | Yes | Yes |
| Parallel | Yes | No | Yes |
| Synthesis | Yes | No | Yes |
| Designed for | Machine callers | Humans/scripts | Humans/scripts |

## 🔁 Reusable Parallel Commands (`emdx each`)

Create saved commands that discover items and process them in parallel. Perfect for repeatable "for each X, do Y" patterns.

```bash
# Create a reusable command
emdx each create fix-conflicts \
  --from "gh pr list --json headRefName,mergeStateStatus | jq -r '.[] | select(.mergeStateStatus==\"DIRTY\") | .headRefName'" \
  --do "Merge origin/main into {{item}}, resolve conflicts, push"

# Run it anytime
emdx each run fix-conflicts

# One-off execution (without saving)
emdx each --from "fd -e py src/" --do "Review {{item}} for security issues"

# Manage saved commands
emdx each list                    # List all saved commands
emdx each show fix-conflicts      # Show command details
emdx each edit fix-conflicts      # Edit in $EDITOR
emdx each delete fix-conflicts    # Delete command
```

**Key features:**
- `--from`: Shell command that outputs items (one per line), or `@discovery-name` for built-ins
- `--do`: What to do with each `{{item}}`
- `-j`: Max parallel executions (default: 3)
- `--synthesize`: Combine results at the end
- `--pr`: Create a PR for each item processed
- `--pr-single`: Create one combined PR for all items
- Worktree isolation is auto-enabled for git/gh commands

**Built-in discoveries** (Coming Soon - use shell commands for now):
```bash
# Built-in discoveries like @prs-with-conflicts, @python-files are planned
# For now, use shell commands directly:
emdx each --from "gh pr list --json headRefName,mergeStateStatus | jq -r '.[] | select(.mergeStateStatus==\"DIRTY\") | .headRefName'" --do "Fix {{item}}"
emdx each --from "fd -e py src/" --do "Review {{item}}"
```

## 🔄 Workflow System for Multi-Agent Tasks

When working on tasks that benefit from parallel execution or multiple perspectives, use the workflow system instead of running individual commands.

### Core Workflows

| Workflow | Use When |
|----------|----------|
| `task_parallel` | Running multiple analysis or fix tasks in parallel |
| `parallel_fix` | Multiple code fixes that might touch same files (uses worktree isolation) |

### Common Patterns

```bash
# Analyze multiple aspects of a codebase in parallel
emdx workflow run task_parallel \
  -t "Find dead code and unused imports" \
  -t "Identify missing error handling" \
  -t "Review test coverage gaps" \
  --title "Tech Debt Analysis" \
  -j 3

# Fix multiple issues with worktree isolation (each task gets own branch)
emdx workflow run parallel_fix \
  -t "Add type hints to auth module" \
  -t "Fix exception handling in api/" \
  -t "Remove deprecated function calls" \
  --worktree --base-branch main

# Use document IDs as tasks (from previous analysis)
emdx workflow run parallel_fix -t 5182 -t 5183 -t 5184 --worktree
```

### When to Use Which Command

| Use `emdx delegate` when... | Use `emdx run` when... | Use `emdx each` when... | Use `emdx workflow` when... |
|------------------------------|------------------------|-------------------------|----------------------------|
| Claude Code needs results inline | Worktree isolation needed | Reusable discovery+action | Complex multi-stage workflows |
| Replacing Task tool sub-agents | Human-facing output | "For each X, do Y" patterns | Need iterative or adversarial modes |
| Single or parallel research | Code changes in parallel | Save for future use | Custom stage configurations |
| Want stdout + persistence | Just want tasks done fast | Same operation on many items | Need detailed run monitoring |

For full workflow documentation, see [docs/workflows.md](docs/workflows.md).

## ✨ AI-Powered Search & Q&A (`emdx ai`)

Semantic search and Q&A over your knowledge base:

```bash
# Build embedding index (one-time setup)
emdx ai index

# Semantic search - finds conceptually related docs
emdx ai search "authentication patterns"
emdx ai similar 42  # Find docs similar to #42

# Q&A with Claude API (needs ANTHROPIC_API_KEY)
emdx ai ask "How does the workflow system work?"

# Q&A with Claude CLI (uses Claude Max subscription - no API cost!)
emdx ai context "How does the workflow system work?" | claude
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

# 4. Create docs for any new features (e.g., docs/mail.md)
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