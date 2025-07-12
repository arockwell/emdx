"""Test the __init__ module."""

import emdx


def test_version_exists():
    """Test that version is defined."""
    assert hasattr(emdx, "__version__")
    assert isinstance(emdx.__version__, str)
    assert len(emdx.__version__) > 0
