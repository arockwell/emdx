"""
Database connection and operations for emdx
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from multiple sources
# 1. First, try user config directory
user_config = Path.home() / '.config' / 'emdx' / '.env'
if user_config.exists():
    load_dotenv(user_config)

# 2. Then load from current directory (for development)
load_dotenv()

# Import the SQLite implementation
from .sqlite_database import SQLiteDatabase, get_db, reset_db

# For now, just use SQLite as the Database class
Database = SQLiteDatabase

# Get the global instance
db = get_db()

# Export everything needed
__all__ = ['Database', 'db', 'get_db', 'reset_db']