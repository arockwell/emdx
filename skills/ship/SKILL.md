---
name: ship
description: Commit all staged and unstaged changes and push to the remote branch.
disable-model-invocation: true
---

# Ship It

Commit and push the current changes.

## Steps

1. Run `git status` to see what's changed (never use `-uall`)
2. Run `git diff` to review staged and unstaged changes
3. Run `git log --oneline -5` to match the repo's commit message style
4. Stage all relevant changed files by name (don't use `git add -A` or `git add .`)
5. Write a concise commit message summarizing the changes — focus on the "why"
6. Commit using a HEREDOC for the message, with `Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>`
7. Push to the current remote branch
8. Report the result: commit hash, branch, and remote URL

If $ARGUMENTS is provided, use it as guidance for the commit message.

## Rules

- Never amend existing commits — always create new ones
- Never force push
- Never skip pre-commit hooks
- Don't commit files that look like secrets (.env, credentials, tokens)
- If there are no changes, say so and stop
