Run an environment diagnostic to fingerprint the current working directory and optionally compare it with another worktree.

## Instructions

1. Run `bash scripts/env-diag.sh` in the **current working directory**. If the script doesn't exist at that path, run it from the git repo root (`git rev-parse --show-toplevel`)/scripts/env-diag.sh. If still not found, inform the user the script is missing.

2. If `$ARGUMENTS` is provided and is a path to another directory, also run `bash scripts/env-diag.sh` from that directory (using `cd` to change into it first) and compare the two outputs.

3. When comparing two environments, highlight these discrepancies clearly:
   - **Different branch** — likely running in the wrong worktree
   - **Different Python version** — could cause subtle behavior differences
   - **Different venv path** — packages may differ
   - **Different source fingerprints** — code is not identical, changes haven't been synced
   - **Different emdx binary** — running a different installation entirely
   - **Different DB path** — data won't match between environments
   - **Stale .pyc files** — Python may be running cached bytecode from old source

4. Based on what differs, suggest the most likely root cause:
   - If branches differ: "You're in a different worktree. The code you're editing isn't what's running."
   - If source hashes differ but branch is same: "Files have diverged. Check for uncommitted changes or stale worktrees."
   - If venv differs: "Different virtual environments. Package versions may not match."
   - If .pyc files are stale: "Stale bytecode cache. Run `find . -name '*.pyc' -delete` to force recompilation."
   - If DB path differs: "Different databases. Data changes in one won't appear in the other."

5. Present the output in a clean, readable format. For single-environment mode, just show the results with any warnings. For comparison mode, show a side-by-side summary of differences.
