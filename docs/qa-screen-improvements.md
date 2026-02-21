# QA Screen Improvement Plan

## Current State

The QA screen has two layers that are **disconnected**:

- **`emdx/ui/qa/qa_screen.py`** — the widget mounted in the TUI. Has its own inline
  `_run_claude()` and `_retrieve_context()` functions, stores conversation entries as
  `dict[str, Any]`, and handles retrieval/answer generation directly.
- **`emdx/ui/qa/qa_presenter.py`** — a proper presenter with typed dataclasses
  (`QAEntry`, `QASource`, `QAStateVM`), semantic + keyword retrieval, state management
  via callbacks, and an `on_answer_chunk` slot for streaming. **Not wired into the
  screen.**

The screen works end-to-end but has significant gaps compared to the Activity and Task
browsers.

## Issues

| Area | Detail |
|------|--------|
| **Duplicate logic** | `qa_screen.py` reimplements retrieval (~60 lines) and Claude invocation (~50 lines) that already exist in `qa_presenter.py` |
| **Untyped state** | Screen stores entries as `list[dict[str, Any]]` instead of the `QAEntry` dataclass |
| **No semantic search** | Screen skips embeddings entirely (terminal corruption concern). The presenter handles semantic search but isn't used |
| **No streaming** | Answer appears all at once after 10-30s. `on_answer_chunk` callback exists on the presenter but has no real streaming implementation |
| **No conversation context** | Each question is independent — no multi-turn follow-up |
| **Single-pane layout** | Flat chat log with no source panel, unlike the two-pane layouts in TaskView and ActivityView |
| **Minimal loading feedback** | Static text ("Generating answer...") with no spinner or progress indication |
| **Basic visual design** | ASCII dividers (`─────`), plain `Q:`/`A:` labels, no visual separation between exchanges |

## Recommendations

### Tier 1 — Foundation (do first, unlocks everything else)

#### 1. Wire the presenter into the screen

The single highest-impact change. `qa_presenter.py` already provides:

- Typed dataclasses (`QAEntry`, `QASource`, `QAStateVM`)
- Semantic + keyword retrieval with automatic fallback
- State management via `on_state_update` callback
- Cancel support via `asyncio.Event`
- `on_answer_chunk` callback slot for streaming

Connecting it eliminates ~70 lines of duplicate logic from `qa_screen.py`, restores
semantic search, and sets up the callback-driven architecture needed for streaming.

The terminal state save/restore pattern (`_save_terminal_state` / `_restore_terminal_state`)
should move into the presenter's `_retrieve` and `_stream_answer` methods, wrapping the
`asyncio.to_thread` calls.

**Files:** `qa_screen.py`, `qa_presenter.py`

#### 2. Streaming answer rendering

Stream tokens into a progressively-updated widget as they arrive instead of waiting for
the complete response. Implementation:

- Change `_stream_answer` in the presenter to parse `stream-json` events incrementally
  (look for `content_block_delta` events, not just the final `result` event)
- Call `on_answer_chunk(delta_text)` for each token batch
- In the screen, append chunks to a `RichLog` or rebuild a `Markdown` widget on each
  chunk (RichLog is simpler; Markdown gives better formatting but may flicker)
- Convert to final rendered `Markdown` widget once the stream completes

**Files:** `qa_presenter.py`, `qa_screen.py`

### Tier 2 — UX Wins

#### 3. Two-pane layout with source panel

Follow the `TaskView` / `ActivityView` pattern:

```
┌──────────────────────────┬─────────────────────┐
│  Conversation            │  Sources             │
│                          │                      │
│  Q: How does auth work?  │  #42 Auth Design     │
│                          │  ────────────────    │
│  A: Authentication uses  │  JWT tokens are...   │
│  JWT tokens as described │                      │
│  in Document #42...      │  #58 Security Audit  │
│                          │  ────────────────    │
│                          │  The auth module...  │
├──────────────────────────┴─────────────────────┤
│  [input]                                        │
├─────────────────────────────────────────────────┤
│  status bar                                     │
└─────────────────────────────────────────────────┘
```

- Left pane (conversation): `ScrollableContainer` with Q&A messages — same as today
- Right pane (sources): `RichLog` or `ScrollableContainer` showing retrieved documents
  for the current/latest answer
- Update source panel each time retrieval completes
- Clicking a source opens `DocumentPreviewScreen` (already exists in `modals.py`)

**Files:** `qa_screen.py` (layout + CSS)

#### 4. Better visual separation of exchanges

Replace ASCII dividers and plain labels with styled containers:

- Use `$surface` / `$surface-darken-1` background tints to distinguish questions from
  answers (matches patterns in other screens)
- Add timestamp and elapsed time to each exchange
- Show retrieval method badge ("semantic" / "keyword") and source count
- Use `Static` widgets with CSS classes instead of inline Rich markup strings

**Files:** `qa_screen.py` (CSS + compose)

#### 5. Loading indicator

Replace static "Generating answer..." text with a two-phase indicator:

- **Retrieval phase:** "Searching... found 5 sources (1.2s)" — update count as docs
  are found
- **Generation phase:** Textual `LoadingIndicator` widget or animated dots
- Remove indicator once streaming begins (tokens replace the spinner)

Small change with outsized impact on perceived responsiveness.

**Files:** `qa_screen.py`

### Tier 3 — Feature Additions

#### 6. Multi-turn conversation context

Pass the last 1-2 Q&A exchanges as additional context in the system prompt so follow-up
questions work naturally:

```
User: How does auth work?
AI: Authentication uses JWT tokens...

User: What about the error handling?  ← this should work
```

This is a prompt-only change in the presenter's `_stream_answer` — append recent entries
to the user message. Cap at ~2000 tokens of prior context to avoid blowing the context
window.

**Files:** `qa_presenter.py`

#### 7. Clickable source references

When answer text contains `#42`, make it interactive:

- Parse rendered answer for `#\d+` patterns
- Wrap in `[@click=view_doc(42)]#42[/]` Rich markup, or post-process the `Markdown`
  widget
- On click, open `DocumentPreviewScreen` modal with the referenced document

**Files:** `qa_screen.py`

#### 8. Copy and re-ask keybindings

- `y` — copy last answer to clipboard (`pyperclip` or Textual's clipboard API)
- `e` — populate input with the last question for editing/re-asking
- Both are single-keybinding additions with no architectural changes needed

**Files:** `qa_screen.py`

## Implementation Order

```
1. Wire presenter into screen ──────────┐
2. Streaming answer rendering ──────────┤ Foundation
3. Loading indicator ───────────────────┘
4. Two-pane source panel ───────────────┐
5. Visual polish (CSS) ─────────────────┤ UX
6. Multi-turn context ─────────────────┘
7. Clickable sources ───────────────────┐
8. Copy / re-ask keybindings ───────────┘ Features
```

Steps 1-3 are the foundation — they fix the architecture and deliver the biggest
perceived improvement (streaming). Steps 4-6 bring the QA screen in line with the
other browsers visually. Steps 7-8 are polish.

## What to Skip

- **Model picker in the TUI** — low value; default model works for Q&A, power users
  can configure via settings
- **Full search history persistence** — the `s` save feature already covers this
- **Conversation branching** — too complex for the current UX; better suited for a
  dedicated chat application
