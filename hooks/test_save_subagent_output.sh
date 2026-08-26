#!/usr/bin/env bash
# Table-driven test for hooks/save-subagent-output.sh.
#
# Stubs `emdx` on PATH so no real save happens, then feeds the hook a JSON
# payload per case on stdin and asserts whether the stub was invoked.
# Covers: agent-type narrowing, the widened dedup regex, and the
# conversational-title skip.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK="$SCRIPT_DIR/save-subagent-output.sh"

STUB_DIR=$(mktemp -d)
LOG_FILE=$(mktemp)
trap 'rm -rf "$STUB_DIR" "$LOG_FILE"' EXIT

cat > "$STUB_DIR/emdx" << EOF
#!/usr/bin/env bash
echo "SAVED: \$*" >> "$LOG_FILE"
exit 0
EOF
chmod +x "$STUB_DIR/emdx"

pass=0
fail=0

# args: name, agent_type, message, expect ("save" or "skip")
run_case() {
    local name="$1" agent_type="$2" message="$3" expect="$4"

    : > "$LOG_FILE"
    local payload
    payload=$(python3 -c '
import json, sys
print(json.dumps({
    "agent_type": sys.argv[1],
    "last_assistant_message": sys.argv[2],
    "stop_hook_active": False,
}))
' "$agent_type" "$message")

    echo "$payload" | PATH="$STUB_DIR:$PATH" "$HOOK" > /dev/null 2>&1

    local saved="skip"
    [ -s "$LOG_FILE" ] && saved="save"

    if [ "$saved" = "$expect" ]; then
        echo "PASS: $name"
        pass=$((pass + 1))
    else
        echo "FAIL: $name (expected $expect, got $saved)"
        fail=$((fail + 1))
    fi
}

pad() {
    # Pad a body past the hook's 200-char minimum without altering its
    # meaningful opening line.
    printf '%s\n\n%s' "$1" "$(printf 'filler content padding out past the two hundred character minimum threshold so the length gate does not short circuit this test case before the logic under test runs. more filler text here to be safe.')"
}

run_case \
    "dedup: plain emdx #NNN citation" \
    "explore" \
    "$(pad 'Saved as emdx #3019.')" \
    "skip"

run_case \
    "dedup: 'doc #NNN' phrasing" \
    "explore" \
    "$(pad 'The save landed as doc #2265.')" \
    "skip"

run_case \
    "dedup: 'doc ID: #NNN' phrasing" \
    "explore" \
    "$(pad 'Findings recorded. emdx doc ID: #3019.')" \
    "skip"

run_case \
    "dedup: bold-markdown citation" \
    "explore" \
    "$(pad 'Linked as doc #**4521**.')" \
    "skip"

run_case \
    "dedup: lowercase 'Doc' with colon" \
    "explore" \
    "$(pad 'See Doc: 6021 for the full writeup.')" \
    "skip"

run_case \
    "conversational: 'Done. Here'\''s the summary:'" \
    "general-purpose" \
    "$(pad "Done. Here's the summary:")" \
    "skip"

run_case \
    "conversational: 'Now I have all I need...'" \
    "general-purpose" \
    "$(pad 'Now I have all I need. Let me write the review.')" \
    "skip"

run_case \
    "conversational: 'All four tasks complete.'" \
    "general-purpose" \
    "$(pad 'All four tasks complete.')" \
    "skip"

run_case \
    "conversational opener but has a heading -> title comes from heading" \
    "general-purpose" \
    "$(pad '# Investigation: stale session cache

Done. Here'\''s the summary of what I found.')" \
    "save"

run_case \
    "normal non-conversational first line, no heading" \
    "explore" \
    "$(pad 'The root cause is a stale cache key written by the session store.')" \
    "save"

run_case \
    "narrowed matcher: role-fleet type 'worker' is skipped" \
    "worker" \
    "$(pad 'Implemented the fix and verified with the test suite passing cleanly.')" \
    "skip"

run_case \
    "narrowed matcher: role-fleet type 'auditor' is skipped" \
    "auditor" \
    "$(pad 'Audited the flow and found no discrepancies worth flagging here today.')" \
    "skip"

run_case \
    "built-in type 'Plan' (case-insensitive) still saves" \
    "Plan" \
    "$(pad 'Proposed a three-step plan to migrate the legacy job queue safely.')" \
    "save"

echo
echo "== $pass passed, $fail failed =="
[ "$fail" -eq 0 ]
