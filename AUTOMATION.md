# EMDX Automation Guide

This guide demonstrates how to integrate EMDX into automated workflows, CI/CD pipelines, and scheduled maintenance tasks using the powerful Unix pipeline integration introduced in version 0.7.0.

## Table of Contents
- [JSON Output Format](#json-output-format)
- [Pipeline Integration](#pipeline-integration)
- [Cron Job Configurations](#cron-job-configurations)
- [CI/CD Integration](#cicd-integration)
- [Scripting Best Practices](#scripting-best-practices)
- [Real-World Examples](#real-world-examples)

## JSON Output Format

Most EMDX commands support `--json` output for programmatic access:

```bash
# Basic JSON output
emdx find "api" --json
emdx analyze --health --json
emdx list --json
emdx lifecycle status --json
```

### Standard JSON Response Structure

```json
{
  "success": true,
  "count": 42,
  "documents": [
    {
      "id": 123,
      "title": "API Documentation",
      "content": "...",
      "project": "backend",
      "tags": ["docs", "api"],
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-20T15:45:00Z"
    }
  ],
  "metadata": {
    "query": "api",
    "execution_time": 0.042
  }
}
```

## Pipeline Integration

### Basic Pipeline Examples

```bash
# Count documents by project
emdx list --json | jq -r '.documents | group_by(.project) | map({project: .[0].project, count: length})'

# Extract all unique tags
emdx tags --json | jq -r '.tags[].name' | sort -u

# Find documents modified in last 7 days
emdx find --date-from "7 days ago" --json | jq -r '.documents[].title'

# Get IDs of all gameplan documents
emdx find --tags "gameplan" --ids-only | head -10
```

### Advanced Filtering

```bash
# Find urgent bugs not assigned
emdx find --tags "bug,urgent" --json | \
  jq -r '.documents[] | select(.tags | contains(["assigned"]) | not) | .id'

# Documents by complexity (word count)
emdx list --json | \
  jq -r '.documents[] | {id: .id, title: .title, words: (.content | split(" ") | length)}' | \
  jq -s 'sort_by(.words) | reverse | .[:10]'

# Active gameplans by age
emdx find --tags "gameplan,active" --json | \
  jq -r '.documents[] | {
    title: .title,
    age_days: ((now - (.created_at | fromdateiso8601)) / 86400 | floor)
  }' | jq -s 'sort_by(.age_days) | reverse'
```

### Batch Operations

```bash
#!/bin/bash
# Tag all documents containing "TODO" as needing review
emdx find "TODO" --ids-only | while read -r id; do
  emdx tag "$id" "needs-review"
done

# Archive completed gameplans older than 30 days
emdx find --tags "gameplan,done" --date-to "30 days ago" --json | \
  jq -r '.documents[].id' | \
  xargs -I {} emdx lifecycle transition {} archived

# Bulk export documents by project
for project in $(emdx projects --json | jq -r '.projects[]'); do
  emdx list --project "$project" --json > "export/${project}.json"
done
```

## Cron Job Configurations

### Daily Maintenance

```bash
# /etc/cron.d/emdx-maintenance
# Run daily maintenance at 2 AM
0 2 * * * user /usr/local/bin/emdx-daily-maintenance.sh
```

#### `/usr/local/bin/emdx-daily-maintenance.sh`
```bash
#!/bin/bash
set -e

LOG_FILE="/var/log/emdx/maintenance-$(date +%Y%m%d).log"
REPORT_FILE="/var/log/emdx/health-$(date +%Y%m%d).json"

echo "=== EMDX Daily Maintenance Started at $(date) ===" >> "$LOG_FILE"

# 1. Generate health report
emdx analyze --all --json > "$REPORT_FILE"

# 2. Check health score
HEALTH_SCORE=$(jq '.health_score' "$REPORT_FILE")
echo "Current health score: $HEALTH_SCORE%" >> "$LOG_FILE"

# 3. Run maintenance if health is low
if [ "$HEALTH_SCORE" -lt 80 ]; then
  echo "Running automated maintenance..." >> "$LOG_FILE"
  emdx maintain --auto --execute >> "$LOG_FILE" 2>&1
fi

# 4. Clean up old documents
emdx maintain --clean --execute >> "$LOG_FILE" 2>&1

# 5. Auto-tag untagged documents
emdx maintain --tags --execute >> "$LOG_FILE" 2>&1

# 6. Update lifecycle stages
emdx lifecycle auto-detect --execute >> "$LOG_FILE" 2>&1

# 7. Generate summary
echo "=== Maintenance Summary ===" >> "$LOG_FILE"
emdx analyze --health --json | jq '.summary' >> "$LOG_FILE"

echo "=== EMDX Daily Maintenance Completed at $(date) ===" >> "$LOG_FILE"
```

### Weekly Reports

```bash
# /etc/cron.d/emdx-reports
# Generate weekly report every Monday at 8 AM
0 8 * * 1 user /usr/local/bin/emdx-weekly-report.sh
```

#### `/usr/local/bin/emdx-weekly-report.sh`
```bash
#!/bin/bash
set -e

REPORT_DIR="/var/reports/emdx"
WEEK=$(date +%Y-W%V)
REPORT_FILE="${REPORT_DIR}/weekly-${WEEK}.md"

cat > "$REPORT_FILE" << EOF
# EMDX Weekly Report - Week $WEEK
Generated: $(date)

## Health Overview
$(emdx analyze --health)

## Activity Summary
$(emdx find --date-from "7 days ago" --json | jq -r '
  "- New documents: \(.count)",
  "- Projects active: \(.documents | map(.project) | unique | length)"
')

## Gameplan Status
$(emdx lifecycle analyze)

## Top Tags This Week
$(emdx find --date-from "7 days ago" --json | \
  jq -r '.documents[].tags[]' | sort | uniq -c | sort -nr | head -10)

## Maintenance Actions
$(emdx maintain --auto --json | jq -r '.recommendations[]')
EOF

# Email the report (optional)
# mail -s "EMDX Weekly Report - $WEEK" team@example.com < "$REPORT_FILE"
```

### Hourly Sync

```bash
# /etc/cron.d/emdx-sync
# Sync to backup every hour
0 * * * * user /usr/local/bin/emdx-backup.sh
```

#### `/usr/local/bin/emdx-backup.sh`
```bash
#!/bin/bash
set -e

BACKUP_DIR="/backup/emdx/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Export all data
emdx list --json > "$BACKUP_DIR/metadata.json"

# Backup each document
emdx list --ids-only | while read -r id; do
  emdx view "$id" --raw > "$BACKUP_DIR/doc-${id}.md"
done

# Compress
tar -czf "$BACKUP_DIR.tar.gz" "$BACKUP_DIR"
rm -rf "$BACKUP_DIR"

# Keep only last 30 days
find /backup/emdx -name "*.tar.gz" -mtime +30 -delete
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Knowledge Base Health Check

on:
  schedule:
    - cron: '0 0 * * *'  # Daily
  workflow_dispatch:

jobs:
  health-check:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Install EMDX
      run: |
        pip install emdx
        
    - name: Check Knowledge Base Health
      run: |
        HEALTH=$(emdx analyze --health --json | jq '.health_score')
        echo "Health Score: $HEALTH%"
        if [ "$HEALTH" -lt 70 ]; then
          echo "::error::Knowledge base health is critically low"
          exit 1
        elif [ "$HEALTH" -lt 80 ]; then
          echo "::warning::Knowledge base health needs attention"
        fi
        
    - name: Generate Report
      run: |
        emdx analyze --all --json > health-report.json
        
    - name: Upload Report
      uses: actions/upload-artifact@v3
      with:
        name: health-report
        path: health-report.json
        
    - name: Auto-fix Issues
      if: failure()
      run: |
        emdx maintain --auto --execute
        emdx analyze --health
```

### GitLab CI Example

```yaml
knowledge-base-maintenance:
  stage: maintenance
  rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
  script:
    - pip install emdx
    - |
      # Health check
      HEALTH=$(emdx analyze --health --json | jq '.health_score')
      echo "Knowledge Base Health: $HEALTH%"
      
      # Maintenance
      if [ "$HEALTH" -lt 80 ]; then
        emdx maintain --auto --execute
      fi
      
      # Report
      emdx analyze --all --json > report.json
  artifacts:
    reports:
      junit: report.json
    expire_in: 30 days
```

## Scripting Best Practices

### Error Handling

```bash
#!/bin/bash
set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Check if EMDX is installed
if ! command -v emdx &> /dev/null; then
    echo "Error: emdx is not installed"
    exit 1
fi

# Use JSON output for reliable parsing
if ! RESULT=$(emdx find "test" --json 2>/dev/null); then
    echo "Error: Search failed"
    exit 1
fi

# Validate JSON response
if ! echo "$RESULT" | jq -e '.success' > /dev/null; then
    echo "Error: Invalid response"
    exit 1
fi
```

### Idempotent Operations

```bash
#!/bin/bash
# Safe re-tagging (won't fail if tag exists)
tag_document() {
    local doc_id=$1
    shift
    local tags=("$@")
    
    # Get current tags
    current_tags=$(emdx tag "$doc_id" --json | jq -r '.tags[]')
    
    # Add only missing tags
    for tag in "${tags[@]}"; do
        if ! echo "$current_tags" | grep -q "^$tag$"; then
            emdx tag "$doc_id" "$tag"
        fi
    done
}
```

### Performance Optimization

```bash
# Use --ids-only for faster operations
emdx find "bug" --ids-only | parallel -j 4 process_document {}

# Batch operations instead of individual calls
ids=$(emdx find "needs-review" --ids-only | paste -sd " " -)
if [ -n "$ids" ]; then
    emdx tag $ids "reviewed"  # Tag all at once
fi

# Use JSON for complex filtering (avoid multiple searches)
emdx list --json > cache.json
jq -r '.documents[] | select(.tags | contains(["urgent"])) | .id' cache.json
```

## Real-World Examples

### 1. Jira Integration

```bash
#!/bin/bash
# sync-to-jira.sh - Create Jira tickets from urgent bugs

JIRA_PROJECT="PROJ"
JIRA_URL="https://company.atlassian.net"

emdx find --tags "bug,urgent" --exclude-tags "jira-created" --json | \
jq -r '.documents[] | @base64' | while read -r doc_base64; do
    doc=$(echo "$doc_base64" | base64 -d)
    
    id=$(echo "$doc" | jq -r '.id')
    title=$(echo "$doc" | jq -r '.title')
    content=$(echo "$doc" | jq -r '.content' | head -n 20)
    
    # Create Jira ticket
    response=$(curl -s -X POST \
        -H "Authorization: Bearer $JIRA_TOKEN" \
        -H "Content-Type: application/json" \
        "$JIRA_URL/rest/api/3/issue" \
        -d "{
            \"fields\": {
                \"project\": {\"key\": \"$JIRA_PROJECT\"},
                \"summary\": \"[EMDX] $title\",
                \"description\": \"From EMDX document #$id\\n\\n$content\",
                \"issuetype\": {\"name\": \"Bug\"}
            }
        }")
    
    if [ $? -eq 0 ]; then
        jira_key=$(echo "$response" | jq -r '.key')
        emdx tag "$id" "jira-created" "jira:$jira_key"
        echo "Created Jira ticket $jira_key for document $id"
    fi
done
```

### 2. Slack Notifications

```bash
#!/bin/bash
# notify-stale-gameplans.sh - Alert on stale active gameplans

SLACK_WEBHOOK="https://hooks.slack.com/services/XXX/YYY/ZZZ"
STALE_DAYS=14

stale_gameplans=$(emdx find --tags "gameplan,active" \
    --date-to "$STALE_DAYS days ago" --json | \
    jq -r '.documents[] | "• \(.title) (idle for \(.days_since_update) days)"')

if [ -n "$stale_gameplans" ]; then
    curl -X POST "$SLACK_WEBHOOK" \
        -H "Content-Type: application/json" \
        -d "{
            \"text\": \"⚠️ *Stale Gameplans Alert*\",
            \"blocks\": [{
                \"type\": \"section\",
                \"text\": {
                    \"type\": \"mrkdwn\",
                    \"text\": \"The following gameplans have been inactive for >$STALE_DAYS days:\\n$stale_gameplans\"
                }
            }]
        }"
fi
```

### 3. Documentation Site Generator

```bash
#!/bin/bash
# generate-docs-site.sh - Build static site from EMDX

OUTPUT_DIR="./docs-site"
mkdir -p "$OUTPUT_DIR"

# Generate index
cat > "$OUTPUT_DIR/index.md" << EOF
# Knowledge Base

Last updated: $(date)

## Projects
EOF

# Add project pages
emdx projects --json | jq -r '.projects[]' | while read -r project; do
    echo "- [$project](./$project.html)" >> "$OUTPUT_DIR/index.md"
    
    # Create project page
    cat > "$OUTPUT_DIR/$project.md" << EOF
# $project

[Back to index](./index.html)

## Documents
EOF
    
    # Add documents
    emdx list --project "$project" --json | \
    jq -r '.documents[] | "- [\(.title)](\(.id).html)"' >> "$OUTPUT_DIR/$project.md"
    
    # Export each document
    emdx list --project "$project" --ids-only | while read -r id; do
        emdx view "$id" --raw > "$OUTPUT_DIR/$id.md"
    done
done

# Convert to HTML with pandoc
find "$OUTPUT_DIR" -name "*.md" -exec \
    pandoc {} -o {}.html --template=template.html \;
```

### 4. Metrics Dashboard Data

```bash
#!/bin/bash
# metrics-export.sh - Export metrics for Grafana/Prometheus

METRICS_FILE="/var/lib/prometheus/node_exporter/emdx_metrics.prom"

cat > "$METRICS_FILE" << EOF
# HELP emdx_health_score Knowledge base health score
# TYPE emdx_health_score gauge
emdx_health_score $(emdx analyze --health --json | jq '.health_score')

# HELP emdx_document_count Total number of documents
# TYPE emdx_document_count gauge
emdx_document_count $(emdx stats --json | jq '.total_documents')

# HELP emdx_active_gameplans Number of active gameplans
# TYPE emdx_active_gameplans gauge
emdx_active_gameplans $(emdx find --tags "gameplan,active" --json | jq '.count')

# HELP emdx_success_rate Gameplan success rate
# TYPE emdx_success_rate gauge
emdx_success_rate $(emdx lifecycle analyze --json | jq '.success_rate')

# HELP emdx_duplicate_ratio Duplicate document ratio
# TYPE emdx_duplicate_ratio gauge
emdx_duplicate_ratio $(emdx analyze --duplicates --json | jq '.duplicate_ratio')
EOF
```

## Conclusion

EMDX's JSON output and Unix pipeline integration enable powerful automation workflows. Key takeaways:

1. **Always use `--json`** for reliable parsing in scripts
2. **Implement proper error handling** with set -e and validation
3. **Use dry-run by default** - require explicit `--execute` flags
4. **Batch operations** for better performance
5. **Monitor health scores** to maintain knowledge base quality
6. **Automate routine maintenance** to prevent degradation

For more examples and updates, check the [EMDX repository](https://github.com/arockwell/emdx).