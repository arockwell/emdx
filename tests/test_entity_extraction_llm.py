"""Tests for LLM-powered entity extraction.

All tests are mocked — no real API calls or Claude CLI invocations.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from emdx.services.entity_service import (
    _MAX_CONTENT_LENGTH,
    LLM_ENTITY_TYPES,
    _build_extraction_prompt,
    _call_claude_for_entities,
    _parse_llm_response,
    _save_llm_entities,
    _save_relationships,
    estimate_cost,
    extract_and_save_entities_llm,
    resolve_model,
)

# ── Model resolution ─────────────────────────────────────────────────


class TestResolveModel:
    """Test model shorthand resolution."""

    def test_haiku_resolves(self) -> None:
        assert resolve_model("haiku") == "claude-haiku-4-5-20250315"

    def test_sonnet_resolves(self) -> None:
        assert resolve_model("sonnet") == "claude-sonnet-4-20250514"

    def test_opus_resolves(self) -> None:
        assert resolve_model("opus") == "claude-opus-4-20250514"

    def test_case_insensitive(self) -> None:
        assert resolve_model("Haiku") == "claude-haiku-4-5-20250315"
        assert resolve_model("SONNET") == "claude-sonnet-4-20250514"

    def test_full_id_passthrough(self) -> None:
        full_id = "claude-custom-model-2026"
        assert resolve_model(full_id) == full_id


# ── Cost estimation ──────────────────────────────────────────────────


class TestEstimateCost:
    """Test cost estimation."""

    def test_returns_positive_float(self) -> None:
        cost = estimate_cost(1000, "haiku")
        assert cost > 0.0

    def test_haiku_cheaper_than_sonnet(self) -> None:
        haiku_cost = estimate_cost(4000, "haiku")
        sonnet_cost = estimate_cost(4000, "sonnet")
        assert haiku_cost < sonnet_cost

    def test_sonnet_cheaper_than_opus(self) -> None:
        sonnet_cost = estimate_cost(4000, "sonnet")
        opus_cost = estimate_cost(4000, "opus")
        assert sonnet_cost < opus_cost

    def test_unknown_model_uses_haiku_pricing(self) -> None:
        unknown_cost = estimate_cost(4000, "unknown-model")
        haiku_cost = estimate_cost(4000, "haiku")
        assert unknown_cost == haiku_cost


# ── JSON parsing ─────────────────────────────────────────────────────


class TestParseLLMResponse:
    """Test response parsing including markdown fence stripping."""

    def test_parses_plain_json(self) -> None:
        raw = json.dumps(
            {
                "entities": [
                    {
                        "name": "Redis Cache",
                        "entity_type": "technology",
                        "confidence": 0.95,
                    }
                ],
                "relationships": [],
            }
        )
        result = _parse_llm_response(raw)
        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "Redis Cache"
        assert result["entities"][0]["entity_type"] == "technology"

    def test_strips_markdown_json_fence(self) -> None:
        inner = json.dumps(
            {
                "entities": [
                    {
                        "name": "Python Flask",
                        "entity_type": "library",
                        "confidence": 0.9,
                    }
                ],
                "relationships": [],
            }
        )
        raw = f"```json\n{inner}\n```"
        result = _parse_llm_response(raw)
        assert len(result["entities"]) == 1
        assert result["entities"][0]["name"] == "Python Flask"

    def test_strips_plain_markdown_fence(self) -> None:
        inner = json.dumps(
            {
                "entities": [
                    {
                        "name": "Docker Compose",
                        "entity_type": "tool",
                        "confidence": 0.85,
                    }
                ],
                "relationships": [],
            }
        )
        raw = f"```\n{inner}\n```"
        result = _parse_llm_response(raw)
        assert len(result["entities"]) == 1

    def test_filters_stopword_entities(self) -> None:
        raw = json.dumps(
            {
                "entities": [
                    {
                        "name": "todo",
                        "entity_type": "concept",
                        "confidence": 0.8,
                    },
                    {
                        "name": "Kubernetes Cluster",
                        "entity_type": "technology",
                        "confidence": 0.9,
                    },
                ],
                "relationships": [],
            }
        )
        result = _parse_llm_response(raw)
        names = [e["name"] for e in result["entities"]]
        assert "todo" not in [n.lower() for n in names]
        assert "Kubernetes Cluster" in names

    def test_filters_short_entities(self) -> None:
        raw = json.dumps(
            {
                "entities": [
                    {
                        "name": "API",
                        "entity_type": "concept",
                        "confidence": 0.8,
                    },
                    {
                        "name": "REST API Gateway",
                        "entity_type": "technology",
                        "confidence": 0.9,
                    },
                ],
                "relationships": [],
            }
        )
        result = _parse_llm_response(raw)
        names = [e["name"] for e in result["entities"]]
        assert "API" not in names
        assert "REST API Gateway" in names

    def test_clamps_confidence(self) -> None:
        raw = json.dumps(
            {
                "entities": [
                    {
                        "name": "Test Entity Thing",
                        "entity_type": "concept",
                        "confidence": 1.5,
                    },
                    {
                        "name": "Another Entity Thing",
                        "entity_type": "concept",
                        "confidence": -0.3,
                    },
                ],
                "relationships": [],
            }
        )
        result = _parse_llm_response(raw)
        for e in result["entities"]:
            assert 0.0 <= e["confidence"] <= 1.0

    def test_normalizes_unknown_entity_type(self) -> None:
        raw = json.dumps(
            {
                "entities": [
                    {
                        "name": "Redis Server Config",
                        "entity_type": "unknown_type",
                        "confidence": 0.8,
                    }
                ],
                "relationships": [],
            }
        )
        result = _parse_llm_response(raw)
        assert result["entities"][0]["entity_type"] == "concept"

    def test_parses_relationships(self) -> None:
        raw = json.dumps(
            {
                "entities": [
                    {
                        "name": "Service Alpha",
                        "entity_type": "project",
                        "confidence": 0.9,
                    },
                    {
                        "name": "Redis Cache",
                        "entity_type": "technology",
                        "confidence": 0.9,
                    },
                ],
                "relationships": [
                    {
                        "source": "Service Alpha",
                        "target": "Redis Cache",
                        "relationship_type": "uses",
                        "confidence": 0.85,
                    }
                ],
            }
        )
        result = _parse_llm_response(raw)
        assert len(result["relationships"]) == 1
        rel = result["relationships"][0]
        assert rel["source"] == "Service Alpha"
        assert rel["target"] == "Redis Cache"
        assert rel["relationship_type"] == "uses"

    def test_skips_empty_relationship_names(self) -> None:
        raw = json.dumps(
            {
                "entities": [],
                "relationships": [
                    {
                        "source": "",
                        "target": "Redis Cache",
                        "relationship_type": "uses",
                        "confidence": 0.8,
                    },
                    {
                        "source": "Service Alpha",
                        "target": "",
                        "relationship_type": "uses",
                        "confidence": 0.8,
                    },
                ],
            }
        )
        result = _parse_llm_response(raw)
        assert len(result["relationships"]) == 0

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_response("not json at all")

    def test_handles_missing_fields(self) -> None:
        raw = json.dumps({"entities": [], "relationships": []})
        result = _parse_llm_response(raw)
        assert result["entities"] == []
        assert result["relationships"] == []


# ── LLM entity types ─────────────────────────────────────────────────


class TestLLMEntityTypes:
    """Test supported entity types."""

    def test_all_expected_types_present(self) -> None:
        expected = {
            "person",
            "organization",
            "technology",
            "concept",
            "location",
            "event",
            "project",
            "tool",
            "api",
            "library",
        }
        assert expected == LLM_ENTITY_TYPES


# ── Prompt building ──────────────────────────────────────────────────


class TestBuildExtractionPrompt:
    """Test prompt construction."""

    def test_includes_title(self) -> None:
        prompt = _build_extraction_prompt("content here", "My Doc")
        assert "My Doc" in prompt

    def test_includes_content(self) -> None:
        prompt = _build_extraction_prompt("content here", "Title")
        assert "content here" in prompt

    def test_truncates_long_content(self) -> None:
        long_content = "x" * (_MAX_CONTENT_LENGTH + 5000)
        prompt = _build_extraction_prompt(long_content, "Title")
        # The prompt should not contain the full content
        assert len(prompt) < len(long_content) + 1000

    def test_mentions_entity_types(self) -> None:
        prompt = _build_extraction_prompt("content", "Title")
        assert "person" in prompt
        assert "technology" in prompt
        assert "organization" in prompt


# ── Claude CLI invocation ────────────────────────────────────────────


class TestCallClaudeForEntities:
    """Test Claude CLI invocation (all mocked)."""

    @patch("emdx.services.entity_service.subprocess.run")
    def test_successful_call(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "entities": [
                        {
                            "name": "Test Entity Service",
                            "entity_type": "project",
                            "confidence": 0.9,
                        }
                    ],
                    "relationships": [],
                }
            ),
            stderr="",
        )
        result = _call_claude_for_entities("some content", "Test Doc")
        assert len(result["entities"]) == 1
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "claude" in call_args[0][0][0]
        assert "--print" in call_args[0][0]

    @patch("emdx.services.entity_service.subprocess.run")
    def test_cli_not_found_raises(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError()
        with pytest.raises(RuntimeError, match="Claude CLI not found"):
            _call_claude_for_entities("content", "Title")

    @patch("emdx.services.entity_service.subprocess.run")
    def test_cli_failure_raises(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="API error occurred",
        )
        with pytest.raises(RuntimeError, match="Claude CLI failed"):
            _call_claude_for_entities("content", "Title")

    @patch("emdx.services.entity_service.subprocess.run")
    def test_timeout_raises(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=60)
        with pytest.raises(subprocess.TimeoutExpired):
            _call_claude_for_entities("content", "Title")

    @patch("emdx.services.entity_service.subprocess.run")
    def test_uses_resolved_model(self, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps({"entities": [], "relationships": []}),
            stderr="",
        )
        _call_claude_for_entities("content", "Title", model="sonnet")
        call_args = mock_run.call_args[0][0]
        assert "claude-sonnet-4-20250514" in call_args


# ── Database persistence ─────────────────────────────────────────────


class TestSaveLLMEntities:
    """Test entity persistence to database."""

    def test_saves_entities(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 0)",
                (8001, "Test Doc", "content"),
            )
            conn.commit()

        entities = [
            {
                "name": "Redis Cache",
                "entity_type": "technology",
                "confidence": 0.95,
            },
            {
                "name": "Auth Service",
                "entity_type": "project",
                "confidence": 0.9,
            },
        ]
        saved = _save_llm_entities(8001, entities)  # type: ignore[arg-type]
        assert saved == 2

        with db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT entity, entity_type, confidence "
                "FROM document_entities WHERE document_id = ?",
                (8001,),
            )
            rows = cursor.fetchall()

        entity_names = {row[0] for row in rows}
        assert "redis cache" in entity_names
        assert "auth service" in entity_names

    def test_saves_zero_for_empty_list(self, isolate_test_database: Any) -> None:
        saved = _save_llm_entities(9999, [])
        assert saved == 0


class TestSaveRelationships:
    """Test relationship persistence."""

    def test_saves_relationships(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 0)",
                (8002, "Test Doc 2", "content"),
            )
            conn.commit()

        # First save entities so we have IDs to reference
        entities = [
            {
                "name": "Service Alpha",
                "entity_type": "project",
                "confidence": 0.9,
            },
            {
                "name": "Redis Cache",
                "entity_type": "technology",
                "confidence": 0.9,
            },
        ]
        _save_llm_entities(8002, entities)  # type: ignore[arg-type]

        relationships = [
            {
                "source": "Service Alpha",
                "target": "Redis Cache",
                "relationship_type": "uses",
                "confidence": 0.85,
            }
        ]
        saved = _save_relationships(relationships, 8002)  # type: ignore[arg-type]
        assert saved == 1

        with db.get_connection() as conn:
            cursor = conn.execute("SELECT relationship_type, confidence FROM entity_relationships")
            rows = cursor.fetchall()

        assert len(rows) >= 1
        assert rows[0][0] == "uses"

    def test_skips_unknown_entities(self, isolate_test_database: Any) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 0)",
                (8003, "Test Doc 3", "content"),
            )
            conn.commit()

        # Save one entity but reference a non-existent one
        entities = [
            {
                "name": "Known Entity Thing",
                "entity_type": "project",
                "confidence": 0.9,
            },
        ]
        _save_llm_entities(8003, entities)  # type: ignore[arg-type]

        relationships = [
            {
                "source": "Known Entity Thing",
                "target": "Unknown Entity Thing",
                "relationship_type": "uses",
                "confidence": 0.8,
            }
        ]
        saved = _save_relationships(relationships, 8003)  # type: ignore[arg-type]
        assert saved == 0

    def test_saves_zero_for_empty_list(self, isolate_test_database: Any) -> None:
        saved = _save_relationships([], 9999)
        assert saved == 0


# ── High-level extraction ────────────────────────────────────────────


class TestExtractAndSaveEntitiesLLM:
    """Test the full extraction + save pipeline (mocked LLM)."""

    @patch("emdx.services.entity_service._call_claude_for_entities")
    def test_full_pipeline(
        self,
        mock_call: MagicMock,
        isolate_test_database: Any,
    ) -> None:
        from emdx.database import db

        with db.get_connection() as conn:
            conn.execute(
                "INSERT INTO documents (id, title, content, is_deleted) VALUES (?, ?, ?, 0)",
                (8010, "Pipeline Doc", "Some content about services"),
            )
            conn.commit()

        mock_call.return_value = {
            "entities": [
                {
                    "name": "Pipeline Service",
                    "entity_type": "project",
                    "confidence": 0.9,
                },
                {
                    "name": "Data Store",
                    "entity_type": "technology",
                    "confidence": 0.85,
                },
            ],
            "relationships": [
                {
                    "source": "Pipeline Service",
                    "target": "Data Store",
                    "relationship_type": "uses",
                    "confidence": 0.8,
                }
            ],
        }

        stats = extract_and_save_entities_llm(8010, model="haiku")

        assert stats["entities_saved"] == 2
        assert stats["relationships_saved"] == 1
        assert stats["model"] == "claude-haiku-4-5-20250315"
        assert stats["estimated_input_tokens"] > 0
        assert stats["estimated_cost_usd"] > 0.0

    @patch("emdx.services.entity_service._call_claude_for_entities")
    def test_nonexistent_doc(
        self,
        mock_call: MagicMock,
        isolate_test_database: Any,
    ) -> None:
        stats = extract_and_save_entities_llm(99999, model="haiku")
        assert stats["entities_saved"] == 0
        assert stats["relationships_saved"] == 0
        mock_call.assert_not_called()
