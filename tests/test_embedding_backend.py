"""Tests for embedding backend selection and adapters.

The backends themselves (fastembed, sentence-transformers) are never
imported here — model loading costs seconds and downloads weights. These
tests cover the resolution logic and the adapter contracts with mocks.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from emdx.services import embedding_service
from emdx.services.embedding_service import (
    BACKEND_ENV_VAR,
    EmbeddingService,
    _backend_name,
    _FastembedModel,
)


@pytest.fixture(autouse=True)
def clean_backend_env(monkeypatch):
    """Isolate each test from the host's backend override and model cache."""
    monkeypatch.delenv(BACKEND_ENV_VAR, raising=False)
    monkeypatch.setattr(embedding_service, "_model", None)


class TestBackendResolution:
    def test_env_override_fastembed(self, monkeypatch):
        monkeypatch.setenv(BACKEND_ENV_VAR, "fastembed")
        assert _backend_name() == "fastembed"

    def test_env_override_sentence_transformers(self, monkeypatch):
        monkeypatch.setenv(BACKEND_ENV_VAR, "sentence-transformers")
        assert _backend_name() == "sentence-transformers"

    def test_unknown_override_falls_through_to_detection(self, monkeypatch):
        monkeypatch.setenv(BACKEND_ENV_VAR, "bogus-backend")
        with patch.object(embedding_service.importlib.util, "find_spec", return_value=None):
            assert _backend_name() == "sentence-transformers"

    def test_prefers_fastembed_when_installed(self):
        with patch.object(
            embedding_service.importlib.util, "find_spec", return_value=MagicMock()
        ) as find_spec:
            assert _backend_name() == "fastembed"
        find_spec.assert_called_once_with("fastembed")

    def test_falls_back_when_fastembed_missing(self):
        with patch.object(embedding_service.importlib.util, "find_spec", return_value=None):
            assert _backend_name() == "sentence-transformers"


class TestModelNamePartitioning:
    """Each backend gets its own model_name key so vector spaces never mix."""

    def test_fastembed_model_name(self, monkeypatch):
        monkeypatch.setenv(BACKEND_ENV_VAR, "fastembed")
        assert EmbeddingService().MODEL_NAME == "all-MiniLM-L6-v2-onnx"

    def test_sentence_transformers_model_name(self, monkeypatch):
        monkeypatch.setenv(BACKEND_ENV_VAR, "sentence-transformers")
        assert EmbeddingService().MODEL_NAME == "all-MiniLM-L6-v2"


class TestFastembedAdapter:
    """The adapter must match sentence-transformers' encode() shape semantics."""

    def _adapter(self):
        inner = MagicMock()
        # fastembed yields one float64 vector per input text
        inner.embed.side_effect = lambda texts: iter(
            np.ones(4, dtype=np.float64) * (i + 1) for i in range(len(texts))
        )
        return _FastembedModel(inner), inner

    def test_single_string_returns_1d_float32(self):
        adapter, inner = self._adapter()
        vec = adapter.encode("hello")
        assert vec.shape == (4,)
        assert vec.dtype == np.float32
        inner.embed.assert_called_once_with(["hello"])

    def test_list_returns_2d_float32(self):
        adapter, inner = self._adapter()
        vecs = adapter.encode(["a", "b", "c"])
        assert vecs.shape == (3, 4)
        assert vecs.dtype == np.float32
        inner.embed.assert_called_once_with(["a", "b", "c"])


class TestGetModel:
    def test_import_error_when_forced_backend_missing(self, monkeypatch):
        monkeypatch.setenv(BACKEND_ENV_VAR, "fastembed")
        with (
            patch.dict("sys.modules", {"fastembed": None}),
            pytest.raises(ImportError, match="fastembed"),
        ):
            embedding_service._get_model()

    def test_model_is_cached(self, monkeypatch):
        monkeypatch.setenv(BACKEND_ENV_VAR, "fastembed")
        fake = MagicMock()
        monkeypatch.setattr(embedding_service, "_model", fake)
        assert embedding_service._get_model() is fake
