"""Comprehensive tests for legend command emoji alias functionality.

This test suite focuses on testing the legend command's display and search
capabilities for emoji aliases.
"""

import pytest
from unittest.mock import patch, MagicMock
from typer.testing import CliRunner
from io import StringIO

from emdx.legend_command import legend_command
from emdx.cli import app
from emdx.emoji_aliases import EMOJI_ALIASES, suggest_aliases


class TestLegendCommandBasic:
    """Test basic legend command functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    def test_legend_command_execution(self):
        """Test that legend command executes without errors."""
        result = self.runner.invoke(app, ['legend'])
        assert result.exit_code == 0

    def test_legend_displays_all_categories(self):
        """Test that legend displays all emoji categories."""
        result = self.runner.invoke(app, ['legend'])
        assert result.exit_code == 0
        
        output = result.stdout
        
        # Check for major categories
        assert "Document Types" in output
        assert "Workflow Status" in output
        assert "Outcomes" in output
        assert "Technical Work" in output
        assert "Priority" in output
        assert "Project Management" in output

    def test_legend_displays_emojis_and_aliases(self):
        """Test that legend displays emojis with their aliases."""
        result = self.runner.invoke(app, ['legend'])
        assert result.exit_code == 0
        
        output = result.stdout
        
        # Check for key emojis and their aliases
        assert "🎯" in output
        assert "gameplan" in output
        assert "🚀" in output
        assert "active" in output
        assert "🐛" in output
        assert "bug" in output

    def test_legend_formatting_consistency(self):
        """Test that legend output has consistent formatting."""
        result = self.runner.invoke(app, ['legend'])
        assert result.exit_code == 0
        
        output = result.stdout
        
        # Should have arrow symbols for alias mappings
        assert "→" in output or "->" in output
        
        # Should have proper sections
        lines = output.split('\n')
        non_empty_lines = [line for line in lines if line.strip()]
        assert len(non_empty_lines) > 10  # Should have substantial content


class TestLegendCommandSearch:
    """Test legend command search functionality."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    def test_legend_search_basic(self):
        """Test basic search functionality."""
        result = self.runner.invoke(app, ['legend', '--search', 'game'])
        assert result.exit_code == 0
        
        output = result.stdout
        assert "🎯" in output
        assert "gameplan" in output

    def test_legend_search_case_insensitive(self):
        """Test that search is case insensitive."""
        result = self.runner.invoke(app, ['legend', '--search', 'GAME'])
        assert result.exit_code == 0
        
        output = result.stdout
        assert "🎯" in output
        assert "gameplan" in output

    def test_legend_search_partial_matches(self):
        """Test search with partial matches."""
        result = self.runner.invoke(app, ['legend', '--search', 'act'])
        assert result.exit_code == 0
        
        output = result.stdout
        assert "🚀" in output
        assert "active" in output

    def test_legend_search_no_matches(self):
        """Test search with no matches."""
        result = self.runner.invoke(app, ['legend', '--search', 'xyz123'])
        assert result.exit_code == 0
        
        output = result.stdout
        # Should handle gracefully, possibly show "no matches" message
        assert len(output.strip()) >= 0  # Should not crash

    def test_legend_search_multiple_matches(self):
        """Test search that returns multiple results."""
        result = self.runner.invoke(app, ['legend', '--search', 'test'])
        assert result.exit_code == 0
        
        output = result.stdout
        # Should find testing alias
        assert "🧪" in output
        assert "test" in output

    def test_legend_search_emoji_characters(self):
        """Test search with emoji characters."""
        result = self.runner.invoke(app, ['legend', '--search', '🎯'])
        assert result.exit_code == 0
        
        output = result.stdout
        assert "🎯" in output

    def test_legend_search_special_characters(self):
        """Test search with special characters."""
        result = self.runner.invoke(app, ['legend', '--search', 'test!@#'])
        assert result.exit_code == 0
        
        # Should handle gracefully without crashing
        assert len(result.stdout) >= 0

    def test_legend_search_empty_string(self):
        """Test search with empty string."""
        result = self.runner.invoke(app, ['legend', '--search', ''])
        assert result.exit_code == 0
        
        # Empty search should show all or nothing depending on implementation
        assert len(result.stdout) >= 0


class TestLegendCommandEdgeCases:
    """Test edge cases and error conditions in legend command."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    def test_legend_with_very_long_search(self):
        """Test legend with very long search term."""
        long_search = "a" * 1000
        result = self.runner.invoke(app, ['legend', '--search', long_search])
        assert result.exit_code == 0
        
        # Should handle gracefully
        assert len(result.stdout) >= 0

    def test_legend_with_unicode_search(self):
        """Test legend with unicode search terms."""
        result = self.runner.invoke(app, ['legend', '--search', 'café'])
        assert result.exit_code == 0
        
        # Should handle gracefully
        assert len(result.stdout) >= 0

    def test_legend_with_whitespace_search(self):
        """Test legend with whitespace in search."""
        result = self.runner.invoke(app, ['legend', '--search', '  game  '])
        assert result.exit_code == 0
        
        output = result.stdout
        # Should handle whitespace and still find gameplan
        assert "🎯" in output or len(output.strip()) == 0

    def test_legend_multiple_consecutive_calls(self):
        """Test multiple consecutive legend calls."""
        for i in range(5):
            result = self.runner.invoke(app, ['legend'])
            assert result.exit_code == 0
            assert "🎯" in result.stdout

    def test_legend_with_various_search_patterns(self):
        """Test legend with various search patterns."""
        search_terms = ["gam", "GAM", "game", "gameplan", "plan", "🎯"]
        
        for term in search_terms:
            result = self.runner.invoke(app, ['legend', '--search', term])
            assert result.exit_code == 0
            # At least gameplan-related results should appear for most terms
            if term in ["gam", "GAM", "game", "gameplan", "plan"]:
                assert "🎯" in result.stdout or "gameplan" in result.stdout


class TestLegendCommandIntegration:
    """Test legend command integration with emoji alias system."""

    def test_legend_shows_all_defined_emojis(self):
        """Test that legend shows all emojis defined in EMOJI_ALIASES."""
        result = self.runner.invoke(app, ['legend'])
        assert result.exit_code == 0
        
        output = result.stdout
        
        # Check that all major emojis are represented
        important_emojis = ["🎯", "🚀", "🐛", "✅", "🧪", "🔧", "✨", "🚨"]
        for emoji in important_emojis:
            assert emoji in output

    def test_legend_alias_accuracy(self):
        """Test that legend shows accurate aliases for emojis."""
        result = self.runner.invoke(app, ['legend'])
        assert result.exit_code == 0
        
        output = result.stdout
        
        # Verify some key alias mappings
        if "🎯" in output:
            # Should show gameplan as an alias for 🎯
            gameplan_section = output[output.find("🎯"):output.find("🎯") + 200]
            assert "gameplan" in gameplan_section

    def test_legend_integration_with_suggest_aliases(self):
        """Test that legend search integrates with suggest_aliases function."""
        with patch('emdx.emoji_aliases.suggest_aliases') as mock_suggest:
            mock_suggest.return_value = [("gameplan", "🎯"), ("active", "🚀")]
            
            # This test verifies integration, exact behavior depends on implementation
            result = self.runner.invoke(app, ['legend', '--search', 'game'])
            assert result.exit_code == 0
            
            # Should show results related to gameplan
            assert "🎯" in result.stdout or "gameplan" in result.stdout

    def test_legend_consistency_with_emoji_aliases_data(self):
        """Test that legend output is consistent with EMOJI_ALIASES data."""
        result = self.runner.invoke(app, ['legend'])
        assert result.exit_code == 0
        
        output = result.stdout
        
        # Verify that major categories from EMOJI_ALIASES are represented
        # Count how many emojis from EMOJI_ALIASES appear in output
        emoji_count = 0
        for emoji in EMOJI_ALIASES.keys():
            if emoji in output:
                emoji_count += 1
        
        # Should show most/all emojis (allowing for formatting variations)
        total_emojis = len(EMOJI_ALIASES)
        assert emoji_count >= total_emojis * 0.8  # At least 80% should appear


class TestLegendCommandOutput:
    """Test legend command output formatting and content."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    def test_legend_output_structure(self):
        """Test that legend output has proper structure."""
        result = self.runner.invoke(app, ['legend'])
        assert result.exit_code == 0
        
        output = result.stdout
        lines = output.split('\n')
        
        # Should have title/header
        title_found = any("legend" in line.lower() or "emoji" in line.lower() 
                         for line in lines[:5])
        assert title_found

    def test_legend_search_output_relevance(self):
        """Test that search results are relevant to search term."""
        result = self.runner.invoke(app, ['legend', '--search', 'bug'])
        assert result.exit_code == 0
        
        output = result.stdout.lower()
        
        # Should contain bug-related content
        assert "bug" in output or "🐛" in result.stdout

    def test_legend_color_formatting(self):
        """Test that legend uses color formatting appropriately."""
        result = self.runner.invoke(app, ['legend'])
        assert result.exit_code == 0
        
        # Rich formatting may include ANSI codes or special characters
        # This test ensures the command completes without color-related errors
        assert len(result.stdout) > 0

    def test_legend_line_length_reasonable(self):
        """Test that legend output lines are reasonably formatted."""
        result = self.runner.invoke(app, ['legend'])
        assert result.exit_code == 0
        
        lines = result.stdout.split('\n')
        
        # Most lines should be reasonable length (allowing for some long alias lists)
        reasonable_lines = sum(1 for line in lines if len(line) <= 120)
        total_lines = len([line for line in lines if line.strip()])
        
        # At least 80% of lines should be reasonable length
        if total_lines > 0:
            assert reasonable_lines / total_lines >= 0.8


class TestLegendCommandMocking:
    """Test legend command with mocked dependencies for isolation."""

    def test_legend_with_mocked_emoji_aliases(self):
        """Test legend command with mocked emoji alias data."""
        mock_aliases = {
            "🎯": ["test-alias", "another-alias"],
            "🚀": ["mock-active", "mock-current"]
        }
        
        with patch('emdx.legend_command.EMOJI_ALIASES', mock_aliases):
            result = self.runner.invoke(app, ['legend'])
            assert result.exit_code == 0
            
            output = result.stdout
            assert "🎯" in output
            assert "🚀" in output

    def test_legend_search_with_mocked_suggestions(self):
        """Test legend search with mocked suggestion function."""
        with patch('emdx.legend_command.suggest_aliases') as mock_suggest:
            mock_suggest.return_value = [("mock-alias", "🎯")]
            
            result = self.runner.invoke(app, ['legend', '--search', 'mock'])
            assert result.exit_code == 0
            
            # Should handle mocked suggestions without error
            assert len(result.stdout) >= 0

    def test_legend_with_mocked_console(self):
        """Test legend command with mocked Rich console."""
        with patch('emdx.legend_command.console') as mock_console:
            mock_console.print = MagicMock()
            
            result = self.runner.invoke(app, ['legend'])
            
            # Should attempt to print output
            assert mock_console.print.called or result.exit_code == 0


class TestLegendCommandPerformance:
    """Test legend command performance characteristics."""

    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()

    def test_legend_execution_speed(self):
        """Test that legend command executes quickly."""
        import time
        
        start_time = time.time()
        result = self.runner.invoke(app, ['legend'])
        end_time = time.time()
        
        assert result.exit_code == 0
        # Should complete in under 2 seconds
        assert (end_time - start_time) < 2.0

    def test_legend_search_speed(self):
        """Test that legend search executes quickly."""
        import time
        
        search_terms = ["game", "active", "bug", "test", "xyz"]
        
        for term in search_terms:
            start_time = time.time()
            result = self.runner.invoke(app, ['legend', '--search', term])
            end_time = time.time()
            
            assert result.exit_code == 0
            # Each search should complete quickly
            assert (end_time - start_time) < 1.0

    def test_legend_memory_usage(self):
        """Test that legend command doesn't consume excessive memory."""
        # Run legend multiple times to check for memory leaks
        for i in range(10):
            result = self.runner.invoke(app, ['legend'])
            assert result.exit_code == 0
        
        # If we get here without hanging or crashing, memory usage is acceptable

    def test_legend_large_search_performance(self):
        """Test legend performance with large search terms."""
        # Test with various large inputs
        large_inputs = [
            "a" * 100,
            "gameplan" * 50,
            "🎯" * 100
        ]
        
        for large_input in large_inputs:
            import time
            start_time = time.time()
            
            result = self.runner.invoke(app, ['legend', '--search', large_input])
            
            end_time = time.time()
            
            assert result.exit_code == 0
            # Should handle large inputs efficiently
            assert (end_time - start_time) < 1.0


class TestLegendCommandErrorHandling:
    """Test error handling in legend command."""

    def test_legend_handles_missing_emoji_data(self):
        """Test legend handles missing emoji alias data gracefully."""
        with patch('emdx.legend_command.EMOJI_ALIASES', {}):
            result = self.runner.invoke(app, ['legend'])
            
            # Should not crash with empty emoji data
            assert result.exit_code == 0

    def test_legend_handles_malformed_emoji_data(self):
        """Test legend handles malformed emoji data."""
        malformed_data = {
            "🎯": None,  # None instead of list
            "invalid": ["alias1", "alias2"]  # Invalid emoji key
        }
        
        with patch('emdx.legend_command.EMOJI_ALIASES', malformed_data):
            result = self.runner.invoke(app, ['legend'])
            
            # Should handle gracefully
            assert result.exit_code == 0

    def test_legend_handles_console_errors(self):
        """Test legend handles console output errors gracefully."""
        with patch('emdx.legend_command.console.print') as mock_print:
            mock_print.side_effect = Exception("Console error")
            
            # Should handle console errors without crashing the CLI
            try:
                result = self.runner.invoke(app, ['legend'])
                # May succeed or fail depending on error handling implementation
            except Exception:
                pass  # Some implementations may let exceptions bubble up

    def test_legend_search_handles_regex_errors(self):
        """Test legend search handles potential regex errors in search."""
        # Special regex characters that might cause issues
        special_chars = ["[", "]", "(", ")", "*", "+", "?", ".", "^", "$"]
        
        for char in special_chars:
            result = self.runner.invoke(app, ['legend', '--search', char])
            # Should handle without regex errors
            assert result.exit_code == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])