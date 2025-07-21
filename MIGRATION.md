# EMDX 0.6.x to 0.7.0 Migration Guide

This guide helps you upgrade from EMDX 0.6.x to 0.7.0, which includes significant changes to command structure, new features, and enhanced automation capabilities.

## Table of Contents
- [Overview of Changes](#overview-of-changes)
- [Breaking Changes](#breaking-changes)
- [Command Migration](#command-migration)
- [Database Migration](#database-migration)
- [Feature Migration](#feature-migration)
- [Workflow Updates](#workflow-updates)
- [Troubleshooting](#troubleshooting)

## Overview of Changes

### What's New in 0.7.0
- **Unified command structure** with `analyze`, `maintain`, and `lifecycle` commands
- **Health monitoring system** with weighted scoring
- **Automated maintenance** with dry-run safety
- **JSON output** for all commands enabling pipeline integration
- **Auto-tagging** with AI-powered content analysis
- **Lifecycle tracking** for gameplans and documents
- **Advanced search** with date filtering and improved performance

### What's Removed
- Individual maintenance commands (`health`, `clean`, `merge`)
- Direct modification without `--execute` flag
- Legacy command aliases

## Breaking Changes

### 1. Command Removal
The following commands no longer exist:

```bash
# OLD (0.6.x) - NO LONGER WORKS
emdx health
emdx clean
emdx merge

# NEW (0.7.0) - USE THESE INSTEAD
emdx analyze --health
emdx maintain --clean
emdx maintain --merge
```

### 2. Dry-Run by Default
All modification operations now preview changes by default:

```bash
# OLD (0.6.x) - Would immediately delete
emdx clean

# NEW (0.7.0) - Shows preview
emdx maintain --clean

# NEW (0.7.0) - Actually performs deletion
emdx maintain --clean --execute
```

### 3. JSON Output Structure
Standardized JSON output format across all commands:

```bash
# OLD (0.6.x) - Varied formats
emdx list --json  # One format
emdx stats --json # Different format

# NEW (0.7.0) - Consistent structure
emdx list --json
emdx analyze --health --json
emdx find "query" --json
# All follow same response pattern
```

## Command Migration

### Health Monitoring

```bash
# OLD (0.6.x)
emdx health
emdx health --detailed

# NEW (0.7.0)
emdx analyze --health
emdx analyze --health --json | jq
```

### Cleanup Operations

```bash
# OLD (0.6.x)
emdx clean                    # Delete duplicates
emdx clean --empty           # Delete empty docs
emdx clean --force          # No confirmation

# NEW (0.7.0)
emdx maintain --clean              # Preview changes
emdx maintain --clean --execute    # Apply changes
emdx analyze --duplicates         # Just analyze
emdx analyze --empty             # Just analyze
```

### Document Merging

```bash
# OLD (0.6.x)
emdx merge --similar
emdx merge doc1 doc2

# NEW (0.7.0)
emdx maintain --merge              # Auto-detect and preview
emdx maintain --merge --execute    # Apply merges
emdx analyze --similar            # Just analyze
```

### Complete Command Mapping

| 0.6.x Command | 0.7.0 Equivalent | Notes |
|---------------|------------------|--------|
| `emdx health` | `emdx analyze --health` | More metrics |
| `emdx health --json` | `emdx analyze --health --json` | Standardized format |
| `emdx clean` | `emdx maintain --clean --execute` | Requires --execute |
| `emdx clean --dry-run` | `emdx maintain --clean` | Default behavior |
| `emdx merge` | `emdx maintain --merge --execute` | Smarter detection |
| `emdx stats` | `emdx stats` | Unchanged |
| `emdx stats --json` | `emdx stats --json` | New format |

## Database Migration

### Automatic Migration
The database schema is automatically migrated on first use of 0.7.0:

```bash
# First run will show:
$ emdx list
Migrating database to version 8...
Migration complete.
```

### Manual Migration (if needed)

```bash
# Backup your database first
cp ~/.config/emdx/knowledge.db ~/.config/emdx/knowledge.db.backup

# Force migration
emdx db migrate --force

# Verify migration
emdx analyze --health
```

### Schema Changes
New tables and columns added in 0.7.0:
- `lifecycle_stages` table for tracking document progression
- `document_metrics` table for performance data
- Additional indexes for improved search performance

## Feature Migration

### 1. Health Monitoring Workflows

**Old Workflow (0.6.x):**
```bash
#!/bin/bash
# Check health manually
emdx health
if [ $? -ne 0 ]; then
    echo "Health check failed"
    emdx clean
fi
```

**New Workflow (0.7.0):**
```bash
#!/bin/bash
# Automated health monitoring
HEALTH=$(emdx analyze --health --json | jq '.health_score')
if [ "$HEALTH" -lt 80 ]; then
    echo "Health score: ${HEALTH}%"
    emdx maintain --auto --execute
fi
```

### 2. Duplicate Management

**Old Workflow (0.6.x):**
```bash
# Find and remove duplicates
emdx clean --dry-run
emdx clean  # Immediate deletion
```

**New Workflow (0.7.0):**
```bash
# Analyze first
emdx analyze --duplicates

# Review specific duplicates
emdx analyze --duplicates --json | jq '.duplicates[0]'

# Safe removal with preview
emdx maintain --clean
emdx maintain --clean --execute
```

### 3. Automation Scripts

**Old Script (0.6.x):**
```bash
#!/bin/bash
# maintenance.sh
emdx health || exit 1
emdx clean
emdx merge --similar
```

**New Script (0.7.0):**
```bash
#!/bin/bash
# maintenance.sh
set -e

# Check health
emdx analyze --health --json > health.json
SCORE=$(jq '.health_score' health.json)

# Run maintenance if needed
if [ "$SCORE" -lt 80 ]; then
    emdx maintain --auto --execute
fi

# Generate report
emdx analyze --all --json > report.json
```

## Workflow Updates

### 1. CI/CD Integration

**Old CI/CD (0.6.x):**
```yaml
- name: Health Check
  run: |
    emdx health
    if [ $? -ne 0 ]; then
      exit 1
    fi
```

**New CI/CD (0.7.0):**
```yaml
- name: Health Check
  run: |
    HEALTH=$(emdx analyze --health --json | jq '.health_score')
    echo "Health Score: $HEALTH%"
    if [ "$HEALTH" -lt 70 ]; then
      echo "::error::Knowledge base health is low"
      exit 1
    fi
```

### 2. Scheduled Maintenance

**Old Cron (0.6.x):**
```cron
0 2 * * * /usr/local/bin/emdx clean && /usr/local/bin/emdx merge
```

**New Cron (0.7.0):**
```cron
0 2 * * * /usr/local/bin/emdx maintain --auto --execute >> /var/log/emdx.log 2>&1
```

### 3. Monitoring Scripts

Update monitoring scripts to use new JSON output:

```bash
# OLD: Parse text output
health_status=$(emdx health | grep "Health:" | cut -d: -f2)

# NEW: Parse JSON
health_score=$(emdx analyze --health --json | jq '.health_score')
```

## Migration Checklist

- [ ] **Backup your database** before upgrading
- [ ] **Update EMDX** to version 0.7.0
- [ ] **Run once** to trigger automatic migration
- [ ] **Update scripts** to use new commands
- [ ] **Add --execute** flags where needed
- [ ] **Test dry-run** behavior before automation
- [ ] **Update CI/CD** pipelines
- [ ] **Update cron jobs** with new commands
- [ ] **Verify JSON parsing** in scripts
- [ ] **Run health check** to verify migration

## Troubleshooting

### Issue: Command not found

**Error:**
```bash
$ emdx health
Error: No such command 'health'
```

**Solution:**
Use the new command structure:
```bash
emdx analyze --health
```

### Issue: Changes not applying

**Error:**
```bash
$ emdx maintain --clean
[Preview of changes]
$ emdx list  # Still shows duplicates
```

**Solution:**
Add `--execute` flag to apply changes:
```bash
emdx maintain --clean --execute
```

### Issue: JSON parsing errors

**Error:**
```bash
parse error: Invalid numeric literal at line 1, column 10
```

**Solution:**
Ensure you're using `--json` flag:
```bash
# Wrong
emdx analyze --health | jq '.health_score'

# Correct
emdx analyze --health --json | jq '.health_score'
```

### Issue: Migration fails

**Error:**
```bash
Error: Database migration failed
```

**Solution:**
1. Backup and try manual migration:
```bash
cp ~/.config/emdx/knowledge.db ~/.config/emdx/knowledge.db.backup
emdx db export > export.json
rm ~/.config/emdx/knowledge.db
emdx db import export.json
```

2. Check disk space and permissions:
```bash
df -h ~/.config/emdx/
ls -la ~/.config/emdx/knowledge.db
```

### Issue: Performance degradation

**Symptoms:**
- Slower searches after upgrade
- Timeouts on large databases

**Solution:**
Run optimization:
```bash
emdx maintain --gc --execute
emdx maintain --gc --rebuild-fts --execute
```

## Best Practices for 0.7.0

1. **Always preview before execute**
   ```bash
   emdx maintain --auto          # Preview
   emdx maintain --auto --execute # Apply
   ```

2. **Use JSON for automation**
   ```bash
   emdx analyze --all --json | jq '.health_score'
   ```

3. **Monitor health regularly**
   ```bash
   # Add to .bashrc or .zshrc
   alias emdx-health='emdx analyze --health'
   ```

4. **Leverage new features**
   - Auto-tagging for better organization
   - Lifecycle tracking for gameplans
   - Pipeline integration for automation

## Getting Help

If you encounter issues not covered here:

1. Check the [README](README.md) for updated documentation
2. Run `emdx --help` for command syntax
3. File an issue on [GitHub](https://github.com/arockwell/emdx/issues)
4. Include output of `emdx --version` and `emdx analyze --health --json`

## Summary

The 0.7.0 upgrade brings powerful new capabilities but requires updating existing workflows. Key points:

- Replace old commands with new equivalents
- Add `--execute` for destructive operations
- Use `--json` for reliable script parsing
- Monitor health scores regularly
- Leverage automation features

Welcome to EMDX 0.7.0 - your intelligent knowledge assistant!