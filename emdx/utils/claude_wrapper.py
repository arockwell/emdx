#!/usr/bin/env python3
"""
Wrapper script for Claude executions that tracks completion status.

This script runs a Claude command and updates the database with the final status,
solving the issue where background executions remain 'running' forever.
"""
import os
import subprocess
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from emdx.models.executions import update_execution_status


def format_timestamp() -> str:
    """Get a formatted timestamp for logging."""
    return datetime.now().strftime("[%H:%M:%S]")


def log_to_file(log_path: Path, message: str) -> None:
    """Append a message to the log file."""
    try:
        with open(log_path, 'a') as f:
            f.write(f"{format_timestamp()} {message}\n")
    except Exception as e:
        # If we can't write to log, at least print to stderr
        print(f"Failed to write to log: {e}", file=sys.stderr)


def main():
    """Main wrapper function."""
    if len(sys.argv) < 4:
        print("Usage: claude_wrapper.py <exec_id> <log_file> <command...>", file=sys.stderr)
        sys.exit(1)

    exec_id = int(sys.argv[1])  # Convert to int - this is the database ID
    log_file = Path(sys.argv[2])
    cmd = sys.argv[3:]

    # TEMPORARY: Disable lock mechanism to test if it's causing issues
    log_to_file(log_file, "🔍 DEBUG: LOCK MECHANISM DISABLED FOR TESTING")
    log_to_file(log_file, "🔍 DEBUG: This should allow multiple executions to run simultaneously")

    # Log wrapper start
    log_to_file(log_file, "🔄 Wrapper script started")
    log_to_file(log_file, f"📋 Full args: {sys.argv}")
    log_to_file(log_file, f"📋 Exec ID: {exec_id}")
    log_to_file(log_file, f"📋 Command: {' '.join(cmd)}")

    exit_code = 1  # Default to failure
    status = "failed"
    lines_processed = 0  # Track lines to detect empty runs

    # Check if claude command exists
    import shutil
    if not shutil.which(cmd[0]):
        log_to_file(log_file, f"❌ Command '{cmd[0]}' not found in PATH")
        log_to_file(log_file, f"💡 PATH: {os.environ.get('PATH', 'not set')}")
        update_execution_status(exec_id, "failed", 127)
        sys.exit(127)

    try:
        # Run the actual Claude command
        log_to_file(log_file, "🚀 Starting Claude process...")
        log_to_file(log_file, f"🔍 Working directory: {os.getcwd()}")
        log_to_file(log_file, f"🔍 Environment PYTHONUNBUFFERED: {os.environ.get('PYTHONUNBUFFERED', 'not set')}")

        # Execute the command and format output before writing to log
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=os.getcwd(),  # Preserve working directory
            text=True,
            bufsize=1  # Line buffered
        )

        # Import formatting function
        import time

        from emdx.commands.claude_execute import format_claude_output, parse_log_timestamp
        start_time = time.time()

        log_to_file(log_file, f"🔍 Process started with PID: {process.pid}")

        # Stream and format output
        lines_processed = 0
        last_timestamp = None
        with open(log_file, 'a') as log_f:
            for line in process.stdout:
                lines_processed += 1
                # Parse timestamp from log line if available
                parsed_timestamp = parse_log_timestamp(line)
                if parsed_timestamp:
                    last_timestamp = parsed_timestamp
                # Use parsed timestamp or last known timestamp, fallback to current time
                timestamp_to_use = parsed_timestamp or last_timestamp or time.time()
                formatted = format_claude_output(line, timestamp_to_use)
                if formatted:
                    log_f.write(formatted + '\n')
                    log_f.flush()  # Ensure real-time updates

        # Wait for process to complete
        process.wait()
        result = process

        duration = time.time() - start_time

        exit_code = result.returncode
        status = "completed" if exit_code == 0 else "failed"

        log_to_file(log_file, f"✅ Claude process finished with exit code: {exit_code}")
        log_to_file(log_file, f"📊 Duration: {duration:.2f}s, Lines processed: {lines_processed}")

    except FileNotFoundError as e:
        log_to_file(log_file, f"❌ Command not found: {cmd[0]}")
        log_to_file(log_file, f"❌ Full error: {str(e)}")
        log_to_file(log_file, "💡 Make sure 'claude' is installed and in your PATH")
        status = "failed"
        exit_code = 127  # Standard command not found exit code

    except subprocess.TimeoutExpired:
        log_to_file(log_file, "⏱️ Process timed out")
        status = "failed"
        exit_code = 124  # Standard timeout exit code

    except KeyboardInterrupt:
        log_to_file(log_file, "⚠️ Process interrupted by user")
        status = "failed"
        exit_code = 130  # Standard SIGINT exit code

    except Exception as e:
        log_to_file(log_file, f"❌ Wrapper error: {str(e)}")
        log_to_file(log_file, f"Traceback:\n{traceback.format_exc()}")
        status = "failed"
        exit_code = 1

    finally:
        # Always try to update the database
        try:
            # Always update status - the lock file should prevent true duplicates
            log_to_file(log_file, f"📊 Updating execution status to: {status}")
            log_to_file(log_file, f"📊 Lines processed: {lines_processed}, Exit code: {exit_code}")
            log_to_file(log_file, f"🔍 DEBUG: About to call update_execution_status({exec_id}, {status}, {exit_code})")

            update_execution_status(exec_id, status, exit_code)

            log_to_file(log_file, "✅ Database updated successfully")
            log_to_file(log_file, f"🔍 DEBUG: Execution {exec_id} is now marked as {status}")
        except Exception as e:
            log_to_file(log_file, f"❌ Failed to update database: {str(e)}")
            # Don't exit with error if only DB update failed
            # The main process ran, which is what matters

    # TEMPORARY: No lock file cleanup since lock mechanism is disabled
    log_to_file(log_file, f"🔍 DEBUG: Wrapper finished for execution {exec_id}")

    # Exit with the same code as the subprocess
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
