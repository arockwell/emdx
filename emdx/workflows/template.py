"""Template resolution for workflow prompts.

Handles {{variable}} substitution in workflow prompts and configuration.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from emdx.workflows.tasks import TaskContext

logger = logging.getLogger(__name__)

# Deprecated variable aliases: old_name -> new_name
# These provide backward compatibility while migrating to unified {{item}} syntax
DEPRECATED_ALIASES: Dict[str, str] = {
    'task': 'item',
    'task_title': 'item_title',
    'task_id': 'item_id',
    'total': 'item_count',  # Documented but not implemented before
    'count': 'item_count',  # Alias for synthesis context
}

# Track which deprecation warnings have been emitted (to avoid spam)
_emitted_warnings: Set[str] = set()


def _resolve_with_aliases(
    var_name: str,
    context: Dict[str, Any],
    warn_deprecated: bool = True,
) -> tuple[Any, bool]:
    """Resolve a variable name, checking aliases if not found directly.

    Args:
        var_name: The variable name to resolve
        context: The context dictionary
        warn_deprecated: Whether to emit deprecation warnings

    Returns:
        Tuple of (resolved_value, found) where found indicates if a value was found
    """
    # First, check if the variable exists directly in context
    if var_name in context:
        return context[var_name], True

    # Check if this is a deprecated alias
    if var_name in DEPRECATED_ALIASES:
        new_name = DEPRECATED_ALIASES[var_name]

        # Emit deprecation warning (once per variable name)
        if warn_deprecated and var_name not in _emitted_warnings:
            _emitted_warnings.add(var_name)
            logger.warning(
                "DEPRECATION: {{%s}} is deprecated. Use {{%s}} instead.",
                var_name,
                new_name,
            )

        # Try to resolve using the new name
        if new_name in context:
            return context[new_name], True

    return '', False


def resolve_template(
    template: Optional[str],
    context: Dict[str, Any],
    warn_deprecated: bool = True,
) -> str:
    """Resolve {{variable}} templates in a string.

    Supports:
    - Simple variables: {{input}} -> context['input']
    - Dotted access: {{stage_name.output}} -> context['stage_name.output']
    - Indexed access: {{all_prev[0]}} -> context['all_prev'][0]
    - Deprecated aliases: {{task}} -> context['item'] (with warning)

    Missing variables become empty strings.

    Args:
        template: String with {{variable}} placeholders
        context: Dictionary of values to substitute
        warn_deprecated: Whether to emit deprecation warnings for old variable names

    Returns:
        Resolved string with all placeholders replaced
    """
    if not template:
        return ""

    result = template

    # Handle indexed access like {{all_prev[0]}}
    indexed_pattern = r'\{\{(\w+)\[(\d+)\]\}\}'
    for match in re.finditer(indexed_pattern, template):
        var_name = match.group(1)
        index = int(match.group(2))

        # Resolve with alias support
        value, found = _resolve_with_aliases(var_name, context, warn_deprecated)
        if found and isinstance(value, list):
            if index < len(value):
                result = result.replace(match.group(0), str(value[index]))
            else:
                result = result.replace(match.group(0), '')
        else:
            result = result.replace(match.group(0), '')

    # Handle simple variables like {{input}} and dotted like {{stage.output}}
    simple_pattern = r'\{\{(\w+(?:\.\w+)*)\}\}'
    for match in re.finditer(simple_pattern, result):
        var_name = match.group(1)

        # Resolve with alias support
        value, _ = _resolve_with_aliases(var_name, context, warn_deprecated)
        result = result.replace(match.group(0), str(value))

    return result


def expand_tasks_to_prompts(
    prompt_template: str,
    tasks: List["TaskContext"],
    warn_deprecated: bool = True,
) -> List[str]:
    """Expand a prompt template with a list of tasks/items.

    Given a prompt template with {{item}}/{{task}} placeholders,
    generates one prompt per task. Supports both new {{item}} syntax
    and deprecated {{task}} syntax for backward compatibility.

    Supported placeholders:
    - {{item}} / {{task}} (deprecated) - The item content
    - {{item_title}} / {{task_title}} (deprecated) - The item title (if from document)
    - {{item_id}} / {{task_id}} (deprecated) - The item ID (if from document)
    - {{item_index}} - Zero-based index in the list
    - {{item_count}} / {{total}} (deprecated) - Total number of items

    Args:
        prompt_template: Template string with item/task placeholders
        tasks: List of resolved task contexts (from tasks.resolve_tasks)
        warn_deprecated: Whether to emit deprecation warnings for old variable names

    Returns:
        List of expanded prompts, one per task
    """
    prompts = []
    total_count = len(tasks)

    for index, task_ctx in enumerate(tasks):
        # Build context with unified naming (item-based)
        context = {
            'item': task_ctx.content,
            'item_title': task_ctx.title,
            'item_id': str(task_ctx.id) if task_ctx.id else '',
            'item_index': index,
            'item_count': total_count,
        }

        # Use resolve_template for full alias and deprecation support
        prompt = resolve_template(prompt_template, context, warn_deprecated)
        prompts.append(prompt)

    return prompts


def find_deprecated_variables(template: str) -> List[str]:
    """Find deprecated variables used in a template.

    Useful for validation, linting, or migration tooling.

    Args:
        template: Template string to analyze

    Returns:
        List of deprecated variable names found in the template
    """
    if not template:
        return []

    deprecated_found = []

    # Check indexed access patterns
    indexed_pattern = r'\{\{(\w+)\[\d+\]\}\}'
    for match in re.finditer(indexed_pattern, template):
        var_name = match.group(1)
        if var_name in DEPRECATED_ALIASES:
            deprecated_found.append(var_name)

    # Check simple variable patterns
    simple_pattern = r'\{\{(\w+(?:\.\w+)*)\}\}'
    for match in re.finditer(simple_pattern, template):
        var_name = match.group(1)
        if var_name in DEPRECATED_ALIASES:
            deprecated_found.append(var_name)

    return list(set(deprecated_found))  # Remove duplicates


def clear_deprecation_warnings() -> None:
    """Clear the set of emitted deprecation warnings.

    Useful for testing to ensure warnings are emitted on each test run.
    """
    global _emitted_warnings
    _emitted_warnings = set()
