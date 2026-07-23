"""Prompt template system for smart execution."""

from pathlib import Path


def load_prompt_template(template_name: str) -> str:
    """Load a prompt template by name."""
    template_path = Path(__file__).parent / f"{template_name}.md"
    if not template_path.exists():
        raise ValueError(f"Prompt template '{template_name}' not found")
    return template_path.read_text()


