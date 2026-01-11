# emdx

[![Version](https://img.shields.io/badge/version-0.7.0-blue.svg)](https://github.com/arockwell/emdx/releases)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

**A terminal-native knowledge base with full-text search, emoji tags, and AI workflow orchestration.**

Stop losing notes in scattered markdown files. EMDX gives you instant search across all your documents, smart tagging with emoji aliases, and powerful multi-stage AI workflows that run agents in parallel, iteratively, or adversarially.

## Key Features

- **Instant Search** - SQLite FTS5 full-text search with ranking
- **Emoji Tags** - Type `gameplan` and get 🎯, type `active` and get 🚀
- **AI Workflows** - Multi-stage orchestration: parallel, iterative, and adversarial execution modes
- **Rich TUI** - Vim-style navigation across documents, files, git diffs, and logs
- **Git Worktrees** - Run parallel workflows in isolated worktrees automatically
- **Zero Config** - SQLite backend, no server required

## Quick Start

```bash
# Install
git clone https://github.com/arockwell/emdx.git
cd emdx && pip install -e .

# Save your first document
echo "Remember to refactor the auth module" | emdx save --title "Auth TODO" --tags "bug,active"

# Search
emdx find "auth"
emdx find --tags "active"

# Browse in TUI
emdx gui
```

## AI Workflows

The workflow system is EMDX's most powerful feature. Chain multiple AI agent runs with different execution strategies.

### Execution Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| **single** | Run once | Simple tasks |
| **parallel** | Run N times simultaneously, synthesize results | Get diverse perspectives, then combine |
| **iterative** | Run N times sequentially, each building on previous | Refine and improve progressively |
| **adversarial** | Advocate → Critic → Synthesizer | Challenge assumptions, find weaknesses |
| **dynamic** | Discover items at runtime, process each in parallel | Process all files matching a pattern |

### Example: Deep Analysis Workflow

```bash
# Run a multi-stage analysis workflow
emdx workflow run deep_analysis --doc 123

# Run in isolated git worktree (for parallel safety)
emdx workflow run deep_analysis --doc 123 --worktree

# Pass variables to customize behavior
emdx workflow run deep_analysis --doc 123 --var focus=security --var depth=thorough
```

### Workflow Commands

```bash
emdx workflow list                    # List all workflows
emdx workflow show <name>             # Show workflow stages and stats
emdx workflow run <name> --doc <id>   # Run workflow on a document
emdx workflow runs                    # List recent workflow runs
emdx workflow status <run_id>         # Check run progress
emdx workflow strategies              # List iteration strategies
```

### Creating Custom Workflows

Create a workflow definition file:

```json
{
  "stages": [
    {
      "name": "research",
      "mode": "parallel",
      "runs": 3,
      "prompt": "Research {{input}} from different angles",
      "synthesis_prompt": "Combine these research findings into a coherent summary"
    },
    {
      "name": "critique",
      "mode": "adversarial",
      "prompt": "Analyze: {{research.synthesis}}"
    },
    {
      "name": "final",
      "mode": "single",
      "prompt": "Create final report from {{critique.output}}"
    }
  ]
}
```

```bash
emdx workflow create my-workflow --display-name "My Workflow" --file workflow.json
```

See [Workflows Guide](docs/workflows.md) for full documentation.

## Core Concepts

### Documents
Every piece of content is a **document** with a unique ID. Documents belong to **projects** (auto-detected from git repos).

```bash
emdx save notes.md                    # Save a file
echo "quick note" | emdx save --title "Note"  # Save from stdin
emdx view 42                          # View document #42
emdx edit 42                          # Edit in $EDITOR
```

### Emoji Tags
Tags use emoji for visual density. Type text aliases instead of hunting for emoji:

| Type this | Get this | Use for |
|-----------|----------|---------|
| `gameplan`, `plan` | 🎯 | Strategic documents |
| `analysis`, `research` | 🔍 | Investigations |
| `notes`, `memo` | 📝 | General notes |
| `docs` | 📚 | Documentation |
| `active`, `working` | 🚀 | Currently in progress |
| `done`, `complete` | ✅ | Finished work |
| `blocked`, `stuck` | 🚧 | Waiting on something |
| `success`, `win` | 🎉 | Positive outcome |
| `failed` | ❌ | Negative outcome |
| `bug`, `issue` | 🐛 | Problems to fix |
| `feature` | ✨ | New functionality |
| `urgent`, `critical` | 🚨 | High priority |
| `refactor` | 🔧 | Code improvements |

```bash
emdx save plan.md --tags "gameplan,active"
emdx tag 42 analysis done success
emdx find --tags "active"
```

## Essential Commands

```bash
# Save content
emdx save file.md                         # Save file
echo "text" | emdx save --title "Title"   # Save from stdin (CORRECT)

# Search
emdx find "search terms"                  # Full-text search
emdx find --tags "tag1,tag2"              # Search by tags

# Browse
emdx list                                 # List all documents
emdx recent                               # Recently accessed
emdx view <id>                            # View document
emdx edit <id>                            # Edit in $EDITOR

# Tags
emdx tag <id> tag1 tag2                   # Add tags
emdx tags                                 # List all tags
emdx legend                               # Show emoji alias reference

# Agents
emdx agent list                           # List agents
emdx agent run <name> --doc <id>          # Run agent on document

# Workflows
emdx workflow list                        # List workflows
emdx workflow run <name> --doc <id>       # Run workflow

# TUI
emdx gui                                  # Launch interactive browser
```

## AI Integration

EMDX is designed for Claude Code and AI assistants.

### For AI Agents: Critical Syntax

```bash
# CORRECT: Save text via stdin
echo "My content here" | emdx save --title "Title"

# WRONG: This looks for a FILE named "My content here"
emdx save "My content here"
```

### Agents vs Workflows

| Feature | Agents | Workflows |
|---------|--------|-----------|
| Complexity | Single task | Multi-stage pipelines |
| Execution | One run | Multiple runs with different modes |
| Output | Single result | Synthesized from multiple runs |
| Use case | Quick tasks | Deep analysis, code review |

```bash
# Simple: run an agent
emdx agent run code-reviewer --doc 123

# Powerful: run a multi-stage workflow
emdx workflow run deep_analysis --doc 123 --worktree
```

See [AI Agents Guide](docs/ai-agents.md) for agent details.

## TUI Browser

Launch with `emdx gui`. Vim-style keybindings:

| Key | Action |
|-----|--------|
| `j/k` | Navigate down/up |
| `Enter` | Select/open |
| `e` | Edit with vim |
| `f` | File browser mode |
| `d` | Git diff browser |
| `l` | Log browser |
| `a` | Agent browser |
| `x` | Execute with Claude |
| `/` | Search |
| `q` | Quit/back |

### Browser Modes

- **Documents** (default) - Browse and manage your knowledge base
- **Files** (`f`) - Browse filesystem with preview
- **Git** (`d`) - Visual diff viewer, worktree switching
- **Logs** (`l`) - Execution monitoring
- **Agents** (`a`) - AI agent management

## Configuration

| Setting | Location | Notes |
|---------|----------|-------|
| Database | `~/.emdx/emdx.db` | Created automatically |
| Editor | `$EDITOR` env var | For external editing |
| GitHub | `GITHUB_TOKEN` or `gh auth login` | For GitHub integration |

## Documentation

- [Workflows Guide](docs/workflows.md) - Multi-stage AI workflow orchestration
- [AI Agents Guide](docs/ai-agents.md) - Create and run custom AI agents
- [CLI Reference](docs/cli-api.md) - Complete command documentation
- [Architecture](docs/architecture.md) - System design and code structure
- [UI Guide](docs/ui-architecture.md) - TUI components and theming
- [Development Setup](docs/development-setup.md) - Contributing guide

## Contributing

```bash
git clone https://github.com/arockwell/emdx.git
cd emdx
poetry install
poetry run emdx --help
```

See [Development Setup](docs/development-setup.md) for testing and code quality guidelines.

## License

MIT License - see LICENSE file for details.
