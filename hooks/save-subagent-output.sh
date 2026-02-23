#!/usr/bin/env bash
# SubagentStop hook: auto-save Task subagent output to the emdx knowledge base.
#
# Receives JSON on stdin with keys:
#   agent_type, last_assistant_message, stop_hook_active
#
# Only saves substantive output (200+ chars) from Explore/general-purpose agents.
# Skips delegate sessions (EMDX_AUTO_SAVE=1) to avoid double-saving.
#
# All saved docs are tagged "subagent,needs-review" for human curation.
set -euo pipefail

# Read full stdin JSON
INPUT=$(cat)

# Skip if inside a delegate session (has its own save-output.sh hook)
if [[ "${EMDX_AUTO_SAVE:-}" == "1" ]]; then
    exit 0
fi

# Single python3 block: parse JSON, apply filters, save to emdx.
# Receives the raw JSON via env var to avoid shell escaping issues.
export _EMDX_HOOK_INPUT="$INPUT"
python3 -c '
import json
import os
import subprocess
import sys

data = json.loads(os.environ["_EMDX_HOOK_INPUT"])

# Guard: re-entry protection
if data.get("stop_hook_active", False):
    sys.exit(0)

# Extract message
msg = data.get("last_assistant_message", "")
if not msg:
    sys.exit(0)

# Guard: skip short/trivial output
if len(msg) < 200:
    sys.exit(0)

# Check emdx is available
result = subprocess.run(["which", "emdx"], capture_output=True)
if result.returncode != 0:
    sys.exit(0)

# Derive title from first non-empty line, truncated to 80 chars
title = ""
for line in msg.splitlines():
    stripped = line.strip().lstrip("#").strip()
    if stripped:
        title = stripped[:80]
        break
if not title:
    title = "Subagent output"

# Save to KB
try:
    subprocess.run(
        ["emdx", "save", "--title", title, "--tags", "subagent,needs-review"],
        input=msg,
        text=True,
        capture_output=True,
        timeout=20,
    )
except Exception:
    pass
' || true
