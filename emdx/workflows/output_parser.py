"""Parse agent execution logs for output documents, PRs, and token usage.

This module extracts structured data from Claude execution logs, including:
- Output document IDs (from emdx save commands)
- PR URLs and numbers (from gh pr create output)
- Token usage statistics (from __RAW_RESULT_JSON__ markers)
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def extract_output_doc_id(log_file: Path) -> Optional[int]:
    """Extract output document ID from execution log.

    Looks for patterns like "Created document #123" or "Saved as #123"
    in the log file. Handles Rich/ANSI formatting codes.

    If multiple document IDs are found, returns the LAST one (most likely
    the final output document).

    Args:
        log_file: Path to the execution log

    Returns:
        Document ID if found, None otherwise
    """
    if not log_file.exists():
        return None

    try:
        content = log_file.read_text()

        # Strip ANSI codes for cleaner matching
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        clean_content = ansi_escape.sub('', content)

        # Also handle Rich markup-style codes like [32m, [0m, [1;32m
        rich_codes = re.compile(r'\[\d+(?:;\d+)*m')
        clean_content = rich_codes.sub('', clean_content)

        # Look for document creation patterns (check LAST match to get final save)
        patterns = [
            r'saved as document #(\d+)',  # Agent natural language
            r'Saved as #(\d+)',           # CLI output
            r'Created document #(\d+)',
            r'Document ID(?:\s+created)?[:\s]*\*?\*?#?(\d+)\*?\*?',  # Agent output (with optional "created" and markdown bold)
            r'\*\*Document ID:\*\*\s*(\d+)',  # Cursor markdown: **Document ID:** 5714
            r'document ID[:\s]+#?(\d+)',
            r'doc_id[:\s]+(\d+)',
            r'✅ Saved as\s*#(\d+)',      # With emoji
            r'doc ID\s*`(\d+)`',          # Markdown backtick format: doc ID `123`
            r'Saved to EMDX as.*?(\d+)',  # "Saved to EMDX as **doc ID `5704`**"
        ]

        # Find ALL matches and return the LAST one (most likely the final output)
        last_match = None
        for pattern in patterns:
            for match in re.finditer(pattern, clean_content, re.IGNORECASE):
                last_match = int(match.group(1))

        return last_match

    except (OSError, IOError) as e:
        logger.debug(f"Could not read log file {log_file}: {type(e).__name__}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error extracting output doc ID from {log_file}: {type(e).__name__}: {e}")
        return None


def _clean_content(content: str) -> str:
    """Strip ANSI codes and Rich markup for cleaner pattern matching."""
    # Strip ANSI escape codes
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    clean = ansi_escape.sub('', content)

    # Also handle Rich markup-style codes like [32m, [0m, [1;32m
    rich_codes = re.compile(r'\[\d+(?:;\d+)*m')
    clean = rich_codes.sub('', clean)

    # Strip markdown bold/italic markers around URLs
    clean = re.sub(r'\*+([^*]+)\*+', r'\1', clean)

    return clean


def extract_pr_url(content: str) -> Optional[str]:
    """Extract GitHub PR URL from text content.

    Looks for various patterns Claude might use when reporting a PR URL.
    Handles Rich/ANSI formatting codes and markdown.

    If multiple PR URLs are found, returns the LAST one (most likely
    the final/actual PR created).

    Args:
        content: Text content to search (log file content or output string)

    Returns:
        PR URL if found, None otherwise
    """
    clean_content = _clean_content(content)

    # Patterns for explicit PR URL markers (with URL capture)
    url_patterns = [
        # Explicit markers with URL
        r'PR_URL[:\s]+\*?\*?(https://github\.com/[^\s\)>\]]+)',
        r'pr_url[:\s]+\*?\*?(https://github\.com/[^\s\)>\]]+)',
        r'PR[:\s]+\*?\*?(https://github\.com/[^\s\)>\]]+/pull/\d+)',
        r'pull request[:\s]+\*?\*?(https://github\.com/[^\s\)>\]]+)',
        # Natural language with URL
        r'[Cc]reated (?:PR|pull request)[:\s]+\*?\*?(https://github\.com/[^\s\)>\]]+)',
        r'[Oo]pened (?:PR|pull request)[:\s]+\*?\*?(https://github\.com/[^\s\)>\]]+)',
        r'PR (?:is |at |created at )?\*?\*?(https://github\.com/[^\s\)>\]]+)',
        # Markdown link format: [text](url)
        r'\[(?:PR|Pull Request)[^\]]*\]\((https://github\.com/[^\s\)]+/pull/\d+)\)',
        r'\[[^\]]*PR[^\]]*\]\((https://github\.com/[^\s\)]+/pull/\d+)\)',
        # Any markdown link containing a PR URL
        r'\[[^\]]*\]\((https://github\.com/[^\s\)]+/pull/\d+)\)',
        # gh CLI output format
        r'(https://github\.com/[^\s\)>\]]+/pull/\d+)\s*$',  # URL at end of line
        # Bare GitHub PR URL on its own line
        r'^\s*(https://github\.com/[^\s\)>\]]+/pull/\d+)\s*$',
    ]

    # Find ALL matches and return the LAST one
    last_match = None
    for pattern in url_patterns:
        for match in re.finditer(pattern, clean_content, re.IGNORECASE | re.MULTILINE):
            url = match.group(1)
            # Clean up any trailing punctuation or markdown
            url = url.rstrip('.,;:!?)>\'"')
            if '/pull/' in url:  # Validate it's actually a PR URL
                last_match = url

    return last_match


def extract_pr_url_from_file(log_file: Path) -> Optional[str]:
    """Extract GitHub PR URL from execution log file.

    Args:
        log_file: Path to the execution log

    Returns:
        PR URL if found, None otherwise
    """
    if not log_file.exists():
        return None

    try:
        content = log_file.read_text()
        return extract_pr_url(content)
    except (OSError, IOError) as e:
        logger.debug(f"Could not read log file {log_file}: {type(e).__name__}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Unexpected error extracting PR URL from {log_file}: {type(e).__name__}: {e}")
        return None


def extract_pr_number(content: str) -> Optional[int]:
    """Extract GitHub PR number from text content.

    Looks for various patterns Claude might use when reporting a PR number.
    Can extract from full URLs or just PR references like "PR #123".

    If multiple PR numbers are found, returns the LAST one.

    Args:
        content: Text content to search

    Returns:
        PR number if found, None otherwise
    """
    clean_content = _clean_content(content)

    # First try to get from URL (most reliable)
    url = extract_pr_url(content)
    if url:
        url_match = re.search(r'/pull/(\d+)', url)
        if url_match:
            return int(url_match.group(1))

    # Patterns for PR number references (without full URL)
    number_patterns = [
        r'PR\s*#(\d+)',
        r'pull request\s*#(\d+)',
        r'[Cc]reated PR\s*#(\d+)',
        r'[Oo]pened PR\s*#(\d+)',
        r'[Mm]erged PR\s*#(\d+)',
        r'PR number[:\s]+#?(\d+)',
    ]

    last_match = None
    for pattern in number_patterns:
        for match in re.finditer(pattern, clean_content, re.IGNORECASE):
            last_match = int(match.group(1))

    return last_match


def extract_all_pr_urls(content: str) -> List[str]:
    """Extract all GitHub PR URLs from text content.

    Unlike extract_pr_url which returns only the last match,
    this returns all unique PR URLs found.

    Args:
        content: Text content to search

    Returns:
        List of unique PR URLs found
    """
    clean_content = _clean_content(content)

    # Match any GitHub PR URL
    pr_url_pattern = r'https://github\.com/[^\s\)>\]]+/pull/\d+'

    urls = set()
    for match in re.finditer(pr_url_pattern, clean_content):
        url = match.group(0)
        # Clean up trailing punctuation
        url = url.rstrip('.,;:!?)>\'"')
        urls.add(url)

    return list(urls)


def extract_token_usage(log_file: Path) -> int:
    """Extract total token usage from Claude execution log.

    Convenience wrapper around extract_token_usage_detailed that
    returns just the total.

    Args:
        log_file: Path to the execution log

    Returns:
        Total tokens used, or 0 if not found
    """
    usage = extract_token_usage_detailed(log_file)
    return usage.get('total', 0)


def extract_token_usage_detailed(log_file: Path) -> Dict[str, int]:
    """Extract detailed token usage from Claude execution log.

    Parses the log file looking for the raw result JSON that was embedded
    by format_claude_output with the __RAW_RESULT_JSON__ marker.

    Args:
        log_file: Path to the execution log

    Returns:
        Dict with keys:
        - input: Input tokens (including cache reads)
        - output: Output tokens
        - cache_in: Cache read tokens
        - cache_create: Cache creation tokens
        - total: Sum of all tokens
        - cost_usd: Total cost in USD
    """
    empty = {
        'input': 0,
        'output': 0,
        'cache_in': 0,
        'cache_create': 0,
        'total': 0,
        'cost_usd': 0.0,
    }

    if not log_file.exists():
        return empty

    try:
        content = log_file.read_text()

        # Look for the raw result JSON marker added by format_claude_output
        marker = '__RAW_RESULT_JSON__:'
        for line in content.split('\n'):
            if line.startswith(marker):
                json_str = line[len(marker):]
                try:
                    data = json.loads(json_str)
                    if data.get('type') == 'result' and 'usage' in data:
                        usage = data['usage']
                        input_tokens = usage.get('input_tokens', 0)
                        output_tokens = usage.get('output_tokens', 0)
                        cache_creation = usage.get('cache_creation_input_tokens', 0)
                        cache_read = usage.get('cache_read_input_tokens', 0)
                        total = input_tokens + output_tokens + cache_creation + cache_read
                        cost_usd = data.get('total_cost_usd', 0.0)
                        return {
                            'input': input_tokens + cache_read,  # Effective input
                            'output': output_tokens,
                            'cache_in': cache_read,
                            'cache_create': cache_creation,
                            'total': total,
                            'cost_usd': cost_usd,
                        }
                except json.JSONDecodeError:
                    continue

        return empty

    except (OSError, IOError) as e:
        logger.debug(f"Could not read log file {log_file}: {type(e).__name__}: {e}")
        return empty
    except Exception as e:
        logger.warning(f"Unexpected error extracting tokens from {log_file}: {type(e).__name__}: {e}")
        return empty
