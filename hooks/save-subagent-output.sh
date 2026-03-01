#!/usr/bin/env bash
# SubagentStop hook: auto-save subagent output to the emdx knowledge base.
#
# Receives JSON on stdin with keys:
#   agent_type, last_assistant_message, stop_hook_active,
#   agent_id, session_id, agent_transcript_path
#
# Saves substantive output (200+ chars) with agent-type tags.
# Skips delegate sessions (EMDX_AUTO_SAVE=1) to avoid double-saving.
set -uo pipefail
# Note: -e intentionally omitted — the Python heredoc's exit code must not
# cause bash to report a non-zero exit, which Claude Code interprets as an
# agent error. We handle errors explicitly and always exit 0.

# Read stdin JSON to a temp file (env vars hit size limits on large payloads)
TMPFILE=$(mktemp /tmp/emdx-hook-input.XXXXXX)
cat > "$TMPFILE"

# Skip if inside a delegate session (has its own save pipeline)
if [[ "${EMDX_AUTO_SAVE:-}" == "1" ]]; then
    rm -f "$TMPFILE"
    exit 0
fi

python3 - "$TMPFILE" << 'PYEOF' || true
import json
import os
import re
import subprocess
import sys

tmpfile = sys.argv[1]

try:
    with open(tmpfile) as f:
        data = json.load(f)
except Exception:
    sys.exit(0)
finally:
    os.unlink(tmpfile)

agent_type = data.get("agent_type", "unknown")

# Guard: re-entry protection
if data.get("stop_hook_active", False):
    sys.exit(0)

# Extract message
msg = data.get("last_assistant_message", "")
if not msg or len(msg) < 200:
    sys.exit(0)

# Check emdx is available
if subprocess.run(["which", "emdx"], capture_output=True).returncode != 0:
    sys.exit(0)

# --- Title derivation ---
# Prefer first markdown heading, fall back to first non-empty line
title = ""
first_line = ""
for line in msg.splitlines():
    stripped = line.strip()
    if not first_line and stripped:
        first_line = stripped.lstrip("#").strip()[:80]
    if stripped.startswith("#"):
        title = stripped.lstrip("#").strip()[:80]
        break
if not title:
    title = first_line or f"{agent_type} agent output"

# --- Tags ---
tags = ["subagent", f"agent:{agent_type.lower()}"]

# Auto-detect PR URLs in output
if re.search(r"https://github\.com/[^/]+/[^/]+/pull/\d+", msg):
    tags.append("has-pr")

tag_str = ",".join(tags)

# --- Save to KB ---
try:
    subprocess.run(
        ["emdx", "save", "--title", title, "--tags", tag_str],
        input=msg,
        text=True,
        capture_output=True,
        timeout=20,
    )
except Exception:
    pass

sys.exit(0)
PYEOF

# Always exit clean — a hook failure should never mark an agent as errored
exit 0
