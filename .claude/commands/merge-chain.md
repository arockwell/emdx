# Merge Chain

Merge a sequence of dependent PRs in order, ensuring CI passes between each.

## Usage

`/merge-chain` with a list of PR numbers (e.g., `#638 #637`)

## Steps

1. For each PR in the chain (in order):
   a. Check CI status with `gh pr checks <number>`
   b. If CI is not yet complete, wait and re-check (up to 5 minutes)
   c. If CI passes, merge with `gh pr merge <number> --squash --auto`
   d. If CI fails, stop and report which PR failed and why

2. After each merge (except the last):
   a. Rebase the next PR's branch onto main: `git fetch origin main && git rebase origin/main`
   b. Force push the rebased branch: `git push --force-with-lease`
   c. Wait for CI to start on the rebased branch

3. Report final status: which PRs merged, which (if any) failed

## Output

Summary table of each PR: number, title, CI status, merge result.
