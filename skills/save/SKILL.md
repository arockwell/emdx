---
name: save
description: Save findings, analysis, or decisions to the emdx knowledge base. Use when you have research results, investigation notes, or decisions worth persisting across sessions.
disable-model-invocation: true
---

# Save to Knowledge Base

Persist the following to emdx: $ARGUMENTS

## How to Save

**Inline content (positional arg):**
```bash
emdx save "Quick note about the auth module"
emdx save "Detailed findings here" --title "Auth Analysis" --tags "analysis,active"
```

**From a file (explicit --file flag):**
```bash
emdx save --file document.md
emdx save --file document.md --title "Custom Title"
```

**From stdin:**
```bash
echo "piped content" | emdx save --title "My Note" --tags "notes"
ls -la | emdx save --title "Directory Listing"
```

**With tags for classification:**

| Content Type | Tags |
|---|---|
| Plans/strategy | `gameplan, active` |
| Investigation | `analysis` |
| Bug fixes | `bugfix` |
| Security | `security` |
| Notes | `notes` |

**Status tags:** `active` (working), `done` (completed), `blocked` (stuck)
**Outcome tags:** `success`, `failed`, `partial`

## Useful Options

- `--auto-link` — Auto-link to semantically similar documents (requires `emdx ai index`)
- `--gist` / `--secret` / `--public` — Create a GitHub gist after saving
- `--copy` — Copy gist URL to clipboard
- `--task <id>` — Link saved document to a task as its output
- `--done` — Also mark the linked task as done (requires `--task`)
- `--supersede` — Auto-link to existing doc with same title

## After Saving

The command outputs the document ID (e.g., "Saved as #42"). Use this ID to reference the document later with `emdx view 42`, `emdx tag add 42 done`, or `emdx delegate --doc 42 "task"`.
