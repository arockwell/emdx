"""Built-in recipes for EMDX.

These recipes ship with emdx and can be installed into a user's
knowledge base with `emdx recipe install <name>`.
"""

from pathlib import Path

RECIPES_DIR = Path(__file__).parent


def list_builtin_recipes() -> list[Path]:
    """List all built-in recipe markdown files."""
    return sorted(RECIPES_DIR.glob("*.md"))


def get_builtin_recipe(name: str) -> Path | None:
    """Get a built-in recipe by name (without .md extension)."""
    path = RECIPES_DIR / f"{name}.md"
    return path if path.exists() else None
