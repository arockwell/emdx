#!/usr/bin/env python3
"""
EMDX Swarm Agent - runs inside a k3d pod.

This script:
1. Reads task from environment
2. Changes to the worktree directory
3. Runs Claude Code with the task
4. Outputs results (captured by orchestrator via kubectl logs)
5. Optionally saves to EMDX via HTTP

The orchestrator creates the pod, mounts the worktree, and collects
output from kubectl logs after the pod completes.
"""

import json
import os
import subprocess
import sys
from datetime import datetime

# Configuration from environment
TASK = os.environ.get("TASK", "")
WORKTREE = os.environ.get("WORKTREE", "/workspaces/default")
EMDX_HOST = os.environ.get("EMDX_HOST", "host.k3d.internal")
EMDX_PORT = os.environ.get("EMDX_PORT", "8765")
EMDX_TAGS = os.environ.get("EMDX_TAGS", "swarm-output,auto")
TIMEOUT = int(os.environ.get("TIMEOUT", "600"))


def log(message: str):
    """Log with timestamp."""
    ts = datetime.now().isoformat()
    print(f"[{ts}] {message}", flush=True)


def run_claude(task: str, cwd: str) -> tuple[int, str, str]:
    """
    Run Claude Code with the given task.

    Returns (exit_code, stdout, stderr)
    """
    log(f"Running Claude with task: {task[:100]}...")

    try:
        result = subprocess.run(
            [
                "claude",
                "-p", task,
                "--output-format", "text",
                "--dangerously-skip-permissions",  # We're in an isolated container
            ],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=TIMEOUT,
            env={
                **os.environ,
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            }
        )
        return result.returncode, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        return 1, "", f"Task timed out after {TIMEOUT}s"
    except Exception as e:
        return 1, "", str(e)


def save_to_emdx(title: str, content: str, tags: list[str]) -> bool:
    """
    Save result to EMDX via HTTP API.

    Note: This requires EMDX to be running an HTTP server.
    If not available, the orchestrator will save via kubectl logs.
    """
    try:
        import requests

        url = f"http://{EMDX_HOST}:{EMDX_PORT}/save"
        response = requests.post(url, json={
            "title": title,
            "content": content,
            "tags": tags
        }, timeout=10)

        if response.ok:
            log(f"Saved to EMDX: {response.json()}")
            return True
        else:
            log(f"Failed to save to EMDX: {response.status_code}")
            return False

    except Exception as e:
        log(f"Could not reach EMDX server: {e}")
        return False


def main():
    """Main agent execution."""
    log("=" * 60)
    log("EMDX Swarm Agent Starting")
    log("=" * 60)

    if not TASK:
        log("ERROR: No TASK environment variable set")
        sys.exit(1)

    log(f"Task: {TASK}")
    log(f"Worktree: {WORKTREE}")
    log(f"EMDX Host: {EMDX_HOST}:{EMDX_PORT}")

    # Change to worktree
    if os.path.exists(WORKTREE):
        os.chdir(WORKTREE)
        log(f"Changed to worktree: {os.getcwd()}")
    else:
        log(f"WARNING: Worktree {WORKTREE} does not exist, using /workspaces")
        os.chdir("/workspaces")

    # Show git status
    git_result = subprocess.run(
        ["git", "status", "--short"],
        capture_output=True, text=True
    )
    if git_result.returncode == 0:
        log(f"Git status:\n{git_result.stdout}")

    # Run Claude
    log("-" * 60)
    exit_code, stdout, stderr = run_claude(TASK, os.getcwd())
    log("-" * 60)

    # Output results (this is what the orchestrator captures)
    print("\n" + "=" * 60)
    print("AGENT OUTPUT START")
    print("=" * 60)
    print(stdout)
    print("=" * 60)
    print("AGENT OUTPUT END")
    print("=" * 60 + "\n")

    if stderr:
        print("\n" + "=" * 60)
        print("AGENT STDERR")
        print("=" * 60)
        print(stderr)
        print("=" * 60 + "\n")

    # Try to save to EMDX (optional, orchestrator also saves)
    if stdout and EMDX_HOST:
        title = f"Swarm: {TASK[:50]}..."
        tags = EMDX_TAGS.split(",")
        save_to_emdx(title, stdout, tags)

    # Report completion
    log(f"Agent completed with exit code: {exit_code}")

    # Check for any git changes
    git_diff = subprocess.run(
        ["git", "diff", "--stat"],
        capture_output=True, text=True
    )
    if git_diff.stdout.strip():
        log(f"Git changes made:\n{git_diff.stdout}")

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
