"""
Tagging rules and configuration for EMDX auto-tagger.
Allows users to define custom patterns for auto-tagging.
"""

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from .constants import DEFAULT_TAGGING_CONFIDENCE, EMDX_CONFIG_DIR

logger = logging.getLogger(__name__)


@dataclass
class TaggingRule:
    """Represents a single tagging rule."""

    name: str
    title_patterns: list[str]
    content_patterns: list[str]
    tags: list[str]
    confidence: float = DEFAULT_TAGGING_CONFIDENCE
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaggingRule":
        """Create from dictionary."""
        return cls(**data)


class TaggingConfig:
    """Manages tagging configuration and custom rules."""

    DEFAULT_CONFIG_PATH = str(EMDX_CONFIG_DIR / "tagging.yaml")

    def __init__(self, config_path: str | None = None):
        self.config_path = Path(config_path or self.DEFAULT_CONFIG_PATH).expanduser()
        self.rules: dict[str, TaggingRule] = {}
        self.load_config()

    def load_config(self) -> None:
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    data = yaml.safe_load(f) or {}

                # Load custom rules
                for name, rule_data in data.get("rules", {}).items():
                    self.rules[name] = TaggingRule.from_dict({"name": name, **rule_data})
            except Exception as e:
                # If config is invalid, start fresh but log the error
                logger.warning(f"Could not load tagging config: {e}")
                self.rules = {}
        else:
            # Create default config
            self.create_default_config()

    def save_config(self) -> None:
        """Save configuration to file."""
        # Ensure directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Convert rules to serializable format
        data = {"rules": {name: rule.to_dict() for name, rule in self.rules.items()}}

        # Remove 'name' from each rule dict (redundant with key)
        for rule_data in data["rules"].values():
            rule_data.pop("name", None)

        with open(self.config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def create_default_config(self) -> None:
        """Create default configuration with example rules."""
        self.rules = {
            "meeting_notes": TaggingRule(
                name="meeting_notes",
                title_patterns=[r"meeting:", r"meeting with", r"standup:", r"1:1 with"],
                content_patterns=[r"action items:", r"decisions:", r"attendees:"],
                tags=["notes", "meeting"],
                confidence=0.85,
            ),
            "code_review": TaggingRule(
                name="code_review",
                title_patterns=[r"review:", r"code review:", r"pr review:"],
                content_patterns=[r"lgtm", r"approved", r"changes requested", r"nit:"],
                tags=["review", "code"],
                confidence=0.8,
            ),
            "learning": TaggingRule(
                name="learning",
                title_patterns=[r"til:", r"learned:", r"learning:"],
                content_patterns=[r"learned that", r"discovered", r"found out"],
                tags=["learning", "notes"],
                confidence=0.75,
            ),
            "ideas": TaggingRule(
                name="ideas",
                title_patterns=[r"idea:", r"concept:", r"proposal:"],
                content_patterns=[r"what if", r"we could", r"propose"],
                tags=["idea", "proposal"],
                confidence=0.7,
            ),
        }
        self.save_config()

    def export_rules(self) -> dict[str, Any]:
        """Export rules as a dictionary compatible with AutoTagger."""
        return {
            name: {
                "title_patterns": rule.title_patterns,
                "content_patterns": rule.content_patterns,
                "tags": rule.tags,
                "confidence": rule.confidence,
            }
            for name, rule in self.rules.items()
            if rule.enabled
        }


def get_default_config() -> TaggingConfig:
    """Get the default tagging configuration."""
    return TaggingConfig()


def merge_with_defaults(custom_patterns: dict[str, Any]) -> dict[str, Any]:
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
