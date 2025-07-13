"""Comprehensive tests for emoji alias integration in core.py functionality.

This test suite focuses specifically on testing the core save and find commands
with emoji alias functionality to ensure proper integration and backward compatibility.
"""

import pytest
from unittest.mock import patch, MagicMock, call
from typer.testing import CliRunner
from io import StringIO

from test_fixtures import TestDatabase
# Core functions tested via CLI interface
from emdx.tags import add_tags_to_document, get_document_tags, search_by_tags
from emdx.emoji_aliases import expand_aliases, get_emoji_for_alias
from emdx.cli import app


class TestCoreEmojiAliasIntegration:
    """Test core commands with emoji alias functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    def test_save_command_with_alias_tags(self, temp_db):
        """Test save command properly expands alias tags."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db), \
             patch('emdx.core.get_project_name', return_value="test-project"), \
             patch('rich.console.Console.print') as mock_print:
            
            # Test save with alias tags
            result = self.runner.invoke(app, [
                'save',
                '--title', 'Test Document with Aliases',
                '--content', 'Content for testing alias expansion',
                '--tags', 'gameplan,active,bug,urgent'
            ])
            
            assert result.exit_code == 0
            
            # Verify document was saved
            docs = temp_db.list_documents()
            assert len(docs) == 1
            doc = docs[0]
            assert doc["title"] == "Test Document with Aliases"
            
            # Verify tags were expanded to emojis
            stored_tags = get_document_tags(doc["id"])
            expected_emojis = ["🎯", "🚀", "🐛", "🚨"]
            assert set(stored_tags) == set(expected_emojis)
            
            # Verify console output mentions tag expansion
            print_calls = [call[0][0] for call in mock_print.call_args_list]
            output = " ".join(str(call) for call in print_calls)
            assert "🎯" in output or "gameplan" in output

    def test_save_command_mixed_aliases_and_emojis(self, temp_db):
        """Test save command with mixed alias and emoji tags."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db), \
             patch('emdx.core.get_project_name', return_value="test-project"):
            
            result = self.runner.invoke(app, [
                'save',
                '--title', 'Mixed Tags Document',
                '--content', 'Testing mixed tag formats',
                '--tags', 'gameplan,🚀,testing,🐛,custom-tag'
            ])
            
            assert result.exit_code == 0
            
            docs = temp_db.list_documents()
            doc_id = docs[0]["id"]
            stored_tags = get_document_tags(doc_id)
            
            # Should contain: 🎯 (gameplan), 🚀 (direct), 🧪 (testing), 🐛 (direct), custom-tag
            expected = ["🎯", "🚀", "🧪", "🐛", "custom-tag"]
            assert set(stored_tags) == set(expected)

    def test_save_command_with_duplicate_aliases(self, temp_db):
        """Test save command removes duplicates from alias expansion."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db), \
             patch('emdx.core.get_project_name', return_value="test-project"):
            
            # Multiple aliases that map to same emoji
            result = self.runner.invoke(app, [
                'save',
                '--title', 'Duplicate Aliases Test',
                '--content', 'Testing duplicate alias handling',
                '--tags', 'gameplan,gp,plan,🎯,strategy'
            ])
            
            assert result.exit_code == 0
            
            docs = temp_db.list_documents()
            doc_id = docs[0]["id"]
            stored_tags = get_document_tags(doc_id)
            
            # Should only have one instance of 🎯
            assert stored_tags.count("🎯") == 1
            assert len(stored_tags) == 1

    def test_save_command_preserves_unknown_tags(self, temp_db):
        """Test that save command preserves unknown/custom tags."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db), \
             patch('emdx.core.get_project_name', return_value="test-project"):
            
            result = self.runner.invoke(app, [
                'save',
                '--title', 'Custom Tags Test',
                '--content', 'Testing custom tag preservation',
                '--tags', 'gameplan,my-custom-tag,project-specific,active'
            ])
            
            assert result.exit_code == 0
            
            docs = temp_db.list_documents()
            doc_id = docs[0]["id"]
            stored_tags = get_document_tags(doc_id)
            
            expected = ["🎯", "my-custom-tag", "project-specific", "🚀"]
            assert set(stored_tags) == set(expected)

    def test_save_command_case_insensitive_aliases(self, temp_db):
        """Test that save command handles case-insensitive aliases."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db), \
             patch('emdx.core.get_project_name', return_value="test-project"):
            
            result = self.runner.invoke(app, [
                'save',
                '--title', 'Case Test',
                '--content', 'Testing case insensitivity',
                '--tags', 'GAMEPLAN,Active,BUG,urgent'
            ])
            
            assert result.exit_code == 0
            
            docs = temp_db.list_documents()
            doc_id = docs[0]["id"]
            stored_tags = get_document_tags(doc_id)
            
            expected = ["🎯", "🚀", "🐛", "🚨"]
            assert set(stored_tags) == set(expected)

    def test_save_command_from_stdin_with_aliases(self, temp_db):
        """Test save command from stdin with alias tags."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db), \
             patch('emdx.core.get_project_name', return_value="test-project"):
            
            # Simulate stdin input
            stdin_content = "Content from stdin for alias testing"
            result = self.runner.invoke(app, [
                'save',
                '--title', 'Stdin Document',
                '--tags', 'gameplan,testing,active'
            ], input=stdin_content)
            
            assert result.exit_code == 0
            
            docs = temp_db.list_documents()
            doc_id = docs[0]["id"]
            doc = temp_db.get_document(doc_id)
            
            assert doc["content"] == stdin_content
            
            stored_tags = get_document_tags(doc_id)
            expected = ["🎯", "🧪", "🚀"]
            assert set(stored_tags) == set(expected)

    def test_find_command_with_alias_tags(self, temp_db, sample_documents):
        """Test find command works with alias tag search."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db):
            
            # Add emoji tags to sample documents
            doc_ids = sample_documents
            add_tags_to_document(doc_ids[0], ["🎯", "🚀"])  # gameplan, active
            add_tags_to_document(doc_ids[1], ["🔧", "✅"])  # refactor, done
            add_tags_to_document(doc_ids[2], ["🐛", "🚨"])  # bug, urgent
            
            # Test find with single alias
            result = self.runner.invoke(app, ['find', '--tags', 'gameplan'])
            assert result.exit_code == 0
            assert "Python Testing Guide" in result.stdout
            
            # Test find with multiple aliases
            result = self.runner.invoke(app, ['find', '--tags', 'bug,urgent'])
            assert result.exit_code == 0
            assert "Git Workflow" in result.stdout
            
            # Test find with mixed aliases and emojis
            result = self.runner.invoke(app, ['find', '--tags', 'refactor,✅'])
            assert result.exit_code == 0
            assert "Docker Best Practices" in result.stdout

    def test_find_command_alias_expansion_in_search(self, temp_db):
        """Test that find command properly expands aliases before searching."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db):
            
            # Create documents with emoji tags
            doc1 = temp_db.save_document("Gameplan Doc", "Strategy content", "project")
            doc2 = temp_db.save_document("Active Doc", "Active content", "project")
            doc3 = temp_db.save_document("Mixed Doc", "Mixed content", "project")
            
            add_tags_to_document(doc1, ["🎯", "🔍"])  # gameplan, analysis
            add_tags_to_document(doc2, ["🚀", "🧪"])  # active, testing
            add_tags_to_document(doc3, ["🎯", "🚀"])  # gameplan, active
            
            # Search using aliases - should find docs with corresponding emojis
            result = self.runner.invoke(app, ['find', '--tags', 'gameplan'])
            assert result.exit_code == 0
            assert "Gameplan Doc" in result.stdout
            assert "Mixed Doc" in result.stdout
            assert "Active Doc" not in result.stdout
            
            # Search with multiple aliases
            result = self.runner.invoke(app, ['find', '--tags', 'gameplan,active', '--tag-mode', 'all'])
            assert result.exit_code == 0
            assert "Mixed Doc" in result.stdout
            assert "Gameplan Doc" not in result.stdout
            assert "Active Doc" not in result.stdout

    def test_find_command_handles_unknown_aliases(self, temp_db):
        """Test find command gracefully handles unknown aliases."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db):
            
            doc_id = temp_db.save_document("Test Doc", "Content", "project")
            add_tags_to_document(doc_id, ["unknown-alias", "custom-tag"])
            
            # Search for unknown alias should work (treated as literal tag)
            result = self.runner.invoke(app, ['find', '--tags', 'unknown-alias'])
            assert result.exit_code == 0
            assert "Test Doc" in result.stdout

    def test_find_command_content_search_with_aliases(self, temp_db):
        """Test find command content search combined with alias tags."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db):
            
            doc1 = temp_db.save_document("Python Guide", "Learn Python programming", "project")
            doc2 = temp_db.save_document("Python Testing", "Testing Python code", "project")
            doc3 = temp_db.save_document("Java Guide", "Learn Java programming", "project")
            
            add_tags_to_document(doc1, ["🎯", "📚"])  # gameplan, documentation
            add_tags_to_document(doc2, ["🧪", "🎯"])  # testing, gameplan
            add_tags_to_document(doc3, ["📚"])       # documentation
            
            # Search for content + alias tags
            result = self.runner.invoke(app, ['find', 'Python', '--tags', 'gameplan'])
            assert result.exit_code == 0
            assert "Python Guide" in result.stdout
            assert "Python Testing" in result.stdout
            assert "Java Guide" not in result.stdout

    def test_view_command_shows_expanded_tags(self, temp_db):
        """Test that view command shows both original and expanded tags."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db):
            
            doc_id = temp_db.save_document("Test Document", "Test content", "project")
            add_tags_to_document(doc_id, ["gameplan", "active", "custom-tag"])
            
            result = self.runner.invoke(app, ['view', str(doc_id)])
            assert result.exit_code == 0
            
            # Should show emoji tags in output
            assert "🎯" in result.stdout
            assert "🚀" in result.stdout
            assert "custom-tag" in result.stdout


class TestCoreCommandEdgeCases:
    """Test edge cases and error conditions in core commands with aliases."""

    def test_save_with_empty_tags(self, temp_db):
        """Test save command with empty tag list."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.core.get_project_name', return_value="test-project"):
            
            runner = CliRunner()
            result = runner.invoke(app, [
                'save',
                '--title', 'No Tags Document',
                '--content', 'Document without tags',
                '--tags', ''
            ])
            
            assert result.exit_code == 0
            docs = temp_db.list_documents()
            assert len(docs) == 1

    def test_save_with_whitespace_in_tags(self, temp_db):
        """Test save command handles whitespace in tags properly."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db), \
             patch('emdx.core.get_project_name', return_value="test-project"):
            
            runner = CliRunner()
            result = runner.invoke(app, [
                'save',
                '--title', 'Whitespace Tags Test',
                '--content', 'Testing whitespace handling',
                '--tags', ' gameplan , active , bug '
            ])
            
            assert result.exit_code == 0
            
            docs = temp_db.list_documents()
            doc_id = docs[0]["id"]
            stored_tags = get_document_tags(doc_id)
            
            expected = ["🎯", "🚀", "🐛"]
            assert set(stored_tags) == set(expected)

    def test_find_with_empty_tag_search(self, temp_db, sample_documents):
        """Test find command with empty tag search."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db):
            
            runner = CliRunner()
            result = runner.invoke(app, ['find', '--tags', ''])
            
            # Should not crash, but also shouldn't return results
            assert result.exit_code == 0

    def test_find_with_special_characters_in_aliases(self, temp_db):
        """Test find command with special characters in search terms."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db):
            
            doc_id = temp_db.save_document("Test Doc", "Content", "project")
            add_tags_to_document(doc_id, ["gameplan!", "test@tag"])
            
            runner = CliRunner()
            # Should handle special characters gracefully
            result = runner.invoke(app, ['find', '--tags', 'gameplan!'])
            assert result.exit_code == 0

    def test_very_long_alias_input(self, temp_db):
        """Test handling of very long tag input."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db), \
             patch('emdx.core.get_project_name', return_value="test-project"):
            
            long_tag = "a" * 1000
            tag_list = f"gameplan,active,{long_tag}"
            
            runner = CliRunner()
            result = runner.invoke(app, [
                'save',
                '--title', 'Long Tag Test',
                '--content', 'Testing very long tags',
                '--tags', tag_list
            ])
            
            assert result.exit_code == 0
            
            docs = temp_db.list_documents()
            doc_id = docs[0]["id"]
            stored_tags = get_document_tags(doc_id)
            
            assert "🎯" in stored_tags
            assert "🚀" in stored_tags
            assert long_tag in stored_tags


class TestCoreCommandPerformance:
    """Test performance characteristics of core commands with emoji aliases."""

    def test_save_command_performance_with_many_tags(self, temp_db):
        """Test save command performance with large number of tags."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db), \
             patch('emdx.core.get_project_name', return_value="test-project"):
            
            # Create a large tag list with mix of aliases and custom tags
            tag_list = []
            aliases = ["gameplan", "active", "bug", "feature", "testing", "refactor"]
            for i in range(100):
                if i < len(aliases):
                    tag_list.append(aliases[i])
                else:
                    tag_list.append(f"custom-tag-{i}")
            
            tag_string = ",".join(tag_list)
            
            import time
            start_time = time.time()
            
            runner = CliRunner()
            result = runner.invoke(app, [
                'save',
                '--title', 'Many Tags Document',
                '--content', 'Document with many tags',
                '--tags', tag_string
            ])
            
            end_time = time.time()
            
            assert result.exit_code == 0
            # Should complete in reasonable time (under 2 seconds)
            assert (end_time - start_time) < 2.0
            
            # Verify tags were processed correctly
            docs = temp_db.list_documents()
            doc_id = docs[0]["id"]
            stored_tags = get_document_tags(doc_id)
            
            # Should have expanded aliases
            assert "🎯" in stored_tags  # gameplan
            assert "🚀" in stored_tags  # active
            assert "🐛" in stored_tags  # bug
            
            # Should have preserved custom tags
            assert "custom-tag-10" in stored_tags

    def test_find_command_performance_with_alias_expansion(self, temp_db):
        """Test find command performance when expanding aliases."""
        with patch('emdx.core.db', temp_db), \
             patch('emdx.tags.db', temp_db):
            
            # Create many documents with various tag combinations
            for i in range(200):
                doc_id = temp_db.save_document(f"Doc {i}", f"Content {i}", "project")
                if i % 4 == 0:
                    add_tags_to_document(doc_id, ["🎯"])  # gameplan
                elif i % 4 == 1:
                    add_tags_to_document(doc_id, ["🚀"])  # active
                elif i % 4 == 2:
                    add_tags_to_document(doc_id, ["🐛"])  # bug
                else:
                    add_tags_to_document(doc_id, ["custom-tag"])
            
            import time
            start_time = time.time()
            
            runner = CliRunner()
            result = runner.invoke(app, ['find', '--tags', 'gameplan'])
            
            end_time = time.time()
            
            assert result.exit_code == 0
            # Should complete in reasonable time
            assert (end_time - start_time) < 1.0
            
            # Should find approximately 50 documents (every 4th)
            output_lines = result.stdout.count("Doc ")
            assert 45 <= output_lines <= 55  # Allow some tolerance


class TestCoreCommandMocking:
    """Test core commands with proper mocking for isolation."""

    def test_save_command_with_mocked_dependencies(self):
        """Test save command with all dependencies mocked."""
        with patch('emdx.core.db') as mock_db, \
             patch('emdx.tags.add_tags_to_document') as mock_add_tags, \
             patch('emdx.core.get_project_name', return_value="test-project"), \
             patch('emdx.emoji_aliases.expand_aliases') as mock_expand:
            
            # Setup mocks
            mock_db.save_document.return_value = 123
            mock_expand.return_value = ["🎯", "🚀"]
            
            runner = CliRunner()
            result = runner.invoke(app, [
                'save',
                '--title', 'Mocked Save Test',
                '--content', 'Testing with mocks',
                '--tags', 'gameplan,active'
            ])
            
            assert result.exit_code == 0
            
            # Verify mocks were called correctly
            mock_db.save_document.assert_called_once()
            mock_expand.assert_called_once_with(('gameplan', 'active'))
            mock_add_tags.assert_called_once_with(123, ["🎯", "🚀"])

    def test_find_command_with_mocked_search(self):
        """Test find command with mocked search functionality."""
        with patch('emdx.tags.search_by_tags') as mock_search, \
             patch('emdx.emoji_aliases.expand_aliases') as mock_expand:
            
            # Setup mocks
            mock_expand.return_value = ["🎯"]
            mock_search.return_value = [
                {"id": 1, "title": "Test Doc", "content": "Content", "project": "test"}
            ]
            
            runner = CliRunner()
            result = runner.invoke(app, ['find', '--tags', 'gameplan'])
            
            assert result.exit_code == 0
            
            # Verify expansion was called
            mock_expand.assert_called_once_with(('gameplan',))
            # Verify search was called with expanded tags
            mock_search.assert_called_once_with(["🎯"], mode="any", project=None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])