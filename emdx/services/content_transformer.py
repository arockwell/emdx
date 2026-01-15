"""Content transformation service for export profiles.

This module provides the ContentTransformer class which applies a sequence
of transformations to document content based on export profile configuration.

Transform Pipeline:
1. Strip specified emoji tags
2. Apply tag-to-label mapping
3. Add header template
4. Add footer template
5. Add YAML frontmatter
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class TransformContext:
    """Context passed through the transform pipeline."""

    document: dict[str, Any]
    profile: dict[str, Any]
    original_content: str
    transformed_content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ContentTransformer:
    """Transform document content based on export profile configuration."""

    def __init__(self, document: dict[str, Any], profile: dict[str, Any]):
        """Initialize the transformer.

        Args:
            document: Document dictionary with id, title, content, project, etc.
            profile: Export profile dictionary with transform configuration
        """
        self.document = document
        self.profile = profile

    def transform(self) -> TransformContext:
        """Apply all transforms in sequence.

        Returns:
            TransformContext with the transformed content and metadata
        """
        ctx = TransformContext(
            document=self.document,
            profile=self.profile,
            original_content=self.document.get("content", ""),
            transformed_content=self.document.get("content", ""),
            metadata={},
        )

        # Extract tags for metadata before stripping
        ctx = self._extract_tags(ctx)

        # Pipeline of transforms
        ctx = self._strip_tags(ctx)
        ctx = self._apply_tag_labels(ctx)
        ctx = self._add_header(ctx)
        ctx = self._add_footer(ctx)
        ctx = self._add_frontmatter(ctx)

        return ctx

    def _extract_tags(self, ctx: TransformContext) -> TransformContext:
        """Extract emoji tags from content for metadata."""
        # Common emoji tag pattern - single emoji characters
        emoji_pattern = re.compile(
            r"[\U0001F300-\U0001F9FF"  # Miscellaneous Symbols and Pictographs
            r"\U0001FA00-\U0001FA6F"  # Chess Symbols
            r"\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
            r"\U00002702-\U000027B0"  # Dingbats
            r"\U0001F600-\U0001F64F"  # Emoticons
            r"]+",
            re.UNICODE,
        )

        tags = emoji_pattern.findall(ctx.original_content)
        if tags:
            ctx.metadata["tags"] = list(set(tags))

        return ctx

    def _strip_tags(self, ctx: TransformContext) -> TransformContext:
        """Remove specified emoji tags from content."""
        strip_tags = self.profile.get("strip_tags")
        if not strip_tags:
            return ctx

        # Parse JSON if string
        if isinstance(strip_tags, str):
            try:
                strip_tags = json.loads(strip_tags)
            except json.JSONDecodeError:
                logger.debug("Failed to parse strip_tags JSON: %s", strip_tags)
                return ctx

        content = ctx.transformed_content

        for tag in strip_tags:
            # Remove tag and any surrounding whitespace (but preserve newlines)
            # Handle tag at start of line, middle of line, or end of line
            content = re.sub(rf"[ \t]*{re.escape(tag)}[ \t]*", " ", content)
            # Clean up any double spaces
            content = re.sub(r"  +", " ", content)
            # Clean up spaces at start/end of lines
            content = re.sub(r"^ +", "", content, flags=re.MULTILINE)
            content = re.sub(r" +$", "", content, flags=re.MULTILINE)

        ctx.transformed_content = content.strip()
        return ctx

    def _apply_tag_labels(self, ctx: TransformContext) -> TransformContext:
        """Replace emoji tags with text labels."""
        tag_map = self.profile.get("tag_to_label")
        if not tag_map:
            return ctx

        # Parse JSON if string
        if isinstance(tag_map, str):
            try:
                tag_map = json.loads(tag_map)
            except json.JSONDecodeError:
                logger.debug("Failed to parse tag_to_label JSON: %s", tag_map)
                return ctx

        content = ctx.transformed_content

        for emoji, label in tag_map.items():
            content = content.replace(emoji, f"[{label}]")

        ctx.transformed_content = content
        return ctx

    def _add_header(self, ctx: TransformContext) -> TransformContext:
        """Prepend header template to content."""
        header = self.profile.get("header_template")
        if not header:
            return ctx

        header = self._expand_template(header, ctx)
        ctx.transformed_content = f"{header}\n\n{ctx.transformed_content}"
        return ctx

    def _add_footer(self, ctx: TransformContext) -> TransformContext:
        """Append footer template to content."""
        footer = self.profile.get("footer_template")
        if not footer:
            return ctx

        footer = self._expand_template(footer, ctx)
        ctx.transformed_content = f"{ctx.transformed_content}\n\n{footer}"
        return ctx

    def _add_frontmatter(self, ctx: TransformContext) -> TransformContext:
        """Add YAML frontmatter if configured."""
        if not self.profile.get("add_frontmatter"):
            return ctx

        fields = self.profile.get("frontmatter_fields")
        if not fields:
            fields = ["title", "date"]

        # Parse JSON if string
        if isinstance(fields, str):
            try:
                fields = json.loads(fields)
            except json.JSONDecodeError:
                logger.debug("Failed to parse frontmatter_fields JSON: %s, using defaults", fields)
                fields = ["title", "date"]

        frontmatter_data = {}

        if "title" in fields:
            frontmatter_data["title"] = self.document.get("title", "Untitled")
        if "date" in fields:
            frontmatter_data["date"] = datetime.now().strftime("%Y-%m-%d")
        if "tags" in fields and ctx.metadata.get("tags"):
            # Convert emoji tags to text labels if mapping exists
            tag_map = self.profile.get("tag_to_label") or {}
            if isinstance(tag_map, str):
                try:
                    tag_map = json.loads(tag_map)
                except json.JSONDecodeError:
                    logger.debug("Failed to parse tag_to_label JSON in frontmatter: %s", tag_map)
                    tag_map = {}

            tags = []
            for tag in ctx.metadata.get("tags", []):
                if tag in tag_map:
                    tags.append(tag_map[tag])
                else:
                    tags.append(tag)
            frontmatter_data["tags"] = tags
        if "author" in fields:
            frontmatter_data["author"] = "Generated by EMDX"
        if "project" in fields:
            frontmatter_data["project"] = self.document.get("project") or "Unknown"
        if "id" in fields:
            frontmatter_data["id"] = self.document.get("id")

        # Generate YAML frontmatter
        yaml_lines = ["---"]
        for key, value in frontmatter_data.items():
            if isinstance(value, list):
                yaml_lines.append(f"{key}:")
                for item in value:
                    yaml_lines.append(f"  - {item}")
            elif value is not None:
                # Escape special characters in strings
                if isinstance(value, str) and (":" in value or '"' in value):
                    yaml_lines.append(f'{key}: "{value}"')
                else:
                    yaml_lines.append(f"{key}: {value}")
        yaml_lines.append("---")

        ctx.transformed_content = "\n".join(yaml_lines) + "\n\n" + ctx.transformed_content
        return ctx

    def _expand_template(self, template: str, ctx: TransformContext) -> str:
        """Expand template variables.

        Supported variables:
        - {{title}}: Document title
        - {{date}}: Current date (YYYY-MM-DD)
        - {{datetime}}: Current datetime (YYYY-MM-DD HH:MM)
        - {{project}}: Document project
        - {{id}}: Document ID
        - {{tags}}: Comma-separated tags
        """
        replacements = {
            "{{title}}": self.document.get("title", "Untitled"),
            "{{date}}": datetime.now().strftime("%Y-%m-%d"),
            "{{datetime}}": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "{{project}}": self.document.get("project") or "Unknown",
            "{{id}}": str(self.document.get("id", "")),
            "{{tags}}": ", ".join(ctx.metadata.get("tags", [])),
        }

        result = template
        for key, value in replacements.items():
            result = result.replace(key, value)

        return result


def transform_document(
    document: dict[str, Any], profile: dict[str, Any]
) -> TransformContext:
    """Convenience function to transform a document with a profile.

    Args:
        document: Document dictionary
        profile: Export profile dictionary

    Returns:
        TransformContext with transformed content
    """
    transformer = ContentTransformer(document, profile)
    return transformer.transform()
