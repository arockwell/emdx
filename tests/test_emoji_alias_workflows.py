"""End-to-end workflow tests for emoji alias system across all EMDX components.

This test suite simulates real user workflows to ensure the emoji alias system
works correctly in practice across the entire application.
"""

import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
import tempfile
import os

from test_fixtures import TestDatabase
from emdx.cli import app
from emdx.tags import add_tags_to_document, get_document_tags, search_by_tags
from emdx.emoji_aliases import expand_aliases, get_all_emojis, get_all_aliases


class TestCompleteUserWorkflows:
    """Test complete user workflows with emoji aliases."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.test_db = TestDatabase(":memory:")

    def test_complete_save_search_view_workflow(self):
        """Test complete workflow: save with aliases → search with aliases → view results."""
        with patch('emdx.core.db', self.test_db), \
             patch('emdx.tags.db', self.test_db), \
             patch('emdx.core.get_project_name', return_value="test-project"):
            
            # Step 1: Save document with alias tags
            save_result = self.runner.invoke(app, [
                'save',
                '--title', 'Authentication Bug Fix Gameplan',
                '--content', 'Detailed strategy to fix the critical authentication issue',
                '--tags', 'gameplan,bug,urgent,active'
            ])
            assert save_result.exit_code == 0
            
            # Step 2: Save another document
            save_result2 = self.runner.invoke(app, [
                'save',
                '--title', 'User Testing Results',
                '--content', 'Results from user testing session',
                '--tags', 'testing,analysis,done,success'
            ])
            assert save_result2.exit_code == 0
            
            # Step 3: Search using aliases
            search_result = self.runner.invoke(app, [
                'find', '--tags', 'gameplan'
            ])
            assert search_result.exit_code == 0
            assert "Authentication Bug Fix Gameplan" in search_result.stdout
            assert "User Testing Results" not in search_result.stdout
            
            # Step 4: Search with multiple aliases
            search_result2 = self.runner.invoke(app, [
                'find', '--tags', 'bug,urgent', '--tag-mode', 'all'
            ])
            assert search_result2.exit_code == 0
            assert "Authentication Bug Fix Gameplan" in search_result2.stdout
            
            # Step 5: Search for success stories
            search_result3 = self.runner.invoke(app, [
                'find', '--tags', 'success'
            ])
            assert search_result3.exit_code == 0
            assert "User Testing Results" in search_result3.stdout
            
            # Step 6: Verify tags were stored as emojis
            docs = self.test_db.list_documents()
            bug_doc = next(doc for doc in docs if "Authentication" in doc["title"])
            stored_tags = get_document_tags(bug_doc["id"])
            
            expected_emojis = ["🎯", "🐛", "🚨", "🚀"]
            assert set(stored_tags) == set(expected_emojis)

    def test_project_management_workflow(self):
        """Test project management workflow with status tracking."""
        with patch('emdx.core.db', self.test_db), \
             patch('emdx.tags.db', self.test_db), \
             patch('emdx.core.get_project_name', return_value="web-app"):
            
            # Create initial gameplan
            self.runner.invoke(app, [
                'save',
                '--title', 'Web App Redesign Gameplan',
                '--content', 'Strategy for redesigning the web application',
                '--tags', 'gameplan,active,feature'
            ])
            
            # Add development tasks
            self.runner.invoke(app, [
                'save',
                '--title', 'UI Component Library',
                '--content', 'Build reusable UI components',
                '--tags', 'feature,active,refactor'
            ])
            
            # Add bug report
            self.runner.invoke(app, [
                'save',
                '--title', 'Mobile Layout Bug',
                '--content', 'Layout breaks on mobile devices',
                '--tags', 'bug,urgent,active'
            ])
            
            # Find all active work
            active_result = self.runner.invoke(app, [
                'find', '--tags', 'active'
            ])
            assert active_result.exit_code == 0
            assert "Web App Redesign Gameplan" in active_result.stdout
            assert "UI Component Library" in active_result.stdout
            assert "Mobile Layout Bug" in active_result.stdout
            
            # Find urgent items
            urgent_result = self.runner.invoke(app, [
                'find', '--tags', 'urgent'
            ])
            assert urgent_result.exit_code == 0
            assert "Mobile Layout Bug" in urgent_result.stdout
            assert "Web App Redesign Gameplan" not in urgent_result.stdout
            
            # Find features vs bugs
            feature_result = self.runner.invoke(app, [
                'find', '--tags', 'feature'
            ])
            assert feature_result.exit_code == 0
            assert "Web App Redesign Gameplan" in feature_result.stdout
            assert "UI Component Library" in feature_result.stdout
            assert "Mobile Layout Bug" not in feature_result.stdout

    def test_documentation_workflow(self):
        """Test documentation workflow with different document types."""
        with patch('emdx.core.db', self.test_db), \
             patch('emdx.tags.db', self.test_db), \
             patch('emdx.core.get_project_name', return_value="docs"):
            
            # Create various documentation types
            docs_data = [
                ("API Documentation", "REST API reference", "documentation,done"),
                ("Architecture Overview", "System architecture design", "architecture,documentation"),
                ("Code Review Notes", "Notes from code review session", "notes,analysis"),
                ("Meeting Notes", "Weekly team meeting notes", "notes,project-management"),
            ]
            
            for title, content, tags in docs_data:
                result = self.runner.invoke(app, [
                    'save',
                    '--title', title,
                    '--content', content,
                    '--tags', tags
                ])
                assert result.exit_code == 0
            
            # Find all documentation
            docs_result = self.runner.invoke(app, [
                'find', '--tags', 'documentation'
            ])
            assert docs_result.exit_code == 0
            assert "API Documentation" in docs_result.stdout
            assert "Architecture Overview" in docs_result.stdout
            
            # Find notes
            notes_result = self.runner.invoke(app, [
                'find', '--tags', 'notes'
            ])
            assert notes_result.exit_code == 0
            assert "Code Review Notes" in notes_result.stdout
            assert "Meeting Notes" in notes_result.stdout
            
            # Find architectural documents
            arch_result = self.runner.invoke(app, [
                'find', '--tags', 'architecture'
            ])
            assert arch_result.exit_code == 0
            assert "Architecture Overview" in arch_result.stdout

    def test_testing_and_qa_workflow(self):
        """Test testing and QA workflow with outcome tracking."""
        with patch('emdx.core.db', self.test_db), \
             patch('emdx.tags.db', self.test_db), \
             patch('emdx.core.get_project_name', return_value="qa"):
            
            # Create test-related documents
            test_docs = [
                ("Unit Test Suite", "Comprehensive unit tests", "testing,done,success"),
                ("Integration Test Results", "Failed integration tests", "testing,failed,bug"),
                ("Performance Test Analysis", "Mixed performance results", "testing,analysis,partial"),
                ("User Acceptance Testing", "UAT session results", "testing,done,success"),
            ]
            
            for title, content, tags in test_docs:
                self.runner.invoke(app, [
                    'save',
                    '--title', title,
                    '--content', content,
                    '--tags', tags
                ])
            
            # Find all testing work
            testing_result = self.runner.invoke(app, [
                'find', '--tags', 'testing'
            ])
            assert testing_result.exit_code == 0
            for title, _, _ in test_docs:
                assert title in testing_result.stdout
            
            # Find successful tests
            success_result = self.runner.invoke(app, [
                'find', '--tags', 'success,testing', '--tag-mode', 'all'
            ])
            assert success_result.exit_code == 0
            assert "Unit Test Suite" in success_result.stdout
            assert "User Acceptance Testing" in success_result.stdout
            assert "Integration Test Results" not in success_result.stdout
            
            # Find failed tests
            failed_result = self.runner.invoke(app, [
                'find', '--tags', 'failed'
            ])
            assert failed_result.exit_code == 0
            assert "Integration Test Results" in failed_result.stdout

    def test_mixed_alias_emoji_workflow(self):
        """Test workflow mixing aliases and direct emoji usage."""
        with patch('emdx.core.db', self.test_db), \
             patch('emdx.tags.db', self.test_db), \
             patch('emdx.core.get_project_name', return_value="mixed"):
            
            # Save with aliases
            self.runner.invoke(app, [
                'save',
                '--title', 'Alias Tagged Document',
                '--content', 'Document tagged with aliases',
                '--tags', 'gameplan,active,feature'
            ])
            
            # Save with direct emojis
            self.runner.invoke(app, [
                'save',
                '--title', 'Emoji Tagged Document',
                '--content', 'Document tagged with direct emojis',
                '--tags', '🎯,🚀,🐛'
            ])
            
            # Save with mixed format
            self.runner.invoke(app, [
                'save',
                '--title', 'Mixed Tagged Document',
                '--content', 'Document with mixed tag formats',
                '--tags', 'gameplan,🚀,testing,🐛'
            ])
            
            # Search should find all relevant documents regardless of input format
            gameplan_search = self.runner.invoke(app, [
                'find', '--tags', 'gameplan'
            ])
            assert gameplan_search.exit_code == 0
            assert "Alias Tagged Document" in gameplan_search.stdout
            assert "Emoji Tagged Document" in gameplan_search.stdout
            assert "Mixed Tagged Document" in gameplan_search.stdout
            
            # Search with emoji should also work
            emoji_search = self.runner.invoke(app, [
                'find', '--tags', '🎯'
            ])
            assert emoji_search.exit_code == 0
            assert "Alias Tagged Document" in emoji_search.stdout
            assert "Emoji Tagged Document" in emoji_search.stdout
            assert "Mixed Tagged Document" in emoji_search.stdout


class TestStdinWorkflows:
    """Test workflows using stdin input with emoji aliases."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.test_db = TestDatabase(":memory:")

    def test_stdin_content_with_alias_tags(self):
        """Test saving content from stdin with alias tags."""
        with patch('emdx.core.db', self.test_db), \
             patch('emdx.tags.db', self.test_db), \
             patch('emdx.core.get_project_name', return_value="stdin-test"):
            
            stdin_content = """# Meeting Notes
            
            Today's team standup:
            - Discussed the authentication bug
            - Planned the new feature rollout
            - Reviewed code quality metrics
            """
            
            result = self.runner.invoke(app, [
                'save',
                '--title', 'Standup Notes',
                '--tags', 'notes,project-management,active'
            ], input=stdin_content)
            
            assert result.exit_code == 0
            
            # Verify content and tags were saved correctly
            docs = self.test_db.list_documents()
            assert len(docs) == 1
            
            doc = docs[0]
            assert doc["title"] == "Standup Notes"
            assert doc["content"] == stdin_content
            
            stored_tags = get_document_tags(doc["id"])
            expected = ["📝", "📊", "🚀"]  # notes, project-management, active
            assert set(stored_tags) == set(expected)

    def test_piped_command_output_with_aliases(self):
        """Test saving piped command output with alias tags."""
        with patch('emdx.core.db', self.test_db), \
             patch('emdx.tags.db', self.test_db), \
             patch('emdx.core.get_project_name', return_value="automation"):
            
            # Simulate piped output
            piped_output = """System Status Report
            
            CPU Usage: 45%
            Memory Usage: 67%
            Disk Space: 23GB free
            
            All systems nominal.
            """
            
            result = self.runner.invoke(app, [
                'save',
                '--title', 'System Status',
                '--tags', 'analysis,done,success'
            ], input=piped_output)
            
            assert result.exit_code == 0
            
            # Search for the analysis
            search_result = self.runner.invoke(app, [
                'find', '--tags', 'analysis'
            ])
            assert search_result.exit_code == 0
            assert "System Status" in search_result.stdout


class TestBulkOperationWorkflows:
    """Test workflows with bulk operations and many documents."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.test_db = TestDatabase(":memory:")

    def test_bulk_document_creation_and_search(self):
        """Test creating many documents and searching efficiently."""
        with patch('emdx.core.db', self.test_db), \
             patch('emdx.tags.db', self.test_db), \
             patch('emdx.core.get_project_name', return_value="bulk-test"):
            
            # Create many documents with various tag combinations
            doc_templates = [
                ("Gameplan", "gameplan,active"),
                ("Feature", "feature,active"),
                ("Bug", "bug,urgent"),
                ("Analysis", "analysis,done"),
                ("Testing", "testing,done,success"),
                ("Refactor", "refactor,active"),
                ("Documentation", "documentation,done"),
                ("Notes", "notes,project-management"),
            ]
            
            # Create 10 of each type
            for i in range(10):
                for doc_type, tags in doc_templates:
                    self.runner.invoke(app, [
                        'save',
                        '--title', f'{doc_type} Document {i+1}',
                        '--content', f'Content for {doc_type.lower()} document {i+1}',
                        '--tags', tags
                    ])
            
            # Verify we have 80 documents
            docs = self.test_db.list_documents()
            assert len(docs) == 80
            
            # Test various searches
            gameplan_results = self.runner.invoke(app, [
                'find', '--tags', 'gameplan'
            ])
            assert gameplan_results.exit_code == 0
            gameplan_count = gameplan_results.stdout.count("Gameplan Document")
            assert gameplan_count == 10
            
            # Test compound searches
            active_features = self.runner.invoke(app, [
                'find', '--tags', 'feature,active', '--tag-mode', 'all'
            ])
            assert active_features.exit_code == 0
            feature_count = active_features.stdout.count("Feature Document")
            assert feature_count == 10
            
            # Test success tracking
            successful_tests = self.runner.invoke(app, [
                'find', '--tags', 'testing,success', '--tag-mode', 'all'
            ])
            assert successful_tests.exit_code == 0
            success_count = successful_tests.stdout.count("Testing Document")
            assert success_count == 10

    def test_performance_with_large_tag_sets(self):
        """Test performance with documents having many tags."""
        with patch('emdx.core.db', self.test_db), \
             patch('emdx.tags.db', self.test_db), \
             patch('emdx.core.get_project_name', return_value="performance-test"):
            
            # Create documents with many tags
            many_tags = "gameplan,active,feature,testing,analysis,refactor,documentation,notes"
            
            import time
            start_time = time.time()
            
            for i in range(50):
                self.runner.invoke(app, [
                    'save',
                    '--title', f'Many Tags Document {i+1}',
                    '--content', f'Document {i+1} with many tags',
                    '--tags', many_tags
                ])
            
            creation_time = time.time() - start_time
            
            # Should complete in reasonable time
            assert creation_time < 30.0  # 30 seconds for 50 docs
            
            # Test search performance
            start_time = time.time()
            
            search_result = self.runner.invoke(app, [
                'find', '--tags', 'gameplan'
            ])
            
            search_time = time.time() - start_time
            
            assert search_result.exit_code == 0
            assert search_time < 5.0  # 5 seconds for search
            
            # Should find all 50 documents
            doc_count = search_result.stdout.count("Many Tags Document")
            assert doc_count == 50


class TestErrorRecoveryWorkflows:
    """Test workflows with error conditions and recovery."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
        self.test_db = TestDatabase(":memory:")

    def test_invalid_tag_handling_workflow(self):
        """Test workflow with invalid tags mixed with valid aliases."""
        with patch('emdx.core.db', self.test_db), \
             patch('emdx.tags.db', self.test_db), \
             patch('emdx.core.get_project_name', return_value="error-test"):
            
            # Save with mix of valid and invalid tags
            result = self.runner.invoke(app, [
                'save',
                '--title', 'Mixed Validity Document',
                '--content', 'Document with mixed tag validity',
                '--tags', 'gameplan,invalid@tag,active,#hashtag,bug'
            ])
            
            # Should succeed (invalid tags preserved as custom tags)
            assert result.exit_code == 0
            
            docs = self.test_db.list_documents()
            doc_id = docs[0]["id"]
            stored_tags = get_document_tags(doc_id)
            
            # Valid aliases should be expanded, invalid ones preserved
            expected = ["🎯", "invalid@tag", "🚀", "#hashtag", "🐛"]
            assert set(stored_tags) == set(expected)
            
            # Search should work for both expanded and preserved tags
            gameplan_search = self.runner.invoke(app, [
                'find', '--tags', 'gameplan'
            ])
            assert gameplan_search.exit_code == 0
            assert "Mixed Validity Document" in gameplan_search.stdout
            
            # Search for invalid tag should also work
            invalid_search = self.runner.invoke(app, [
                'find', '--tags', 'invalid@tag'
            ])
            assert invalid_search.exit_code == 0
            assert "Mixed Validity Document" in invalid_search.stdout

    def test_empty_and_whitespace_tag_workflow(self):
        """Test workflow with empty and whitespace-only tags."""
        with patch('emdx.core.db', self.test_db), \
             patch('emdx.tags.db', self.test_db), \
             patch('emdx.core.get_project_name', return_value="whitespace-test"):
            
            # Test with various whitespace scenarios
            result = self.runner.invoke(app, [
                'save',
                '--title', 'Whitespace Test Document',
                '--content', 'Testing whitespace in tags',
                '--tags', ' gameplan , , active,  ,bug,  '
            ])
            
            assert result.exit_code == 0
            
            docs = self.test_db.list_documents()
            doc_id = docs[0]["id"]
            stored_tags = get_document_tags(doc_id)
            
            # Should have trimmed whitespace and expanded aliases
            expected = ["🎯", "🚀", "🐛"]
            assert set(stored_tags) == set(expected)


class TestLegendIntegrationWorkflows:
    """Test workflows that integrate legend command with other operations."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    def test_legend_guided_tagging_workflow(self):
        """Test workflow using legend to guide tag selection."""
        with patch('emdx.core.db', TestDatabase(":memory:")), \
             patch('emdx.tags.db', TestDatabase(":memory:")), \
             patch('emdx.core.get_project_name', return_value="legend-guided"):
            
            # Step 1: User checks legend for available aliases
            legend_result = self.runner.invoke(app, ['legend'])
            assert legend_result.exit_code == 0
            assert "gameplan" in legend_result.stdout
            assert "🎯" in legend_result.stdout
            
            # Step 2: User searches legend for specific functionality
            search_result = self.runner.invoke(app, ['legend', '--search', 'plan'])
            assert search_result.exit_code == 0
            assert "gameplan" in search_result.stdout or "🎯" in search_result.stdout
            
            # Step 3: User creates document with aliases learned from legend
            save_result = self.runner.invoke(app, [
                'save',
                '--title', 'Project Planning Document',
                '--content', 'Strategic planning for the new project',
                '--tags', 'gameplan,active,analysis'
            ])
            assert save_result.exit_code == 0

    def test_legend_troubleshooting_workflow(self):
        """Test using legend to troubleshoot tag issues."""
        # User might use legend to understand why their search isn't working
        
        # Step 1: User searches for documents but doesn't find what they expect
        with patch('emdx.core.db', TestDatabase(":memory:")), \
             patch('emdx.tags.db', TestDatabase(":memory:")):
            
            search_result = self.runner.invoke(app, [
                'find', '--tags', 'plan'
            ])
            assert search_result.exit_code == 0
            # Might not find anything because 'plan' is an alias, not stored directly
            
        # Step 2: User checks legend to understand available aliases
        legend_result = self.runner.invoke(app, ['legend', '--search', 'plan'])
        assert legend_result.exit_code == 0
        
        # Step 3: User realizes they should search for 'gameplan' or use the emoji
        with patch('emdx.core.db', TestDatabase(":memory:")), \
             patch('emdx.tags.db', TestDatabase(":memory:")):
            
            corrected_search = self.runner.invoke(app, [
                'find', '--tags', 'gameplan'
            ])
            assert corrected_search.exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])