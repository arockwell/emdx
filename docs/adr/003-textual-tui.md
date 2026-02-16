# ADR-003: Textual for TUI

## Status

Accepted

## Context

EMDX needs a terminal user interface (TUI) for interactive document browsing, log viewing, and execution monitoring. The TUI (`emdx gui`) provides a rich, keyboard-driven experience for power users. Requirements include:

- **Rich widgets**: Tables, trees, panels, and text viewers
- **Vim-like navigation**: j/k movement, modal editing patterns
- **Real-time updates**: Live log streaming, reactive UI updates
- **Cross-platform**: Works consistently across macOS, Linux, and Windows terminals
- **Modern features**: Mouse support, CSS-like styling, responsive layouts

We considered several alternatives:

1. **curses/ncurses**: Standard library, very low-level
2. **urwid**: Established Python TUI library, callback-based
3. **blessed/blessings**: Thin wrapper over curses with better API
4. **Textual**: Modern, async, CSS-styled, from the Rich author
5. **prompt_toolkit**: Good for prompts, less suited for full-screen apps

## Decision

We chose **Textual** as the TUI framework.

### Key implementation details:

- **Multi-modal browser** in `emdx/ui/browser_container.py`
- **Specialized browsers**: DocumentBrowser, LogBrowser, ActivityView
- **Vim-style keybindings**: j/k navigation, g/G for top/bottom, modal selection
- **Reactive data binding**: UI automatically updates when data changes
- **Theme system** in `emdx/ui/themes.py` for visual customization

### Component hierarchy:

```
App (emdx gui)
└── BrowserContainer
    ├── DocumentBrowser (default, press 'd')
    │   ├── DocumentTable
    │   ├── PreviewPanel
    │   └── DetailsPanel
    ├── LogBrowser (press 'l')
    │   ├── ExecutionTable
    │   ├── LogViewer (with streaming)
    │   └── MetadataPanel
    ├── ActivityView (press 'a')
    │   ├── ActivityTree
    │   └── ContextPanel
```

## Consequences

### Positive

- **Rich terminal UI**: Modern widgets with CSS-like styling
- **Reactive updates**: `reactive` decorator automatically refreshes UI when data changes
- **Event system**: Clean separation between key handling and business logic
- **Cross-platform**: Consistent behavior across terminal emulators
- **Async-ready**: Native async/await support for background operations
- **Developer experience**: Hot reload, devtools, good debugging support
- **Ecosystem**: Same author as Rich, shares styling concepts

### Negative

- **Relatively new**: Less battle-tested than curses/urwid (though maturing rapidly)
- **Heavier dependency**: Larger than minimal curses wrapper
- **Learning curve**: Custom widget model and CSS subset to learn
- **Performance**: Can be slower than raw curses for extremely large datasets

### Mitigations

- **Pagination**: Large document lists use pagination, not full render
- **Lazy loading**: Log viewer streams content rather than loading all at once
- **Testing**: Textual provides testing tools for automated UI testing
- **Fallback**: CLI commands remain fully functional without TUI

## Key Patterns Used

### Widget Composition

```python
class DocumentBrowser(Widget):
    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("e", "edit", "Edit"),
        # ...
    ]

    def compose(self) -> ComposeResult:
        yield DocumentTable()
        yield PreviewPanel()
```

### Reactive Properties

```python
class LogViewer(Widget):
    content = reactive("")  # UI auto-updates when this changes

    def watch_content(self, value: str) -> None:
        """Called automatically when content changes."""
        self.refresh()
```

### Event Bubbling

```python
class DocumentSelected(Message):
    """Posted when a document is selected."""
    def __init__(self, doc_id: int):
        self.doc_id = doc_id
        super().__init__()

# Parent widgets can handle child events
def on_document_selected(self, event: DocumentSelected) -> None:
    self.preview.load(event.doc_id)
```

## References

- [Textual Documentation](https://textual.textualize.io/)
- [Textual GitHub](https://github.com/Textualize/textual)
- [EMDX UI Architecture](../ui-architecture.md)
