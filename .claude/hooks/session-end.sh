#!/usr/bin/env bash
# SessionEnd hook: update task status when a delegate session completes.
#
# Receives JSON on stdin with keys:
#   session_id, cwd, transcript_path
#
# Only activates when EMDX_TASK_ID is set (by delegate launcher).
# Regular human sessions are not affected.
#
# Env vars (set by delegate launcher):
#   EMDX_TASK_ID       - Task to mark as done/failed
#   EMDX_EXECUTION_ID  - Execution record to update with metrics
set -euo pipefail

# Read stdin JSON
INPUT=$(cat)

# Only run if a task is being tracked
if [[ -z "${EMDX_TASK_ID:-}" ]]; then
    exit 0
fi

# Extract transcript path for metrics
TRANSCRIPT=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('transcript_path', ''))
" 2>/dev/null || true)

# Mark task as done (delegate launcher handles failure via exit code)
emdx task done "$EMDX_TASK_ID" 2>/dev/null || true

# Extract and record metrics from transcript if available
if [[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" && -n "${EMDX_EXECUTION_ID:-}" ]]; then
    python3 -c "
import json, sys

try:
    with open('$TRANSCRIPT') as f:
        transcript = json.load(f)

    # Sum token usage from transcript messages
    input_tokens = 0
    output_tokens = 0
    for msg in transcript:
        usage = msg.get('usage', {})
        input_tokens += usage.get('input_tokens', 0)
        output_tokens += usage.get('output_tokens', 0)

    if input_tokens or output_tokens:
        from emdx.models.executions import update_execution
        update_execution(
            int('$EMDX_EXECUTION_ID'),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            tokens_used=input_tokens + output_tokens,
        )
except Exception:
    pass  # Never fail the session end
" 2>/dev/null || true
fi
