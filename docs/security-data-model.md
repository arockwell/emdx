# EMDX Security and Data Model

This document describes EMDX's security model, data storage, and privacy considerations.

## Overview

EMDX is a **local-first, single-user** knowledge base system. All data is stored locally on your machine with no cloud dependencies or external data transmission.

## Data Storage

### Database Location

| Data | Default Location | Purpose |
|------|------------------|---------|
| Main database | `~/.emdx/emdx.db` | SQLite database with all documents, tags, metadata |
| Execution logs | `~/.emdx/logs/` | Log files from command executions |
| Configuration | `~/.emdx/config.json` | Optional user configuration |

You can override the database location with the `EMDX_DB_PATH` environment variable.

### Data Contents

The database stores:
- **Documents**: Title, content, project association, creation/modification timestamps
- **Tags**: Tag names (including emoji), text aliases, usage counts
- **Executions**: Command history, status, log file paths, timing data
- **Agents**: AI agent configurations, prompts, execution history
- **FTS Index**: Full-text search index for fast content searching

### File Permissions

EMDX creates files with your user's default permissions:
- Database files: Readable/writable by owner only (typically `600` or `644`)
- Log files: Same as database
- Directory: `~/.emdx/` created with standard directory permissions

**Recommendation**: Ensure your home directory and `~/.emdx/` have appropriate permissions:
```bash
chmod 700 ~/.emdx  # Owner-only access
```

## Security Model

### Single-User Design

EMDX is designed for **single-user, local operation**:
- No authentication or user accounts
- No access control between users
- No encryption at rest (database is plain SQLite)
- No network services or listening ports

### What EMDX Does NOT Provide

- **Multi-user access control**: No user authentication
- **Encryption at rest**: Data stored in plain SQLite format
- **Network security**: No network services (except optional GitHub Gist integration)
- **Audit logging**: No security audit trail
- **Data isolation**: Single database for all data

### External Integrations

EMDX has optional integrations that communicate externally:

| Integration | Data Transmitted | Authentication |
|-------------|-----------------|----------------|
| GitHub Gist | Document content (when explicitly shared) | `GITHUB_TOKEN` environment variable |
| AI Agents | Document content sent to Claude API | Anthropic API key (via Claude Code) |

**Important**: Only use these integrations if you're comfortable with the data leaving your machine.

## Privacy Considerations

### What Stays Local

By default, EMDX operates entirely locally:
- All documents stored in local SQLite database
- Full-text search performed locally
- TUI runs in your terminal with no external connections
- No telemetry or usage data collection

### What Can Leave Your Machine

Only explicit user actions can send data externally:

1. **`emdx gist create`**: Uploads document content to GitHub
2. **`emdx agent run`**: Sends document content to Claude API for AI processing

These actions require explicit commands and configuration (API tokens).

### Sensitive Data Recommendations

If storing sensitive information:

1. **Don't use external integrations** for sensitive documents
2. **Consider disk encryption** (FileVault, LUKS, BitLocker)
3. **Use appropriate file permissions** on `~/.emdx/`
4. **Don't store secrets** (API keys, passwords) in documents
5. **Be cautious with tags** that might reveal sensitive patterns

## Backup and Recovery

### Backing Up Your Data

The entire knowledge base is contained in the database file:

```bash
# Simple backup
cp ~/.emdx/emdx.db ~/.emdx/emdx.db.backup

# With timestamp
cp ~/.emdx/emdx.db ~/.emdx/emdx.db.$(date +%Y%m%d)

# Include logs
tar -czf emdx-backup-$(date +%Y%m%d).tar.gz ~/.emdx/
```

### Automated Backups

Consider adding to your backup routine:

```bash
# Example: Daily backup to a separate location
0 2 * * * cp ~/.emdx/emdx.db /path/to/backups/emdx-$(date +\%Y\%m\%d).db
```

### Recovery

To restore from backup:
```bash
# Stop any running EMDX processes
pkill -f emdx

# Restore
cp /path/to/backup/emdx.db ~/.emdx/emdx.db
```

### Data Export

You can export data for migration or portability:

```bash
# Export all documents as SQL
sqlite3 ~/.emdx/emdx.db ".dump documents" > documents.sql

# Export to CSV
sqlite3 -header -csv ~/.emdx/emdx.db "SELECT * FROM documents;" > documents.csv
```

## Database Integrity

### Checking Integrity

```bash
# SQLite integrity check
sqlite3 ~/.emdx/emdx.db "PRAGMA integrity_check;"

# Should return: ok
```

### Optimization

For large databases, periodic optimization helps:

```bash
# Vacuum (reclaim space, reorganize)
sqlite3 ~/.emdx/emdx.db "VACUUM;"

# Update statistics (improves query planning)
sqlite3 ~/.emdx/emdx.db "ANALYZE;"
```

## Future Considerations

While EMDX currently operates as a single-user local application, potential future enhancements might include:

- **Optional encryption at rest** for sensitive documents
- **Document-level sharing controls** for AI agent access
- **Audit logging** for compliance use cases
- **Sync capabilities** with end-to-end encryption

These would be opt-in features that maintain the local-first philosophy.

---

**Related Documentation:**
- [Database Design](database-design.md) - Schema and migration details
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
- [Architecture](architecture.md) - System design overview
