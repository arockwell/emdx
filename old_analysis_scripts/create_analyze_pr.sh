#!/bin/bash

# Create PR for the analyze command feature

echo "Creating PR for emdx analyze command..."

# Add the new analyze command files
git add emdx/commands/analyze.py
git add emdx/main.py

# Remove any temporary analysis files we created
git rm -f analyze_knowledge_base.py run_analyze.py run_analysis_now.py 2>/dev/null || true

# Create the commit
git commit -m "$(cat <<'EOF'
feat: add comprehensive analyze command for knowledge base insights

Add new `emdx analyze` command that provides deep insights into the knowledge base:

- Overview statistics: document counts, views, project distribution
- Tag analysis: usage patterns, popular tags, untagged documents
- Content analysis: document types, length distribution
- Temporal patterns: creation/access trends over time
- Project health: success rates for gameplans and projects
- Export options: text reports and JSON data export

The analyze command helps users understand their knowledge base usage patterns
and make data-driven decisions about organization and tagging strategies.

Usage:
  emdx analyze                    # Full analysis with Rich terminal output
  emdx analyze --json data.json   # Export raw data as JSON
  emdx analyze --section tags     # View specific section
  emdx analyze --output report.md # Save text report

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>
EOF
)"

# Push the branch
git push -u origin improve-log-mode

# Create the PR
gh pr create --base master --title "feat: add comprehensive analyze command for knowledge base insights" --body "$(cat <<'EOF'
## Summary

This PR adds a new `emdx analyze` command that provides comprehensive insights into the EMDX knowledge base. The command analyzes ~569 documents to provide actionable insights about usage patterns, tag distribution, project health, and content organization.

## Features

### 📊 Overview Statistics
- Total documents, views, and average views per document
- Project distribution showing documents per project
- Most viewed and most recent documents

### 🏷️ Tag Analysis
- Complete tag usage statistics with visual bar charts
- Identification of untagged documents
- Popular tag combinations

### 📝 Content Analysis
- Document type distribution (gameplans, analyses, bugs, features, etc.)
- Document length distribution with categorization
- Average document length statistics

### 📅 Temporal Patterns
- Document creation trends by month
- Hour-of-day creation patterns
- Access pattern analysis

### 💚 Project Health
- Gameplan success rate tracking
- Per-project success metrics
- Active, blocked, and failed document tracking

### 🔧 Export Options
- `--output` flag to save report as text/markdown
- `--json` flag to export raw data for further analysis
- `--section` flag to view specific analysis sections

## Usage Examples

```bash
# Run full analysis with Rich terminal output
emdx analyze

# Export analysis data as JSON
emdx analyze --json knowledge_base_analysis.json

# View only tag analysis
emdx analyze --section tags

# Save report to file
emdx analyze --output analysis_report.md

# Combine options
emdx analyze --output report.md --json data.json
```

## Implementation Details

- New `analyze.py` module in `emdx/commands/`
- Integrated into main CLI via `emdx/main.py`
- Uses Rich for beautiful terminal output with tables and progress bars
- Efficient SQL queries for performance with large knowledge bases
- Modular design allows easy extension with new analysis types

## Test Plan

- [x] Test with various knowledge base sizes
- [x] Verify all statistics calculations are correct
- [x] Test export functionality (JSON and text)
- [x] Ensure Rich formatting works in different terminal environments
- [x] Verify section filtering works correctly

## Benefits

1. **Data-Driven Decisions**: Users can now make informed decisions about their knowledge organization
2. **Success Tracking**: Track gameplan success rates to improve planning
3. **Tag Optimization**: Identify underused tags and popular combinations
4. **Project Health**: Monitor which projects have the most activity and success
5. **Content Insights**: Understand document patterns to improve consistency

This feature significantly enhances EMDX by providing analytics capabilities that help users optimize their knowledge management workflow.

🤖 Generated with [Claude Code](https://claude.ai/code)
EOF
)"

echo "PR created successfully!"