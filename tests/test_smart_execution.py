"""Tests for smart execution system."""

import pytest

from emdx.commands.claude_execute import ExecutionType, get_execution_context


def test_execution_context_detection():
    """Test that execution context is correctly detected based on tags."""
    # Test note detection (using emoji tags)
    context = get_execution_context(['📝', 'other'])
    assert context['type'] == ExecutionType.NOTE
    assert 'analysis' in context['output_tags']
    assert context['output_title_prefix'] == 'Analysis: '
    
    # Test analysis detection
    context = get_execution_context(['🔍', '🚀'])
    assert context['type'] == ExecutionType.ANALYSIS
    assert 'gameplan' in context['output_tags']
    assert 'active' in context['output_tags']
    assert context['output_title_prefix'] == 'Gameplan: '
    
    # Test gameplan detection
    context = get_execution_context(['🎯', '🚀'])
    assert context['type'] == ExecutionType.GAMEPLAN
    assert context.get('create_pr') is True
    assert len(context['output_tags']) == 0
    
    # Test generic detection
    context = get_execution_context(['random', 'tags'])
    assert context['type'] == ExecutionType.GENERIC
    assert context['prompt_template'] is None


def test_emoji_tag_detection():
    """Test that emoji tags are properly detected."""
    # Test note emoji
    context = get_execution_context(['📝'])
    assert context['type'] == ExecutionType.NOTE
    
    # Test analysis emoji
    context = get_execution_context(['🔍'])
    assert context['type'] == ExecutionType.ANALYSIS
    
    # Test gameplan emoji
    context = get_execution_context(['🎯'])
    assert context['type'] == ExecutionType.GAMEPLAN


def test_prompt_building():
    """Test prompt template system."""
    from emdx.prompts import build_prompt
    
    # Test with no template
    prompt = build_prompt(None, 'Test content')
    assert prompt == 'Test content'
    
    # Test with valid template
    prompt = build_prompt('analyze_note', 'Test content')
    assert 'Test content' in prompt
    assert 'Analyze this note' in prompt
    
    # Test invalid template
    with pytest.raises(ValueError):
        build_prompt('invalid_template', 'Test content')