"""Shared URL linkification helpers for TUI widgets.

Converts plain-text URLs into Rich Text with @click meta so that
clicking a link in any RichLog opens it in the default browser.
The action uses the ``app.`` namespace prefix so it resolves on
BrowserContainer.action_open_url regardless of which widget the
click lands on.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rich.style import Style
from rich.text import Text

if TYPE_CHECKING:
    from textual.widgets import RichLog

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


def linkify_richlog(richlog: RichLog) -> None:
    """Post-process a RichLog to add @click meta to URL-containing segments.

    Walks every line in the RichLog and replaces strips that contain URLs
    with new strips whose URL segments carry ``@click`` meta. This is useful
    after writing a Rich Markdown renderable, which produces ``style.link``
    but not ``@click`` meta.
    """
    from rich.segment import Segment
    from textual.strip import Strip

    for idx, strip in enumerate(richlog.lines):
        plain = strip.text
        if "http" not in plain:
            continue
        new_segments: list[Segment] = []
        changed = False
        for seg in strip._segments:
            text = seg.text
            style = seg.style
            # If Rich already set style.link, add @click meta
            if style and style.link and style.link.startswith("http"):
                url = clean_url(style.link)
                new_style = style + Style(
                    meta={"@click": f"app.open_url({url!r})"},
                )
                new_segments.append(Segment(text, new_style, seg.control))
                changed = True
            # If plain text contains a bare URL, split and linkify
            elif "http" in text and _URL_RE.search(text):
                last = 0
                for match in _URL_RE.finditer(text):
                    url = clean_url(match.group(0))
                    if not url:
                        continue
                    if match.start() > last:
                        new_segments.append(Segment(text[last : match.start()], style, None))
                    link_style = (
                        (style or Style.null())
                        + _LINK_STYLE
                        + Style(
                            meta={"@click": f"app.open_url({url!r})"},
                        )
                    )
                    new_segments.append(Segment(url, link_style, None))
                    leftover_start = match.start() + len(url)
                    if leftover_start < match.end():
                        new_segments.append(
                            Segment(text[leftover_start : match.end()], style, None)
                        )
                    last = match.end()
                if last < len(text):
                    new_segments.append(Segment(text[last:], style, None))
                changed = True
            else:
                new_segments.append(seg)
        if changed:
            richlog.lines[idx] = Strip(new_segments, strip.cell_length)
