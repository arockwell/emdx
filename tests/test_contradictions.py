"""Tests for the contradiction detection service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.services.contradiction_service import (
    ContradictionMatch,
    ContradictionResult,
    ContradictionService,
    _extract_claims,
    _has_negation,
    _is_claim_sentence,
    _split_sentences,
    _word_overlap,
)

runner = CliRunner()


# ── Unit tests for helper functions ──────────────────────────────────


class TestSplitSentences:
    """Tests for sentence splitting."""

    def test_basic_splitting(self) -> None:
        text = "This is a first sentence here. This is a second sentence here."
        result = _split_sentences(text)
        assert len(result) == 2

    def test_filters_short_sentences(self) -> None:
        text = "Short. This is a much longer proper sentence here."
        result = _split_sentences(text)
        assert len(result) == 1
        assert "much longer" in result[0]

    def test_empty_text(self) -> None:
        assert _split_sentences("") == []

    def test_question_and_exclamation(self) -> None:
        text = "Is this a valid question to ask? Yes it absolutely is a valid question!"
        result = _split_sentences(text)
        assert len(result) == 2


class TestIsClaimSentence:
    """Tests for claim detection."""

    def test_always_is_claim(self) -> None:
        assert _is_claim_sentence("You should always use HTTPS.")

    def test_never_is_claim(self) -> None:
        assert _is_claim_sentence("You should never use plain HTTP.")

    def test_must_is_claim(self) -> None:
        assert _is_claim_sentence("Users must authenticate before access.")

    def test_plain_text_not_claim(self) -> None:
        assert not _is_claim_sentence("The cat sat on the mat today.")


class TestExtractClaims:
    """Tests for claim extraction."""

    def test_extracts_claim_sentences(self) -> None:
        content = (
            "Python is a great language for data science. "
            "The weather was nice today outside. "
            "You must always validate user input carefully."
        )
        claims = _extract_claims(content)
        assert len(claims) >= 1
        # At least the "is" and "must" sentences
        claim_text = " ".join(claims)
        assert "must" in claim_text.lower() or "is" in claim_text.lower()

    def test_empty_content(self) -> None:
        assert _extract_claims("") == []


class TestHasNegation:
    """Tests for negation detection."""

    def test_not_detected(self) -> None:
        assert _has_negation("You should not use eval.")

    def test_never_detected(self) -> None:
        assert _has_negation("Never store passwords in plaintext.")

    def test_dont_detected(self) -> None:
        assert _has_negation("We don't support IE11.")

    def test_no_negation(self) -> None:
        assert not _has_negation("Python is a great programming language.")


class TestWordOverlap:
    """Tests for word overlap computation."""

    def test_identical_sentences(self) -> None:
        s = "Python is great for web development"
        overlap = _word_overlap(s, s)
        assert overlap == 1.0

    def test_no_overlap(self) -> None:
        s1 = "Python rocks everywhere always"
        s2 = "Java excels somewhere sometimes"
        overlap = _word_overlap(s1, s2)
        assert overlap == 0.0

    def test_partial_overlap(self) -> None:
        s1 = "Python is great for machine learning"
        s2 = "Python is great for web development"
        overlap = _word_overlap(s1, s2)
        assert 0.0 < overlap < 1.0

    def test_empty_sentences(self) -> None:
        assert _word_overlap("", "") == 0.0
        assert _word_overlap("hello world", "") == 0.0


# ── Unit tests for ContradictionMatch / ContradictionResult ──────────


class TestContradictionMatch:
    """Tests for ContradictionMatch dataclass."""

    def test_to_dict(self) -> None:
        match = ContradictionMatch(
            excerpt1="Python is always fast.",
            excerpt2="Python is not always fast.",
            confidence=0.75,
            method="heuristic",
        )
        d = match.to_dict()
        assert d["excerpt1"] == "Python is always fast."
        assert d["excerpt2"] == "Python is not always fast."
        assert d["confidence"] == 0.75
        assert d["method"] == "heuristic"


class TestContradictionResult:
    """Tests for ContradictionResult dataclass."""

    def test_to_dict(self) -> None:
        result = ContradictionResult(
            doc1_id=1,
            doc1_title="Doc A",
            doc2_id=2,
            doc2_title="Doc B",
            similarity=0.85,
            matches=[
                ContradictionMatch(
                    excerpt1="A is true.",
                    excerpt2="A is not true.",
                    confidence=0.8,
                    method="heuristic",
                )
            ],
        )
        d = result.to_dict()
        assert d["doc1_id"] == 1
        assert d["doc2_id"] == 2
        assert d["similarity"] == 0.85
        assert len(d["matches"]) == 1
        assert d["matches"][0]["method"] == "heuristic"


# ── Heuristic contradiction detection tests ──────────────────────────


class TestHeuristicDetection:
    """Tests for heuristic contradiction detection."""

    def test_detects_negation_contradiction(self) -> None:
        svc = ContradictionService()
        doc1 = (
            "Python is always the best choice for data science. "
            "It is essential for modern data analysis workflows."
        )
        doc2 = (
            "Python is not always the best choice for data science. "
            "Other languages are sometimes more appropriate."
        )
        matches = svc._check_heuristic(doc1, doc2)
        assert len(matches) > 0
        assert matches[0].method == "heuristic"
        assert matches[0].confidence > 0.0

    def test_no_contradiction_in_similar_claims(self) -> None:
        svc = ContradictionService()
        doc1 = (
            "Python is great for machine learning applications. "
            "It requires proper setup and configuration."
        )
        doc2 = (
            "Python is excellent for machine learning projects. "
            "It requires careful library management."
        )
        matches = svc._check_heuristic(doc1, doc2)
        # No negation mismatch, so no contradictions
        assert len(matches) == 0

    def test_no_contradiction_in_unrelated_docs(self) -> None:
        svc = ContradictionService()
        doc1 = "Python is great for web development always."
        doc2 = "Docker containers are not lightweight enough."
        matches = svc._check_heuristic(doc1, doc2)
        # Low overlap -> no contradiction
        assert len(matches) == 0

    def test_limits_matches_to_five(self) -> None:
        svc = ContradictionService()
        # Create documents with many potential contradictions
        claims = []
        neg_claims = []
        for i in range(10):
            claims.append(f"Feature {i} is always required for production systems.")
            neg_claims.append(f"Feature {i} is never required for production systems.")
        doc1 = " ".join(claims)
        doc2 = " ".join(neg_claims)
        matches = svc._check_heuristic(doc1, doc2)
        assert len(matches) <= 5


# ── Service-level tests with mocking ─────────────────────────────────


class TestContradictionServiceEmbeddings:
    """Tests for the service with mocked embeddings."""

    def test_no_embeddings_returns_empty(self) -> None:
        svc = ContradictionService()
        with patch.object(svc, "_check_embeddings_exist", return_value=False):
            # find_contradictions checks embeddings via the command,
            # but _get_candidate_pairs will be empty
            with patch.object(svc, "_get_candidate_pairs", return_value=[]):
                results = svc.find_contradictions()
                assert results == []

    def test_nli_unavailable_uses_heuristic(self) -> None:
        svc = ContradictionService()
        svc._nli_model_available = False
        assert not svc._check_nli_available()

    def test_find_contradictions_with_mocked_pairs(self) -> None:
        svc = ContradictionService()
        svc._nli_model_available = False

        mock_pairs = [
            (1, 2, 0.85, "Config Guide A", "Config Guide B"),
        ]

        doc1_content = (
            "The server must always run on port 8080 for production. "
            "This is a mandatory requirement for all deployments."
        )
        doc2_content = (
            "The server must never run on port 8080 for production. "
            "This port is not suitable for production systems."
        )

        with (
            patch.object(svc, "_get_candidate_pairs", return_value=mock_pairs),
            patch.object(
                svc,
                "_get_doc_content",
                side_effect=lambda doc_id: doc1_content if doc_id == 1 else doc2_content,
            ),
        ):
            results = svc.find_contradictions(limit=10)

        assert len(results) == 1
        assert results[0].doc1_id == 1
        assert results[0].doc2_id == 2
        assert len(results[0].matches) > 0

    def test_find_contradictions_no_matches(self) -> None:
        svc = ContradictionService()
        svc._nli_model_available = False

        mock_pairs = [
            (1, 2, 0.85, "Python Guide", "Python Tutorial"),
        ]

        doc1_content = (
            "Python is great for data analysis workflows. "
            "It has excellent library support everywhere."
        )
        doc2_content = (
            "Python is wonderful for data analysis tasks. "
            "The ecosystem provides strong library coverage."
        )

        with (
            patch.object(svc, "_get_candidate_pairs", return_value=mock_pairs),
            patch.object(
                svc,
                "_get_doc_content",
                side_effect=lambda doc_id: doc1_content if doc_id == 1 else doc2_content,
            ),
        ):
            results = svc.find_contradictions(limit=10)

        assert len(results) == 0

    def test_empty_doc_content_skipped(self) -> None:
        svc = ContradictionService()
        svc._nli_model_available = False

        mock_pairs = [(1, 2, 0.9, "Doc A", "Doc B")]

        with (
            patch.object(svc, "_get_candidate_pairs", return_value=mock_pairs),
            patch.object(svc, "_get_doc_content", return_value=None),
        ):
            results = svc.find_contradictions()
            assert results == []


# ── CLI command tests ────────────────────────────────────────────────


class TestContradictionsCommand:
    """Tests for the maintain contradictions CLI command."""

    def test_no_embeddings_shows_message(self) -> None:
        from emdx.main import app

        with patch("emdx.services.contradiction_service.ContradictionService") as MockSvc:
            instance = MockSvc.return_value
            instance._check_embeddings_exist.return_value = False

            result = runner.invoke(app, ["maintain", "contradictions"])
            assert result.exit_code == 1
            assert "maintain index" in result.output

    def test_no_embeddings_json_output(self) -> None:
        from emdx.main import app

        with patch("emdx.services.contradiction_service.ContradictionService") as MockSvc:
            instance = MockSvc.return_value
            instance._check_embeddings_exist.return_value = False

            result = runner.invoke(app, ["maintain", "contradictions", "--json"])
            assert result.exit_code == 1
            assert "No embedding index found" in result.output

    def test_no_contradictions_found(self) -> None:
        from emdx.main import app

        with patch("emdx.services.contradiction_service.ContradictionService") as MockSvc:
            instance = MockSvc.return_value
            instance._check_embeddings_exist.return_value = True
            instance._check_nli_available.return_value = False
            instance.find_contradictions.return_value = []

            result = runner.invoke(app, ["maintain", "contradictions"])
            assert result.exit_code == 0
            assert "No contradictions" in result.output

    def test_contradictions_found_displayed(self) -> None:
        import re

        from emdx.main import app

        mock_result = MagicMock()
        mock_result.doc1_id = 1
        mock_result.doc1_title = "Guide A"
        mock_result.doc2_id = 2
        mock_result.doc2_title = "Guide B"
        mock_result.similarity = 0.9
        mock_match = MagicMock()
        mock_match.confidence = 0.8
        mock_match.method = "heuristic"
        mock_match.excerpt1 = "Always use HTTPS."
        mock_match.excerpt2 = "Never use HTTPS."
        mock_result.matches = [mock_match]

        with patch("emdx.services.contradiction_service.ContradictionService") as MockSvc:
            instance = MockSvc.return_value
            instance._check_embeddings_exist.return_value = True
            instance._check_nli_available.return_value = False
            instance.find_contradictions.return_value = [mock_result]

            result = runner.invoke(app, ["maintain", "contradictions"])
            assert result.exit_code == 0
            # Strip ANSI escape codes for assertion
            plain = re.sub(r"\x1b\[[0-9;]*m", "", result.output)
            assert "1 contradicting" in plain

    def test_json_output_format(self) -> None:
        from emdx.main import app

        mock_result = ContradictionResult(
            doc1_id=1,
            doc1_title="Doc A",
            doc2_id=2,
            doc2_title="Doc B",
            similarity=0.85,
            matches=[
                ContradictionMatch(
                    excerpt1="Always use X.",
                    excerpt2="Never use X.",
                    confidence=0.75,
                    method="heuristic",
                )
            ],
        )

        with patch("emdx.services.contradiction_service.ContradictionService") as MockSvc:
            instance = MockSvc.return_value
            instance._check_embeddings_exist.return_value = True
            instance._check_nli_available.return_value = False
            instance.find_contradictions.return_value = [mock_result]

            result = runner.invoke(app, ["maintain", "contradictions", "--json"])
            assert result.exit_code == 0
            # Verify the mock was called correctly
            instance.find_contradictions.assert_called_once()
            # Verify the ContradictionResult.to_dict() produces valid JSON
            d = mock_result.to_dict()
            assert d["doc1_id"] == 1
            assert d["matches"][0]["method"] == "heuristic"
