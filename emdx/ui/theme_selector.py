"""
Theme selector modal for EMDX TUI.

Provides a modal dialog for selecting and previewing themes.
"""

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static, Label, OptionList
from textual.widgets.option_list import Option

from emdx.config.ui_config import get_theme, set_theme
from emdx.ui.themes import get_theme_display_info


class ThemeSelectorScreen(ModalScreen):
    """Modal screen for selecting a theme."""

    CSS = """
    ThemeSelectorScreen {
        align: center middle;
    }

    #theme-selector-container {
        width: 60;
        height: auto;
        max-height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }

    #theme-selector-title {
        text-align: center;
        text-style: bold;
        padding-bottom: 1;
        color: $text;
    }

    #theme-list {
        height: auto;
        max-height: 20;
        margin-bottom: 1;
        border: solid $primary;
    }

    #theme-description {
        height: 3;
        padding: 1;
        background: $boost;
        color: $text-muted;
        text-align: center;
    }

    #theme-instructions {
        margin-top: 1;
        text-align: center;
        color: $text-muted;
    }
    """

    def __init__(self):
        super().__init__()
        self.themes = get_theme_display_info()
        self.current_theme = get_theme()

    def compose(self) -> ComposeResult:
        with Vertical(id="theme-selector-container"):
            yield Label("🎨 Select Theme", id="theme-selector-title")

            # Theme list
            option_list = OptionList(id="theme-list")
            yield option_list

            # Description panel
            yield Static("", id="theme-description")

            # Instructions
            yield Static(
                "j/k Navigate • Enter Select • Esc Cancel",
                id="theme-instructions"
            )

    def on_mount(self) -> None:
        """Populate the theme list."""
        option_list = self.query_one("#theme-list", OptionList)

        # Add themes to the list
        for theme_info in self.themes:
            name = theme_info["name"]
            display = theme_info["display_name"]

            # Mark current theme
            if name == self.current_theme:
                display = f"● {display} (current)"
            else:
                display = f"  {display}"

            option_list.add_option(Option(display, id=name))

        # Highlight current theme
        current_idx = next(
            (i for i, t in enumerate(self.themes) if t["name"] == self.current_theme),
            0
        )
        option_list.highlighted = current_idx

        # Update description
        self._update_description(current_idx)

        # Focus the list
        option_list.focus()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Update description when option is highlighted."""
        if event.option and event.option.id:
            idx = next(
                (i for i, t in enumerate(self.themes) if t["name"] == event.option.id),
                0
            )
            self._update_description(idx)

    def _update_description(self, idx: int) -> None:
        """Update the description panel."""
        if 0 <= idx < len(self.themes):
            theme_info = self.themes[idx]
            desc = self.query_one("#theme-description", Static)
            desc.update(theme_info["description"])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle theme selection."""
        if event.option and event.option.id:
            self._select_theme(event.option.id)

    def _select_theme(self, theme_name: str) -> None:
        """Apply and save the selected theme."""
        # Apply theme
        self.app.theme = theme_name

        # Save preference
        set_theme(theme_name)

        # Close modal
        self.dismiss(theme_name)

    def on_key(self, event: events.Key) -> None:
        """Handle key events."""
        if event.key == "escape":
            self.dismiss(None)
        elif event.key == "enter":
            option_list = self.query_one("#theme-list", OptionList)
            if option_list.highlighted is not None:
                option = option_list.get_option_at_index(option_list.highlighted)
                if option and option.id:
                    self._select_theme(option.id)
        elif event.key == "j" or event.key == "down":
            option_list = self.query_one("#theme-list", OptionList)
            option_list.action_cursor_down()
            event.stop()
        elif event.key == "k" or event.key == "up":
            option_list = self.query_one("#theme-list", OptionList)
            option_list.action_cursor_up()
            event.stop()
