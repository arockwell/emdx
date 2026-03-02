#!/usr/bin/env bash
# Plugin SessionStart hook: verify emdx is installed and give clear feedback.
#
# Receives JSON on stdin (hook protocol). Stdout is injected into Claude's context.
set -euo pipefail

# Consume stdin (required by hook protocol)
cat > /dev/null

if command -v emdx &> /dev/null; then
    version=$(emdx --version 2>/dev/null || echo "unknown")
    echo "● emdx ${version} — knowledge base ready"
    echo ""
    emdx prime 2>/dev/null || true
else
    echo "⚠ emdx CLI not found."
    echo ""
    echo "Install with:"
    echo "  uv tool install emdx     # recommended"
    echo "  pip install emdx          # alternative"
    echo ""
    echo "Then run: emdx status"
fi
