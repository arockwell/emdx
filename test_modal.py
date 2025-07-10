#!/usr/bin/env python3
"""Test the modal browser directly."""

import sys
import curses

# Add the current directory to Python path
sys.path.insert(0, '.')

from emdx.modal_browser import main

if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)