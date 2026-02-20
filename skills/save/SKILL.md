---
name: save
description: Save findings, analysis, or decisions to the emdx knowledge base. Use when you have research results, investigation notes, or decisions worth persisting across sessions.
disable-model-invocation: true
---

# Save to Knowledge Base

Persist the following to emdx: $ARGUMENTS

## How to Save

**From stdin (most common for inline content):**
```bash
echo "your content here" | emdx save --title "Descriptive Title" --tags "analysis,active"
```

**From a file:**
```bash
emdx save path/to/document.md
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

## Common Gotcha

**DON'T:** `emdx save "text content"` — this looks for a FILE named "text content"
**DO:** `echo "text content" | emdx save --title "My Text"` — saves text via stdin

## After Saving

The command outputs the document ID (e.g., "Saved as #42"). Use this ID to reference the document later with `emdx view 42`, `emdx tag add 42 done`, or `emdx delegate --doc 42 "task"`.
