"""Tests for recipe executor - step execution, piping, validation."""

from unittest.mock import MagicMock, patch

from emdx.services.recipe_executor import RecipeResult, execute_recipe
from emdx.services.recipe_parser import Recipe, RecipeInput, RecipeStep


def _make_recipe(
    steps: list[RecipeStep] | None = None,
    inputs: list[RecipeInput] | None = None,
    title: str = "Test Recipe",
    tags: list[str] | None = None,
) -> Recipe:
    """Helper to build a Recipe for testing."""
    return Recipe(
        title=title,
        inputs=inputs or [],
        steps=steps or [],
        tags=tags or [],
        raw_content="",
    )


def _make_single_result(doc_id: int | None = 1, pr_url: str | None = None):
    """Helper to build a mock SingleResult."""
    result = MagicMock()
    result.doc_id = doc_id
    result.pr_url = pr_url
    result.success = doc_id is not None
    return result


class TestExecuteRecipeValidation:
    """Tests for input validation in execute_recipe."""

    @patch("emdx.services.recipe_executor._execute_steps")
    def test_missing_required_input_fails(self, mock_steps):
        recipe = _make_recipe(
            inputs=[RecipeInput(name="target", required=True)],
            steps=[RecipeStep(number=1, name="S", prompt="p")],
        )
        result = execute_recipe(recipe, inputs={})
        assert not result.success
        assert "target" in (result.error or "")
        mock_steps.assert_not_called()

    @patch("emdx.services.recipe_executor._execute_steps")
    def test_valid_inputs_proceed(self, mock_steps):
        mock_steps.return_value = RecipeResult(success=True)
        recipe = _make_recipe(
            inputs=[RecipeInput(name="target", required=True)],
            steps=[RecipeStep(number=1, name="S", prompt="p")],
        )
        result = execute_recipe(recipe, inputs={"target": "api"})
        assert result.success
        mock_steps.assert_called_once()


class TestExecuteSteps:
    """Tests for _execute_steps (the step loop)."""

    @patch("emdx.services.recipe_executor.get_document")
    @patch("emdx.commands.delegate._run_single")
    def test_single_step_success(self, mock_run_single, mock_get_doc):
        mock_run_single.return_value = _make_single_result(doc_id=10)
        mock_get_doc.return_value = {"content": "step 1 output"}

        recipe = _make_recipe(
            steps=[RecipeStep(number=1, name="Scan", prompt="Do the scan")],
        )
        result = execute_recipe(recipe, quiet=True)
        assert result.success
        assert len(result.steps) == 1
        assert result.steps[0].doc_id == 10

    @patch("emdx.services.recipe_executor.get_document")
    @patch("emdx.commands.delegate._run_single")
    def test_multi_step_pipes_output(self, mock_run_single, mock_get_doc):
        mock_run_single.side_effect = [
            _make_single_result(doc_id=10),
            _make_single_result(doc_id=11),
        ]
        mock_get_doc.side_effect = [
            {"content": "step 1 output"},
            {"content": "step 2 output"},
        ]

        recipe = _make_recipe(
            steps=[
                RecipeStep(number=1, name="Scan", prompt="Do scan"),
                RecipeStep(number=2, name="Fix", prompt="Fix issues"),
            ],
        )
        result = execute_recipe(recipe, quiet=True)
        assert result.success
        assert len(result.steps) == 2

        # Verify step 2 received step 1's output
        call_args = mock_run_single.call_args_list[1]
        prompt = call_args.kwargs.get("prompt") or call_args[1].get("prompt", "")
        if not prompt:
            prompt = call_args[0][0] if call_args[0] else ""
        assert "step 1 output" in prompt

    @patch("emdx.services.recipe_executor.get_document")
    @patch("emdx.commands.delegate._run_single")
    def test_step_failure_stops_execution(self, mock_run_single, mock_get_doc):
        mock_run_single.side_effect = [
            _make_single_result(doc_id=10),
            _make_single_result(doc_id=None),  # Step 2 fails
        ]
        mock_get_doc.return_value = {"content": "step 1 output"}

        recipe = _make_recipe(
            steps=[
                RecipeStep(number=1, name="Scan", prompt="Do scan"),
                RecipeStep(number=2, name="Fix", prompt="Fix issues"),
                RecipeStep(number=3, name="Report", prompt="Write report"),
            ],
        )
        result = execute_recipe(recipe, quiet=True)
        assert not result.success
        assert result.failed_at == 2
        assert len(result.steps) == 2
        # Step 3 should not have been executed
        assert mock_run_single.call_count == 2

    @patch("emdx.utils.git.cleanup_worktree")
    @patch(
        "emdx.utils.git.create_worktree",
        return_value=("/tmp/wt", "delegate/test-branch"),
    )
    @patch("emdx.services.recipe_executor.get_document")
    @patch("emdx.commands.delegate._run_single")
    def test_pr_url_captured(self, mock_run_single, mock_get_doc, mock_create_wt, mock_cleanup_wt):
        mock_run_single.return_value = _make_single_result(
            doc_id=10, pr_url="https://github.com/test/repo/pull/1"
        )
        mock_get_doc.return_value = {"content": "done"}

        recipe = _make_recipe(
            steps=[
                RecipeStep(
                    number=1,
                    name="Fix",
                    prompt="Fix it",
                    flags={"pr": True},
                )
            ],
        )
        result = execute_recipe(recipe, quiet=True)
        assert result.success
        assert result.pr_url == "https://github.com/test/repo/pull/1"

    @patch("emdx.services.recipe_executor.get_document")
    @patch("emdx.commands.delegate._run_single")
    def test_variable_substitution(self, mock_run_single, mock_get_doc):
        mock_run_single.return_value = _make_single_result(doc_id=10)
        mock_get_doc.return_value = {"content": "done"}

        recipe = _make_recipe(
            inputs=[
                RecipeInput(name="target", required=True),
                RecipeInput(name="severity", default="medium"),
            ],
            steps=[
                RecipeStep(
                    number=1,
                    name="Scan",
                    prompt="Scan {{target}} at {{severity}} level",
                )
            ],
        )
        result = execute_recipe(recipe, inputs={"target": "auth-module"}, quiet=True)
        assert result.success

        # Verify substitution happened
        call_args = mock_run_single.call_args
        prompt = call_args.kwargs.get("prompt") or call_args[0][0]
        assert "auth-module" in prompt
        assert "medium" in prompt  # default value

    @patch("emdx.utils.git.cleanup_worktree")
    @patch(
        "emdx.utils.git.create_worktree",
        return_value=("/tmp/wt", "delegate/test-branch"),
    )
    @patch("emdx.services.recipe_executor.get_document")
    @patch("emdx.commands.delegate._run_single")
    def test_step_flags_passed_through(
        self, mock_run_single, mock_get_doc, mock_create_wt, mock_cleanup_wt
    ):
        mock_run_single.return_value = _make_single_result(doc_id=10)
        mock_get_doc.return_value = {"content": "done"}

        recipe = _make_recipe(
            steps=[
                RecipeStep(
                    number=1,
                    name="Fix",
                    prompt="Fix it",
                    flags={"pr": True, "timeout": 1800},
                )
            ],
        )
        result = execute_recipe(recipe, quiet=True)
        assert result.success

        call_kwargs = mock_run_single.call_args.kwargs
        assert call_kwargs.get("pr") is True
