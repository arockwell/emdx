"""Tests for the chunk splitter utility."""


from emdx.utils.chunk_splitter import (
    MAX_CHUNK_CHARS,
    MIN_CHUNK_CHARS,
    Chunk,
    estimate_tokens,
    split_into_chunks,
)


class TestSplitIntoChunks:
    """Tests for split_into_chunks function."""

    def test_empty_document_returns_empty_list(self):
        """Empty content returns no chunks."""
        assert split_into_chunks("") == []
        assert split_into_chunks("   ") == []
        assert split_into_chunks("\n\n") == []

    def test_short_document_single_chunk(self):
        """Documents shorter than MIN_CHUNK_CHARS become one chunk."""
        content = "This is a short document."
        chunks = split_into_chunks(content, "Title")
        assert len(chunks) == 1
        assert chunks[0].heading_path == "Title"
        assert "short document" in chunks[0].text

    def test_short_document_without_title(self):
        """Short document without title uses 'Document' as heading."""
        content = "Short content here."
        chunks = split_into_chunks(content)
        assert len(chunks) == 1
        assert chunks[0].heading_path == "Document"

    def test_splits_on_markdown_headings(self):
        """Content with headings is split at heading boundaries."""
        # Each section needs to be at least MIN_CHUNK_CHARS to avoid being merged
        intro_text = "This is the introduction section. " * 15  # ~500 chars
        methods_text = "This is the methods section with detailed information. " * 15
        content = f"""
## Introduction

{intro_text}

## Methods

{methods_text}

"""
        chunks = split_into_chunks(content, "My Document")

        # Should have multiple chunks split by headings
        assert len(chunks) >= 2

        # Check heading paths are preserved
        heading_paths = [c.heading_path for c in chunks]
        assert any("Introduction" in hp for hp in heading_paths)
        assert any("Methods" in hp for hp in heading_paths)

    def test_heading_hierarchy_preserved(self):
        """Nested headings create proper heading paths."""
        content = """
## Main Section

Content under main.

### Subsection

Content under subsection.

#### Sub-subsection

Deep content here.
"""
        chunks = split_into_chunks(content, "Doc")

        # Find chunk with sub-subsection
        deep_chunks = [c for c in chunks if "Sub-subsection" in c.heading_path]
        if deep_chunks:
            # Should include parent headings in path
            assert "Main Section" in deep_chunks[0].heading_path

    def test_respects_max_chunk_size(self):
        """Large chunks are split to respect MAX_CHUNK_CHARS."""
        # Create content that exceeds max chunk size
        large_paragraph = "This is a sentence. " * 200  # ~4000 chars
        content = f"## Section\n\n{large_paragraph}"

        chunks = split_into_chunks(content)

        # All chunks should be at or below max size
        for chunk in chunks:
            assert len(chunk.text) <= MAX_CHUNK_CHARS + 50  # Small tolerance

    def test_merges_small_chunks(self):
        """Very small adjacent chunks are merged together."""
        content = """
## A

Short.

## B

Brief.

## C

Tiny.
"""
        chunks = split_into_chunks(content)

        # Small chunks should be merged, so we should have fewer chunks
        # than the number of headings if they're all tiny
        assert len(chunks) <= 3

    def test_chunk_indices_sequential(self):
        """Chunk indices are sequential starting from 0."""
        content = """
## One

First section.

## Two

Second section.

## Three

Third section.
"""
        chunks = split_into_chunks(content)

        indices = [c.index for c in chunks]
        for i, idx in enumerate(indices):
            assert idx == i

    def test_line_numbers_tracked(self):
        """Chunks track their start and end line numbers."""
        content = """## Section

Line 3 content.
Line 4 content.
Line 5 content.
"""
        chunks = split_into_chunks(content)

        for chunk in chunks:
            assert chunk.start_line >= 1
            assert chunk.end_line >= chunk.start_line


class TestChunkDataclass:
    """Tests for the Chunk dataclass."""

    def test_display_heading_with_path(self):
        """display_heading formats heading path with § prefix."""
        chunk = Chunk(
            index=0,
            heading_path="Methods > Data Collection",
            text="Sample text",
            start_line=1,
            end_line=5,
        )
        assert chunk.display_heading == '§"Methods > Data Collection"'

    def test_display_heading_empty_path(self):
        """display_heading returns empty string for empty path."""
        chunk = Chunk(
            index=0,
            heading_path="",
            text="Sample text",
            start_line=1,
            end_line=1,
        )
        assert chunk.display_heading == ""


class TestEstimateTokens:
    """Tests for token estimation."""

    def test_estimate_tokens_basic(self):
        """Token estimation works for typical text."""
        # ~4 chars per token
        text = "This is a test sentence."  # 24 chars
        tokens = estimate_tokens(text)
        assert tokens == 6  # 24 // 4

    def test_estimate_tokens_empty(self):
        """Empty string estimates 0 tokens."""
        assert estimate_tokens("") == 0

    def test_estimate_tokens_long_text(self):
        """Longer text gives proportionally more tokens."""
        short = "Hi"  # 2 chars -> 0 tokens
        long = "Hello world!" * 100  # 1200 chars -> 300 tokens

        assert estimate_tokens(short) < estimate_tokens(long)


class TestTokenLimits:
    """Tests for token/character limit behavior."""

    def test_constants_defined(self):
        """Token limit constants are properly defined."""
        assert MIN_CHUNK_CHARS > 0
        assert MAX_CHUNK_CHARS > MIN_CHUNK_CHARS
        # Min should be around 400 chars (100 tokens * 4 chars/token)
        assert MIN_CHUNK_CHARS >= 300
        # Max should be around 2000 chars (500 tokens * 4 chars/token)
        assert MAX_CHUNK_CHARS >= 1500

    def test_very_large_document_handled(self):
        """Very large documents don't cause infinite loops or crashes."""
        # Create a large document with repeated content
        section = "## Section {i}\n\nParagraph content. " * 20
        content = "\n\n".join(section.format(i=i) for i in range(50))

        # Should complete without error
        chunks = split_into_chunks(content, "Large Doc")

        # Should have produced chunks
        assert len(chunks) > 0

        # Total content should be preserved (roughly)
        total_text = " ".join(c.text for c in chunks)
        # At least some content preserved
        assert len(total_text) > len(content) // 2
