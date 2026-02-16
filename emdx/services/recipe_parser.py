"""Recipe markdown parser for structured multi-step recipes.

Recipes are markdown documents with optional YAML frontmatter and numbered
step headers. This parser extracts inputs, steps, and per-step annotations.

Format:
    ---
    inputs:
      - name: target
        description: What to analyze
        required: true
      - name: severity
        default: medium
    tags: [security, audit]
    ---

    # Security Audit

    ## Step 1: Scan
    Find all endpoints in {{target}} and scan for vulnerabilities
    at {{severity}} level and above.

    ## Step 2: Triage
    Prioritize findings by exploitability and impact.

    ## Step 3: Fix [--pr, --timeout 1800]
    Create fixes for each high-priority finding.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml


@dataclass
class RecipeInput:
    """A declared input for a recipe."""

    name: str
    description: str = ""
    required: bool = False
    default: str | None = None


@dataclass
class RecipeStep:
    """A single step in a recipe."""

    number: int
    name: str
    prompt: str
    flags: dict[str, str | bool | int] = field(default_factory=dict)


@dataclass
class Recipe:
    """A parsed recipe with metadata, inputs, and steps."""

    title: str
    inputs: list[RecipeInput] = field(default_factory=list)
    steps: list[RecipeStep] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    raw_content: str = ""


class RecipeParseError(Exception):
    """Raised when recipe markdown cannot be parsed."""


# Regex for frontmatter block
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Regex for step headers: "## Step N: Name" or "## Step N: Name [--flags]"
_STEP_RE = re.compile(
    r"^##\s+[Ss]tep\s+(\d+)\s*:\s*(.+?)$",
    re.MULTILINE,
)

# Regex for annotation brackets at end of step name: [--pr, --timeout 1800]
_ANNOTATION_RE = re.compile(r"\[([^\]]+)\]\s*$")

# Regex for {{variable}} placeholders
_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def parse_recipe(content: str) -> Recipe:
    """Parse a recipe from markdown content.

    Returns a Recipe with extracted frontmatter, title, and steps.
    A document without step headers is treated as a simple (single-step) recipe.
    """
    raw_content = content
    body = content
    frontmatter: dict = {}

    # Extract frontmatter
    fm_match = _FRONTMATTER_RE.match(content)
    if fm_match:
        try:
            frontmatter = yaml.safe_load(fm_match.group(1)) or {}
        except yaml.YAMLError as e:
            raise RecipeParseError(f"Invalid YAML frontmatter: {e}") from e
        body = content[fm_match.end():]

    # Parse inputs from frontmatter
    inputs = _parse_inputs(frontmatter.get("inputs", []))

    # Parse tags from frontmatter
    tags = frontmatter.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]

    # Extract title from first # heading
    title = _extract_title(body)

    # Parse steps
    steps = _parse_steps(body)

    return Recipe(
        title=title,
        inputs=inputs,
        steps=steps,
        tags=tags,
        raw_content=raw_content,
    )


def is_structured_recipe(content: str) -> bool:
    """Check if content has step headers (i.e., is a multi-step recipe)."""
    return bool(_STEP_RE.search(content))


def validate_inputs(
    recipe: Recipe, provided: dict[str, str]
) -> list[str]:
    """Validate that required inputs are provided.

    Returns list of error messages (empty = valid).
    """
    errors = []
    for inp in recipe.inputs:
        if inp.required and inp.name not in provided:
            if inp.default is None:
                errors.append(f"Required input '{inp.name}' not provided")
    return errors


def substitute(text: str, values: dict[str, str]) -> str:
    """Replace {{var}} placeholders with values."""
    def replacer(match: re.Match) -> str:
        name = match.group(1)
        return values.get(name, match.group(0))

    return _VAR_RE.sub(replacer, text)


def resolve_inputs(
    recipe: Recipe, provided: dict[str, str]
) -> dict[str, str]:
    """Build final input values by merging provided values with defaults."""
    values: dict[str, str] = {}
    for inp in recipe.inputs:
        if inp.name in provided:
            values[inp.name] = provided[inp.name]
        elif inp.default is not None:
            values[inp.name] = inp.default
    return values


def _parse_inputs(raw: list | None) -> list[RecipeInput]:
    """Parse input declarations from frontmatter."""
    if not raw or not isinstance(raw, list):
        return []

    inputs = []
    for item in raw:
        if isinstance(item, str):
            inputs.append(RecipeInput(name=item))
        elif isinstance(item, dict):
            inputs.append(RecipeInput(
                name=item.get("name", ""),
                description=item.get("description", ""),
                required=bool(item.get("required", False)),
                default=str(item["default"]) if "default" in item else None,
            ))
    return inputs


def _extract_title(body: str) -> str:
    """Extract title from first # heading in body."""
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line.lstrip("# ").strip()
    return "Untitled Recipe"


def _parse_steps(body: str) -> list[RecipeStep]:
    """Parse ## Step N: headers and their content from body."""
    matches = list(_STEP_RE.finditer(body))
    if not matches:
        return []

    steps = []
    for i, match in enumerate(matches):
        number = int(match.group(1))
        raw_name = match.group(2).strip()

        # Extract annotations from name
        flags = _parse_annotations(raw_name)
        name = _ANNOTATION_RE.sub("", raw_name).strip()

        # Extract prompt content between this step and the next
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        prompt = body[start:end].strip()

        steps.append(RecipeStep(
            number=number,
            name=name,
            prompt=prompt,
            flags=flags,
        ))

    return steps


def _parse_annotations(name: str) -> dict[str, str | bool | int]:
    """Parse [--flag, --key value] annotations from step name."""
    flags: dict[str, str | bool | int] = {}
    ann_match = _ANNOTATION_RE.search(name)
    if not ann_match:
        return flags

    raw = ann_match.group(1)
    # Split on commas, then parse each flag
    parts = [p.strip() for p in raw.split(",")]
    for part in parts:
        tokens = part.split()
        if not tokens:
            continue
        flag = tokens[0].lstrip("-")
        if len(tokens) > 1:
            # --flag value
            try:
                flags[flag] = int(tokens[1])
            except ValueError:
                flags[flag] = tokens[1]
        else:
            # --flag (boolean)
            flags[flag] = True

    return flags
