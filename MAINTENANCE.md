# EMDX Maintenance Guide

This guide explains how to keep your EMDX knowledge base healthy, organized, and performing optimally.

## 📊 Understanding Health Metrics

EMDX 0.7.0 introduces a comprehensive health monitoring system with 6 weighted metrics:

### Overall Health Score

The overall health score (0-100%) is calculated from weighted metrics:

```bash
emdx analyze --health
```

Output example:
```
Overall Health Score: 85%

Health Metrics:
Tag Coverage      75%  ⚠️   75% of documents have tags
Duplicate Ratio   95%  ✅   Only 5% duplicates found
Organization      90%  ✅   Well-organized projects
Activity          80%  ✅   Regular access patterns
Quality           85%  ✅   Good content quality
Growth            70%  ⚠️   Steady growth rate
```

### Individual Metrics Explained

#### 1. Tag Coverage (Weight: 25%)
- **What it measures**: Percentage of documents with at least one tag
- **Good**: >80% tagged
- **Warning**: 60-80% tagged
- **Poor**: <60% tagged
- **How to improve**: Run `emdx maintain --tags --execute`

#### 2. Duplicate Ratio (Weight: 20%)
- **What it measures**: Inverse of duplicate percentage (fewer is better)
- **Good**: <5% duplicates
- **Warning**: 5-10% duplicates
- **Poor**: >10% duplicates
- **How to improve**: Run `emdx maintain --clean --execute`

#### 3. Organization (Weight: 20%)
- **What it measures**: Project distribution and naming consistency
- **Good**: Documents spread across multiple projects with balanced distribution
- **Warning**: Most documents in one project or "[No Project]"
- **Poor**: No project organization
- **How to improve**: Use `--project` when saving documents, or save from git repos for auto-detection

#### 4. Activity (Weight: 15%)
- **What it measures**: Recent access patterns and usage
- **Good**: Regular access across documents
- **Warning**: Some stale documents
- **Poor**: Many untouched documents
- **How to improve**: Review and update old content

#### 5. Quality (Weight: 15%)
- **What it measures**: Content length, empty documents, metadata
- **Good**: Rich content with good metadata
- **Warning**: Some thin content
- **Poor**: Many empty or minimal documents
- **How to improve**: Enrich thin documents or remove them

#### 6. Growth (Weight: 5%)
- **What it measures**: Knowledge base growth rate
- **Good**: Steady growth
- **Warning**: Slowing growth
- **Poor**: No recent additions
- **How to improve**: Regular documentation habits

## 🔧 Maintenance Commands

### Interactive Maintenance Wizard

The easiest way to maintain your knowledge base:

```bash
emdx maintain
```

This will:
1. Analyze your knowledge base
2. Show current health score
3. List all issues found
4. Ask what you want to fix
5. Execute selected fixes

### Automated Maintenance

Fix everything automatically:

```bash
# Dry run first (default)
emdx maintain --auto

# Execute all fixes
emdx maintain --auto --execute
```

### Specific Maintenance Tasks

#### Clean Duplicates and Empty Documents
```bash
# See what would be cleaned
emdx maintain --clean

# Actually clean
emdx maintain --clean --execute
```

This will:
- Remove exact duplicate documents (keeping the one with most views)
- Remove documents with less than 10 characters
- Preserve all data in trash (recoverable)

#### Auto-Tag Documents
```bash
# Preview auto-tagging
emdx maintain --tags

# Apply auto-tags
emdx maintain --tags --execute
```

Auto-tagging rules:
- Analyzes title and content
- Applies confidence-based tagging (>60% confidence)
- Maximum 3 tags per document
- Conservative to avoid over-tagging

#### Merge Similar Documents
```bash
# Find merge candidates
emdx maintain --merge

# Merge with default threshold (70%)
emdx maintain --merge --execute

# Merge with custom threshold
emdx maintain --merge --threshold 0.85 --execute
```

Merging process:
- Finds documents with >70% similarity
- Keeps document with more views
- Intelligently combines content
- Preserves all metadata

#### Garbage Collection
```bash
# Check what needs cleaning
emdx maintain --gc

# Run garbage collection
emdx maintain --gc --execute
```

Garbage collection removes:
- Orphaned tags (no documents)
- Old trash (>30 days)
- Database fragmentation (vacuum)

#### Lifecycle Management
```bash
# Review stale gameplans
emdx maintain --lifecycle

# Auto-transition stale items
emdx maintain --lifecycle --execute
```

Lifecycle rules:
- Active → Blocked: No updates for 30 days
- Active → Done: Marked complete in content
- Blocked → Archived: Blocked for 90+ days

## 📅 Maintenance Schedules

### Daily Tasks (Automated)
```bash
# Add to crontab
0 6 * * * emdx maintain --tags --execute
0 7 * * * emdx analyze --health --json >> health.log
```

### Weekly Tasks
```bash
# Sunday maintenance
0 2 * * 0 emdx maintain --clean --execute
0 3 * * 0 emdx maintain --merge --execute
```

### Monthly Tasks
```bash
# First of month
0 4 1 * * emdx maintain --gc --execute
0 5 1 * * emdx lifecycle analyze
```

### Quarterly Review (Manual)
```bash
# Run interactively every 3 months
emdx maintain
emdx analyze --all
emdx projects  # Review project organization
```

## 🚨 Troubleshooting Common Issues

### Low Tag Coverage

**Symptoms**: Health score below 70%, many untagged documents

**Solution**:
```bash
# Find untagged documents
emdx find --no-tags "*" --format json | jq -r '.[] | "[\(.id)] \(.title)"'

# Auto-tag them
emdx maintain --tags --execute

# Manually tag specific types
emdx find "bug error" --no-tags "*" --ids-only | xargs -I {} emdx tag {} bug
```

### High Duplicate Count

**Symptoms**: Duplicate ratio metric below 80%

**Solution**:
```bash
# Analyze duplicates in detail
emdx analyze --duplicates --json | jq '.exact_duplicates.groups[0:5]'

# Review before cleaning
emdx maintain --clean  # Dry run

# Clean if satisfied
emdx maintain --clean --execute
```

### Poor Organization

**Symptoms**: Most documents in "[No Project]"

**Solution**:
```bash
# List documents without projects
emdx list --project "[No Project]"

# Batch update projects based on tags
emdx find --tags "python" --project "[No Project]" --ids-only | \
  xargs -I {} emdx update {} --project "python-scripts"
```

### Stale Content

**Symptoms**: Low activity score, old documents

**Solution**:
```bash
# Find stale documents
emdx find --modified-before "6 months ago" --limit 20

# Review and update or archive
emdx find --modified-before "1 year ago" --ids-only | \
  xargs -I {} emdx lifecycle transition {} archived
```

## 🏥 Health Monitoring Automation

### Health Tracking Script

```bash
#!/bin/bash
# track-health.sh
# Run daily to track health over time

# Get current health
HEALTH=$(emdx analyze --health --json)

# Extract key metrics
echo "$HEALTH" | jq '{
  timestamp: now,
  overall_score: .overall_score,
  metrics: .metrics | map_values(.value),
  statistics: .statistics
}' >> ~/.config/emdx/health-history.jsonl

# Alert if health drops
SCORE=$(echo "$HEALTH" | jq '.overall_score')
if (( $(echo "$SCORE < 0.7" | bc -l) )); then
    echo "EMDX health dropped to ${SCORE}!"
    # Send notification
fi
```

### Health Dashboard

Create a simple health dashboard:

```bash
#!/bin/bash
# health-dashboard.sh

echo "=== EMDX Health Dashboard ==="
echo

# Current health
emdx analyze --health

echo -e "\n=== Recent Trends ==="
# Show last 7 days
tail -7 ~/.config/emdx/health-history.jsonl | \
  jq -r '"\(.timestamp | strftime("%Y-%m-%d")): \(.overall_score * 100 | floor)%"'

echo -e "\n=== Quick Actions ==="
echo "1. Run maintenance: emdx maintain"
echo "2. View duplicates: emdx analyze --duplicates"
echo "3. Find untagged: emdx find --no-tags '*'"
```

## 🔍 Deep Cleaning

Sometimes you need a thorough cleanup:

### Complete Cleanup Process

```bash
#!/bin/bash
# deep-clean.sh
# Thorough knowledge base cleanup

echo "Starting deep clean..."

# 1. Backup first!
cp ~/.config/emdx/knowledge.db ~/.config/emdx/knowledge.db.backup

# 2. Remove duplicates
echo "Removing duplicates..."
emdx maintain --clean --execute

# 3. Merge similar documents
echo "Merging similar documents..."
emdx maintain --merge --threshold 0.8 --execute

# 4. Auto-tag everything
echo "Auto-tagging documents..."
emdx maintain --tags --execute

# 5. Transition stale items
echo "Managing lifecycle..."
emdx maintain --lifecycle --execute

# 6. Garbage collection
echo "Running garbage collection..."
emdx maintain --gc --execute

# 7. Final report
echo -e "\n=== Final Health Report ==="
emdx analyze --health

echo -e "\nDeep clean complete!"
```

## 📈 Maintaining High Health

### Best Practices

1. **Tag Everything**: Make tagging a habit
   ```bash
   # Always include tags when saving
   emdx save document.md --tags "relevant,tags,here"
   ```

2. **Use Projects**: Organize by project from the start
   ```bash
   # Project is auto-detected from git, or specify:
   emdx save notes.md --project "my-project"
   ```

3. **Regular Reviews**: Schedule weekly reviews
   ```bash
   # Add to calendar/cron
   emdx recent 20  # Review recent additions
   emdx find --no-tags "*" --limit 10  # Tag untagged
   ```

4. **Avoid Duplicates**: Search before saving
   ```bash
   # Check if content exists
   emdx find "unique phrase from document"
   ```

5. **Rich Content**: Save meaningful documents
   - Include context and details
   - Avoid one-line documents
   - Add descriptions to code snippets

### Health Goals

Aim for these targets:

| Metric | Target | Why |
|--------|--------|-----|
| Overall Health | >85% | Indicates well-maintained KB |
| Tag Coverage | >90% | Everything findable |
| Duplicate Ratio | >95% | Minimal redundancy |
| Organization | >80% | Clear structure |
| Activity | >70% | Living documentation |
| Quality | >80% | Valuable content |

## 🌟 Real-World Maintenance Workflows

### Workflow 1: The Morning Routine
```bash
#!/bin/bash
# morning-review.sh
# Start your day with a healthy knowledge base

echo "🌅 Good morning! Let's check your knowledge base..."
echo

# Quick health check
emdx analyze --health | grep "Overall Score"

# Show what needs attention
echo -e "\n🔧 Maintenance needed:"
emdx maintain --auto | grep -A 5 "This will:"

# Recent additions that need tags
echo -e "\n🏷️  Recent documents without tags:"
emdx find --created-after "yesterday" --no-tags "*" --limit 5

# Today's active gameplans
echo -e "\n🎯 Active gameplans:"
emdx find --tags "gameplan,active" --limit 5
```

### Workflow 2: The Weekly Sprint Review
```bash
#!/bin/bash
# sprint-review.sh
# End of sprint knowledge cleanup

echo "=== Sprint Knowledge Review ==="

# Documents created this sprint
echo "Documents created this week:"
emdx find --created-after "1 week ago" --format json | jq 'length'

# Tag the sprint's work
SPRINT="sprint-$(date +%U)"
emdx find --created-after "1 week ago" --ids-only | \
  xargs -I {} emdx tag {} "$SPRINT"

# Archive completed gameplans
echo -e "\nCompleted gameplans:"
emdx find --tags "gameplan,done" --modified-after "1 week ago" \
  --ids-only | xargs -I {} emdx lifecycle transition {} archived

# Clean up
emdx maintain --auto --execute
```

### Workflow 3: The Monthly Deep Dive
```bash
#!/bin/bash
# monthly-analysis.sh
# Monthly knowledge base analysis and cleanup

MONTH=$(date +%B)
echo "=== $MONTH Knowledge Base Analysis ==="

# Growth metrics
echo "Growth this month:"
emdx analyze --json | jq -r '
  "Total documents: \(.statistics.total_documents)
  Active projects: \(.statistics.total_projects)
  Unique tags: \(.statistics.total_tags)"
'

# Project-level health
echo -e "\nProject Health Scores:"
emdx project-stats --json | jq -r '.projects[] | 
  "\(.name): \(.document_count) docs, \(.avg_tags_per_doc) avg tags"
'

# Find neglected projects
echo -e "\nProjects needing attention:"
emdx project-stats --json | jq -r '.projects[] | 
  select(.days_since_last_update > 30) | .name
'

# Deep maintenance
echo -e "\nRunning deep maintenance..."
emdx maintain --auto --execute
emdx maintain --gc --execute
```

## 🆘 Recovery Procedures

### Restore from Trash

```bash
# View trash
emdx trash

# Restore specific document
emdx restore 123

# Restore all documents deleted today
emdx trash --deleted-after "today" --ids-only | \
  xargs -I {} emdx restore {}
```

### Restore from Backup

```bash
# List backups
ls -la ~/.config/emdx/knowledge.db.*

# Restore from backup
cp ~/.config/emdx/knowledge.db.backup ~/.config/emdx/knowledge.db
```

### Export Before Major Changes

```bash
# Full export
emdx list --format json > export-$(date +%Y%m%d).json

# Export with content
emdx export --full > full-export-$(date +%Y%m%d).json
```

## 🎯 Maintenance Checklist

Use this checklist for manual maintenance:

- [ ] Check overall health score
- [ ] Review untagged documents
- [ ] Look for duplicates
- [ ] Check for empty documents
- [ ] Review stale gameplans
- [ ] Update project assignments
- [ ] Run garbage collection
- [ ] Backup database
- [ ] Review growth trends
- [ ] Update maintenance scripts

## 💡 Pro Tips

### Preventive Maintenance
1. **Always use auto-tag on save**: `emdx save doc.md --auto-tag`
2. **Search before saving** to avoid duplicates
3. **Use meaningful titles** for better organization
4. **Regular small cleanups** beat big maintenance sessions

### Performance Optimization
```bash
# Optimize database after major operations
emdx maintain --gc --execute

# Check database size
du -h ~/.config/emdx/knowledge.db

# Export old content before archiving
emdx find --modified-before "1 year ago" --format json > archive.json
```

### Integration with Development Workflow
```bash
# Git post-commit hook
#!/bin/bash
# .git/hooks/post-commit
git diff --name-only HEAD~1 | grep -E '\.(md|txt|doc)$' | \
  xargs -I {} emdx save {} --auto-tag --project "$(basename $(pwd))"
```

Keep your knowledge base healthy and it will serve you well! 🌟