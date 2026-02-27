#!/usr/bin/env bash
# SessionStart hook: inject emdx work context into Claude sessions.
#
# Receives JSON on stdin: {"session_id": "...", "cwd": "...", "session_type": "..."}
# Stdout is added to Claude's context.
#
# Env vars (set by delegate launcher):
#   EMDX_AUTO_SAVE - Enable auto-save ("1" for delegate sessions)
#   EMDX_DOC_ID    - Include specific document as context
#   EMDX_TASK_ID   - Mark task as active on session start
set -euo pipefail

# Consume stdin (required by hook protocol)
cat > /dev/null

if [[ "${EMDX_AUTO_SAVE:-}" == "1" ]]; then
    # DELEGATE context — minimal priming
    echo "● emdx delegate — Focus on your assigned task only."
    echo "Output is auto-saved to the knowledge base when you finish."
    echo "Do NOT check ready tasks or pick up other work."

    # Subtask progress tracking
    if [[ -n "${EMDX_TASK_ID:-}" ]]; then
        echo ""
        echo "## REQUIRED: Progress Tracking"
        echo "You MUST break your work into steps and track progress."
        echo "Do this FIRST, before writing any code:"
        echo ""
        echo "  emdx task add \"Read and understand the codebase\" --epic $EMDX_TASK_ID"
        echo "  emdx task add \"Implement the changes\" --epic $EMDX_TASK_ID"
        echo "  emdx task add \"Run tests and fix issues\" --epic $EMDX_TASK_ID"
        echo "  emdx task add \"Final review and cleanup\" --epic $EMDX_TASK_ID"
        echo ""
        echo "Mark each step done as you complete it:"
        echo "  emdx task done <id>"
    fi

    if [[ -n "${EMDX_DOC_ID:-}" ]]; then
        echo "Document context (doc #${EMDX_DOC_ID}) follows below."
        echo ""
        echo "=== Document Context (doc #${EMDX_DOC_ID}) ==="
        emdx view "$EMDX_DOC_ID" 2>/dev/null || true
    fi
else
    # HUMAN context — full orientation
    emdx prime 2>/dev/null || true

    # If a doc context was set, include it
    if [[ -n "${EMDX_DOC_ID:-}" ]]; then
        echo ""
        echo "=== Document Context (doc #${EMDX_DOC_ID}) ==="
        emdx view "$EMDX_DOC_ID" 2>/dev/null || true
    fi
fi

# Task activation (both contexts)
if [[ -n "${EMDX_TASK_ID:-}" ]]; then
    emdx task active "$EMDX_TASK_ID" 2>/dev/null || true
fi
