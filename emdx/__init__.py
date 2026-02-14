"""
emdx - Documentation Index Management System
"""

import hashlib
import logging
import time
from pathlib import Path

__version__ = "0.14.0"

# Generate a unique build identifier based on current timestamp and file modification times
def _generate_build_id():
    """Generate a unique build identifier for version tracking."""
    try:
        # Get current file modification time
        current_file = Path(__file__)
        mtime = current_file.stat().st_mtime

        # Create hash from timestamp and version
        build_data = f"{__version__}-{mtime}-{time.time()}"
        build_hash = hashlib.md5(build_data.encode()).hexdigest()[:8]
        return f"{__version__}-{build_hash}"
    except Exception as e:
        # Fallback to timestamp if file ops fail
        # Use print since logging may not be configured yet at import time
        logging.getLogger(__name__).debug(f"Build ID generation fell back to timestamp: {e}")
        return f"{__version__}-{int(time.time())}"

__build_id__ = _generate_build_id()
