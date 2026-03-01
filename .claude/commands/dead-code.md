# Dead Code Audit

Find and remove dead code from the codebase using vulture + targeted layer audits.

## Steps

### 1. Run Vulture Baseline

```bash
pip install vulture 2>/dev/null
vulture emdx/ --min-confidence 60 2>&1 | grep -v "unused function\|unused method\|unused class" | grep -v "^$"
```

Filter out framework false positives (CLI commands, Textual methods, TypedDict fields).
Focus on the non-framework unused functions:

```bash
vulture emdx/ --min-confidence 60 2>&1 | grep -E "unused (function|method|class)" | grep -v "compose\|on_mount\|on_key\|on_focus\|action_\|on_data_table\|on_input\|on_list_view\|on_option\|DEFAULT_CSS\|CSS\|watch_" | grep -v "emdx/commands/" | grep -v "emdx/ui/"
```

### 2. Parallel Layer Audits

Using vulture's output as leads, launch parallel agents (Agent tool, `subagent_type: "Explore"`) for each layer:

- **emdx/services/** — For every public function/method, grep for callers outside the file. List those with zero callers.
- **emdx/utils/** — Same approach.
- **emdx/config/ + emdx/models/** — Check constants, TypedDicts, functions.
- **emdx/database/ + tests/** — Check DB helpers for callers. Find test files testing removed features.

### 3. Create Cleanup PRs

Based on results, create one PR per layer with the dead code removed.

### 4. Verify and Merge

Check CI on each PR. Fix any issues (common: tests importing removed code).

## Important

- Always verify zero callers with grep before removing — vulture has false positives
- Framework methods (Textual, Click/Typer) are called via dispatch, not direct import
- TypedDict fields are NOT dead code — they're used via dict access
- When removing functions, also remove their tests and imports
- Private methods called from OTHER files won't show in vulture's per-file analysis
- When multiple PRs touch the same file, merge one at a time — they WILL conflict
