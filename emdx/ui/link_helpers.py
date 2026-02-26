"""Shared URL linkification helpers for TUI widgets.

Converts plain-text URLs into Rich Text with @click meta so that
clicking a link in any RichLog opens it in the default browser.
The action uses the ``app.`` namespace prefix so it resolves on
BrowserContainer.action_open_url regardless of which widget the
click lands on.
"""

import re

from rich.style import Style
from rich.text import Text

# Match http/https URLs, stopping at whitespace and common delimiters
_URL_RE = re.compile(r"https?://[^\s<>\[\]\"{}]+")

_LINK_STYLE = Style(underline=True, color="bright_cyan")


def clean_url(raw: str) -> str:
    """Strip trailing punctuation that is likely not part of the URL."""
    url = raw
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1]
    url = url.rstrip(".,;:!?'\"")
    return url


def linkify_text(raw: str) -> Text:
    """Build a Rich Text with URLs rendered as clickable action links.

    Non-URL text is preserved as-is. Each URL gets an underlined cyan
    style with ``@click`` meta that dispatches ``app.open_url(url)``.
    """
    text = Text()
    last_end = 0
    for match in _URL_RE.finditer(raw):
        url = clean_url(match.group(0))
        if not url:
            continue
        if match.start() > last_end:
            text.append(raw[last_end : match.start()])
        link_style = _LINK_STYLE + Style(
            meta={"@click": f"app.open_url({url!r})"},
        )
        text.append(url, style=link_style)
        leftover_start = match.start() + len(url)
        if leftover_start < match.end():
            text.append(raw[leftover_start : match.end()])
        last_end = match.end()
    if last_end < len(raw):
        text.append(raw[last_end:])
    return text


def extract_urls(text: str) -> list[str]:
    """Extract clean URLs from text."""
    urls: list[str] = []
    for match in _URL_RE.finditer(text):
        url = clean_url(match.group(0))
        if url:
            urls.append(url)
    return urls
