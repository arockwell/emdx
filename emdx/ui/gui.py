"""
GUI interface for emdx - seamless textual browser with nvim integration
"""

from typing import Optional

import typer

from emdx.utils.output import console

app = typer.Typer()


@app.command()
def gui(
    theme: Optional[str] = typer.Option(
        None,
        "--theme",
        "-t",
        help="Theme to use (emdx-dark, emdx-light, emdx-nord, emdx-solarized-dark, emdx-solarized-light)",
    ),
):
    """Seamless TUI browser with zero-flash nvim integration."""
    from emdx.ui.nvim_wrapper import run_textual_with_nvim_wrapper

    try:
        run_textual_with_nvim_wrapper(theme=theme)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1) from e
