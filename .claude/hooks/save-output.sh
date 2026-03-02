#!/usr/bin/env bash
# SubagentStop hook: save subagent output to the emdx knowledge base.
#
# Receives JSON on stdin with keys:
#   session_id, cwd, last_assistant_message, agent_transcript_path,
#   agent_type, agent_id, stop_hook_active
#
# Saves substantive output (200+ chars) with subagent tags.
# If EMDX_TASK_ID is set, links the saved doc to that task.
set -uo pipefail
# Note: -e intentionally omitted — we handle errors explicitly and always
# exit 0. A hook failure should never mark an agent as errored.

# Skip if emdx not installed
command -v emdx &>/dev/null || { cat > /dev/null; exit 0; }

# Skip if jq not installed (needed for JSON parsing)
command -v jq &>/dev/null || { cat > /dev/null; exit 0; }

# Read stdin JSON
INPUT=$(cat)

# Guard: re-entry protection
STOP_HOOK_ACTIVE=$(echo "$INPUT" | jq -r '.stop_hook_active // false' 2>/dev/null)
if [[ "$STOP_HOOK_ACTIVE" == "true" ]]; then
    exit 0
fi

# Extract message
MESSAGE=$(echo "$INPUT" | jq -r '.last_assistant_message // ""' 2>/dev/null)

# Skip if message is too short (noise filtering)
MSG_LEN=${#MESSAGE}
if [[ $MSG_LEN -lt 200 ]]; then
    exit 0
fi

# Extract agent type for tags
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // "unknown"' 2>/dev/null)
AGENT_TYPE_LOWER=$(echo "$AGENT_TYPE" | tr '[:upper:]' '[:lower:]')

# --- Title derivation ---
# Prefer first markdown heading, fall back to first non-empty line
TITLE=""
while IFS= read -r line; do
    stripped=$(echo "$line" | sed 's/^[[:space:]]*//' | sed 's/[[:space:]]*$//')
    if [[ -z "$TITLE" && -n "$stripped" ]]; then
        # First non-empty line as fallback
        FIRST_LINE=$(echo "$stripped" | sed 's/^#*//' | sed 's/^[[:space:]]*//' | cut -c1-80)
    fi
    if [[ "$stripped" == \#* ]]; then
        TITLE=$(echo "$stripped" | sed 's/^#*//' | sed 's/^[[:space:]]*//' | cut -c1-80)
        break
    fi
done <<< "$MESSAGE"
TITLE="${TITLE:-${FIRST_LINE:-${AGENT_TYPE} agent output}}"

# --- Tags ---
TAGS="subagent,agent:${AGENT_TYPE_LOWER}"

# Auto-detect PR URLs in output
if echo "$MESSAGE" | grep -qE 'https://github\.com/[^/]+/[^/]+/pull/[0-9]+'; then
    TAGS="${TAGS},has-pr"
fi

# --- Save to KB ---
TASK_ID="${EMDX_TASK_ID:-}"

if [[ -n "$TASK_ID" ]]; then
    # Save and link to task
    SAVE_OUTPUT=$(echo "$MESSAGE" | emdx save --title "$TITLE" --tags "$TAGS" --task "$TASK_ID" 2>/dev/null) || true
else
    # Save without task linkage
    SAVE_OUTPUT=$(echo "$MESSAGE" | emdx save --title "$TITLE" --tags "$TAGS" 2>/dev/null) || true
fi

# Always exit clean
exit 0
