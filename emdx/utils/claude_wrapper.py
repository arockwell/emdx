#!/usr/bin/env python3
"""
Wrapper script for Claude executions that tracks completion status.

This script runs a Claude command and updates the database with the final status,
solving the issue where background executions remain 'running' forever.
"""
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from emdx.models.executions import update_execution_status, update_execution_heartbeat
from emdx.utils.structured_logger import StructuredLogger, ProcessType, LogLevel




def heartbeat_thread(exec_id: int, stop_event: threading.Event) -> None:
    """Background thread that updates heartbeat every 30 seconds."""
    while not stop_event.is_set():
        try:
            update_execution_heartbeat(exec_id)
        except Exception:
            # Silently ignore heartbeat failures
            pass
        
        # Wait 30 seconds or until stop event
        stop_event.wait(30)


def main():
    """Main wrapper function."""
    if len(sys.argv) < 4:
        print("Usage: claude_wrapper.py <exec_id> <log_file> <command...>", file=sys.stderr)
        sys.exit(1)

    exec_id = int(sys.argv[1])  # Convert to int - this is the database ID
    log_file = Path(sys.argv[2])
    cmd = sys.argv[3:]

    # Initialize structured logger for wrapper process
    logger = StructuredLogger(log_file, ProcessType.WRAPPER, os.getpid())
    
    # Log execution start
    logger.log_execution_start(exec_id, f"Execution #{exec_id}", os.getcwd())
    logger.log_process_lifecycle("start", {"exec_id": exec_id, "command": cmd})

    exit_code = 1  # Default to failure
    status = "failed"
    lines_processed = 0  # Track lines to detect empty runs
    
    # Start heartbeat thread
    stop_heartbeat = threading.Event()
    heartbeat = threading.Thread(target=heartbeat_thread, args=(exec_id, stop_heartbeat))
    heartbeat.daemon = True
    heartbeat.start()

    # Check if claude command exists
    import shutil
    if not shutil.which(cmd[0]):
        logger.error(f"Command '{cmd[0]}' not found in PATH", {
            "command": cmd[0],
            "path": os.environ.get('PATH', 'not set')
        })
        update_execution_status(exec_id, "failed", 127)
        sys.exit(127)

    try:
        # Run the actual Claude command
        logger.info("Starting Claude process", {
            "working_directory": os.getcwd(),
            "pythonunbuffered": os.environ.get('PYTHONUNBUFFERED', 'not set')
        })

        # Execute the command and format output before writing to log
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # Don't set cwd - inherit from parent process which already set it
            text=True,
            bufsize=1  # Line buffered
        )

        start_time = time.time()

        logger.info(f"Claude process started with PID: {process.pid}", {
            "claude_pid": process.pid
        })

        # Stream and format output
        lines_processed = 0
        for line in process.stdout:
            lines_processed += 1
            line = line.strip()
            if not line:
                continue
            
            try:
                # Try to parse as JSON from Claude
                data = json.loads(line)
                logger.log_claude_output(data)
            except json.JSONDecodeError:
                # Not JSON - log as plain text from Claude
                if line and not line.startswith("{"):
                    logger.info(f"Claude output: {line}", {
                        "source": "claude_stdout",
                        "raw": True
                    })

        # Wait for process to complete
        process.wait()
        result = process

        duration = time.time() - start_time

        exit_code = result.returncode
        status = "completed" if exit_code == 0 else "failed"

        logger.log_execution_complete(exec_id, exit_code, duration)
        logger.info(f"Lines processed: {lines_processed}", {
            "lines_processed": lines_processed
        })

    except FileNotFoundError as e:
        logger.error(f"Command not found: {cmd[0]}", {
            "error": str(e),
            "hint": "Make sure 'claude' is installed and in your PATH"
        })
        status = "failed"
        exit_code = 127  # Standard command not found exit code

    except subprocess.TimeoutExpired:
        logger.error("Process timed out")
        status = "failed"
        exit_code = 124  # Standard timeout exit code

    except KeyboardInterrupt:
        logger.warning("Process interrupted by user")
        status = "failed"
        exit_code = 130  # Standard SIGINT exit code

    except Exception as e:
        logger.error(f"Wrapper error: {str(e)}", {
            "traceback": traceback.format_exc()
        })
        status = "failed"
        exit_code = 1

    finally:
        # Stop heartbeat thread
        stop_heartbeat.set()
        heartbeat.join(timeout=1)
        
        # Always try to update the database
        try:
            # Always update status - the lock file should prevent true duplicates
            update_execution_status(exec_id, status, exit_code)
            logger.info("Database updated successfully", {
                "status": status,
                "exit_code": exit_code
            })
        except Exception as e:
            logger.error(f"Failed to update database: {str(e)}")
            # Don't exit with error if only DB update failed
            # The main process ran, which is what matters


    # Exit with the same code as the subprocess
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
