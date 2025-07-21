# EMDX Migration Guide: 0.6.x → 0.7.0

This guide helps you migrate from EMDX 0.6.x to 0.7.0, which includes significant command consolidation and new features.

## 🚨 Breaking Changes

### Command Consolidation

EMDX 0.7.0 consolidates 15+ separate commands into 3 focused commands for better usability:

| Old Command | New Command | Notes |
|------------|-------------|-------|
| `emdx health` | `emdx analyze --health` | Now part of unified analysis |
| `emdx health check` | `emdx analyze --health` | Same as above |
| `emdx clean duplicates` | `emdx maintain --clean --execute` | Requires --execute to run |
| `emdx clean empty` | `emdx maintain --clean --execute` | Combined with duplicates |
| `emdx merge find` | `emdx analyze --similar` | Read-only analysis |
| `emdx merge similar` | `emdx maintain --merge --execute` | Actual merging |
| `emdx gc` | `emdx maintain --gc --execute` | Part of maintenance |
| `emdx tag batch` | `emdx maintain --tags --execute` | Auto-tagging |
| `emdx tag suggest` | `emdx tag <id> --suggest` | Per-document suggestions |

### Dry-Run by Default

**IMPORTANT**: The `maintain` command runs in dry-run mode by default. You must explicitly use `--execute` to perform changes:

```bash
# Old (immediate execution)
emdx clean duplicates

# New (dry-run by default)
emdx maintain --clean          # Shows what would be done
emdx maintain --clean --execute # Actually performs cleanup
```

### Removed Commands

These commands have been completely removed:
- `emdx health monitor` - Use cron with `emdx analyze --health --json`
- `emdx clean all` - Use `emdx maintain --auto --execute`

## ✨ New Features

### Unified Analysis Command

The new `emdx analyze` command provides comprehensive read-only analysis:

```bash
# Complete health check
emdx analyze --health

# Find issues
emdx analyze --duplicates
emdx analyze --similar
emdx analyze --empty

# Tag and project analysis
emdx analyze --tags
emdx analyze --projects
emdx analyze --lifecycle

# Run everything
emdx analyze --all

# JSON output for automation
emdx analyze --health --json | jq '.overall_score'
```

### Unified Maintenance Command

The new `emdx maintain` command handles all modifications:

```bash
# Interactive wizard (guides you through fixes)
emdx maintain

# Auto-fix everything
emdx maintain --auto --execute

# Specific fixes
emdx maintain --clean --execute    # Remove duplicates/empty docs
emdx maintain --merge --execute    # Merge similar documents
emdx maintain --tags --execute     # Auto-tag documents
emdx maintain --gc --execute       # Garbage collection
emdx maintain --lifecycle --execute # Transition stale gameplans
```

### Unix Pipeline Support

New flags enable powerful pipeline operations:

```bash
# Get document IDs only
emdx find --tags "bug" --ids-only

# Filter by dates
emdx find --created-after "2025-01-01" --modified-before "2025-02-01"

# Exclude tags
emdx find --tags "bug" --no-tags "fixed,wontfix"

# JSON everywhere
emdx analyze --all --json
emdx find "search" --format json
```

## 📋 Migration Checklist

1. **Update your scripts**:
   - Replace old commands with new equivalents
   - Add `--execute` where needed
   - Update any JSON parsing for new structure

2. **Update cron jobs**:
   ```bash
   # Old
   0 6 * * * emdx health check
   0 0 * * 0 emdx gc
   
   # New
   0 6 * * * emdx analyze --health --json >> health.log
   0 0 * * 0 emdx maintain --gc --execute
   ```

3. **Update aliases**:
   ```bash
   # ~/.bashrc or ~/.zshrc
   alias emdx-health='emdx analyze --health'
   alias emdx-clean='emdx maintain --clean --execute'
   alias emdx-fix='emdx maintain --auto --execute'
   ```

4. **Test workflows**:
   - Run commands with dry-run first
   - Verify JSON output structure if using automation
   - Check that pipeline operations work as expected

## 🔄 Rollback

If you need to rollback to 0.6.x:

```bash
# Backup your database first!
cp ~/.config/emdx/knowledge.db ~/.config/emdx/knowledge.db.backup

# Downgrade
pipx install emdx==0.6.1 --force
```

The database schema is backward compatible, so your data is safe.

## 💡 Tips for 0.7.0

### Use the Interactive Wizard
When in doubt, just run `emdx maintain` - it will analyze your knowledge base and guide you through recommended fixes.

### Leverage JSON Output
Almost every command now supports `--json` for automation:

```bash
# Track health over time
emdx analyze --health --json | jq '{
  date: now | strftime("%Y-%m-%d"),
  score: .overall_score,
  docs: .statistics.total_documents
}' >> health-history.jsonl

# Find problem documents
emdx analyze --duplicates --json | jq '.exact_duplicates.groups[] | .ids[]'
```

### Create Maintenance Scripts
```bash
#!/bin/bash
# daily-maintenance.sh

echo "=== EMDX Daily Maintenance ==="
echo "Analyzing health..."
emdx analyze --health

echo -e "\nFixing issues..."
emdx maintain --auto --execute

echo -e "\nDone! Current stats:"
emdx stats
```

## 🆘 Getting Help

- Run `emdx <command> --help` for detailed command help
- Check the [README](README.md) for examples
- Report issues at https://github.com/arockwell/emdx/issues

## 🎯 Why These Changes?

1. **Clarity**: 3 commands are easier to remember than 15
2. **Safety**: Dry-run by default prevents accidents
3. **Power**: Unix pipeline integration enables automation
4. **Consistency**: All commands follow similar patterns

Welcome to EMDX 0.7.0 - your knowledge base just got smarter! 🚀