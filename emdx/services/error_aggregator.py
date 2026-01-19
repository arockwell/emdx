"""Simple error aggregation facade for unified reporting.

This module provides a simple `report_error` function that delegates to the
ErrorCollector service. It's designed to be imported by components that need
to report errors without coupling to the full error collection API.
"""

from typing import Any, Dict, Optional

from .error_collector import error_collector


def get_error_aggregator():
    """Get the error collector instance.

    Returns:
        The ErrorCollector singleton for querying errors
    """
    return error_collector


def report_error(
    source: str,
    message: str,
    context: Optional[Dict[str, Any]] = None,
    stack_trace: Optional[str] = None,
    severity: str = "error",
    execution_id: Optional[int] = None,
) -> Optional[int]:
    """Report an error to the centralized error collector.

    Args:
        source: Component name (workflow, cascade, agent, execution, etc.)
        message: Error message
        context: Optional dictionary with source-specific context
        stack_trace: Optional traceback string
        severity: "error", "warning", or "info" (default: "error")
        execution_id: Optional link to execution record

    Returns:
        Created error ID, or None if failed
    """
    return error_collector.report(
        severity=severity,
        source=source,
        message=message,
        context=context,
        traceback=stack_trace,
        execution_id=execution_id,
    )
