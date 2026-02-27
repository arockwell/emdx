#!/usr/bin/env bash
# Stop hook: auto-save Claude's last message to the emdx knowledge base.
#
# DEPRECATED: As of the inline-save refactor, delegate.py saves output
# directly in Python after subprocess.run(). This hook is retained for
# backward compatibility but delegates no longer set EMDX_AUTO_SAVE=1.
#
# Receives JSON on stdin with keys:
#   session_id, cwd, last_assistant_message, stop_hook_active
#
# Only activates when EMDX_AUTO_SAVE=1 (no longer set by delegate launcher).
set -euo pipefail

# Consume stdin (required by hook protocol)
cat > /dev/null

# Only run when explicitly opted in (delegates no longer set this)
if [[ "${EMDX_AUTO_SAVE:-}" != "1" ]]; then
    exit 0
fi
