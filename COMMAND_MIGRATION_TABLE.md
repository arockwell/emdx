# EMDX Command Migration Table (0.6.x → 0.7.0)

This comprehensive table maps all EMDX commands from version 0.6.x to their equivalents in 0.7.0.

## 🔄 Command Consolidation Overview

EMDX 0.7.0 consolidates 40+ commands into a more focused set, with two main unified commands:
- **`analyze`** - All read-only analysis operations
- **`maintain`** - All modification operations (dry-run by default)

## 📊 Complete Command Migration Table

### Core Commands (Unchanged)
| Command | Status | Notes |
|---------|--------|-------|
| `emdx save` | ✅ Unchanged | Enhanced with `--auto-tag` flag |
| `emdx find` | ✅ Unchanged | Added `--ids-only`, `--json`, date filtering |
| `emdx view` | ✅ Unchanged | |
| `emdx edit` | ✅ Unchanged | |
| `emdx delete` | ✅ Unchanged | |
| `emdx trash` | ✅ Unchanged | |
| `emdx restore` | ✅ Unchanged | |
| `emdx purge` | ✅ Unchanged | |

### Browse Commands (Unchanged)
| Command | Status | Notes |
|---------|--------|-------|
| `emdx list` | ✅ Unchanged | Added `--format json` support |
| `emdx recent` | ✅ Unchanged | |
| `emdx stats` | ✅ Unchanged | Enhanced with JSON output |
| `emdx project-stats` | ✅ Unchanged | |
| `emdx projects` | ✅ Unchanged | |
| `emdx gui` | ✅ Unchanged | Enhanced TUI with tags column |

### Tag Commands (Mostly Unchanged)
| Command | Status | Notes |
|---------|--------|-------|
| `emdx tag` | ✅ Unchanged | Added `--suggest` flag |
| `emdx untag` | ✅ Unchanged | |
| `emdx tags` | ✅ Unchanged | Added `--format json` |
| `emdx retag` | ✅ Unchanged | |
| `emdx merge-tags` | ✅ Unchanged | |
| `emdx legend` | ✅ Unchanged | |
| `emdx batch` | ⚠️ Deprecated | Use `emdx maintain --tags` |

### Health & Maintenance Commands (MAJOR CHANGES)
| Old Command | New Command | Notes |
|-------------|-------------|-------|
| `emdx health` | `emdx analyze --health` | Consolidated into analyze |
| `emdx health check` | `emdx analyze --health` | Same as above |
| `emdx health monitor` | ❌ Removed | Use cron + `--json` |
| `emdx clean duplicates` | `emdx maintain --clean --execute` | Requires --execute |
| `emdx clean empty` | `emdx maintain --clean --execute` | Combined with duplicates |
| `emdx clean all` | `emdx maintain --auto --execute` | Auto-fix all issues |
| `emdx merge find` | `emdx analyze --similar` | Read-only analysis |
| `emdx merge similar` | `emdx maintain --merge --execute` | Actual merging |
| `emdx gc` | `emdx maintain --gc --execute` | Part of maintenance |
| `emdx gc schedule` | ❌ Removed | Use cron jobs |
| `emdx tag batch` | `emdx maintain --tags --execute` | Batch auto-tagging |
| `emdx tag suggest` | `emdx tag <id> --suggest` | Per-document suggestions |

### Execution Commands (Unchanged)
| Command | Status | Notes |
|---------|--------|-------|
| `emdx exec list` | ✅ Unchanged | |
| `emdx exec running` | ✅ Unchanged | |
| `emdx exec stats` | ✅ Unchanged | |
| `emdx exec show` | ✅ Unchanged | Enhanced log viewer |
| `emdx exec logs` | ✅ Unchanged | |
| `emdx exec tail` | ✅ Unchanged | |
| `emdx exec kill` | ✅ Unchanged | |
| `emdx exec killall` | ✅ Unchanged | |

### Claude & Lifecycle Commands (Unchanged)
| Command | Status | Notes |
|---------|--------|-------|
| `emdx claude execute` | ✅ Unchanged | |
| `emdx lifecycle status` | ✅ Unchanged | |
| `emdx lifecycle transition` | ✅ Unchanged | |
| `emdx lifecycle analyze` | ✅ Unchanged | |
| `emdx lifecycle auto-detect` | ✅ Unchanged | |
| `emdx lifecycle flow` | ✅ Unchanged | |

### Gist Commands (Unchanged)
| Command | Status | Notes |
|---------|--------|-------|
| `emdx gist` | ✅ Unchanged | |
| `emdx gist-list` | ✅ Unchanged | |

## 🆕 New Unified Commands

### `emdx analyze` - Read-Only Analysis
All analysis operations are now under one command with flags:

```bash
emdx analyze               # Default: health overview with recommendations
emdx analyze --health      # Detailed health metrics
emdx analyze --duplicates  # Find duplicate documents
emdx analyze --similar     # Find similar documents
emdx analyze --empty       # Find empty documents
emdx analyze --tags        # Tag coverage analysis
emdx analyze --lifecycle   # Gameplan lifecycle patterns
emdx analyze --projects    # Project-level analysis
emdx analyze --all         # Run all analyses
emdx analyze --json        # JSON output (works with all flags)
```

### `emdx maintain` - Modification Operations
All maintenance operations with dry-run by default:

```bash
emdx maintain                      # Interactive wizard
emdx maintain --auto               # Preview all fixes
emdx maintain --auto --execute     # Apply all fixes
emdx maintain --clean              # Preview duplicate/empty removal
emdx maintain --clean --execute    # Remove duplicates/empty docs
emdx maintain --merge              # Preview similar doc merging
emdx maintain --merge --execute    # Merge similar documents
emdx maintain --tags               # Preview auto-tagging
emdx maintain --tags --execute     # Apply auto-tags
emdx maintain --gc                 # Preview garbage collection
emdx maintain --gc --execute       # Run garbage collection
emdx maintain --lifecycle          # Preview lifecycle transitions
emdx maintain --lifecycle --execute # Apply lifecycle transitions
```

## ⚡ Quick Migration Examples

### Old Way vs New Way

```bash
# Checking health
OLD: emdx health
NEW: emdx analyze --health

# Cleaning duplicates
OLD: emdx clean duplicates
NEW: emdx maintain --clean --execute

# Finding similar documents
OLD: emdx merge find
NEW: emdx analyze --similar

# Batch tagging
OLD: emdx tag batch
NEW: emdx maintain --tags --execute

# Running garbage collection
OLD: emdx gc
NEW: emdx maintain --gc --execute

# Complete maintenance
OLD: emdx clean all && emdx gc && emdx tag batch
NEW: emdx maintain --auto --execute
```

## 🔧 Key Changes to Remember

1. **Dry-Run by Default**: `maintain` commands show what would happen unless you add `--execute`
2. **Unified Commands**: Most operations are now under `analyze` or `maintain`
3. **JSON Everywhere**: Add `--json` to any `analyze` command for automation
4. **Pipeline Support**: New flags like `--ids-only` enable Unix pipeline integration
5. **Interactive Wizard**: Running `maintain` without flags starts an interactive guide

## 📝 Migration Checklist

- [ ] Update all scripts to use new command syntax
- [ ] Add `--execute` to maintenance operations that should apply changes
- [ ] Replace monitoring scripts with `analyze --json` + cron
- [ ] Update any command aliases in shell configuration
- [ ] Test workflows with dry-run before adding `--execute`