"""Tests for emoji alias system."""

from emdx.utils.emoji_aliases import (
    EMOJI_ALIASES,
    EMOJI_TAGS,
    REVERSE_ALIASES,
    expand_alias_string,
    expand_aliases,
    get_aliases_for_emoji,
    get_all_aliases,
    get_category_emojis,
    is_emoji_tag,
    is_text_alias,
    normalize_tag_to_emoji,
    suggest_aliases,
)


class TestExpandAliases:
    """Test expand_aliases function."""

    def test_basic_expansion(self):
        assert expand_aliases(["gameplan", "active"]) == ["\U0001f3af", "\U0001f680"]

    def test_already_emoji(self):
        assert expand_aliases(["\U0001f527"]) == ["\U0001f527"]

    def test_mixed_aliases_and_emojis(self):
        result = expand_aliases(["gameplan", "\U0001f527", "urgent"])
        assert result == ["\U0001f3af", "\U0001f527", "\U0001f6a8"]

    def test_case_insensitive(self):
        assert expand_aliases(["GAMEPLAN"]) == ["\U0001f3af"]
        assert expand_aliases(["GamePlan"]) == ["\U0001f3af"]
        assert expand_aliases(["ACTIVE"]) == ["\U0001f680"]

    def test_whitespace_stripping(self):
        assert expand_aliases(["  gameplan  ", " active "]) == ["\U0001f3af", "\U0001f680"]

    def test_unknown_alias_kept(self):
        assert expand_aliases(["unknown-tag"]) == ["unknown-tag"]
        assert expand_aliases(["custom"]) == ["custom"]

    def test_empty_list(self):
        assert expand_aliases([]) == []

    def test_all_document_types(self):
        result = expand_aliases(["gameplan", "analysis", "notes", "docs", "architecture"])
        assert result == [
            "\U0001f3af",
            "\U0001f50d",
            "\U0001f4dd",
            "\U0001f4da",
            "\U0001f3d7\ufe0f",
        ]  # noqa: E501

    def test_all_workflow_statuses(self):
        result = expand_aliases(["active", "done", "blocked"])
        assert result == ["\U0001f680", "\u2705", "\U0001f6a7"]

    def test_all_outcomes(self):
        result = expand_aliases(["success", "failed", "partial"])
        assert result == ["\U0001f389", "\u274c", "\u26a1"]

    def test_synonyms_map_to_same_emoji(self):
        for alias in ["gameplan", "plan", "strategy", "goal"]:
            assert expand_aliases([alias]) == ["\U0001f3af"]
        for alias in ["active", "current", "working", "wip"]:
            assert expand_aliases([alias]) == ["\U0001f680"]


class TestExpandAliasString:
    """Test expand_alias_string function."""

    def test_comma_separated(self):
        result = expand_alias_string("gameplan, active, refactor")
        assert "\U0001f3af" in result
        assert "\U0001f680" in result
        assert "\U0001f527" in result

    def test_no_spaces(self):
        result = expand_alias_string("notes,urgent")
        assert "\U0001f4dd" in result
        assert "\U0001f6a8" in result

    def test_empty_string(self):
        assert expand_alias_string("") == ""

    def test_single_tag(self):
        assert expand_alias_string("gameplan") == "\U0001f3af"

    def test_extra_commas(self):
        result = expand_alias_string("gameplan,,active")
        assert "\U0001f3af" in result
        assert "\U0001f680" in result

    def test_whitespace_only(self):
        result = expand_alias_string("   ")
        assert result == ""


class TestGetAliasesForEmoji:
    """Test get_aliases_for_emoji function."""

    def test_known_emoji(self):
        aliases = get_aliases_for_emoji("\U0001f3af")
        assert "gameplan" in aliases
        assert "plan" in aliases
        assert "strategy" in aliases
        assert "goal" in aliases

    def test_unknown_emoji(self):
        assert get_aliases_for_emoji("\U0001f4a9") == []

    def test_all_emojis_have_aliases(self):
        for emoji in EMOJI_TAGS:
            aliases = get_aliases_for_emoji(emoji)
            assert len(aliases) > 0, f"Emoji {emoji} has no aliases"


class TestIsEmojiTag:
    """Test is_emoji_tag function."""

    def test_known_emoji(self):
        assert is_emoji_tag("\U0001f3af") is True
        assert is_emoji_tag("\U0001f680") is True
        assert is_emoji_tag("\u2705") is True

    def test_unknown_emoji(self):
        assert is_emoji_tag("\U0001f4a9") is False

    def test_text_is_not_emoji(self):
        assert is_emoji_tag("gameplan") is False
        assert is_emoji_tag("active") is False

    def test_empty_string(self):
        assert is_emoji_tag("") is False


class TestIsTextAlias:
    """Test is_text_alias function."""

    def test_known_alias(self):
        assert is_text_alias("gameplan") is True
        assert is_text_alias("active") is True
        assert is_text_alias("done") is True

    def test_case_insensitive(self):
        assert is_text_alias("GAMEPLAN") is True
        assert is_text_alias("Active") is True

    def test_unknown_alias(self):
        assert is_text_alias("unknown") is False
        assert is_text_alias("foobar") is False

    def test_emoji_is_not_alias(self):
        assert is_text_alias("\U0001f3af") is False

    def test_empty_string(self):
        assert is_text_alias("") is False


class TestNormalizeTagToEmoji:
    """Test normalize_tag_to_emoji function."""

    def test_text_to_emoji(self):
        assert normalize_tag_to_emoji("gameplan") == "\U0001f3af"
        assert normalize_tag_to_emoji("active") == "\U0001f680"

    def test_already_emoji(self):
        assert normalize_tag_to_emoji("\U0001f3af") == "\U0001f3af"

    def test_unknown_returns_original(self):
        assert normalize_tag_to_emoji("unknown-tag") == "unknown-tag"

    def test_case_insensitive(self):
        assert normalize_tag_to_emoji("GAMEPLAN") == "\U0001f3af"

    def test_whitespace_stripped(self):
        assert normalize_tag_to_emoji("  gameplan  ") == "\U0001f3af"


class TestGetAllAliases:
    """Test get_all_aliases function."""

    def test_returns_copy(self):
        result = get_all_aliases()
        assert result == EMOJI_ALIASES
        # Should be a copy, not the same object
        result["test_key"] = "test_value"
        assert "test_key" not in EMOJI_ALIASES

    def test_all_values_are_strings(self):
        for key, value in get_all_aliases().items():
            assert isinstance(key, str)
            assert isinstance(value, str)


class TestGetCategoryEmojis:
    """Test get_category_emojis function."""

    def test_all_categories_present(self):
        cats = get_category_emojis()
        expected = [
            "Document Types",
            "Workflow Status",
            "Outcomes",
            "Technical Work",
            "Priority",
            "Project Management",
        ]
        for cat in expected:
            assert cat in cats

    def test_category_values_are_lists(self):
        for _cat, emojis in get_category_emojis().items():
            assert isinstance(emojis, list)
            assert len(emojis) > 0


class TestSuggestAliases:
    """Test suggest_aliases function."""

    def test_prefix_match(self):
        result = suggest_aliases("game")
        assert "gameplan" in result

    def test_multiple_matches(self):
        result = suggest_aliases("a")
        assert len(result) > 1
        # Should include aliases starting with 'a'
        for alias in result:
            assert alias.startswith("a")

    def test_empty_input(self):
        assert suggest_aliases("") == []

    def test_whitespace_input(self):
        assert suggest_aliases("   ") == []

    def test_no_matches(self):
        assert suggest_aliases("zzzzzzz") == []

    def test_case_insensitive(self):
        result = suggest_aliases("GAME")
        assert "gameplan" in result

    def test_max_10_results(self):
        # Even with a broad prefix, should limit to 10
        result = suggest_aliases("a")
        assert len(result) <= 10

    def test_sorted_by_length_then_alpha(self):
        result = suggest_aliases("a")
        # Verify sort: shorter first, then alphabetical
        for i in range(len(result) - 1):
            if len(result[i]) == len(result[i + 1]):
                assert result[i] <= result[i + 1]
            else:
                assert len(result[i]) <= len(result[i + 1])


class TestReverseAliases:
    """Test the REVERSE_ALIASES mapping."""

    def test_consistency(self):
        """Every alias in EMOJI_ALIASES should appear in REVERSE_ALIASES."""
        for alias, emoji in EMOJI_ALIASES.items():
            assert emoji in REVERSE_ALIASES
            assert alias in REVERSE_ALIASES[emoji]

    def test_every_emoji_tag_has_reverse(self):
        for emoji in EMOJI_TAGS:
            assert emoji in REVERSE_ALIASES
