"""
GUI interface for emdx - seamless textual browser
"""


import typer

from emdx.utils.output import console


def gui(
    theme: str | None = typer.Option(
        None,
        "--theme",
        "-t",
        help="Theme to use (emdx-dark, emdx-light, emdx-nord, emdx-solarized-dark, emdx-solarized-light)",  # noqa: E501
    ),
):
    """TUI browser for the EMDX knowledge base."""
    from emdx.ui.run_browser import run_browser

    try:
        run_browser(theme=theme)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1) from e
