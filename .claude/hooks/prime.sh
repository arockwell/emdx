#!/usr/bin/env bash
# SessionStart hook: inject emdx work context into Claude sessions.
#
# Receives JSON on stdin: {"session_id": "...", "cwd": "...", "session_type": "..."}
# Stdout is added to Claude's context.
#
# Env vars (set by delegate launcher):
#   EMDX_DOC_ID    - Include specific document as context
#   EMDX_TASK_ID   - Mark task as active on session start
set -euo pipefail

# Consume stdin (required by hook protocol)
cat > /dev/null

# Prime with current work context (quiet = just ready tasks)
emdx prime --quiet 2>/dev/null || true

# If delegate set a doc context, include it
if [[ -n "${EMDX_DOC_ID:-}" ]]; then
    echo ""
    echo "=== Document Context (doc #${EMDX_DOC_ID}) ==="
    emdx view "$EMDX_DOC_ID" 2>/dev/null || true
fi

# If delegate set a task, mark it active
if [[ -n "${EMDX_TASK_ID:-}" ]]; then
    emdx task active "$EMDX_TASK_ID" 2>/dev/null || true
fi
