"""Caches and duplicate IDs belong to their effective database."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

from emdx.database import DatabaseConnection, connection  # noqa: E402
from emdx.services.similarity import SimilarityService  # noqa: E402


def make_database(path: Path, prefix: str, *, distinct: bool = False) -> DatabaseConnection:
    source = DatabaseConnection(path)
    source.ensure_schema()
    with source.get_connection() as conn:
        for number in range(1, 4):
            content = (
                "Python libraries enable reliable development testing of applications. "
                "Machine learning algorithms process data and generate predictions. "
            )
            if distinct:
                content = (
                    "Sourdough baking requires flour yeast water fermentation kneading crust. "
                    "Bread recipes describe hydration temperature dough and starter feeding.",
                    "Astronomy examines distant galaxies nebulae stars planets telescopes orbits. "
                    "Observatories measure cosmic radiation spectra waves and comets.",
                    "Orchestral music includes violins cellos trumpets clarinets flutes. "
                    "Conductors rehearse symphonies melodies harmonies rhythms and concertos.",
                )[number - 1]
            conn.execute(
                "INSERT INTO documents (id, title, content) VALUES (?, ?, ?)",
                (number, f"{prefix} document {number}", content),
            )
        conn.commit()
    return source


def test_cached_duplicates_follow_database_switches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("emdx.services.similarity.EMDX_CONFIG_DIR", tmp_path / "cache")
    monkeypatch.setattr(SimilarityService, "MAX_DF", 1.0)
    monkeypatch.setattr(SimilarityService, "MIN_DF", 1)
    first = make_database(tmp_path / "a.db", "Alpha")
    second = make_database(tmp_path / "b.db", "Beta", distinct=True)
    monkeypatch.setattr(connection, "db_connection", first)
    service = SimilarityService()
    pairs = service.find_all_duplicate_pairs()
    assert {(pair[0], pair[1]) for pair in pairs} == {(1, 2), (1, 3), (2, 3)}
    assert all("Alpha" in pair[2] and "Alpha" in pair[3] for pair in pairs)
    first_cache = service._cache_path

    monkeypatch.setattr(connection, "db_connection", second)
    pairs = service.find_all_duplicate_pairs()
    # These same numeric IDs are unrelated documents in B. Reusing A's
    # cache would incorrectly nominate all three for duplicate deletion.
    assert pairs == []
    assert service._doc_ids == [1, 2, 3]
    assert all("Beta" in title for title in service._doc_titles)
    assert service._cache_path != first_cache

    monkeypatch.setattr(connection, "db_connection", first)
    monkeypatch.setattr(service, "build_index", lambda *a, **kw: pytest.fail("Must reload A"))
    pairs = service.find_all_duplicate_pairs()
    assert {(pair[0], pair[1]) for pair in pairs} == {(1, 2), (1, 3), (2, 3)}
    assert all("Alpha" in pair[2] and "Alpha" in pair[3] for pair in pairs)
    assert service._cache_path == first_cache


def test_explicit_database_and_untrusted_cache_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("emdx.services.similarity.EMDX_CONFIG_DIR", tmp_path / "cache")
    monkeypatch.setattr(SimilarityService, "MAX_DF", 1.0)
    first = make_database(tmp_path / "a.db", "Alpha")
    second = make_database(tmp_path / "b.db", "Beta")
    monkeypatch.setattr(connection, "db_connection", first)
    service = SimilarityService(second.db_path)
    service.build_index()
    assert all("Beta" in title for title in service._doc_titles)
    metadata_path = service._cache_path / "metadata.json"
    metadata = json.loads(metadata_path.read_text())
    assert metadata["database_identity"] == str(second.db_path.resolve())
    metadata["database_identity"] = str(first.db_path.resolve())
    metadata_path.write_text(json.dumps(metadata))
    assert not SimilarityService(second.db_path)._load_cache()
    del metadata["database_identity"]
    metadata_path.write_text(json.dumps(metadata))
    assert not SimilarityService(second.db_path)._load_cache()

    legacy = service._cache_dir / "metadata.json"
    legacy.write_text(json.dumps(metadata))
    metadata_path.unlink()
    assert not SimilarityService(second.db_path)._load_cache()
    assert legacy.exists()
