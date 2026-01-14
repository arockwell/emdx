# EMDX TUI Theming Analysis

## Overview

This document provides a comprehensive analysis of all themeable elements in the EMDX TUI application, along with proposed light and dark theme designs.

**Textual Version:** 4.0+
**Theming Approach:** CSS Variables + Textual's built-in theme system

---

## 1. Current CSS Variables in Use

The EMDX TUI already uses Textual's CSS variable system extensively:

| Variable | Purpose | Usage Count |
|----------|---------|-------------|
| `$primary` | Main accent color (borders, highlights) | 50+ |
| `$secondary` | Secondary accent color | 10+ |
| `$background` | Main application background | 20+ |
| `$surface` | Container/panel backgrounds | 30+ |
| `$boost` | Elevated backgrounds (status bars, headers) | 40+ |
| `$text` | Primary text color | 25+ |
| `$text-muted` | Secondary/dimmed text | 20+ |
| `$success` | Success states (green-like) | 15+ |
| `$warning` | Warning states (yellow-like) | 15+ |
| `$error` | Error states (red-like) | 15+ |
| `$accent` | Selection/highlight color | 10+ |
| `$panel` | Panel-specific backgrounds | 5+ |

---

## 2. Hardcoded Colors (Need Migration)

These hardcoded values should be converted to CSS variables for full theme support:

| Value | Location | Suggested Variable |
|-------|----------|-------------------|
| `black` | `worktree_picker.py` (input bg) | `$surface` or `$background` |
| `white` | `worktree_picker.py` (input text) | `$text` |
| `yellow` | `worktree_picker.py` (focus border) | `$warning` or `$accent` |
| `gray` | `document_browser.py`, `log_browser.py` | `$text-muted` or `$surface` |
| `#333333` | `vim_editor.py` (line number border) | `$surface` |

---

## 3. Complete Themeable Elements Catalog

### 3.1 Status Bars & Headers

**Pattern:** `background: $boost; color: $text; text-style: bold`

Components using this pattern:
- Document Browser status bar
- Log Browser status bar
- Agent Browser status bar
- Workflow Browser status bar
- Control Center status bar
- Activity View status bar
- All Pulse views (Kanban, Timeline, Focus, etc.)

### 3.2 Container Backgrounds

| Background Type | CSS | Usage |
|-----------------|-----|-------|
| Main background | `background: $background` | App root |
| Surface/Cards | `background: $surface` | Modals, cards, panels |
| Elevated | `background: $boost` | Headers, status bars |
| Panel | `background: $panel` | Sidebars |
| Semi-transparent accent | `background: $primary 20%` | Highlighted items |
| Success indicator | `background: $success 20%` | Running states |

### 3.3 Border Styles

**Border Types in Use:**
- `solid` - Standard borders
- `thick` - Emphasized borders (modals)
- `heavy` - Heavy weight dividers
- `tall` - Vertical status indicators (kanban cards)

**Border Color Patterns:**

| Pattern | Purpose | Example Usage |
|---------|---------|---------------|
| `border: solid $primary` | Standard dividers | Input fields, panels |
| `border: thick $primary` | Modal containers | All modal dialogs |
| `border: thick $error` | Error states | Delete confirmation modals |
| `border: thick $background` | Subtle containers | Secondary modals |
| `border-left: tall $success` | Active status | Kanban active cards |
| `border-left: tall $warning` | Blocked status | Kanban blocked cards |
| `border-left: solid $primary` | Section emphasis | Activity view sections |
| `border-right: solid $primary` | Panel dividers | Sidebars |
| `border-top/bottom: solid $surface` | Subtle dividers | Section separators |

### 3.4 Text Colors

| Style | CSS/Markup | Usage |
|-------|------------|-------|
| Primary text | `color: $text` | Main content |
| Muted text | `color: $text-muted` | Secondary info, hints |
| Success text | `color: $success` | Success messages |
| Warning text | `color: $warning` | Warning labels |
| Error text | `color: $error` | Error messages |

### 3.5 Rich Markup Colors

Used in dynamic content via Rich library:

| Markup | Purpose | Suggested Theme Variable |
|--------|---------|-------------------------|
| `[red]` | Errors, failures | `$error` |
| `[green]` | Success, research category | `$success` |
| `[yellow]` | Warnings, generation category | `$warning` |
| `[blue]` | Information, analysis | `$primary` or `$accent` |
| `[cyan]` | Debugging, distances | `$secondary` |
| `[bold]` | Emphasis | N/A (style) |
| `[dim]` | Secondary content | `$text-muted` |
| `[italic]` | Subtle info | N/A (style) |

### 3.6 Status Color Mapping

From `task_detail.py`:

```python
STATUS_COLORS = {
    'open': 'white',      # Should be $text
    'active': 'green',    # Should be $success
    'blocked': 'yellow',  # Should be $warning
    'done': 'dim',        # Should be $text-muted
    'failed': 'red',      # Should be $error
}
```

### 3.7 Modal Dialogs

**Standard Modal Pattern:**
```css
.modal-container {
    background: $surface;
    border: thick $primary;
}
.modal-title {
    color: $warning;
    text-style: bold;
}
```

**Error Modal Pattern:**
```css
.error-modal {
    background: $surface;
    border: thick $error;
}
.error-title {
    color: $error;
}
```

### 3.8 Form Elements

| Element | Style |
|---------|-------|
| Input field | `border: solid $primary; background: $surface` |
| Input focus | `border: solid $accent` (or `$warning`) |
| Error field | `border: thick $error` |
| Label | `color: $text` |
| Hint/placeholder | `color: $text-muted` |
| Error label | `color: $error` |

### 3.9 Data Tables

DataTable widgets inherit Textual's default styling:
- Header: `background: $boost`
- Rows: `background: $surface` (alternating with transparency)
- Selection: `background: $accent` or `$primary 20%`
- Borders: `border: solid $primary`

### 3.10 Vim Editor Components

| Element | Current | Suggested |
|---------|---------|-----------|
| Line numbers (active) | `bold yellow` | `$warning` or `$accent` |
| Line numbers (relative) | `dim yellow` | `$text-muted` |
| Distance indicator | `dim cyan` | `$secondary` |
| Line number border | `#333333` | `$surface` |

### 3.11 Kanban/Timeline Views

**Kanban Cards:**
- Default: `background: $surface`
- Selected: `background: $accent`
- Active: `border-left: tall $success`
- Blocked: `border-left: tall $warning`
- Done: `color: $text-muted`

**Timeline Bars:**
- Running: `background: $success`
- Completed: `background: $primary`
- Failed: `background: $error`
- Selected: `border: tall $accent`

### 3.12 Code Syntax Highlighting

From `markdown_config.py`:

**Dark Themes:** monokai, dracula, nord, one-dark, gruvbox-dark
**Light Themes:** manni, tango, perldoc, friendly, colorful

---

## 4. Proposed Theme Designs

### 4.1 EMDX Dark Theme (Default)

A modern dark theme with cyan/blue accents inspired by terminal aesthetics.

```python
EMDX_DARK = {
    # Core colors
    "primary": "#00D9FF",      # Bright cyan - main accent
    "secondary": "#9D4EDD",    # Purple - secondary accent
    "accent": "#FF006E",       # Hot pink - selection/highlight

    # Backgrounds
    "background": "#0D1117",   # Deep dark blue-black
    "surface": "#161B22",      # Slightly lighter for cards/panels
    "panel": "#1C2128",        # Sidebar backgrounds
    "boost": "#21262D",        # Status bars, headers

    # Text
    "foreground": "#E6EDF3",   # Primary text (bright)
    "text-muted": "#8B949E",   # Secondary text (dimmed)

    # Status colors
    "success": "#3FB950",      # Green - success states
    "warning": "#D29922",      # Amber - warning states
    "error": "#F85149",        # Red - error states
}

# Matching code theme: "monokai" or "one-dark"
```

**Design Rationale:**
- GitHub-inspired dark palette for familiarity
- High contrast cyan accent for visibility
- Distinct status colors that work on dark backgrounds
- Purple secondary for visual interest without clashing

### 4.2 EMDX Light Theme

A clean, professional light theme with blue accents.

```python
EMDX_LIGHT = {
    # Core colors
    "primary": "#0969DA",      # Blue - main accent
    "secondary": "#8250DF",    # Purple - secondary accent
    "accent": "#BF3989",       # Magenta - selection/highlight

    # Backgrounds
    "background": "#FFFFFF",   # Pure white
    "surface": "#F6F8FA",      # Light gray for cards/panels
    "panel": "#F0F2F5",        # Slightly darker for sidebars
    "boost": "#DFE3E8",        # Status bars, headers

    # Text
    "foreground": "#1F2328",   # Primary text (near black)
    "text-muted": "#656D76",   # Secondary text (gray)

    # Status colors
    "success": "#1A7F37",      # Dark green - visible on light
    "warning": "#9A6700",      # Dark amber - visible on light
    "error": "#CF222E",        # Dark red - visible on light
}

# Matching code theme: "tango" or "friendly"
```

**Design Rationale:**
- Clean white background reduces eye strain in bright environments
- Darker status colors ensure WCAG contrast compliance
- Blue primary matches common UI conventions
- Subtle surface variations maintain visual hierarchy

### 4.3 EMDX Nord Theme

A muted, low-contrast theme based on the popular Nord palette.

```python
EMDX_NORD = {
    # Core colors
    "primary": "#88C0D0",      # Frost blue
    "secondary": "#B48EAD",    # Aurora purple
    "accent": "#EBCB8B",       # Aurora yellow

    # Backgrounds
    "background": "#2E3440",   # Polar night
    "surface": "#3B4252",      # Polar night (lighter)
    "panel": "#434C5E",        # Polar night (lighter)
    "boost": "#4C566A",        # Polar night (lightest)

    # Text
    "foreground": "#ECEFF4",   # Snow storm
    "text-muted": "#D8DEE9",   # Snow storm (dimmed)

    # Status colors
    "success": "#A3BE8C",      # Aurora green
    "warning": "#EBCB8B",      # Aurora yellow
    "error": "#BF616A",        # Aurora red
}

# Matching code theme: "nord"
```

### 4.4 EMDX Solarized Dark

Classic Solarized dark for those who prefer it.

```python
EMDX_SOLARIZED_DARK = {
    # Core colors
    "primary": "#268BD2",      # Blue
    "secondary": "#6C71C4",    # Violet
    "accent": "#2AA198",       # Cyan

    # Backgrounds
    "background": "#002B36",   # Base03
    "surface": "#073642",      # Base02
    "panel": "#073642",        # Base02
    "boost": "#586E75",        # Base01

    # Text
    "foreground": "#839496",   # Base0
    "text-muted": "#657B83",   # Base00

    # Status colors
    "success": "#859900",      # Green
    "warning": "#B58900",      # Yellow
    "error": "#DC322F",        # Red
}

# Matching code theme: "solarized-dark"
```

### 4.5 EMDX Solarized Light

```python
EMDX_SOLARIZED_LIGHT = {
    # Core colors
    "primary": "#268BD2",      # Blue
    "secondary": "#6C71C4",    # Violet
    "accent": "#2AA198",       # Cyan

    # Backgrounds
    "background": "#FDF6E3",   # Base3
    "surface": "#EEE8D5",      # Base2
    "panel": "#EEE8D5",        # Base2
    "boost": "#93A1A1",        # Base1

    # Text
    "foreground": "#657B83",   # Base00
    "text-muted": "#839496",   # Base0

    # Status colors
    "success": "#859900",      # Green
    "warning": "#B58900",      # Yellow
    "error": "#DC322F",        # Red
}

# Matching code theme: "solarized-light"
```

---

## 5. Theme Implementation Checklist

### Phase 1: Infrastructure
- [ ] Create `emdx/ui/themes.py` with theme definitions
- [ ] Create `emdx/config/ui_config.py` for preference storage
- [ ] Add theme loading in `BrowserContainer.on_mount()`
- [ ] Store preferences in `~/.config/emdx/ui_config.json`

### Phase 2: Migrate Hardcoded Colors
- [ ] `worktree_picker.py` - Replace `black`, `white`, `yellow`
- [ ] `document_browser.py` - Replace `gray`
- [ ] `log_browser.py` - Replace `gray`
- [ ] `vim_editor.py` - Replace `#333333`
- [ ] `task_detail.py` - Update STATUS_COLORS dict

### Phase 3: Rich Markup Colors
- [ ] Create theme-aware color helper function
- [ ] Update all `[red]`, `[green]`, `[yellow]` markup to use helper
- [ ] Ensure contrast works on both light and dark themes

### Phase 4: Code Theme Sync
- [ ] Update `markdown_config.py` to read from theme config
- [ ] Map main theme to appropriate code theme
- [ ] Allow override via config

### Phase 5: Theme Switcher UI
- [ ] Add `Ctrl+T` keybinding for theme switcher
- [ ] Create theme selection modal/command palette
- [ ] Persist selection immediately on change

### Phase 6: Testing
- [ ] Test all 5 themes across all browser views
- [ ] Verify contrast ratios meet WCAG AA standards
- [ ] Test on various terminal emulators

---

## 6. Configuration File Structure

**Location:** `~/.config/emdx/ui_config.json`

```json
{
    "theme": "emdx-dark",
    "code_theme": "auto",
    "custom_themes": {},
    "ui_preferences": {
        "sidebar_width": 30,
        "show_line_numbers": true
    }
}
```

**Theme Options:**
- `emdx-dark` (default)
- `emdx-light`
- `emdx-nord`
- `emdx-solarized-dark`
- `emdx-solarized-light`
- `textual-dark` (Textual built-in)
- `textual-light` (Textual built-in)
- `nord` (Textual built-in)
- `gruvbox` (Textual built-in)
- `tokyo-night` (Textual built-in)

**Code Theme Options:**
- `auto` - Match main theme automatically
- Or any Pygments theme name

---

## 7. API Design

### Theme Manager (`emdx/ui/themes.py`)

```python
from textual.theme import Theme
from typing import Dict, Optional

# Theme definitions
EMDX_THEMES: Dict[str, Theme] = {
    "emdx-dark": Theme(...),
    "emdx-light": Theme(...),
    "emdx-nord": Theme(...),
    "emdx-solarized-dark": Theme(...),
    "emdx-solarized-light": Theme(...),
}

# Code theme mapping
CODE_THEME_MAP: Dict[str, str] = {
    "emdx-dark": "monokai",
    "emdx-light": "tango",
    "emdx-nord": "nord",
    "emdx-solarized-dark": "solarized-dark",
    "emdx-solarized-light": "solarized-light",
}

def register_themes(app: App) -> None:
    """Register all custom themes with the app."""
    for name, theme in EMDX_THEMES.items():
        app.register_theme(theme)

def get_code_theme(main_theme: str) -> str:
    """Get matching code theme for syntax highlighting."""
    return CODE_THEME_MAP.get(main_theme, "monokai")

def is_dark_theme(theme_name: str) -> bool:
    """Check if a theme is dark or light."""
    light_themes = {"emdx-light", "emdx-solarized-light", "textual-light"}
    return theme_name not in light_themes
```

### UI Config (`emdx/config/ui_config.py`)

```python
import json
from pathlib import Path
from typing import Any, Dict

def get_ui_config_path() -> Path:
    """Get path to UI config file."""
    config_dir = Path.home() / ".config" / "emdx"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "ui_config.json"

def load_ui_config() -> Dict[str, Any]:
    """Load UI configuration from file."""
    path = get_ui_config_path()
    if path.exists():
        return json.loads(path.read_text())
    return {"theme": "emdx-dark", "code_theme": "auto"}

def save_ui_config(config: Dict[str, Any]) -> None:
    """Save UI configuration to file."""
    path = get_ui_config_path()
    path.write_text(json.dumps(config, indent=2))

def get_theme() -> str:
    """Get current theme name."""
    return load_ui_config().get("theme", "emdx-dark")

def set_theme(theme_name: str) -> None:
    """Set and persist theme."""
    config = load_ui_config()
    config["theme"] = theme_name
    save_ui_config(config)
```

---

## 8. Summary

**Current State:**
- ✅ Already uses CSS variables extensively (excellent foundation)
- ✅ Consistent patterns for status bars, modals, borders
- ⚠️ 5 hardcoded colors need migration
- ⚠️ Rich markup colors need theme-aware helper

**Proposed Themes:**
1. **EMDX Dark** - Modern dark with cyan accents (default)
2. **EMDX Light** - Clean professional light theme
3. **EMDX Nord** - Muted, low-contrast dark
4. **EMDX Solarized Dark** - Classic Solarized
5. **EMDX Solarized Light** - Classic Solarized light

**Implementation Effort:**
- Phase 1-2: ~2-3 hours (infrastructure + migrations)
- Phase 3-4: ~1-2 hours (Rich colors + code themes)
- Phase 5-6: ~2-3 hours (UI + testing)
- **Total: ~5-8 hours**

The EMDX codebase is well-prepared for theming due to consistent use of CSS variables. The main work involves creating the theme manager, migrating the few hardcoded colors, and building a theme switcher UI.

---

## 9. Audit Findings & Corrections

This section documents issues found during code review of the analysis.

### 9.1 Corrected CSS Variable Usage Counts

The original estimates were inaccurate. Actual counts from codebase grep:

| Variable | Original Estimate | Actual Count | Status |
|----------|-------------------|--------------|--------|
| `$primary` | 50+ | **39** | ❌ Overstated |
| `$surface` | 30+ | **31** | ✅ Accurate |
| `$text-muted` | 20+ | **29** | ✅ Understated |
| `$boost` | 40+ | **20** | ❌ Overstated |
| `$text` | 25+ | **7** | ❌ Overstated |
| `$warning` | 15+ | **14** | ✅ Accurate |
| `$success` | 15+ | **8** | ❌ Overstated |
| `$error` | 15+ | **8** | ❌ Overstated |
| `$background` | 20+ | **6** | ❌ Overstated |
| `$accent` | 10+ | **2** | ❌ Overstated |
| `$secondary` | 10+ | **1** | ❌ Overstated |
| `$panel` | 5+ | **1** | ✅ Accurate |

### 9.2 Additional Hardcoded Colors (MISSED)

The original audit missed significant Rich markup color usage:

**Additional locations found:**
| Color | File | Usage |
|-------|------|-------|
| `yellow` | `emdx/commands/agents.py` | `border_style="yellow"` (lines 149, 358) |
| `cyan` | `emdx/commands/agents.py` | `border_style="cyan"` (lines 612, 673) |
| `cyan` | `emdx/commands/workflows.py` | Rich panel borders |
| `green`, `yellow`, `dim` | `emdx/commands/similarity.py` | Extensive Rich markup |

**Total Rich markup color instances: 471+** (not just the few listed in Section 3.5)

### 9.3 Theme API Verification Required

**CRITICAL: The proposed API needs verification against Textual 4.0 documentation.**

The analysis proposes:
```python
app.register_theme(theme)  # ⚠️ Unverified method name
app.theme = "name"         # ⚠️ Unverified property
```

**Action Required:** Before implementation, verify:
1. Exact `Theme` class constructor parameters
2. Method name for registering custom themes
3. Whether themes can be changed at runtime or only at startup
4. Import path: `from textual.theme import Theme` vs other location

### 9.4 Property Name Issue: `foreground` vs `text`

The theme definitions use `"foreground"` for text color:
```python
"foreground": "#E6EDF3",   # Used in proposed themes
```

But the codebase CSS uses `$text`:
```css
color: $text;              # Used in actual TCSS
```

**Action Required:** Verify if Textual's Theme object accepts `foreground` or `text` as the property name.

### 9.5 Rich Markup Colors Are NOT Theme-Aware

**MAJOR DESIGN ISSUE:** Rich markup like `[red]`, `[green]`, `[yellow]` uses hardcoded ANSI terminal colors. These do **not** automatically respect Textual theme colors.

**Implications:**
- Phase 3 ("Create theme-aware color helper") is more complex than described
- Cannot simply replace `[red]` with a variable - need wrapper functions
- 471+ instances across codebase need migration strategy

**Proposed Solution:**
```python
# Helper function to get theme-aware Rich color
def theme_color(color_name: str) -> str:
    """Map semantic color to Rich markup based on current theme."""
    theme = get_current_theme()
    color_map = {
        "error": theme.error,      # Returns hex like "#F85149"
        "success": theme.success,
        "warning": theme.warning,
    }
    return color_map.get(color_name, color_name)

# Usage:
f"[{theme_color('error')}]Error message[/]"
```

### 9.6 Missing Implementation Details

**Phase 3 gaps:**
- No code example for Rich color helper function
- No migration strategy for 471+ Rich markup instances
- No guidance on how to handle Rich `border_style` parameters

**Phase 4 gaps:**
- No explanation of how `markdown_config.py` integrates with theme system
- Missing code for reading theme preference from config

**Runtime concerns:**
- No details on UI refresh after theme change
- Missing explanation of Textual's theme reactivity

### 9.7 Terminal Compatibility Not Addressed

**Missing considerations:**
- 256-color terminal fallbacks
- True color (24-bit) detection
- Color palette limitations on older terminals
- Testing matrix for terminal emulators

### 9.8 Summary of Required Fixes

| Issue | Severity | Fix Required |
|-------|----------|--------------|
| Verify Textual Theme API | **HIGH** | Check docs before implementation |
| Rich markup not theme-aware | **HIGH** | Design helper function system |
| `foreground` vs `text` property | **MEDIUM** | Verify correct property name |
| 471+ Rich color instances | **MEDIUM** | Create migration plan |
| Incorrect usage counts | **LOW** | Already corrected above |
| Missing Phase 3-4 details | **MEDIUM** | Add implementation examples |
| Terminal compatibility | **LOW** | Add to Phase 6 testing |

---

## 10. Next Steps

Before implementation:
1. **Verify Textual 4.0 Theme API** - Read official docs or source code
2. **Design Rich color helper** - Create wrapper for theme-aware markup
3. **Audit all Rich markup** - Full list of files needing migration
4. **Prototype theme switching** - Test API before full implementation
