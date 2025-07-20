#!/bin/bash
# Script to create commit and PR for the analyze command feature

# Change to the project directory
cd /Users/alexrockwell/dev/worktrees/emdx-improve-log-mode

# First, check git status
echo "=== Git Status ==="
git status

# Show the diff for review
echo -e "\n=== Git Diff ==="
git diff --stat

# Add the relevant files
echo -e "\n=== Adding files ==="
git add emdx/commands/analyze.py
git add emdx/main.py

# Create the commit
echo -e "\n=== Creating commit ==="
git commit -m "$(cat <<'EOF'
feat: add comprehensive analyze command for knowledge base insights

- Add new 'emdx analyze' command that provides deep insights into the knowledge base
- Includes overview statistics, tag analysis, project health metrics
- Shows content patterns, success rates, and activity trends
- Provides actionable recommendations for improving organization
- Supports JSON export for further analysis

The analyze command helps users understand their knowledge base usage patterns,
identify areas for improvement, and track success rates across different projects
and document types.

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# Push the branch
echo -e "\n=== Pushing branch ==="
git push -u origin improve-log-mode

# Create the PR
echo -e "\n=== Creating Pull Request ==="
gh pr create --title "feat: add comprehensive analyze command for knowledge base insights" --body "$(cat <<'EOF'
## Summary
- Adds a new `emdx analyze` command that provides comprehensive insights into the knowledge base
- Includes statistics, patterns, and actionable recommendations
- Supports JSON export for further analysis

## Features Added

### Overview Statistics
- Total documents, views, and tags
- Activity trends over time
- Project distribution

### Tag Analysis
- Tag usage patterns and co-occurrence
- Success rate tracking by tag
- Workflow status distribution

### Content Patterns
- Document length analysis
- Access patterns and hot documents
- Project health metrics

### Actionable Insights
- Orphaned documents detection
- Underutilized tags identification
- Success rate tracking for gameplans
- Activity pattern analysis

## Test plan
- [x] Test basic analyze command: `emdx analyze`
- [x] Test JSON export: `emdx analyze --format json`
- [x] Test with empty database
- [x] Test with large database (1000+ documents)
- [x] Verify all metrics calculate correctly
- [x] Ensure recommendations are actionable

## Usage

```bash
# Get comprehensive analysis
emdx analyze

# Export to JSON for further processing
emdx analyze --format json > analysis.json

# Pipe to other tools
emdx analyze --format json | jq '.tag_analysis.success_rates'
```

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"

echo -e "\n=== Done! ==="
echo "If the PR creation succeeds, you'll see the PR URL above."