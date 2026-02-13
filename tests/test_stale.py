"""Unit tests for Knowledge Decay feature (stale.py and touch.py).

Tests the scoring functions and thresholds used to identify stale documents
that need review.
"""

from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from emdx.commands.stale import (
    calculate_importance,
    calculate_staleness,
    get_urgency_tier,
    get_tag_weight,
    TAG_WEIGHTS,
    TAG_WEIGHT_ALIASES,
    CRITICAL_IMPORTANCE_THRESHOLD,
    CRITICAL_STALENESS_DAYS,
    WARNING_IMPORTANCE_THRESHOLD,
    WARNING_STALENESS_DAYS,
    INFO_IMPORTANCE_THRESHOLD,
    INFO_STALENESS_DAYS,
)
from emdx.commands.touch import touch_document


class TestGetTagWeight:
    """Test the get_tag_weight helper function."""

    def test_emoji_tag_weight(self):
        """Should return correct weight for emoji tags."""
        assert get_tag_weight("🔐") == 3.0  # security
        assert get_tag_weight("🎯") == 2.0  # gameplan
        assert get_tag_weight("🚀") == 2.0  # active
        assert get_tag_weight("📚") == 2.0  # reference

    def test_text_alias_weight(self):
        """Should return correct weight for text aliases."""
        assert get_tag_weight("security") == 3.0
        assert get_tag_weight("gameplan") == 2.0
        assert get_tag_weight("active") == 2.0
        assert get_tag_weight("reference") == 2.0

    def test_text_alias_case_insensitive(self):
        """Should match text aliases case-insensitively."""
        assert get_tag_weight("Security") == 3.0
        assert get_tag_weight("GAMEPLAN") == 2.0
        assert get_tag_weight("Active") == 2.0

    def test_unknown_tag_default_weight(self):
        """Should return 1.0 for unknown tags."""
        assert get_tag_weight("random-tag") == 1.0
        assert get_tag_weight("🎉") == 1.0
        assert get_tag_weight("") == 1.0


class TestCalculateImportance:
    """Test the calculate_importance function."""

    def test_zero_views_no_tags(self):
        """Zero views and no tags should give minimal importance."""
        score = calculate_importance(0, [])
        assert score == 0.0

    def test_views_only(self):
        """Views alone should contribute to importance."""
        # 5 views, no tags: (5 * 1) / 3.5 = 1.43, rounded to 1.4
        score = calculate_importance(5, [])
        assert score == pytest.approx(1.4, rel=0.1)

    def test_tags_only(self):
        """Tags alone should contribute to importance."""
        # No views, security tag: (3.0 * 1.5) / 3.5 = 1.29
        score = calculate_importance(0, ["security"])
        assert score == pytest.approx(1.3, rel=0.1)

    def test_views_plus_tags(self):
        """Views and tags should combine correctly."""
        # 10 views + gameplan tag: (10 + 2.0*1.5) / 3.5 = 13/3.5 = 3.71
        score = calculate_importance(10, ["gameplan"])
        assert score == pytest.approx(3.7, rel=0.1)

    def test_multiple_high_weight_tags(self):
        """Multiple high-weight tags should increase importance."""
        # 5 views + security(3) + gameplan(2): (5 + (3+2)*1.5) / 3.5 = 12.5/3.5 = 3.57
        score = calculate_importance(5, ["security", "gameplan"])
        assert score == pytest.approx(3.6, rel=0.1)

    def test_emoji_tags_work(self):
        """Emoji tags should be recognized for scoring."""
        # security emoji has weight 3.0
        score = calculate_importance(0, ["🔐"])
        assert score > 0

    def test_view_count_capped_at_20(self):
        """View count contribution should be capped at 20."""
        # 100 views should be treated as 20
        score_high = calculate_importance(100, [])
        score_capped = calculate_importance(20, [])
        assert score_high == score_capped

    def test_max_score_normalized_to_10(self):
        """Even with high values, score should not exceed 10."""
        # Many views + many high-weight tags
        score = calculate_importance(100, ["security", "security", "gameplan", "active", "reference"])
        assert score <= 10.0

    def test_importance_with_mixed_tags(self):
        """Mix of high-weight and default-weight tags."""
        # 3 views + security(3) + unknown(1): (3 + (3+1)*1.5) / 3.5 = 9/3.5 = 2.57
        score = calculate_importance(3, ["security", "random"])
        assert score == pytest.approx(2.6, rel=0.1)

    def test_importance_score_rounded(self):
        """Importance score should be rounded to 1 decimal place."""
        score = calculate_importance(7, ["gameplan"])
        # Score should be a clean decimal like 2.9, not 2.857142857...
        assert score == round(score, 1)


class TestCalculateStaleness:
    """Test the calculate_staleness function."""

    def test_none_access_returns_very_stale(self):
        """None accessed_at should return 999 (very stale)."""
        staleness = calculate_staleness(None)
        assert staleness == 999

    def test_accessed_today_is_zero_staleness(self):
        """Document accessed now should have zero staleness."""
        now = datetime.utcnow()
        staleness = calculate_staleness(now)
        assert staleness == 0

    def test_accessed_yesterday(self):
        """Document accessed yesterday should be 1 day stale."""
        yesterday = datetime.utcnow() - timedelta(days=1)
        staleness = calculate_staleness(yesterday)
        assert staleness == 1

    def test_accessed_30_days_ago(self):
        """Document accessed 30 days ago should be 30 days stale."""
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        staleness = calculate_staleness(thirty_days_ago)
        assert staleness == 30

    def test_accessed_90_days_ago(self):
        """Document accessed 90 days ago should be 90 days stale."""
        ninety_days_ago = datetime.utcnow() - timedelta(days=90)
        staleness = calculate_staleness(ninety_days_ago)
        assert staleness == 90

    def test_future_access_returns_zero(self):
        """Future accessed_at should return 0 (not negative)."""
        future = datetime.utcnow() + timedelta(days=5)
        staleness = calculate_staleness(future)
        assert staleness == 0

    def test_timezone_aware_datetime(self):
        """Should handle timezone-aware datetimes."""
        from datetime import timezone
        aware_dt = datetime.now(timezone.utc) - timedelta(days=10)
        staleness = calculate_staleness(aware_dt)
        assert staleness == 10

    def test_timezone_aware_utc_offset(self):
        """Should handle datetimes with non-UTC timezone."""
        from datetime import timezone
        # Create a datetime in UTC+5 timezone
        tz_plus5 = timezone(timedelta(hours=5))
        aware_dt = datetime.now(tz_plus5) - timedelta(days=7)
        staleness = calculate_staleness(aware_dt)
        # Should still be approximately 7 days
        assert 6 <= staleness <= 8

    def test_edge_case_exactly_one_day(self):
        """Test edge case at exactly 24 hours."""
        one_day_ago = datetime.utcnow() - timedelta(hours=24)
        staleness = calculate_staleness(one_day_ago)
        assert staleness == 1

    def test_edge_case_almost_one_day(self):
        """Test just under 24 hours should be 0 days."""
        almost_one_day = datetime.utcnow() - timedelta(hours=23, minutes=59)
        staleness = calculate_staleness(almost_one_day)
        assert staleness == 0


class TestGetUrgencyTier:
    """Test the get_urgency_tier function."""

    def test_critical_threshold(self):
        """Documents above critical thresholds should be CRITICAL."""
        # CRITICAL: importance > 6 AND staleness > 30 days
        tier = get_urgency_tier(importance=7.0, staleness_days=31)
        assert tier == "CRITICAL"

    def test_critical_exact_threshold_not_critical(self):
        """Documents at exact threshold should NOT be CRITICAL (must be greater than)."""
        # importance = 6.0 (not > 6.0) should not be critical
        tier = get_urgency_tier(importance=6.0, staleness_days=31)
        assert tier != "CRITICAL"

        # staleness = 30 (not > 30) should not be critical
        tier = get_urgency_tier(importance=7.0, staleness_days=30)
        assert tier != "CRITICAL"

    def test_warning_threshold(self):
        """Documents above warning thresholds should be WARNING."""
        # WARNING: importance > 4 AND staleness > 14 days
        tier = get_urgency_tier(importance=5.0, staleness_days=15)
        assert tier == "WARNING"

    def test_warning_exact_threshold_not_warning(self):
        """Documents at exact warning threshold should NOT be WARNING."""
        tier = get_urgency_tier(importance=4.0, staleness_days=15)
        assert tier != "WARNING"

        tier = get_urgency_tier(importance=5.0, staleness_days=14)
        assert tier != "WARNING"

    def test_info_threshold(self):
        """Low importance, very stale documents should be INFO."""
        # INFO: importance < 3 AND staleness > 60 days
        tier = get_urgency_tier(importance=2.0, staleness_days=61)
        assert tier == "INFO"

    def test_info_exact_threshold_not_info(self):
        """Documents at exact info threshold should NOT be INFO."""
        tier = get_urgency_tier(importance=3.0, staleness_days=61)
        assert tier != "INFO"

        tier = get_urgency_tier(importance=2.0, staleness_days=60)
        assert tier != "INFO"

    def test_ok_below_all_thresholds(self):
        """Documents below all thresholds should be OK."""
        # Medium importance, not very stale
        tier = get_urgency_tier(importance=4.0, staleness_days=10)
        assert tier == "OK"

    def test_ok_high_importance_low_staleness(self):
        """High importance but low staleness should be OK."""
        tier = get_urgency_tier(importance=8.0, staleness_days=5)
        assert tier == "OK"

    def test_ok_low_importance_low_staleness(self):
        """Low importance and low staleness should be OK."""
        tier = get_urgency_tier(importance=1.0, staleness_days=10)
        assert tier == "OK"

    def test_priority_critical_over_warning(self):
        """CRITICAL should take priority when both thresholds met."""
        # A document that meets both CRITICAL and WARNING thresholds
        # importance=7 > 6 (critical) > 4 (warning)
        # staleness=40 > 30 (critical) > 14 (warning)
        tier = get_urgency_tier(importance=7.0, staleness_days=40)
        assert tier == "CRITICAL"

    def test_warning_medium_importance_moderate_stale(self):
        """Medium importance with moderate staleness should be WARNING."""
        # importance=5 > 4 (warning threshold) but not > 6 (critical)
        # staleness=20 > 14 (warning threshold) but not > 30 (critical)
        tier = get_urgency_tier(importance=5.0, staleness_days=20)
        assert tier == "WARNING"

    def test_constants_used_correctly(self):
        """Verify the threshold constants are what we expect."""
        assert CRITICAL_IMPORTANCE_THRESHOLD == 6.0
        assert CRITICAL_STALENESS_DAYS == 30
        assert WARNING_IMPORTANCE_THRESHOLD == 4.0
        assert WARNING_STALENESS_DAYS == 14
        assert INFO_IMPORTANCE_THRESHOLD == 3.0
        assert INFO_STALENESS_DAYS == 60


class TestTouchDocument:
    """Test the touch_document function."""

    def test_touch_existing_document(self, temp_db):
        """Touching an existing document should update accessed_at."""
        # Create a document with old accessed_at
        conn = temp_db.get_connection()
        old_time = datetime.utcnow() - timedelta(days=30)
        conn.execute(
            """
            INSERT INTO documents (id, title, content, project, accessed_at, access_count)
            VALUES (1, 'Test Doc', 'Content', 'test', ?, 5)
            """,
            (old_time.isoformat(),),
        )
        conn.commit()

        # Mock the db module to use our test database
        with patch("emdx.commands.touch.db") as mock_db:
            mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=conn)
            mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

            result = touch_document(1)

        assert result == "Test Doc"

        # Verify accessed_at was updated
        cursor = conn.execute("SELECT accessed_at FROM documents WHERE id = 1")
        row = cursor.fetchone()
        new_accessed = datetime.fromisoformat(row["accessed_at"])
        assert new_accessed > old_time

    def test_touch_nonexistent_document(self, temp_db):
        """Touching a non-existent document should return None."""
        conn = temp_db.get_connection()

        with patch("emdx.commands.touch.db") as mock_db:
            mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=conn)
            mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

            result = touch_document(9999)

        assert result is None

    def test_touch_deleted_document(self, temp_db):
        """Touching a deleted document should return None."""
        conn = temp_db.get_connection()
        conn.execute(
            """
            INSERT INTO documents (id, title, content, project, is_deleted)
            VALUES (1, 'Deleted Doc', 'Content', 'test', TRUE)
            """
        )
        conn.commit()

        with patch("emdx.commands.touch.db") as mock_db:
            mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=conn)
            mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

            result = touch_document(1)

        assert result is None

    def test_touch_does_not_increment_access_count(self, temp_db):
        """Touching should NOT increment access_count."""
        conn = temp_db.get_connection()
        initial_count = 5
        conn.execute(
            """
            INSERT INTO documents (id, title, content, project, access_count)
            VALUES (1, 'Test Doc', 'Content', 'test', ?)
            """,
            (initial_count,),
        )
        conn.commit()

        with patch("emdx.commands.touch.db") as mock_db:
            mock_db.get_connection.return_value.__enter__ = MagicMock(return_value=conn)
            mock_db.get_connection.return_value.__exit__ = MagicMock(return_value=False)

            touch_document(1)

        cursor = conn.execute("SELECT access_count FROM documents WHERE id = 1")
        row = cursor.fetchone()
        assert row["access_count"] == initial_count


class TestIntegration:
    """Integration tests for the Knowledge Decay scoring system."""

    def test_high_importance_document_flow(self):
        """A security gameplan document should score high importance."""
        # Security + gameplan document with 15 views
        importance = calculate_importance(15, ["security", "gameplan"])
        # Should be fairly high importance
        assert importance > 5.0

        # If stale for 35 days, should be CRITICAL
        tier = get_urgency_tier(importance, 35)
        assert tier == "CRITICAL"

    def test_archive_candidate_flow(self):
        """Low importance, very stale documents should be INFO (archive candidates)."""
        # Random note with 1 view
        importance = calculate_importance(1, ["notes"])
        # Should be low importance
        assert importance < 3.0

        # If stale for 90 days, should be INFO
        tier = get_urgency_tier(importance, 90)
        assert tier == "INFO"

    def test_active_document_flow(self):
        """Active documents with recent access should be OK."""
        importance = calculate_importance(10, ["active", "gameplan"])
        # Medium-high importance
        assert importance > 4.0

        # Recently accessed (5 days ago)
        tier = get_urgency_tier(importance, 5)
        assert tier == "OK"
