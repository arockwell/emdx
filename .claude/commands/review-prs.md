# Review Open PRs

Review open pull requests and provide merge/close/fix recommendations.

## Scope
$ARGUMENTS — Optional: repo name or path to limit scope (e.g., "emdx", "~/dev/emdx", "semantic_notes"). If empty, scans all repos in ~/dev/ with open PRs.

## Steps

1. **Discovery**:
   - If $ARGUMENTS is provided: resolve it to a repo path (check ~/dev/$ARGUMENTS first, then treat as absolute path). Only review that single repo.
   - If $ARGUMENTS is empty: find all git repos in ~/dev/ with open PRs using `gh pr list --state open`
2. **Fetch details**: For each PR, get title, author, CI status, mergeability, additions/deletions, age, labels via `gh pr list --state open --json number,title,author,createdAt,additions,deletions,reviewDecision,mergeable,statusCheckRollup,headRefName,labels,isDraft`
3. **Analyze each PR**:
   - Check CI status (all green? which checks fail? are failures pre-existing on main?)
   - Check mergeability (MERGEABLE, CONFLICTING, UNKNOWN)
   - Identify Dependabot PRs vs human PRs
   - Identify duplicate/competing PRs (same feature, different branches)
   - For duplicates: read PR descriptions and diffs to compare approaches, test counts, CI status
4. **For competing PRs**: Use `gh pr view <N> --json body,title,commits,files` and `gh pr diff <N>` to compare
5. **Check for shared file conflicts**: If two PRs create the same new file, flag the merge order dependency

## Output

Per-repo table with columns: PR#, Title, Author, CI, Mergeable, Verdict (Merge/Close/Fix first/Wait)

Then a summary table: Repo | Total | Merge | Close | Fix first | Wait

For competing PRs, explain which to pick and why. Suggest a merge order that minimizes conflicts.

## Important
- Dependabot PRs with only `scan_ruby` failing but tests passing are generally safe to merge — the scan failure is likely pre-existing on main
- When ALL checks fail (including tests), don't merge — the test suite itself is likely broken on that repo
- Flag merge order dependencies when PRs touch the same files
- Old PRs (months) with merge conflicts should usually be closed rather than resolved
- When PRs are created by sub-agents, there are often duplicates (v1/v2) — always compare before recommending
