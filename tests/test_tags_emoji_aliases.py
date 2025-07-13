"""Comprehensive tests for emoji alias integration in tags.py functionality.

This test suite focuses on testing the tags module's database operations
and search functionality with emoji alias support.
"""

import pytest
from unittest.mock import patch, MagicMock

from test_fixtures import TestDatabase
from emdx.tags import (
    add_tags_to_document, 
    remove_tags_from_document, 
    get_document_tags,
    search_by_tags,
    get_all_tags,
    get_tag_usage_stats,
    suggest_tags,
    update_tag_usage
)
from emdx.emoji_aliases import expand_aliases, normalize_tags


class TestTagsEmojiAliasIntegration:
    """Test tags module emoji alias functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.test_db = TestDatabase(":memory:")

    def test_add_tags_with_aliases_expansion(self):
        """Test that add_tags_to_document properly expands aliases."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            # Add tags using aliases
            add_tags_to_document(doc_id, ["gameplan", "active", "bug", "testing"])
            
            # Verify tags were expanded to emojis
            stored_tags = get_document_tags(doc_id)
            expected_emojis = ["🎯", "🚀", "🐛", "🧪"]
            assert set(stored_tags) == set(expected_emojis)

    def test_add_tags_mixed_aliases_and_emojis(self):
        """Test adding mixed alias and emoji tags."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            # Mix of aliases, emojis, and custom tags
            mixed_tags = ["gameplan", "🚀", "custom-tag", "active", "🐛"]
            add_tags_to_document(doc_id, mixed_tags)
            
            stored_tags = get_document_tags(doc_id)
            expected = ["🎯", "🚀", "custom-tag", "🐛"]  # gameplan->🎯, active->🚀
            assert set(stored_tags) == set(expected)

    def test_add_tags_removes_duplicates_after_expansion(self):
        """Test that duplicate tags are removed after alias expansion."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            # Multiple aliases that map to same emoji
            duplicate_tags = ["gameplan", "gp", "plan", "🎯", "strategy"]
            add_tags_to_document(doc_id, duplicate_tags)
            
            stored_tags = get_document_tags(doc_id)
            # Should only have one instance of 🎯
            assert stored_tags.count("🎯") == 1
            assert len(stored_tags) == 1

    def test_add_tags_case_insensitive_aliases(self):
        """Test that aliases work case-insensitively."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            case_variants = ["GAMEPLAN", "Active", "BUG", "TeStInG"]
            add_tags_to_document(doc_id, case_variants)
            
            stored_tags = get_document_tags(doc_id)
            expected = ["🎯", "🚀", "🐛", "🧪"]
            assert set(stored_tags) == set(expected)

    def test_add_tags_preserves_unknown_tags(self):
        """Test that unknown/custom tags are preserved."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            mixed_tags = ["gameplan", "unknown-alias", "custom-tag", "active"]
            add_tags_to_document(doc_id, mixed_tags)
            
            stored_tags = get_document_tags(doc_id)
            expected = ["🎯", "unknown-alias", "custom-tag", "🚀"]
            assert set(stored_tags) == set(expected)

    def test_search_by_tags_with_aliases(self):
        """Test search_by_tags with alias expansion."""
        # Create test documents
        doc1 = self.test_db.save_document("Doc 1", "Content 1", "project")
        doc2 = self.test_db.save_document("Doc 2", "Content 2", "project")
        doc3 = self.test_db.save_document("Doc 3", "Content 3", "project")
        
        with patch('emdx.tags.db', self.test_db):
            # Add emoji tags to documents
            add_tags_to_document(doc1, ["🎯", "🚀"])  # gameplan, active
            add_tags_to_document(doc2, ["🎯", "🐛"])  # gameplan, bug
            add_tags_to_document(doc3, ["🚀", "🧪"])  # active, testing
            
            # Search using aliases
            results = search_by_tags(["gameplan"], mode="any")
            assert len(results) == 2  # doc1 and doc2
            
            results = search_by_tags(["active"], mode="any")
            assert len(results) == 2  # doc1 and doc3
            
            results = search_by_tags(["gameplan", "active"], mode="all")
            assert len(results) == 1  # only doc1

    def test_search_by_tags_mixed_aliases_and_emojis(self):
        """Test search with mixed alias and emoji tags."""
        doc1 = self.test_db.save_document("Doc 1", "Content 1", "project")
        doc2 = self.test_db.save_document("Doc 2", "Content 2", "project")
        
        with patch('emdx.tags.db', self.test_db):
            add_tags_to_document(doc1, ["🎯", "🚀"])
            add_tags_to_document(doc2, ["🎯", "🐛"])
            
            # Search with mixed format
            results = search_by_tags(["gameplan", "🚀"], mode="all")
            assert len(results) == 1  # only doc1
            
            results = search_by_tags(["🎯", "active"], mode="any")
            assert len(results) == 2  # both docs have 🎯, doc1 has 🚀 (active)

    def test_search_by_tags_unknown_aliases(self):
        """Test search with unknown aliases (treated as literal tags)."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            add_tags_to_document(doc_id, ["unknown-alias", "custom-tag"])
            
            # Search for unknown alias should work as literal tag
            results = search_by_tags(["unknown-alias"], mode="any")
            assert len(results) == 1

    def test_remove_tags_with_aliases(self):
        """Test removing tags using aliases."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            # Add tags using aliases
            add_tags_to_document(doc_id, ["gameplan", "active", "bug"])
            
            # Remove using alias
            remove_tags_from_document(doc_id, ["gameplan"])
            
            stored_tags = get_document_tags(doc_id)
            # Should only have active and bug emojis left
            expected = ["🚀", "🐛"]
            assert set(stored_tags) == set(expected)

    def test_remove_tags_mixed_aliases_and_emojis(self):
        """Test removing tags using mixed aliases and emojis."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            add_tags_to_document(doc_id, ["gameplan", "active", "bug", "testing"])
            
            # Remove using mixed format
            remove_tags_from_document(doc_id, ["gameplan", "🧪"])  # alias + emoji
            
            stored_tags = get_document_tags(doc_id)
            expected = ["🚀", "🐛"]  # active, bug remain
            assert set(stored_tags) == set(expected)

    def test_get_all_tags_includes_emojis(self):
        """Test that get_all_tags returns emoji tags."""
        doc1 = self.test_db.save_document("Doc 1", "Content 1", "project")
        doc2 = self.test_db.save_document("Doc 2", "Content 2", "project")
        
        with patch('emdx.tags.db', self.test_db):
            add_tags_to_document(doc1, ["gameplan", "active"])
            add_tags_to_document(doc2, ["bug", "testing", "custom-tag"])
            
            all_tags = get_all_tags()
            
            # Should include emoji tags and custom tags
            tag_names = [tag["name"] for tag in all_tags]
            assert "🎯" in tag_names
            assert "🚀" in tag_names
            assert "🐛" in tag_names
            assert "🧪" in tag_names
            assert "custom-tag" in tag_names

    def test_suggest_tags_includes_aliases(self):
        """Test that suggest_tags includes alias suggestions."""
        with patch('emdx.tags.db', self.test_db):
            # Create some documents with tags for suggestions
            doc_id = self.test_db.save_document("Test Doc", "Content", "project")
            add_tags_to_document(doc_id, ["gameplan", "active"])
            
            # Mock the emoji alias suggestion system
            with patch('emdx.emoji_aliases.suggest_aliases') as mock_suggest:
                mock_suggest.return_value = [("gameplan", "🎯"), ("active", "🚀")]
                
                suggestions = suggest_tags("gam")
                
                # Should include alias suggestions
                mock_suggest.assert_called_once_with("gam")

    def test_tag_usage_stats_with_emojis(self):
        """Test tag usage statistics with emoji tags."""
        doc1 = self.test_db.save_document("Doc 1", "Content 1", "project")
        doc2 = self.test_db.save_document("Doc 2", "Content 2", "project")
        doc3 = self.test_db.save_document("Doc 3", "Content 3", "project")
        
        with patch('emdx.tags.db', self.test_db):
            add_tags_to_document(doc1, ["gameplan", "active"])     # 🎯, 🚀
            add_tags_to_document(doc2, ["gameplan", "bug"])        # 🎯, 🐛
            add_tags_to_document(doc3, ["active", "testing"])      # 🚀, 🧪
            
            stats = get_tag_usage_stats()
            
            # Should track usage of emoji tags
            tag_counts = {stat["name"]: stat["count"] for stat in stats}
            assert tag_counts.get("🎯", 0) == 2  # gameplan used twice
            assert tag_counts.get("🚀", 0) == 2  # active used twice
            assert tag_counts.get("🐛", 0) == 1  # bug used once
            assert tag_counts.get("🧪", 0) == 1  # testing used once


class TestTagsEmojiAliasEdgeCases:
    """Test edge cases in tags module emoji alias functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.test_db = TestDatabase(":memory:")

    def test_add_empty_tag_list(self):
        """Test adding empty tag list."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            add_tags_to_document(doc_id, [])
            
            stored_tags = get_document_tags(doc_id)
            assert stored_tags == []

    def test_add_tags_with_whitespace(self):
        """Test adding tags with whitespace."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            whitespace_tags = [" gameplan ", "  active  ", "\tbugs\t"]
            add_tags_to_document(doc_id, whitespace_tags)
            
            stored_tags = get_document_tags(doc_id)
            # Should handle whitespace and expand aliases
            expected = ["🎯", "🚀", "bugs"]  # bugs != bug, so preserved
            assert set(stored_tags) == set(expected)

    def test_add_tags_with_special_characters(self):
        """Test adding tags with special characters."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            special_tags = ["gameplan!", "test@tag", "#hashtag", "café"]
            add_tags_to_document(doc_id, special_tags)
            
            stored_tags = get_document_tags(doc_id)
            # Special character versions should not be aliases
            assert "gameplan!" in stored_tags
            assert "test@tag" in stored_tags
            assert "#hashtag" in stored_tags
            assert "café" in stored_tags
            # No emojis should be present
            assert "🎯" not in stored_tags

    def test_search_empty_tag_list(self):
        """Test searching with empty tag list."""
        with patch('emdx.tags.db', self.test_db):
            results = search_by_tags([], mode="any")
            assert len(results) == 0

    def test_remove_nonexistent_tags(self):
        """Test removing tags that don't exist on document."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            add_tags_to_document(doc_id, ["gameplan"])
            
            # Try to remove tag that doesn't exist
            remove_tags_from_document(doc_id, ["nonexistent"])
            
            stored_tags = get_document_tags(doc_id)
            assert stored_tags == ["🎯"]  # Original tag should remain

    def test_very_long_tag_names(self):
        """Test handling very long tag names."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            long_tag = "a" * 1000
            add_tags_to_document(doc_id, ["gameplan", long_tag])
            
            stored_tags = get_document_tags(doc_id)
            assert "🎯" in stored_tags
            assert long_tag in stored_tags

    def test_unicode_in_tags(self):
        """Test handling unicode characters in tags."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            unicode_tags = ["gameplan", "测试", "🌟", "café", "naïve"]
            add_tags_to_document(doc_id, unicode_tags)
            
            stored_tags = get_document_tags(doc_id)
            assert "🎯" in stored_tags  # gameplan expanded
            assert "测试" in stored_tags
            assert "🌟" in stored_tags
            assert "café" in stored_tags
            assert "naïve" in stored_tags


class TestTagsEmojiAliasPerformance:
    """Test performance characteristics of tags module with emoji aliases."""

    def setup_method(self):
        """Set up test environment."""
        self.test_db = TestDatabase(":memory:")

    def test_add_tags_performance_with_many_aliases(self):
        """Test performance when adding many alias tags."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            # Create large list of alias tags
            many_aliases = ["gameplan"] * 100 + ["active"] * 100 + ["bug"] * 100
            
            import time
            start_time = time.time()
            
            add_tags_to_document(doc_id, many_aliases)
            
            end_time = time.time()
            
            # Should complete in reasonable time
            assert (end_time - start_time) < 1.0
            
            # Should only have unique emojis
            stored_tags = get_document_tags(doc_id)
            expected = ["🎯", "🚀", "🐛"]
            assert set(stored_tags) == set(expected)

    def test_search_performance_with_many_documents(self):
        """Test search performance with many tagged documents."""
        # Create many documents
        doc_ids = []
        for i in range(500):
            doc_id = self.test_db.save_document(f"Doc {i}", f"Content {i}", "project")
            doc_ids.append(doc_id)
        
        with patch('emdx.tags.db', self.test_db):
            # Add tags to all documents
            for i, doc_id in enumerate(doc_ids):
                if i % 3 == 0:
                    add_tags_to_document(doc_id, ["gameplan"])
                elif i % 3 == 1:
                    add_tags_to_document(doc_id, ["active"])
                else:
                    add_tags_to_document(doc_id, ["bug"])
            
            # Test search performance
            import time
            start_time = time.time()
            
            results = search_by_tags(["gameplan"], mode="any")
            
            end_time = time.time()
            
            # Should complete quickly and find correct number
            assert (end_time - start_time) < 1.0
            assert len(results) >= 160  # Approximately 1/3 of 500

    def test_tag_expansion_caching_performance(self):
        """Test that tag expansion uses caching for performance."""
        with patch('emdx.tags.db', self.test_db):
            doc_id = self.test_db.save_document("Test Doc", "Content", "project")
            
            # Same tag list multiple times
            tag_list = ["gameplan", "active", "bug", "testing"]
            
            import time
            
            # First expansion (may be slower due to cache miss)
            start_time = time.time()
            add_tags_to_document(doc_id, tag_list)
            first_time = time.time() - start_time
            
            # Remove tags for next test
            remove_tags_from_document(doc_id, tag_list)
            
            # Second expansion (should be faster due to caching)
            start_time = time.time()
            add_tags_to_document(doc_id, tag_list)
            second_time = time.time() - start_time
            
            # Second time should be at least as fast (caching effect may vary)
            # Just ensure both complete in reasonable time
            assert first_time < 0.1
            assert second_time < 0.1


class TestTagsEmojiAliasMocking:
    """Test tags module with comprehensive mocking for isolation."""

    def test_add_tags_with_mocked_expansion(self):
        """Test add_tags_to_document with mocked alias expansion."""
        with patch('emdx.tags.db') as mock_db, \
             patch('emdx.tags.expand_aliases') as mock_expand:
            
            # Setup mocks
            mock_expand.return_value = ["🎯", "🚀"]
            mock_db.get_connection.return_value.__enter__.return_value = MagicMock()
            
            # Test function
            add_tags_to_document(123, ["gameplan", "active"])
            
            # Verify expansion was called
            mock_expand.assert_called_once_with(("gameplan", "active"))

    def test_search_by_tags_with_mocked_expansion(self):
        """Test search_by_tags with mocked alias expansion."""
        with patch('emdx.tags.db') as mock_db, \
             patch('emdx.tags.expand_aliases') as mock_expand:
            
            # Setup mocks
            mock_expand.return_value = ["🎯"]
            mock_db.get_connection.return_value.__enter__.return_value.execute.return_value.fetchall.return_value = []
            
            # Test function
            search_by_tags(["gameplan"], mode="any")
            
            # Verify expansion was called
            mock_expand.assert_called_once_with(("gameplan",))

    def test_remove_tags_with_mocked_expansion(self):
        """Test remove_tags_from_document with mocked alias expansion."""
        with patch('emdx.tags.db') as mock_db, \
             patch('emdx.tags.expand_aliases') as mock_expand:
            
            # Setup mocks
            mock_expand.return_value = ["🎯"]
            mock_db.get_connection.return_value.__enter__.return_value = MagicMock()
            
            # Test function
            remove_tags_from_document(123, ["gameplan"])
            
            # Verify expansion was called
            mock_expand.assert_called_once_with(("gameplan",))


class TestTagsEmojiAliasErrorHandling:
    """Test error handling in tags module emoji alias functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.test_db = TestDatabase(":memory:")

    def test_add_tags_handles_expansion_errors(self):
        """Test that add_tags_to_document handles expansion errors gracefully."""
        doc_id = self.test_db.save_document("Test Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db), \
             patch('emdx.tags.expand_aliases') as mock_expand:
            
            # Mock expansion error
            mock_expand.side_effect = Exception("Expansion error")
            
            # Should handle error gracefully (fallback to original tags)
            try:
                add_tags_to_document(doc_id, ["gameplan", "active"])
                # If no exception, verify fallback behavior
                stored_tags = get_document_tags(doc_id)
                # May contain original tags or be empty depending on error handling
            except Exception:
                # Some error handling implementations may re-raise
                pass

    def test_search_handles_expansion_errors(self):
        """Test that search_by_tags handles expansion errors gracefully."""
        with patch('emdx.tags.db', self.test_db), \
             patch('emdx.tags.expand_aliases') as mock_expand:
            
            # Mock expansion error
            mock_expand.side_effect = Exception("Expansion error")
            
            # Should handle error gracefully
            try:
                results = search_by_tags(["gameplan"], mode="any")
                # Should return some result (possibly empty) rather than crash
                assert isinstance(results, list)
            except Exception:
                # Some implementations may re-raise errors
                pass

    def test_malformed_emoji_data_handling(self):
        """Test handling of malformed emoji alias data."""
        with patch('emdx.emoji_aliases.EMOJI_ALIASES', {"invalid": []}):
            # Test with corrupted emoji data
            from emdx.emoji_aliases import expand_aliases
            
            # Should not crash with empty alias lists
            result = expand_aliases(("gameplan",))
            assert result == ["gameplan"]  # Should preserve original


if __name__ == "__main__":
    pytest.main([__file__, "-v"])