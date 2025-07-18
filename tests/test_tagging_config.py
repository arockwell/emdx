"""Tests for the tagging configuration system."""

import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, mock_open

from emdx.config.tagging_rules import TaggingRule, TaggingConfig, merge_with_defaults


class TestTaggingRule:
    """Test the TaggingRule dataclass."""
    
    def test_create_rule(self):
        """Test creating a tagging rule."""
        rule = TaggingRule(
            name="test_rule",
            title_patterns=[r"test:"],
            content_patterns=[r"assert"],
            tags=["test"],
            confidence=0.8
        )
        
        assert rule.name == "test_rule"
        assert rule.title_patterns == [r"test:"]
        assert rule.content_patterns == [r"assert"]
        assert rule.tags == ["test"]
        assert rule.confidence == 0.8
        assert rule.enabled is True
    
    def test_rule_to_dict(self):
        """Test converting rule to dictionary."""
        rule = TaggingRule(
            name="test_rule",
            title_patterns=[r"test:"],
            content_patterns=[],
            tags=["test"]
        )
        
        data = rule.to_dict()
        assert data['name'] == "test_rule"
        assert data['title_patterns'] == [r"test:"]
        assert data['tags'] == ["test"]
        assert data['confidence'] == 0.75  # default
    
    def test_rule_from_dict(self):
        """Test creating rule from dictionary."""
        data = {
            'name': 'test_rule',
            'title_patterns': [r'test:'],
            'content_patterns': [r'pytest'],
            'tags': ['test', 'qa'],
            'confidence': 0.9,
            'enabled': False
        }
        
        rule = TaggingRule.from_dict(data)
        assert rule.name == 'test_rule'
        assert rule.tags == ['test', 'qa']
        assert rule.confidence == 0.9
        assert rule.enabled is False


class TestTaggingConfig:
    """Test the TaggingConfig class."""
    
    @pytest.fixture
    def temp_config_path(self):
        """Create a temporary config file path."""
        with tempfile.NamedTemporaryFile(suffix='.yaml', delete=False) as tmp:
            yield tmp.name
        Path(tmp.name).unlink(missing_ok=True)
    
    def test_create_default_config(self, temp_config_path):
        """Test creating default configuration."""
        config = TaggingConfig(config_path=temp_config_path)
        
        # Should have default rules
        assert len(config.rules) > 0
        assert 'meeting_notes' in config.rules
        assert 'code_review' in config.rules
        
        # Verify file was created
        assert Path(temp_config_path).exists()
    
    def test_load_existing_config(self, temp_config_path):
        """Test loading existing configuration."""
        # Create a config file
        config_data = {
            'rules': {
                'custom_rule': {
                    'title_patterns': [r'custom:'],
                    'content_patterns': [],
                    'tags': ['custom'],
                    'confidence': 0.85,
                    'enabled': True
                }
            }
        }
        
        with open(temp_config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # Load it
        config = TaggingConfig(config_path=temp_config_path)
        
        assert 'custom_rule' in config.rules
        assert config.rules['custom_rule'].tags == ['custom']
        assert config.rules['custom_rule'].confidence == 0.85
    
    def test_save_config(self, temp_config_path):
        """Test saving configuration."""
        config = TaggingConfig(config_path=temp_config_path)
        
        # Add a custom rule
        rule = TaggingRule(
            name='save_test',
            title_patterns=[r'saved:'],
            content_patterns=[],
            tags=['saved'],
            confidence=0.7
        )
        config.add_rule(rule)
        
        # Load in a new instance
        config2 = TaggingConfig(config_path=temp_config_path)
        assert 'save_test' in config2.rules
        assert config2.rules['save_test'].tags == ['saved']
    
    def test_add_rule(self, temp_config_path):
        """Test adding a rule."""
        config = TaggingConfig(config_path=temp_config_path)
        initial_count = len(config.rules)
        
        rule = TaggingRule(
            name='new_rule',
            title_patterns=[r'new:'],
            content_patterns=[],
            tags=['new']
        )
        
        result = config.add_rule(rule)
        assert result is True
        assert len(config.rules) == initial_count + 1
        assert 'new_rule' in config.rules
    
    def test_remove_rule(self, temp_config_path):
        """Test removing a rule."""
        config = TaggingConfig(config_path=temp_config_path)
        
        # Add then remove
        rule = TaggingRule(name='temp_rule', title_patterns=[], content_patterns=[], tags=['temp'])
        config.add_rule(rule)
        assert 'temp_rule' in config.rules
        
        result = config.remove_rule('temp_rule')
        assert result is True
        assert 'temp_rule' not in config.rules
        
        # Try removing non-existent
        result = config.remove_rule('non_existent')
        assert result is False
    
    def test_get_rule(self, temp_config_path):
        """Test getting a specific rule."""
        config = TaggingConfig(config_path=temp_config_path)
        
        rule = config.get_rule('meeting_notes')
        assert rule is not None
        assert rule.name == 'meeting_notes'
        
        rule = config.get_rule('non_existent')
        assert rule is None
    
    def test_list_rules(self, temp_config_path):
        """Test listing active rules."""
        config = TaggingConfig(config_path=temp_config_path)
        
        # Disable one rule
        if 'meeting_notes' in config.rules:
            config.disable_rule('meeting_notes')
        
        active_rules = config.list_rules()
        assert all(rule.enabled for rule in active_rules)
        assert not any(rule.name == 'meeting_notes' for rule in active_rules)
    
    def test_enable_disable_rule(self, temp_config_path):
        """Test enabling and disabling rules."""
        config = TaggingConfig(config_path=temp_config_path)
        
        # Disable
        result = config.disable_rule('meeting_notes')
        assert result is True
        assert config.rules['meeting_notes'].enabled is False
        
        # Enable
        result = config.enable_rule('meeting_notes')
        assert result is True
        assert config.rules['meeting_notes'].enabled is True
        
        # Non-existent rule
        result = config.disable_rule('non_existent')
        assert result is False
    
    def test_export_rules(self, temp_config_path):
        """Test exporting rules for AutoTagger."""
        config = TaggingConfig(config_path=temp_config_path)
        
        # Disable one rule
        config.disable_rule('meeting_notes')
        
        exported = config.export_rules()
        
        # Should only include enabled rules
        assert 'meeting_notes' not in exported
        assert 'code_review' in exported
        
        # Check format
        for name, rule_data in exported.items():
            assert 'title_patterns' in rule_data
            assert 'content_patterns' in rule_data
            assert 'tags' in rule_data
            assert 'confidence' in rule_data
    
    def test_import_rules(self, temp_config_path):
        """Test importing rules."""
        config = TaggingConfig(config_path=temp_config_path)
        
        rules_data = {
            'imported_rule': {
                'title_patterns': [r'import:'],
                'content_patterns': [r'from'],
                'tags': ['import'],
                'confidence': 0.8
            }
        }
        
        config.import_rules(rules_data)
        
        assert 'imported_rule' in config.rules
        assert config.rules['imported_rule'].tags == ['import']
    
    def test_validate_rule(self, temp_config_path):
        """Test rule validation."""
        config = TaggingConfig(config_path=temp_config_path)
        
        # Valid rule
        valid_rule = TaggingRule(
            name='valid',
            title_patterns=[r'test:'],
            content_patterns=[],
            tags=['test'],
            confidence=0.8
        )
        errors = config.validate_rule(valid_rule)
        assert len(errors) == 0
        
        # Invalid: no name
        invalid_rule1 = TaggingRule(
            name='',
            title_patterns=[r'test:'],
            content_patterns=[],
            tags=['test']
        )
        errors = config.validate_rule(invalid_rule1)
        assert any('name' in error for error in errors)
        
        # Invalid: no tags
        invalid_rule2 = TaggingRule(
            name='notags',
            title_patterns=[r'test:'],
            content_patterns=[],
            tags=[]
        )
        errors = config.validate_rule(invalid_rule2)
        assert any('tag' in error for error in errors)
        
        # Invalid: no patterns
        invalid_rule3 = TaggingRule(
            name='nopatterns',
            title_patterns=[],
            content_patterns=[],
            tags=['test']
        )
        errors = config.validate_rule(invalid_rule3)
        assert any('pattern' in error for error in errors)
        
        # Invalid: bad regex
        invalid_rule4 = TaggingRule(
            name='badregex',
            title_patterns=[r'[invalid(regex'],
            content_patterns=[],
            tags=['test']
        )
        errors = config.validate_rule(invalid_rule4)
        assert any('regex' in error for error in errors)
        
        # Invalid: confidence out of bounds
        invalid_rule5 = TaggingRule(
            name='badconf',
            title_patterns=[r'test:'],
            content_patterns=[],
            tags=['test'],
            confidence=1.5
        )
        errors = config.validate_rule(invalid_rule5)
        assert any('confidence' in error for error in errors)
    
    def test_invalid_config_file(self, temp_config_path):
        """Test handling invalid config file."""
        # Write invalid YAML
        with open(temp_config_path, 'w') as f:
            f.write("invalid: yaml: content: [")
        
        # Should handle gracefully and create default
        config = TaggingConfig(config_path=temp_config_path)
        assert len(config.rules) == 0  # Empty due to error


class TestMergeWithDefaults:
    """Test merging custom patterns with defaults."""
    
    @patch('emdx.config.tagging_rules.get_default_config')
    def test_merge_with_defaults(self, mock_get_config):
        """Test merging custom patterns with defaults."""
        # Mock config with custom rules
        mock_config = mock_get_config.return_value
        mock_config.export_rules.return_value = {
            'custom_from_config': {
                'title_patterns': [r'config:'],
                'content_patterns': [],
                'tags': ['config'],
                'confidence': 0.8
            }
        }
        
        # Custom patterns to merge
        custom_patterns = {
            'custom_direct': {
                'title_patterns': [r'direct:'],
                'content_patterns': [],
                'tags': ['direct'],
                'confidence': 0.9
            }
        }
        
        # Merge
        merged = merge_with_defaults(custom_patterns)
        
        # Should have all three sources
        assert 'gameplan' in merged  # from AutoTagger defaults
        assert 'custom_from_config' in merged  # from config
        assert 'custom_direct' in merged  # from parameter
    
    @patch('emdx.config.tagging_rules.get_default_config')
    def test_merge_precedence(self, mock_get_config):
        """Test that custom patterns override defaults."""
        # Mock config that overrides 'gameplan'
        mock_config = mock_get_config.return_value
        mock_config.export_rules.return_value = {
            'gameplan': {
                'title_patterns': [r'custom_gameplan:'],
                'content_patterns': [],
                'tags': ['custom_tag'],
                'confidence': 0.95
            }
        }
        
        merged = merge_with_defaults(None)
        
        # Custom should override default
        assert merged['gameplan']['tags'] == ['custom_tag']
        assert merged['gameplan']['confidence'] == 0.95


if __name__ == "__main__":
    pytest.main([__file__, "-v"])