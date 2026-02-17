# TUI Debug — Terminal State Debugging

Debug TUI issues where mouse/keys stop working after background operations.

## When to Use

- Mouse stops working after a background operation completes
- Keys stop responding after `asyncio.to_thread` calls
- TUI freezes but the process is still alive
- Symptoms appear only in the real app, not in isolated test apps

## Terminal State Instrumentation

Add checkpoint logging around suspected code:

```python
import sys, termios, logging
logger = logging.getLogger(__name__)

fd = sys.stdin.fileno()
attrs = termios.tcgetattr(fd)
logger.info("TERMINAL [label]: iflag=%#x lflag=%#x", attrs[0], attrs[3])
```

## Key Values

| State | lflag | Meaning |
|-------|-------|---------|
| Raw mode (Textual healthy) | `0x43` | No ECHO, no ICANON — Textual controls input |
| Cooked mode (BROKEN) | `0x5cb` | ECHO + ICANON + ISIG — terminal reset to normal |

If lflag changes between checkpoints, the code between them is the culprit.

## Fix Pattern

```python
import sys, termios

def _save_terminal_state():
    try:
        return termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        return None

def _restore_terminal_state(saved):
    if saved is None:
        return
    try:
        fd = sys.stdin.fileno()
        current = termios.tcgetattr(fd)
        if current != saved:
            termios.tcsetattr(fd, termios.TCSANOW, saved)
    except Exception:
        pass
```

Wrap dangerous calls:
```python
saved = _save_terminal_state()
result = await asyncio.to_thread(dangerous_function)
_restore_terminal_state(saved)
```

## Known Offenders

- **torch / sentence-transformers import**: Resets terminal on first import in a thread
- **UnifiedExecutor subprocess path**: Something in its execution pipeline corrupts state
- Any library that calls `termios.tcsetattr()` or `os.system("stty ...")` during init

## Logging

- TUI logs: `~/.config/emdx/tui_debug.log` (NOT `emdx.log`)
- emdx.* loggers are at INFO level, root at WARNING
- Use `logger.info()` — `logger.debug()` won't appear

## Binary Search Approach

When the offender isn't obvious:

1. Build a minimal version that works (no background work)
2. Add one component at a time until it breaks
3. Instrument the breaking component with terminal state checks
4. Narrow down to the exact line that corrupts state

See PR #694 for a full example of this approach.
