# Workflow System Analysis & Refactoring Recommendations

**Date:** 2026-01-15
**Branch:** workflow-analysis

## Executive Summary

The workflow system has solid foundational concepts but suffers from **ad-hoc growth** leading to:
- **Unused abstraction layer** (strategies/ folder never imported)
- **Monolithic executor** (1542 lines duplicating all strategy logic)
- **Fragile log parsing** for output capture
- **Hidden magic** in context variable handling

The good news: the core architecture is sound. The problems are implementation-level and fixable incrementally.

---

## Current Architecture

```
emdx/workflows/
├── executor.py          # 1542 lines - monolithic orchestrator
├── base.py              # 348 lines - data models (good)
├── database.py          # 1079 lines - CRUD operations
├── registry.py          # 221 lines - workflow CRUD
├── services.py          # 168 lines - lazy-loaded service layer
├── worktree_pool.py     # 251 lines - git worktree management
├── tasks.py             # 51 lines - task resolution
└── strategies/          # COMPLETELY UNUSED
    ├── base.py          # 569 lines - duplicates executor methods!
    ├── single.py        # 58 lines
    ├── parallel.py      # 127 lines
    ├── iterative.py     # 112 lines
    ├── adversarial.py   # 119 lines
    └── dynamic.py       # 216 lines
```

### Total Lines: ~5000 (but ~1000 are dead code in strategies/)

---

## Problem 1: Duplicate Code / Unused Strategies

### The Issue

The `strategies/` folder contains a complete Strategy Pattern implementation that is **never used**.

```python
# executor.py line 341-351 - switches on mode DIRECTLY:
if stage.mode == ExecutionMode.SINGLE:
    result = await self._execute_single(...)
elif stage.mode == ExecutionMode.PARALLEL:
    result = await self._execute_parallel(...)
# etc.
```

Meanwhile, `strategies/base.py` defines `ExecutionStrategy` abstract class with identical `run_agent()`, `resolve_template()`, and `synthesize_outputs()` methods.

### Impact
- ~700 lines of dead code
- Changes need to be made in TWO places (if someone thinks strategies are used)
- Confusing for maintainers

### Fix Options

**Option A: Delete strategies/ entirely (fastest)**
- Remove `emdx/workflows/strategies/` folder
- Keep all logic in `executor.py`
- Pros: Simple, removes confusion
- Cons: Keeps executor monolithic

**Option B: Actually use strategies (better long-term)**
- Refactor executor to delegate to strategy classes
- Delete duplicated methods from executor
- Pros: Clean separation, easier testing
- Cons: More refactoring work

**Recommendation: Option A now, Option B later if executor grows**

---

## Problem 2: Monolithic executor.py

### The Issue

`executor.py` is 1542 lines with multiple responsibilities:
- Workflow orchestration (`execute_workflow`)
- Stage execution dispatch (`_execute_stage`)
- 5 execution modes (`_execute_single`, `_execute_parallel`, etc.)
- Agent invocation (`_run_agent` - 170 lines!)
- Log parsing (`_extract_output_doc_id`, `_extract_token_usage_detailed`)
- Template resolution (`_resolve_template`)
- Synthesis (`_synthesize_outputs`)
- Document variable loading (`_load_document_variables`)
- Task expansion (`_expand_tasks_to_prompts`)

### Impact
- Hard to test individual pieces
- Hard to understand at a glance
- Bug fixes require understanding the whole file

### Fix

Split into focused modules:

```
emdx/workflows/
├── executor.py           # ~200 lines - just orchestration
├── agent_runner.py       # ~250 lines - _run_agent logic
├── output_parser.py      # ~150 lines - log parsing
├── template_resolver.py  # ~100 lines - template substitution
├── synthesis.py          # ~150 lines - output synthesis
└── modes/
    ├── single.py
    ├── parallel.py
    ├── iterative.py
    ├── adversarial.py
    └── dynamic.py
```

---

## Problem 3: Fragile Log Parsing for Output Capture

### The Issue

The system tells Claude to save output via `emdx save`, then parses logs to find the document ID:

```python
# executor.py line 1067-1072
output_instruction = """
IMPORTANT: When you complete this task, save your final output/analysis as a document using:
echo "YOUR OUTPUT HERE" | emdx save --title "Workflow Output" --tags "workflow-output"
Report the document ID that was created."""

# Then later, regex parsing (line 1216-1223):
patterns = [
    r'saved as document #(\d+)',
    r'Saved as #(\d+)',
    r'Created document #(\d+)',
    # ...
]
```

### Impact
- If Claude doesn't follow instructions exactly, output is lost
- If log format changes, parsing breaks
- Multiple regex patterns = fragility
- No validation that extracted ID actually exists

### Fix Options

**Option A: Structured output file (simple)**
- Have agent write to a known file path: `~/.config/emdx/workflow-output-{run_id}.json`
- Contains `{"doc_id": 123, "title": "...", "content": "..."}`
- Parse JSON instead of regex

**Option B: Direct API return (better)**
- Modify `execute_with_claude` to return structured result including created doc IDs
- Track documents created during execution via database hooks
- Query documents created between exec start/end time with `workflow-output` tag

**Option C: Pre-create document, have agent update (most reliable)**
- Create empty document before running agent
- Pass document ID to agent: "Update document #123 with your output"
- Agent uses `emdx update 123 --content "..."`
- No parsing needed

**Recommendation: Option B (requires execute_with_claude changes)**

---

## Problem 4: Hidden Magic in Context Variables

### The Issue

The context dictionary has undocumented magic behavior:

```python
# Auto-loading doc_N variables (line 269-301):
# If context['doc_1'] = 123, automatically creates:
#   doc_1_content = <document content>
#   doc_1_title = <document title>
#   doc_1_id = 123

# Magic underscore prefixes for internal state:
context['_working_dir']        # Working directory
context['_max_concurrent_override']  # Concurrency limit
context['_discovery_override'] # Discovery command override

# Stage output storage:
context[f"{stage.name}.output"]      # Stage output content
context[f"{stage.name}.output_id"]   # Stage output doc ID
context[f"{stage.name}.synthesis"]   # Synthesis content
context[f"{stage.name}.synthesis_id"] # Synthesis doc ID
context[f"{stage.name}.outputs"]     # All parallel outputs
```

### Impact
- Developers must read code to understand available variables
- Easy to typo variable names (`stage.output` vs `stage_name.output`)
- No autocomplete or validation

### Fix

Create explicit context object:

```python
@dataclass
class WorkflowContext:
    """Explicit workflow execution context."""

    # Input
    input_doc_id: Optional[int] = None
    input_content: str = ""
    input_title: str = ""

    # Execution state
    working_dir: Path = field(default_factory=Path.cwd)
    max_concurrent: int = 10
    base_branch: str = "main"

    # User variables (from --var flags)
    variables: Dict[str, Any] = field(default_factory=dict)

    # Stage outputs (populated during execution)
    stage_outputs: Dict[str, StageOutput] = field(default_factory=dict)

    def get_stage_output(self, stage_name: str) -> Optional[StageOutput]:
        """Get output from a previous stage."""
        return self.stage_outputs.get(stage_name)

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a user variable."""
        return self.variables.get(name, default)
```

---

## Problem 5: Error Handling Inconsistency

### The Issue

Errors are handled differently across the codebase:

```python
# Some errors return StageResult(success=False):
if not output_doc_ids:
    return StageResult(success=False, error_message=f"All parallel runs failed")

# Some errors are raised:
raise ValueError(f"Workflow not found: {workflow_name_or_id}")

# Some errors are silently logged:
except Exception as e:
    logging.getLogger(__name__).warning(f"Could not create group: {e}")
    # Continues execution!

# continue_on_failure flag exists but isn't consistently used
```

### Impact
- Unpredictable behavior
- Hard to know what failed and why
- Silent failures corrupt expected state

### Fix

Standardize on result types:

```python
@dataclass
class WorkflowError:
    """Structured error information."""
    stage: str
    run_number: Optional[int]
    error_type: str  # 'agent_failed', 'synthesis_failed', 'discovery_failed'
    message: str
    recoverable: bool = False

@dataclass
class StageResult:
    success: bool
    # ...existing fields...
    errors: List[WorkflowError] = field(default_factory=list)
```

---

## Problem 6: Duplicate StageResult Class

### The Issue

`StageResult` is defined identically in two places:

- `executor.py` line 34
- `strategies/base.py` line 20

### Fix

Delete from `executor.py`, import from `strategies/base.py` (or move to `base.py` if deleting strategies/).

---

## Priority Ranking

| Priority | Issue | Effort | Impact |
|----------|-------|--------|--------|
| **P0** | Delete unused strategies/ | Low | High - removes confusion |
| **P1** | Split executor.py | Medium | High - maintainability |
| **P1** | Fix output capture | Medium | High - reliability |
| **P2** | Explicit context object | Medium | Medium - clarity |
| **P2** | Standardize errors | Medium | Medium - debugging |
| **P3** | Batch document queries | Low | Low - performance |

---

## Proposed Refactoring Plan

### Phase 1: Cleanup (Low risk)
1. Delete `strategies/` folder entirely
2. Move `StageResult` to `base.py`
3. Remove duplicate logger initialization in executor.py (line 13 and 17)

### Phase 2: Split Executor (Medium risk)
1. Extract `_run_agent` → `agent_runner.py`
2. Extract log parsing → `output_parser.py`
3. Extract `_resolve_template` → `template_resolver.py`
4. Extract `_synthesize_outputs` → `synthesis.py`
5. Keep orchestration in `executor.py`

### Phase 3: Improve Output Capture (Higher risk)
1. Modify `execute_with_claude` to track documents created
2. Remove log parsing approach
3. Return structured result from agent execution

### Phase 4: Polish
1. Create explicit `WorkflowContext` class
2. Standardize error handling
3. Add validation for StageConfig

---

## Quick Wins (Can Do Now)

1. **Delete strategies/ folder** - No functional change, just cleanup
2. **Fix duplicate logger** in executor.py line 13 vs 17
3. **Document magic context keys** in docstring or separate doc
4. **Add validation** to StageConfig (synthesis_prompt required for parallel, etc.)

---

## Questions for Discussion

1. **Do we want to keep the Strategy pattern?** If future execution modes are expected, keeping the pattern (and actually using it) makes sense.

2. **Is log parsing acceptable?** If modifying execute_with_claude is hard, we could improve the log parsing reliability instead.

3. **Should context be explicit?** The magic is convenient but error-prone. Worth the refactoring?

4. **Test coverage?** What's current test coverage of workflow code? Refactoring without tests is risky.
