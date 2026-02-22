"""Tests for text formatting utilities."""

from emdx.utils.text_formatting import (
    truncate_description,
    truncate_title,
)


class TestTruncateTitle:
    """Test truncate_title function."""

    def test_short_text_unchanged(self) -> None:
        assert truncate_title("Hello") == "Hello"

    def test_exact_length_unchanged(self) -> None:
        text = "x" * 50
        assert truncate_title(text) == text

    def test_long_text_truncated(self) -> None:
        text = "x" * 60
        result = truncate_title(text)
        assert result == "x" * 50 + "..."
        assert len(result) == 53

    def test_custom_max_len(self) -> None:
        text = "Hello World"
        assert truncate_title(text, max_len=5) == "Hello..."

    def test_empty_string(self) -> None:
        assert truncate_title("") == ""

    def test_one_over_limit(self) -> None:
        text = "x" * 51
        result = truncate_title(text)
        assert result.endswith("...")
        assert len(result) == 53

    def test_unicode_text(self) -> None:
        text = "\U0001f680" * 60
        result = truncate_title(text)
        assert result.endswith("...")

    def test_default_max_len_is_50(self) -> None:
        text = "a" * 50
        assert truncate_title(text) == text
        text = "a" * 51
        assert truncate_title(text) == "a" * 50 + "..."


class TestTruncateDescription:
    """Test truncate_description function."""

    def test_short_text_unchanged(self) -> None:
        assert truncate_description("Short text") == "Short text"

    def test_default_max_len_is_40(self) -> None:
        text = "b" * 40
        assert truncate_description(text) == text
        text = "b" * 41
        assert truncate_description(text) == "b" * 40 + "..."

    def test_custom_max_len(self) -> None:
        assert truncate_description("Hello World", max_len=5) == "Hello..."

    def test_empty_string(self) -> None:
        assert truncate_description("") == ""
