"""Tests for the caching layer."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from emdx.services.cache import (
    AccessCountBuffer,
    CacheEntry,
    CacheManager,
    CacheStats,
    TTLCache,
    cached,
    get_access_buffer,
)


class TestCacheStats:
    """Tests for CacheStats dataclass."""

    def test_hit_rate_calculation(self):
        """Test hit rate is calculated correctly."""
        stats = CacheStats(hits=70, misses=30)
        assert stats.hit_rate == 70.0

    def test_hit_rate_zero_requests(self):
        """Test hit rate when no requests have been made."""
        stats = CacheStats(hits=0, misses=0)
        assert stats.hit_rate == 0.0

    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = CacheStats(
            hits=100, misses=50, evictions=5, expirations=3, current_size=45, max_size=100
        )
        result = stats.to_dict()
        assert result["hits"] == 100
        assert result["misses"] == 50
        assert result["evictions"] == 5
        assert result["expirations"] == 3
        assert result["current_size"] == 45
        assert result["max_size"] == 100
        assert result["hit_rate_percent"] == pytest.approx(66.67, rel=0.01)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_is_expired_false(self):
        """Test entry is not expired when within TTL."""
        entry = CacheEntry(value="test", expires_at=time.time() + 100)
        assert not entry.is_expired()

    def test_is_expired_true(self):
        """Test entry is expired when past TTL."""
        entry = CacheEntry(value="test", expires_at=time.time() - 1)
        assert entry.is_expired()


class TestTTLCache:
    """Tests for TTLCache class."""

    def test_basic_set_get(self):
        """Test basic set and get operations."""
        cache = TTLCache[str](maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_nonexistent_key(self):
        """Test getting a key that doesn't exist."""
        cache = TTLCache[str](maxsize=10, ttl=60)
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = TTLCache[str](maxsize=10, ttl=0.1)  # 100ms TTL
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

        time.sleep(0.15)  # Wait for expiration
        assert cache.get("key1") is None

    def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        cache = TTLCache[str](maxsize=3, ttl=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1 to make it recently used
        cache.get("key1")

        # Add another item, should evict key2 (least recently used)
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"  # Was accessed, kept
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"  # Kept
        assert cache.get("key4") == "value4"  # New entry

    def test_delete(self):
        """Test deleting cache entries."""
        cache = TTLCache[str](maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert cache.delete("key1") is True
        assert cache.get("key1") is None
        assert cache.delete("nonexistent") is False

    def test_clear(self):
        """Test clearing all cache entries."""
        cache = TTLCache[str](maxsize=10, ttl=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        cleared = cache.clear()
        assert cleared == 2
        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_contains(self):
        """Test __contains__ method."""
        cache = TTLCache[str](maxsize=10, ttl=60)
        cache.set("key1", "value1")
        assert "key1" in cache
        assert "nonexistent" not in cache

    def test_cleanup_expired(self):
        """Test cleaning up expired entries."""
        cache = TTLCache[str](maxsize=10, ttl=0.1)
        cache.set("key1", "value1")
        cache.set("key2", "value2")

        time.sleep(0.15)

        removed = cache.cleanup_expired()
        assert removed == 2
        assert cache.stats.current_size == 0

    def test_stats_tracking(self):
        """Test that statistics are tracked correctly."""
        cache = TTLCache[str](maxsize=10, ttl=60)

        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.stats
        assert stats.hits == 2
        assert stats.misses == 1
        assert stats.current_size == 1

    def test_thread_safety(self):
        """Test that cache operations are thread-safe."""
        cache = TTLCache[int](maxsize=1000, ttl=60)
        errors = []

        def writer(start, count):
            try:
                for i in range(count):
                    cache.set(f"key-{start + i}", start + i)
            except Exception as e:
                errors.append(e)

        def reader(count):
            try:
                for i in range(count):
                    cache.get(f"key-{i}")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=(0, 100)),
            threading.Thread(target=writer, args=(100, 100)),
            threading.Thread(target=reader, args=(200,)),
            threading.Thread(target=reader, args=(200,)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0


class TestCacheManager:
    """Tests for CacheManager singleton."""

    def setup_method(self):
        """Reset CacheManager before each test."""
        CacheManager.reset_instance()

    def teardown_method(self):
        """Clean up after each test."""
        CacheManager.reset_instance()

    def test_singleton(self):
        """Test that CacheManager is a singleton."""
        manager1 = CacheManager.instance()
        manager2 = CacheManager.instance()
        assert manager1 is manager2

    def test_default_caches_registered(self):
        """Test that default caches are registered."""
        manager = CacheManager.instance()
        assert manager.get_cache("documents") is not None
        assert manager.get_cache("tags") is not None
        assert manager.get_cache("search") is not None
        assert manager.get_cache("aggregations") is not None

    def test_register_custom_cache(self):
        """Test registering a custom cache."""
        manager = CacheManager.instance()
        custom_cache = TTLCache[str](maxsize=50, ttl=30, name="custom")
        manager.register("custom", custom_cache)
        assert manager.get_cache("custom") is custom_cache

    def test_invalidate_specific_key(self):
        """Test invalidating a specific key."""
        manager = CacheManager.instance()
        cache = manager.get_cache("documents")
        cache.set("doc:1", {"id": 1, "title": "Test"})

        result = manager.invalidate("documents", "doc:1")
        assert result is True
        assert cache.get("doc:1") is None

    def test_invalidate_entire_cache(self):
        """Test invalidating entire cache."""
        manager = CacheManager.instance()
        cache = manager.get_cache("documents")
        cache.set("doc:1", {"id": 1})
        cache.set("doc:2", {"id": 2})

        result = manager.invalidate("documents")
        assert result is True
        assert cache.stats.current_size == 0

    def test_clear_all(self):
        """Test clearing all caches."""
        manager = CacheManager.instance()

        # Add some entries to various caches
        manager.get_cache("documents").set("key1", "value1")
        manager.get_cache("tags").set("key2", "value2")

        results = manager.clear_all()
        assert sum(results.values()) >= 2

    def test_get_stats(self):
        """Test getting cache statistics."""
        manager = CacheManager.instance()
        cache = manager.get_cache("documents")
        cache.set("key1", "value1")
        cache.get("key1")

        stats = manager.get_stats("documents")
        assert stats["hits"] >= 1
        assert stats["current_size"] >= 1

    def test_get_total_stats(self):
        """Test getting total statistics across all caches."""
        manager = CacheManager.instance()

        # Add operations to multiple caches
        manager.get_cache("documents").set("key1", "value1")
        manager.get_cache("documents").get("key1")
        manager.get_cache("tags").set("key2", "value2")
        manager.get_cache("tags").get("nonexistent")

        total = manager.get_total_stats()
        assert total["hits"] >= 1
        assert total["misses"] >= 1
        assert total["cache_count"] >= 4

    def test_enabled_disabled(self):
        """Test enabling/disabling caching."""
        manager = CacheManager.instance()
        cache = manager.get_cache("documents")
        cache.set("key1", "value1")

        # Disable clears caches
        manager.enabled = False
        assert manager.enabled is False
        assert cache.stats.current_size == 0

        # Re-enable
        manager.enabled = True
        assert manager.enabled is True


class TestCachedDecorator:
    """Tests for the @cached decorator."""

    def setup_method(self):
        """Reset CacheManager before each test."""
        CacheManager.reset_instance()

    def teardown_method(self):
        """Clean up after each test."""
        CacheManager.reset_instance()

    def test_basic_caching(self):
        """Test that function results are cached."""
        call_count = 0

        @cached("documents")
        def get_data(key: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"key": key, "data": "expensive_computation"}

        # First call - should execute function
        result1 = get_data("test")
        assert call_count == 1
        assert result1["key"] == "test"

        # Second call - should return cached value
        result2 = get_data("test")
        assert call_count == 1  # Function not called again
        assert result2 == result1

    def test_cache_miss_on_different_args(self):
        """Test that different arguments result in cache misses."""
        call_count = 0

        @cached("documents")
        def get_data(key: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"key": key}

        get_data("key1")
        get_data("key2")
        assert call_count == 2

    def test_custom_key_function(self):
        """Test using a custom key function."""
        call_count = 0

        @cached("documents", key_func=lambda x, **kw: x)
        def get_data(key: str, metadata: dict = None) -> dict:
            nonlocal call_count
            call_count += 1
            return {"key": key}

        get_data("test", metadata={"a": 1})
        get_data("test", metadata={"b": 2})  # Same key, should be cached
        assert call_count == 1

    def test_caching_disabled(self):
        """Test that caching can be disabled."""
        call_count = 0

        @cached("documents")
        def get_data(key: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"key": key}

        manager = CacheManager.instance()
        manager.enabled = False

        get_data("test")
        get_data("test")
        assert call_count == 2  # Function called each time

    def test_none_results_not_cached(self):
        """Test that None results are not cached."""
        call_count = 0

        @cached("documents")
        def get_data(key: str):
            nonlocal call_count
            call_count += 1
            return None

        get_data("test")
        get_data("test")
        assert call_count == 2  # None results not cached


class TestAccessCountBuffer:
    """Tests for AccessCountBuffer class."""

    def test_record_access(self):
        """Test recording access counts."""
        buffer = AccessCountBuffer(flush_threshold=100, flush_interval=60)
        buffer.record_access(1)
        buffer.record_access(1)
        buffer.record_access(2)

        assert buffer.buffered_docs == 2
        assert buffer.pending_count == 3

    def test_flush_on_threshold(self):
        """Test that flush happens when threshold is reached."""
        buffer = AccessCountBuffer(flush_threshold=3, flush_interval=9999)

        with patch.object(buffer, "flush") as mock_flush:
            buffer.record_access(1)
            buffer.record_access(2)
            assert mock_flush.call_count == 0

            buffer.record_access(3)  # Should trigger flush
            assert mock_flush.call_count == 1

    def test_flush_writes_to_database(self):
        """Test that flush actually writes to the database."""
        buffer = AccessCountBuffer(flush_threshold=100, flush_interval=60)
        buffer.record_access(1)
        buffer.record_access(1)

        # Mock the database connection module
        with patch("emdx.database.connection.db_connection") as mock_db:
            mock_conn = MagicMock()
            mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

            flushed = buffer.flush()
            assert flushed == 1  # One unique document
            mock_conn.execute.assert_called()

    def test_flush_clears_buffer(self):
        """Test that flush clears the buffer."""
        buffer = AccessCountBuffer(flush_threshold=100, flush_interval=60)
        buffer.record_access(1)
        buffer.record_access(2)

        with patch("emdx.database.connection.db_connection") as mock_db:
            mock_conn = MagicMock()
            mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

            buffer.flush()
            assert buffer.buffered_docs == 0
            assert buffer.pending_count == 0


class TestGetAccessBuffer:
    """Tests for the global access buffer."""

    def test_returns_singleton(self):
        """Test that get_access_buffer returns a singleton."""
        # Reset the global buffer
        import emdx.services.cache as cache_module
        cache_module._access_buffer = None

        buffer1 = get_access_buffer()
        buffer2 = get_access_buffer()
        assert buffer1 is buffer2


class TestSearchCaching:
    """Integration tests for search caching."""

    def setup_method(self):
        """Reset CacheManager before each test."""
        CacheManager.reset_instance()

    def teardown_method(self):
        """Clean up after each test."""
        CacheManager.reset_instance()

    def test_search_results_cached(self):
        """Test that search results are cached."""
        from emdx.database.search import _make_search_cache_key

        # Create cache keys for same search
        key1 = _make_search_cache_key("test query", None, 10, False, None, None, None, None)
        key2 = _make_search_cache_key("test query", None, 10, False, None, None, None, None)
        assert key1 == key2

        # Different queries should have different keys
        key3 = _make_search_cache_key("different query", None, 10, False, None, None, None, None)
        assert key1 != key3

    def test_search_cache_key_includes_all_params(self):
        """Test that cache key includes all search parameters."""
        from emdx.database.search import _make_search_cache_key

        key1 = _make_search_cache_key("test", "project1", 10, False, None, None, None, None)
        key2 = _make_search_cache_key("test", "project2", 10, False, None, None, None, None)
        assert key1 != key2

        key3 = _make_search_cache_key("test", None, 10, False, "2023-01-01", None, None, None)
        key4 = _make_search_cache_key("test", None, 10, False, None, None, None, None)
        assert key3 != key4
