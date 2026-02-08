"""Tests for emdx.services.content_transformer module."""

import pytest
from datetime import datetime

from emdx.services.content_transformer import (
    ContentTransformer,
    TransformContext,
    transform_document,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc(**overrides):
    """Return a minimal document dict, merged with *overrides*."""
    base = {
        "id": 1,
        "title": "Test Doc",
        "content": "Hello world",
        "project": "proj",
    }
    base.update(overrides)
    return base


def _profile(**overrides):
    """Return a minimal profile dict, merged with *overrides*."""
    base = {"format": "markdown", "dest_type": "clipboard"}
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# TransformContext dataclass
# ---------------------------------------------------------------------------

class TestTransformContext:
    def test_defaults(self):
        ctx = TransformContext(
            document={}, profile={}, original_content="a", transformed_content="b"
        )
        assert ctx.metadata == {}

    def test_metadata_mutable(self):
        ctx = TransformContext(
            document={}, profile={}, original_content="", transformed_content=""
        )
        ctx.metadata["key"] = "val"
        assert ctx.metadata["key"] == "val"


# ---------------------------------------------------------------------------
# _extract_tags
# ---------------------------------------------------------------------------

class TestExtractTags:
    def test_extracts_emoji_tags_to_metadata(self):
        doc = _doc(content="Hello \U0001F680 world \u2702")
        t = ContentTransformer(doc, _profile())
        ctx = t.transform()
        assert "tags" in ctx.metadata
        assert len(ctx.metadata["tags"]) >= 1

    def test_no_emoji_no_tags_key(self):
        doc = _doc(content="Plain text only")
        t = ContentTransformer(doc, _profile())
        ctx = t.transform()
        assert "tags" not in ctx.metadata

    def test_duplicate_emojis_deduped(self):
        doc = _doc(content="\U0001F680 \U0001F680 \U0001F680")
        t = ContentTransformer(doc, _profile())
        ctx = t.transform()
        assert len(ctx.metadata["tags"]) == 1


# ---------------------------------------------------------------------------
# _strip_tags
# ---------------------------------------------------------------------------

class TestStripTags:
    def test_strips_specified_emojis(self):
        doc = _doc(content="\U0001F6A7 WIP text")
        t = ContentTransformer(doc, _profile(strip_tags=["\U0001F6A7"]))
        ctx = t.transform()
        assert "\U0001F6A7" not in ctx.transformed_content
        assert "WIP text" in ctx.transformed_content

    def test_strips_multiple_tags(self):
        doc = _doc(content="\U0001F6A7 hello \U0001F41B bug")
        t = ContentTransformer(
            doc, _profile(strip_tags=["\U0001F6A7", "\U0001F41B"])
        )
        ctx = t.transform()
        assert "\U0001F6A7" not in ctx.transformed_content
        assert "\U0001F41B" not in ctx.transformed_content

    def test_strip_tags_accepts_json_string(self):
        doc = _doc(content="\U0001F6A7 WIP")
        t = ContentTransformer(doc, _profile(strip_tags='["\U0001F6A7"]'))
        ctx = t.transform()
        assert "\U0001F6A7" not in ctx.transformed_content

    def test_strip_tags_bad_json_is_noop(self):
        doc = _doc(content="\U0001F6A7 WIP")
        t = ContentTransformer(doc, _profile(strip_tags="not json"))
        ctx = t.transform()
        # Bad JSON -> skip strip, content preserved
        assert "\U0001F6A7" in ctx.transformed_content

    def test_empty_strip_tags_is_noop(self):
        doc = _doc(content="hello")
        t = ContentTransformer(doc, _profile(strip_tags=[]))
        ctx = t.transform()
        assert ctx.transformed_content == "hello"

    def test_no_strip_tags_key_is_noop(self):
        doc = _doc(content="hello")
        t = ContentTransformer(doc, _profile())
        ctx = t.transform()
        assert ctx.transformed_content == "hello"


# ---------------------------------------------------------------------------
# _apply_tag_labels
# ---------------------------------------------------------------------------

class TestApplyTagLabels:
    def test_emoji_replaced_with_label(self):
        doc = _doc(content="\U0001F41B bug report")
        t = ContentTransformer(
            doc, _profile(tag_to_label={"\U0001F41B": "bug"})
        )
        ctx = t.transform()
        assert "[bug]" in ctx.transformed_content
        assert "\U0001F41B" not in ctx.transformed_content

    def test_multiple_label_mappings(self):
        doc = _doc(content="\U0001F41B bug \u2728 feature")
        t = ContentTransformer(
            doc,
            _profile(
                tag_to_label={"\U0001F41B": "bug", "\u2728": "feature"}
            ),
        )
        ctx = t.transform()
        assert "[bug]" in ctx.transformed_content
        assert "[feature]" in ctx.transformed_content

    def test_tag_to_label_json_string(self):
        doc = _doc(content="\U0001F41B oops")
        t = ContentTransformer(
            doc, _profile(tag_to_label='{"\\U0001F41B": "bug"}')
        )
        # JSON string with the actual emoji character (not the escape)
        t2 = ContentTransformer(
            _doc(content="\U0001F41B oops"),
            _profile(tag_to_label='{"' + "\U0001F41B" + '": "bug"}'),
        )
        ctx = t2.transform()
        assert "[bug]" in ctx.transformed_content

    def test_tag_to_label_bad_json_is_noop(self):
        doc = _doc(content="\U0001F41B hi")
        t = ContentTransformer(doc, _profile(tag_to_label="bad json"))
        ctx = t.transform()
        assert "\U0001F41B" in ctx.transformed_content

    def test_no_tag_to_label_is_noop(self):
        doc = _doc(content="no emojis here")
        t = ContentTransformer(doc, _profile())
        ctx = t.transform()
        assert ctx.transformed_content == "no emojis here"


# ---------------------------------------------------------------------------
# _add_header / _add_footer
# ---------------------------------------------------------------------------

class TestHeaderFooter:
    def test_header_prepended(self):
        doc = _doc(content="Body text")
        t = ContentTransformer(doc, _profile(header_template="# HEADER"))
        ctx = t.transform()
        assert ctx.transformed_content.startswith("# HEADER")
        assert "Body text" in ctx.transformed_content

    def test_footer_appended(self):
        doc = _doc(content="Body text")
        t = ContentTransformer(doc, _profile(footer_template="-- footer"))
        ctx = t.transform()
        assert ctx.transformed_content.endswith("-- footer")
        assert "Body text" in ctx.transformed_content

    def test_header_template_expands_variables(self):
        doc = _doc(id=99, title="My Title", project="cool")
        t = ContentTransformer(
            doc, _profile(header_template="# {{title}} ({{project}}, #{{id}})")
        )
        ctx = t.transform()
        assert "# My Title (cool, #99)" in ctx.transformed_content

    def test_footer_template_expands_date(self):
        doc = _doc()
        t = ContentTransformer(doc, _profile(footer_template="Date: {{date}}"))
        ctx = t.transform()
        today = datetime.now().strftime("%Y-%m-%d")
        assert f"Date: {today}" in ctx.transformed_content

    def test_no_header_is_noop(self):
        doc = _doc(content="hello")
        t = ContentTransformer(doc, _profile())
        ctx = t.transform()
        assert ctx.transformed_content == "hello"


# ---------------------------------------------------------------------------
# _add_frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_frontmatter_adds_yaml_delimiters(self):
        doc = _doc(title="Post")
        t = ContentTransformer(
            doc,
            _profile(add_frontmatter=True, frontmatter_fields=["title", "date"]),
        )
        ctx = t.transform()
        assert ctx.transformed_content.startswith("---\n")
        assert "\n---\n" in ctx.transformed_content

    def test_frontmatter_includes_title(self):
        doc = _doc(title="My Post")
        t = ContentTransformer(
            doc, _profile(add_frontmatter=True, frontmatter_fields=["title"])
        )
        ctx = t.transform()
        assert "title: My Post" in ctx.transformed_content

    def test_frontmatter_includes_date(self):
        doc = _doc()
        t = ContentTransformer(
            doc, _profile(add_frontmatter=True, frontmatter_fields=["date"])
        )
        ctx = t.transform()
        today = datetime.now().strftime("%Y-%m-%d")
        assert f"date: {today}" in ctx.transformed_content

    def test_frontmatter_includes_author(self):
        doc = _doc()
        t = ContentTransformer(
            doc, _profile(add_frontmatter=True, frontmatter_fields=["author"])
        )
        ctx = t.transform()
        assert "author: Generated by EMDX" in ctx.transformed_content

    def test_frontmatter_includes_project(self):
        doc = _doc(project="myproj")
        t = ContentTransformer(
            doc, _profile(add_frontmatter=True, frontmatter_fields=["project"])
        )
        ctx = t.transform()
        assert "project: myproj" in ctx.transformed_content

    def test_frontmatter_includes_id(self):
        doc = _doc(id=42)
        t = ContentTransformer(
            doc, _profile(add_frontmatter=True, frontmatter_fields=["id"])
        )
        ctx = t.transform()
        assert "id: 42" in ctx.transformed_content

    def test_frontmatter_tags_uses_label_map(self):
        doc = _doc(content="\U0001F680 rocket content")
        t = ContentTransformer(
            doc,
            _profile(
                add_frontmatter=True,
                frontmatter_fields=["tags"],
                tag_to_label={"\U0001F680": "launch"},
            ),
        )
        ctx = t.transform()
        assert "launch" in ctx.transformed_content

    def test_frontmatter_default_fields_when_none(self):
        doc = _doc(title="Def")
        t = ContentTransformer(doc, _profile(add_frontmatter=True))
        ctx = t.transform()
        # Should default to ["title", "date"]
        assert "title: Def" in ctx.transformed_content
        assert "date:" in ctx.transformed_content

    def test_frontmatter_fields_json_string(self):
        doc = _doc(title="JSon")
        t = ContentTransformer(
            doc,
            _profile(
                add_frontmatter=True, frontmatter_fields='["title", "author"]'
            ),
        )
        ctx = t.transform()
        assert "title: JSon" in ctx.transformed_content
        assert "author:" in ctx.transformed_content

    def test_frontmatter_fields_bad_json_uses_defaults(self):
        doc = _doc(title="Bad")
        t = ContentTransformer(
            doc, _profile(add_frontmatter=True, frontmatter_fields="not json")
        )
        ctx = t.transform()
        assert "title: Bad" in ctx.transformed_content

    def test_no_frontmatter_flag_is_noop(self):
        doc = _doc(content="plain")
        t = ContentTransformer(doc, _profile())
        ctx = t.transform()
        assert not ctx.transformed_content.startswith("---")

    def test_frontmatter_escapes_colons_in_title(self):
        doc = _doc(title="Part: One")
        t = ContentTransformer(
            doc, _profile(add_frontmatter=True, frontmatter_fields=["title"])
        )
        ctx = t.transform()
        assert '"Part: One"' in ctx.transformed_content


# ---------------------------------------------------------------------------
# _expand_template
# ---------------------------------------------------------------------------

class TestExpandTemplate:
    def test_expand_all_variables(self):
        doc = _doc(id=5, title="T", project="P")
        t = ContentTransformer(doc, _profile())
        ctx = TransformContext(
            document=doc,
            profile=_profile(),
            original_content="",
            transformed_content="",
            metadata={"tags": ["\U0001F680"]},
        )
        result = t._expand_template(
            "{{title}} {{project}} {{id}} {{date}} {{datetime}} {{tags}}", ctx
        )
        assert "T" in result
        assert "P" in result
        assert "5" in result
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in result
        assert "\U0001F680" in result


# ---------------------------------------------------------------------------
# transform_document convenience function
# ---------------------------------------------------------------------------

class TestTransformDocument:
    def test_convenience_function(self):
        doc = _doc(content="hi")
        ctx = transform_document(doc, _profile())
        assert isinstance(ctx, TransformContext)
        assert ctx.transformed_content == "hi"

    def test_convenience_function_applies_transforms(self):
        doc = _doc(content="\U0001F6A7 WIP")
        ctx = transform_document(doc, _profile(strip_tags=["\U0001F6A7"]))
        assert "\U0001F6A7" not in ctx.transformed_content


# ---------------------------------------------------------------------------
# Full pipeline integration
# ---------------------------------------------------------------------------

class TestFullPipeline:
    def test_pipeline_ordering(self):
        """Verify header -> body -> footer with frontmatter on top."""
        doc = _doc(id=1, title="Title", content="Body", project="P")
        profile = _profile(
            header_template="HEADER",
            footer_template="FOOTER",
            add_frontmatter=True,
            frontmatter_fields=["title"],
        )
        ctx = ContentTransformer(doc, profile).transform()
        text = ctx.transformed_content
        # Frontmatter first
        assert text.startswith("---\n")
        # Then header, body, footer in order
        header_idx = text.index("HEADER")
        body_idx = text.index("Body")
        footer_idx = text.index("FOOTER")
        assert header_idx < body_idx < footer_idx

    def test_empty_content_document(self):
        doc = _doc(content="")
        ctx = ContentTransformer(doc, _profile()).transform()
        assert ctx.transformed_content == ""
        assert ctx.original_content == ""

    def test_missing_content_key(self):
        doc = {"id": 1, "title": "No content"}
        ctx = ContentTransformer(doc, _profile()).transform()
        assert ctx.transformed_content == ""
