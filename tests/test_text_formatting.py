"""Tests for text formatting utilities."""

from emdx.utils.text_formatting import (
    truncate_description,
    truncate_path,
    truncate_text,
    truncate_title,
)


class TestTruncateTitle:
    """Test truncate_title function."""

    def test_short_text_unchanged(self):
        assert truncate_title("Hello") == "Hello"

    def test_exact_length_unchanged(self):
        text = "x" * 50
        assert truncate_title(text) == text

    def test_long_text_truncated(self):
        text = "x" * 60
        result = truncate_title(text)
        assert result == "x" * 50 + "..."
        assert len(result) == 53

    def test_custom_max_len(self):
        text = "Hello World"
        assert truncate_title(text, max_len=5) == "Hello..."

    def test_empty_string(self):
        assert truncate_title("") == ""

    def test_one_over_limit(self):
        text = "x" * 51
        result = truncate_title(text)
        assert result.endswith("...")
        assert len(result) == 53

    def test_unicode_text(self):
        text = "\U0001f680" * 60
        result = truncate_title(text)
        assert result.endswith("...")

    def test_default_max_len_is_50(self):
        text = "a" * 50
        assert truncate_title(text) == text
        text = "a" * 51
        assert truncate_title(text) == "a" * 50 + "..."


class TestTruncateDescription:
    """Test truncate_description function."""

    def test_short_text_unchanged(self):
        assert truncate_description("Short text") == "Short text"

    def test_default_max_len_is_40(self):
        text = "b" * 40
        assert truncate_description(text) == text
        text = "b" * 41
        assert truncate_description(text) == "b" * 40 + "..."

    def test_custom_max_len(self):
        assert truncate_description("Hello World", max_len=5) == "Hello..."

    def test_empty_string(self):
        assert truncate_description("") == ""


class TestTruncatePath:
    """Test truncate_path function."""

    def test_short_path_unchanged(self):
        assert truncate_path("/home/user/file.txt") == "/home/user/file.txt"

    def test_default_max_len_is_35(self):
        text = "p" * 35
        assert truncate_path(text) == text
        text = "p" * 36
        assert truncate_path(text) == "p" * 35 + "..."

    def test_long_path_truncated(self):
        path = "/very/long/deeply/nested/directory/structure/file.txt"
        result = truncate_path(path)
        assert result.endswith("...")

    def test_empty_string(self):
        assert truncate_path("") == ""


class TestTruncateText:
    """Test truncate_text function."""

    def test_short_text_unchanged(self):
        assert truncate_text("Hi") == "Hi"

    def test_default_max_len_is_30(self):
        text = "c" * 30
        assert truncate_text(text) == text
        text = "c" * 31
        assert truncate_text(text) == "c" * 30 + "..."

    def test_custom_max_len(self):
        assert truncate_text("Hello World", max_len=5) == "Hello..."

    def test_empty_string(self):
        assert truncate_text("") == ""

    def test_special_characters(self):
        text = "!@#$%^&*()" * 5
        result = truncate_text(text)
        assert result.endswith("...")

    def test_newlines_in_text(self):
        text = "line1\nline2\nline3\nline4\nline5\nline6"
        result = truncate_text(text)
        assert result.endswith("...")

    def test_max_len_zero(self):
        assert truncate_text("abc", max_len=0) == "..."

    def test_max_len_one(self):
        assert truncate_text("abc", max_len=1) == "a..."
