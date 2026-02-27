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
#   EMDX_TASK_ID  - Task to mark as done/failed
set -euo pipefail

# Read stdin JSON
INPUT=$(cat)

# Only run if a task is being tracked
if [[ -z "${EMDX_TASK_ID:-}" ]]; then
    exit 0
fi

# Mark task as done (delegate launcher handles failure via exit code)
emdx task done "$EMDX_TASK_ID" 2>/dev/null || true
