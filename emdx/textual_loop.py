#!/usr/bin/env python3
"""
Wrapper to run textual browser in a loop for edit/view actions.
"""
import subprocess
import sys
import os

def run_browser_loop():
    """Run the textual browser in a loop."""
    while True:
        # Run the browser
        result = subprocess.run([sys.executable, '-m', 'emdx.textual_browser'])
        
        # Check if it exited normally (quit) or for an action
        if result.returncode != 0:
            # Some error occurred
            break

if __name__ == "__main__":
    run_browser_loop()