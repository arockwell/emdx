"""
Caching infrastructure for EMDX performance optimization.

Provides TTL-based and LRU caching with thread safety, metrics tracking,
and cache management utilities.

Memory Safety Considerations:
- All caches are bounded by default (maxsize=1000)
- TTL expiration prevents unbounded growth
- Explicit cleanup via shutdown hooks
- Cache statistics available for monitoring
"""

import atexit
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Generic, Hashable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    current_size: int = 0
    max_size: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate hit rate as percentage."""
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return (self.hits / total) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for reporting."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "current_size": self.current_size,
            "max_size": self.max_size,
            "hit_rate_percent": round(self.hit_rate, 2),
        }


@dataclass
class CacheEntry(Generic[T]):
    """A single cache entry with expiration tracking."""

    value: T
    expires_at: float  # Unix timestamp
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        return time.time() > self.expires_at


class TTLCache(Generic[T]):
    """
    Thread-safe TTL cache with LRU eviction.

    Features:
    - TTL-based expiration
    - LRU eviction when maxsize reached
    - Thread-safe operations
    - Performance metrics

    Usage:
        cache = TTLCache[dict](maxsize=100, ttl=300)  # 100 items, 5 min TTL
        cache.set("key", {"data": "value"})
        result = cache.get("key")  # Returns {"data": "value"} or None
    """

    def __init__(
        self,
        maxsize: int = 1000,
        ttl: float = 300,  # 5 minutes default
        name: str = "cache",
    ):
        """
        Initialize TTL cache.

        Args:
            maxsize: Maximum number of entries
            ttl: Time-to-live in seconds for entries
            name: Name for identification in logs/stats
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self.name = name
        self._cache: OrderedDict[Hashable, CacheEntry[T]] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = CacheStats(max_size=maxsize)

    def get(self, key: Hashable) -> T | None:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats.misses += 1
                return None

            if entry.is_expired():
                # Remove expired entry
                del self._cache[key]
                self._stats.expirations += 1
                self._stats.misses += 1
                self._stats.current_size = len(self._cache)
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._stats.hits += 1
            return entry.value

    def set(self, key: Hashable, value: T, ttl: float | None = None) -> None:
        """
        Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional custom TTL (uses default if not specified)
        """
        with self._lock:
            actual_ttl = ttl if ttl is not None else self.ttl
            expires_at = time.time() + actual_ttl

            # Remove if already exists (to update order)
            if key in self._cache:
                del self._cache[key]

            # Evict oldest if at capacity
            while len(self._cache) >= self.maxsize:
                self._cache.popitem(last=False)
                self._stats.evictions += 1

            self._cache[key] = CacheEntry(value=value, expires_at=expires_at)
            self._stats.current_size = len(self._cache)

    def delete(self, key: Hashable) -> bool:
        """
        Delete an entry from the cache.

        Args:
            key: Cache key

        Returns:
            True if entry was deleted, False if not found
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats.current_size = len(self._cache)
                return True
            return False

    def clear(self) -> int:
        """
        Clear all entries from the cache.

        Returns:
            Number of entries cleared
        """
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats.current_size = 0
            return count

    def __contains__(self, key: Hashable) -> bool:
        """Check if key exists and is not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[key]
                self._stats.expirations += 1
                self._stats.current_size = len(self._cache)
                return False
            return True

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries.

        Returns:
            Number of entries removed
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items() if entry.is_expired()
            ]
            for key in expired_keys:
                del self._cache[key]
            self._stats.expirations += len(expired_keys)
            self._stats.current_size = len(self._cache)
            return len(expired_keys)

    @property
    def stats(self) -> CacheStats:
        """Get current cache statistics."""
        with self._lock:
            self._stats.current_size = len(self._cache)
            return self._stats


class CacheManager:
    """
    Singleton manager for all application caches.

    Provides centralized access to caches, statistics, and cache operations.

    Usage:
        cache_manager = CacheManager.instance()
        cache_manager.register("documents", TTLCache(maxsize=500, ttl=300))
        cache_manager.get_cache("documents").set("key", value)
    """

    _instance: "CacheManager | None" = None
    _lock = threading.Lock()

    def __init__(self):
        """Initialize cache manager with default caches."""
        self._caches: dict[str, TTLCache] = {}
        self._enabled = True
        self._initialize_default_caches()

    @classmethod
    def instance(cls) -> "CacheManager":
        """Get singleton instance of CacheManager."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton instance. Primarily for testing."""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.clear_all()
            cls._instance = None

    def _initialize_default_caches(self) -> None:
        """Initialize standard caches used by the application."""
        # Document cache - short TTL since documents can change
        self.register("documents", TTLCache(maxsize=500, ttl=120, name="documents"))

        # Tag cache - longer TTL since tags change less frequently
        self.register("tags", TTLCache(maxsize=1000, ttl=300, name="tags"))

        # Search cache - medium TTL
        self.register("search", TTLCache(maxsize=100, ttl=120, name="search"))

        # Aggregation cache - stats and summaries
        self.register("aggregations", TTLCache(maxsize=50, ttl=60, name="aggregations"))

    def register(self, name: str, cache: TTLCache) -> None:
        """
        Register a cache with the manager.

        Args:
            name: Unique identifier for the cache
            cache: The TTLCache instance
        """
        self._caches[name] = cache
        logger.debug("Registered cache: %s (maxsize=%d, ttl=%ds)",
                     name, cache.maxsize, cache.ttl)

    def get_cache(self, name: str) -> TTLCache | None:
        """
        Get a registered cache by name.

        Args:
            name: Cache identifier

        Returns:
            The cache instance or None if not found
        """
        return self._caches.get(name)

    def invalidate(self, cache_name: str, key: Hashable | None = None) -> bool:
        """
        Invalidate cache entries.

        Args:
            cache_name: Name of the cache
            key: Optional specific key to invalidate (clears all if None)

        Returns:
            True if cache was found and operation completed
        """
        cache = self._caches.get(cache_name)
        if cache is None:
            return False

        if key is None:
            cache.clear()
        else:
            cache.delete(key)
        return True

    def clear_all(self) -> dict[str, int]:
        """
        Clear all registered caches.

        Returns:
            Dictionary mapping cache name to number of entries cleared
        """
        results = {}
        for name, cache in self._caches.items():
            results[name] = cache.clear()
        return results

    def get_stats(self, cache_name: str | None = None) -> dict[str, Any]:
        """
        Get statistics for caches.

        Args:
            cache_name: Optional specific cache (returns all if None)

        Returns:
            Dictionary of cache statistics
        """
        if cache_name:
            cache = self._caches.get(cache_name)
            if cache:
                return cache.stats.to_dict()
            return {}

        return {name: cache.stats.to_dict() for name, cache in self._caches.items()}

    def get_total_stats(self) -> dict[str, Any]:
        """
        Get aggregated statistics across all caches.

        Returns:
            Dictionary with total hits, misses, etc.
        """
        total = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
            "total_size": 0,
            "cache_count": len(self._caches),
        }

        for cache in self._caches.values():
            stats = cache.stats
            total["hits"] += stats.hits
            total["misses"] += stats.misses
            total["evictions"] += stats.evictions
            total["expirations"] += stats.expirations
            total["total_size"] += stats.current_size

        total_requests = total["hits"] + total["misses"]
        total["hit_rate_percent"] = (
            round((total["hits"] / total_requests) * 100, 2) if total_requests > 0 else 0
        )

        return total

    def cleanup_expired(self) -> dict[str, int]:
        """
        Clean up expired entries in all caches.

        Returns:
            Dictionary mapping cache name to number of entries cleaned
        """
        results = {}
        for name, cache in self._caches.items():
            results[name] = cache.cleanup_expired()
        return results

    @property
    def enabled(self) -> bool:
        """Whether caching is enabled globally."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        """Enable or disable caching globally."""
        self._enabled = value
        if not value:
            self.clear_all()


def cached(
    cache_name: str,
    ttl: float | None = None,
    key_func: Callable[..., Hashable] | None = None,
) -> Callable:
    """
    Decorator for caching function results.

    Args:
        cache_name: Name of the cache to use (must be registered)
        ttl: Optional TTL override for this function
        key_func: Optional function to generate cache key from args

    Usage:
        @cached("documents", ttl=60)
        def get_document(doc_id: int) -> dict:
            # Database query here
            pass

        @cached("search", key_func=lambda q, **kw: (q, kw.get("project")))
        def search(query: str, project: str | None = None) -> list:
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            manager = CacheManager.instance()

            # Skip caching if disabled
            if not manager.enabled:
                return func(*args, **kwargs)

            cache = manager.get_cache(cache_name)
            if cache is None:
                logger.warning("Cache '%s' not registered, calling function directly", cache_name)
                return func(*args, **kwargs)

            # Generate cache key
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # Default: use all args and sorted kwargs
                cache_key = (args, tuple(sorted(kwargs.items())))

            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result

            # Call function and cache result
            result = func(*args, **kwargs)
            if result is not None:
                cache.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


# Access count debouncing for documents
class AccessCountBuffer:
    """
    Buffer for debouncing access count updates.

    Instead of writing to the database on every document access,
    this buffers counts and flushes periodically.
    """

    def __init__(
        self,
        flush_threshold: int = 100,
        flush_interval: float = 60.0,
    ):
        """
        Initialize access count buffer.

        Args:
            flush_threshold: Number of buffered updates before auto-flush
            flush_interval: Seconds between auto-flushes
        """
        self._buffer: dict[int, int] = {}
        self._lock = threading.Lock()
        self._last_flush = time.time()
        self._flush_threshold = flush_threshold
        self._flush_interval = flush_interval
        self._pending_flushes = 0

    def record_access(self, doc_id: int) -> None:
        """
        Record a document access.

        Args:
            doc_id: The document ID that was accessed
        """
        with self._lock:
            self._buffer[doc_id] = self._buffer.get(doc_id, 0) + 1
            self._pending_flushes += 1

            # Check if we should flush
            should_flush = (
                len(self._buffer) >= self._flush_threshold
                or time.time() - self._last_flush > self._flush_interval
            )

        if should_flush:
            self.flush()

    def flush(self) -> int:
        """
        Flush buffered access counts to the database.

        Returns:
            Number of documents updated
        """
        with self._lock:
            if not self._buffer:
                return 0

            buffer_copy = self._buffer.copy()
            self._buffer.clear()
            self._last_flush = time.time()
            self._pending_flushes = 0

        # Perform the database update outside the lock
        from emdx.database.connection import db_connection

        updated = 0
        try:
            with db_connection.get_connection() as conn:
                for doc_id, count in buffer_copy.items():
                    conn.execute(
                        """
                        UPDATE documents
                        SET access_count = access_count + ?,
                            accessed_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND is_deleted = FALSE
                        """,
                        (count, doc_id),
                    )
                    updated += 1
                conn.commit()
        except Exception as e:
            logger.error("Failed to flush access counts: %s", e)

        return updated

    @property
    def pending_count(self) -> int:
        """Number of pending access count updates."""
        with self._lock:
            return self._pending_flushes

    @property
    def buffered_docs(self) -> int:
        """Number of unique documents in buffer."""
        with self._lock:
            return len(self._buffer)


# Global access count buffer instance
_access_buffer: AccessCountBuffer | None = None


def get_access_buffer() -> AccessCountBuffer:
    """Get the global access count buffer instance."""
    global _access_buffer
    if _access_buffer is None:
        _access_buffer = AccessCountBuffer()
    return _access_buffer


def _shutdown_handler() -> None:
    """Clean up caches and flush buffers on shutdown."""
    global _access_buffer

    # Flush access buffer
    if _access_buffer is not None:
        try:
            flushed = _access_buffer.flush()
            if flushed > 0:
                logger.debug("Flushed %d access count updates on shutdown", flushed)
        except Exception as e:
            logger.error("Error flushing access buffer on shutdown: %s", e)

    # Clear caches
    try:
        CacheManager.instance().clear_all()
    except Exception as e:
        logger.error("Error clearing caches on shutdown: %s", e)


# Register shutdown handler
atexit.register(_shutdown_handler)
