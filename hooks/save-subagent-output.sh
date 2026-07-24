#!/usr/bin/env bash
# SubagentStop hook: auto-save subagent output to the emdx knowledge base.
#
# Receives JSON on stdin with keys:
#   agent_type, last_assistant_message, stop_hook_active,
#   agent_id, session_id, agent_transcript_path
#
# Saves substantive output (200+ chars) with agent-type tags.
# If EMDX_TASK_ID is set, links the saved doc to that task.
set -uo pipefail
# Note: -e intentionally omitted — the Python heredoc's exit code must not
# cause bash to report a non-zero exit, which Claude Code interprets as an
# agent error. We handle errors explicitly and always exit 0.

# Read stdin JSON to a temp file (env vars hit size limits on large payloads)
TMPFILE=$(mktemp /tmp/emdx-hook-input.XXXXXX)
cat > "$TMPFILE"

python3 - "$TMPFILE" << 'PYEOF' || true
import json
import os
import re
import subprocess
import sys

tmpfile = sys.argv[1]

try:
    with open(tmpfile) as f:
        data = json.load(f)
except Exception:
    sys.exit(0)
finally:
    os.unlink(tmpfile)

agent_type = data.get("agent_type", "unknown")

# Guard: re-entry protection
if data.get("stop_hook_active", False):
    sys.exit(0)

# Extract message
msg = data.get("last_assistant_message", "")
if not msg or len(msg) < 200:
    sys.exit(0)

# Agent types whose final output is worth a knowledge-base record.
# DRIFT CONTRACT: this set must match the SubagentStop matcher in
# hooks.json — update both together (the /new-agent skill's checklist).
#   - built-ins:  explore, plan, general-purpose
#   - role fleet: worker, auditor, reviewer, scout, verifier,
#                 epic-runner, recorder, pr-reviewer,
#                 sentry-issue-investigator
#   - monitor is excluded on purpose: watch/poll output is transient
allowed_types = {
    "explore", "plan", "general-purpose",
    "worker", "auditor", "reviewer", "scout", "verifier",
    "epic-runner", "recorder", "pr-reviewer", "sentry-issue-investigator",
}
if agent_type.lower() not in allowed_types:
    sys.exit(0)

# Backstop, not duplicator: role-fleet agents are instructed to save
# their own findings and cite the doc id in their final report. A message
# that already cites a doc id has its content in emdx — skip.
if re.search(r"(?:emdx|doc)\s*#\d{3,}", msg):
    sys.exit(0)

# Check emdx is available
if subprocess.run(["which", "emdx"], capture_output=True).returncode != 0:
    sys.exit(0)

# --- Title derivation ---
# Prefer first markdown heading, fall back to first non-empty line
title = ""
first_line = ""
for line in msg.splitlines():
    stripped = line.strip()
    if not first_line and stripped:
        first_line = stripped.lstrip("#").strip()[:80]
    if stripped.startswith("#"):
        title = stripped.lstrip("#").strip()[:80]
        break
if not title:
    title = first_line or f"{agent_type} agent output"

# --- Tags ---
tags = ["subagent", f"agent:{agent_type.lower()}"]

# Auto-detect PR URLs in output
if re.search(r"https://github\.com/[^/]+/[^/]+/pull/\d+", msg):
    tags.append("has-pr")

# --- Extract ticket IDs from title + first 2000 chars of body ---
TICKET_RE = re.compile(r"\b(KEEP|COL|HDC|DASH|DEVOPS|PZR|COLO)-(\d+)\b", re.IGNORECASE)
search_text = title + " " + msg[:2000]
ticket_matches = set()
for prefix, num in TICKET_RE.findall(search_text):
    ticket_matches.add(f"{prefix.lower()}-{num}")
for ticket in sorted(ticket_matches):
    tags.append(ticket)

# --- Extract ticket from git branch if nothing found in text ---
if not ticket_matches:
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        branch_match = TICKET_RE.search(branch)
        if branch_match:
            tags.append(f"{branch_match.group(1).lower()}-{branch_match.group(2)}")
    except Exception:
        pass

# --- Extract PR numbers from text ---
pr_nums = set(re.findall(r"(?:PR\s*#?|pull/)(\d{3,})", msg[:2000], re.IGNORECASE))
for pr in sorted(pr_nums):
    tags.append(f"pr-{pr}")

# --- Infer content type from title keywords ---
title_lower = title.lower()
CONTENT_TYPE_MAP = [
    (r"\b(?:investigat|root.cause|deep.dive)\b", "investigation"),
    (r"\b(?:gameplan|implementation.plan|plan)\b", "gameplan"),
    (r"\b(?:saga|narrative|write.?up)\b", "saga"),
    (r"\b(?:review|code.review|pr.review)\b", "pr-review"),
    (r"\b(?:decision|chose|decided|going.with)\b", "decision"),
    (r"\b(?:lit(?:erate)?.review|walkthrough)\b", "literate-review"),
    (r"\b(?:exploration|research|summary.of.findings)\b", "analysis"),
    (r"\b(?:coding.standard|convention|pattern)\b", "coding-standards"),
]
for pattern, content_tag in CONTENT_TYPE_MAP:
    if re.search(pattern, title_lower):
        tags.append(content_tag)
        break

tag_str = ",".join(tags)

# --- Save to KB ---
cmd = ["emdx", "save", "--title", title, "--tags", tag_str]

# Link to task if EMDX_TASK_ID is set
task_id = os.environ.get("EMDX_TASK_ID", "")
if task_id:
    cmd.extend(["--task", task_id])

try:
    subprocess.run(
        cmd,
        input=msg,
        text=True,
        capture_output=True,
        timeout=20,
    )
except Exception:
    pass

sys.exit(0)
PYEOF

# Always exit clean — a hook failure should never mark an agent as errored
exit 0
