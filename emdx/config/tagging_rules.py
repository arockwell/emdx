"""
Tagging rules and configuration for EMDX auto-tagger.
Allows users to define custom patterns for auto-tagging.
"""

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class TaggingRule:
    """Represents a single tagging rule."""
    name: str
    title_patterns: List[str]
    content_patterns: List[str]
    tags: List[str]
    confidence: float = 0.75
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaggingRule':
        """Create from dictionary."""
        return cls(**data)


class TaggingConfig:
    """Manages tagging configuration and custom rules."""
    
    DEFAULT_CONFIG_PATH = "~/.config/emdx/tagging.yaml"
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path or self.DEFAULT_CONFIG_PATH).expanduser()
        self.rules: Dict[str, TaggingRule] = {}
        self.load_config()
    
    def load_config(self):
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    data = yaml.safe_load(f) or {}
                
                # Load custom rules
                for name, rule_data in data.get('rules', {}).items():
                    self.rules[name] = TaggingRule.from_dict({
                        'name': name,
                        **rule_data
                    })
            except Exception as e:
                # If config is invalid, start fresh but log the error
                logger.warning(f"Could not load tagging config: {e}")
                self.rules = {}
        else:
            # Create default config
            self.create_default_config()
    
    def save_config(self):
        """Save configuration to file."""
        # Ensure directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert rules to serializable format
        data = {
            'rules': {
                name: rule.to_dict()
                for name, rule in self.rules.items()
            }
        }
        
        # Remove 'name' from each rule dict (redundant with key)
        for rule_data in data['rules'].values():
            rule_data.pop('name', None)
        
        with open(self.config_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def create_default_config(self):
        """Create default configuration with example rules."""
        self.rules = {
            'meeting_notes': TaggingRule(
                name='meeting_notes',
                title_patterns=[r'meeting:', r'meeting with', r'standup:', r'1:1 with'],
                content_patterns=[r'action items:', r'decisions:', r'attendees:'],
                tags=['notes', 'meeting'],
                confidence=0.85
            ),
            'code_review': TaggingRule(
                name='code_review',
                title_patterns=[r'review:', r'code review:', r'pr review:'],
                content_patterns=[r'lgtm', r'approved', r'changes requested', r'nit:'],
                tags=['review', 'code'],
                confidence=0.8
            ),
            'learning': TaggingRule(
                name='learning',
                title_patterns=[r'til:', r'learned:', r'learning:'],
                content_patterns=[r'learned that', r'discovered', r'found out'],
                tags=['learning', 'notes'],
                confidence=0.75
            ),
            'ideas': TaggingRule(
                name='ideas',
                title_patterns=[r'idea:', r'concept:', r'proposal:'],
                content_patterns=[r'what if', r'we could', r'propose'],
                tags=['idea', 'proposal'],
                confidence=0.7
            )
        }
        self.save_config()
    
    def add_rule(self, rule: TaggingRule) -> bool:
        """Add or update a tagging rule."""
        self.rules[rule.name] = rule
        self.save_config()
        return True
    
    def remove_rule(self, name: str) -> bool:
        """Remove a tagging rule."""
        if name in self.rules:
            del self.rules[name]
            self.save_config()
            return True
        return False
    
    def get_rule(self, name: str) -> Optional[TaggingRule]:
        """Get a specific rule by name."""
        return self.rules.get(name)
    
    def list_rules(self) -> List[TaggingRule]:
        """List all active rules."""
        return [rule for rule in self.rules.values() if rule.enabled]
    
    def enable_rule(self, name: str) -> bool:
        """Enable a rule."""
        if name in self.rules:
            self.rules[name].enabled = True
            self.save_config()
            return True
        return False
    
    def disable_rule(self, name: str) -> bool:
        """Disable a rule."""
        if name in self.rules:
            self.rules[name].enabled = False
            self.save_config()
            return True
        return False
    
    def export_rules(self) -> Dict[str, Any]:
        """Export rules as a dictionary compatible with AutoTagger."""
        return {
            name: {
                'title_patterns': rule.title_patterns,
                'content_patterns': rule.content_patterns,
                'tags': rule.tags,
                'confidence': rule.confidence
            }
            for name, rule in self.rules.items()
            if rule.enabled
        }
    
    def import_rules(self, rules_data: Dict[str, Any]):
        """Import rules from a dictionary."""
        for name, rule_data in rules_data.items():
            self.rules[name] = TaggingRule(
                name=name,
                title_patterns=rule_data.get('title_patterns', []),
                content_patterns=rule_data.get('content_patterns', []),
                tags=rule_data.get('tags', []),
                confidence=rule_data.get('confidence', 0.75),
                enabled=rule_data.get('enabled', True)
            )
        self.save_config()
    
    def validate_rule(self, rule: TaggingRule) -> List[str]:
        """Validate a tagging rule and return any errors."""
        errors = []
        
        if not rule.name:
            errors.append("Rule must have a name")
        
        if not rule.tags:
            errors.append("Rule must specify at least one tag")
        
        if not rule.title_patterns and not rule.content_patterns:
            errors.append("Rule must have at least one title or content pattern")
        
        if rule.confidence < 0 or rule.confidence > 1:
            errors.append("Confidence must be between 0 and 1")
        
        # Test regex patterns
        import re
        for pattern in rule.title_patterns + rule.content_patterns:
            try:
                re.compile(pattern)
            except re.error as e:
                errors.append(f"Invalid regex pattern '{pattern}': {e}")
        
        return errors


def get_default_config() -> TaggingConfig:
    """Get the default tagging configuration."""
    return TaggingConfig()


def merge_with_defaults(custom_patterns: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge custom patterns with default AutoTagger patterns.
    Custom patterns take precedence.
    """
    from ..services.auto_tagger import AutoTagger
    
    # Start with default patterns
    merged = AutoTagger.DEFAULT_PATTERNS.copy()
    
    # Load custom patterns from config
    config = get_default_config()
    custom_from_config = config.export_rules()
    
    # Merge config patterns
    merged.update(custom_from_config)
    
    # Merge provided custom patterns (highest priority)
    if custom_patterns:
        merged.update(custom_patterns)
    
    return merged
