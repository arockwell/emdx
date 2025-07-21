# EMDX Maintenance Guide

This guide covers health monitoring, maintenance operations, and troubleshooting for EMDX knowledge bases. Version 0.7.0 introduces comprehensive health metrics and automated maintenance capabilities.

## Table of Contents
- [Health Monitoring](#health-monitoring)
- [Maintenance Operations](#maintenance-operations)
- [Metric Interpretation](#metric-interpretation)
- [Troubleshooting Guide](#troubleshooting-guide)
- [Best Practices](#best-practices)
- [Maintenance Schedules](#maintenance-schedules)

## Health Monitoring

### Overview

EMDX uses a weighted scoring system to calculate overall knowledge base health (0-100%):

```bash
# Quick health check
emdx analyze --health

# Detailed health report with all metrics
emdx analyze --health --json | jq
```

### Health Score Components

| Metric | Weight | Description | Target |
|--------|--------|-------------|--------|
| Tag Coverage | 30% | Percentage of documents with tags | >80% |
| Duplicate Ratio | 25% | Inverse of duplicate document ratio | <5% duplicates |
| Organization Score | 25% | Documents with projects assigned | >90% |
| Activity Score | 20% | Recent access patterns | Varies |

### Health Status Levels

- **90-100%**: Excellent - Well-maintained knowledge base
- **80-89%**: Good - Minor improvements recommended
- **70-79%**: Fair - Maintenance needed
- **60-69%**: Poor - Significant issues present
- **<60%**: Critical - Immediate attention required

## Maintenance Operations

### Automated Maintenance

The `emdx maintain` command provides intelligent maintenance with dry-run safety:

```bash
# Preview all recommended fixes
emdx maintain --auto

# Apply all fixes
emdx maintain --auto --execute

# Specific maintenance tasks
emdx maintain --clean          # Remove duplicates/empty docs
emdx maintain --merge          # Merge similar documents
emdx maintain --tags           # Auto-tag documents
emdx maintain --gc             # Database optimization
emdx maintain --lifecycle      # Update document stages
```

### Manual Maintenance Tasks

#### 1. Duplicate Removal

```bash
# Find duplicates
emdx analyze --duplicates

# Review specific duplicate set
emdx analyze --duplicates --json | jq '.duplicates[0]'

# Remove duplicates (keeps most recently accessed)
emdx maintain --clean --execute
```

#### 2. Document Merging

```bash
# Find similar documents (>85% similarity)
emdx analyze --similar

# Adjust similarity threshold
emdx analyze --similar --threshold 0.90

# Merge similar documents
emdx maintain --merge --execute
```

#### 3. Auto-Tagging

```bash
# Preview tag suggestions
emdx maintain --tags

# Apply auto-tagging
emdx maintain --tags --execute

# Check tag coverage after
emdx analyze --tags
```

#### 4. Database Optimization

```bash
# Run garbage collection
emdx maintain --gc --execute

# This performs:
# - VACUUM to reclaim space
# - REINDEX for query performance
# - ANALYZE for query planner stats
```

## Metric Interpretation

### Tag Coverage Analysis

```bash
emdx analyze --tags --json | jq '.tag_metrics'
```

**Interpreting Results:**
- **High Coverage (>80%)**: Documents are well-categorized
- **Medium Coverage (50-80%)**: Many documents need tags
- **Low Coverage (<50%)**: Systematic tagging needed

**Common Issues:**
- Imported documents often lack tags
- Older documents may have outdated tags
- Quick captures frequently untagged

**Solutions:**
```bash
# Auto-tag untagged documents
emdx find --no-tags --ids-only | xargs -I {} emdx maintain --tags --doc {}

# Bulk tag by content patterns
emdx find "meeting" --no-tags --ids-only | xargs -I {} emdx tag {} "meeting"
```

### Duplicate Detection

```bash
emdx analyze --duplicates --json | jq '.summary'
```

**Types of Duplicates:**
1. **Exact Duplicates**: Identical content
2. **Near Duplicates**: >85% similar content
3. **Title Duplicates**: Same title, different content

**Resolution Strategies:**
```bash
# Safe removal (keeps most accessed)
emdx maintain --clean --strategy keep-most-accessed --execute

# Manual review
emdx analyze --duplicates --json | jq -r '.duplicates[] | 
  "Set \(.set_id): \(.ids | join(", "))"'
```

### Lifecycle Patterns

```bash
emdx lifecycle analyze --json | jq '.patterns'
```

**Key Metrics:**
- **Success Rate**: Percentage of completed gameplans marked successful
- **Average Duration**: Time from creation to completion
- **Stale Documents**: Active items unchanged for >30 days
- **Abandonment Rate**: Items that never complete

**Improving Lifecycle Health:**
```bash
# Find stale active gameplans
emdx find --tags "gameplan,active" --date-to "30 days ago"

# Transition abandoned items
emdx lifecycle auto-detect --execute
```

## Troubleshooting Guide

### Common Issues and Solutions

#### 1. Low Health Score

**Symptoms:**
- Health score consistently below 70%
- Degrading search performance
- Difficult to find documents

**Diagnosis:**
```bash
# Get detailed breakdown
emdx analyze --all --json > health-report.json
jq '.health_metrics' health-report.json
```

**Solutions:**
```bash
# Run comprehensive maintenance
emdx maintain --auto --execute

# If score still low, check specific metrics
emdx analyze --tags      # Fix: auto-tag
emdx analyze --duplicates # Fix: clean
emdx analyze --empty     # Fix: remove
```

#### 2. Search Performance Issues

**Symptoms:**
- Slow search results
- Incomplete matches
- Timeout errors

**Diagnosis:**
```bash
# Check database size
ls -lh ~/.config/emdx/knowledge.db

# Analyze search patterns
emdx find "test query" --json | jq '.metadata.execution_time'
```

**Solutions:**
```bash
# Rebuild FTS index
emdx maintain --gc --rebuild-fts --execute

# Optimize database
emdx maintain --gc --execute

# For very large databases (>1GB)
emdx maintain --gc --aggressive --execute
```

#### 3. Tag Inconsistencies

**Symptoms:**
- Similar tags with different names
- Emoji/text alias confusion
- Orphaned tags

**Diagnosis:**
```bash
# List all tags with usage
emdx tags --sort usage

# Find similar tag names
emdx tags --json | jq -r '.tags[].name' | sort | uniq -d
```

**Solutions:**
```bash
# Merge similar tags
emdx merge-tags "🐛" "bug" --into "bug"

# Remove unused tags
emdx tags --unused --json | jq -r '.tags[].name' | 
  xargs -I {} emdx tag --remove-unused {}
```

#### 4. Duplicate Document Explosion

**Symptoms:**
- Same content saved multiple times
- Rapid growth in document count
- High duplicate ratio (>20%)

**Diagnosis:**
```bash
# Check duplicate patterns
emdx analyze --duplicates --json | jq '.patterns'

# Find source of duplicates
emdx analyze --duplicates --by-date --json
```

**Solutions:**
```bash
# Immediate cleanup
emdx maintain --clean --aggressive --execute

# Prevent future duplicates
# Add to save workflow:
content_hash=$(echo "$content" | sha256sum)
if ! emdx find --hash "$content_hash" --json | jq -e '.count == 0'; then
  echo "Duplicate content detected"
fi
```

### Database Issues

#### Corruption Recovery

```bash
# Check database integrity
sqlite3 ~/.config/emdx/knowledge.db "PRAGMA integrity_check;"

# If corruption detected:
# 1. Backup corrupted database
cp ~/.config/emdx/knowledge.db ~/knowledge.db.corrupt

# 2. Export what can be saved
emdx list --json > export.json 2>/dev/null || true

# 3. Rebuild from export
mv ~/.config/emdx/knowledge.db ~/.config/emdx/knowledge.db.old
emdx import export.json
```

#### Migration Failures

```bash
# Check current schema version
sqlite3 ~/.config/emdx/knowledge.db "SELECT version FROM schema_version;"

# Force migration retry
emdx db migrate --force

# Manual migration (last resort)
emdx db export > backup.json
rm ~/.config/emdx/knowledge.db
emdx db import backup.json
```

## Best Practices

### Preventive Maintenance

1. **Regular Health Checks**
   ```bash
   # Add to daily routine
   alias emdx-health='emdx analyze --health'
   ```

2. **Scheduled Maintenance**
   ```bash
   # Weekly maintenance script
   #!/bin/bash
   emdx maintain --auto --execute
   emdx analyze --health
   ```

3. **Tag Hygiene**
   - Use consistent tag naming
   - Leverage emoji aliases
   - Regular tag audits
   - Document tag meanings

4. **Duplicate Prevention**
   - Check before saving
   - Use meaningful titles
   - Regular cleanup
   - Monitor duplicate ratio

### Performance Optimization

1. **Database Maintenance**
   ```bash
   # Monthly optimization
   emdx maintain --gc --execute
   ```

2. **Search Optimization**
   - Use specific queries
   - Leverage tag filters
   - Limit result sets
   - Index frequently searched fields

3. **Storage Management**
   ```bash
   # Archive old documents
   emdx find --date-to "1 year ago" --tags "archived" --ids-only |
     xargs -I {} emdx export {} --format json > archive.json
   ```

## Maintenance Schedules

### Daily Tasks (Automated)
- Health score check
- Auto-tag new documents
- Lifecycle transitions
- Duplicate detection

### Weekly Tasks
- Comprehensive maintenance run
- Tag audit
- Performance check
- Backup verification

### Monthly Tasks
- Database optimization
- Storage cleanup
- Metrics analysis
- Strategy review

### Quarterly Tasks
- Full system audit
- Tag taxonomy review
- Workflow optimization
- Archive old content

## Monitoring and Alerts

### Setup Health Monitoring

```bash
#!/bin/bash
# health-monitor.sh

THRESHOLD=70
HEALTH=$(emdx analyze --health --json | jq '.health_score')

if [ "$HEALTH" -lt "$THRESHOLD" ]; then
  # Send alert (email, Slack, etc.)
  echo "EMDX Health Alert: Score dropped to ${HEALTH}%" |
    mail -s "EMDX Health Warning" admin@example.com
    
  # Auto-remediate
  emdx maintain --auto --execute
fi
```

### Metrics Dashboard

Create a simple metrics dashboard:

```bash
#!/bin/bash
# dashboard.sh

clear
echo "=== EMDX Health Dashboard ==="
echo "Generated: $(date)"
echo ""

# Health Score
health=$(emdx analyze --health --json | jq -r '.health_score')
echo "Overall Health: ${health}%"

# Key Metrics
emdx analyze --all --json | jq -r '
  "Documents: \(.total_documents)",
  "Projects: \(.total_projects)",
  "Tag Coverage: \(.tag_coverage)%",
  "Duplicate Ratio: \(.duplicate_ratio)%",
  "Active Gameplans: \(.active_gameplans)"
'

echo ""
echo "=== Recent Activity ==="
emdx find --date-from "today" --json | jq -r '
  "Documents Today: \(.count)"
'

echo ""
echo "=== Recommendations ==="
emdx analyze --health --json | jq -r '.recommendations[]'
```

## Conclusion

Effective maintenance keeps your EMDX knowledge base healthy and performant. Key principles:

1. **Monitor regularly** - Check health scores frequently
2. **Automate routine tasks** - Use cron jobs and scripts
3. **Act on metrics** - Don't ignore declining scores
4. **Prevent issues** - Better than fixing them later
5. **Document patterns** - Track what works for your workflow

For additional support, see the [Troubleshooting](#troubleshooting-guide) section or file an issue on GitHub.