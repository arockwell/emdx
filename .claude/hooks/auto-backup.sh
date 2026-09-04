#!/usr/bin/env bash
# SessionStart hook: create a daily backup of the emdx knowledge base.
#
# Daily checks are scoped to the effective database by the CLI.
# Skips environments without emdx installed.
set -euo pipefail

# Consume stdin (required by hook protocol)
cat > /dev/null

# Skip if emdx not installed
command -v emdx &>/dev/null || exit 0

# Resolve the effective database in the CLI; global shell globs mix different KBs.
emdx maintain backup --daily --quiet 2>/dev/null || true
