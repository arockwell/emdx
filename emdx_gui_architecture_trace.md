# EMDX GUI Architecture Trace

## 1. Entry Point Flow
```
emdx gui → gui.py::gui() → nvim_wrapper::run_textual_with_nvim_wrapper() → run_browser::run_browser() → BrowserContainer().run()
```

## 2. App Hierarchy
```
BrowserContainer (App) [browser_container.py]
├── CSS: Defines #browser-mount (height: 1fr) and #status (height: 1)
├── compose():
│   └── Vertical
│       ├── Static(id="browser-mount")  # Container for swappable browsers
│       └── Label(id="status")          # Status bar
└── on_mount():
    └── Mounts DocumentBrowser into #browser-mount
```

## 3. DocumentBrowser Widget Structure [document_browser.py]
```
DocumentBrowser (Widget)
├── CSS: 
│   ├── #sidebar: width: 2fr, height: 100%, layout: vertical
│   ├── #doc-table: height: 2fr, min-height: 10
│   ├── #details-panel: height: 1fr, min-height: 12, max-height: 50%, border: heavy red
│   └── #preview-container: width: 1fr
├── compose():
│   ├── Input(id="search-input")
│   ├── Input(id="tag-input")
│   ├── Label(id="tag-selector")
│   └── Horizontal
│       ├── Vertical(id="sidebar")
│       │   ├── DataTable(id="doc-table")      # Takes 2fr of sidebar
│       │   └── RichLog(id="details-panel")    # Takes 1fr of sidebar - THIS SHOULD BE VISIBLE!
│       └── Vertical(id="preview-container")
│           ├── Label(id="vim-mode-indicator")
│           └── ScrollableContainer(id="preview")
│               └── RichLog(id="preview-content")
└── on_mount():
    ├── Sets up table
    ├── Queries for #details-panel and writes debug content
    └── Logs sidebar children count
```

## 4. CSS Analysis

### Details Panel CSS:
```css
#details-panel {
    height: 1fr;            /* Should take 1/3 of sidebar space */
    min-height: 12;         /* Minimum 12 lines */
    max-height: 50%;        /* Maximum half of sidebar */
    border: heavy red;      /* VERY VISIBLE RED BORDER */
    padding: 1;
    background: $error 20%; /* Light red background */
    overflow-y: auto;
}
```

### Sidebar Layout:
- Sidebar uses `layout: vertical` 
- DataTable gets `height: 2fr` (2/3 of space)
- Details panel gets `height: 1fr` (1/3 of space)

## 5. Debug Logging

The code has extensive debug logging:
1. "🔴 COMPOSE CALLED - CREATING LHS SPLIT"
2. "🔴 CREATING SIDEBAR WITH TABLE AND DETAILS PANEL"
3. "🔴 YIELDING DETAILS PANEL NOW"
4. "🔴 DETAILS PANEL YIELDED"
5. "🔴 QUERYING FOR DETAILS PANEL"
6. "🔴 DETAILS PANEL FOUND!"
7. "🔴 WRITING TO DETAILS PANEL"
8. "🔴 SIDEBAR CHILDREN COUNT: {count}"
9. "🔴 SIDEBAR CHILD {i}: {class} with id={id}"

## 6. Potential Issues

1. **Fractional Heights**: The `fr` units might not be working as expected in Textual
2. **Container Overflow**: Parent container might be constraining the sidebar
3. **CSS Cascade**: Another CSS rule might be overriding the details panel styles
4. **Mount Order**: Widget might be getting removed or replaced after mount
5. **Layout Engine**: Textual's layout engine might not be calculating fractional units correctly

## 7. Widget Lifecycle

1. BrowserContainer creates and mounts DocumentBrowser
2. DocumentBrowser.compose() yields all widgets including details panel
3. DocumentBrowser.on_mount() queries for details panel and writes content
4. The details panel SHOULD be visible with:
   - Red border (border: heavy red)
   - Light red background ($error 20%)
   - Debug text "🔴🔴🔴 **DETAILS PANEL IS HERE** 🔴🔴🔴"

## 8. Key Finding

The details panel is being created and mounted correctly (based on the code), but it's not showing up visually. This suggests a layout/rendering issue rather than a creation issue.

## 9. Next Steps to Debug

1. Check if Textual is properly handling fractional units in vertical layouts
2. Try using fixed heights instead of fractional units
3. Check the actual computed styles at runtime
4. Verify the parent container isn't constraining the height
5. Test with simpler CSS to isolate the issue