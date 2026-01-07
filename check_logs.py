#!/usr/bin/env python3
"""Simple script to check and tail key event logs"""

import subprocess
from pathlib import Path


def check_logs():
    log_dir = Path.home() / ".config" / "emdx"

    key_log = log_dir / "key_events.log"
    debug_log = log_dir / "tui_debug.log"

    print("🔍 EMDX Log Checker")
    print("=" * 50)

    if key_log.exists():
        print(f"\n📋 Last 20 key events from {key_log}:")
        print("-" * 40)
        subprocess.run(["tail", "-20", str(key_log)], check=False)
    else:
        print(f"\n❌ Key events log not found at {key_log}")

    if debug_log.exists():
        print(f"\n🐛 Last 10 debug entries from {debug_log}:")
        print("-" * 40)
        # Use subprocess pipeline for safety
        tail_process = subprocess.Popen(["tail", "-10", str(debug_log)], stdout=subprocess.PIPE)
        subprocess.run(["grep", "-E", "CRASH|ERROR|Key event"], stdin=tail_process.stdout, check=False)
        tail_process.stdout.close()
        tail_process.wait()
    else:
        print(f"\n❌ Debug log not found at {debug_log}")

    print(f"\n💡 To monitor live: tail -f '{key_log}'")
    print(f"💡 Clear logs: rm '{key_log}' '{debug_log}'")


if __name__ == "__main__":
    check_logs()
