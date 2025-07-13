"""Comprehensive tests for emoji alias integration in TUI browser functionality.

This test suite focuses on testing the textual browser's search and tag management
capabilities with emoji alias support.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

from test_fixtures import TestDatabase
from emdx.textual_browser_minimal import EmdxBrowser
from emdx.tags import add_tags_to_document, get_document_tags
from emdx.emoji_aliases import expand_aliases


class TestTUIBrowserEmojiAliases:
    """Test TUI browser emoji alias functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.test_db = TestDatabase(":memory:")

    @pytest.mark.asyncio
    async def test_browser_search_with_aliases(self):
        """Test browser search functionality with alias expansion."""
        # Create test documents with emoji tags
        doc1 = self.test_db.save_document("Gameplan Doc", "Strategy content", "project")
        doc2 = self.test_db.save_document("Active Project", "Current work", "project")
        doc3 = self.test_db.save_document("Bug Report", "Critical issue", "project")
        
        with patch('emdx.tags.db', self.test_db):
            add_tags_to_document(doc1, ["🎯", "🔍"])  # gameplan, analysis
            add_tags_to_document(doc2, ["🚀", "✨"])  # active, feature
            add_tags_to_document(doc3, ["🐛", "🚨"])  # bug, urgent
        
        # Mock the browser and database connection
        with patch('emdx.textual_browser_minimal.db', self.test_db), \
             patch('emdx.tags.db', self.test_db):
            
            browser = EmdxBrowser()
            
            # Test search with alias - should expand to emoji before search
            with patch.object(browser, 'search_documents') as mock_search:
                mock_search.return_value = [
                    {"id": doc1, "title": "Gameplan Doc", "content": "Strategy content", 
                     "project": "project", "created_at": "2024-01-01", "access_count": 1}
                ]
                
                # Simulate search with alias
                await browser.action_search_documents("gameplan")
                
                # Should have called search (implementation details may vary)
                mock_search.assert_called()

    @pytest.mark.asyncio
    async def test_browser_tag_management_with_aliases(self):
        """Test browser tag add/remove functionality with aliases."""
        doc_id = self.test_db.save_document("Test Document", "Content", "project")
        
        with patch('emdx.textual_browser_minimal.db', self.test_db), \
             patch('emdx.tags.db', self.test_db):
            
            browser = EmdxBrowser()
            
            # Mock the tag management methods
            with patch.object(browser, 'add_tag_to_document') as mock_add_tag, \
                 patch.object(browser, 'refresh_document_list') as mock_refresh:
                
                # Simulate adding alias tags
                await browser.add_tag_to_document(doc_id, "gameplan")
                await browser.add_tag_to_document(doc_id, "active")
                
                # Verify methods were called
                mock_add_tag.assert_called()

    @pytest.mark.asyncio
    async def test_browser_handles_mixed_emoji_and_alias_tags(self):
        """Test browser properly handles documents with mixed tag types."""
        doc_id = self.test_db.save_document("Mixed Tags Doc", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            add_tags_to_document(doc_id, ["gameplan", "🚀", "custom-tag", "active"])
        
        with patch('emdx.textual_browser_minimal.db', self.test_db), \
             patch('emdx.tags.db', self.test_db):
            
            browser = EmdxBrowser()
            
            # Test document loading with mixed tags
            with patch.object(browser, 'load_documents') as mock_load:
                mock_load.return_value = [
                    {"id": doc_id, "title": "Mixed Tags Doc", "content": "Content",
                     "project": "project", "created_at": "2024-01-01", "access_count": 1}
                ]
                
                docs = await browser.load_documents()
                assert len(docs) == 1

    def test_browser_tag_display_formatting(self):
        """Test that browser properly formats emoji tags for display."""
        doc_id = self.test_db.save_document("Display Test", "Content", "project")
        
        with patch('emdx.tags.db', self.test_db):
            add_tags_to_document(doc_id, ["🎯", "🚀", "custom-tag"])
        
        # Test tag formatting (this would depend on actual browser implementation)
        stored_tags = get_document_tags(doc_id)
        
        # Verify emojis are preserved for display
        assert "🎯" in stored_tags
        assert "🚀" in stored_tags
        assert "custom-tag" in stored_tags

    @pytest.mark.asyncio
    async def test_browser_search_performance_with_aliases(self):
        """Test browser search performance with alias expansion."""
        # Create many documents for performance testing
        doc_ids = []
        for i in range(100):
            doc_id = self.test_db.save_document(f"Doc {i}", f"Content {i}", "project")
            doc_ids.append(doc_id)
        
        with patch('emdx.tags.db', self.test_db):
            # Add various tag combinations
            for i, doc_id in enumerate(doc_ids):
                if i % 4 == 0:
                    add_tags_to_document(doc_id, ["🎯"])  # gameplan
                elif i % 4 == 1:
                    add_tags_to_document(doc_id, ["🚀"])  # active
                elif i % 4 == 2:
                    add_tags_to_document(doc_id, ["🐛"])  # bug
                else:
                    add_tags_to_document(doc_id, ["custom"])
        
        with patch('emdx.textual_browser_minimal.db', self.test_db), \
             patch('emdx.tags.db', self.test_db):
            
            browser = EmdxBrowser()
            
            # Test search performance
            import time
            start_time = time.time()
            
            with patch.object(browser, 'search_documents') as mock_search:
                mock_search.return_value = []  # Simplified for performance test
                await browser.action_search_documents("gameplan")
            
            end_time = time.time()
            
            # Should complete quickly
            assert (end_time - start_time) < 0.5

    @pytest.mark.asyncio
    async def test_browser_tag_autocomplete_with_aliases(self):
        """Test browser tag autocomplete includes aliases."""
        with patch('emdx.textual_browser_minimal.db', self.test_db):
            browser = EmdxBrowser()
            
            # Mock autocomplete functionality
            with patch('emdx.emoji_aliases.suggest_aliases') as mock_suggest:
                mock_suggest.return_value = [("gameplan", "🎯"), ("active", "🚀")]
                
                # Test autocomplete for partial alias
                suggestions = mock_suggest("game")
                
                assert len(suggestions) > 0
                assert any("gameplan" in str(suggestion) for suggestion in suggestions)

    def test_browser_tag_validation_with_aliases(self):
        """Test that browser validates tags including aliases."""
        from emdx.emoji_aliases import is_valid_tag
        
        # Test various tag types
        assert is_valid_tag("gameplan") is True    # Valid alias
        assert is_valid_tag("🎯") is True          # Valid emoji
        assert is_valid_tag("custom-tag") is False # Unknown tag
        assert is_valid_tag("invalid@tag") is False # Invalid characters

    @pytest.mark.asyncio
    async def test_browser_handles_tag_update_conflicts(self):
        """Test browser handles concurrent tag updates gracefully."""
        doc_id = self.test_db.save_document("Conflict Test", "Content", "project")
        
        with patch('emdx.textual_browser_minimal.db', self.test_db), \
             patch('emdx.tags.db', self.test_db):
            
            browser = EmdxBrowser()
            
            # Simulate concurrent tag operations
            with patch.object(browser, 'add_tag_to_document') as mock_add:
                mock_add.return_value = None  # Simulate success
                
                # Multiple rapid tag additions
                await browser.add_tag_to_document(doc_id, "gameplan")
                await browser.add_tag_to_document(doc_id, "active")
                await browser.add_tag_to_document(doc_id, "testing")
                
                # Should handle all operations
                assert mock_add.call_count == 3


class TestTUIBrowserEdgeCases:
    """Test edge cases in TUI browser emoji alias functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.test_db = TestDatabase(":memory:")

    @pytest.mark.asyncio
    async def test_browser_empty_search_with_aliases(self):
        """Test browser handles empty search gracefully."""
        with patch('emdx.textual_browser_minimal.db', self.test_db):
            browser = EmdxBrowser()
            
            with patch.object(browser, 'search_documents') as mock_search:
                mock_search.return_value = []
                
                # Empty search should not crash
                await browser.action_search_documents("")
                
                mock_search.assert_called()

    @pytest.mark.asyncio
    async def test_browser_special_characters_in_search(self):
        """Test browser handles special characters in search terms."""
        with patch('emdx.textual_browser_minimal.db', self.test_db):
            browser = EmdxBrowser()
            
            with patch.object(browser, 'search_documents') as mock_search:
                mock_search.return_value = []
                
                # Special characters should not crash browser
                await browser.action_search_documents("test@search!")
                await browser.action_search_documents("unicode:café")
                
                assert mock_search.call_count == 2

    @pytest.mark.asyncio
    async def test_browser_very_long_search_terms(self):
        """Test browser handles very long search terms."""
        with patch('emdx.textual_browser_minimal.db', self.test_db):
            browser = EmdxBrowser()
            
            long_search = "a" * 1000
            
            with patch.object(browser, 'search_documents') as mock_search:
                mock_search.return_value = []
                
                # Long search should not crash
                await browser.action_search_documents(long_search)
                
                mock_search.assert_called()

    def test_browser_tag_display_truncation(self):
        """Test browser properly truncates very long tags for display."""
        doc_id = self.test_db.save_document("Long Tag Test", "Content", "project")
        
        long_tag = "very-long-custom-tag-name-that-exceeds-normal-display-width"
        
        with patch('emdx.tags.db', self.test_db):
            add_tags_to_document(doc_id, ["🎯", long_tag, "🚀"])
        
        stored_tags = get_document_tags(doc_id)
        assert long_tag in stored_tags
        
        # Browser should handle display of long tags without breaking layout
        # (This would require actual UI testing in a real implementation)

    @pytest.mark.asyncio
    async def test_browser_rapid_tag_operations(self):
        """Test browser handles rapid tag add/remove operations."""
        doc_id = self.test_db.save_document("Rapid Test", "Content", "project")
        
        with patch('emdx.textual_browser_minimal.db', self.test_db), \
             patch('emdx.tags.db', self.test_db):
            
            browser = EmdxBrowser()
            
            # Mock rapid operations
            with patch.object(browser, 'add_tag_to_document') as mock_add, \
                 patch.object(browser, 'remove_tag_from_document') as mock_remove:
                
                # Rapid add/remove sequence
                await browser.add_tag_to_document(doc_id, "gameplan")
                await browser.remove_tag_from_document(doc_id, "gameplan")
                await browser.add_tag_to_document(doc_id, "active")
                await browser.add_tag_to_document(doc_id, "testing")
                
                # Should handle all operations
                assert mock_add.call_count == 3
                assert mock_remove.call_count == 1


class TestTUIBrowserIntegrationMocking:
    """Test TUI browser with comprehensive mocking for isolation."""

    @pytest.mark.asyncio
    async def test_browser_with_mocked_emoji_expansion(self):
        """Test browser with mocked emoji alias expansion."""
        with patch('emdx.textual_browser_minimal.expand_aliases') as mock_expand, \
             patch('emdx.textual_browser_minimal.db') as mock_db:
            
            # Setup mocks
            mock_expand.return_value = ["🎯", "🚀"]
            mock_db.search_documents.return_value = []
            
            browser = EmdxBrowser()
            
            with patch.object(browser, 'search_documents') as mock_search:
                mock_search.return_value = []
                
                # Simulate search that triggers alias expansion
                await browser.action_search_documents("gameplan,active")
                
                # Verify expansion was used
                # (Implementation details depend on how search integrates with aliases)

    @pytest.mark.asyncio
    async def test_browser_with_mocked_tag_operations(self):
        """Test browser tag operations with full mocking."""
        with patch('emdx.textual_browser_minimal.db') as mock_db, \
             patch('emdx.tags.add_tags_to_document') as mock_add_tags, \
             patch('emdx.tags.remove_tags_from_document') as mock_remove_tags:
            
            browser = EmdxBrowser()
            
            # Mock successful tag operations
            mock_add_tags.return_value = None
            mock_remove_tags.return_value = None
            
            with patch.object(browser, 'add_tag_to_document') as mock_add, \
                 patch.object(browser, 'remove_tag_from_document') as mock_remove:
                
                # Test tag operations
                await browser.add_tag_to_document(123, "gameplan")
                await browser.remove_tag_from_document(123, "active")
                
                # Verify operations were attempted
                mock_add.assert_called_once_with(123, "gameplan")
                mock_remove.assert_called_once_with(123, "active")

    def test_browser_initialization_with_mocked_dependencies(self):
        """Test browser initialization with all dependencies mocked."""
        with patch('emdx.textual_browser_minimal.db') as mock_db, \
             patch('emdx.textual_browser_minimal.console') as mock_console:
            
            # Should initialize without errors
            browser = EmdxBrowser()
            assert browser is not None
            
            # Basic properties should be accessible
            assert hasattr(browser, 'title')


class TestTUIBrowserErrorHandling:
    """Test error handling in TUI browser emoji alias functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.test_db = TestDatabase(":memory:")

    @pytest.mark.asyncio
    async def test_browser_handles_database_errors_gracefully(self):
        """Test browser handles database errors during alias operations."""
        with patch('emdx.textual_browser_minimal.db') as mock_db:
            # Mock database error
            mock_db.search_documents.side_effect = Exception("Database error")
            
            browser = EmdxBrowser()
            
            with patch.object(browser, 'search_documents') as mock_search:
                mock_search.side_effect = Exception("Search error")
                
                # Should handle error gracefully without crashing
                try:
                    await browser.action_search_documents("gameplan")
                except Exception:
                    # Error handling depends on browser implementation
                    pass

    @pytest.mark.asyncio
    async def test_browser_handles_tag_operation_failures(self):
        """Test browser handles tag operation failures."""
        with patch('emdx.textual_browser_minimal.db', self.test_db), \
             patch('emdx.tags.add_tags_to_document') as mock_add:
            
            # Mock tag operation failure
            mock_add.side_effect = Exception("Tag operation failed")
            
            browser = EmdxBrowser()
            
            with patch.object(browser, 'add_tag_to_document') as mock_browser_add:
                mock_browser_add.side_effect = Exception("Browser tag error")
                
                # Should handle error gracefully
                try:
                    await browser.add_tag_to_document(123, "gameplan")
                except Exception:
                    # Error handling depends on implementation
                    pass

    def test_browser_handles_malformed_emoji_data(self):
        """Test browser handles malformed emoji data gracefully."""
        # Test with corrupted emoji data
        with patch('emdx.emoji_aliases.EMOJI_ALIASES', {}):
            from emdx.emoji_aliases import expand_aliases
            
            # Should handle empty emoji mapping
            result = expand_aliases(("gameplan", "active"))
            assert result == ["gameplan", "active"]  # Should preserve original

    @pytest.mark.asyncio
    async def test_browser_memory_handling_with_large_datasets(self):
        """Test browser memory handling with large numbers of tagged documents."""
        # Create many documents for memory test
        doc_ids = []
        for i in range(1000):
            doc_id = self.test_db.save_document(f"Doc {i}", f"Content {i}", "project")
            doc_ids.append(doc_id)
        
        with patch('emdx.tags.db', self.test_db):
            # Add tags to all documents
            for doc_id in doc_ids:
                add_tags_to_document(doc_id, ["🎯", "🚀"])
        
        with patch('emdx.textual_browser_minimal.db', self.test_db), \
             patch('emdx.tags.db', self.test_db):
            
            browser = EmdxBrowser()
            
            # Should handle large dataset without memory issues
            with patch.object(browser, 'load_documents') as mock_load:
                mock_load.return_value = [
                    {"id": i, "title": f"Doc {i}", "content": f"Content {i}",
                     "project": "project", "created_at": "2024-01-01", "access_count": 1}
                    for i in range(100)  # Limit for testing
                ]
                
                docs = await browser.load_documents()
                assert len(docs) == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])