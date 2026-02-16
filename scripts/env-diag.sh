#!/usr/bin/env bash
# env-diag.sh — Fast environment fingerprint for debugging multi-worktree issues
# Run in two terminals side-by-side to instantly spot differences.
# Exit code is always 0 (diagnostic tool, never fails).

set -o pipefail

section() {
    echo ""
    echo "=== $1 ==="
}

# --- Identity ---
section "IDENTITY"
echo "cwd:        $(pwd)"
echo "git branch: $(git branch --show-current 2>/dev/null || echo '(not a git repo)')"
echo "worktree:   $(git rev-parse --show-toplevel 2>/dev/null || echo '(unknown)')"
echo "last commit: $(git log -1 --format='%h %s' 2>/dev/null || echo '(no commits)')"

# --- Python Environment ---
section "PYTHON ENV"
echo "python:     $(python3 --version 2>/dev/null || echo '(not found)')"
venv_path=$(poetry env info --path 2>/dev/null || echo "(no venv)")
echo "venv:       $venv_path"
emdx_bin=$(command -v emdx 2>/dev/null || echo "(not found)")
echo "emdx bin:   $emdx_bin"
if [ -n "$VIRTUAL_ENV" ]; then
    echo "VIRTUAL_ENV: $VIRTUAL_ENV"
fi

# --- Key Packages ---
section "KEY PACKAGES"
for pkg in textual rich click typer; do
    ver=$(pip show "$pkg" 2>/dev/null | grep '^Version:' | cut -d' ' -f2)
    printf "%-12s %s\n" "$pkg:" "${ver:-(not installed)}"
done

# --- Source Fingerprint ---
section "SOURCE FINGERPRINT"
root=$(git rev-parse --show-toplevel 2>/dev/null)
if [ -n "$root" ]; then
    for f in emdx/ui/activity_browser.py emdx/ui/browser_container.py emdx/ui/modals.py emdx/ui/gui.py emdx/database/connection.py; do
        filepath="$root/$f"
        if [ -f "$filepath" ]; then
            hash=$(md5 -q "$filepath" 2>/dev/null || md5sum "$filepath" 2>/dev/null | cut -d' ' -f1)
            printf "%-45s %s\n" "$f:" "$hash"
        else
            printf "%-45s %s\n" "$f:" "(missing)"
        fi
    done
else
    echo "(not in a git repo, skipping)"
fi

# --- Database ---
section "DATABASE"
db_path=$(python3 -c "from emdx.database.connection import get_db_path; print(get_db_path())" 2>/dev/null)
if [ -n "$db_path" ]; then
    echo "db path:    $db_path"
    if [ -f "$db_path" ]; then
        echo "db size:    $(du -h "$db_path" | cut -f1)"
    else
        echo "db size:    (file not found)"
    fi
else
    echo "db path:    (could not determine)"
fi

# --- Recent TUI Logs ---
section "RECENT TUI LOGS (last 5 WARNING/ERROR)"
log_file="$HOME/.config/emdx/tui_debug.log"
if [ -f "$log_file" ]; then
    grep -E '(WARNING|ERROR)' "$log_file" | tail -5
    total=$(grep -cE '(WARNING|ERROR)' "$log_file" 2>/dev/null || echo 0)
    echo "(total warning/error lines: $total)"
else
    echo "(no log file at $log_file)"
fi

# --- Stale .pyc Check ---
section "STALE PYC CHECK"
if [ -n "$root" ]; then
    stale_count=0
    while IFS= read -r pyc_file; do
        # Convert .pyc path to .py source path
        # __pycache__/foo.cpython-311.pyc -> foo.py
        py_dir=$(dirname "$(dirname "$pyc_file")")
        base=$(basename "$pyc_file" | sed 's/\.cpython-[0-9]*\.pyc$/.py/')
        py_file="$py_dir/$base"
        if [ -f "$py_file" ] && [ "$pyc_file" -nt "$py_file" ]; then
            stale_count=$((stale_count + 1))
        fi
    done < <(find "$root" -name "*.pyc" -path "*/__pycache__/*" 2>/dev/null)
    echo "stale .pyc files: $stale_count"
    if [ "$stale_count" -gt 0 ]; then
        echo "(run 'find . -name \"*.pyc\" -delete' to clean)"
    fi
else
    echo "(not in a git repo, skipping)"
fi

echo ""
exit 0
