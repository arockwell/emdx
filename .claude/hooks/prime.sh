#!/usr/bin/env bash
# SessionStart hook: inject emdx work context into Claude sessions.
#
# Receives JSON on stdin: {"session_id": "...", "cwd": "...", "session_type": "..."}
# Stdout is added to Claude's context.
#
# Optional env vars:
#   EMDX_DOC_ID    - Include specific document as context
#   EMDX_TASK_ID   - Mark task as active on session start
set -euo pipefail

# Consume stdin (required by hook protocol)
cat > /dev/null

# Prime with KB context (ready tasks, in-progress work, recent docs)
emdx prime 2>/dev/null || true

# Include document context if specified
if [[ -n "${EMDX_DOC_ID:-}" ]]; then
    echo ""
    echo "=== Document Context (doc #${EMDX_DOC_ID}) ==="
    emdx view "$EMDX_DOC_ID" 2>/dev/null || true
fi

# Task activation
if [[ -n "${EMDX_TASK_ID:-}" ]]; then
    emdx task active "$EMDX_TASK_ID" 2>/dev/null || true
fi
