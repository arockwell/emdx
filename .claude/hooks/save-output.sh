#!/usr/bin/env bash
# Stop hook: auto-save Claude's last message to the emdx knowledge base.
#
# Receives JSON on stdin with keys:
#   session_id, cwd, last_assistant_message, stop_hook_active
#
# Only activates when EMDX_AUTO_SAVE=1 (set by delegate launcher).
# Regular human sessions are not affected.
#
# Env vars (set by delegate launcher):
#   EMDX_AUTO_SAVE  - Must be "1" to enable saving
#   EMDX_TITLE      - Document title (default: first line of message)
#   EMDX_TAGS       - Comma-separated tags to apply
#   EMDX_TASK_ID    - Task ID to link the saved doc to
#   EMDX_BATCH_FILE - File to append doc ID to (for parallel coordination)
set -euo pipefail

# Read full stdin JSON
INPUT=$(cat)

# Only run when delegate has opted in
if [[ "${EMDX_AUTO_SAVE:-}" != "1" ]]; then
    exit 0
fi

# Prevent re-entry: if stop_hook_active is true, another stop hook is running
ACTIVE=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('true' if d.get('stop_hook_active', False) else 'false')
")
if [[ "$ACTIVE" == "true" ]]; then
    exit 0
fi

# Extract the assistant's last message
MSG=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('last_assistant_message', ''))
")

# Skip if empty
if [[ -z "$MSG" ]]; then
    exit 0
fi

# Derive title: use EMDX_TITLE if set, otherwise first line truncated to 80 chars
if [[ -n "${EMDX_TITLE:-}" ]]; then
    TITLE="$EMDX_TITLE"
else
    TITLE=$(echo "$MSG" | head -1 | cut -c1-80)
    if [[ -z "$TITLE" ]]; then
        TITLE="Claude session output"
    fi
fi

# Build tags
TAGS="needs-review"
if [[ -n "${EMDX_TAGS:-}" ]]; then
    TAGS="${EMDX_TAGS},${TAGS}"
fi

# Save to KB and extract doc ID
SAVE_OUTPUT=$(echo "$MSG" | emdx save --title "$TITLE" --tags "$TAGS" 2>&1 || true)
DOC_ID=$(echo "$SAVE_OUTPUT" | python3 -c "
import sys, re
m = re.search(r'#(\d+)', sys.stdin.read())
print(m.group(1) if m else '')
")

# Link to task if specified
if [[ -n "${EMDX_TASK_ID:-}" && -n "$DOC_ID" ]]; then
    emdx task log "$EMDX_TASK_ID" "Saved output as doc #${DOC_ID}" 2>/dev/null || true
fi

# Write doc ID to batch file for parallel coordination
if [[ -n "${EMDX_BATCH_FILE:-}" && -n "$DOC_ID" ]]; then
    echo "$DOC_ID" >> "$EMDX_BATCH_FILE"
fi

# Report what we saved (goes to Claude as user message)
if [[ -n "$DOC_ID" ]]; then
    echo "Output saved to emdx as doc #${DOC_ID}."
fi
