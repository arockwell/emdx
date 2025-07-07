# Plan for Adding Pagination to emdx view

## Current Issue
When using `emdx view`, long documents scroll past the terminal window, making it hard to read from the beginning.

## Approach Options

### Option 1: Use Python's built-in pager (Current attempt)
- Use Rich's console with a pager
- Problem: Rich's pager requires specific context manager usage

### Option 2: Use system pager directly
- Pipe output to `less` or system pager
- More reliable, works like git log, man pages, etc.

### Option 3: Add --no-pager flag
- Default to using pager
- Allow users to disable with flag if they want to pipe elsewhere

## Recommended Solution

Use Python's `pydoc.pager()` or subprocess to call system pager:

```python
import pydoc
import os

# Render everything to a string first
output = render_document(doc)

# Use pager (respects PAGER env var, falls back to less/more)
pydoc.pager(output)
```

Or more control:

```python
import subprocess
import os

pager = os.environ.get('PAGER', 'less')
process = subprocess.Popen(pager, stdin=subprocess.PIPE, text=True)
process.communicate(output)
```

This would:
- Work on all systems
- Respect user's PAGER preference
- Provide familiar navigation (like reading man pages)
- Not require mdcat or other dependencies