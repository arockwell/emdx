#!/usr/bin/env python3
"""
Test script to validate all V2 browsers can be imported and instantiated.

This script checks that each browser:
1. Can be imported without errors
2. Can be instantiated
3. Has expected methods (compose, on_mount)

Run with: poetry run python scripts/test_v2_browsers.py
"""

import sys
import traceback
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class BrowserTestResult:
    """Result of testing a single browser."""

    name: str
    import_status: str
    import_error: Optional[str]
    instantiation_status: str
    instantiation_error: Optional[str]
    has_compose: bool
    has_on_mount: bool
    line_count: Optional[int]


# Define V2 browsers to test with their import paths
V2_BROWSERS = [
    ("ExampleBrowser", "emdx.ui.browsers", "example_browser"),
    ("LogBrowserV2", "emdx.ui.browsers", "log_browser_v2"),
    ("FileBrowserV2", "emdx.ui.browsers", "file_browser_v2"),
    ("GitBrowserV2", "emdx.ui.browsers", "git_browser_v2"),
    ("TaskBrowserV2", "emdx.ui.browsers", "task_browser_v2"),
    # Optional browsers - may or may not exist as V2 versions
    ("WorkflowBrowserV2", "emdx.ui.browsers", "workflow_browser_v2"),
    ("DocumentBrowserV2", "emdx.ui.browsers", "document_browser_v2"),
    ("ActivityBrowserV2", "emdx.ui.browsers", "activity_browser_v2"),
]


def count_lines(module_path: str, file_name: str) -> Optional[int]:
    """Count lines in the source file."""
    import importlib.util
    from pathlib import Path

    try:
        # Get the module's file path
        spec = importlib.util.find_spec(f"{module_path}.{file_name}")
        if spec and spec.origin:
            source_path = Path(spec.origin)
            if source_path.exists():
                return len(source_path.read_text().splitlines())
    except Exception:
        pass
    return None


def test_browser(
    browser_name: str, module_path: str, file_name: str
) -> BrowserTestResult:
    """Test a single browser for import and instantiation."""
    result = BrowserTestResult(
        name=browser_name,
        import_status="FAIL",
        import_error=None,
        instantiation_status="SKIP",
        instantiation_error=None,
        has_compose=False,
        has_on_mount=False,
        line_count=None,
    )

    # Try import
    browser_class: Optional[Any] = None
    try:
        module = __import__(f"{module_path}.{file_name}", fromlist=[browser_name])
        browser_class = getattr(module, browser_name)
        result.import_status = "OK"
        result.line_count = count_lines(module_path, file_name)
    except ImportError as e:
        result.import_error = f"ImportError: {e}"
        return result
    except AttributeError as e:
        result.import_error = f"AttributeError: {e}"
        return result
    except Exception as e:
        result.import_error = f"{type(e).__name__}: {e}"
        return result

    # Try instantiation
    try:
        instance = browser_class()
        result.instantiation_status = "OK"

        # Check for expected methods
        result.has_compose = hasattr(instance, "compose") and callable(
            getattr(instance, "compose")
        )
        result.has_on_mount = hasattr(instance, "on_mount") and callable(
            getattr(instance, "on_mount")
        )
    except Exception as e:
        result.instantiation_status = "FAIL"
        result.instantiation_error = f"{type(e).__name__}: {str(e)[:100]}"

    return result


def print_summary_table(results: list[BrowserTestResult]) -> None:
    """Print a formatted summary table of results."""
    # Calculate column widths
    name_width = max(len(r.name) for r in results) + 2
    status_width = 6
    methods_width = 15
    lines_width = 8

    # Header
    header = (
        f"{'Browser':<{name_width}} "
        f"{'Import':<{status_width}} "
        f"{'Instance':<{status_width}} "
        f"{'Methods':<{methods_width}} "
        f"{'Lines':<{lines_width}} "
        f"Error"
    )
    separator = "-" * len(header)

    print("\n" + separator)
    print("V2 BROWSER TEST RESULTS")
    print(separator)
    print(header)
    print(separator)

    for r in results:
        # Methods check
        if r.import_status == "OK" and r.instantiation_status == "OK":
            methods = []
            if r.has_compose:
                methods.append("compose")
            if r.has_on_mount:
                methods.append("on_mount")
            methods_str = ",".join(methods) if methods else "none"
        else:
            methods_str = "-"

        # Line count
        lines_str = str(r.line_count) if r.line_count else "-"

        # Error message
        error = r.import_error or r.instantiation_error or ""
        if len(error) > 60:
            error = error[:57] + "..."

        print(
            f"{r.name:<{name_width}} "
            f"{r.import_status:<{status_width}} "
            f"{r.instantiation_status:<{status_width}} "
            f"{methods_str:<{methods_width}} "
            f"{lines_str:<{lines_width}} "
            f"{error}"
        )

    print(separator)


def main() -> int:
    """Run all browser tests and return exit code."""
    print("Testing V2 Browsers...")
    print("=" * 60)

    results: list[BrowserTestResult] = []
    all_passed = True
    optional_browsers = {"WorkflowBrowserV2", "DocumentBrowserV2", "ActivityBrowserV2"}

    for browser_name, module_path, file_name in V2_BROWSERS:
        print(f"Testing {browser_name}...", end=" ")
        result = test_browser(browser_name, module_path, file_name)
        results.append(result)

        # Determine if this is a pass/fail
        is_optional = browser_name in optional_browsers
        is_import_fail = result.import_status != "OK"

        if is_import_fail and is_optional:
            print("SKIP (optional)")
        elif is_import_fail:
            print(f"FAIL (import): {result.import_error}")
            all_passed = False
        elif result.instantiation_status != "OK":
            print(f"FAIL (instantiation): {result.instantiation_error}")
            all_passed = False
        elif not result.has_compose:
            print("FAIL (missing compose method)")
            all_passed = False
        elif not result.has_on_mount:
            print("FAIL (missing on_mount method)")
            all_passed = False
        else:
            print(f"OK ({result.line_count} lines)")

    # Print summary
    print_summary_table(results)

    # Count results
    passed = sum(
        1
        for r in results
        if r.import_status == "OK"
        and r.instantiation_status == "OK"
        and r.has_compose
        and r.has_on_mount
    )
    failed = sum(
        1
        for r in results
        if (r.import_status != "OK" or r.instantiation_status != "OK")
        and r.name not in optional_browsers
    )
    skipped = sum(
        1
        for r in results
        if r.import_status != "OK" and r.name in optional_browsers
    )

    print(f"\nSummary: {passed} passed, {failed} failed, {skipped} skipped (optional)")

    if all_passed:
        print("\nAll required browsers passed!")
        return 0
    else:
        print("\nSome required browsers failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
