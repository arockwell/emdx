# EMDX Workflow Orchestration

Workflows are EMDX's most powerful feature for AI-assisted work. They let you chain multiple agent runs with different execution strategies—parallel for diverse perspectives, iterative for progressive refinement, or adversarial for rigorous critique.

## Overview

A workflow consists of **stages**, each with an **execution mode**:

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Stage 1   │───▶│   Stage 2   │───▶│   Stage 3   │
│  parallel   │    │ adversarial │    │   single    │
│   3 runs    │    │  3 phases   │    │  1 run      │
└─────────────┘    └─────────────┘    └─────────────┘
      │                  │                  │
      ▼                  ▼                  ▼
  synthesis          synthesis           output
```

Each stage's output becomes available to subsequent stages via template variables.

## Execution Modes

### Single Mode
Run once. The simplest mode for straightforward tasks.

```json
{
  "name": "generate",
  "mode": "single",
  "prompt": "Generate documentation for {{input}}"
}
```

### Parallel Mode
Run N times simultaneously, then synthesize results. Use when you want diverse perspectives.

```json
{
  "name": "research",
  "mode": "parallel",
  "runs": 3,
  "prompt": "Research {{input}} focusing on different aspects",
  "synthesis_prompt": "Combine these research findings into a comprehensive summary:\n\n{{outputs}}"
}
```

**How it works:**
1. Runs the prompt 3 times concurrently
2. Collects all outputs
3. Runs `synthesis_prompt` to combine them
4. Stores both individual outputs and synthesis for later stages

### Iterative Mode
Run N times sequentially, each building on the previous. Use for progressive refinement.

```json
{
  "name": "refine",
  "mode": "iterative",
  "runs": 3,
  "prompts": [
    "Create initial draft for {{input}}",
    "Improve this draft, focusing on clarity:\n{{prev_output}}",
    "Final polish, ensure consistency:\n{{prev_output}}"
  ]
}
```

**How it works:**
1. Runs first prompt
2. Passes output to second prompt as `{{prev_output}}`
3. Continues until all runs complete
4. Final output is the result of the last run

You can also use **iteration strategies** (predefined prompt sequences):

```json
{
  "name": "refine",
  "mode": "iterative",
  "runs": 3,
  "iteration_strategy": "progressive_refinement"
}
```

### Adversarial Mode
Advocate → Critic → Synthesizer pattern. Use to challenge assumptions and find weaknesses.

```json
{
  "name": "review",
  "mode": "adversarial",
  "prompt": "Review this code:\n{{input}}"
}
```

**How it works:**
1. **Advocate**: Makes the strongest case for the approach
2. **Critic**: Challenges the advocate, finds weaknesses
3. **Synthesizer**: Combines both perspectives into balanced output

### Dynamic Mode
Discover items at runtime, process each in parallel. Use for batch processing.

```json
{
  "name": "process_files",
  "mode": "dynamic",
  "discovery_command": "find . -name '*.py' -type f",
  "item_variable": "file",
  "prompt": "Analyze this Python file:\n{{file}}",
  "synthesis_prompt": "Summarize findings across all files:\n{{outputs}}",
  "max_concurrent": 5,
  "continue_on_failure": true
}
```

**How it works:**
1. Runs `discovery_command` to get list of items
2. Processes each item in parallel (up to `max_concurrent`)
3. Synthesizes all results
4. Optionally continues even if some items fail

## CLI Commands

### List Workflows

```bash
emdx workflow list                          # All workflows
emdx workflow list --category analysis      # Filter by category
emdx workflow list --all                    # Include inactive
emdx workflow list --format json            # JSON output
```

### Show Workflow Details

```bash
emdx workflow show deep_analysis
```

Output:
```
╭─ Workflow #3 ────────────────────────────────────────╮
│ Deep Analysis                                        │
│ Name: deep_analysis                                  │
│                                                      │
│ Multi-perspective analysis with synthesis            │
╰──────────────────────────────────────────────────────╯

Stages:
┏━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━┓
┃ # ┃ Name      ┃ Mode       ┃ Runs ┃ Strategy             ┃
┡━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━┩
│ 1 │ research  │ parallel   │ 3    │ -                    │
│ 2 │ critique  │ adversarial│ 3    │ -                    │
│ 3 │ synthesize│ single     │ 1    │ -                    │
└───┴───────────┴────────────┴──────┴──────────────────────┘

Statistics:
  Total runs: 47
  Success rate: 89.4%
  Last used: 2025-01-10 14:32:00
```

### Run a Workflow

```bash
# Basic run
emdx workflow run deep_analysis --doc 123

# With variables
emdx workflow run deep_analysis --doc 123 --var focus=security

# In isolated git worktree (recommended for parallel workflows)
emdx workflow run deep_analysis --doc 123 --worktree

# Custom base branch for worktree
emdx workflow run deep_analysis --doc 123 --worktree --base-branch develop

# Keep worktree after completion (for debugging)
emdx workflow run deep_analysis --doc 123 --worktree --keep-worktree

# Override dynamic stage discovery
emdx workflow run file_processor --discover "find . -name '*.ts'"

# Limit concurrent executions
emdx workflow run file_processor --max-concurrent 3
```

### Monitor Runs

```bash
# List recent runs
emdx workflow runs
emdx workflow runs --workflow deep_analysis    # Filter by workflow
emdx workflow runs --status running            # Filter by status
emdx workflow runs --limit 50                  # More results

# Check specific run status
emdx workflow status 42
```

Output:
```
╭─ Workflow Run #42 ────────────────────────────────────╮
│ Deep Analysis                                         │
│ Status: running                                       │
│ Current stage: critique                               │
╰───────────────────────────────────────────────────────╯

Stage Progress:
┏━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━┓
┃ Stage     ┃ Mode       ┃ Progress ┃ Status ┃ Tokens ┃ Duration ┃
┡━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━┩
│ research  │ parallel   │ 3/3      │ ✓      │ 4521   │ 12.3s    │
│ critique  │ adversarial│ 2/3      │ ⟳      │ 2103   │ 8.1s     │
│ synthesize│ single     │ 0/1      │ -      │ 0      │ -        │
└───────────┴────────────┴──────────┴────────┴────────┴──────────┘
```

### Iteration Strategies

```bash
emdx workflow strategies                    # List all strategies
emdx workflow strategies --category code    # Filter by category
```

Built-in strategies include:
- `progressive_refinement` - Draft → Improve → Polish
- `devil_advocate` - Propose → Challenge → Resolve
- `expert_perspectives` - Multiple expert viewpoints

## Creating Workflows

### From JSON File

Create `my-workflow.json`:

```json
{
  "stages": [
    {
      "name": "analyze",
      "mode": "parallel",
      "runs": 3,
      "prompt": "Analyze {{input}} from the perspective of: {{perspective}}",
      "synthesis_prompt": "Combine these analyses into a comprehensive report"
    },
    {
      "name": "recommend",
      "mode": "single",
      "prompt": "Based on this analysis:\n{{analyze.synthesis}}\n\nProvide actionable recommendations."
    }
  ],
  "variables": {
    "perspective": "security, performance, maintainability"
  }
}
```

```bash
emdx workflow create code-review \
  --display-name "Code Review" \
  --description "Multi-perspective code analysis" \
  --category analysis \
  --file my-workflow.json
```

### Stage Configuration Options

```json
{
  "name": "stage_name",
  "mode": "parallel",
  "runs": 3,
  "agent_id": 5,
  "prompt": "Custom prompt with {{variables}}",
  "prompts": ["First run", "Second run", "Third run"],
  "iteration_strategy": "progressive_refinement",
  "synthesis_prompt": "Combine outputs: {{outputs}}",
  "input": "{{prev_stage.output}}",
  "timeout_seconds": 300,
  "discovery_command": "find . -name '*.py'",
  "item_variable": "file",
  "max_concurrent": 5,
  "continue_on_failure": true
}
```

| Field | Description |
|-------|-------------|
| `name` | Unique stage identifier |
| `mode` | Execution mode: single, parallel, iterative, adversarial, dynamic |
| `runs` | Number of runs (for parallel/iterative) |
| `agent_id` | Optional: use specific agent instead of prompt |
| `prompt` | The prompt template |
| `prompts` | Per-run prompts (for iterative mode) |
| `iteration_strategy` | Use predefined prompt sequence |
| `synthesis_prompt` | How to combine parallel/dynamic outputs |
| `input` | Template for stage input (default: previous stage output) |
| `timeout_seconds` | Max execution time per run |
| `discovery_command` | Shell command for dynamic mode |
| `item_variable` | Variable name for discovered items |
| `max_concurrent` | Max parallel runs for dynamic mode |
| `continue_on_failure` | Keep going if some dynamic items fail |

### Template Variables

Access data from previous stages and inputs:

| Variable | Description |
|----------|-------------|
| `{{input}}` | Input document content |
| `{{input_title}}` | Input document title |
| `{{stage_name.output}}` | Output from named stage |
| `{{stage_name.synthesis}}` | Synthesis from parallel/dynamic stage |
| `{{stage_name.outputs}}` | All individual outputs (as list) |
| `{{prev_output}}` | Previous run's output (iterative mode) |
| `{{outputs}}` | All outputs for synthesis prompt |
| `{{item}}` | Current item (dynamic mode, or custom `item_variable`) |

## Git Worktree Integration

For workflows that modify files, use `--worktree` to run in an isolated git worktree:

```bash
emdx workflow run refactor --doc 123 --worktree
```

This:
1. Creates a new branch (`workflow-<timestamp>-<pid>-<random>`)
2. Creates a worktree in a sibling directory
3. Runs the workflow in that worktree
4. Cleans up the worktree on completion

Benefits:
- Parallel workflows don't conflict
- Your working directory stays clean
- Easy to review changes before merging

## Database Schema

Workflows are stored in these tables:

- **`workflows`** - Workflow configurations and definitions
- **`workflow_runs`** - Execution history and status
- **`workflow_stage_runs`** - Per-stage execution tracking
- **`workflow_individual_runs`** - Individual runs within stages
- **`iteration_strategies`** - Predefined prompt sequences

## Best Practices

1. **Start simple** - Begin with single-stage workflows, add complexity as needed
2. **Use worktrees** - Always use `--worktree` for workflows that modify files
3. **Set timeouts** - Prevent runaway executions with reasonable timeouts
4. **Monitor runs** - Use `emdx workflow status` to track progress
5. **Test prompts** - Validate prompts with single-mode stages first
6. **Name stages clearly** - Stage names become variable prefixes
7. **Handle failures** - Use `continue_on_failure` for dynamic batch processing

## Troubleshooting

### Workflow Not Found
```bash
emdx workflow list --all    # Check if it's inactive
```

### Run Fails
```bash
emdx workflow status <run_id>   # Check which stage failed
emdx log                         # View execution logs
```

### Worktree Issues
```bash
git worktree list                # See all worktrees
git worktree remove <path>       # Manual cleanup
```

### Variable Not Resolved
- Check stage names match exactly
- Verify previous stage completed successfully
- Use `{{stage_name.output}}` not `{{stage_name}}`
