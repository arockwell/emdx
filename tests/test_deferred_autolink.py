"""Tests for deferred embedding + auto-linking on save (#1038).

`emdx save` must not load or instantiate the embedding service by
default — it queues the doc in pending_auto_links, and the catch-up
happens in `emdx maintain index` / `emdx maintain link --pending`.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from emdx.commands.core import app as core_app
from emdx.commands.maintain import app as maintain_app
from emdx.services.link_service import (
    AutoLinkResult,
    PendingLinkSummary,
    process_pending_links,
)

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point EMDX_CONFIG_FILE at a per-test temp file (defaults apply)."""
    monkeypatch.setenv("EMDX_CONFIG_FILE", str(tmp_path / "config.json"))


def _clear_queue() -> None:
    from emdx.database import db

    with db.get_connection() as conn:
        conn.execute("DELETE FROM pending_auto_links")
        conn.commit()


@pytest.fixture(autouse=True)
def clean_queue(isolate_test_database: Any) -> Generator[None, None, None]:
    """Start and end each test with an empty deferred-link queue."""
    _clear_queue()
    yield
    _clear_queue()


def _insert_doc(doc_id: int, title: str, project: str | None = None, deleted: int = 0) -> None:
    from emdx.database import db

    with db.get_connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO documents (id, title, content, project, is_deleted) "
            "VALUES (?, ?, ?, ?, ?)",
            (doc_id, title, f"content of {title}", project, deleted),
        )
        conn.commit()


def _delete_doc(doc_id: int) -> None:
    from emdx.database import db

    with db.get_connection() as conn:
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()


class TestSaveDefersEmbedding:
    """save never touches the embedding service unless --sync-link is given."""

    def _save(self, *extra_args: str, doc_id: int = 4242) -> Any:
        with (
            patch("emdx.commands.core.display_save_result"),
            patch("emdx.commands.core.apply_tags", return_value=[]),
            patch("emdx.commands.core.create_document", return_value=doc_id),
            patch("emdx.commands.core.detect_project", return_value="proj-defer"),
            patch("emdx.services.link_service.auto_link_document") as mock_link,
            patch("emdx.services.embedding_service.EmbeddingService") as mock_service,
        ):
            result = runner.invoke(core_app, ["save", "deferral test content", *extra_args])
        return result, mock_link, mock_service

    def test_default_save_never_instantiates_embedding_service(self) -> None:
        from emdx.database import pending_links

        result, mock_link, mock_service = self._save()
        assert result.exit_code == 0, result.output
        mock_service.assert_not_called()
        mock_link.assert_not_called()
        assert pending_links.get_pending() == [{"document_id": 4242, "project_scope": "proj-defer"}]
        assert "deferred" in result.output

    def test_cross_project_queues_null_scope(self) -> None:
        from emdx.database import pending_links

        result, _, _ = self._save("--cross-project")
        assert result.exit_code == 0, result.output
        assert pending_links.get_pending() == [{"document_id": 4242, "project_scope": None}]

    def test_no_auto_link_skips_queue(self) -> None:
        from emdx.database import pending_links

        result, mock_link, mock_service = self._save("--no-auto-link")
        assert result.exit_code == 0, result.output
        mock_link.assert_not_called()
        mock_service.assert_not_called()
        assert pending_links.count() == 0

    def test_sync_link_runs_old_synchronous_path(self) -> None:
        from emdx.database import pending_links

        result, mock_link, _ = self._save("--sync-link")
        assert result.exit_code == 0, result.output
        mock_link.assert_called_once_with(4242, project="proj-defer")
        assert pending_links.count() == 0

    def test_json_output_reports_deferred_mode(self) -> None:
        result, _, _ = self._save("--json")
        assert result.exit_code == 0, result.output
        # json.loads on full stdout proves the deferral notice didn't leak
        data = json.loads(result.stdout)
        assert data["id"] == 4242
        assert data["auto_link"] == "deferred"

    def test_json_output_reports_off_mode(self) -> None:
        result, _, _ = self._save("--no-auto-link", "--json")
        data = json.loads(result.stdout)
        assert data["auto_link"] == "off"

    def test_json_output_reports_sync_mode(self) -> None:
        result, _, _ = self._save("--sync-link", "--json")
        data = json.loads(result.stdout)
        assert data["auto_link"] == "sync"


class TestProcessPendingLinks:
    """The catch-up pass embeds + links queued docs and drains the queue."""

    def _mock_service(self, indexed_documents: int = 10) -> MagicMock:
        service = MagicMock()
        service.stats.return_value = MagicMock(indexed_documents=indexed_documents)
        return service

    def test_processes_queue_and_links(self) -> None:
        from emdx.database import pending_links

        _insert_doc(9101, "Deferred doc one", project="proj-a")
        _insert_doc(9102, "Deferred doc two", project="proj-b")
        pending_links.enqueue(9101, "proj-a")
        pending_links.enqueue(9102, None)

        with (
            patch(
                "emdx.services.embedding_service.EmbeddingService",
                return_value=self._mock_service(),
            ),
            patch("emdx.services.link_service.auto_link_document") as mock_link,
        ):
            mock_link.side_effect = [
                AutoLinkResult(doc_id=9101, links_created=2, linked_doc_ids=[1, 2], scores=[]),
                AutoLinkResult(doc_id=9102, links_created=1, linked_doc_ids=[3], scores=[]),
            ]
            summary = process_pending_links()

        assert summary.docs_processed == 2
        assert summary.links_created == 3
        assert summary.docs_skipped == 0
        assert summary.docs_failed == 0
        assert pending_links.count() == 0
        # Project scope recorded at save time is honored
        assert mock_link.call_args_list[0].kwargs["project"] == "proj-a"
        assert mock_link.call_args_list[1].kwargs["project"] is None

        _delete_doc(9101)
        _delete_doc(9102)

    def test_deleted_docs_are_dequeued_without_linking(self) -> None:
        from emdx.database import pending_links

        _insert_doc(9103, "Deleted deferred doc", deleted=1)
        pending_links.enqueue(9103, None)

        with (
            patch(
                "emdx.services.embedding_service.EmbeddingService",
                return_value=self._mock_service(),
            ),
            patch("emdx.services.link_service.auto_link_document") as mock_link,
        ):
            summary = process_pending_links()

        mock_link.assert_not_called()
        assert summary.docs_skipped == 1
        assert pending_links.count() == 0
        _delete_doc(9103)

    def test_no_index_keeps_queue(self) -> None:
        from emdx.database import pending_links

        _insert_doc(9104, "Doc without index")
        pending_links.enqueue(9104, None)

        with (
            patch(
                "emdx.services.embedding_service.EmbeddingService",
                return_value=self._mock_service(indexed_documents=0),
            ),
            patch("emdx.services.link_service.auto_link_document") as mock_link,
        ):
            summary = process_pending_links()

        mock_link.assert_not_called()
        assert summary.no_index is True
        assert pending_links.count() == 1
        _delete_doc(9104)

    def test_failed_doc_stays_queued(self) -> None:
        from emdx.database import pending_links

        _insert_doc(9105, "Failing deferred doc")
        pending_links.enqueue(9105, None)

        with (
            patch(
                "emdx.services.embedding_service.EmbeddingService",
                return_value=self._mock_service(),
            ),
            patch(
                "emdx.services.link_service.auto_link_document",
                side_effect=RuntimeError("boom"),
            ),
        ):
            summary = process_pending_links()

        assert summary.docs_failed == 1
        assert pending_links.count() == 1
        _delete_doc(9105)


class TestMaintainCatchUp:
    """`maintain index` and `maintain link --pending` drain the queue."""

    def test_maintain_index_drains_pending_queue(self) -> None:
        from emdx.database import pending_links

        _insert_doc(9106, "Doc for maintain index")
        pending_links.enqueue(9106, None)

        service = MagicMock()
        service.stats.return_value = MagicMock(
            indexed_documents=0,
            total_documents=1,
            coverage_percent=0,
            indexed_chunks=1,
            index_size_bytes=0,
            chunk_index_size_bytes=0,
        )
        service.index_all.return_value = 1

        with (
            patch("emdx.services.embedding_service.EmbeddingService", return_value=service),
            patch(
                "emdx.services.link_service.process_pending_links",
                return_value=PendingLinkSummary(1, 2, 0, 0),
            ) as mock_process,
        ):
            result = runner.invoke(maintain_app, ["index"])

        assert result.exit_code == 0, result.output
        mock_process.assert_called_once()
        assert "Auto-linked 1 pending document(s)" in result.output
        _delete_doc(9106)

    def test_maintain_index_up_to_date_still_drains_queue(self) -> None:
        from emdx.database import pending_links

        _insert_doc(9107, "Doc queued but index current")
        pending_links.enqueue(9107, None)

        service = MagicMock()
        service.stats.return_value = MagicMock(
            indexed_documents=1,
            total_documents=1,
            coverage_percent=100,
            indexed_chunks=5,
            index_size_bytes=0,
            chunk_index_size_bytes=0,
        )

        with (
            patch("emdx.services.embedding_service.EmbeddingService", return_value=service),
            patch(
                "emdx.services.link_service.process_pending_links",
                return_value=PendingLinkSummary(1, 0, 0, 0),
            ) as mock_process,
        ):
            result = runner.invoke(maintain_app, ["index"])

        assert result.exit_code == 0, result.output
        service.index_all.assert_not_called()
        mock_process.assert_called_once()
        _delete_doc(9107)

    def test_maintain_link_pending(self) -> None:
        with patch(
            "emdx.services.link_service.process_pending_links",
            return_value=PendingLinkSummary(3, 5, 1, 0),
        ) as mock_process:
            result = runner.invoke(maintain_app, ["link", "--pending"])

        assert result.exit_code == 0, result.output
        mock_process.assert_called_once_with(threshold=0.5, max_links=5)
        assert "Auto-linked 3 pending document(s)" in result.output
        assert "Skipped 1 deleted document(s)" in result.output

    def test_maintain_link_pending_rejects_doc_id(self) -> None:
        result = runner.invoke(maintain_app, ["link", "42", "--pending"])
        assert result.exit_code == 1

    def test_maintain_link_without_target_errors(self) -> None:
        result = runner.invoke(maintain_app, ["link"])
        assert result.exit_code == 1
