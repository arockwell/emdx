# emdx

[![Version](https://img.shields.io/badge/version-0.14.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**Parallel task orchestration and knowledge capture for Claude Code.**

Run multiple Claude agents in parallel, discover tasks dynamically, and automatically capture everything to a searchable knowledge base.

## What Makes EMDX Different

EMDX is designed for one workflow: **using Claude Code to get things done at scale**.

- Run 10 tasks in parallel with 5 worker slots
- Discover tasks from shell commands at runtime
- Every output automatically indexed and searchable
- Semantic search across your entire history

```bash
# Run parallel code analysis
emdx delegate "Review auth module" "Check error handling" "Audit SQL queries" -j 3

# Discover tasks dynamically from git branches
emdx delegate --each "git branch -r | grep feature" --do "Review branch {{item}}"
```

## Installation

**Requirements:** Python 3.11+

```bash
# Install with uv (recommended)
uv tool install emdx

# With optional extras
uv tool install 'emdx[ai]'           # Semantic search, embeddings, Claude Q&A
uv tool install 'emdx[similarity]'    # TF-IDF, MinHash duplicate detection
uv tool install 'emdx[all]'           # Everything (AI + similarity + Google)

# Or install with pip
pip install emdx
pip install 'emdx[all]'

# Development (from source)
git clone https://github.com/arockwell/emdx.git
cd emdx
uv sync                               # or: poetry install --all-extras
```

## Quick Start: `emdx delegate`

`emdx delegate` is the single command for all AI execution. Results print to stdout AND persist to the knowledge base.

```bash
# Single task
emdx delegate "analyze the auth module"

# Parallel tasks (up to 10 concurrent)
emdx delegate "check auth" "review tests" "scan for XSS"

# Control concurrency
emdx delegate "t1" "t2" "t3" "t4" "t5" -j 3

# Combine parallel outputs into one summary
emdx delegate --synthesize "analyze auth" "analyze api" "analyze database"

# Set a title for tracking
emdx delegate -T "Security Audit" "check XSS" "check SQL injection" "check CSRF"
```

### Sequential Pipelines

Chain tasks where each step receives the previous output:

```bash
# Analyze, then plan, then implement
emdx delegate --chain "analyze the problem" "design a solution" "implement it"

# Chain with PR creation at the end
emdx delegate --chain --pr "analyze the issue" "implement the fix"
```

### Dynamic Task Discovery

Discover tasks at runtime from shell commands:

```bash
# Review all feature branches
emdx delegate --each "git branch -r | grep feature" --do "Review branch {{item}}"

# Analyze all Python files in a directory
emdx delegate --each "fd -e py src" --do "Analyze {{item}}"

# Process all open PRs
emdx delegate --each "gh pr list --json number -q '.[].number'" --do "Review PR #{{item}}"
```

### Document Context and PR Creation

```bash
# Use a document as input context
emdx delegate --doc 42 "implement the plan described here"

# Have the agent create a PR
emdx delegate --pr "fix the auth bug"

# Worktree isolation (clean git environment)
emdx delegate --worktree --pr "fix the null pointer in auth"

# Combine: doc context + chain + worktree + PR
emdx delegate --doc 42 --chain --worktree --pr "analyze" "implement"
```

### Run from Document IDs

```bash
# Use previous emdx documents as task prompts
emdx delegate 5350 5351 5352
```

## Cascade: Ideas to Code

Transform ideas through stages to working code: idea → prompt → analyzed → planned → done (PR).

```bash
# Add an idea to the cascade
emdx cascade add "Add dark mode toggle to settings"

# Check status
emdx cascade status

# Process stages (each advances the document)
emdx cascade process idea --sync
emdx cascade process prompt --sync
emdx cascade process analyzed --sync
emdx cascade process planned --sync  # Creates code and PR

# Or run continuously
emdx cascade run
```

## Workflow System

For complex multi-stage execution beyond what `delegate` offers:

```bash
# List available workflows
emdx workflow list

# Run with inline tasks
emdx workflow run task_parallel \
  -t "Analyze authentication" \
  -t "Analyze authorization" \
  -t "Analyze data flow"

# Use worktree isolation (each task gets its own git worktree)
emdx workflow run parallel_fix \
  -t "Fix auth bug" \
  -t "Fix validation bug" \
  --worktree --base-branch main

# Control concurrency
emdx workflow run task_parallel -t "t1" -t "t2" -t "t3" -j 2
```

### Execution Modes

| Mode | Use Case |
|------|----------|
| `single` | One task, full attention |
| `parallel` | Multiple independent tasks |
| `iterative` | Sequential refinement |
| `adversarial` | Multiple perspectives, then synthesis |
| `dynamic` | Discover tasks at runtime |

## Monitoring Executions

```bash
# List running executions
emdx exec running

# Follow logs
emdx exec show 42

# Health check
emdx exec health

# Kill a stuck execution
emdx exec kill 42

# Kill all running
emdx exec killall
```

## Finding Information

EMDX provides multiple ways to locate information, from quick keyword searches to semantic AI-powered discovery.

### Quick Reference

| I want to... | Command |
|--------------|---------|
| Search by keywords | `emdx find "auth bug"` |
| Filter by tags | `emdx find --tags "active,gameplan"` |
| Find by meaning/concept | `emdx ai search "rate limiting strategies"` |
| Find docs similar to one | `emdx similar 42` |
| Find docs matching text | `emdx similar-text "error handling pattern"` |
| See recent work | `emdx recent` |
| List all docs | `emdx list` |
| List by project | `emdx list --project myapp` |
| Read a specific doc | `emdx view 42` |
| Ask a question | `emdx ai context "how does auth work?" \| claude` |
| Browse interactively | `emdx gui` (interactive TUI - for human use, not AI agents) |

### Keyword Search

Fast full-text search using SQLite FTS5:

```bash
emdx find "authentication"           # Search for terms
emdx find --tags "active"            # Filter by tags
emdx find "security" --tags "analysis"  # Combine text and tags
emdx find "api" --project myapp      # Filter by project
```

### Semantic Search

Find documents by meaning, not just keywords:

```bash
# Build the index first (one-time)
emdx ai index

# Search by concept
emdx ai search "how we handle rate limiting"
emdx ai search "authentication flow"

# Adjust threshold (lower = more results)
emdx ai search "caching" --threshold 0.3
```

### Similar Documents

Find related content:

```bash
emdx similar 42                      # Docs similar to #42
emdx similar-text "retry logic with exponential backoff"
```

### Q&A Over Your Knowledge Base

```bash
# Using Claude CLI (recommended - uses Claude Max subscription)
emdx ai context "How does the workflow system work?" | claude

# Using Claude API (requires ANTHROPIC_API_KEY)
emdx ai ask "How did we solve the auth bug?"
```

### Browsing

```bash
emdx recent                          # Recently accessed
emdx recent 20                       # Last 20
emdx list                            # All documents
emdx list --project myapp            # By project
emdx view 42                         # Read specific doc
emdx gui                             # Interactive TUI (for human use, not AI agents)
```

### For AI Agents

Recommended search strategy for Claude Code and other AI agents:

```bash
# 1. Start with semantic search for open-ended questions
emdx ai search "authentication implementation"

# 2. Use keyword search for specific terms or IDs
emdx find "AUTH-123"

# 3. Use tag filtering to narrow by status/type
emdx find --tags "gameplan,active"    # Current plans
emdx find --tags "analysis,done"      # Completed analyses

# 4. Expand from a known good doc
emdx similar 42

# 5. Get synthesized answers
emdx ai context "What patterns do we use for error handling?" | claude
```

### Session Start

At the start of each session, get current work context:

```bash
# Full priming context
emdx prime

# Quick status overview
emdx status
```

### Emoji Tags

Type text aliases instead of emoji:

| Type | Get | Use for |
|------|-----|---------|
| `gameplan` | 🎯 | Strategic plans |
| `analysis` | 🔍 | Investigations |
| `active` | 🚀 | In progress |
| `done` | ✅ | Completed |
| `blocked` | 🚧 | Waiting |
| `success` | 🎉 | Worked |
| `failed` | ❌ | Didn't work |

```bash
emdx tag 42 gameplan active
emdx find --tags "gameplan,success"
emdx legend  # Full alias reference
```

## When to Use What

| I want to... | Use this |
|--------------|----------|
| Run one or many tasks in parallel | `emdx delegate "t1" "t2" "t3"` |
| Chain tasks sequentially | `emdx delegate --chain "analyze" "plan" "implement"` |
| Discover tasks dynamically | `emdx delegate --each "command" --do "template"` |
| Create a PR from a task | `emdx delegate --pr "fix the bug"` |
| Isolate work in a worktree | `emdx delegate --worktree "fix X"` |
| Run complex multi-stage work | `emdx workflow run workflow_name` |
| Go from idea to PR autonomously | `emdx cascade add "idea"` |
| Search by keywords | `emdx find "query"` |
| Search by meaning | `emdx ai search "concept"` |
| Find similar docs | `emdx similar 42` |
| Ask questions | `emdx ai context "question" \| claude` |
| Check running tasks | `emdx exec running` |
| Kill stuck work | `emdx exec kill id` |

## Documentation

- [CLI Reference](docs/cli-api.md) - Complete command documentation
- [Workflow System](docs/workflows.md) - Multi-stage execution patterns
- [AI System](docs/ai-system.md) - Semantic search and Q&A
- [Architecture](docs/architecture.md) - System design
- [Development Setup](docs/development-setup.md) - Contributing guide

## Development

```bash
uv sync                    # or: poetry install
uv run emdx --help         # or: poetry run emdx --help
uv run pytest              # or: poetry run pytest
```

## License

MIT License - see LICENSE file.
