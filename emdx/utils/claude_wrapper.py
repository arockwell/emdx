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

from emdx.models.executions import update_execution_heartbeat, update_execution_status


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

    # Open log file directly for human-readable output
    log_handle = open(log_file, 'w', buffering=1)  # Line buffered
    
    # Helper to write timestamped log entries
    def write_log(message: str):
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_handle.write(f"[{timestamp}] {message}\n")
        log_handle.flush()
    
    # Log execution start
    write_log(f"🚀 Starting execution #{exec_id}")
    write_log(f"📂 Working directory: {os.getcwd()}")
    
    # Do lightweight environment validation (no subprocess calls)
    write_log("🔍 Checking environment...")

    exit_code = 1  # Default to failure
    status = "failed"
    lines_processed = 0  # Track lines to detect empty runs
    
    # Start heartbeat thread
    stop_heartbeat = threading.Event()
    heartbeat = threading.Thread(target=heartbeat_thread, args=(exec_id, stop_heartbeat))
    heartbeat.daemon = True
    heartbeat.start()

    # Quick check if claude exists without subprocess
    import shutil
    if not shutil.which(cmd[0]):
        write_log(f"❌ Command '{cmd[0]}' not found in PATH")
        write_log(f"PATH: {os.environ.get('PATH', 'not set')}")
        write_log("💡 Make sure Claude Code is installed: https://docs.anthropic.com/claude-code")
        update_execution_status(exec_id, "failed", 127)
        log_handle.close()
        sys.exit(127)

    try:
        # Run the actual Claude command
        write_log("Starting Claude process...")

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

        write_log(f"Claude process started with PID: {process.pid}")

        # Stream and format output
        lines_processed = 0
        for line in process.stdout:
            lines_processed += 1
            line = line.strip()
            if not line:
                continue
            
            # Try to parse and format Claude's JSON output
            try:
                data = json.loads(line)
                if data.get("type") == "assistant" and "message" in data:
                    # Extract the actual message text from Claude
                    message = data["message"]
                    if "content" in message and message["content"]:
                        for content in message["content"]:
                            if content.get("type") == "text":
                                write_log(f"🤖 Claude: {content['text']}")
                            elif content.get("type") == "tool_use":
                                tool_name = content.get("name", "unknown")
                                write_log(f"🔧 Using tool: {tool_name}")
                elif data.get("type") == "result":
                    # Final result from Claude
                    if data.get("subtype") == "success":
                        write_log(f"✅ Result: {data.get('result', 'Success')}")
                    else:
                        write_log(f"❌ Error: {data.get('error', 'Unknown error')}")
                elif data.get("type") == "system":
                    # Format system messages nicely
                    if data.get("subtype") == "init":
                        # Extract useful info from init message
                        write_log(f"🔧 System initialized")
                        write_log(f"📍 Working directory: {data.get('cwd', 'unknown')}")
                        write_log(f"🤖 Model: {data.get('model', 'unknown')}")
                        # List available tools
                        tools = data.get('tools', [])
                        if tools:
                            # Group tools into categories for better display
                            basic_tools = []
                            mcp_tools = []
                            for tool in tools:
                                if tool.startswith('mcp__'):
                                    mcp_tools.append(tool.replace('mcp__gmail-mcp__', ''))
                                else:
                                    basic_tools.append(tool)
                            
                            if basic_tools:
                                write_log(f"🛠️ Tools available:")
                                for i, tool in enumerate(basic_tools, 1):
                                    write_log(f"    {i:2d}. {tool}")
                                if len(basic_tools) > 20:  # Only show first 20 to keep logs readable
                                    write_log(f"         ...and {len(basic_tools) - 20} more")
                            
                            if mcp_tools:
                                write_log(f"📧 MCP Gmail tools:")
                                for i, tool in enumerate(mcp_tools, 1):
                                    write_log(f"    {i:2d}. {tool}")
                    else:
                        write_log(f"🔧 System: {data.get('subtype', 'info')}")
                elif data.get("type") == "user":
                    # Skip user messages - these are usually tool results that clutter the log
                    pass
                else:
                    # For other JSON types, only log if they seem important
                    if data.get("type") not in ["user"]:
                        write_log(f"🔧 {data.get('type', 'unknown')}: {data.get('subtype', '')}")
            except json.JSONDecodeError:
                # Not JSON - just write as-is
                if line.strip():
                    log_handle.write(line + "\n")
                    log_handle.flush()

        # Wait for process to complete
        process.wait()
        result = process

        duration = time.time() - start_time

        exit_code = result.returncode
        status = "completed" if exit_code == 0 else "failed"

        write_log(f"✅ Execution completed in {duration:.1f}s")
        write_log(f"Exit code: {exit_code}")
        write_log(f"Lines processed: {lines_processed}")

    except FileNotFoundError as e:
        write_log(f"❌ Command not found: {cmd[0]}")
        write_log(f"Error: {str(e)}")
        write_log("Make sure 'claude' is installed and in your PATH")
        status = "failed"
        exit_code = 127  # Standard command not found exit code

    except subprocess.TimeoutExpired:
        write_log("❌ Process timed out")
        status = "failed"
        exit_code = 124  # Standard timeout exit code

    except KeyboardInterrupt:
        write_log("⚠️ Process interrupted by user")
        status = "failed"
        exit_code = 130  # Standard SIGINT exit code

    except Exception as e:
        write_log(f"❌ Wrapper error: {str(e)}")
        write_log("Traceback:")
        for line in traceback.format_exc().splitlines():
            write_log(f"  {line}")
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
            write_log(f"✅ Database updated: {status} (exit code: {exit_code})")
        except Exception as e:
            write_log(f"❌ Failed to update database: {str(e)}")
            # Don't exit with error if only DB update failed
            # The main process ran, which is what matters
        
        # Close log file
        log_handle.close()

    # Exit with the same code as the subprocess
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
