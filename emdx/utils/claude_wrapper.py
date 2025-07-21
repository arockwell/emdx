#!/usr/bin/env python3
"""
Wrapper script for Claude executions that tracks completion status.

This script runs a Claude command and updates the database with the final status,
solving the issue where background executions remain 'running' forever.
"""
import sys
import subprocess
import os
from pathlib import Path
from datetime import datetime
import traceback

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
    
    exec_id = sys.argv[1]  # Can be numeric or string ID
    log_file = Path(sys.argv[2])
    cmd = sys.argv[3:]
    
    # Log wrapper start
    log_to_file(log_file, "🔄 Wrapper script started")
    log_to_file(log_file, f"📋 Execution ID: {exec_id}")
    log_to_file(log_file, f"📋 Command: {' '.join(cmd)}")
    
    exit_code = 1  # Default to failure
    status = "failed"
    
    try:
        # Run the actual Claude command
        log_to_file(log_file, "🚀 Starting Claude process...")
        
        # Execute the command and stream output directly to log file
        with open(log_file, 'a') as log_f:
            result = subprocess.run(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                cwd=os.getcwd()  # Preserve working directory
            )
        
        exit_code = result.returncode
        status = "completed" if exit_code == 0 else "failed"
        
        log_to_file(log_file, f"✅ Claude process finished with exit code: {exit_code}")
        
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
            log_to_file(log_file, f"📊 Updating execution status to: {status}")
            # Convert exec_id to int if it's a numeric string
            if exec_id.isdigit():
                update_execution_status(int(exec_id), status, exit_code)
            else:
                # Legacy string ID support
                update_execution_status(exec_id, status, exit_code)
            log_to_file(log_file, "✅ Database updated successfully")
        except Exception as e:
            log_to_file(log_file, f"❌ Failed to update database: {str(e)}")
            # Don't exit with error if only DB update failed
            # The main process ran, which is what matters
    
    # Exit with the same code as the subprocess
    sys.exit(exit_code)


if __name__ == "__main__":
    main()