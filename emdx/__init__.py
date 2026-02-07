"""
emdx - Documentation Index Management System
"""

import hashlib
import time
from pathlib import Path

__version__ = "0.10.0"

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
    except Exception:
        # Fallback to timestamp if file ops fail
        return f"{__version__}-{int(time.time())}"

__build_id__ = _generate_build_id()
