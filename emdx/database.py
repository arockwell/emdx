"""
Database connection and operations for emdx
"""

from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from multiple sources
# 1. First, try user config directory
user_config = Path.home() / ".config" / "emdx" / ".env"
if user_config.exists():
    load_dotenv(user_config)

# 2. Then load from current directory (for development)
load_dotenv()

# Import the SQLite implementation
from .sqlite_database import SQLiteDatabase, db

# For now, just use SQLite as the Database class
Database = SQLiteDatabase

# Export the global instance
__all__ = ["Database", "db"]
