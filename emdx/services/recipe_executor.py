"""Recipe executor - runs parsed recipes step by step.

Executes recipe steps sequentially, piping each step's output as context
to the next. Uses delegate's _run_single for actual execution.

The executor is thin: it validates inputs, substitutes variables,
orchestrates the step loop, and reports results. All heavy lifting
(Claude execution, output persistence, worktree management) is
handled by delegate's existing infrastructure.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

from ..database.documents import get_document
from .recipe_parser import Recipe, resolve_inputs, substitute, validate_inputs


@dataclass
class StepResult:
    """Result of executing a single recipe step."""

    step_number: int
    step_name: str
    doc_id: int | None = None
    pr_url: str | None = None
    success: bool = True
    error: str | None = None


@dataclass
class RecipeResult:
    """Result of executing a full recipe."""

    success: bool
    steps: list[StepResult] = field(default_factory=list)
    failed_at: int | None = None
    pr_url: str | None = None
    error: str | None = None


def execute_recipe(
    recipe: Recipe,
    inputs: dict[str, str] | None = None,
    *,
    model: str | None = None,
    quiet: bool = False,
    worktree: bool = False,
    base_branch: str = "main",
    tags: list[str] | None = None,
    parent_doc_id: int | None = None,
) -> RecipeResult:
    """Execute a parsed recipe step by step.

    Each step runs via delegate's _run_single. Output from each step is
    piped as context to the next step.

    Args:
        recipe: Parsed Recipe object
        inputs: Values for declared recipe inputs
        model: Model override
        quiet: Suppress metadata output
        worktree: Run in isolated git worktree
        base_branch: Base branch for worktree
        tags: Additional tags for output documents
        parent_doc_id: Parent document ID for lineage tracking

    Returns:
        RecipeResult with step-by-step results
    """
    from ..commands.delegate import _run_single

    # Validate inputs
    provided = inputs or {}
    errors = validate_inputs(recipe, provided)
    if errors:
        return RecipeResult(
            success=False,
            error=f"Input validation failed: {'; '.join(errors)}",
        )

    # Resolve inputs (merge provided with defaults)
    values = resolve_inputs(recipe, provided)

    # Build tags
    all_tags = list(tags or [])
    all_tags.extend(recipe.tags)
    if "recipe-output" not in all_tags:
        all_tags.append("recipe-output")

    # Setup worktree if needed (shared across all steps)
    worktree_path: str | None = None
    worktree_branch: str | None = None

    # Check if any step needs --pr or --branch
    any_pr = any(s.flags.get("pr") for s in recipe.steps)
    any_branch = any(s.flags.get("branch") for s in recipe.steps)
    use_worktree = worktree or any_pr or any_branch

    if use_worktree:
        from ..utils.git import create_worktree

        try:
            task_title = recipe.title or "recipe execution"
            worktree_path, worktree_branch = create_worktree(base_branch, task_title=task_title)
            if not quiet:
                sys.stderr.write(f"recipe: worktree created at {worktree_path}\n")
        except Exception as e:
            return RecipeResult(
                success=False,
                error=f"Failed to create worktree: {e}",
            )

    try:
        return _execute_steps(
            recipe=recipe,
            values=values,
            tags=all_tags,
            model=model,
            quiet=quiet,
            worktree_path=worktree_path,
            worktree_branch=worktree_branch,
            parent_doc_id=parent_doc_id,
            run_single=_run_single,
        )
    finally:
        # Clean up worktree unless --branch was used (needs local branch)
        if worktree_path and not any_branch:
            from ..utils.git import cleanup_worktree

            if not quiet:
                sys.stderr.write(f"recipe: cleaning up worktree {worktree_path}\n")
            try:
                cleanup_worktree(worktree_path)
            except Exception as cleanup_err:
                # Log cleanup failure but don't mask original exception
                sys.stderr.write(f"recipe: worktree cleanup failed: {cleanup_err}\n")


def _execute_steps(
    recipe: Recipe,
    values: dict[str, str],
    tags: list[str],
    model: str | None,
    quiet: bool,
    worktree_path: str | None,
    worktree_branch: str | None,
    parent_doc_id: int | None,
    run_single: Any,
) -> RecipeResult:
    """Execute recipe steps sequentially, piping output forward."""
    step_results: list[StepResult] = []
    previous_output = ""
    pr_url = None
    total = len(recipe.steps)

    for step in recipe.steps:
        step_num = step.number

        # Substitute variables in step prompt
        prompt = substitute(step.prompt, values)

        # Build full prompt with previous context
        if previous_output:
            full_prompt = (
                f"Previous step output:\n\n{previous_output}\n\n---\n\n"
                f"Your task (step {step_num}/{total}): {prompt}"
            )
        else:
            full_prompt = f"Your task (step {step_num}/{total}): {prompt}"

        if not quiet:
            sys.stdout.write(f"\n=== Step {step_num}/{total}: {step.name} ===\n")

        # Resolve per-step flags
        step_pr = bool(step.flags.get("pr", False))
        step_branch = bool(step.flags.get("branch", False))
        step_timeout_raw = step.flags.get("timeout")
        step_timeout = int(step_timeout_raw) if step_timeout_raw is not None else None

        step_title = f"{recipe.title} [step {step_num}/{total}: {step.name}]"

        result = run_single(
            prompt=full_prompt,
            tags=tags,
            title=step_title,
            model=model,
            quiet=quiet,
            pr=step_pr,
            branch=step_branch,
            pr_branch=worktree_branch if (step_pr or step_branch) else None,
            working_dir=worktree_path,
            source_doc_id=parent_doc_id,
            seq=step_num,
            timeout=step_timeout,
        )

        step_result = StepResult(
            step_number=step_num,
            step_name=step.name,
            doc_id=result.doc_id,
            pr_url=result.pr_url,
            success=result.doc_id is not None,
        )

        if result.pr_url:
            pr_url = result.pr_url

        step_results.append(step_result)

        if result.doc_id is None:
            step_result.success = False
            step_result.error = "Step produced no output"
            if not quiet:
                sys.stderr.write(f"recipe: failed at step {step_num}/{total}: {step.name}\n")
            return RecipeResult(
                success=False,
                steps=step_results,
                failed_at=step_num,
                pr_url=pr_url,
                error=f"Failed at step {step_num}: {step.name}",
            )

        # Read output for next step
        doc = get_document(result.doc_id)
        if doc:
            previous_output = doc.get("content", "")

    # All steps completed
    if not quiet and step_results:
        ids = [str(s.doc_id) for s in step_results if s.doc_id]
        sys.stderr.write(f"recipe: completed {total} steps, doc_ids:{','.join(ids)}\n")
        if pr_url:
            sys.stderr.write(f"recipe: PR created: {pr_url}\n")

    return RecipeResult(
        success=True,
        steps=step_results,
        pr_url=pr_url,
    )
