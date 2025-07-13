"""Performance and regression tests for emoji alias system.

This test suite focuses on performance characteristics and regression testing
to ensure the emoji alias system scales well and doesn't introduce performance
regressions.
"""

import pytest
import time
import threading
from unittest.mock import patch, MagicMock

from test_fixtures import TestDatabase
from emdx.emoji_aliases import expand_aliases, normalize_tags, suggest_aliases
from emdx.tags import add_tags_to_document, search_by_tags, get_document_tags
# Core imports handled via CLI testing instead


class TestPerformanceBaseline:
    """Establish performance baselines for emoji alias operations."""

    def test_expand_aliases_performance(self):
        """Test performance of alias expansion with various input sizes."""
        # Small input (typical use case)
        small_input = ("gameplan", "active", "bug", "testing")
        start_time = time.time()
        for _ in range(1000):
            result = expand_aliases(small_input)
        small_time = time.time() - start_time
        
        # Should complete 1000 expansions very quickly
        assert small_time < 0.1
        assert result == ["🎯", "🚀", "🐛", "🧪"]
        
        # Medium input
        medium_input = tuple(["gameplan", "active"] * 10)
        start_time = time.time()
        for _ in range(100):
            result = expand_aliases(medium_input)
        medium_time = time.time() - start_time
        
        # Should still be fast
        assert medium_time < 0.1
        assert result == ["🎯", "🚀"]  # Duplicates removed
        
        # Large input (stress test)
        large_input = tuple(["gameplan", "active", "bug"] * 100)
        start_time = time.time()
        result = expand_aliases(large_input)
        large_time = time.time() - start_time
        
        # Even large inputs should be fast
        assert large_time < 0.01
        assert result == ["🎯", "🚀", "🐛"]

    def test_alias_lookup_performance(self):
        """Test performance of individual alias lookups."""
        from emdx.emoji_aliases import get_emoji_for_alias, is_alias
        
        # Test individual lookups
        aliases_to_test = ["gameplan", "active", "bug", "testing", "feature", "refactor"]
        
        start_time = time.time()
        for _ in range(10000):
            for alias in aliases_to_test:
                emoji = get_emoji_for_alias(alias)
                is_valid = is_alias(alias)
        lookup_time = time.time() - start_time
        
        # 60,000 lookups should be very fast
        assert lookup_time < 0.1

    def test_suggestion_performance(self):
        """Test performance of alias suggestion system."""
        test_queries = ["game", "act", "bu", "test", "feat"]
        
        start_time = time.time()
        for _ in range(1000):
            for query in test_queries:
                suggestions = suggest_aliases(query, limit=5)
        suggestion_time = time.time() - start_time
        
        # 5000 suggestion queries should complete quickly
        assert suggestion_time < 1.0

    def test_large_tag_list_normalization(self):
        """Test performance with very large tag lists."""
        # Create a large list mixing aliases, emojis, and custom tags
        large_tag_list = []
        for i in range(1000):
            if i % 4 == 0:
                large_tag_list.append("gameplan")
            elif i % 4 == 1:
                large_tag_list.append("🚀")
            elif i % 4 == 2:
                large_tag_list.append("active")
            else:
                large_tag_list.append(f"custom-{i}")
        
        start_time = time.time()
        result = normalize_tags(large_tag_list)
        normalize_time = time.time() - start_time
        
        # Should complete quickly even with 1000 tags
        assert normalize_time < 0.1
        
        # Should have removed duplicates and expanded aliases
        assert "🎯" in result
        assert "🚀" in result
        assert result.count("🎯") == 1  # No duplicates


class TestConcurrencyPerformance:
    """Test performance under concurrent access conditions."""

    def test_concurrent_alias_expansion(self):
        """Test alias expansion under concurrent access."""
        results = []
        errors = []
        
        def expand_worker():
            try:
                for _ in range(100):
                    result = expand_aliases(("gameplan", "active", "bug"))
                    results.append(result)
            except Exception as e:
                errors.append(str(e))
        
        # Start 10 concurrent workers
        threads = []
        start_time = time.time()
        
        for _ in range(10):
            thread = threading.Thread(target=expand_worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all to complete
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        
        # Should complete without errors
        assert len(errors) == 0
        assert len(results) == 1000  # 10 threads * 100 operations
        
        # Should complete in reasonable time
        assert (end_time - start_time) < 2.0
        
        # All results should be consistent
        expected = ["🎯", "🚀", "🐛"]
        for result in results:
            assert result == expected

    def test_concurrent_database_operations(self):
        """Test concurrent database operations with alias expansion."""
        test_db = TestDatabase(":memory:")
        results = []
        errors = []
        
        def db_worker(worker_id):
            try:
                with patch('emdx.tags.db', test_db):
                    for i in range(20):
                        doc_id = test_db.save_document(
                            f"Worker {worker_id} Doc {i}", 
                            f"Content {i}", 
                            "test"
                        )
                        add_tags_to_document(doc_id, ["gameplan", "active"])
                        stored_tags = get_document_tags(doc_id)
                        results.append((worker_id, i, stored_tags))
            except Exception as e:
                errors.append(f"Worker {worker_id}: {str(e)}")
        
        # Start 5 concurrent workers
        threads = []
        start_time = time.time()
        
        for worker_id in range(5):
            thread = threading.Thread(target=db_worker, args=(worker_id,))
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        end_time = time.time()
        
        # Should complete without errors
        assert len(errors) == 0, f"Errors: {errors}"
        assert len(results) == 100  # 5 workers * 20 operations
        
        # Should complete in reasonable time
        assert (end_time - start_time) < 5.0
        
        # All results should have correct tags
        expected_tags = ["🎯", "🚀"]
        for worker_id, doc_num, tags in results:
            assert set(tags) == set(expected_tags)


class TestMemoryPerformance:
    """Test memory usage characteristics of emoji alias system."""

    def test_memory_usage_with_large_datasets(self):
        """Test memory usage doesn't grow excessively with large datasets."""
        test_db = TestDatabase(":memory:")
        
        with patch('emdx.tags.db', test_db):
            # Create many documents with tags
            doc_ids = []
            for i in range(500):
                doc_id = test_db.save_document(f"Doc {i}", f"Content {i}", "memory-test")
                doc_ids.append(doc_id)
                
                # Add various tag combinations
                if i % 5 == 0:
                    add_tags_to_document(doc_id, ["gameplan", "active"])
                elif i % 5 == 1:
                    add_tags_to_document(doc_id, ["bug", "urgent"])
                elif i % 5 == 2:
                    add_tags_to_document(doc_id, ["feature", "testing"])
                elif i % 5 == 3:
                    add_tags_to_document(doc_id, ["refactor", "done"])
                else:
                    add_tags_to_document(doc_id, ["analysis", "notes"])
            
            # Perform many search operations
            search_terms = ["gameplan", "active", "bug", "urgent", "feature"]
            for _ in range(100):
                for term in search_terms:
                    results = search_by_tags([term], mode="any")
                    # Verify we get reasonable results
                    assert len(results) > 0
            
            # Memory usage should remain stable (hard to test directly,
            # but operations should continue to perform well)
            
            # Test final search performance
            start_time = time.time()
            final_results = search_by_tags(["gameplan"], mode="any")
            search_time = time.time() - start_time
            
            # Should still be fast after all operations
            assert search_time < 0.5
            assert len(final_results) == 100  # Every 5th document

    def test_caching_effectiveness(self):
        """Test that caching improves performance for repeated operations."""
        # Test expand_aliases caching
        test_input = ("gameplan", "active", "bug", "testing", "feature")
        
        # First call (cache miss)
        start_time = time.time()
        result1 = expand_aliases(test_input)
        first_time = time.time() - start_time
        
        # Subsequent calls (cache hits)
        start_time = time.time()
        for _ in range(1000):
            result2 = expand_aliases(test_input)
        cached_time = time.time() - start_time
        
        # Results should be identical
        assert result1 == result2
        
        # Cached calls should be much faster
        assert cached_time < first_time * 10  # Allow for some variance
        
        # Both should still be very fast
        assert first_time < 0.01
        assert cached_time < 0.1


class TestRegressionPrevention:
    """Tests to prevent performance regressions in emoji alias system."""

    def test_alias_expansion_time_complexity(self):
        """Test that alias expansion scales linearly with input size."""
        # Test with increasing input sizes
        sizes = [10, 50, 100, 500]
        times = []
        
        for size in sizes:
            # Create input with mixed aliases
            test_input = tuple(["gameplan", "active", "bug"] * (size // 3))
            
            start_time = time.time()
            result = expand_aliases(test_input)
            elapsed = time.time() - start_time
            times.append(elapsed)
            
            # Verify correctness
            assert result == ["🎯", "🚀", "🐛"]
        
        # Times should scale reasonably (not exponentially)
        for i in range(1, len(times)):
            # Each step shouldn't be more than 10x slower than previous
            assert times[i] < times[i-1] * 10

    def test_search_performance_with_many_tags(self):
        """Test search performance doesn't degrade with many tags per document."""
        test_db = TestDatabase(":memory:")
        
        with patch('emdx.tags.db', test_db):
            # Create documents with increasing numbers of tags
            for doc_num in range(50):
                doc_id = test_db.save_document(f"Doc {doc_num}", "Content", "perf-test")
                
                # Add increasing number of tags (mix of aliases and custom)
                num_tags = min(doc_num + 1, 20)  # Cap at 20 tags
                tags = []
                aliases = ["gameplan", "active", "bug", "testing", "feature"]
                
                for i in range(num_tags):
                    if i < len(aliases):
                        tags.append(aliases[i])
                    else:
                        tags.append(f"custom-{i}")
                
                add_tags_to_document(doc_id, tags)
            
            # Test search performance
            search_times = []
            for _ in range(10):
                start_time = time.time()
                results = search_by_tags(["gameplan"], mode="any")
                search_time = time.time() - start_time
                search_times.append(search_time)
                
                # Should find documents
                assert len(results) > 0
            
            # All searches should be reasonably fast
            max_search_time = max(search_times)
            avg_search_time = sum(search_times) / len(search_times)
            
            assert max_search_time < 0.1
            assert avg_search_time < 0.05

    def test_no_memory_leaks_in_repeated_operations(self):
        """Test for memory leaks in repeated alias operations."""
        # Perform many repeated operations
        for cycle in range(10):
            # Alias expansion
            for _ in range(100):
                result = expand_aliases(("gameplan", "active", "bug"))
                assert result == ["🎯", "🚀", "🐛"]
            
            # Suggestion queries
            for _ in range(50):
                suggestions = suggest_aliases("game", limit=5)
                assert len(suggestions) > 0
            
            # Normalization
            for _ in range(50):
                normalized = normalize_tags(["gameplan", "🚀", "active", "custom"])
                assert "🎯" in normalized
                assert "🚀" in normalized
        
        # If we complete all cycles without hanging or crashing,
        # memory usage is acceptable


class TestPerformanceRegression:
    """Specific tests to catch performance regressions."""

    def test_baseline_save_and_search_performance(self):
        """Establish baseline performance for save and search operations."""
        test_db = TestDatabase(":memory:")
        
        with patch('emdx.core.db', test_db), \
             patch('emdx.tags.db', test_db):
            
            # Baseline save performance
            start_time = time.time()
            for i in range(100):
                doc_id = test_db.save_document(f"Perf Doc {i}", f"Content {i}", "perf")
                add_tags_to_document(doc_id, ["gameplan", "active", "testing"])
            save_time = time.time() - start_time
            
            # Should save 100 documents quickly
            assert save_time < 2.0
            
            # Baseline search performance
            start_time = time.time()
            for _ in range(50):
                results = search_by_tags(["gameplan"], mode="any")
                assert len(results) == 100
            search_time = time.time() - start_time
            
            # Should complete 50 searches quickly
            assert search_time < 1.0

    def test_worst_case_performance_scenarios(self):
        """Test performance in worst-case scenarios."""
        # Worst case: Many documents, many tags each, complex searches
        test_db = TestDatabase(":memory:")
        
        with patch('emdx.tags.db', test_db):
            # Create documents with many overlapping tags
            all_aliases = ["gameplan", "active", "bug", "testing", "feature", 
                          "refactor", "analysis", "notes", "documentation"]
            
            for i in range(200):
                doc_id = test_db.save_document(f"Complex Doc {i}", f"Content {i}", "complex")
                # Each document gets 5-7 random tags
                import random
                num_tags = random.randint(5, 7)
                tags = random.sample(all_aliases, num_tags)
                add_tags_to_document(doc_id, tags)
            
            # Worst case search: multiple tags with different modes
            start_time = time.time()
            
            # Complex "all" mode search
            results = search_by_tags(["gameplan", "active", "testing"], mode="all")
            complex_search_time = time.time() - start_time
            
            # Should complete even complex searches quickly
            assert complex_search_time < 1.0
            
            # Results should be reasonable
            assert isinstance(results, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])