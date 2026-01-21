# Cursor CLI Support Implementation Plan

## Executive Summary

This document outlines a comprehensive plan to add Cursor CLI support to EMDX's execution system. The analysis reveals that **adding Cursor support is highly feasible** due to:

1. **Near-identical JSON output formats** between Claude and Cursor CLIs
2. **Single execution funnel** - all commands converge through `claude_executor.py`
3. **Well-structured abstractions** already in place (`ExecutionConfig`, `ExecutionResult`)
4. **Minimal CLI flag differences** requiring only minor adaptations

**Estimated Total Effort**: 1-2 days for production-ready implementation

---

## Key Findings

### CLI Interface Comparison

| Aspect | Claude CLI | Cursor CLI | Compatibility |
|--------|-----------|------------|---------------|
| **Command** | `claude` | `cursor agent` | Different binary |
| **Prompt flag** | `--print <prompt>` | `-p` + positional | Different syntax |
| **Output format** | `--output-format stream-json` | `--output-format stream-json` | ✅ Identical |
| **Model flag** | `--model <model>` | `--model <model>` | ✅ Identical |
| **Tool control** | `--allowedTools X,Y,Z` | `--force` (all tools) | Different approach |
| **Verbose** | `--verbose` (required for stream-json) | Not required | Claude-specific |
| **Workspace** | Uses `cwd` | `--workspace <path>` | Optional flag |

### JSON Output Format Compatibility

**Critical Finding**: Both CLIs produce nearly identical NDJSON output!

| Message Type | Claude | Cursor | Notes |
|--------------|--------|--------|-------|
| `system/init` | ✅ | ✅ | Cursor adds `apiKeySource`, Claude adds `tools` |
| `user` | ❌ | ✅ | Cursor echoes user input |
| `assistant` | ✅ | ✅ | Claude has richer metadata |
| `result` | ✅ | ✅ | Claude has `total_cost_usd`, Cursor has `request_id` |

**Parser Impact**: A unified parser can handle both with source detection on first message.

### Hardcoded References Inventory

| Location | Reference | Change Required |
|----------|-----------|-----------------|
| `services/claude_executor.py:108,250` | `cmd = ["claude", ...]` | Parameterize binary |
| `utils/environment.py:16` | `REQUIRED_COMMANDS = ["claude", "git"]` | Make configurable |
| `utils/environment.py:55-63,141-149` | Claude version checks | Add Cursor checks |
| `config/constants.py:186` | `DEFAULT_CLAUDE_MODEL` | Add Cursor models |

---

## Architecture Design

### Strategy Pattern for CLI Executors

```
┌─────────────────────────────────────────────────────────────────┐
│                     USER COMMANDS                               │
│         (emdx run, agent, each, workflow, cascade)              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                   UnifiedExecutor                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                  ExecutionConfig                         │   │
│  │  + cli_tool: Literal["claude", "cursor"] = "claude"     │   │
│  │  + prompt: str                                           │   │
│  │  + model: Optional[str]  # None = use default           │   │
│  │  + allowed_tools: List[str]                              │   │
│  │  + working_dir: str                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                           │                                     │
│                           ▼                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │               CliExecutorFactory                         │   │
│  │  get_executor(cli_tool) -> CliExecutor                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │
           ┌───────────────┴───────────────┐
           ▼                               ▼
┌─────────────────────┐         ┌─────────────────────┐
│  ClaudeCliExecutor  │         │  CursorCliExecutor  │
│  - build_command()  │         │  - build_command()  │
│  - parse_output()   │         │  - parse_output()   │
│  - get_models()     │         │  - get_models()     │
└─────────────────────┘         └─────────────────────┘
           │                               │
           ▼                               ▼
┌─────────────────────┐         ┌─────────────────────┐
│ claude --print ...  │         │ cursor agent -p ... │
└─────────────────────┘         └─────────────────────┘
```

### New File Structure

```
emdx/
├── services/
│   ├── cli_executor/                    # NEW: CLI executor package
│   │   ├── __init__.py                  # Export factory and base
│   │   ├── base.py                      # CliExecutor ABC
│   │   ├── claude.py                    # ClaudeCliExecutor
│   │   ├── cursor.py                    # CursorCliExecutor
│   │   └── factory.py                   # CliExecutorFactory
│   ├── claude_executor.py               # MODIFY: Use factory
│   └── unified_executor.py              # MODIFY: Add cli_tool field
├── config/
│   ├── constants.py                     # MODIFY: Add CLI config
│   └── cli_config.py                    # NEW: CLI-specific settings
├── utils/
│   ├── environment.py                   # MODIFY: Detect both CLIs
│   └── output_parser.py                 # MODIFY: Unified parsing
└── workflows/
    └── output_parser.py                 # MODIFY: Source-aware parsing
```

---

## Implementation Phases

### Phase 1: Core Abstraction (4-6 hours)

**Goal**: Create CLI executor abstraction without breaking existing functionality.

#### 1.1 Create `cli_config.py`

```python
# emdx/config/cli_config.py
from dataclasses import dataclass
from typing import Literal, Dict, List, Optional
from enum import Enum

class CliTool(str, Enum):
    CLAUDE = "claude"
    CURSOR = "cursor"

@dataclass
class CliConfig:
    """Configuration for a CLI tool."""
    binary: str                          # "claude" or "cursor agent"
    prompt_flag: str                     # "--print" or "-p"
    output_format_flag: str              # "--output-format"
    model_flag: str                      # "--model"
    requires_verbose: bool               # Claude needs --verbose for stream-json
    supports_allowed_tools: bool         # Claude has --allowedTools
    force_flag: Optional[str]            # Cursor uses --force
    workspace_flag: Optional[str]        # Cursor uses --workspace
    default_model: str                   # Default model for this CLI

CLI_CONFIGS: Dict[CliTool, CliConfig] = {
    CliTool.CLAUDE: CliConfig(
        binary="claude",
        prompt_flag="--print",
        output_format_flag="--output-format",
        model_flag="--model",
        requires_verbose=True,
        supports_allowed_tools=True,
        force_flag=None,
        workspace_flag=None,
        default_model="claude-opus-4-5-20251101",
    ),
    CliTool.CURSOR: CliConfig(
        binary="cursor agent",
        prompt_flag="-p",
        output_format_flag="--output-format",
        model_flag="--model",
        requires_verbose=False,
        supports_allowed_tools=False,
        force_flag="--force",
        workspace_flag="--workspace",
        default_model="auto",
    ),
}

# Model mappings for cross-CLI compatibility
MODEL_ALIASES = {
    "opus": {"claude": "claude-opus-4-5-20251101", "cursor": "opus-4.5"},
    "sonnet": {"claude": "claude-sonnet-4-5-20250929", "cursor": "sonnet-4.5"},
    "auto": {"claude": "claude-sonnet-4-5-20250929", "cursor": "auto"},
}
```

#### 1.2 Create `CliExecutor` Base Class

```python
# emdx/services/cli_executor/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any

@dataclass
class CliCommand:
    """Represents a CLI command to execute."""
    args: List[str]
    env: Dict[str, str]
    cwd: Optional[str]

@dataclass
class CliResult:
    """Result from CLI execution."""
    success: bool
    output: str
    error: Optional[str]
    exit_code: int
    tokens_used: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int

class CliExecutor(ABC):
    """Abstract base class for CLI executors."""

    @abstractmethod
    def build_command(
        self,
        prompt: str,
        model: Optional[str],
        allowed_tools: Optional[List[str]],
        output_format: str,
        working_dir: Optional[str],
    ) -> CliCommand:
        """Build the CLI command to execute."""
        pass

    @abstractmethod
    def parse_result(self, stdout: str, stderr: str, exit_code: int) -> CliResult:
        """Parse CLI output into structured result."""
        pass

    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Get list of available models for this CLI."""
        pass

    @abstractmethod
    def validate_environment(self) -> tuple[bool, Dict[str, Any]]:
        """Validate that the CLI is properly installed."""
        pass
```

#### 1.3 Implement `ClaudeCliExecutor`

```python
# emdx/services/cli_executor/claude.py
from .base import CliExecutor, CliCommand, CliResult
from ..config.cli_config import CLI_CONFIGS, CliTool

class ClaudeCliExecutor(CliExecutor):
    def __init__(self):
        self.config = CLI_CONFIGS[CliTool.CLAUDE]

    def build_command(
        self,
        prompt: str,
        model: Optional[str],
        allowed_tools: Optional[List[str]],
        output_format: str = "stream-json",
        working_dir: Optional[str] = None,
    ) -> CliCommand:
        cmd = [
            self.config.binary,
            self.config.prompt_flag, prompt,
            self.config.output_format_flag, output_format,
            self.config.model_flag, model or self.config.default_model,
        ]

        if self.config.requires_verbose and output_format == "stream-json":
            cmd.append("--verbose")

        if allowed_tools and self.config.supports_allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])

        return CliCommand(args=cmd, env={}, cwd=working_dir)

    def parse_result(self, stdout: str, stderr: str, exit_code: int) -> CliResult:
        # Extract from __RAW_RESULT_JSON__ marker (existing logic)
        # ...existing parsing logic from output_parser.py...
        pass
```

#### 1.4 Implement `CursorCliExecutor`

```python
# emdx/services/cli_executor/cursor.py
from .base import CliExecutor, CliCommand, CliResult
from ..config.cli_config import CLI_CONFIGS, CliTool

class CursorCliExecutor(CliExecutor):
    def __init__(self):
        self.config = CLI_CONFIGS[CliTool.CURSOR]

    def build_command(
        self,
        prompt: str,
        model: Optional[str],
        allowed_tools: Optional[List[str]],
        output_format: str = "stream-json",
        working_dir: Optional[str] = None,
    ) -> CliCommand:
        # cursor agent uses positional prompt with -p flag
        cmd = ["cursor", "agent"]
        cmd.append(self.config.prompt_flag)  # -p
        cmd.extend([self.config.output_format_flag, output_format])
        cmd.extend([self.config.model_flag, model or self.config.default_model])

        # Cursor doesn't have --allowedTools, use --force for full access
        if allowed_tools and self.config.force_flag:
            cmd.append(self.config.force_flag)

        if working_dir and self.config.workspace_flag:
            cmd.extend([self.config.workspace_flag, working_dir])

        # Add prompt as positional argument at end
        cmd.append(prompt)

        return CliCommand(args=cmd, env={}, cwd=working_dir)

    def parse_result(self, stdout: str, stderr: str, exit_code: int) -> CliResult:
        # Parse Cursor's NDJSON output (similar to Claude but without cost)
        # ...
        pass
```

#### 1.5 Create Factory

```python
# emdx/services/cli_executor/factory.py
from typing import Optional
from .base import CliExecutor
from .claude import ClaudeCliExecutor
from .cursor import CursorCliExecutor
from ..config.cli_config import CliTool

_executors = {
    CliTool.CLAUDE: ClaudeCliExecutor,
    CliTool.CURSOR: CursorCliExecutor,
}

def get_cli_executor(cli_tool: Optional[str] = None) -> CliExecutor:
    """Get the appropriate CLI executor.

    Args:
        cli_tool: "claude", "cursor", or None (uses default/env var)

    Returns:
        CliExecutor instance
    """
    if cli_tool is None:
        # Check environment variable, default to Claude
        import os
        cli_tool = os.environ.get("EMDX_CLI_TOOL", "claude")

    tool = CliTool(cli_tool)
    return _executors[tool]()
```

### Phase 2: Integration (2-4 hours)

**Goal**: Wire up the abstraction to existing code paths.

#### 2.1 Update `ExecutionConfig`

```python
# emdx/services/unified_executor.py
@dataclass
class ExecutionConfig:
    prompt: str
    working_dir: str = field(default_factory=os.getcwd)
    title: str = "CLI Execution"
    doc_id: Optional[int] = None
    output_instruction: Optional[str] = None
    allowed_tools: List[str] = field(default_factory=lambda: DEFAULT_ALLOWED_TOOLS.copy())
    timeout_seconds: int = 300
    cli_tool: str = "claude"  # NEW: "claude" or "cursor"
    model: Optional[str] = None  # NEW: Override default model
```

#### 2.2 Update `execute_claude_sync`

```python
# emdx/services/claude_executor.py
from .cli_executor.factory import get_cli_executor

def execute_cli_sync(
    task: str,
    execution_id: int,
    log_file: Path,
    cli_tool: str = "claude",
    model: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
    working_dir: Optional[str] = None,
    doc_id: Optional[str] = None,
    timeout: int = 300,
) -> dict:
    """Execute a task with specified CLI tool synchronously."""

    executor = get_cli_executor(cli_tool)

    # Validate environment
    is_valid, env_info = executor.validate_environment()
    if not is_valid:
        return {"success": False, "error": f"Environment validation failed: {env_info}"}

    # Build command
    cmd_obj = executor.build_command(
        prompt=task,
        model=model,
        allowed_tools=allowed_tools or DEFAULT_ALLOWED_TOOLS,
        output_format="text",  # sync uses text
        working_dir=working_dir,
    )

    # Execute
    result = subprocess.run(
        cmd_obj.args,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cmd_obj.cwd,
        env={**os.environ, **cmd_obj.env},
    )

    # Parse result
    cli_result = executor.parse_result(result.stdout, result.stderr, result.returncode)

    return {
        "success": cli_result.success,
        "output": cli_result.output,
        "error": cli_result.error,
        "exit_code": cli_result.exit_code,
    }

# Keep backward compatibility
def execute_claude_sync(*args, **kwargs):
    """Backward compatible wrapper."""
    return execute_cli_sync(*args, cli_tool="claude", **kwargs)
```

#### 2.3 Update `environment.py`

```python
# emdx/utils/environment.py
class EnvironmentValidator:
    def __init__(self, cli_tool: str = "claude"):
        self.cli_tool = cli_tool
        self.REQUIRED_COMMANDS = self._get_required_commands()

    def _get_required_commands(self) -> List[str]:
        base = ["git"]
        if self.cli_tool == "claude":
            return base + ["claude"]
        elif self.cli_tool == "cursor":
            return base + ["cursor"]
        return base

    def check_commands(self) -> None:
        for cmd in self.REQUIRED_COMMANDS:
            path = shutil.which(cmd)
            if path:
                self.info[f"{cmd}_path"] = path
                self._check_version(cmd)
            else:
                self.errors.append(f"Required command '{cmd}' not found in PATH")

    def _check_version(self, cmd: str) -> None:
        try:
            if cmd == "claude":
                result = subprocess.run(["claude", "--version"], ...)
            elif cmd == "cursor":
                result = subprocess.run(["cursor", "agent", "--version"], ...)
            # ...
        except Exception as e:
            self.warnings.append(f"Could not get version for {cmd}: {e}")
```

### Phase 3: User Interface (1-2 hours)

**Goal**: Expose CLI selection to users.

#### 3.1 Add CLI Flag to Commands

```python
# emdx/commands/run.py
@app.command()
def run(
    tasks: List[str] = typer.Argument(...),
    cli_tool: str = typer.Option("claude", "--cli", "-C", help="CLI tool: claude or cursor"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="Model to use"),
    # ... existing options
):
    """Run tasks with specified CLI tool."""
    # ...
```

#### 3.2 Add Environment Variable Support

```python
# emdx/config/cli_config.py
import os

def get_default_cli_tool() -> str:
    """Get default CLI tool from environment or config."""
    return os.environ.get("EMDX_CLI_TOOL", "claude")

def get_default_model(cli_tool: str) -> str:
    """Get default model for CLI tool."""
    env_key = f"EMDX_{cli_tool.upper()}_MODEL"
    if model := os.environ.get(env_key):
        return model
    return CLI_CONFIGS[CliTool(cli_tool)].default_model
```

#### 3.3 Add Configuration File Support

```yaml
# ~/.config/emdx/cli.yaml
default_cli: cursor  # or "claude"

claude:
  model: claude-opus-4-5-20251101
  allowed_tools:
    - Read
    - Write
    - Edit
    - Bash

cursor:
  model: auto
  force_mode: true  # Use --force flag
```

### Phase 4: Testing & Documentation (2-3 hours)

#### 4.1 Unit Tests

```python
# tests/test_cli_executor.py
import pytest
from emdx.services.cli_executor.factory import get_cli_executor
from emdx.services.cli_executor.claude import ClaudeCliExecutor
from emdx.services.cli_executor.cursor import CursorCliExecutor

def test_factory_returns_claude_by_default():
    executor = get_cli_executor()
    assert isinstance(executor, ClaudeCliExecutor)

def test_factory_returns_cursor():
    executor = get_cli_executor("cursor")
    assert isinstance(executor, CursorCliExecutor)

def test_claude_command_building():
    executor = ClaudeCliExecutor()
    cmd = executor.build_command(
        prompt="test prompt",
        model="claude-sonnet-4-5-20250929",
        allowed_tools=["Read", "Write"],
        output_format="stream-json",
    )
    assert "claude" in cmd.args
    assert "--print" in cmd.args
    assert "--verbose" in cmd.args
    assert "--allowedTools" in cmd.args

def test_cursor_command_building():
    executor = CursorCliExecutor()
    cmd = executor.build_command(
        prompt="test prompt",
        model="auto",
        allowed_tools=["Read", "Write"],
        output_format="stream-json",
    )
    assert "cursor" in cmd.args
    assert "agent" in cmd.args
    assert "-p" in cmd.args
    assert "--verbose" not in cmd.args  # Cursor doesn't need it
```

#### 4.2 Integration Tests

```python
# tests/integration/test_cli_execution.py
@pytest.mark.integration
@pytest.mark.skipif(not shutil.which("cursor"), reason="Cursor not installed")
def test_cursor_simple_execution():
    result = execute_cli_sync(
        task="respond with just hello",
        execution_id=1,
        log_file=Path("/tmp/test.log"),
        cli_tool="cursor",
        model="auto",
        timeout=30,
    )
    assert result["success"]
    assert "hello" in result["output"].lower()
```

---

## Risk Assessment

### Low Risk
- **Output format parsing**: Both CLIs use nearly identical NDJSON
- **Command building**: Well-understood CLI interfaces
- **Backward compatibility**: Factory pattern preserves existing behavior

### Medium Risk
- **Tool restrictions**: Cursor lacks `--allowedTools`, uses `--force` instead
- **Model mapping**: Different model names between CLIs
- **Cost tracking**: Cursor doesn't report token costs

### Mitigation Strategies
1. **Tool restrictions**: Document that Cursor has all-or-nothing tool access
2. **Model mapping**: Create alias mapping (e.g., "opus" → appropriate model per CLI)
3. **Cost tracking**: Return 0/None for Cursor cost fields, log warning

---

## Migration Path

### For Existing Users

1. **No breaking changes**: Default remains Claude
2. **Opt-in**: Set `EMDX_CLI_TOOL=cursor` or use `--cli cursor` flag
3. **Gradual rollout**: Test with specific commands before full migration

### For New Users

1. **Auto-detection**: If only Cursor is installed, use it by default
2. **First-run prompt**: Ask which CLI to use if both are available
3. **Documentation**: Clear comparison of CLI capabilities

---

## Timeline

| Phase | Tasks | Effort | Dependencies |
|-------|-------|--------|--------------|
| 1 | Core abstraction | 4-6 hours | None |
| 2 | Integration | 2-4 hours | Phase 1 |
| 3 | User interface | 1-2 hours | Phase 2 |
| 4 | Testing & docs | 2-3 hours | Phase 3 |
| **Total** | | **9-15 hours** | |

---

## Success Criteria

1. ✅ `emdx run --cli cursor "task"` works end-to-end
2. ✅ `emdx agent --cli cursor "task"` saves output to emdx
3. ✅ `emdx each --cli cursor ...` processes items in parallel
4. ✅ `emdx workflow --cli cursor ...` executes full workflows
5. ✅ Existing Claude workflows continue working unchanged
6. ✅ Token/cost tracking works for Claude, gracefully absent for Cursor
7. ✅ Environment validation detects and reports correct CLI
8. ✅ All existing tests pass
9. ✅ New integration tests pass with both CLIs

---

## Appendix: CLI Command Comparison

### Claude CLI
```bash
claude --print "your prompt" \
  --allowedTools "Read,Write,Edit,Bash" \
  --output-format stream-json \
  --model claude-opus-4-5-20251101 \
  --verbose
```

### Cursor CLI
```bash
cursor agent -p \
  --output-format stream-json \
  --model auto \
  --force \
  "your prompt"
```

### Key Differences
1. **Binary**: `claude` vs `cursor agent`
2. **Prompt position**: Claude uses `--print <prompt>`, Cursor uses positional
3. **Verbose**: Claude requires `--verbose` for stream-json, Cursor doesn't
4. **Tool control**: Claude has `--allowedTools`, Cursor has `--force`
5. **Workspace**: Cursor has explicit `--workspace`, Claude uses `cwd`
