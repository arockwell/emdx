# Migrating from Workflows to Swarm

This document outlines how to migrate from `emdx workflow` to `emdx swarm`.

## Why Migrate?

The swarm system is simpler and more powerful:

| Feature | workflow | swarm |
|---------|----------|-------|
| Isolation | Git worktrees only | k3d pods + worktrees |
| Parallelism | Thread pool | Kubernetes scheduling |
| Resource limits | None | Per-pod memory/CPU limits |
| Cleanup | Manual | Automatic pod lifecycle |
| Debugging | Log files | kubectl logs/exec |
| Complexity | High (stages, synthesis modes) | Low (just run tasks) |

## Command Mapping

### Basic Parallel Execution

```bash
# OLD: workflow
emdx workflow run task_parallel -t "task1" -t "task2" -t "task3"

# NEW: swarm
emdx swarm run "task1" "task2" "task3"
```

### With Synthesis

```bash
# OLD: workflow with synthesis
emdx workflow run task_parallel -t "analyze auth" -t "analyze api" --synthesis-mode aggregate

# NEW: swarm with synthesis
emdx swarm run --synthesize "analyze auth" "analyze api"
```

### With Worktree Isolation

```bash
# OLD: workflow with worktrees
emdx workflow run parallel_fix -t "fix1" -t "fix2" --worktree

# NEW: swarm (k3d provides better isolation by default)
emdx swarm run "fix1" "fix2"

# Or for local mode with worktrees only:
emdx swarm run --local "fix1" "fix2"
```

### From Document IDs

```bash
# OLD: workflow from docs
emdx workflow run task_parallel -t 5182 -t 5183

# NEW: swarm from docs (use --from with emdx view)
emdx swarm run "$(emdx view 5182 --raw)" "$(emdx view 5183 --raw)"

# Or better - use a discovery command
emdx swarm run --from "emdx find --tags bug,active --format id | xargs -I{} emdx view {} --raw"
```

### Concurrency Control

```bash
# OLD: workflow jobs
emdx workflow run task_parallel -t "t1" -t "t2" -t "t3" -j 2

# NEW: swarm jobs
emdx swarm run -j 2 "t1" "t2" "t3"
```

## Features NOT Migrated (Intentionally)

These workflow features are intentionally NOT in swarm because they add complexity without clear value:

1. **Adversarial mode** - Let Claude handle this in the prompt
2. **Iterative mode** - Use a bash loop instead
3. **Custom stages** - Just run multiple swarm commands
4. **Stage dependencies** - Use sequential swarm runs

The philosophy: keep swarm simple. Complex orchestration should be in your own scripts, not in EMDX.

## Cluster Management

Swarm adds cluster management commands:

```bash
# Start the battlestation
emdx swarm cluster start

# Check status
emdx swarm cluster status

# Stop (preserves state)
emdx swarm cluster stop

# Delete entirely
emdx swarm cluster delete
```

## When to Use Local Mode

Use `--local` when:
- k3d is not installed
- Quick one-off tasks
- Debugging agent scripts
- Network restrictions

```bash
emdx swarm run --local "task1" "task2"
```

Local mode uses parallel subprocesses with git worktree isolation (same as old workflow system).

## Resource Configuration

Swarm lets you configure resources per task:

```bash
# Give agents more memory (for large codebases)
emdx swarm run --memory 6Gi "analyze huge repo"

# Limit concurrency (don't melt laptop)
emdx swarm run -j 4 "t1" "t2" "t3" "t4" "t5" "t6"

# Custom timeout
emdx swarm run --timeout 1200 "long running task"
```

## Deprecation Timeline

1. **Now**: Both workflow and swarm available
2. **v0.11**: workflow marked as deprecated in help
3. **v0.12**: workflow removed

The swarm system is the future. Migrate when ready.
