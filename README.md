# emdx

[![Version](https://img.shields.io/badge/version-0.7.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**Parallel task orchestration and knowledge capture for Claude Code.**

Run multiple Claude agents in parallel, discover tasks dynamically, and automatically capture everything to a searchable knowledge base.

## What Makes EMDX Different

EMDX is designed for one workflow: **using Claude Code to get things done at scale**.

- Run 10 tasks in parallel with 5 worker slots
- Discover tasks from shell commands at runtime
- Save configurations as presets for one-command execution
- Every output automatically indexed and searchable
- Semantic search across your entire history

```bash
# Run parallel code analysis
emdx run "Review auth module" "Check error handling" "Audit SQL queries" -j 3

# Discover tasks dynamically from git branches
emdx run -d "git branch -r | grep feature" -t "Review {{task}}"

# Use a saved preset
emdx run -p security-audit
```

## Installation

```bash
git clone https://github.com/arockwell/emdx.git
cd emdx && pip install -e .
```

## Quick Start: Parallel Tasks

The `emdx run` command is the fastest way to execute parallel tasks with Claude:

```bash
# Run multiple tasks in parallel
emdx run "task one" "task two" "task three"

# Control concurrency (10 tasks, 5 slots)
emdx run "t1" "t2" "t3" "t4" "t5" "t6" "t7" "t8" "t9" "t10" -j 5

# Add synthesis to combine outputs
emdx run --synthesize "analyze auth" "analyze api" "analyze database"

# Set a title for tracking
emdx run -T "Security Audit" "check XSS" "check SQL injection" "check CSRF"
```

### Dynamic Task Discovery

Discover tasks at runtime from shell commands:

```bash
# Review all feature branches
emdx run -d "git branch -r | grep feature" -t "Review branch {{task}}"

# Analyze all Python files in a directory
emdx run -d "find src -name '*.py' -type f" -t "Analyze {{task}}"

# Process all open PRs
emdx run -d "gh pr list --json number -q '.[].number'" -t "Review PR #{{task}}"

# Run on document IDs from previous work
emdx run 5350 5351 5352
```

### Presets

Save configurations for common workflows:

```bash
# Create a preset
emdx preset create security-audit \
  --discover "find . -name '*.py'" \
  --template "Security review {{task}}" \
  --jobs 5 \
  --synthesize

# Use it
emdx run -p security-audit

# List presets
emdx preset list
```

## Workflow System

For complex multi-stage execution, use the workflow system:

```bash
# List available workflows
emdx workflow list

# Run with inline tasks
emdx workflow run parallel_analysis \
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

### Workflow Presets

Save workflow configurations for reuse:

```bash
# Create from variables
emdx workflow preset create parallel_analysis my-preset \
  -v topic="API Security"

# Create from a successful run
emdx workflow preset from-run parallel_analysis my-preset --run 42

# Use a preset
emdx workflow run parallel_analysis --preset my-preset
```

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
| Browse interactively | `emdx gui` |

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
emdx gui                             # Interactive TUI
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
| Run quick parallel tasks | `emdx run "t1" "t2" "t3"` |
| Discover tasks dynamically | `emdx run -d "command" -t "template"` |
| Save a task configuration | `emdx preset create name` |
| Run complex multi-stage work | `emdx workflow run workflow_name` |
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
poetry install
poetry run emdx --help
poetry run pytest
```

## License

MIT License - see LICENSE file.
