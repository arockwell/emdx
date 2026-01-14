# EMDX TUI Theming Implementation Gameplan

## Overview

Implement a multi-theme system for the EMDX TUI application with 5 custom themes, theme persistence, and a theme switcher UI.

**Prerequisites:** Analysis complete (see `docs/theming-analysis.md`)
**Branch:** `make-themes`

---

## Phase 1: Core Infrastructure

### 1.1 Create Theme Definitions (`emdx/ui/themes.py`)

Create the theme manager module with all 5 custom themes.

**Verified Textual 4.0 API:**
```python
from textual.theme import Theme

# Theme constructor - name and primary are required, rest optional
Theme(
    name="emdx-dark",
    primary="#00D9FF",
    secondary="#9D4EDD",
    accent="#FF006E",
    foreground="#E6EDF3",
    background="#0D1117",
    surface="#161B22",
    panel="#1C2128",
    boost="#21262D",
    success="#3FB950",
    warning="#D29922",
    error="#F85149",
    dark=True,  # Important for light/dark detection
)
```

**Themes to implement:**
1. `emdx-dark` - Modern dark with cyan accents (default)
2. `emdx-light` - Clean professional light theme
3. `emdx-nord` - Muted Nord palette
4. `emdx-solarized-dark` - Classic Solarized dark
5. `emdx-solarized-light` - Classic Solarized light

**Functions to implement:**
- `get_all_themes() -> dict[str, Theme]`
- `register_all_themes(app: App) -> None`
- `get_code_theme(theme_name: str) -> str` - Map to Pygments theme
- `is_dark_theme(theme_name: str) -> bool`

### 1.2 Create UI Config Module (`emdx/config/ui_config.py`)

Handle theme preference persistence.

**Config location:** `~/.config/emdx/ui_config.json`

**Functions to implement:**
- `get_ui_config_path() -> Path`
- `load_ui_config() -> dict[str, Any]`
- `save_ui_config(config: dict) -> None`
- `get_theme() -> str`
- `set_theme(theme_name: str) -> None`

**Default config:**
```json
{
    "theme": "emdx-dark",
    "code_theme": "auto"
}
```

### 1.3 Integrate with BrowserContainer

Update `emdx/ui/browser_container.py` to load and apply themes on startup.

**Changes:**
1. Import theme manager and ui_config
2. In `on_mount()`: register themes, load preference, apply theme
3. Add action for theme switching: `action_switch_theme()`

---

## Phase 2: Migrate Hardcoded Colors

### 2.1 CSS Hardcoded Colors (5 files)

| File | Current | Replace With |
|------|---------|--------------|
| `worktree_picker.py` | `black` (input bg) | `$surface` |
| `worktree_picker.py` | `white` (input text) | `$text` |
| `worktree_picker.py` | `yellow` (focus border) | `$warning` |
| `document_browser.py` | `gray` (border) | `$primary` |
| `log_browser.py` | `gray` (border) | `$primary` |
| `vim_editor.py` | `#333333` (border) | `$surface` |

### 2.2 Status Colors Dict

Update `emdx/ui/pulse/zoom1/task_detail.py`:

```python
# Before
STATUS_COLORS = {
    'open': 'white',
    'active': 'green',
    'blocked': 'yellow',
    'done': 'dim',
    'failed': 'red',
}

# After - use CSS variable names for Rich
STATUS_COLORS = {
    'open': '$text',       # Will need helper
    'active': '$success',
    'blocked': '$warning',
    'done': '$text-muted',
    'failed': '$error',
}
```

---

## Phase 3: Rich Markup Theme Helper

### 3.1 The Problem

Rich markup like `[red]Error[/red]` uses hardcoded ANSI colors that don't respect Textual themes. We have **471+ instances** across the codebase.

### 3.2 Solution: Theme Color Helper

Create `emdx/ui/theme_colors.py`:

```python
from textual.app import App
from functools import lru_cache

# Semantic color names to Rich-compatible format
def get_theme_color(app: App, semantic: str) -> str:
    """
    Get Rich-compatible color string for semantic color name.

    Args:
        app: The Textual App instance
        semantic: One of 'error', 'success', 'warning', 'primary', 'secondary', 'muted'

    Returns:
        Hex color string like '#F85149'
    """
    theme = app.get_theme(app.theme)
    if not theme:
        # Fallback to standard colors
        fallbacks = {
            'error': 'red',
            'success': 'green',
            'warning': 'yellow',
            'primary': 'cyan',
            'secondary': 'magenta',
            'muted': 'dim',
        }
        return fallbacks.get(semantic, semantic)

    color_map = {
        'error': theme.error,
        'success': theme.success,
        'warning': theme.warning,
        'primary': theme.primary,
        'secondary': theme.secondary,
        'muted': theme.foreground,  # With dim style
    }
    return color_map.get(semantic) or semantic

def themed_markup(app: App, semantic: str, text: str) -> str:
    """
    Create Rich markup with theme-aware color.

    Usage:
        themed_markup(app, 'error', 'Failed!')  # Returns '[#F85149]Failed![/]'
    """
    color = get_theme_color(app, semantic)
    return f"[{color}]{text}[/]"
```

### 3.3 Migration Strategy

**High-priority files (UI components with app access):**
- `emdx/ui/git_browser.py` - `[red]`, `[yellow]` markup
- `emdx/ui/workflow_browser.py` - `[green]`, `[red]` markup
- `emdx/ui/pulse/zoom1/task_detail.py` - STATUS_COLORS

**Lower priority (CLI commands without app access):**
- `emdx/commands/agents.py` - `border_style="yellow"`, `border_style="cyan"`
- `emdx/commands/similarity.py` - Extensive Rich markup
- `emdx/commands/workflows.py` - Rich panel borders

**Note:** CLI commands run outside the TUI and don't have theme context. These can remain with standard colors or use environment variable detection.

---

## Phase 4: Code Syntax Theme Integration

### 4.1 Update markdown_config.py

Modify `emdx/ui/markdown_config.py` to read from theme config:

```python
from emdx.config.ui_config import load_ui_config
from emdx.ui.themes import get_code_theme, is_dark_theme

def get_configured_code_theme() -> str:
    """Get code theme based on UI config."""
    config = load_ui_config()
    code_theme = config.get("code_theme", "auto")

    if code_theme == "auto":
        main_theme = config.get("theme", "emdx-dark")
        return get_code_theme(main_theme)

    return code_theme
```

### 4.2 Code Theme Mapping

| Main Theme | Code Theme |
|------------|------------|
| `emdx-dark` | `monokai` |
| `emdx-light` | `tango` |
| `emdx-nord` | `nord` |
| `emdx-solarized-dark` | `solarized-dark` |
| `emdx-solarized-light` | `solarized-light` |

---

## Phase 5: Theme Switcher UI

### 5.1 Add Keybinding

In `BrowserContainer`, add keybinding `ctrl+t` for theme switching.

```python
BINDINGS = [
    # ... existing bindings
    Binding("ctrl+t", "switch_theme", "Theme"),
]
```

### 5.2 Create Theme Selector Modal

Create `emdx/ui/theme_selector.py`:

- Modal dialog showing available themes
- Preview of theme colors (optional)
- Immediate application on selection
- Persist selection to config

**UI Elements:**
- OptionList or RadioSet with theme names
- Theme description/preview
- Apply/Cancel buttons

### 5.3 Footer Update

Add theme indicator to status bar showing current theme name.

---

## Phase 6: Testing & Polish

### 6.1 Manual Testing Matrix

Test each theme across all views:
- [ ] Document Browser
- [ ] Log Browser
- [ ] Agent Browser
- [ ] Workflow Browser
- [ ] Git Browser (diff colors)
- [ ] Control Center
- [ ] Activity View
- [ ] Pulse views (Kanban, Timeline, Focus)
- [ ] All modal dialogs
- [ ] Vim editor (line numbers)

### 6.2 Terminal Compatibility

Test on:
- [ ] iTerm2 (macOS)
- [ ] Terminal.app (macOS)
- [ ] Alacritty
- [ ] VS Code integrated terminal
- [ ] Verify 24-bit color support detection

### 6.3 Edge Cases

- [ ] Theme switching while modal is open
- [ ] Theme persistence across app restarts
- [ ] Invalid theme name in config (fallback handling)
- [ ] Missing config file (create defaults)

---

## File Changes Summary

### New Files
| File | Purpose |
|------|---------|
| `emdx/ui/themes.py` | Theme definitions and registration |
| `emdx/config/ui_config.py` | UI preference persistence |
| `emdx/ui/theme_colors.py` | Rich markup theme helper |
| `emdx/ui/theme_selector.py` | Theme switcher modal |

### Modified Files
| File | Changes |
|------|---------|
| `emdx/ui/browser_container.py` | Theme loading, keybinding |
| `emdx/ui/worktree_picker.py` | Replace hardcoded colors |
| `emdx/ui/document_browser.py` | Replace `gray` border |
| `emdx/ui/log_browser.py` | Replace `gray` border |
| `emdx/ui/vim_editor.py` | Replace `#333333` |
| `emdx/ui/markdown_config.py` | Theme-aware code highlighting |
| `emdx/ui/pulse/zoom1/task_detail.py` | Theme-aware status colors |
| `emdx/ui/git_browser.py` | Theme-aware Rich markup |
| `emdx/ui/workflow_browser.py` | Theme-aware Rich markup |

---

## Implementation Order

```
Phase 1.1 → Phase 1.2 → Phase 1.3 → Phase 2 → Phase 5 → Phase 6
                                      ↓
                                   Phase 3 (can parallel)
                                      ↓
                                   Phase 4 (can parallel)
```

**Critical path:** 1.1 → 1.2 → 1.3 → 5 (basic theming works)
**Can defer:** Phase 3, 4 (Rich colors, code themes)

---

## Success Criteria

1. ✅ User can switch between 5 themes via `Ctrl+T`
2. ✅ Theme preference persists across sessions
3. ✅ All UI components respect theme colors
4. ✅ No hardcoded colors remain in CSS
5. ✅ Code syntax highlighting matches theme
6. ✅ Works on major terminal emulators

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Rich markup migration is extensive | Prioritize UI components, defer CLI commands |
| Theme switching causes UI glitches | Test thoroughly, add refresh if needed |
| Some terminals don't support 24-bit color | Textual handles fallback automatically |
| Config file corruption | Validate on load, use defaults on error |
