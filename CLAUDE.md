# EMDX - Knowledge Base CLI Tool

## ⚠️ CRITICAL: Interactive Commands

**NEVER run `emdx gui`** - This launches an interactive TUI that will hang Claude Code sessions.

**WORKAROUND**: Do not ask Claude to run the GUI command. Use CLI commands instead.

## 📖 Project Overview

EMDX is a command-line knowledge base and documentation management system built in Python. It provides full-text search, tagging, project organization, and multiple interfaces for managing and accessing your knowledge base.

**For detailed information, see: [📚 Complete Documentation](docs/)**

## 🏗️ Architecture Summary

**Core Technologies:**
- **Python 3.13+** (minimum requirement)
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
python3.13 -m venv venv
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

## 🎯 Claude Code Integration Workflow

### Auto-Tagging for Project Management

When working with EMDX through Claude Code, automatically apply tags based on content patterns:

**Document Types:**
- `gameplan` - Strategic plans → 🎯
- `analysis` - Investigation results → 🔍  
- `notes` - General notes → 📝

**Workflow Status:**
- `active` - Currently working on → 🚀
- `done` - Completed → ✅
- `blocked` - Stuck/waiting → 🚧

**Outcomes (Success Tracking):**
- `success` - Worked as intended → 🎉
- `failed` - Didn't work → ❌
- `partial` - Mixed results → ⚡

### Integration Guidelines

When Claude Code helps with EMDX:

1. **Suggest tags** during save operations based on content
2. **Ask permission** before applying tags: "I detected this looks like a gameplan, should I tag it as `gameplan, active`?"
3. **Update tags** when project status changes
4. **Generate progress reports** from tag analytics
5. **Use consistent workflows** for project tracking

### Example Workflow
```bash
# Create gameplan with Claude Code assistance
echo "Gameplan: Implement user authentication system" | poetry run emdx save --title "Auth Gameplan" --tags "gameplan,active"

# Update status as work progresses
poetry run emdx tag 123 blocked
poetry run emdx untag 123 active

# Mark complete with outcome
poetry run emdx tag 123 done success
poetry run emdx untag 123 blocked
```

## 🚀 Quick Task Execution (`emdx run`)

The fastest way to run parallel tasks:

```bash
# Run multiple tasks in parallel
emdx run "analyze auth" "review tests" "check docs"

# With synthesis to combine outputs
emdx run --synthesize "task1" "task2" "task3"

# Dynamic discovery from shell commands
emdx run -d "git branch -r | grep feature" -t "Review {{task}}"

# Control concurrency
emdx run -j 3 "task1" "task2" "task3" "task4"
```

## 🔄 Workflow System for Multi-Agent Tasks

When working on tasks that benefit from parallel execution or multiple perspectives, use the workflow system instead of running individual commands.

### Core Workflows

| Workflow | Use When |
|----------|----------|
| `task_parallel` | Running multiple analysis or fix tasks in parallel |
| `parallel_fix` | Multiple code fixes that might touch same files (uses worktree isolation) |
| `parallel_analysis` | Getting multiple perspectives on a problem with synthesis |

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

### When to Use `emdx run` vs `emdx workflow`

| Use `emdx run` when... | Use `emdx workflow` when... |
|------------------------|----------------------------|
| Quick, ad-hoc parallel tasks | Complex multi-stage workflows |
| Simple task lists | Need iterative or adversarial modes |
| One-off discovery commands | Custom stage configurations |
| Just want tasks done fast | Need detailed run monitoring |

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

---

**Documentation Links:**
- [📚 Complete Documentation](docs/) - Full project guides
- [🏗️ Architecture](docs/architecture.md) - System design and code structure  
- [⚙️ Development Setup](docs/development-setup.md) - Contributing guide
- [📋 CLI Reference](docs/cli-api.md) - Complete command documentation