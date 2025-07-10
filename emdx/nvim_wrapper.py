#!/usr/bin/env python3
"""
External nvim wrapper that completely manages terminal state to eliminate flash.
"""

import os
import sys
import subprocess
import tempfile
import termios
import tty
from pathlib import Path

def save_terminal_state():
    """Save current terminal state."""
    try:
        fd = sys.stdin.fileno()
        return termios.tcgetattr(fd)
    except:
        return None

def restore_terminal_state(state):
    """Restore terminal state."""
    if state:
        try:
            fd = sys.stdin.fileno()
            termios.tcsetattr(fd, termios.TCSADRAIN, state)
        except:
            pass

def clear_screen_completely():
    """Clear screen and reset cursor completely."""
    # Multiple approaches to ensure clean screen
    sys.stdout.write('\033[2J')  # Clear entire screen
    sys.stdout.write('\033[H')   # Move cursor to home
    sys.stdout.write('\033[3J')  # Clear scrollback
    sys.stdout.flush()
    
    # Also use system clear
    os.system('clear')

def run_textual_with_nvim_wrapper():
    """Run textual browser with external nvim wrapper."""
    
    # Save initial terminal state
    initial_state = save_terminal_state()
    
    try:
        while True:
            # Clear screen before starting textual
            clear_screen_completely()
            
            # Check for edit signal first
            edit_signal = f"/tmp/emdx_edit_signal_{os.getpid()}"
            if os.path.exists(edit_signal):
                with open(edit_signal, 'r') as f:
                    temp_file, doc_id = f.read().strip().split('|')
                os.remove(edit_signal)
                
                # Clear screen completely before nvim
                clear_screen_completely()
                
                # Launch nvim with saved terminal state
                restore_terminal_state(initial_state)
                result = subprocess.run(['nvim', temp_file])
                
                # Process changes if nvim succeeded
                if result.returncode == 0:
                    process_nvim_changes(temp_file, int(doc_id))
                
                # Clean up temp file
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
                
                # Continue loop to restart textual
                continue
            
            # Run textual browser
            from emdx.textual_browser_minimal import run_minimal
            exit_code = run_minimal()
            
            # Check exit code to see if we should continue
            if exit_code == 42:  # Special code for edit request
                continue
            else:
                break  # Normal exit
                
    finally:
        # Restore original terminal state
        restore_terminal_state(initial_state)
        clear_screen_completely()

def process_nvim_changes(temp_file: str, doc_id: int):
    """Process changes from nvim editing."""
    try:
        if not os.path.exists(temp_file):
            return
            
        with open(temp_file, 'r') as f:
            lines = f.readlines()
        
        # Remove comment lines
        lines = [line for line in lines if not line.strip().startswith('#')]
        
        if not lines:
            return
        
        # Extract title and content
        new_title = ""
        content_start = 0
        for i, line in enumerate(lines):
            if line.strip():
                new_title = line.strip()
                content_start = i + 1
                break
        
        if not new_title:
            return
        
        new_content = ''.join(lines[content_start:]).strip()
        
        # Update document
        from emdx.database import db
        db.update_document(doc_id, new_title, new_content)
        
    except Exception as e:
        print(f"Error processing changes: {e}")

if __name__ == "__main__":
    run_textual_with_nvim_wrapper()