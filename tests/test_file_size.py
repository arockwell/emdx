"""Tests for file size formatting utilities."""

from emdx.utils.file_size import format_file_size


class TestFormatFileSize:
    """Test cases for format_file_size function."""

    def test_zero_bytes(self):
        """Test formatting of 0 bytes."""
        assert format_file_size(0) == "0 B"

    def test_negative_bytes(self):
        """Test handling of negative numbers."""
        assert format_file_size(-1) == "Invalid size"
        assert format_file_size(-1000) == "Invalid size"

    def test_bytes(self):
        """Test formatting of byte values."""
        assert format_file_size(1) == "1 B"
        assert format_file_size(1023) == "1023 B"

    def test_kilobytes(self):
        """Test formatting of kilobyte values."""
        assert format_file_size(1024) == "1 KB"
        assert format_file_size(1536) == "1.5 KB"
        assert format_file_size(10240) == "10 KB"
        assert format_file_size(102400) == "100 KB"

    def test_megabytes(self):
        """Test formatting of megabyte values."""
        assert format_file_size(1048576) == "1 MB"  # 1024 * 1024
        assert format_file_size(3670016) == "3.5 MB"  # 3.5 * 1024 * 1024
        assert format_file_size(10485760) == "10 MB"
        assert format_file_size(104857600) == "100 MB"

    def test_gigabytes(self):
        """Test formatting of gigabyte values."""
        assert format_file_size(1073741824) == "1 GB"  # 1024^3
        assert format_file_size(2252341555) == "2.1 GB"  # ~2.1 * 1024^3
        assert format_file_size(10737418240) == "10 GB"

    def test_terabytes(self):
        """Test formatting of terabyte values."""
        assert format_file_size(1099511627776) == "1 TB"  # 1024^4
        assert format_file_size(5497558138880) == "5 TB"

    def test_petabytes(self):
        """Test formatting of petabyte values."""
        assert format_file_size(1125899906842624) == "1 PB"  # 1024^5
        assert format_file_size(2251799813685248) == "2 PB"

    def test_decimal_precision(self):
        """Test decimal precision rules."""
        # Less than 10: 2 decimal places
        assert format_file_size(1536) == "1.5 KB"
        assert format_file_size(2867) == "2.8 KB"

        # Between 10 and 100: 1 decimal place
        assert format_file_size(12288) == "12 KB"
        assert format_file_size(51200) == "50 KB"
        assert format_file_size(15872) == "15.5 KB"

        # 100 or more: no decimal places
        assert format_file_size(102400) == "100 KB"
        assert format_file_size(157696) == "154 KB"

    def test_edge_cases(self):
        """Test edge cases around unit boundaries."""
        assert format_file_size(1023) == "1023 B"
        assert format_file_size(1024) == "1 KB"
        assert format_file_size(1048575) == "1024 KB"
        assert format_file_size(1048576) == "1 MB"
