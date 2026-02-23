---
name: setup
description: Install and configure the emdx CLI tool. Run this once to set up emdx on your system.
disable-model-invocation: true
---

# Setup emdx

Install and verify the emdx CLI.

## Steps

### 1. Check current state

```bash
command -v emdx && emdx --version || echo "emdx not found"
```

### 2. Install emdx

If emdx is not installed, install it. Prefer `uv` if available, fall back to `pip`:

```bash
# Try uv first (faster, isolated)
uv tool install emdx 2>/dev/null || pip install emdx
```

### 3. Verify installation

```bash
emdx --version
emdx status --stats
```

### 4. Report to user

Tell the user:
- Which version was installed
- Whether their knowledge base already has documents or is fresh
- That they can now use `/emdx:save`, `/emdx:delegate`, `/emdx:research`, and other emdx skills
