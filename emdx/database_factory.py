"""Database factory for lazy initialization of database connections."""

import threading
from typing import Optional
from weakref import WeakSet

from .config import get_config
from .sqlite_database import SQLiteDatabase


class DatabaseFactory:
    """Factory for creating and managing database instances."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._instance: Optional[SQLiteDatabase] = None
        self._initialized = False
        self._instances: WeakSet[SQLiteDatabase] = WeakSet()
    
    def get_database(self, db_path: Optional = None) -> SQLiteDatabase:
        """
        Get a database instance, creating one if needed.
        
        Args:
            db_path: Optional path to override default database location
            
        Returns:
            SQLiteDatabase instance
        """
        with self._lock:
            if self._instance is None or db_path is not None:
                config = get_config()
                actual_db_path = db_path if db_path is not None else config.db_path
                self._instance = SQLiteDatabase(actual_db_path)
                self._instances.add(self._instance)
            
            return self._instance
    
    def ensure_schema(self, db_instance: Optional[SQLiteDatabase] = None) -> None:
        """
        Ensure database schema is initialized.
        
        Args:
            db_instance: Optional database instance, uses default if None
        """
        with self._lock:
            if self._initialized:
                return
                
            db = db_instance or self.get_database()
            db.ensure_schema()
            self._initialized = True
    
    def reset(self) -> None:
        """Reset the factory state - useful for testing."""
        with self._lock:
            self._instance = None
            self._initialized = False
            # Clear all weak references
            self._instances.clear()


# Global factory instance
_factory = DatabaseFactory()


def get_database(db_path: Optional = None) -> SQLiteDatabase:
    """
    Get a database instance using the global factory.
    
    Args:
        db_path: Optional path to override default database location
        
    Returns:
        SQLiteDatabase instance
    """
    return _factory.get_database(db_path)


def ensure_database_schema(db_instance: Optional[SQLiteDatabase] = None) -> None:
    """
    Ensure database schema is initialized using the global factory.
    
    Args:
        db_instance: Optional database instance, uses default if None
    """
    _factory.ensure_schema(db_instance)


def reset_database_factory() -> None:
    """Reset the global database factory - useful for testing."""
    _factory.reset()