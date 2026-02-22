"""
Markdown chunk splitter for semantic search.

Splits documents into chunks based on markdown headings and paragraphs,
preserving heading paths for context. Optimized for ~100-500 token chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """A chunk of document text with heading context."""

    index: int
    heading_path: str  # e.g., "Methods > Data Collection"
    text: str
    start_line: int
    end_line: int

    @property
    def display_heading(self) -> str:
        """Format heading path for display: §"Methods > Data Collection"."""
        if self.heading_path:
            return f'§"{self.heading_path}"'
        return ""


# Rough approximation: 1 token ≈ 4 characters for English text
CHARS_PER_TOKEN = 4
MIN_CHUNK_TOKENS = 100
MAX_CHUNK_TOKENS = 500
MIN_CHUNK_CHARS = MIN_CHUNK_TOKENS * CHARS_PER_TOKEN
MAX_CHUNK_CHARS = MAX_CHUNK_TOKENS * CHARS_PER_TOKEN


def split_into_chunks(content: str, title: str = "") -> list[Chunk]:
    """
    Split markdown content into chunks for semantic search.

    Strategy:
    1. Split on markdown headings (##, ###, etc.)
    2. If a section is too large, split on paragraph breaks
    3. If still too large, split on sentence boundaries
    4. Very short docs (<MIN_CHUNK_TOKENS) become a single chunk

    Args:
        content: The markdown document content
        title: Document title (used for first chunk heading path)

    Returns:
        List of Chunk objects with heading context
    """
    if not content or not content.strip():
        return []

    # Prepend title for better embedding
    full_text = f"{title}\n\n{content}" if title else content

    # For very short documents, return as single chunk
    if len(full_text) < MIN_CHUNK_CHARS:
        return [
            Chunk(
                index=0,
                heading_path=title or "Document",
                text=full_text.strip(),
                start_line=1,
                end_line=full_text.count("\n") + 1,
            )
        ]

    # Split by headings
    chunks = _split_by_headings(content, title)

    # Post-process: split large chunks, merge small ones
    chunks = _split_large_chunks(chunks)
    chunks = _merge_small_chunks(chunks)

    # Re-index after merging
    for i, chunk in enumerate(chunks):
        chunk.index = i

    return chunks


def _split_by_headings(content: str, title: str) -> list[Chunk]:
    """Split content by markdown headings, preserving heading hierarchy."""
    # Match markdown headings: ## Heading, ### Subheading, etc.
    heading_pattern = re.compile(r"^(#{1,6})\s+(.+?)$", re.MULTILINE)

    chunks: list[Chunk] = []
    heading_stack: list[tuple[int, str]] = []  # (level, heading_text)
    last_pos = 0
    current_line = 1

    # Add title to stack as level 0
    if title:
        heading_stack.append((0, title))

    for match in heading_pattern.finditer(content):
        # Get text before this heading
        text_before = content[last_pos : match.start()].strip()

        if text_before:
            heading_path = " > ".join(h for _, h in heading_stack) if heading_stack else ""
            end_line = current_line + text_before.count("\n")
            chunks.append(
                Chunk(
                    index=len(chunks),
                    heading_path=heading_path,
                    text=text_before,
                    start_line=current_line,
                    end_line=end_line,
                )
            )
            current_line = end_line + 1

        # Update heading stack
        level = len(match.group(1))  # Number of # characters
        heading_text = match.group(2).strip()

        # Pop headings at same or lower level
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()

        heading_stack.append((level, heading_text))
        last_pos = match.end()
        current_line += 1  # Account for the heading line

    # Don't forget the last section
    text_after = content[last_pos:].strip()
    if text_after:
        heading_path = " > ".join(h for _, h in heading_stack) if heading_stack else ""
        chunks.append(
            Chunk(
                index=len(chunks),
                heading_path=heading_path,
                text=text_after,
                start_line=current_line,
                end_line=current_line + text_after.count("\n"),
            )
        )

    return chunks


def _split_large_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Split chunks that exceed MAX_CHUNK_CHARS."""
    result: list[Chunk] = []

    for chunk in chunks:
        if len(chunk.text) <= MAX_CHUNK_CHARS:
            result.append(chunk)
            continue

        # Try splitting by paragraphs first (double newline)
        paragraphs = re.split(r"\n\n+", chunk.text)

        current_text = ""
        current_start = chunk.start_line
        part_num = 1

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            if len(current_text) + len(para) + 2 <= MAX_CHUNK_CHARS:
                if current_text:
                    current_text += "\n\n"
                current_text += para
            else:
                # Save current chunk
                if current_text:
                    heading_path = chunk.heading_path
                    if part_num > 1:
                        heading_path = f"{chunk.heading_path} (cont.)"
                    result.append(
                        Chunk(
                            index=len(result),
                            heading_path=heading_path,
                            text=current_text,
                            start_line=current_start,
                            end_line=current_start + current_text.count("\n"),
                        )
                    )
                    part_num += 1
                    current_start = chunk.start_line + current_text.count("\n") + 1

                # Start new chunk with this paragraph
                # If paragraph itself is too large, split by sentences
                if len(para) > MAX_CHUNK_CHARS:
                    sentence_chunks = _split_by_sentences(para, chunk.heading_path, current_start)
                    result.extend(sentence_chunks)
                    current_text = ""
                else:
                    current_text = para

        # Don't forget the last piece
        if current_text:
            heading_path = chunk.heading_path
            if part_num > 1:
                heading_path = f"{chunk.heading_path} (cont.)"
            result.append(
                Chunk(
                    index=len(result),
                    heading_path=heading_path,
                    text=current_text,
                    start_line=current_start,
                    end_line=current_start + current_text.count("\n"),
                )
            )

    return result


def _split_by_sentences(text: str, heading_path: str, start_line: int) -> list[Chunk]:
    """Split text by sentences when paragraph splitting isn't enough."""
    # Simple sentence splitting on . ! ?
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[Chunk] = []
    current_text = ""
    current_start = start_line

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(current_text) + len(sentence) + 1 <= MAX_CHUNK_CHARS:
            if current_text:
                current_text += " "
            current_text += sentence
        else:
            if current_text:
                chunks.append(
                    Chunk(
                        index=len(chunks),
                        heading_path=f"{heading_path} (cont.)",
                        text=current_text,
                        start_line=current_start,
                        end_line=current_start + current_text.count("\n"),
                    )
                )
                current_start = current_start + current_text.count("\n") + 1
            current_text = sentence

    if current_text:
        chunks.append(
            Chunk(
                index=len(chunks),
                heading_path=f"{heading_path} (cont.)",
                text=current_text,
                start_line=current_start,
                end_line=current_start + current_text.count("\n"),
            )
        )

    return chunks


def _merge_small_chunks(chunks: list[Chunk]) -> list[Chunk]:
    """Merge consecutive small chunks that share a heading path prefix."""
    if len(chunks) <= 1:
        return chunks

    result: list[Chunk] = []
    i = 0

    while i < len(chunks):
        chunk = chunks[i]

        # If this chunk is large enough, keep it as-is
        if len(chunk.text) >= MIN_CHUNK_CHARS:
            result.append(chunk)
            i += 1
            continue

        # Try to merge with next chunks that are also small
        merged_text = chunk.text
        merged_end = chunk.end_line
        j = i + 1

        while j < len(chunks):
            next_chunk = chunks[j]

            # Only merge if the combined size is still reasonable
            combined_len = len(merged_text) + len(next_chunk.text) + 2
            if combined_len > MAX_CHUNK_CHARS:
                break

            # Merge
            merged_text += "\n\n" + next_chunk.text
            merged_end = next_chunk.end_line
            j += 1

            # Stop if we've reached a good size
            if len(merged_text) >= MIN_CHUNK_CHARS:
                break

        result.append(
            Chunk(
                index=len(result),
                heading_path=chunk.heading_path,
                text=merged_text,
                start_line=chunk.start_line,
                end_line=merged_end,
            )
        )
        i = j

    return result
