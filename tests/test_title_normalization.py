"""Tests for title normalization."""

from emdx.utils.title_normalization import (
    normalize_title,
    title_similarity,
    titles_match,
)


class TestNormalizeTitle:
    """Test normalize_title function."""

    def test_empty_string(self):
        assert normalize_title("") == ""

    def test_plain_title_unchanged(self):
        assert normalize_title("My Document") == "My Document"

    def test_removes_iso_timestamp(self):
        result = normalize_title("Report - 2026-01-11T00:05:45.123456")
        assert "2026" not in result
        assert result.strip() == "Report"

    def test_removes_iso_timestamp_with_timezone(self):
        result = normalize_title("Report - 2026-01-11T00:05:45+00:00")
        assert "2026" not in result

    def test_removes_iso_timestamp_with_z(self):
        result = normalize_title("Report 2026-01-11T00:05:45Z")
        assert "2026" not in result

    def test_removes_date_in_parentheses(self):
        result = normalize_title("Meeting Notes (2025-01-10)")
        assert result == "Meeting Notes"

    def test_removes_date_after_dash(self):
        result = normalize_title("Weekly Review - 2025-03-15")
        assert result == "Weekly Review"

    def test_removes_standalone_date(self):
        result = normalize_title("Report 2025-01-10 Summary")
        assert "2025-01-10" not in result

    def test_removes_agent_number(self):
        result = normalize_title("Task Output (Agent 1)")
        assert result == "Task Output"
        result = normalize_title("Task Output (Agent 5)")
        assert result == "Task Output"

    def test_removes_agent_number_case_insensitive(self):
        result = normalize_title("Task (agent 3)")
        assert result == "Task"

    def test_removes_task_number(self):
        result = normalize_title("Fix Bug #123")
        assert result == "Fix Bug"

    def test_removes_issue_number(self):
        result = normalize_title("Issue #456 Fix")
        assert result == "Fix"

    def test_removes_task_prefix_number(self):
        result = normalize_title("Task #45 Complete")
        assert result == "Complete"

    def test_removes_version_suffix(self):
        result = normalize_title("Design Doc v2")
        assert result == "Design Doc"

    def test_removes_version_in_parens(self):
        result = normalize_title("Design Doc (v3)")
        assert result == "Design Doc"

    def test_removes_version_case_insensitive(self):
        result = normalize_title("Spec V1")
        assert result == "Spec"

    def test_removes_error_suffix(self):
        result = normalize_title("Synthesis Report (error)")
        assert result == "Synthesis Report"

    def test_removes_error_case_insensitive(self):
        result = normalize_title("Report (Error)")
        assert result == "Report"

    def test_normalizes_whitespace(self):
        result = normalize_title("Too   many    spaces")
        assert result == "Too many spaces"

    def test_strips_trailing_whitespace(self):
        result = normalize_title("  Hello World  ")
        assert result == "Hello World"

    def test_multiple_removals(self):
        title = "Project Plan (Agent 1) - 2025-06-01 v2 #42"
        result = normalize_title(title)
        assert "Agent" not in result
        assert "2025" not in result
        assert "v2" not in result.lower()
        assert "#42" not in result
        assert "Project Plan" in result

    def test_only_date_returns_empty_or_minimal(self):
        result = normalize_title("(2025-01-01)")
        assert result == ""

    def test_unicode_title(self):
        result = normalize_title("Rapport d'\u00e9valuation")
        assert result == "Rapport d'\u00e9valuation"


class TestTitlesMatch:
    """Test titles_match function."""

    def test_identical_titles(self):
        assert titles_match("Hello", "Hello") is True

    def test_different_titles(self):
        assert titles_match("Hello", "World") is False

    def test_match_after_date_removal(self):
        assert titles_match(
            "Report - 2025-01-10",
            "Report - 2025-02-15",
        ) is True

    def test_match_after_agent_removal(self):
        assert titles_match(
            "Task Output (Agent 1)",
            "Task Output (Agent 5)",
        ) is True

    def test_match_after_version_removal(self):
        assert titles_match(
            "Design Doc v1",
            "Design Doc v2",
        ) is True

    def test_match_after_number_removal(self):
        assert titles_match(
            "Fix Bug #100",
            "Fix Bug #200",
        ) is True

    def test_no_match_different_base(self):
        assert titles_match(
            "Report A - 2025-01-10",
            "Report B - 2025-01-10",
        ) is False

    def test_empty_titles(self):
        assert titles_match("", "") is True

    def test_one_empty(self):
        assert titles_match("Hello", "") is False
        assert titles_match("", "Hello") is False

    def test_match_with_multiple_differences(self):
        assert titles_match(
            "Plan (Agent 1) - 2025-01-01 v1",
            "Plan (Agent 3) - 2025-06-15 v5",
        ) is True


class TestTitleSimilarity:
    """Test title_similarity function."""

    def test_identical_titles(self):
        score = title_similarity("Hello World", "Hello World")
        assert score == 1.0

    def test_completely_different(self):
        score = title_similarity("AAAA", "ZZZZ")
        assert score < 0.5

    def test_similar_titles(self):
        score = title_similarity("Project Plan Alpha", "Project Plan Beta")
        assert score > 0.5

    def test_empty_strings(self):
        assert title_similarity("", "") == 0.0
        assert title_similarity("Hello", "") == 0.0
        assert title_similarity("", "Hello") == 0.0

    def test_normalization_applied(self):
        # Same base title with different dates should be 1.0
        score = title_similarity(
            "Report - 2025-01-10",
            "Report - 2025-02-15",
        )
        assert score == 1.0

    def test_case_insensitive(self):
        score = title_similarity("Hello", "hello")
        assert score == 1.0

    def test_returns_float(self):
        score = title_similarity("A", "B")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
