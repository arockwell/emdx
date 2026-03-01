#!/usr/bin/env bash
# SessionStart hook: create a daily backup of the emdx knowledge base.
#
# Fast path: if today's backup exists, exits after a single glob — no Python.
# Skips delegate sessions and environments without emdx installed.
set -euo pipefail

# Consume stdin (required by hook protocol)
cat > /dev/null

# Skip delegate sessions
[[ "${EMDX_AUTO_SAVE:-}" == "1" ]] && exit 0

# Skip if emdx not installed
command -v emdx &>/dev/null || exit 0

# Skip if no database exists yet
DB="${HOME}/.config/emdx/knowledge.db"
[[ -f "$DB" ]] || exit 0

# Fast check: already backed up today?
TODAY=$(date -u +%Y-%m-%d)
BACKUP_DIR="${HOME}/.config/emdx/backups"
ls "${BACKUP_DIR}"/emdx-backup-${TODAY}* &>/dev/null 2>&1 && exit 0

# Create backup (quiet, won't block session start)
emdx maintain backup --quiet 2>/dev/null || true
