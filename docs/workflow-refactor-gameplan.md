# Workflow System Refactoring Gameplan

**Related Analysis:** #5370
**Goal:** Clean up workflow code, improve maintainability, reduce bugs

---

## Phase 1: Dead Code Removal (Low Risk)

### Step 1.1: Delete unused strategies/ folder

**Files to delete:**
- `emdx/workflows/strategies/__init__.py`
- `emdx/workflows/strategies/base.py`
- `emdx/workflows/strategies/registry.py`
- `emdx/workflows/strategies/single.py`
- `emdx/workflows/strategies/parallel.py`
- `emdx/workflows/strategies/iterative.py`
- `emdx/workflows/strategies/adversarial.py`
- `emdx/workflows/strategies/dynamic.py`

**Verification:**
```bash
# Confirm no imports
rg "from.*strategies" emdx/
rg "import.*strategies" emdx/
```

**Risk:** None - code is never imported

### Step 1.2: Move StageResult to base.py

**Current locations:**
- `executor.py` line 34 (used)
- `strategies/base.py` line 20 (deleted in 1.1)

**Action:**
- Move `StageResult` dataclass from `executor.py` to `base.py`
- Update import in `executor.py`

### Step 1.3: Fix duplicate logger in executor.py

**Issue:** Logger initialized twice
```python
# Line 13
logger = logging.getLogger(__name__)
# Line 17 (after imports)
logger = logging.getLogger(__name__)
```

**Action:** Delete line 17

### Step 1.4: Run tests, commit

```bash
pytest tests/workflows/
git add -A && git commit -m "refactor(workflows): Remove unused strategies folder and cleanup"
```

---

## Phase 2: Split executor.py (Medium Risk)

### Step 2.1: Extract template resolution

**Create:** `emdx/workflows/template.py`

**Move from executor.py:**
- `_resolve_template()` method (lines 1501-1538)
- Make it a standalone function

**New file structure:**
```python
# emdx/workflows/template.py
"""Template resolution for workflow prompts."""

import re
from typing import Any, Dict, Optional

def resolve_template(template: Optional[str], context: Dict[str, Any]) -> str:
    """Resolve {{variable}} templates in a string.

    Supports:
    - Simple variables: {{input}}
    - Dotted access: {{stage_name.output}}
    - Indexed access: {{all_prev[0]}}
    """
    # ... existing logic ...
```

**Update executor.py:**
```python
from .template import resolve_template
# Replace self._resolve_template calls with resolve_template
```

### Step 2.2: Extract output parsing

**Create:** `emdx/workflows/output_parser.py`

**Move from executor.py:**
- `_extract_output_doc_id()` (lines 1189-1242)
- `_extract_token_usage()` (lines 1244-1254)
- `_extract_token_usage_detailed()` (lines 1256-1306)

**New file structure:**
```python
# emdx/workflows/output_parser.py
"""Parse agent execution logs for output and token usage."""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

def extract_output_doc_id(log_file: Path) -> Optional[int]:
    """Extract output document ID from execution log."""
    # ... existing logic ...

def extract_token_usage_detailed(log_file: Path) -> Dict[str, int]:
    """Extract detailed token usage from execution log."""
    # ... existing logic ...
```

### Step 2.3: Extract agent runner

**Create:** `emdx/workflows/agent_runner.py`

**Move from executor.py:**
- `_run_agent()` method (lines 1014-1187)

This is the biggest extraction. The function:
1. Updates individual run status
2. Sets up log file
3. Creates execution record
4. Builds prompt with save instruction
5. Calls Claude
6. Extracts output doc ID
7. Extracts token usage
8. Updates records

**New file structure:**
```python
# emdx/workflows/agent_runner.py
"""Agent execution for workflow runs."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .output_parser import extract_output_doc_id, extract_token_usage_detailed
from .services import document_service, execution_service, claude_service
from . import database as wf_db
from emdx.database.documents import record_document_source

logger = logging.getLogger(__name__)

async def run_agent(
    individual_run_id: int,
    agent_id: Optional[int],
    prompt: str,
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Run an agent with the given prompt.

    Args:
        individual_run_id: Individual run ID for tracking
        agent_id: Optional agent ID (not currently used)
        prompt: The prompt to send to Claude
        context: Execution context (must include _working_dir)

    Returns:
        Dict with success, output_doc_id, tokens_used, etc.
    """
    # ... existing logic ...
```

### Step 2.4: Extract synthesis

**Create:** `emdx/workflows/synthesis.py`

**Move from executor.py:**
- `_synthesize_outputs()` method (lines 1308-1468)

**New file structure:**
```python
# emdx/workflows/synthesis.py
"""Output synthesis for parallel workflow runs."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .output_parser import extract_output_doc_id
from .services import document_service, execution_service, claude_service
from .template import resolve_template
from . import database as wf_db
from emdx.database.documents import record_document_source

logger = logging.getLogger(__name__)

async def synthesize_outputs(
    stage_run_id: int,
    output_doc_ids: List[int],
    synthesis_prompt: Optional[str],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    """Synthesize multiple outputs into one using Claude."""
    # ... existing logic ...
```

### Step 2.5: Simplify executor.py

After extractions, executor.py should contain:
- `WorkflowExecutor` class
- `execute_workflow()` - orchestration
- `_execute_stage()` - dispatch
- `_execute_single()` - single mode
- `_execute_parallel()` - parallel mode
- `_execute_iterative()` - iterative mode
- `_execute_adversarial()` - adversarial mode
- `_execute_dynamic()` - dynamic mode
- `_run_discovery()` - discovery command execution
- `_load_document_variables()` - doc variable magic
- `_expand_tasks_to_prompts()` - task expansion

**Target:** ~800 lines (down from 1542)

### Step 2.6: Run tests, commit

```bash
pytest tests/workflows/
git add -A && git commit -m "refactor(workflows): Extract template, output_parser, agent_runner, synthesis modules"
```

---

## Phase 3: Improve Output Capture (Higher Risk)

### Step 3.1: Add document tracking to execute_with_claude

**File:** `emdx/commands/claude_execute.py`

**Change:** Track documents created during execution

```python
def execute_with_claude(...) -> Tuple[int, Optional[int]]:
    """Execute Claude with document tracking.

    Returns:
        Tuple of (exit_code, output_doc_id)
    """
    # Record timestamp before execution
    start_time = datetime.now()

    # ... existing execution ...

    # After execution, find documents created with workflow-output tag
    # that were created after start_time
    output_doc_id = find_workflow_output_doc(start_time)

    return exit_code, output_doc_id
```

### Step 3.2: Update agent_runner to use new return

**File:** `emdx/workflows/agent_runner.py`

**Change:** Use returned doc ID instead of log parsing

```python
# Before:
exit_code = await loop.run_in_executor(...)
output_doc_id = extract_output_doc_id(log_file)

# After:
exit_code, output_doc_id = await loop.run_in_executor(...)
# output_doc_id is already known, no parsing needed
```

### Step 3.3: Keep log parsing as fallback

Don't delete `extract_output_doc_id()` yet - keep as fallback for:
- Old logs
- Edge cases where document wasn't tracked
- Debugging

### Step 3.4: Run tests, commit

```bash
pytest tests/workflows/
pytest tests/commands/  # Also test claude_execute changes
git add -A && git commit -m "feat(workflows): Track output documents directly instead of log parsing"
```

---

## Phase 4: Explicit Context (Medium Risk)

### Step 4.1: Define WorkflowContext dataclass

**File:** `emdx/workflows/context.py`

```python
"""Workflow execution context."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

@dataclass
class StageOutput:
    """Output from a completed stage."""
    doc_id: int
    content: str
    title: str
    synthesis_doc_id: Optional[int] = None
    synthesis_content: Optional[str] = None
    individual_doc_ids: List[int] = field(default_factory=list)

@dataclass
class WorkflowContext:
    """Explicit workflow execution context.

    Replaces the magic Dict[str, Any] with typed fields.
    """

    # Input document
    input_doc_id: Optional[int] = None
    input_content: str = ""
    input_title: str = ""

    # Execution settings
    working_dir: Path = field(default_factory=Path.cwd)
    max_concurrent: int = 10
    base_branch: str = "main"

    # User-provided variables (from --var flags and presets)
    variables: Dict[str, Any] = field(default_factory=dict)

    # Auto-loaded document content (doc_N -> content, title)
    loaded_docs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Stage outputs (populated during execution)
    stage_outputs: Dict[str, StageOutput] = field(default_factory=dict)

    # Internal state
    workflow_run_id: Optional[int] = None
    workflow_name: str = ""

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a user variable."""
        return self.variables.get(name, default)

    def get_stage_output(self, stage_name: str) -> Optional[StageOutput]:
        """Get output from a completed stage."""
        return self.stage_outputs.get(stage_name)

    def to_template_context(self) -> Dict[str, Any]:
        """Convert to dict for template resolution.

        This maintains backwards compatibility with existing templates.
        """
        ctx = {}

        # Input
        ctx['input'] = self.input_content
        ctx['input_title'] = self.input_title

        # Variables
        ctx.update(self.variables)

        # Loaded docs
        for doc_key, doc_data in self.loaded_docs.items():
            ctx[f"{doc_key}_content"] = doc_data.get('content', '')
            ctx[f"{doc_key}_title"] = doc_data.get('title', '')
            ctx[f"{doc_key}_id"] = doc_data.get('id')

        # Stage outputs
        for stage_name, output in self.stage_outputs.items():
            ctx[f"{stage_name}.output"] = output.content
            ctx[f"{stage_name}.output_id"] = output.doc_id
            if output.synthesis_content:
                ctx[f"{stage_name}.synthesis"] = output.synthesis_content
                ctx[f"{stage_name}.synthesis_id"] = output.synthesis_doc_id

        # Internal (underscore prefix)
        ctx['_working_dir'] = str(self.working_dir)
        ctx['workflow_name'] = self.workflow_name
        ctx['run_id'] = self.workflow_run_id

        return ctx
```

### Step 4.2: Update executor to use WorkflowContext

**File:** `emdx/workflows/executor.py`

Gradual migration:
1. Create `WorkflowContext` at start of `execute_workflow()`
2. Convert to dict via `to_template_context()` when calling existing methods
3. Over time, update methods to accept `WorkflowContext` directly

### Step 4.3: Update agent_runner and synthesis

Accept `WorkflowContext` instead of `Dict[str, Any]`

### Step 4.4: Run tests, commit

```bash
pytest tests/workflows/
git add -A && git commit -m "refactor(workflows): Add explicit WorkflowContext dataclass"
```

---

## Phase 5: Error Handling (Lower Priority)

### Step 5.1: Define WorkflowError

**File:** `emdx/workflows/base.py`

```python
@dataclass
class WorkflowError:
    """Structured workflow error."""
    stage_name: str
    run_number: Optional[int]
    error_type: str  # 'agent_failed', 'synthesis_failed', 'discovery_failed', 'validation'
    message: str
    recoverable: bool = False
    details: Optional[Dict[str, Any]] = None
```

### Step 5.2: Update StageResult

```python
@dataclass
class StageResult:
    success: bool
    output_doc_id: Optional[int] = None
    synthesis_doc_id: Optional[int] = None
    individual_outputs: List[int] = field(default_factory=list)
    tokens_used: int = 0
    execution_time_ms: int = 0
    error_message: Optional[str] = None  # Keep for backwards compat
    errors: List[WorkflowError] = field(default_factory=list)  # New structured errors
```

### Step 5.3: Add validation to StageConfig

**File:** `emdx/workflows/base.py`

```python
@dataclass
class StageConfig:
    # ... existing fields ...

    def __post_init__(self):
        """Validate configuration."""
        if self.mode == ExecutionMode.PARALLEL and not self.synthesis_prompt:
            raise ValueError(f"Stage '{self.name}': parallel mode requires synthesis_prompt")
        if self.mode == ExecutionMode.DYNAMIC and not self.discovery_command:
            raise ValueError(f"Stage '{self.name}': dynamic mode requires discovery_command")
        if self.runs < 1:
            raise ValueError(f"Stage '{self.name}': runs must be >= 1")
```

### Step 5.4: Run tests, commit

```bash
pytest tests/workflows/
git add -A && git commit -m "refactor(workflows): Add structured errors and config validation"
```

---

## Testing Strategy

### Before Each Phase

1. Run existing tests: `pytest tests/workflows/`
2. Manual smoke test: `emdx workflow run task_parallel -t "test task" --dry-run`

### Test Coverage Goals

- `template.py`: Unit tests for all template patterns
- `output_parser.py`: Unit tests with sample log files
- `agent_runner.py`: Integration tests (mocked Claude)
- `synthesis.py`: Integration tests (mocked Claude)
- `context.py`: Unit tests for serialization/deserialization

### Create Test Fixtures

```python
# tests/workflows/fixtures.py
import pytest
from pathlib import Path

@pytest.fixture
def sample_log_with_doc_id(tmp_path):
    """Log file with document creation output."""
    log = tmp_path / "test.log"
    log.write_text("Starting...\n✅ Saved as #1234\nDone.")
    return log

@pytest.fixture
def sample_workflow_context():
    """Minimal workflow context for testing."""
    from emdx.workflows.context import WorkflowContext
    return WorkflowContext(
        input_content="Test input",
        working_dir=Path.cwd(),
        variables={"var1": "value1"},
    )
```

---

## Rollback Plan

Each phase is independently revertable:

```bash
# Revert Phase 1
git revert <phase1-commit>

# Revert Phase 2
git revert <phase2-commit>

# etc.
```

Key principle: Each commit should leave tests passing.

---

## Success Criteria

### Phase 1 Complete
- [ ] strategies/ folder deleted
- [ ] No unused imports
- [ ] Tests pass

### Phase 2 Complete
- [ ] executor.py < 900 lines
- [ ] New modules have clear single responsibility
- [ ] Tests pass

### Phase 3 Complete
- [ ] Output capture works without log parsing
- [ ] Fallback to log parsing still works
- [ ] Tests pass

### Phase 4 Complete
- [ ] WorkflowContext is documented
- [ ] Magic variable behavior is explicit
- [ ] Tests pass

### Phase 5 Complete
- [ ] Errors include stage/run context
- [ ] Invalid configs fail fast with clear messages
- [ ] Tests pass

---

## Estimated Effort

| Phase | Effort | Risk |
|-------|--------|------|
| Phase 1 | 1-2 hours | Low |
| Phase 2 | 4-6 hours | Medium |
| Phase 3 | 3-4 hours | Medium-High |
| Phase 4 | 3-4 hours | Medium |
| Phase 5 | 2-3 hours | Low |

**Total:** 13-19 hours of focused work

Can be done incrementally - each phase is independently valuable.
