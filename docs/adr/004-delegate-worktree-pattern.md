# ADR-004: Delegate/Worktree Pattern for Parallel Execution

## Status

Accepted

## Context

EMDX supports delegating tasks to Claude Code agents for parallel AI-assisted work. When multiple agents work simultaneously or when agents need to make code changes, they can conflict with each other and with the user's working directory. Requirements include:

- **Parallel execution**: Run multiple agent tasks concurrently (up to 10)
- **Isolation**: Agents shouldn't interfere with each other's file changes
- **PR creation**: Agents should be able to create pull requests for their changes
- **Clean state**: Each agent starts with a known-good codebase state
- **Result persistence**: Agent outputs are saved to the knowledge base for future reference

We considered several approaches:

1. **Sequential execution**: Run tasks one at a time (simple but slow)
2. **Shared directory**: All agents work in the same directory (fast but conflicts)
3. **Docker containers**: Isolated environments (heavyweight, complex setup)
4. **Git worktrees**: Lightweight directory copies sharing git history
5. **Temporary clones**: Full repo copies (wastes disk space, slow)

## Decision

We chose **git worktrees** for isolation combined with **inline result output** for immediate feedback.

### Key implementation details:

**Worktree creation** (`emdx/utils/git.py`):
```python
def create_worktree(base_branch: str = "main") -> tuple[str, str]:
    """Create a unique git worktree for isolated execution."""
    timestamp = int(time.time())
    random_suffix = random.randint(1000, 9999)
    pid = os.getpid()
    unique_id = f"{timestamp}-{pid}-{random_suffix}"
    branch_name = f"worktree-{unique_id}"
    worktree_dir = Path(repo_root).parent / f"emdx-worktree-{unique_id}"

    subprocess.run(
        ["git", "worktree", "add", "-b", branch_name, str(worktree_dir), base_branch],
        check=True
    )
    return str(worktree_dir), branch_name
```

**Delegate command patterns** (`emdx/commands/delegate.py`):
```bash
# Parallel tasks (each in its own worktree if needed)
emdx delegate "task1" "task2" "task3"

# With worktree isolation explicitly
emdx delegate --worktree "make risky changes"

# With PR creation (implies --worktree)
emdx delegate --pr "fix the auth bug"

```

**Result handling**:
- Results print to **stdout** (so calling Claude can read them inline)
- Results also persist to **emdx knowledge base** (so they're searchable later)
- Execution metadata tracked in database for monitoring

## Consequences

### Positive

- **True isolation**: Each agent has its own working directory and branch
- **No conflicts**: Parallel agents can't overwrite each other's changes
- **Clean PRs**: Each task can create a focused, single-purpose PR
- **Fast creation**: Worktrees are nearly instant (hardlinks, shared objects)
- **Space efficient**: Worktrees share the git object database
- **Inline results**: Results appear in stdout for immediate consumption by Claude
- **Persistent results**: Results also saved to knowledge base for later reference

### Negative

- **Git dependency**: Requires working git repository
- **Cleanup needed**: Worktrees must be cleaned up after completion
- **Branch proliferation**: Many short-lived branches created
- **Path complexity**: Agents must handle different working directories

### Mitigations

- **Automatic cleanup**: `cleanup_worktree()` removes worktrees on completion
- **Unique naming**: Timestamp + PID + random ensures no collisions
- **Branch cleanup**: Worktree branches can be deleted after PR merge
- **Fallback**: Non-worktree mode available for read-only tasks

## Execution Modes

### Standard (no worktree)

Best for read-only analysis tasks:
```bash
emdx delegate "analyze the auth module"
```
- Runs in current directory
- No file changes expected
- Fastest execution

### Parallel

Multiple tasks execute concurrently:
```bash
emdx delegate "task1" "task2" "task3" -j 5
```
- Up to 10 concurrent tasks
- Each can have its own worktree if `--worktree` specified

### Worktree-isolated

For tasks that modify files:
```bash
emdx delegate --worktree "refactor the database layer"
```
- Fresh worktree based on specified branch
- Changes isolated from main working directory

### With PR

For tasks that should create pull requests:
```bash
emdx delegate --pr "fix the auth bug"
```
- Implies `--worktree`
- Agent instructed to create PR after changes
- PR URL captured in output

## References

- [Git Worktrees Documentation](https://git-scm.com/docs/git-worktree)
- [EMDX Delegate Command](../cli-api.md#delegate)
- [Architecture Overview](../architecture.md)
