# EMDX Automation Guide

EMDX 0.7.0 introduces powerful Unix pipeline integration and JSON output, enabling sophisticated automation workflows. This guide shows you how to integrate EMDX into your development workflow.

## 🎯 New in 0.7.0

EMDX 0.7.0 transforms automation capabilities:
- **Consolidated commands** make scripting simpler
- **JSON everywhere** enables sophisticated pipelines
- **Auto-tagging** reduces manual organization
- **Health monitoring** enables proactive maintenance
- **Dry-run by default** prevents automation accidents

## 🔧 Core Automation Features

### Pipeline-Friendly Output

EMDX commands now support flags designed for Unix pipelines:

- `--ids-only` - Output only document IDs (one per line)
- `--json` - Machine-readable JSON output
- `--format json|csv` - Export in standard formats
- `--quiet` - Suppress decorative output

### Date Filtering

Filter documents by creation or modification time:

- `--created-after DATE`
- `--created-before DATE`
- `--modified-after DATE`
- `--modified-before DATE`

Dates can be:
- ISO format: `2025-01-15`
- Relative: `yesterday`, `last week`, `2 days ago`

### Tag Filtering

Advanced tag operations:

- `--tags TAG1,TAG2` - Must have ALL tags (AND)
- `--any-tags TAG1,TAG2` - Must have ANY tag (OR)
- `--no-tags TAG1,TAG2` - Must NOT have these tags

## 📚 Automation Recipes

### Daily Knowledge Capture

```bash
#!/bin/bash
# capture-daily-notes.sh
# Run at end of day to capture various logs and notes

# Capture git commits from today
git log --since="today 00:00" --oneline | \
  emdx save --title "Git commits $(date +%Y-%m-%d)" --tags "daily,git"

# Capture Docker status
docker ps -a | \
  emdx save --title "Docker status $(date +%Y-%m-%d)" --tags "daily,docker"

# Capture system logs
journalctl --since today | tail -100 | \
  emdx save --title "System logs $(date +%Y-%m-%d)" --tags "daily,logs"

echo "Daily capture complete!"
```

### Automated Tagging

```bash
#!/bin/bash
# auto-tag-documents.sh
# Automatically tag documents based on content patterns

# Tag all Python-related documents
emdx find "import python def class" --ids-only | \
  xargs -I {} emdx tag {} python

# Tag all Docker/Kubernetes content
emdx find "docker kubernetes container pod" --ids-only | \
  xargs -I {} emdx tag {} devops

# Tag all bug reports
emdx find "bug error exception failed" --ids-only | \
  xargs -I {} emdx tag {} bug

# Tag old active items as stale
emdx find --tags "active" --modified-before "30 days ago" --ids-only | \
  xargs -I {} emdx tag {} stale
```

### Knowledge Base Health Monitor

```bash
#!/bin/bash
# health-monitor.sh
# Monitor knowledge base health and alert on issues

# Get health score
HEALTH_SCORE=$(emdx analyze --health --json | jq '.overall_score')

# Check if health is poor
if (( $(echo "$HEALTH_SCORE < 0.7" | bc -l) )); then
    echo "WARNING: Knowledge base health is poor: ${HEALTH_SCORE}"
    
    # Get specific issues
    emdx analyze --health --json | jq '.metrics | to_entries[] | 
      select(.value.score < 70) | 
      "\(.key): \(.value.details)"'
    
    # Send notification (example with mail)
    echo "Knowledge base health is ${HEALTH_SCORE}. Run 'emdx maintain --auto' to fix." | \
      mail -s "EMDX Health Alert" user@example.com
fi
```

### Duplicate Detection and Cleanup

```bash
#!/bin/bash
# find-and-review-duplicates.sh
# Interactive duplicate review process

# Find duplicates and save to file
emdx analyze --duplicates --json > duplicates.json

# Count duplicate groups
DUPE_COUNT=$(jq '.exact_duplicates.count' duplicates.json)

if [ "$DUPE_COUNT" -gt 0 ]; then
    echo "Found $DUPE_COUNT duplicate groups"
    
    # Review each group
    jq -r '.exact_duplicates.groups[] | 
      "=== Duplicate Group: \(.title) ===\nIDs: \(.ids | join(", "))\n"' duplicates.json
    
    read -p "Remove duplicates automatically? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        emdx maintain --clean --execute
    fi
fi
```

### Project Documentation Sync

```bash
#!/bin/bash
# sync-project-docs.sh
# Keep project documentation in sync with EMDX

PROJECT="my-project"
DOCS_DIR="./docs"

# Find all markdown files modified today
find "$DOCS_DIR" -name "*.md" -mtime -1 | while read -r file; do
    # Check if already in EMDX
    TITLE=$(basename "$file" .md)
    DOC_ID=$(emdx find --exact-title "$TITLE" --project "$PROJECT" --ids-only | head -1)
    
    if [ -z "$DOC_ID" ]; then
        # New document
        emdx save "$file" --project "$PROJECT" --tags "docs,auto-sync"
        echo "Added: $file"
    else
        # Update existing
        emdx edit "$DOC_ID" < "$file"
        echo "Updated: $file"
    fi
done
```

## 🤖 Cron Job Examples

Add these to your crontab with `crontab -e`:

```bash
# Daily maintenance at 2 AM
0 2 * * * /usr/local/bin/emdx maintain --auto --execute >> /var/log/emdx-maintain.log 2>&1

# Hourly health check
0 * * * * /usr/local/bin/emdx analyze --health --json >> /var/log/emdx-health.jsonl

# Weekly duplicate cleanup
0 0 * * 0 /usr/local/bin/emdx maintain --clean --execute

# Tag untagged documents every evening
0 18 * * * /usr/local/bin/emdx maintain --tags --execute

# Backup database daily
0 3 * * * cp ~/.config/emdx/knowledge.db ~/backups/emdx-$(date +\%Y\%m\%d).db
```

## 📊 Analytics and Reporting

### Growth Tracking

```bash
#!/bin/bash
# track-growth.sh
# Track knowledge base growth over time

# Append current stats to log
emdx analyze --json | jq '{
  date: now | strftime("%Y-%m-%d"),
  total_documents: .statistics.total_documents,
  total_projects: .statistics.total_projects,
  health_score: .health.overall_score
}' >> ~/emdx-growth.jsonl

# Generate monthly report
jq -s '
  group_by(.date[0:7]) | 
  map({
    month: .[0].date[0:7],
    avg_health: (map(.health_score) | add / length),
    doc_growth: (.[0].total_documents - .[-1].total_documents),
    final_count: .[-1].total_documents
  })
' ~/emdx-growth.jsonl
```

### Tag Usage Analysis

```bash
#!/bin/bash
# analyze-tag-usage.sh

# Get tag statistics
emdx tags --format json | jq -r '
  sort_by(.count) | reverse | .[] | 
  "\(.name): \(.count) documents"
' > tag-report.txt

# Find untagged documents from last week
emdx find --created-after "1 week ago" --no-tags "*" --format json | \
  jq -r '.[] | "[\(.id)] \(.title)"' > untagged-recent.txt

# Find overtagged documents (more than 5 tags)
emdx list --format json | jq -r '
  .[] | select(.tags | length > 5) | 
  "[\(.id)] \(.title): \(.tags | length) tags"
' > overtagged.txt
```

## 🔗 Integration Examples

### Git Hooks

`.git/hooks/post-commit`:
```bash
#!/bin/bash
# Save commit message to EMDX

COMMIT_MSG=$(git log -1 --pretty=%B)
COMMIT_SHA=$(git log -1 --pretty=%h)

echo "$COMMIT_MSG" | emdx save \
  --title "Commit $COMMIT_SHA" \
  --tags "git,commit,auto" \
  --project "$(basename $(git rev-parse --show-toplevel))"
```

### CI/CD Integration

```yaml
# .github/workflows/document.yml
name: Document to EMDX

on:
  pull_request:
    types: [closed]

jobs:
  document:
    if: github.event.pull_request.merged == true
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Install EMDX
        run: pip install emdx
      
      - name: Document PR
        run: |
          PR_BODY="${{ github.event.pull_request.body }}"
          PR_TITLE="${{ github.event.pull_request.title }}"
          echo "$PR_BODY" | emdx save \
            --title "PR #${{ github.event.pull_request.number }}: $PR_TITLE" \
            --tags "pr,merged,auto"
```

### Docker Integration

```dockerfile
# Dockerfile
FROM python:3.9-slim

# Install EMDX for documentation
RUN pip install emdx

# Copy documentation automation scripts
COPY scripts/emdx-automation /usr/local/bin/
RUN chmod +x /usr/local/bin/emdx-automation/*

# Run documentation capture on container start
ENTRYPOINT ["/usr/local/bin/emdx-automation/capture-runtime.sh"]
```

## 🏗️ Building Custom Tools

### EMDX API Wrapper

```python
#!/usr/bin/env python3
# emdx_api.py
# Python wrapper for EMDX automation

import subprocess
import json
from datetime import datetime
from typing import List, Dict, Optional

class EMDX:
    @staticmethod
    def save(content: str, title: str, tags: List[str] = None) -> int:
        """Save content to EMDX and return document ID."""
        cmd = ['emdx', 'save', '--title', title]
        if tags:
            cmd.extend(['--tags', ','.join(tags)])
        
        result = subprocess.run(
            cmd, 
            input=content.encode(), 
            capture_output=True
        )
        
        # Parse ID from output
        output = result.stdout.decode()
        if "Document saved with ID:" in output:
            return int(output.split("ID:")[1].strip())
        return None
    
    @staticmethod
    def find(query: str, tags: List[str] = None) -> List[Dict]:
        """Search documents and return results."""
        cmd = ['emdx', 'find', query, '--format', 'json']
        if tags:
            cmd.extend(['--tags', ','.join(tags)])
        
        result = subprocess.run(cmd, capture_output=True)
        return json.loads(result.stdout.decode())
    
    @staticmethod
    def analyze_health() -> Dict:
        """Get knowledge base health metrics."""
        result = subprocess.run(
            ['emdx', 'analyze', '--health', '--json'],
            capture_output=True
        )
        return json.loads(result.stdout.decode())

# Example usage
if __name__ == "__main__":
    # Save a document
    doc_id = EMDX.save(
        "This is automated content",
        f"Auto-saved at {datetime.now()}",
        ["python", "auto"]
    )
    
    # Search documents
    results = EMDX.find("automated", tags=["python"])
    
    # Check health
    health = EMDX.analyze_health()
    print(f"Health score: {health['overall_score']:.2%}")
```

### Slack Integration

```python
#!/usr/bin/env python3
# emdx_slack_bot.py
# Save Slack messages to EMDX

import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import subprocess

slack_token = os.environ["SLACK_BOT_TOKEN"]
client = WebClient(token=slack_token)

def save_to_emdx(message, channel_name, user_name):
    """Save Slack message to EMDX."""
    content = f"From: {user_name}\nChannel: #{channel_name}\n\n{message}"
    title = f"Slack: {message[:50]}..."
    
    subprocess.run([
        'emdx', 'save',
        '--title', title,
        '--tags', 'slack,chat,auto',
        '--project', 'slack-archive'
    ], input=content.encode())

# Save important messages when they're reacted to with :bookmark:
def handle_reaction_added(event):
    if event['reaction'] == 'bookmark':
        # Get the message
        result = client.conversations_history(
            channel=event['item']['channel'],
            latest=event['item']['ts'],
            limit=1
        )
        
        message = result['messages'][0]
        save_to_emdx(
            message['text'],
            event['channel'],
            message['user']
        )
```

## 🎯 Best Practices

### 1. Use Dry-Run First
Always test maintenance operations with dry-run:
```bash
emdx maintain --auto          # See what would happen
emdx maintain --auto --execute # Actually do it
```

### 2. Consistent Tagging
Create a tagging script for consistency:
```bash
#!/bin/bash
# tag-conventions.sh

# Status tags
STATUS_TAGS="active done blocked stale"

# Type tags  
TYPE_TAGS="bug feature docs test refactor"

# Apply conventions
emdx find --no-tags "$STATUS_TAGS" --ids-only | \
  xargs -I {} emdx tag {} active
```

### 3. Regular Backups
```bash
#!/bin/bash
# backup-emdx.sh

BACKUP_DIR="$HOME/backups/emdx"
mkdir -p "$BACKUP_DIR"

# Backup with timestamp
cp ~/.config/emdx/knowledge.db \
   "$BACKUP_DIR/knowledge-$(date +%Y%m%d-%H%M%S).db"

# Keep only last 30 days
find "$BACKUP_DIR" -name "knowledge-*.db" -mtime +30 -delete
```

### 4. Monitor Growth
Track your knowledge base growth:
```bash
# Add to .bashrc/.zshrc
alias emdx-stats='emdx analyze --json | jq -r "
  \"Documents: \" + (.statistics.total_documents | tostring) + 
  \"\nProjects: \" + (.statistics.total_projects | tostring) +
  \"\nHealth: \" + (.health.overall_score * 100 | floor | tostring) + \"%\"
"'
```

## 🚀 Advanced Workflows

### Multi-Stage Pipeline
```bash
# Complex workflow: Find stale bugs, review, and archive

# Stage 1: Find stale bugs
emdx find --tags "bug,active" --modified-before "60 days ago" --ids-only > stale-bugs.txt

# Stage 2: Generate report
cat stale-bugs.txt | while read -r id; do
    emdx view "$id" --format json | jq -r '"[\(.id)] \(.title)"'
done > stale-bugs-report.txt

# Stage 3: Interactive review
echo "Review stale bugs:"
cat stale-bugs-report.txt

# Stage 4: Batch transition
cat stale-bugs.txt | xargs -I {} emdx lifecycle transition {} archived
```

### Knowledge Base As Code
```yaml
# emdx-config.yml
# Define your knowledge base structure

projects:
  - name: my-app
    auto_tags: [development, app]
    
  - name: research
    auto_tags: [research, notes]

automation:
  - name: tag-python-files
    trigger: "*.py"
    tags: [python, code]
    
  - name: archive-old-active
    schedule: "0 0 * * 0"  # Weekly
    command: |
      emdx find --tags active --modified-before "90 days ago" --ids-only |
      xargs -I {} emdx lifecycle transition {} archived
```

## 🛠️ Troubleshooting

### Debug Mode
```bash
# Enable debug output
export EMDX_DEBUG=1
emdx find "test" --ids-only

# Check what commands would run
set -x  # Enable bash debug
./my-automation-script.sh
```

### Common Issues

1. **Permission Denied**
   ```bash
   chmod +x ~/.local/bin/emdx-*
   ```

2. **Cron Not Running**
   ```bash
   # Check cron logs
   grep CRON /var/log/syslog
   
   # Ensure full paths in crontab
   which emdx  # Get full path
   ```

3. **JSON Parsing Errors**
   ```bash
   # Validate JSON output
   emdx analyze --json | jq empty
   ```

## 🌟 Success Stories

### Story 1: The DevOps Team
"We pipe our Docker logs and Kubernetes events directly into EMDX. Auto-tagging identifies issues immediately. Our incident response time dropped by 40%."

```bash
# Their automation
kubectl events | emdx save --title "K8s events $(date)" --auto-tag
docker logs app | tail -1000 | emdx save --title "App logs" --auto-tag
```

### Story 2: The Research Lab
"EMDX replaced our mess of text files. The health monitoring keeps our research organized, and JSON export feeds directly into our analysis pipeline."

```bash
# Their daily routine
emdx maintain --auto --execute
emdx find --tags "experiment,active" --format json | python analyze.py
```

### Story 3: The Solo Developer
"I save everything - code snippets, debug sessions, architecture decisions. The weekly maintenance keeps it manageable. It's like having a personal knowledge assistant."

```bash
# Their git hook
git log -1 --pretty=full | emdx save --title "Commit: %s" --auto-tag
```

Start automating today and let EMDX work for you! 🤖