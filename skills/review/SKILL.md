---
name: review
description: Run quality checks on the emdx knowledge base — find stale docs, redundancies, contradictions, knowledge gaps, and code drift. Produces a prioritized action plan with specific fix commands.
---

# Knowledge Base Quality Review

Audit the emdx knowledge base for quality issues and produce an actionable improvement plan.

If the user provided a focus area, scope the review accordingly: $ARGUMENTS

## Steps

### 1. Run quality checks

Execute all maintenance diagnostics. Run these commands and capture their output:

```bash
emdx maintain freshness --stale
```

```bash
emdx maintain compact --dry-run
```

```bash
emdx maintain contradictions
```

```bash
emdx maintain drift
```

```bash
emdx maintain code-drift
```

```bash
emdx maintain gaps
```

```bash
emdx stale --tier critical
```

### 2. Review recent additions

Check recent documents for quality issues (unclear titles, missing tags, orphaned docs):

```bash
emdx find --recent 20
```

For any documents that look problematic, inspect them:

```bash
emdx view <id>
```

Look for:
- Missing or unhelpful titles
- Missing tags (especially `active`/`done` status tags)
- Very short or empty content
- Duplicate content that the compact check may have missed
- Documents that should be linked to tasks or epics but aren't

### 3. Check KB vitals

Get an overview of the knowledge base health:

```bash
emdx status --vitals
```

### 4. Synthesize findings into a report

Produce a structured report with these sections:

```
## KB Quality Review

### Critical Issues
Items that need immediate attention (contradictions, severely stale critical docs).
List each with the specific fix command.

### Stale Documents
Docs that haven't been reviewed in a long time and may be outdated.
For each: ID, title, last reviewed date, and recommended action:
- `emdx touch <id>` — if still accurate, mark as reviewed
- `emdx edit <id>` — if needs updates
- `emdx delete <id>` — if obsolete
- `emdx tag add <id> done` — if completed work

### Redundancies
Similar or duplicate documents that could be merged.
For each pair: IDs, titles, similarity score, and the merge command:
- `emdx maintain compact --merge <id1> <id2>`

### Contradictions
Conflicting claims found across documents.
For each: the two documents, the conflicting statements, and which is likely correct.

### Stale Work Items
Tasks or work-tracking docs that have drifted (no updates in 30+ days).
For each: ID, title, age, and recommended action:
- `emdx task done <id>` — if actually complete
- `emdx task active <id>` — if resuming work
- `emdx task delete <id>` — if abandoned

### Code Drift
Code references in documents that no longer match the codebase.
For each: doc ID, the stale reference, and what changed.

### Knowledge Gaps
Topics or areas with thin coverage.
For each: the gap area and a suggested task:
- `emdx task add "Document <topic>" --cat DOCS`

### Recent Document Quality
Issues found in the 20 most recent documents.
For each: ID, issue description, and fix command.

### Recommendations
Top 5 prioritized actions to improve KB quality, ordered by impact.
Each recommendation should be a specific command or small set of commands.
```

### 5. Offer to apply fixes

After presenting the report, ask the user which fixes to apply. Group them by risk level:

| Risk | Actions | Examples |
|------|---------|---------|
| **Safe** | Marking docs as reviewed, adding tags | `emdx touch <id>`, `emdx tag add <id> done` |
| **Moderate** | Merging duplicates, creating tasks | `emdx maintain compact --merge`, `emdx task add` |
| **Destructive** | Deleting documents | `emdx delete <id>` |

Apply only the fixes the user approves. For destructive actions, confirm each one individually.

## Important

- Run ALL diagnostic commands in step 1 before analyzing — some checks are slow but all provide valuable signal
- If $ARGUMENTS specifies a focus area (e.g., "architecture docs"), still run all checks but prioritize findings related to that area
- Be specific in recommendations — every action item should include the exact command to run
- Don't create tasks for trivial issues — focus on high-impact improvements
- If the KB is healthy, say so — don't manufacture problems
