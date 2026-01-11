# EMDX Tech Debt Tasks - Parallel Execution Plan

Generated from tech debt audit on 2026-01-10. Organized into parallel tracks that can run simultaneously without conflicts.

---

## Parallel Execution Strategy

```
Track A: Exception Handling    ─────────────────────────────►
Track B: Code Deduplication    ─────────────────────────────►
Track C: Type Safety           ─────────────────────────────►
Track D: Dead Code Cleanup     ─────────────────────────────►
Track E: Architecture Fixes    ─────────────────────────────►
```

Each track works on non-overlapping files to avoid merge conflicts.

---

# TRACK A: Exception Handling & Error Logging
**Can run in parallel with all other tracks**

## A1: Fix Silent Exceptions in Services
**Files:** `emdx/services/` (except log_stream.py)

### Locations to Fix
| File | Line | Current | Fix |
|------|------|---------|-----|
| `document_executor.py` | 160, 165 | `except Exception:` nested | Log + catch specific types |
| `claude_executor.py` | 51-52 | `except Exception: return "[File not found]"` | Catch `FileNotFoundError` specifically |
| `export_destinations.py` | (find line) | `except Exception:` | Add logging |
| `similarity.py` | (find line) | `except Exception:` | Add logging |

### Requirements
1. Add `import logging` and `logger = logging.getLogger(__name__)` if missing
2. Log exceptions with context before handling
3. Catch specific exception types where possible
4. Keep existing behavior (return values, continue, etc.)

---

## A2: Fix Silent Exceptions in Commands
**Files:** `emdx/commands/` (gist.py, maintain.py, export_profiles.py, claude_execute.py, gdoc.py)

### Locations to Fix
| File | Lines | Issue |
|------|-------|-------|
| `gist.py` | 50, 101, 108, 161, 168 | Silent subprocess failures |
| `maintain.py` | 627-628 | Silent `except Exception: pass` |
| `export_profiles.py` | (find line) | Silent exception |
| `claude_execute.py` | (2 locations) | Silent exceptions |
| `gdoc.py` | (find line) | Silent exception |

### Requirements
1. Add `logger.debug()` for expected failures
2. Add `logger.warning()` for unexpected failures
3. Include context in log messages

---

## A3: Fix Silent Exceptions in Applications
**Files:** `emdx/applications/maintenance.py`

### Location
- Line 432: `except Exception: continue` during document merge

### Requirements
1. Change to: `except Exception as e: logger.warning(f"Error during merge: {e}", exc_info=True); continue`

---

## A4: Fix Silent Exceptions in UI Layer
**Files:** `emdx/ui/` (multiple files)

### Locations to Fix
| File | Count | Notes |
|------|-------|-------|
| `document_browser.py` | 9 | Multiple handlers |
| `text_areas.py` | 3 | |
| `git_browser_standalone.py` | 3 | |
| `agent_form.py` | 2 | |
| `task_browser.py` | 2 | |
| `file_browser/navigation.py` | 2 | |
| `browser_container.py` | 1 | |
| `textual_browser.py` | 1 | |

### Requirements
1. Add logging to each silent handler
2. Use `logger.debug()` for UI-related exceptions that shouldn't interrupt user

---

## A5: Fix Silent Exceptions in Utils
**Files:** `emdx/utils/git.py`, `emdx/utils/logging.py`, `emdx/__init__.py`

### Requirements
1. Review each `except Exception:` block
2. Add appropriate logging

---

# TRACK B: Code Deduplication
**Can run in parallel with all other tracks**

## B1: Create Shared Console Module
**Files:** Create `emdx/utils/output.py`

### Requirements
1. Create new file:
```python
"""Shared console output utilities."""
from rich.console import Console

# Shared console instance for all CLI output
console = Console()
```

---

## B2: Migrate Console Imports - Commands Part 1
**Files:** `emdx/commands/` (analyze.py, agents.py, browse.py, core.py, executions.py)

### For Each File
1. Remove `from rich.console import Console` and `console = Console()`
2. Add `from emdx.utils.output import console`

---

## B3: Migrate Console Imports - Commands Part 2
**Files:** `emdx/commands/` (gc.py, gdoc.py, gist.py, lifecycle.py, maintain.py)

### Same as B2

---

## B4: Migrate Console Imports - Commands Part 3
**Files:** `emdx/commands/` (tags.py, tasks.py, workflows.py, claude_execute.py, export.py, export_profiles.py, similarity.py)

### Same as B2

---

## B5: Migrate Console Imports - Other Modules
**Files:** `emdx/main.py`, `emdx/ui/gui.py`, `emdx/utils/environment.py`

### Same as B2

---

## B6: Create CLI Error Handling Decorator
**Files:** Create `emdx/utils/cli.py`

### Requirements
1. Create decorator for common error pattern:
```python
"""CLI utilities for error handling."""
import functools
from typing import Callable
import typer
from emdx.utils.output import console

def handle_cli_errors(action: str) -> Callable:
    """Decorator that catches exceptions and prints user-friendly errors."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except typer.Exit:
                raise  # Don't catch intentional exits
            except Exception as e:
                console.print(f"[red]Error {action}: {e}[/red]")
                raise typer.Exit(1) from e
        return wrapper
    return decorator
```
2. Add tests for the decorator

---

## B7: Standardize Logger Initialization
**Files:** All files using `logging.getLogger(__name__)`

### Requirements
1. Check if `emdx/utils/logging.py` has a `get_logger()` utility
2. If yes, migrate all to use it
3. If no, standardize on `logger = logging.getLogger(__name__)`
4. Document standard in code style guide

---

# TRACK C: Type Safety
**Can run in parallel with all other tracks**

## C1: Add Types to Workflow Services
**Files:** `emdx/workflows/services.py`

### Requirements
1. Define `ExecutionResult` TypedDict:
```python
from typing import TypedDict, Optional

class ExecutionResult(TypedDict):
    id: int
    doc_id: Optional[int]
    doc_title: str
    status: str
    started_at: str
    completed_at: Optional[str]
    log_file: str
    exit_code: Optional[int]
```
2. Update `get_execution()` return type to `Optional[ExecutionResult]`

---

## C2: Add Types to Execution Data Manager
**Files:** `emdx/ui/execution_data_manager.py`

### Requirements
1. Define `GitWorktree` TypedDict:
```python
class GitWorktree(TypedDict):
    path: str
    branch: str
    commit: str
    # Add other fields as discovered
```
2. Update `project_worktrees: List[GitWorktree]`
3. Update `worktrees: Optional[List[GitWorktree]]`

---

## C3: Fix Any Types in Auto-Tagger
**Files:** `emdx/services/auto_tagger.py`

### Location
- Line 305: `params: List[Any] = []`

### Requirements
1. Change to `params: List[Union[str, int, float, None]] = []`
2. Or use more specific type based on actual usage

---

# TRACK D: Dead Code Cleanup
**Can run in parallel with all other tracks**

## D1: Remove Deprecated Browser Stubs
**Files:** `emdx/ui/textual_browser.py`

### Requirements
1. Verify no imports of `MinimalDocumentBrowser` or `run_minimal` exist:
   ```bash
   rg "MinimalDocumentBrowser|run_minimal" --type py
   ```
2. Remove lines 20-28 (the stub functions)
3. Remove duplicate import at line 31

---

## D2: Clean Up Redundant Pass Statements
**Files:** Multiple (run search to find all)

### Find Command
```bash
rg "except.*:" -A2 emdx/ | grep -B1 "^\s*pass\s*$" | grep -v "^--$"
```

### Requirements
1. Remove `pass` statements that follow other statements in exception handlers
2. Keep `pass` only when it's the sole statement

---

## D3: Remove Unused db_path Parameter
**Files:** `emdx/services/duplicate_detector.py`

### Location
- Lines 17-20: `__init__` has unused `db_path` parameter

### Requirements
1. Remove the `db_path` parameter
2. Update any callers (search for `DuplicateDetector(`)

---

## D4: Document or Remove Legacy Comments
**Files:** `emdx/commands/claude_execute.py`

### Locations
- Line 66: `# Legacy behavior`
- Line ~1100: `# Legacy execution mode`

### Requirements
1. Add proper documentation explaining why legacy behavior exists, OR
2. Remove the legacy code paths if no longer needed

---

# TRACK E: Architecture & Implementation Fixes
**Can run in parallel with all other tracks**

## E1: Implement Log Stream Polling Fallback
**Files:** `emdx/services/log_stream.py`

### Location
- Lines 124-130: `_start_polling_fallback()` is a stub

### Requirements
1. Implement timer-based polling:
```python
def _start_polling_fallback(self) -> None:
    """Fallback to polling if file watching fails."""
    import threading

    def poll():
        while self._running:
            try:
                content = self._read_new_content()
                if content:
                    self._notify_subscribers(content)
            except Exception as e:
                logger.debug(f"Polling error: {e}")
            time.sleep(self._poll_interval)

    self._poll_thread = threading.Thread(target=poll, daemon=True)
    self._poll_thread.start()
```
2. Add `_poll_interval` config (default 1.0 seconds)
3. Add `_running` flag for clean shutdown
4. Add test for polling behavior

---

## E2: Implement Log View Search
**Files:** `emdx/ui/pulse/zoom2/log_view.py`

### Location
- Line 285: `action_search()` is a stub

### Requirements
1. Add search input widget (Textual Input)
2. Implement search through log content
3. Highlight or scroll to matches
4. Support Escape to cancel search

---

## E3: Move Imports Out of Exception Handlers
**Files:** `emdx/services/document_executor.py`

### Location
- Lines 160-164: `import tempfile` inside exception handler

### Requirements
1. Move `import tempfile` to top of file with other imports

---

## E4: Fix Pattern Usage Tracking Stub
**Files:** `emdx/services/auto_tagger.py`

### Location
- Lines 474-476: `NotImplementedError` for pattern tracking

### Requirements
Either:
1. Implement pattern usage tracking with database table, OR
2. Remove the method entirely if not needed

---

# Execution Summary

## Parallel Tracks (No Conflicts)

| Track | Tasks | Est. Time | Dependencies |
|-------|-------|-----------|--------------|
| A: Exception Handling | A1-A5 | 3-4 hours | None |
| B: Code Deduplication | B1-B7 | 4-5 hours | B2-B5 depend on B1 |
| C: Type Safety | C1-C3 | 2-3 hours | None |
| D: Dead Code Cleanup | D1-D4 | 1-2 hours | None |
| E: Architecture Fixes | E1-E4 | 4-5 hours | None |

## Task Counts by Priority

| Priority | Count | Tasks |
|----------|-------|-------|
| Critical | 1 | E1 (polling fallback) |
| High | 7 | A1, A2, A3, B1-B5 |
| Medium | 8 | A4, A5, B6, B7, C1, C2, C3, E2 |
| Low | 7 | D1, D2, D3, D4, E3, E4 |

## Recommended Parallel Execution

**Wave 1 (Start Immediately - 5 agents):**
- Agent A: Track A (A1 → A2 → A3 → A4 → A5)
- Agent B: Track B (B1 → B2 → B3 → B4 → B5 → B6 → B7)
- Agent C: Track C (C1 → C2 → C3)
- Agent D: Track D (D1 → D2 → D3 → D4)
- Agent E: Track E (E1 → E2 → E3 → E4)

All tracks can run simultaneously. Each agent works through their track sequentially.

## Workflow Definition

To run as an EMDX workflow:
```json
{
  "stages": [
    {
      "name": "tech_debt_parallel",
      "mode": "parallel",
      "runs": 5,
      "prompts": [
        "Execute Track A: Fix all silent exception handlers in emdx/services/, emdx/commands/, emdx/applications/, emdx/ui/, and emdx/utils/. Add logging before each silent pass/continue. Use logger.debug() for expected failures, logger.warning() for unexpected ones. Files: document_executor.py, claude_executor.py, gist.py, maintain.py, etc. Run tests when done.",
        "Execute Track B: Create shared console module and migrate all Console() instantiations. 1) Create emdx/utils/output.py with shared console. 2) Update all 20 files in emdx/commands/ and emdx/ui/ to import from shared module. 3) Create emdx/utils/cli.py with error handling decorator. Run tests when done.",
        "Execute Track C: Add proper types to replace Any. 1) Add ExecutionResult TypedDict to emdx/workflows/services.py. 2) Add GitWorktree TypedDict to emdx/ui/execution_data_manager.py. 3) Fix List[Any] in emdx/services/auto_tagger.py. Run tests when done.",
        "Execute Track D: Remove dead code. 1) Remove deprecated stubs in emdx/ui/textual_browser.py (MinimalDocumentBrowser, run_minimal). 2) Remove redundant pass statements after logging. 3) Remove unused db_path param in duplicate_detector.py. 4) Document legacy code in claude_execute.py. Run tests when done.",
        "Execute Track E: Fix architecture issues. 1) Implement polling fallback in emdx/services/log_stream.py. 2) Implement search in emdx/ui/pulse/zoom2/log_view.py. 3) Move imports out of exception handlers. 4) Handle pattern tracking stub in auto_tagger.py. Run tests when done."
      ],
      "synthesis_prompt": "Synthesize all tech debt fix results. Report: 1) What was fixed in each track. 2) Any items that couldn't be completed and why. 3) Test results. 4) Recommendations for follow-up work. Save as emdx document with tags: tech-debt, fix-report, comprehensive."
    }
  ]
}
```
