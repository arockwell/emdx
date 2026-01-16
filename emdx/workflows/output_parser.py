"""Parse agent execution logs for output documents and token usage.

This module extracts structured data from Claude execution logs, including:
- Output document IDs (from emdx save commands)
- Token usage statistics (from __RAW_RESULT_JSON__ markers)
"""

import json
import logging
import re
from pathlib import Path
from typing import Dict, Optional

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
            r'document ID[:\s]+#?(\d+)',
            r'doc_id[:\s]+(\d+)',
            r'✅ Saved as\s*#(\d+)',      # With emoji
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
