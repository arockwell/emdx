# EMDX Real-World Examples & Workflows

A collection of practical examples showing how to use EMDX 0.7.0's powerful features in real-world scenarios.

## 🎆 What's New in These Examples

These workflows showcase EMDX 0.7.0's game-changing features:

- **🤖 Auto-tagging**: Every `emdx save` includes `--auto-tag` for intelligent organization
- **📊 JSON Integration**: Complex pipelines using `--json` and `jq` for data processing
- **🚀 Pipeline Power**: Unix-style automation with `--ids-only` and `xargs`
- **🏥 Health Monitoring**: Automated maintenance and health tracking
- **🔄 Consolidated Commands**: Using `analyze` and `maintain` for powerful operations
- **📅 Date Filtering**: Time-based queries with `--created-after` and `--modified-before`
- **🏷️ Smart Tagging**: Lifecycle management and tag-based workflows

### 📝 How to Use These Examples

1. **Copy and adapt**: Each script is a starting point - modify for your needs
2. **Combine workflows**: Mix and match patterns from different examples
3. **Start simple**: Begin with basic versions and add complexity over time
4. **Test first**: Always run with dry-run or preview modes when available

### 🛠️ Prerequisites

These examples assume you have:
- EMDX 0.7.0+ installed
- Basic shell scripting knowledge
- Common Unix tools: `jq`, `curl`, `git`
- Optional: `gh` CLI for GitHub integration

## 📚 Table of Contents

1. [Daily Development Workflows](#daily-development-workflows)
   - Capture Everything During Debugging
   - Code Review Workflow
2. [Project Management](#project-management)
   - Sprint Planning Automation
   - Project Documentation Generator
3. [Research & Learning](#research--learning)
   - Learning Journal Workflow
   - Research Session Capture
4. [DevOps & Monitoring](#devops--monitoring)
   - Incident Response Automation
   - Performance Monitoring
5. [Team Collaboration](#team-collaboration)
   - Standup Notes Aggregator
   - Knowledge Sharing Session
6. [Advanced Automation](#advanced-automation)
   - Self-Organizing Knowledge Base
   - AI-Powered Summary Generator
   - Cross-Project Knowledge Transfer
7. [Learning & Onboarding](#learning--onboarding)
   - New Team Member Onboarding
   - Personal Learning Path
8. [Consulting & Client Work](#consulting--client-work)
   - Client Project Setup
9. [Academic Research](#academic-research)
   - Literature Review Workflow
10. [Enterprise Integration](#enterprise-integration)
    - Confluence/Wiki Migration

## 💻 Daily Development Workflows

### Capture Everything During Debugging

```bash
#!/bin/bash
# debug-session.sh
# Capture a complete debugging session

SESSION="debug-$(date +%Y%m%d-%H%M%S)"

# Start capturing
echo "Starting debug session: $SESSION"

# Capture initial state
docker ps | emdx save --title "$SESSION: Initial Docker state" --tags "debug,docker" --auto-tag

# Capture error logs
docker logs app 2>&1 | tail -100 | emdx save --title "$SESSION: Error logs" --tags "debug,error" --auto-tag

# Capture your debugging notes
cat << EOF | emdx save --title "$SESSION: Debug notes" --tags "debug,notes"
## Issue
Application failing with connection timeout

## Investigation
- Checked Docker network: OK
- Checked env vars: Missing DB_HOST
- Checked logs: Connection refused to localhost:5432

## Solution
DB_HOST was not set in docker-compose.yml
EOF

# Capture the fix
git diff | emdx save --title "$SESSION: Fix applied" --tags "debug,solution" --auto-tag

echo "Debug session captured. View with: emdx find --tags debug --created-after today"
```

### Code Review Workflow

```bash
#!/bin/bash
# code-review.sh
# Capture insights from code reviews

PR_NUMBER=$1
REPO=$(basename $(git rev-parse --show-toplevel))

# Get PR details
gh pr view $PR_NUMBER --json title,body,commits,reviews > pr-details.json

# Save PR summary
jq -r '"# PR #\(.number): \(.title)\n\n\(.body)"' pr-details.json | \
  emdx save --title "Review: PR #$PR_NUMBER" --tags "review,pr,$REPO" --auto-tag

# Save review comments
jq -r '.reviews[] | "## Review by \(.author.login)\n\(.body)"' pr-details.json | \
  emdx save --title "Review comments: PR #$PR_NUMBER" --tags "review,feedback" --auto-tag

# Save your own review notes
echo "What did you learn from this PR?" 
read -r learning
echo "$learning" | emdx save --title "Learning: PR #$PR_NUMBER" --tags "learning,review" --auto-tag

rm pr-details.json
```

## 📊 Project Management

### Sprint Planning Automation

```bash
#!/bin/bash
# sprint-planning.sh
# Organize sprint planning with EMDX

SPRINT_NUM=$1
SPRINT_START=$(date +%Y-%m-%d)
SPRINT_END=$(date -d "+2 weeks" +%Y-%m-%d)

# Create sprint gameplan
cat << EOF | emdx save --title "Sprint $SPRINT_NUM Gameplan" --tags "gameplan,sprint-$SPRINT_NUM,active" --auto-tag
# Sprint $SPRINT_NUM: $SPRINT_START to $SPRINT_END

## Goals
1. Complete user authentication
2. Fix critical bugs from last sprint
3. Deploy to staging

## Tasks
- [ ] Implement JWT tokens
- [ ] Add password reset flow
- [ ] Fix memory leak in worker
- [ ] Update documentation
- [ ] Performance testing

## Success Metrics
- All tests passing
- <200ms API response time
- Zero critical bugs
EOF

# Import Jira/GitHub issues
gh issue list --limit 20 --label "sprint-$SPRINT_NUM" --json number,title,body | \
  jq -r '.[] | "# Issue #\(.number): \(.title)\n\n\(.body)"' | \
  while IFS= read -r issue; do
    echo "$issue" | emdx save --title "Sprint $SPRINT_NUM: $(echo "$issue" | head -1)" \
      --tags "task,sprint-$SPRINT_NUM,active" --auto-tag
  done

echo "Sprint $SPRINT_NUM planned! Track with: emdx find --tags sprint-$SPRINT_NUM"
```

### Project Documentation Generator

```bash
#!/bin/bash
# generate-docs.sh
# Generate project documentation from EMDX

PROJECT=${1:-$(basename $(pwd))}
OUTPUT="docs/project-knowledge.md"

mkdir -p docs

cat << EOF > $OUTPUT
# $PROJECT Knowledge Base

Generated on $(date)

## Overview
EOF

# Add project stats
emdx stats --project "$PROJECT" >> $OUTPUT

cat << EOF >> $OUTPUT

## Active Gameplans
EOF

# List active gameplans
emdx find --tags "gameplan,active" --project "$PROJECT" --format json | \
  jq -r '.[] | "- [\(.id)] \(.title)"' >> $OUTPUT

cat << EOF >> $OUTPUT

## Recent Learnings
EOF

# Recent learnings
emdx find --tags "learning" --project "$PROJECT" --created-after "1 month ago" \
  --format json | jq -r '.[] | "### \(.title)\n\(.snippet)\n"' >> $OUTPUT

cat << EOF >> $OUTPUT

## Solved Issues
EOF

# Documented solutions
emdx find --tags "solution" --project "$PROJECT" --limit 10 --format json | \
  jq -r '.[] | "- \(.title) (ID: \(.id))"' >> $OUTPUT

echo "Documentation generated at $OUTPUT"
```

## 🔬 Research & Learning

### Learning Journal Workflow

```bash
#!/bin/bash
# learning-journal.sh
# Track what you learn each day

# Today's learning entry
TITLE="Learning Journal: $(date +%Y-%m-%d)"

# Check if today's entry exists
EXISTING=$(emdx find --exact-title "$TITLE" --ids-only | head -1)

if [ -z "$EXISTING" ]; then
  # Create new entry
  cat << EOF | emdx save --title "$TITLE" --tags "journal,learning,active" --auto-tag
# Learning Journal: $(date +%Y-%m-%d)

## What I Learned Today

### Technical
- 

### Concepts
- 

### Tools
- 

### To Explore
- 

## Reflections

EOF
  echo "Created today's journal. Opening for edit..."
  emdx edit "$TITLE"
else
  # Append to existing
  echo "Updating today's journal..."
  emdx edit "$EXISTING"
fi
```

### Research Session Capture

```bash
#!/bin/bash
# research-session.sh
# Capture research findings systematically

TOPIC="$1"
if [ -z "$TOPIC" ]; then
  echo "Usage: $0 <research-topic>"
  exit 1
fi

SESSION_ID="research-$(date +%s)"

# Create research gameplan
cat << EOF | emdx save --title "Research: $TOPIC" --tags "research,gameplan,active" --auto-tag
# Research Gameplan: $TOPIC

## Objective
Understanding $TOPIC

## Key Questions
1. What is it?
2. How does it work?
3. When to use it?
4. Best practices?
5. Common pitfalls?

## Resources to Check
- [ ] Official documentation
- [ ] Tutorial videos
- [ ] GitHub examples
- [ ] Blog posts
- [ ] Stack Overflow

## Notes
(Research findings will be linked here)
EOF

echo "Research session started: $SESSION_ID"
echo "Save findings with tag: research-$SESSION_ID"

# Helper function for the session
cat << 'EOF' > /tmp/research-save.sh
#!/bin/bash
FINDING="$1"
echo "$FINDING" | emdx save --title "Finding: $TOPIC - $(date +%H:%M)" \
  --tags "research,research-$SESSION_ID,finding" --auto-tag
EOF
chmod +x /tmp/research-save.sh

echo "Use this to save findings: /tmp/research-save.sh \"your finding\""
```

## 🚀 DevOps & Monitoring

### Incident Response Automation

```bash
#!/bin/bash
# incident-response.sh
# Automated incident documentation

SEVERITY=$1  # critical|high|medium|low
DESCRIPTION="$2"

INCIDENT_ID="INC-$(date +%Y%m%d-%H%M%S)"

# Create incident record
cat << EOF | emdx save --title "Incident $INCIDENT_ID: $DESCRIPTION" \
  --tags "incident,$SEVERITY,active" --auto-tag
# Incident Report: $INCIDENT_ID

**Severity**: $SEVERITY
**Reported**: $(date)
**Status**: Investigating

## Description
$DESCRIPTION

## Impact
- 

## Timeline
- $(date +%H:%M) - Incident reported
- 

## Root Cause
(To be determined)

## Resolution
(In progress)

## Follow-up Actions
- [ ] Root cause analysis
- [ ] Update monitoring
- [ ] Document lessons learned
EOF

# Capture system state
echo "## System State at $(date)" | emdx save --title "$INCIDENT_ID: System State" \
  --tags "incident,diagnostics" --auto-tag

# Capture key metrics
df -h | emdx save --title "$INCIDENT_ID: Disk Usage" --tags "incident,metrics" --auto-tag
free -m | emdx save --title "$INCIDENT_ID: Memory Usage" --tags "incident,metrics" --auto-tag
docker ps | emdx save --title "$INCIDENT_ID: Running Containers" --tags "incident,docker" --auto-tag

echo "Incident $INCIDENT_ID created. Track with: emdx find --tags incident,$INCIDENT_ID"
```

### Performance Monitoring

```bash
#!/bin/bash
# performance-monitor.sh
# Track application performance over time

APP_NAME="myapp"
ENDPOINT="https://api.example.com/health"

# Run performance test
RESPONSE_TIME=$(curl -w "%{time_total}" -o /dev/null -s "$ENDPOINT")
STATUS_CODE=$(curl -w "%{http_code}" -o /dev/null -s "$ENDPOINT")

# Save results
cat << EOF | emdx save --title "Performance: $APP_NAME $(date +%Y-%m-%d_%H:%M)" \
  --tags "performance,monitoring,$APP_NAME" --auto-tag
# Performance Report: $APP_NAME

**Timestamp**: $(date)
**Endpoint**: $ENDPOINT
**Response Time**: ${RESPONSE_TIME}s
**Status Code**: $STATUS_CODE

## Metrics
\`\`\`
Response Time: ${RESPONSE_TIME}s
Status: $STATUS_CODE
Load Average: $(uptime | awk -F'load average:' '{print $2}')
Memory Free: $(free -m | grep Mem | awk '{print $4}')MB
\`\`\`
EOF

# Alert if slow
if (( $(echo "$RESPONSE_TIME > 1.0" | bc -l) )); then
  echo "SLOW RESPONSE DETECTED: ${RESPONSE_TIME}s" | \
    emdx save --title "ALERT: Slow Response $(date +%H:%M)" --tags "alert,performance,urgent" --auto-tag
fi
```

## 👥 Team Collaboration

### Standup Notes Aggregator

```bash
#!/bin/bash
# team-standup.sh
# Aggregate team standup notes

TEAM="engineering"
DATE=$(date +%Y-%m-%d)

# Create standup summary
cat << EOF | emdx save --title "Team Standup: $DATE" --tags "standup,team,$TEAM" --auto-tag
# $TEAM Team Standup - $DATE

## Team Updates

EOF

# Collect individual updates
for member in alice bob charlie; do
  echo "Enter $member's update (end with Ctrl-D):"
  update=$(cat)
  
  cat << EOF | emdx save --title "Standup: $member - $DATE" --tags "standup,individual" --auto-tag
### $member
$update

EOF
done

# Find blockers across all standups
echo "## Team Blockers" | emdx save --title "Blockers: $DATE" --tags "standup,blockers,urgent" --auto-tag
emdx find "blocked OR blocker OR stuck" --created-after "today" --tags "standup" | \
  emdx save --title "Blockers Summary: $DATE" --tags "standup,blockers,urgent" --auto-tag
```

### Knowledge Sharing Session

```bash
#!/bin/bash
# knowledge-share.sh
# Document knowledge sharing sessions

TOPIC="$1"
PRESENTER="$2"

# Pre-session prep
cat << EOF | emdx save --title "Knowledge Share Prep: $TOPIC" --tags "knowledge-share,prep" --auto-tag
# Knowledge Sharing Session: $TOPIC

**Presenter**: $PRESENTER
**Date**: $(date +%Y-%m-%d)
**Attendees**: 

## Agenda
1. Introduction (5 min)
2. Core Concepts (15 min)
3. Demo (15 min)
4. Q&A (10 min)
5. Next Steps (5 min)

## Key Points to Cover
- 
- 
- 

## Resources
- 
- 
EOF

# During session - quick capture
echo "During the session, capture insights with:"
echo "emdx save --tags knowledge-share,insight,$(echo $TOPIC | tr ' ' '-')"

# Post-session
cat << 'EOF' > /tmp/session-summary.sh
#!/bin/bash
cat << SUMMARY | emdx save --title "Knowledge Share Summary: $TOPIC" \
  --tags "knowledge-share,summary,learning" --auto-tag
## Summary: $TOPIC

### Key Takeaways
1. 
2. 
3. 

### Action Items
- [ ] 
- [ ] 

### Questions for Follow-up
- 
- 

### Recording
[Link to recording]

### Feedback
- What went well:
- What could improve:
SUMMARY
EOF
chmod +x /tmp/session-summary.sh

echo "After session, run: /tmp/session-summary.sh"
```

## 🤖 Advanced Automation

### Self-Organizing Knowledge Base

```bash
#!/bin/bash
# self-organize.sh
# Fully automated knowledge base maintenance

LOG_FILE="$HOME/.config/emdx/automation.log"

log() {
    echo "[$(date)] $1" >> "$LOG_FILE"
}

# Morning optimization
morning_routine() {
    log "Starting morning optimization"
    
    # Auto-tag everything from yesterday
    emdx find --created-after "yesterday" --no-tags "*" --ids-only | \
      xargs -I {} emdx tag {} --suggest --apply
    
    # Check health
    HEALTH=$(emdx analyze --health --json | jq '.overall_score')
    log "Health score: $HEALTH"
    
    if (( $(echo "$HEALTH < 0.8" | bc -l) )); then
        log "Running auto-maintenance"
        emdx maintain --auto --execute
    fi
}

# Afternoon analysis
afternoon_analysis() {
    log "Starting afternoon analysis"
    
    # Find and link related documents
    emdx analyze --similar --json | jq -r '.similar_groups[] | 
      select(.similarity > 0.8) | .documents[]' | while read -r doc_id; do
        # Add cross-reference tags
        emdx tag "$doc_id" "see-also"
    done
    
    # Archive completed items
    emdx find --tags "done" --modified-before "1 week ago" --ids-only | \
      xargs -I {} emdx lifecycle transition {} archived
}

# Evening backup
evening_backup() {
    log "Starting evening backup"
    
    # Export today's additions
    emdx find --created-after "today" --format json > \
      "$HOME/backups/emdx-$(date +%Y%m%d).json"
    
    # Compress old backups
    find "$HOME/backups" -name "emdx-*.json" -mtime +7 -exec gzip {} \;
    
    # Generate daily report
    emdx analyze --all --json | jq '{
        date: now | strftime("%Y-%m-%d"),
        health: .overall_score,
        new_docs: .statistics.documents_today,
        active_projects: .statistics.active_projects,
        top_tags: .top_tags[0:5]
    }' | emdx save --title "Daily Report: $(date +%Y-%m-%d)" \
          --tags "report,automated" --auto-tag
}

# Determine time of day and run appropriate routine
HOUR=$(date +%H)

if [ "$HOUR" -lt 12 ]; then
    morning_routine
elif [ "$HOUR" -lt 17 ]; then
    afternoon_analysis
else
    evening_backup
fi

log "Automation complete"
```

### AI-Powered Summary Generator

```bash
#!/bin/bash
# ai-summary.sh
# Generate AI summaries of your knowledge base

PROJECT="${1:-all}"
DAYS="${2:-7}"

# Export recent documents
if [ "$PROJECT" = "all" ]; then
    DOCS=$(emdx find --created-after "$DAYS days ago" --format json)
else
    DOCS=$(emdx find --project "$PROJECT" --created-after "$DAYS days ago" --format json)
fi

# Create prompt for AI
cat << EOF > /tmp/ai-prompt.txt
Please analyze these documents and provide:
1. Key themes and patterns
2. Important decisions made
3. Problems solved
4. Areas needing attention
5. Suggested next actions

Documents:
$DOCS
EOF

# If you have an AI CLI tool installed (like llm or claude)
# llm -m gpt-4 < /tmp/ai-prompt.txt | \
#   emdx save --title "AI Analysis: $PROJECT ($(date +%Y-%m-%d))" \
#   --tags "analysis,ai-generated,summary" --auto-tag

echo "AI prompt saved to /tmp/ai-prompt.txt"
echo "Use with your preferred AI tool to generate insights"
```

### Cross-Project Knowledge Transfer

```bash
#!/bin/bash
# knowledge-transfer.sh
# Share learnings across projects

SOURCE_PROJECT="$1"
TARGET_PROJECT="$2"

if [ -z "$SOURCE_PROJECT" ] || [ -z "$TARGET_PROJECT" ]; then
    echo "Usage: $0 <source-project> <target-project>"
    exit 1
fi

echo "Transferring knowledge from $SOURCE_PROJECT to $TARGET_PROJECT"

# Find transferable knowledge
emdx find --project "$SOURCE_PROJECT" --tags "learning,solution,best-practice" \
  --format json > /tmp/transfer.json

# Process each document
jq -r '.[] | @base64' /tmp/transfer.json | while read -r doc_base64; do
    doc=$(echo "$doc_base64" | base64 -d)
    
    # Extract key info
    title=$(echo "$doc" | jq -r '.title')
    content=$(echo "$doc" | jq -r '.content')
    tags=$(echo "$doc" | jq -r '.tags | join(",")')
    
    # Create transferred document
    cat << EOF | emdx save --title "[Transfer] $title" \
      --project "$TARGET_PROJECT" \
      --tags "transferred,$tags" --auto-tag
# Transferred from: $SOURCE_PROJECT

$content

---
*Transferred on $(date) for cross-project learning*
EOF
done

echo "Knowledge transfer complete!"
rm /tmp/transfer.json
```

## 🎯 Quick Command Reference

```bash
# Most useful command combinations

# Find recent untagged documents
emdx find --created-after "1 week ago" --no-tags "*"

# Export project knowledge
emdx list --project "myproject" --format json > myproject-knowledge.json

# Bulk tag by content
emdx find "docker" --ids-only | xargs -I {} emdx tag {} docker devops

# Archive old documents
emdx find --modified-before "6 months ago" --ids-only | \
  xargs -I {} emdx lifecycle transition {} archived

# Generate tag cloud
emdx tags --format json | jq -r '.[] | "\(.count)\t\(.name)"' | \
  sort -nr | head -20

# Find empty documents
emdx analyze --empty --json | jq -r '.empty_documents[]'

# Track knowledge growth
emdx stats --json | jq '{date: now, docs: .total_documents}' >> growth.jsonl
```

## 🎓 Learning & Onboarding

### New Team Member Onboarding

```bash
#!/bin/bash
# onboard-teammate.sh
# Create comprehensive onboarding knowledge base

TEAMMEMBER="$1"
TEAM="$2"

if [ -z "$TEAMMEMBER" ] || [ -z "$TEAM" ]; then
    echo "Usage: $0 <name> <team>"
    exit 1
fi

# Create onboarding gameplan
cat << EOF | emdx save --title "Onboarding: $TEAMMEMBER ($TEAM)" --tags "onboarding,gameplan,active" --auto-tag
# Onboarding Plan: $TEAMMEMBER

**Team**: $TEAM
**Start Date**: $(date +%Y-%m-%d)
**Buddy**: [Assign buddy]

## Week 1: Foundation
- [ ] Complete security setup
- [ ] Access to all required systems
- [ ] Read team documentation
- [ ] Shadow experienced team member
- [ ] First small task assignment

## Week 2: Deep Dive
- [ ] Understand codebase architecture
- [ ] Review recent project history
- [ ] Attend all team meetings
- [ ] Complete first medium task

## Week 3: Integration
- [ ] Lead a small feature
- [ ] Present learnings to team
- [ ] Contribute to documentation
- [ ] Identify improvement opportunities

## Resources
- Team handbook: [link]
- Code repositories: [links]
- Contact list: [link]
EOF

# Collect essential team knowledge
emdx find --tags "team-knowledge,$TEAM" --format json | \
  jq -r '.[] | "- [\(.id)] \(.title)"' | \
  emdx save --title "Essential Reading: $TEAM Team" --tags "onboarding,reading-list" --auto-tag

echo "Onboarding plan created for $TEAMMEMBER"
echo "Track progress with: emdx find --tags onboarding,$TEAMMEMBER"
```

### Personal Learning Path

```bash
#!/bin/bash
# learning-path.sh
# Create structured learning paths for new technologies

TECH="$1"
GOAL="$2"

if [ -z "$TECH" ]; then
    echo "Usage: $0 <technology> [goal]"
    exit 1
fi

GOAL=${GOAL:-"Understand and use effectively"}

# Create learning gameplan
cat << EOF | emdx save --title "Learning Path: $TECH" --tags "learning,gameplan,active" --auto-tag
# Learning Path: $TECH

**Goal**: $GOAL
**Started**: $(date +%Y-%m-%d)
**Target Completion**: $(date -d "+1 month" +%Y-%m-%d)

## Phase 1: Foundation (Week 1)
- [ ] Read official documentation
- [ ] Complete "Hello World" tutorial
- [ ] Understand core concepts
- [ ] Set up development environment

## Phase 2: Practice (Week 2-3)
- [ ] Build small project
- [ ] Follow advanced tutorials
- [ ] Read best practices
- [ ] Join community forums

## Phase 3: Mastery (Week 4)
- [ ] Build something useful
- [ ] Optimize performance
- [ ] Contribute to open source
- [ ] Teach someone else

## Resources
- Official docs: [link]
- Tutorials: [links]
- Community: [links]
- Books/Courses: [links]

## Progress Notes
(Weekly updates go here)
EOF

echo "Learning path created for $TECH"
echo "Save progress with: emdx save --tags learning,$TECH,progress"
```

## 💼 Consulting & Client Work

### Client Project Setup

```bash
#!/bin/bash
# client-project-setup.sh
# Initialize knowledge base for new client project

CLIENT="$1"
PROJECT="$2"

if [ -z "$CLIENT" ] || [ -z "$PROJECT" ]; then
    echo "Usage: $0 <client-name> <project-name>"
    exit 1
fi

PROJECT_ID="${CLIENT}-${PROJECT}"

# Project kickoff document
cat << EOF | emdx save --title "Project Kickoff: $PROJECT_ID" --tags "project,kickoff,$PROJECT_ID" --auto-tag
# Project Kickoff: $PROJECT_ID

**Client**: $CLIENT
**Project**: $PROJECT
**Start Date**: $(date +%Y-%m-%d)
**Status**: Active

## Objectives
- 

## Scope
### In Scope
- 

### Out of Scope
- 

## Timeline
- Phase 1: 
- Phase 2: 
- Go-live: 

## Key Contacts
- Client PM: 
- Technical Lead: 
- Business Owner: 

## Success Criteria
1. 
2. 
3. 

## Risks
- 

## Next Steps
- [ ] Requirements gathering
- [ ] Technical architecture
- [ ] Project plan
EOF

echo "Client project $PROJECT_ID initialized"
echo "Track with: emdx find --tags $PROJECT_ID"
```

## 🔬 Academic Research

### Literature Review Workflow

```bash
#!/bin/bash
# literature-review.sh
# Systematic literature review using EMDX

TOPIC="$1"
if [ -z "$TOPIC" ]; then
    echo "Usage: $0 <research-topic>"
    exit 1
fi

# Create research protocol
cat << EOF | emdx save --title "Literature Review Protocol: $TOPIC" --tags "research,protocol,active" --auto-tag
# Literature Review Protocol: $TOPIC

**Started**: $(date +%Y-%m-%d)
**Researcher**: $(whoami)

## Research Question
[Define your research question]

## Search Strategy
### Databases
- [ ] Google Scholar
- [ ] PubMed
- [ ] IEEE Xplore
- [ ] ACM Digital Library
- [ ] arXiv

### Keywords
- Primary: "$TOPIC"
- Secondary: [related terms]
- Boolean operators: [search strings]

### Inclusion Criteria
- Publication date: [range]
- Language: English
- Peer-reviewed: Yes
- Full text available: Yes

### Exclusion Criteria
- [Define exclusion criteria]

## Screening Process
1. Title screening
2. Abstract screening
3. Full-text review
4. Quality assessment

## Data Extraction
- Citation details
- Methodology
- Key findings
- Limitations
- Relevance score (1-5)
EOF

echo "Literature review protocol created for: $TOPIC"
echo "Track progress with: emdx find --tags literature-review,$TOPIC"
```

## 🏢 Enterprise Integration

### Confluence/Wiki Migration

```bash
#!/bin/bash
# wiki-migration.sh
# Migrate from corporate wiki to EMDX

SOURCE_WIKI="$1"  # e.g., "confluence", "notion", "sharepoint"
SPACE="$2"        # Wiki space/area name

if [ -z "$SOURCE_WIKI" ] || [ -z "$SPACE" ]; then
    echo "Usage: $0 <source-wiki> <space-name>"
    exit 1
fi

# Create migration plan
cat << EOF | emdx save --title "Wiki Migration: $SPACE from $SOURCE_WIKI" --tags "migration,wiki,project" --auto-tag
# Wiki Migration Plan: $SPACE

**Source**: $SOURCE_WIKI
**Target**: EMDX
**Started**: $(date +%Y-%m-%d)
**Status**: Planning

## Migration Strategy
1. **Inventory**: Catalog all content
2. **Prioritize**: Identify high-value content
3. **Transform**: Convert to markdown
4. **Import**: Bulk import to EMDX
5. **Organize**: Apply tags and structure
6. **Validate**: Verify migration success

## Timeline
- Week 1: Inventory and planning
- Week 2: Export and conversion
- Week 3: Import and organization
- Week 4: Validation and cleanup
EOF

echo "Migration plan created for $SPACE"
echo "Track with: emdx find --tags migration,$SPACE"
```

## 🌟 Pro Tips for Workflow Success

### Start Small, Think Big
```bash
# Begin with simple patterns
echo "Today I learned about async/await" | emdx save --title "TIL: Async" --auto-tag

# Gradually build complexity
emdx find --tags "learning" --created-after "this week" --format json | \
  jq -r '.[] | "- \(.title)"' | \
  emdx save --title "This Week's Learning Summary" --auto-tag
```

### Make It Automatic
```bash
# Add to your .bashrc/.zshrc
alias til='echo "$1" | emdx save --title "TIL: $(date +%Y-%m-%d)" --auto-tag'
alias emdx-health='emdx analyze --health'
alias emdx-clean='emdx maintain --auto --execute'

# Use cron for regular maintenance
echo "0 6 * * * emdx maintain --auto --execute" | crontab -
```

### Measure What Matters
```bash
# Track your knowledge growth
emdx analyze --json | jq '.statistics.total_documents' >> ~/knowledge-growth.log

# Monitor health over time
emdx analyze --health --json | jq '{date: now, score: .overall_score}' >> ~/health-history.jsonl
```

### Share and Collaborate
```bash
# Export workflows for your team
emdx find --tags "workflow,automation" --format json > team-workflows.json

# Create team knowledge templates
emdx save template.md --title "Team Meeting Template" --tags "template,team"
```

Remember: The best workflow is the one you'll actually use. Start simple and evolve!