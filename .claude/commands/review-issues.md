# Review Open Issues

Review open GitHub issues and provide triage/prioritization recommendations.

## Scope
$ARGUMENTS — Optional: repo name or path to limit scope (e.g., "emdx", "~/dev/emdx"). If empty, scans all repos in ~/dev/ with open issues.

## Steps

1. **Discovery**:
   - If $ARGUMENTS is provided: resolve it to a repo path (check ~/dev/$ARGUMENTS first, then treat as absolute path). Only review that single repo.
   - If $ARGUMENTS is empty: find all git repos in ~/dev/ with open issues using `gh issue list --state open`
2. **Fetch details**: For each repo with open issues, get full metadata via `gh issue list --state open --json number,title,author,createdAt,updatedAt,labels,assignees,milestone,comments,body`
3. **Analyze each issue**:
   - Check age (when created, when last updated, any recent activity)
   - Check labels and milestone assignment
   - Check if there's an associated PR (look for linked PRs or branch naming conventions)
   - Check comment count and whether the issue has a clear reproduction or acceptance criteria
   - Identify stale issues (no activity in 30+ days with no assignee or milestone)
   - Identify duplicate issues (same topic, different descriptions)
   - Identify issues that are actually completed but not closed (linked merged PRs, or described work already done)
4. **For issues with linked PRs**: Use `gh pr list --state all --search "fixes #N OR closes #N"` to check if already resolved
5. **Categorize**: Sort issues into buckets — bugs, features, chores, questions/discussions

## Output

Per-repo table with columns: Issue#, Title, Author, Age, Labels, Activity, Verdict (Actionable/Stale/Close/Duplicate/Already Fixed)

Then a summary table: Repo | Total | Actionable | Stale | Close | Already Fixed

## Recommendations

After the tables, provide:
- **Quick wins**: Issues that look easy to close (already fixed, duplicates, stale with no engagement)
- **Priority issues**: Bugs or feature requests with clear requirements and recent activity
- **Triage needed**: Issues missing labels, milestones, or clear acceptance criteria
- **Suggested closes**: Issues that should be closed with a reason (stale, wontfix, duplicate of #N)

## Important
- Stale issues (90+ days, no assignee, no milestone, no recent comments) are candidates for closing
- Issues referencing merged PRs should be verified as fixed and closed
- Bug reports without reproduction steps should be flagged for triage, not auto-closed
- Feature requests with 0 comments and 60+ days old are likely low-priority
- When issues are created by automation (Dependabot, CI), note that separately
- Check if the repo has issue templates — issues not following them may need triage
