"""
GUI interface for emdx - seamless textual browser with nvim integration
"""

import typer
from rich.console import Console

app = typer.Typer()
console = Console()


@app.command()
def gui():
    """Seamless TUI browser with zero-flash nvim integration."""
    from emdx.ui.nvim_wrapper import run_textual_with_nvim_wrapper

    try:
        run_textual_with_nvim_wrapper()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        console.print(f"❌ Error: {e}", style="red")
        raise typer.Exit(1) from e
