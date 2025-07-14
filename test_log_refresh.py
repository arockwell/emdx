#!/usr/bin/env python3
"""
Test script to verify log browser auto-refresh functionality.
This script creates a test log file and simulates writing to it.
"""
import time
import logging
from pathlib import Path

# Set up logging to see debug messages
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def create_test_log():
    """Create a test log file and simulate writing to it."""
    log_file = Path("/tmp/emdx_test_log.txt")
    
    print(f"Creating test log file: {log_file}")
    
    # Write initial content
    with open(log_file, 'w') as f:
        f.write("Initial log content\n")
        f.write("Testing auto-refresh functionality\n")
    
    print("Initial content written. Now run EMDX log browser to view this file.")
    print("Then run this script with 'append' to add more content:")
    print(f"python {__file__} append")
    
    return log_file

def append_to_log():
    """Append new content to the test log file."""
    log_file = Path("/tmp/emdx_test_log.txt")
    
    if not log_file.exists():
        print("Test log file doesn't exist. Run without arguments first.")
        return
    
    print("Appending new content to test log...")
    
    for i in range(5):
        with open(log_file, 'a') as f:
            f.write(f"New log entry {i+1} at {time.strftime('%H:%M:%S')}\n")
        print(f"Wrote entry {i+1}")
        time.sleep(3)  # Wait 3 seconds between writes
    
    print("Finished appending content.")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "append":
        append_to_log()
    else:
        create_test_log()