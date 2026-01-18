# EMDX Workflow System

The EMDX workflow system provides powerful orchestration for multi-agent executions. Workflows are **execution patterns** that define *how* to process tasks, while tasks are provided at runtime.

## When to Use What

EMDX has multiple ways to execute tasks, forming a "complexity ladder":

| Command | Use When | Example |
|---------|----------|---------|
| `emdx run "task"` | Single quick task | `emdx run "analyze auth module"` |
| `emdx run "t1" "t2"` | Multiple parallel tasks | `emdx run "fix X" "fix Y" -j 3` |
| `emdx each run <name>` | Reusable "for each X, do Y" | `emdx each run fix-conflicts` |
| `emdx workflow run <wf>` | Complex multi-stage workflows | `emdx workflow run deep_analysis` |
| `emdx cascade` | Ideas → code through stages | `emdx cascade add "idea"` |

### The Execution Ladder

Think of these tools as rungs on a ladder, from simplest to most powerful:

1. **`emdx run`** - The fastest path. Just describe what you want done. Great for one-off tasks.
2. **`emdx each`** - When you have a reusable pattern: "for each X from this command, do Y."
3. **`emdx workflow`** - When you need multi-stage processing, iteration, or adversarial modes.
4. **`emdx cascade`** - When transforming ideas through stages to working code.

Start at the top. Graduate down only when you need more power.

## Recommended Workflows

These are the core dynamic workflows designed for reuse with `--task` flags:

| Workflow | ID | Purpose | Best For |
|----------|-----|---------|----------|
| **task_parallel** | 31 | Run arbitrary tasks in parallel | Multi-task analysis, parallel fixes |
| **parallel_fix** | 30 | Parallel fixes with worktree isolation | Code fixes that touch same files |
| **parallel_analysis** | 24 | Parallel analysis with synthesis | Multi-perspective reviews |
| **dynamic_items** | 29 | Process items discovered at runtime | File processing, branch operations |

### Quick Examples

```bash
# Run 5 analysis tasks in parallel
emdx workflow run task_parallel \
  -t "Analyze authentication security" \
  -t "Review error handling patterns" \
  -t "Check for dead code" \
  -t "Evaluate test coverage" \
  -t "Audit logging practices" \
  --title "Security Audit Q1" \
  -j 3

# Fix multiple issues with worktree isolation (prevents conflicts)
emdx workflow run parallel_fix \
  -t "Fix type hints in auth module" \
  -t "Add missing docstrings to API" \
  -t "Remove deprecated imports" \
  --worktree --base-branch main

# Discover and process all Python files
emdx workflow run dynamic_items \
  --discover "find . -name '*.py' -type f | head -10" \
  -j 5
```

## Choosing the Right Tool: Decision Flowchart

EMDX offers three ways to run parallel tasks. Use this flowchart to pick the right one:

```
┌─────────────────────────────────────────────────────────────┐
│                 Do you have a task to run?                  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│        Is it a one-time or ad-hoc execution?                │
│                                                             │
│  YES → Will you run it again with same discovery pattern?   │
│        │                                                    │
│        ├─ NO  → Use `emdx run`                              │
│        │        (Quick parallel tasks, simple task lists)   │
│        │                                                    │
│        └─ YES → Use `emdx each`                             │
│                 (Save discovery + action for reuse)         │
│                                                             │
│  NO (Complex/multi-stage) → Use `emdx workflow run`         │
│     (Iterative, adversarial, multi-stage orchestration)     │
└─────────────────────────────────────────────────────────────┘
```

### Quick Reference Table

| Scenario | Tool | Example |
|----------|------|---------|
| Run 3 analysis tasks right now | `emdx run` | `emdx run "analyze auth" "review tests" "check docs"` |
| Process all Python files once | `emdx run` | `emdx run -d "fd -e py" -t "Review {{item}}"` |
| Repeatedly fix merge conflicts | `emdx each` | `emdx each create fix-conflicts --from "..." --do "..."` |
| For-each pattern you'll reuse | `emdx each` | `emdx each run fix-conflicts` |
| Multi-perspective code review | `emdx workflow` | `emdx workflow run parallel_analysis -t "review X"` |
| Progressive refinement (draft→polish) | `emdx workflow` | `emdx workflow run iterative_refine --doc 123` |
| Debate-style analysis | `emdx workflow` | `emdx workflow run adversarial_review -t "..." ` |
| Need synthesis of outputs | Both | `emdx run --synthesize` or workflow with synthesis_prompt |
| Worktree isolation needed | Both | `emdx workflow run X --worktree` or `emdx each --worktree` |

### Detailed Comparison

| Feature | `emdx run` | `emdx each` | `emdx workflow run` |
|---------|------------|-------------|---------------------|
| **Purpose** | Quick parallel execution | Reusable discovery+action | Complex orchestration |
| **Task Source** | CLI arguments or `-d` discovery | Saved `--from` command | CLI `-t` flags or doc ID |
| **Persistence** | None (one-shot) | Commands saved to DB | Workflows defined in DB |
| **Execution Modes** | Parallel only | Parallel only | Single, Parallel, Iterative, Adversarial, Dynamic |
| **Synthesis** | `--synthesize` flag | `--synthesize` flag | `synthesis_prompt` in config |
| **Variables** | None | None | Full template system |
| **Stage Chaining** | No | No | Yes (multi-stage pipelines) |
| **Worktree Isolation** | Auto when needed | `--worktree` flag | `--worktree` flag |
| **Best For** | Ad-hoc tasks | Repeated patterns | Production workflows |

### When to Graduate

**From `emdx run` to `emdx each`:**
- You're running the same discovery command repeatedly
- You want to share a pattern with your team
- The discovery logic is complex and worth saving

**From `emdx run`/`emdx each` to `emdx workflow`:**
- You need iterative refinement (draft → improve → polish)
- You want adversarial review (advocate → critic → synthesis)
- You're chaining multiple stages together
- You want detailed run tracking in the Activity view

## Core Concept: Execution Patterns vs Runtime Tasks

**Key Mental Model**: Workflows define the *shape* of execution. Tasks are the *data* you feed in.

```
Workflow = HOW to process (pattern, strategy, synthesis)
Tasks    = WHAT to process (provided at runtime via --task)
```

This separation means:
- One workflow can be reused for many different task sets
- The number of runs is determined by the number of tasks, not hardcoded
- Tasks can be strings (direct input) or document IDs (load content from DB)

## Execution Modes

EMDX supports five execution modes, each with different processing patterns.

### SINGLE
Run once with a single prompt.

```yaml
stages:
  - name: analyze
    mode: single
    prompt: "Analyze this codebase for security issues"
```

**Use case**: Simple, one-shot tasks like analysis or report generation.

### PARALLEL
Run N times simultaneously, then synthesize all outputs into one result.

```yaml
stages:
  - name: multi_perspective
    mode: parallel
    runs: 5
    prompt: "Review {{input}} from a {{perspective}} perspective"
    synthesis_prompt: "Synthesize these {{output_count}} reviews into a coherent summary:\n\n{{outputs}}"
```

**Use case**: Get multiple perspectives on the same problem, then combine insights.

With tasks (task-driven parallel):
```bash
emdx workflow run parallel_analysis \
  -t "Analyze authentication security" \
  -t "Analyze input validation" \
  -t "Analyze data encryption" \
  -j 3  # max 3 concurrent
```

### ITERATIVE
Run N times sequentially, with each run building on the previous output.

```yaml
stages:
  - name: refine
    mode: iterative
    runs: 3
    prompts:
      - "Create initial draft: {{input}}"
      - "Refine this draft, improving clarity: {{prev}}"
      - "Final polish, fix any remaining issues: {{prev}}"
```

**Use case**: Progressive refinement, where each iteration improves upon the last.

Template variables for iterative mode:
- `{{prev}}` - Output from the previous iteration
- `{{all_prev}}` - All previous outputs joined with separators
- `{{run_number}}` - Current iteration number (1-indexed)

### ADVERSARIAL
Three-role pattern: Advocate -> Critic -> Synthesizer.

```yaml
stages:
  - name: debate
    mode: adversarial
    runs: 3
    prompts:
      - "ADVOCATE: Argue strongly FOR this approach: {{input}}"
      - "CRITIC: Challenge this advocacy. What are the weaknesses?: {{prev}}"
      - "SYNTHESIS: Given the advocacy and criticism, provide balanced assessment:\n\nAdvocate: {{all_prev[0]}}\nCritic: {{prev}}"
```

**Use case**: Thorough analysis through debate, finding both strengths and weaknesses.

### DYNAMIC
Discover items at runtime via a shell command, then process each in parallel.

```yaml
stages:
  - name: process_files
    mode: dynamic
    discovery_command: "find . -name '*.py' -type f"
    item_variable: file
    max_concurrent: 5
    continue_on_failure: true
    prompt: "Analyze Python file: {{file}}"
    synthesis_prompt: "Summarize findings from all {{output_count}} files:\n\n{{outputs}}"
```

**Use case**: Process a dynamic list of items (files, branches, issues) discovered at runtime.

## CLI Commands

### List Workflows
```bash
# List all workflows
emdx workflow list

# Filter by category
emdx workflow list --category analysis

# Include inactive workflows
emdx workflow list --all

# JSON output
emdx workflow list --format json
```

### Show Workflow Details
```bash
emdx workflow show <name_or_id>
emdx workflow show parallel_analysis
emdx workflow show 5
```

### Run a Workflow
```bash
# Basic run with input document
emdx workflow run <workflow> --doc <doc_id>

# Run with tasks (task-driven execution)
emdx workflow run task_parallel \
  -t "Find irrelevant documentation" \
  -t "Identify dead code" \
  -t "Evaluate architecture"

# Add a custom title (shown in Activity view)
emdx workflow run task_parallel \
  -t "Security review" \
  --title "Q1 Security Audit"

# Tasks can be document IDs
emdx workflow run task_parallel -t 5182 -t 5183 -t 5184

# Mix strings and doc IDs
emdx workflow run task_parallel -t "Analyze auth" -t 5185

# Control concurrency
emdx workflow run task_parallel -t "task1" -t "task2" -t "task3" -j 2

# Override variables
emdx workflow run my_workflow --var topic=Security --var depth=deep

# Run in isolated worktree
emdx workflow run my_workflow --worktree --base-branch main

# Override discovery command for dynamic mode
emdx workflow run dynamic_analysis --discover "ls *.py"
```

### Monitor Runs
```bash
# List recent runs
emdx workflow runs

# Filter by workflow
emdx workflow runs --workflow parallel_analysis

# Filter by status
emdx workflow runs --status running

# Show detailed run status
emdx workflow status <run_id>
emdx workflow status 42
```

## Template System

Workflows use `{{variable}}` syntax for dynamic content.

### Standard Variables
| Variable | Description |
|----------|-------------|
| `{{input}}` | Input document content or previous stage output |
| `{{input_title}}` | Title of input document |
| `{{prev}}` | Previous iteration output (iterative/adversarial mode) |
| `{{all_prev}}` | All previous outputs as list |
| `{{run_number}}` | Current run number (1-indexed) |

### Task Variables (from --task flag)
| Variable | Description |
|----------|-------------|
| `{{item}}` | Item content (string or loaded document content) |
| `{{task_title}}` | Document title (if task was a doc ID) |
| `{{task_id}}` | Document ID (if task was a doc ID) |

### Auto-Loaded Document Variables

When you pass a variable like `doc_1=123` (where 123 is a document ID), the workflow system **automatically** creates three additional variables:

| Variable Pattern | Description |
|-----------------|-------------|
| `{{doc_N}}` | The original value (document ID) |
| `{{doc_N_content}}` | Full content of the referenced document |
| `{{doc_N_title}}` | Title of the referenced document |
| `{{doc_N_id}}` | Document ID (same as doc_N, for explicit reference) |

**Example Usage:**

```bash
# Pass two documents as variables
emdx workflow run my_workflow \
  --var doc_1=5182 \
  --var doc_2=5183

# In your workflow prompt template:
# "Compare {{doc_1_title}} with {{doc_2_title}}:
#
#  Document 1:
#  {{doc_1_content}}
#
#  Document 2:
#  {{doc_2_content}}"
```

**How It Works:**
1. Any variable matching the pattern `doc_N` (e.g., `doc_1`, `doc_2`, `doc_99`) is detected
2. If the value is an integer, it's treated as a document ID
3. The document is loaded from the database
4. Three derived variables are automatically created: `doc_N_content`, `doc_N_title`, `doc_N_id`
5. If the document doesn't exist, `doc_N_content` will contain an error message

**Use Cases:**
- Multi-document comparison workflows
- Parameterized analysis across document sets
- Template-based document processing

### Dynamic Mode Variables
| Variable | Description |
|----------|-------------|
| `{{item}}` | Current discovered item (configurable via `item_variable`) |
| `{{item_index}}` | Zero-based index of current item |
| `{{total_items}}` | Total number of discovered items |

### Parallel/Synthesis Variables
| Variable | Description |
|----------|-------------|
| `{{outputs}}` | All parallel outputs joined with separators |
| `{{output_count}}` | Number of outputs being synthesized |

### Stage Output Variables
| Variable | Description |
|----------|-------------|
| `{{stage_name.output}}` | Output from a named stage |
| `{{stage_name.output_id}}` | Document ID of stage output |
| `{{stage_name.synthesis}}` | Synthesis output from parallel stage |

### Indexed Access
```yaml
# Access specific item from a list
prompt: "First point was: {{all_prev[0]}}"
```

## StageConfig Reference

Each stage in a workflow is configured with these fields:

```yaml
stages:
  - name: string              # Required: unique stage name
    mode: string              # Required: single|parallel|iterative|adversarial|dynamic
    runs: int                 # Number of runs (default: 3)
    agent_id: int             # Optional: specific agent to use
    prompt: string            # Prompt template for this stage
    prompts: [string]         # Per-run prompts (for iterative/parallel)
    synthesis_prompt: string  # Prompt for synthesizing parallel/dynamic outputs
    input: string             # Template reference like "{{prev_stage.output}}"
    timeout_seconds: int      # Stage timeout (default: 3600)

    # Dynamic mode specific:
    discovery_command: string # Shell command that outputs items (one per line)
    item_variable: string     # Variable name for each item (default: "item")
    max_concurrent: int       # Max parallel executions (default: 10)
    continue_on_failure: bool # Keep processing if one item fails (default: true)
```

## Worktree Isolation

For parallel execution, EMDX can create isolated git worktrees to prevent conflicts.

### Why Worktrees?
When running multiple agents in parallel, they may:
- Modify the same files simultaneously
- Create conflicting git states
- Step on each other's changes

Worktree isolation gives each parallel task its own working directory.

### Using Worktrees
```bash
# Enable worktree isolation
emdx workflow run parallel_analysis --worktree

# Specify base branch
emdx workflow run parallel_analysis --worktree --base-branch develop

# Keep worktrees for debugging (not cleaned up)
emdx workflow run parallel_analysis --worktree --keep-worktree
```

### WorktreePool
The `WorktreePool` manages worktree lifecycle:
- Creates worktrees on-demand up to `max_concurrent`
- Reuses worktrees when possible
- Cleans up on completion (unless `--keep-worktree`)
- Resets worktrees between uses

## Practical Examples

### Example 1: Multi-Perspective Code Review
```bash
emdx workflow run parallel_analysis \
  -t "Review security aspects of auth.py" \
  -t "Review performance aspects of auth.py" \
  -t "Review maintainability of auth.py" \
  -j 3
```

### Example 2: Process All Python Files
Create a dynamic workflow or use discovery override:
```bash
emdx workflow run dynamic_analysis \
  --discover "find . -name '*.py' -type f | head -20" \
  -j 5
```

### Example 3: Iterative Document Refinement
```bash
# Create a document with initial content
echo "Draft: My initial ideas..." | emdx save --title "Draft"

# Run iterative refinement
emdx workflow run iterative_refine --doc 5200
```

### Example 4: Task-Driven Analysis with Document IDs
```bash
# Save analysis tasks as documents
echo "Analyze authentication flow" | emdx save --title "Auth Task"
echo "Analyze API security" | emdx save --title "API Task"

# Use document IDs as tasks
emdx workflow run task_parallel -t 5182 -t 5183
```

## Architecture Notes

### Execution Flow
1. CLI parses tasks and variables
2. Workflow config loaded from database
3. Tasks expanded into prompts (if task-driven)
4. Stages execute sequentially
5. Each stage may run parallel/iterative/etc. internally
6. Outputs saved as documents
7. Final synthesis (if applicable) creates summary document

### Document Groups
Parallel and dynamic executions create document groups:
- Individual outputs saved as "exploration" role
- Synthesis output saved as "primary" role
- Groups enable easy browsing of related outputs

### Database Tables
- `workflows` - Workflow definitions
- `workflow_runs` - Execution history
- `workflow_stage_runs` - Stage-level tracking
- `workflow_individual_runs` - Individual run tracking

For schema details, see [Database Design](database-design.md).
