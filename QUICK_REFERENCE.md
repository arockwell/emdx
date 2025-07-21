# EMDX 0.7.0 Quick Reference

## Essential Commands

### 📝 Save & Capture
```bash
emdx save file.md                              # Save file
echo "text" | emdx save --title "Note"         # Save text
cmd | emdx save --title "Output"               # Save command output
emdx save file.md --tags "docs,important"      # Save with tags
```

### 🔍 Search & Find
```bash
emdx find "query"                              # Basic search
emdx find "bug" --tags "urgent"                # Search with tags
emdx find --date-from "yesterday"              # Recent documents
emdx find "api" --json | jq '.count'           # JSON output
emdx find --tags "gameplan,active"             # Tag filtering
```

### 📊 Analysis & Health
```bash
emdx analyze --health                          # Health check
emdx analyze --duplicates                      # Find duplicates
emdx analyze --all --json                      # Full analysis
emdx lifecycle status                          # Document stages
```

### 🔧 Maintenance (Dry-run by default!)
```bash
emdx maintain --auto                           # Preview all fixes
emdx maintain --auto --execute                 # Apply fixes
emdx maintain --clean --execute                # Remove duplicates
emdx maintain --tags --execute                 # Auto-tag documents
```

### 🏷️ Tag Management
```bash
emdx tag 123 gameplan active                   # Add tags
emdx untag 123 active                          # Remove tags
emdx tags                                      # List all tags
emdx legend                                    # Emoji reference
```

### 👀 View & Edit
```bash
emdx view 123                                  # View document
emdx edit 123                                  # Edit document
emdx recent 10                                 # Recent documents
emdx gui                                       # TUI browser
```

## Power Features

### Unix Pipelines
```bash
# Find urgent bugs
emdx find "bug" --json | jq '.documents[] | select(.tags | contains(["urgent"]))'

# Batch tag documents
emdx find "TODO" --ids-only | xargs -I {} emdx tag {} "needs-review"

# Export for processing
emdx list --json > backup.json
```

### Automation
```bash
# Health monitoring
[ $(emdx analyze --health --json | jq '.health_score') -lt 80 ] && emdx maintain --auto --execute

# Daily maintenance
0 2 * * * emdx maintain --auto --execute >> /var/log/emdx.log
```

## Emoji Tag Reference

| Emoji | Aliases | Meaning |
|-------|---------|---------|
| 🎯 | gameplan, plan, strategy | Strategic plans |
| 🚀 | active, rocket, current | Currently active |
| ✅ | done, complete, finished | Completed |
| 🐛 | bug, issue, problem | Bugs/issues |
| ✨ | feature, new, enhancement | New features |
| 📚 | docs, documentation | Documentation |
| 🚧 | blocked, stuck, waiting | Blocked items |
| 🚨 | urgent, critical | High priority |

## Key Changes in 0.7.0

### ❌ Removed Commands
- ~~`emdx health`~~ → `emdx analyze --health`
- ~~`emdx clean`~~ → `emdx maintain --clean`
- ~~`emdx merge`~~ → `emdx maintain --merge`

### ✅ New Commands
- `emdx analyze` - Read-only analysis
- `emdx maintain` - Modifications (needs --execute)
- `emdx lifecycle` - Document progression

### ⚠️ Safety First
All destructive operations require `--execute`:
```bash
emdx maintain --clean           # Preview only
emdx maintain --clean --execute # Actually delete
```

## Common Workflows

### New Document
```bash
echo "Meeting notes" | emdx save --title "Team Standup" --tags "meeting,active"
```

### Find & Update
```bash
emdx find "refactor" --tags "active"
emdx edit 123
emdx tag 123 done success
```

### Health Check & Fix
```bash
emdx analyze --health
emdx maintain --auto --execute
```

### Export & Backup
```bash
emdx list --json > $(date +%Y%m%d)-backup.json
```

## Tips & Tricks

1. **Use aliases**: Add to ~/.bashrc or ~/.zshrc
   ```bash
   alias eh='emdx analyze --health'
   alias em='emdx maintain --auto'
   alias ef='emdx find'
   ```

2. **JSON + jq**: Powerful combinations
   ```bash
   emdx find "bug" --json | jq -r '.documents[] | "\(.id): \(.title)"'
   ```

3. **Dry-run first**: Always preview
   ```bash
   emdx maintain --clean         # Check first
   emdx maintain --clean --execute # Then apply
   ```

4. **Tag consistently**: Use text aliases
   ```bash
   emdx tag 123 gameplan active  # Not 🎯 🚀
   ```

## Need Help?
- `emdx --help` - Command help
- `emdx [command] --help` - Specific command help
- [README.md](README.md) - Full documentation
- [MIGRATION.md](MIGRATION.md) - Upgrade guide