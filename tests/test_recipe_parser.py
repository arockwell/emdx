"""Tests for recipe parser - frontmatter, steps, annotations, substitution."""

import pytest

from emdx.services.recipe_parser import (
    RecipeParseError,
    is_structured_recipe,
    parse_recipe,
    resolve_inputs,
    substitute,
    validate_inputs,
)


class TestParseRecipe:
    """Tests for parse_recipe function."""

    def test_simple_recipe_no_steps(self):
        content = "# My Recipe\n\nJust do the thing."
        recipe = parse_recipe(content)
        assert recipe.title == "My Recipe"
        assert recipe.steps == []
        assert recipe.inputs == []

    def test_structured_recipe_with_steps(self):
        content = (
            "# Security Audit\n\n"
            "## Step 1: Scan\nScan all endpoints.\n\n"
            "## Step 2: Triage\nPrioritize findings.\n\n"
            "## Step 3: Fix\nCreate fixes.\n"
        )
        recipe = parse_recipe(content)
        assert recipe.title == "Security Audit"
        assert len(recipe.steps) == 3
        assert recipe.steps[0].number == 1
        assert recipe.steps[0].name == "Scan"
        assert "Scan all endpoints" in recipe.steps[0].prompt
        assert recipe.steps[1].number == 2
        assert recipe.steps[1].name == "Triage"
        assert recipe.steps[2].number == 3
        assert recipe.steps[2].name == "Fix"

    def test_frontmatter_parsing(self):
        content = (
            "---\n"
            "inputs:\n"
            "  - name: target\n"
            "    description: What to scan\n"
            "    required: true\n"
            "  - name: severity\n"
            "    default: medium\n"
            "tags: [security, audit]\n"
            "---\n\n"
            "# Audit\n\n"
            "## Step 1: Scan\nScan {{target}}.\n"
        )
        recipe = parse_recipe(content)
        assert len(recipe.inputs) == 2
        assert recipe.inputs[0].name == "target"
        assert recipe.inputs[0].required is True
        assert recipe.inputs[0].description == "What to scan"
        assert recipe.inputs[1].name == "severity"
        assert recipe.inputs[1].default == "medium"
        assert recipe.inputs[1].required is False
        assert recipe.tags == ["security", "audit"]

    def test_frontmatter_tags_as_string(self):
        content = "---\ntags: security, audit\n---\n\n# Audit\n"
        recipe = parse_recipe(content)
        assert recipe.tags == ["security", "audit"]

    def test_step_annotations(self):
        content = (
            "# Recipe\n\n"
            "## Step 1: Scan\nDo scan.\n\n"
            "## Step 2: Fix [--pr, --timeout 1800]\nCreate fixes.\n"
        )
        recipe = parse_recipe(content)
        assert recipe.steps[0].flags == {}
        assert recipe.steps[1].flags == {"pr": True, "timeout": 1800}
        assert recipe.steps[1].name == "Fix"

    def test_step_annotation_single_flag(self):
        content = "# R\n\n## Step 1: Deploy [--pr]\nDeploy it.\n"
        recipe = parse_recipe(content)
        assert recipe.steps[0].flags == {"pr": True}

    def test_no_title_fallback(self):
        content = "## Step 1: Scan\nScan stuff.\n"
        recipe = parse_recipe(content)
        assert recipe.title == "Untitled Recipe"

    def test_invalid_yaml_frontmatter(self):
        content = "---\ninputs: [unclosed\n---\n\n# R\n"
        with pytest.raises(RecipeParseError, match="Invalid YAML"):
            parse_recipe(content)

    def test_inputs_as_simple_strings(self):
        content = "---\ninputs:\n  - target\n  - severity\n---\n\n# R\n"
        recipe = parse_recipe(content)
        assert len(recipe.inputs) == 2
        assert recipe.inputs[0].name == "target"
        assert recipe.inputs[1].name == "severity"

    def test_empty_content(self):
        recipe = parse_recipe("")
        assert recipe.title == "Untitled Recipe"
        assert recipe.steps == []

    def test_step_prompt_includes_content_between_headers(self):
        content = (
            "# R\n\n"
            "## Step 1: First\n"
            "Line one.\nLine two.\n\nParagraph two.\n\n"
            "## Step 2: Second\nNext step.\n"
        )
        recipe = parse_recipe(content)
        assert "Line one." in recipe.steps[0].prompt
        assert "Paragraph two." in recipe.steps[0].prompt
        assert "Next step." in recipe.steps[1].prompt

    def test_raw_content_preserved(self):
        content = "---\ntags: [a]\n---\n\n# R\n\n## Step 1: S\nDo it.\n"
        recipe = parse_recipe(content)
        assert recipe.raw_content == content


class TestIsStructuredRecipe:
    """Tests for is_structured_recipe function."""

    def test_with_steps(self):
        assert is_structured_recipe("## Step 1: Scan\nDo it.\n")

    def test_without_steps(self):
        assert not is_structured_recipe("# Just a document\n\nNo steps here.")

    def test_case_insensitive_step(self):
        assert is_structured_recipe("## step 1: Scan\nDo it.\n")


class TestValidateInputs:
    """Tests for validate_inputs function."""

    def test_all_required_provided(self):
        content = "---\ninputs:\n  - name: target\n    required: true\n---\n\n# R\n"
        recipe = parse_recipe(content)
        errors = validate_inputs(recipe, {"target": "api"})
        assert errors == []

    def test_missing_required(self):
        content = "---\ninputs:\n  - name: target\n    required: true\n---\n\n# R\n"
        recipe = parse_recipe(content)
        errors = validate_inputs(recipe, {})
        assert len(errors) == 1
        assert "target" in errors[0]

    def test_required_with_default_is_ok(self):
        content = (
            "---\ninputs:\n"
            "  - name: severity\n    required: true\n    default: medium\n"
            "---\n\n# R\n"
        )
        recipe = parse_recipe(content)
        errors = validate_inputs(recipe, {})
        assert errors == []

    def test_optional_not_provided(self):
        content = "---\ninputs:\n  - name: severity\n    default: medium\n---\n\n# R\n"
        recipe = parse_recipe(content)
        errors = validate_inputs(recipe, {})
        assert errors == []


class TestSubstitute:
    """Tests for substitute function."""

    def test_simple_substitution(self):
        assert substitute("Scan {{target}}", {"target": "api"}) == "Scan api"

    def test_multiple_vars(self):
        result = substitute("{{a}} and {{b}}", {"a": "one", "b": "two"})
        assert result == "one and two"

    def test_missing_var_left_as_is(self):
        assert substitute("{{missing}}", {}) == "{{missing}}"

    def test_no_vars(self):
        assert substitute("no vars here", {"a": "1"}) == "no vars here"


class TestResolveInputs:
    """Tests for resolve_inputs function."""

    def test_provided_overrides_default(self):
        content = "---\ninputs:\n  - name: severity\n    default: medium\n---\n\n# R\n"
        recipe = parse_recipe(content)
        values = resolve_inputs(recipe, {"severity": "high"})
        assert values == {"severity": "high"}

    def test_default_used_when_not_provided(self):
        content = "---\ninputs:\n  - name: severity\n    default: medium\n---\n\n# R\n"
        recipe = parse_recipe(content)
        values = resolve_inputs(recipe, {})
        assert values == {"severity": "medium"}

    def test_no_default_no_value(self):
        content = "---\ninputs:\n  - name: target\n    required: true\n---\n\n# R\n"
        recipe = parse_recipe(content)
        values = resolve_inputs(recipe, {})
        assert values == {}
