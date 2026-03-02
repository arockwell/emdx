# ADR-002: Typer for CLI Framework

## Status

Accepted

## Context

EMDX requires a robust CLI framework to handle its command-line interface. The CLI is the primary interface for users, supporting commands like `save`, `find`, `view`, `task`, and many others. Requirements include:

- **Type safety**: Python type hints for better IDE support and error catching
- **Rich output**: Terminal formatting, colors, and tables for better UX
- **Command organization**: Nested subcommands (e.g., `emdx tag list`, `emdx task create`)
- **Auto-generated help**: Comprehensive `--help` output from function signatures
- **Maintainability**: Easy to add new commands without boilerplate

We considered several alternatives:

1. **argparse**: Python standard library, verbose but no dependencies
2. **Click**: Mature, decorator-based, widely used
3. **Typer**: Built on Click, uses type hints, auto-completion support
4. **Fire**: Auto-generates CLI from any Python object
5. **Docopt**: Generates parser from docstring, less common

## Decision

We chose **Typer** as the CLI framework.

### Key implementation details:

- **Entry point** in `emdx/main.py` using `typer.Typer()`
- **Command modules** in `emdx/commands/` (core.py, browse.py, tags.py, etc.)
- **Rich integration** via `typer[all]` for enhanced output formatting
- **Type hints** throughout for parameter validation and help generation

### Example command pattern:

```python
import typer
from typing import Optional

app = typer.Typer(name="task", help="Manage tasks")

@app.command()
def add(
    title: str = typer.Argument(..., help="Task title"),
    description: Optional[str] = typer.Option(None, "--description", "-D", help="Task description"),
    epic: Optional[int] = typer.Option(None, "--epic", help="Parent epic ID"),
    category: Optional[str] = typer.Option(None, "--cat", help="Task category"),
):
    """Create a new task."""
    # Implementation...
```

## Consequences

### Positive

- **Minimal boilerplate**: Type hints serve double duty as documentation and validation
- **Great IDE support**: Auto-completion, type checking, and inline documentation
- **Rich integration**: Built-in support for progress bars, tables, and colors via Rich
- **Click compatibility**: Can use Click features when needed (e.g., advanced callbacks)
- **Shell completion**: Automatic shell completion scripts for bash/zsh/fish
- **Consistent patterns**: All commands follow same structure, easy for contributors

### Negative

- **Dependency**: Adds typer + click + rich to dependency tree
- **Learning curve**: Developers need to understand Typer conventions
- **Magic behavior**: Some implicit behaviors (like argument vs option) can surprise newcomers

### Mitigations

- **Clear conventions**: CLAUDE.md documents command patterns for contributors
- **Dependency management**: Poetry lockfile ensures reproducible installs
- **Testing**: Commands are testable via typer.testing.CliRunner

## References

- [Typer Documentation](https://typer.tiangolo.com/)
- [Click Documentation](https://click.palletsprojects.com/)
- [Rich Documentation](https://rich.readthedocs.io/)
- [EMDX CLI Reference](../cli-api.md)
