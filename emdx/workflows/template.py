"""Template resolution for workflow prompts.

Handles {{variable}} substitution in workflow prompts and configuration.
"""

import re
from typing import Any, Dict, List, Optional


def resolve_template(template: Optional[str], context: Dict[str, Any]) -> str:
    """Resolve {{variable}} templates in a string.

    Supports:
    - Simple variables: {{input}} -> context['input']
    - Dotted access: {{stage_name.output}} -> context['stage_name.output']
    - Indexed access: {{all_prev[0]}} -> context['all_prev'][0]

    Missing variables become empty strings.

    Args:
        template: String with {{variable}} placeholders
        context: Dictionary of values to substitute

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
        if var_name in context and isinstance(context[var_name], list):
            if index < len(context[var_name]):
                result = result.replace(match.group(0), str(context[var_name][index]))
            else:
                result = result.replace(match.group(0), '')

    # Handle simple variables like {{input}} and dotted like {{stage.output}}
    simple_pattern = r'\{\{(\w+(?:\.\w+)*)\}\}'
    for match in re.finditer(simple_pattern, result):
        var_name = match.group(1)
        value = context.get(var_name, '')
        result = result.replace(match.group(0), str(value))

    return result


def expand_tasks_to_prompts(
    prompt_template: str,
    tasks: List[Any],
) -> List[str]:
    """Expand a prompt template with a list of tasks.

    Given a prompt template with {{task}}, {{task_title}}, {{task_id}} placeholders,
    generates one prompt per task.

    Args:
        prompt_template: Template string with task placeholders
        tasks: List of resolved task contexts (from tasks.resolve_tasks)

    Returns:
        List of expanded prompts, one per task
    """
    prompts = []

    for task_ctx in tasks:
        prompt = prompt_template
        prompt = prompt.replace('{{task}}', task_ctx.content)
        prompt = prompt.replace('{{task_title}}', task_ctx.title)
        prompt = prompt.replace('{{task_id}}', str(task_ctx.id) if task_ctx.id else '')
        prompts.append(prompt)

    return prompts
