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

## Knowledge Base

All outputs are automatically saved and indexed. Search your entire history:

```bash
# Full-text search
emdx find "authentication bug"

# Search by tags
emdx find --tags "gameplan,active"

# Combined
emdx find "security" --tags "analysis"

# View a document
emdx view 42
```

### Semantic Search

Find documents by meaning, not just keywords:

```bash
# Build the index (one-time)
emdx ai index

# Semantic search
emdx ai search "how we handle rate limiting"

# Find similar documents
emdx ai similar 42

# Q&A with Claude API
emdx ai ask "What was our caching strategy?"

# Q&A with Claude CLI (no API cost)
emdx ai context "error handling patterns" | claude
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
| Search my history | `emdx find "query"` |
| Semantic search | `emdx ai search "concept"` |
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
