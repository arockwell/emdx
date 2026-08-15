"""Tests for core CRUD commands (save, view, edit, delete, restore, etc.)."""

import json
import re
from datetime import datetime
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from emdx.commands.core import InputContent, app, generate_title, get_input_content
from emdx.models.document import Document
from emdx.models.search import SearchHit
from emdx.models.task import Task

runner = CliRunner()


def _out(result) -> str:
    """Strip ANSI escape sequences from CliRunner output for assertions."""
    return re.sub(r"\x1b\[[0-9;]*m", "", result.stdout)


# ---------------------------------------------------------------------------
# get_input_content helper
# ---------------------------------------------------------------------------
class TestGetInputContent:
    """Tests for the get_input_content helper."""

    @patch("sys.stdin")
    def test_reads_file_via_file_path_kwarg(self, mock_stdin, tmp_path):
        """--file kwarg returns file content."""
        mock_stdin.isatty.return_value = True
        f = tmp_path / "note.md"
        f.write_text("hello world")

        result = get_input_content(None, file_path=str(f))
        assert result.content == "hello world"
        assert result.source_type == "file"
        assert result.source_path == f

    @patch("sys.stdin")
    def test_positional_arg_is_always_content(self, mock_stdin):
        """Positional arg is treated as direct content (never a file path)."""
        mock_stdin.isatty.return_value = True
        result = get_input_content("just some text")
        assert result.content == "just some text"
        assert result.source_type == "direct"

    @patch("sys.stdin")
    def test_no_input_exits(self, mock_stdin):
        """No input at all raises typer.Exit."""
        import pytest
        from typer import Exit

        mock_stdin.isatty.return_value = True
        with pytest.raises(Exit):
            get_input_content(None)

    @patch("sys.stdin")
    def test_reads_from_stdin(self, mock_stdin):
        """Stdin content is read when available."""
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = "piped content"

        result = get_input_content(None)
        assert result.content == "piped content"
        assert result.source_type == "stdin"

    @patch("sys.stdin")
    def test_positional_skips_stdin_probe(self, mock_stdin):
        """Positional arg must never touch stdin, even open non-TTY stdin (GH #1034)."""
        mock_stdin.isatty.return_value = False
        mock_stdin.read.side_effect = AssertionError("stdin.read() must not be called")

        result = get_input_content("hello world")
        assert result.content == "hello world"
        assert result.source_type == "direct"
        mock_stdin.read.assert_not_called()

    @patch("sys.stdin")
    def test_bare_dash_reads_stdin(self, mock_stdin):
        """A bare "-" means stdin, not a literal hyphen body."""
        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = "piped content"

        result = get_input_content("-")
        assert result.content == "piped content"
        assert result.source_type == "stdin"

    @patch("sys.stdin")
    def test_bare_dash_with_empty_stdin_exits(self, mock_stdin):
        """A "-" with nothing piped fails loudly rather than saving "-"."""
        import pytest
        from click.exceptions import Exit

        mock_stdin.isatty.return_value = False
        mock_stdin.read.return_value = ""

        with pytest.raises(Exit):
            get_input_content("-")

    @patch("sys.stdin")
    def test_dash_prefixed_content_is_not_stdin(self, mock_stdin):
        """Only a bare "-" routes to stdin; a leading hyphen stays content."""
        mock_stdin.isatty.return_value = True

        result = get_input_content("- a markdown bullet")
        assert result.content == "- a markdown bullet"
        assert result.source_type == "direct"

    @patch("sys.stdin")
    def test_file_skips_stdin_probe(self, mock_stdin, tmp_path):
        """--file must never touch stdin, even open non-TTY stdin (GH #1034)."""
        mock_stdin.isatty.return_value = False
        mock_stdin.read.side_effect = AssertionError("stdin.read() must not be called")
        f = tmp_path / "note.md"
        f.write_text("file content")

        result = get_input_content(None, file_path=str(f))
        assert result.content == "file content"
        mock_stdin.read.assert_not_called()

    @patch("emdx.commands.core._stdin_ready", return_value=False)
    @patch("sys.stdin")
    def test_idle_stdin_errors_instead_of_hanging(self, mock_stdin, mock_ready):
        """Open non-TTY stdin with no data errors out instead of blocking (GH #1034)."""
        import pytest
        from typer import Exit

        mock_stdin.isatty.return_value = False
        mock_stdin.read.side_effect = AssertionError("stdin.read() must not be called")

        with pytest.raises(Exit):
            get_input_content(None)
        mock_stdin.read.assert_not_called()


# ---------------------------------------------------------------------------
# generate_title helper
# ---------------------------------------------------------------------------
class TestGenerateTitle:
    """Tests for title generation."""

    def test_provided_title_wins(self):
        ic = InputContent(content="anything", source_type="file")
        assert generate_title(ic, "My Title") == "My Title"

    def test_file_source_uses_stem(self, tmp_path):
        f = tmp_path / "readme.md"
        ic = InputContent(content="x", source_type="file", source_path=f)
        assert generate_title(ic, None) == "readme"

    def test_stdin_source_generates_timestamp_title(self):
        ic = InputContent(content="piped data", source_type="stdin")
        title = generate_title(ic, None)
        assert "Piped content" in title

    def test_direct_source_uses_first_line(self):
        ic = InputContent(content="First line\nSecond line", source_type="direct")
        title = generate_title(ic, None)
        assert "First line" in title


# ---------------------------------------------------------------------------
# save command
# ---------------------------------------------------------------------------
class TestSaveCommand:
    """Tests for the save command."""

    @patch("emdx.commands.core.display_save_result")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_save_file(self, mock_detect, mock_create, mock_tags, mock_display, tmp_path):
        """Save a real file via CLI."""
        f = tmp_path / "doc.md"
        f.write_text("# Hello\nWorld")

        mock_detect.return_value = "test-proj"
        mock_create.return_value = 42
        mock_tags.return_value = []

        result = runner.invoke(app, ["save", "--file", str(f)])
        assert result.exit_code == 0
        mock_create.assert_called_once()
        args = mock_create.call_args
        assert args[0][0] == "doc"  # title = file stem

    @patch("emdx.commands.core.display_save_result")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_save_with_title_and_project(
        self, mock_detect, mock_create, mock_tags, mock_display, tmp_path
    ):  # noqa: E501
        """Save with explicit --title and --project."""
        f = tmp_path / "note.md"
        f.write_text("content")

        mock_detect.return_value = "override-proj"
        mock_create.return_value = 1
        mock_tags.return_value = []

        result = runner.invoke(
            app,
            [
                "save",
                "--file",
                str(f),
                "--title",
                "Custom Title",
                "--project",
                "my-project",
            ],
        )
        assert result.exit_code == 0
        args = mock_create.call_args
        assert args[0][0] == "Custom Title"

    @patch("emdx.commands.core.display_save_result")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_save_with_tags(self, mock_detect, mock_create, mock_tags, mock_display, tmp_path):
        """Save with --tags."""
        f = tmp_path / "tagged.md"
        f.write_text("tagged content")

        mock_detect.return_value = None
        mock_create.return_value = 5
        mock_tags.return_value = ["python", "testing"]

        result = runner.invoke(
            app,
            [
                "save",
                "--file",
                str(f),
                "--tags",
                "python,testing",
            ],
        )
        assert result.exit_code == 0
        mock_tags.assert_called_once_with(5, "python,testing")

    def test_save_no_input(self):
        """Save with no arguments should fail."""
        result = runner.invoke(app, ["save"])
        assert result.exit_code != 0

    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_save_json_output_file(self, mock_detect, mock_create, mock_tags, tmp_path):
        """--json with --file emits a single JSON object on stdout."""
        f = tmp_path / "doc.md"
        f.write_text("# Hello\nWorld")

        mock_detect.return_value = "test-proj"
        mock_create.return_value = 42
        mock_tags.return_value = ["python"]

        result = runner.invoke(app, ["save", "--file", str(f), "--json", "--tags", "python"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data == {
            "id": 42,
            "title": "doc",
            "project": "test-proj",
            "tags": ["python"],
        }

    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_save_json_output_stdin(self, mock_detect, mock_create, mock_tags):
        """--json with stdin input emits a single JSON object on stdout."""
        mock_detect.return_value = None
        mock_create.return_value = 7
        mock_tags.return_value = []

        result = runner.invoke(
            app,
            ["save", "--json", "--title", "Piped Doc"],
            input="Analysis results here\n",
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data == {"id": 7, "title": "Piped Doc", "project": None, "tags": []}

    @patch("emdx.models.tasks.resolve_task_id")
    @patch("emdx.models.tasks.update_task")
    @patch("emdx.models.tasks.get_task")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_save_json_output_with_task(
        self,
        mock_detect,
        mock_create,
        mock_tags,
        mock_get_task,
        mock_update_task,
        mock_resolve,
        tmp_path,
    ):
        """--json with --task still links the doc to the task and reports task_id."""
        f = tmp_path / "doc.md"
        f.write_text("content")

        mock_detect.return_value = None
        mock_create.return_value = 99
        mock_tags.return_value = []
        mock_resolve.return_value = 5
        mock_get_task.return_value = Task(id=5, title="Research task", status="open")
        mock_update_task.return_value = True

        result = runner.invoke(app, ["save", "--file", str(f), "--task", "5", "--done", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == 99
        assert data["task_id"] == 5
        mock_update_task.assert_called_once_with(5, output_doc_id=99, status="done")

    @patch("emdx.services.link_service.auto_link_document")
    @patch("emdx.services.entity_service.entity_match_wikify")
    @patch("emdx.services.wikify_service.title_match_wikify")
    @patch("emdx.commands.core.apply_tags")
    @patch("emdx.commands.core.create_document")
    @patch("emdx.commands.core.detect_project")
    def test_save_json_suppresses_decorative_output(
        self,
        mock_detect,
        mock_create,
        mock_tags,
        mock_wikify,
        mock_entity,
        mock_autolink,
        tmp_path,
    ):
        """--json suppresses wiki-link/entity-link/auto-link notices.

        Forces all three auto-linking side effects to report created links;
        json.loads succeeding on the full stdout proves nothing else leaked
        onto it.
        """
        from emdx.services.entity_service import EntityWikifyResult
        from emdx.services.link_service import AutoLinkResult
        from emdx.services.wikify_service import WikifyResult

        f = tmp_path / "doc.md"
        f.write_text("content")

        mock_detect.return_value = "proj"
        mock_create.return_value = 55
        mock_tags.return_value = []
        mock_wikify.return_value = WikifyResult(doc_id=55, links_created=2)
        mock_entity.return_value = EntityWikifyResult(
            doc_id=55, entities_extracted=1, links_created=1
        )
        mock_autolink.return_value = AutoLinkResult(
            doc_id=55, links_created=1, linked_doc_ids=[1], scores=[0.9]
        )

        result = runner.invoke(app, ["save", "--file", str(f), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == 55

    def test_save_json_done_without_task_errors_as_json(self):
        """--json --done without --task reports the error as JSON, not rich text."""
        result = runner.invoke(app, ["save", "x", "--done", "--json"])
        assert result.exit_code != 0
        data = json.loads(result.stdout)
        assert data["error"] == "--done requires --task"


# ---------------------------------------------------------------------------
# find command
# ---------------------------------------------------------------------------
class TestFindCommand:
    """Tests for the find command."""

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_documents")
    def test_find_basic(self, mock_search, mock_get_tags):
        """Basic search returns results."""
        mock_search.return_value = [
            SearchHit.from_row(
                {
                    "id": 1,
                    "title": "Found Doc",
                    "project": "proj",
                    "created_at": datetime(2024, 1, 1),
                    "access_count": 3,
                }
            )
        ]
        mock_get_tags.return_value = {1: ["python"]}

        # Use --mode keyword to force FTS path (which is what search_documents mock tests)
        result = runner.invoke(app, ["find", "hello", "--mode", "keyword"])
        assert result.exit_code == 0
        assert "Found Doc" in _out(result)

    def test_find_no_args(self):
        """Find with no search terms and no tags should error."""
        result = runner.invoke(app, ["find"])
        assert result.exit_code != 0

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_documents")
    def test_find_no_results(self, mock_search, mock_get_tags):
        """Search with no results shows appropriate message."""
        mock_search.return_value = []

        # Use --mode keyword to force FTS path (which is what search_documents mock tests)
        result = runner.invoke(app, ["find", "nonexistent", "--mode", "keyword"])
        assert result.exit_code == 0
        assert "No results" in _out(result)

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_documents")
    def test_find_ids_only(self, mock_search, mock_get_tags):
        """--ids-only outputs just IDs."""
        mock_search.return_value = [
            SearchHit.from_row(
                {
                    "id": 42,
                    "title": "Doc",
                    "project": None,
                    "created_at": datetime(2024, 1, 1),
                    "access_count": 0,
                }
            )
        ]
        mock_get_tags.return_value = {}

        # Use --mode keyword to force FTS path (which is what search_documents mock tests)
        result = runner.invoke(app, ["find", "test", "--ids-only", "--mode", "keyword"])
        assert result.exit_code == 0
        assert "42" in _out(result)

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_documents")
    def test_find_json_output(self, mock_search, mock_get_tags):
        """--json outputs JSON array."""
        mock_search.return_value = [
            SearchHit.from_row(
                {
                    "id": 1,
                    "title": "JSON Doc",
                    "project": "p",
                    "created_at": datetime(2024, 1, 1),
                    "updated_at": datetime(2024, 1, 2),
                    "access_count": 0,
                }
            )
        ]
        mock_get_tags.return_value = {1: []}

        # Use --mode keyword to force FTS path (which is what search_documents mock tests)
        result = runner.invoke(app, ["find", "test", "--json", "--mode", "keyword"])
        assert result.exit_code == 0
        assert '"id": 1' in _out(result)

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_by_tags")
    def test_find_by_tags(self, mock_search_tags, mock_get_tags):
        """Find with --tags does tag-based search."""
        mock_search_tags.return_value = [
            {
                "id": 5,
                "title": "Tagged",
                "project": None,
                "created_at": datetime(2024, 6, 1),
                "access_count": 1,
            }
        ]
        mock_get_tags.return_value = {5: ["python"]}

        result = runner.invoke(app, ["find", "--tags", "python"])
        assert result.exit_code == 0
        assert "Tagged" in _out(result)

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_by_tags")
    def test_find_by_tag_singular_alias(self, mock_search_tags, mock_get_tags):
        """GH #1105: --tag is an alias for --tags."""
        mock_search_tags.return_value = [
            {
                "id": 5,
                "title": "Tagged",
                "project": None,
                "created_at": datetime(2024, 6, 1),
                "access_count": 1,
            }
        ]
        mock_get_tags.return_value = {5: ["python"]}

        result = runner.invoke(app, ["find", "--tag", "python"])
        assert result.exit_code == 0
        mock_search_tags.assert_called_once_with(["python"], mode="all", project=None, limit=10)

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_by_tags")
    def test_find_by_tag_search_alias(self, mock_search_tags, mock_get_tags):
        """GH #1105: --tag-search is an alias for --tags."""
        mock_search_tags.return_value = []
        mock_get_tags.return_value = {}

        result = runner.invoke(app, ["find", "--tag-search", "python"])
        assert result.exit_code == 0
        mock_search_tags.assert_called_once_with(["python"], mode="all", project=None, limit=10)

    @patch("emdx.commands.core.get_tags_for_documents")
    @patch("emdx.commands.core.search_documents")
    def test_find_keyword_mode_boosts_manual_link(self, mock_search, mock_get_tags):
        """#1115: --mode keyword (the legacy FTS path) also applies the
        manual-link ranking boost, reordering equally-ranked results.
        """
        from emdx.database import db
        from emdx.database.document_links import create_link

        with db.get_connection() as conn:
            raw_id = conn.execute(
                "INSERT INTO documents (title, content) VALUES (?, ?)",
                ("Raw Legwork", "content"),
            ).lastrowid
            synthesis_id = conn.execute(
                "INSERT INTO documents (title, content) VALUES (?, ?)",
                ("Synthesis Answer", "content"),
            ).lastrowid
            citing_id = conn.execute(
                "INSERT INTO documents (title, content) VALUES (?, ?)",
                ("Citing Doc", "content"),
            ).lastrowid
            conn.commit()

        create_link(citing_id, synthesis_id, similarity_score=1.0, method="manual")

        # search_documents returns them in this (unboosted) order, tied on rank
        mock_search.return_value = [
            SearchHit.from_row(
                {
                    "id": raw_id,
                    "title": "Raw Legwork",
                    "project": None,
                    "created_at": datetime(2024, 1, 1),
                    "access_count": 0,
                    "rank": -5.0,
                }
            ),
            SearchHit.from_row(
                {
                    "id": synthesis_id,
                    "title": "Synthesis Answer",
                    "project": None,
                    "created_at": datetime(2024, 1, 1),
                    "access_count": 0,
                    "rank": -5.0,
                }
            ),
        ]
        mock_get_tags.return_value = {raw_id: [], synthesis_id: []}

        result = runner.invoke(app, ["find", "tied query", "--mode", "keyword", "--json"])
        assert result.exit_code == 0
        payload = json.loads(_out(result))
        ids_in_order = [row["id"] for row in payload]
        assert ids_in_order.index(synthesis_id) < ids_in_order.index(raw_id)

    def test_find_all_with_tags_filters_and_reports_real_tags(self):
        """GH #1126: --all --tags should filter results (not silently list
        everything) and report real tags in JSON, not null.
        """
        from emdx.database import db
        from emdx.models.tags import add_tags_to_document

        with db.get_connection() as conn:
            tagged_id = conn.execute(
                "INSERT INTO documents (title, content) VALUES (?, ?)",
                ("Tagged Doc", "content"),
            ).lastrowid
            untagged_id = conn.execute(
                "INSERT INTO documents (title, content) VALUES (?, ?)",
                ("Untagged Doc", "content"),
            ).lastrowid
            conn.commit()

        add_tags_to_document(tagged_id, ["distinctive-tag"])

        result = runner.invoke(app, ["find", "--all", "--tags", "distinctive-tag", "--json"])
        assert result.exit_code == 0
        payload = json.loads(_out(result))
        ids = [row["id"] for row in payload]

        # Only the tagged doc should be present -- the untagged (but more
        # recent, since it was inserted later) doc must not leak through.
        assert tagged_id in ids
        assert untagged_id not in ids

        tagged_row = next(row for row in payload if row["id"] == tagged_id)
        assert tagged_row["tags"] == ["distinctive-tag"]

    def test_find_all_without_tags_lists_everything(self):
        """--all with no --tags keeps listing all documents (no regression)."""
        from emdx.database import db

        with db.get_connection() as conn:
            doc_id = conn.execute(
                "INSERT INTO documents (title, content) VALUES (?, ?)",
                ("Untagged Only Doc", "content"),
            ).lastrowid
            conn.commit()

        result = runner.invoke(app, ["find", "--all", "--json"])
        assert result.exit_code == 0
        payload = json.loads(_out(result))
        ids = [row["id"] for row in payload]
        assert doc_id in ids

    def _seed_query_plus_tag_scenario(self) -> int:
        """Seed docs reproducing #1118: a keyword+tag combo that must not
        silently return zero results.

        Creates one old, uniquely-keyword-matching document sharing a tag
        with many newer documents that don't match the keyword. Before the
        fix, both `search_by_tags` (ordered newest-first) and the outer
        search were capped at the default --limit (10), so the old matching
        document fell outside both candidate windows and the intersection
        came up empty even though a real match existed.

        Returns the id of the document that should be found.
        """
        from emdx.database.documents import save_document
        from emdx.models.tags import add_tags_to_document

        target_id = save_document(
            title="Old doc with the unique needle",
            content="this document mentions zzzneedle exactly once",
        )
        add_tags_to_document(target_id, ["regressiontag"])

        # Push 15 newer, tag-sharing but keyword-irrelevant documents on top
        # of it so `target_id` is not among the 10 most recently created
        # tagged documents, nor among the top 10 keyword-ranked documents.
        for i in range(15):
            newer_id = save_document(
                title=f"Newer unrelated doc {i}",
                content="unrelated filler content",
            )
            add_tags_to_document(newer_id, ["regressiontag"])

        return target_id

    def _seed_hybrid_search_side_truncation_scenario(self) -> int:
        """Seed docs reproducing #1118 on the *search* side of the hybrid
        path specifically: many documents rank above the real answer on
        keyword relevance alone, but only the answer carries the tag.

        Before the fix, `hybrid_service.search(..., limit=limit)` was called
        with the outer --limit (10) *before* the tag filter ran, so the
        weakly-matching but correctly-tagged document was discarded from the
        candidate pool before the tag intersection even had a chance to see
        it — even though it was the only document exposed to the tag filter.

        Returns the id of the document that should be found.
        """
        from emdx.database.documents import save_document
        from emdx.models.tags import add_tags_to_document

        # 15 documents that repeat the query term heavily, ranking well
        # above the real answer on keyword relevance, but not carrying the
        # tag we're filtering on.
        for i in range(15):
            save_document(
                title=f"Noise doc {i}",
                content="zzzneedle zzzneedle zzzneedle zzzneedle zzzneedle filler",
            )

        target_id = save_document(
            title="The tagged answer",
            content="this document mentions zzzneedle exactly once",
        )
        add_tags_to_document(target_id, ["regressiontag"])

        return target_id

    def test_find_keyword_plus_tags_default_mode(self):
        """#1118: default (hybrid) search combined with --tags must not
        silently drop a real match whose text-relevance rank falls outside
        the top-`limit` window before the tag filter runs.
        """
        target_id = self._seed_hybrid_search_side_truncation_scenario()

        result = runner.invoke(app, ["find", "zzzneedle", "--tags", "regressiontag", "--json"])
        assert result.exit_code == 0
        payload = json.loads(_out(result))
        ids = [row["id"] for row in payload]
        assert target_id in ids

    def test_find_keyword_plus_tags_explicit_keyword_mode(self):
        """#1118: same regression, exercised via the explicit --mode keyword
        (FTS-only) path in `_find_keyword_search`.
        """
        target_id = self._seed_query_plus_tag_scenario()

        result = runner.invoke(
            app,
            ["find", "zzzneedle", "--tags", "regressiontag", "--mode", "keyword", "--json"],
        )
        assert result.exit_code == 0
        payload = json.loads(_out(result))
        ids = [row["id"] for row in payload]
        assert target_id in ids


# ---------------------------------------------------------------------------
# view command
# ---------------------------------------------------------------------------
class TestViewCommand:
    """Tests for the view command."""

    @patch("emdx.commands.core.get_document_tags")
    @patch("emdx.commands.core.get_document")
    def test_view_by_id(self, mock_get_doc, mock_get_tags):
        """View a document by numeric ID."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "My Doc",
                "content": "Hello world",
                "project": "test",
                "created_at": datetime(2024, 1, 1),
                "access_count": 5,
            }
        )
        mock_get_tags.return_value = ["python"]

        result = runner.invoke(app, ["view", "1", "--no-pager"])
        assert result.exit_code == 0
        assert "My Doc" in _out(result)

    @patch("emdx.commands.core.get_document")
    def test_view_not_found(self, mock_get_doc):
        """View nonexistent document shows error."""
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["view", "999"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    @patch("emdx.commands.core.get_document_tags")
    @patch("emdx.commands.core.get_document")
    def test_view_raw(self, mock_get_doc, mock_get_tags):
        """View with --raw shows raw content."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Raw Doc",
                "content": "# Raw markdown",
                "project": None,
                "created_at": datetime(2024, 1, 1),
                "access_count": 0,
            }
        )
        mock_get_tags.return_value = []

        result = runner.invoke(app, ["view", "1", "--raw", "--no-pager"])
        assert result.exit_code == 0
        assert "# Raw markdown" in _out(result)

    @patch("emdx.commands.core.get_document_tags")
    @patch("emdx.commands.core.get_document")
    def test_view_no_header(self, mock_get_doc, mock_get_tags):
        """View with --no-header hides header."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "No Header",
                "content": "Just content",
                "project": None,
                "created_at": datetime(2024, 1, 1),
                "access_count": 0,
            }
        )
        mock_get_tags.return_value = []

        result = runner.invoke(app, ["view", "1", "--no-header", "--no-pager"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Project:" not in out
        assert "Views:" not in out

    @patch("emdx.commands.core.get_document_tags")
    @patch("emdx.commands.core.get_document")
    def test_view_json(self, mock_get_doc, mock_get_tags):
        """View with --json outputs valid JSON."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "JSON Doc",
                "content": "Hello world",
                "project": "test",
                "created_at": datetime(2024, 1, 1),
                "updated_at": datetime(2024, 1, 2),
                "accessed_at": datetime(2024, 1, 3),
                "access_count": 5,
            }
        )
        mock_get_tags.return_value = ["python"]

        result = runner.invoke(app, ["view", "1", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == 1
        assert data["title"] == "JSON Doc"
        assert data["content"] == "Hello world"
        assert data["project"] == "test"
        assert data["tags"] == ["python"]
        assert data["access_count"] == 5

    def test_view_missing_id(self):
        """View with no ID should fail."""
        result = runner.invoke(app, ["view"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# edit command
# ---------------------------------------------------------------------------
class TestEditCommand:
    """Tests for the edit command."""

    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    def test_edit_title_only(self, mock_get_doc, mock_update):
        """Edit with --title updates title without opening editor."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Old Title",
                "content": "content",
                "project": "p",
                "created_at": datetime(2024, 1, 1),
            }
        )
        mock_update.return_value = True

        result = runner.invoke(app, ["edit", "1", "--title", "New Title"])
        assert result.exit_code == 0
        assert "New Title" in _out(result)
        mock_update.assert_called_once_with(1, "New Title", "content")

    @patch("emdx.commands.core.get_document")
    def test_edit_doc_not_found(self, mock_get_doc):
        """Edit nonexistent document shows error."""
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["edit", "999"])
        assert result.exit_code != 0
        assert "not found" in _out(result)

    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    def test_edit_title_failure(self, mock_get_doc, mock_update):
        """Edit that fails to update shows error."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Title",
                "content": "c",
                "project": None,
                "created_at": datetime(2024, 1, 1),
            }
        )
        mock_update.return_value = False

        result = runner.invoke(app, ["edit", "1", "--title", "New"])
        assert result.exit_code != 0
        assert "Error" in _out(result)

    def test_edit_missing_id(self):
        """Edit with no ID should fail."""
        result = runner.invoke(app, ["edit"])
        assert result.exit_code != 0

    @patch("emdx.commands.core.subprocess.run")
    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    def test_edit_content_flag(self, mock_get_doc, mock_update, mock_run):
        """--content replaces the body without launching an editor (GH #1036)."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 3,
                "title": "Doc",
                "content": "old body",
                "project": None,
                "created_at": datetime(2024, 1, 1),
            }
        )
        mock_update.return_value = True

        result = runner.invoke(app, ["edit", "3", "--content", "new body"])
        assert result.exit_code == 0
        mock_update.assert_called_once_with(3, "Doc", "new body")
        mock_run.assert_not_called()

    @patch("emdx.commands.core.subprocess.run")
    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    def test_edit_file_flag(self, mock_get_doc, mock_update, mock_run, tmp_path):
        """--file replaces the body from a file without launching an editor."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 3,
                "title": "Doc",
                "content": "old body",
                "project": None,
                "created_at": datetime(2024, 1, 1),
            }
        )
        mock_update.return_value = True
        f = tmp_path / "body.md"
        f.write_text("# Heading\n\nfrom file")

        result = runner.invoke(app, ["edit", "3", "--file", str(f)])
        assert result.exit_code == 0
        mock_update.assert_called_once_with(3, "Doc", "# Heading\n\nfrom file")
        mock_run.assert_not_called()

    @patch("emdx.commands.core.get_document")
    def test_edit_file_missing_errors(self, mock_get_doc):
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 3,
                "title": "Doc",
                "content": "c",
                "project": None,
                "created_at": datetime(2024, 1, 1),
            }
        )
        result = runner.invoke(app, ["edit", "3", "--file", "/nonexistent/x.md"])
        assert result.exit_code != 0

    @patch("emdx.commands.core.subprocess.run")
    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    def test_edit_file_dash_reads_stdin(self, mock_get_doc, mock_update, mock_run):
        """--file - replaces the body from stdin."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 3,
                "title": "Doc",
                "content": "old",
                "project": None,
                "created_at": datetime(2024, 1, 1),
            }
        )
        mock_update.return_value = True

        result = runner.invoke(app, ["edit", "3", "--file", "-"], input="stdin body\n")
        assert result.exit_code == 0
        mock_update.assert_called_once_with(3, "Doc", "stdin body\n")
        mock_run.assert_not_called()

    @patch("emdx.commands.core.subprocess.run")
    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    def test_edit_piped_stdin(self, mock_get_doc, mock_update, mock_run):
        """Piping content into edit updates the body without an editor."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 3,
                "title": "Doc",
                "content": "old",
                "project": None,
                "created_at": datetime(2024, 1, 1),
            }
        )
        mock_update.return_value = True

        result = runner.invoke(app, ["edit", "3"], input="piped body\n")
        assert result.exit_code == 0
        mock_update.assert_called_once_with(3, "Doc", "piped body\n")
        mock_run.assert_not_called()

    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    def test_edit_content_with_title_updates_both(self, mock_get_doc, mock_update):
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 3,
                "title": "Old Title",
                "content": "old",
                "project": None,
                "created_at": datetime(2024, 1, 1),
            }
        )
        mock_update.return_value = True

        result = runner.invoke(app, ["edit", "3", "--title", "New Title", "--content", "new"])
        assert result.exit_code == 0
        mock_update.assert_called_once_with(3, "New Title", "new")

    @patch("emdx.commands.core.get_document")
    def test_edit_file_and_content_conflict(self, mock_get_doc):
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 3,
                "title": "Doc",
                "content": "c",
                "project": None,
                "created_at": datetime(2024, 1, 1),
            }
        )
        result = runner.invoke(app, ["edit", "3", "--file", "x.md", "--content", "y"])
        assert result.exit_code != 0
        assert "mutually exclusive" in _out(result)

    def _doc_with_headings(self):
        return Document.from_row(
            {
                "id": 7,
                "title": "My Doc",
                "content": "intro\n\n## Section A\n\nbody a\n\n## Section B\n\nbody b",
                "project": None,
                "created_at": datetime(2024, 1, 1),
            }
        )

    @patch("emdx.commands.core.subprocess.run")
    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    def test_edit_unchanged_is_noop(self, mock_get_doc, mock_update, mock_run):
        """Saving the buffer untouched must not change the document (GH #1035)."""
        mock_get_doc.return_value = self._doc_with_headings()
        mock_run.return_value = MagicMock(returncode=0)  # editor saves unchanged

        result = runner.invoke(app, ["edit", "7"])
        assert result.exit_code == 0
        assert "No changes made" in _out(result)
        mock_update.assert_not_called()

    @patch("emdx.commands.core.subprocess.run")
    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    def test_edit_preserves_markdown_headings(self, mock_get_doc, mock_update, mock_run):
        """Lines starting with # in the body survive an edit (GH #1035)."""
        mock_get_doc.return_value = self._doc_with_headings()
        mock_update.return_value = True

        def fake_editor(cmd, *args, **kwargs):
            path = cmd[1]
            with open(path) as f:
                buffer = f.read()
            with open(path, "w") as f:
                f.write(buffer + "\n\n## Section C\n\nsee #42 for details\n")
            return MagicMock(returncode=0)

        mock_run.side_effect = fake_editor

        result = runner.invoke(app, ["edit", "7"])
        assert result.exit_code == 0
        mock_update.assert_called_once()
        _, new_title, new_content = mock_update.call_args[0]
        assert new_title == "My Doc"
        assert "## Section A" in new_content
        assert "## Section B" in new_content
        assert "## Section C" in new_content
        assert "#42 for details" in new_content

    @patch("emdx.commands.core.subprocess.run")
    @patch("emdx.commands.core.update_document")
    @patch("emdx.commands.core.get_document")
    def test_edit_sentinel_deleted_falls_back(self, mock_get_doc, mock_update, mock_run):
        """If the user deletes the whole preamble, body headings still survive."""
        mock_get_doc.return_value = self._doc_with_headings()
        mock_update.return_value = True

        def fake_editor(cmd, *args, **kwargs):
            path = cmd[1]
            with open(path, "w") as f:
                f.write("My Doc\n\nnew intro\n\n## Kept Heading\n\nbody\n")
            return MagicMock(returncode=0)

        mock_run.side_effect = fake_editor

        result = runner.invoke(app, ["edit", "7"])
        assert result.exit_code == 0
        mock_update.assert_called_once()
        _, new_title, new_content = mock_update.call_args[0]
        assert new_title == "My Doc"
        assert "## Kept Heading" in new_content


# ---------------------------------------------------------------------------
# delete command
# ---------------------------------------------------------------------------
class TestDeleteCommand:
    """Tests for the delete command."""

    @patch("emdx.commands.core.delete_document")
    @patch("emdx.commands.core.get_document")
    def test_delete_soft(self, mock_get_doc, mock_delete):
        """Soft delete with --force skips confirmation."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "To Delete",
                "project": "p",
                "created_at": datetime(2024, 1, 1),
                "access_count": 0,
            }
        )
        mock_delete.return_value = True

        result = runner.invoke(app, ["delete", "1", "--force"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Moved" in out or "trash" in out
        mock_delete.assert_called_once_with("1", hard_delete=False)

    @patch("emdx.commands.core.delete_document")
    @patch("emdx.commands.core.get_document")
    def test_delete_hard_force(self, mock_get_doc, mock_delete):
        """Hard delete with --force --hard."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Perm Delete",
                "project": None,
                "created_at": datetime(2024, 1, 1),
                "access_count": 0,
            }
        )
        mock_delete.return_value = True

        result = runner.invoke(app, ["delete", "1", "--force", "--hard"])
        assert result.exit_code == 0
        assert "Permanently deleted" in _out(result)
        mock_delete.assert_called_once_with("1", hard_delete=True)

    @patch("emdx.commands.core.get_document")
    def test_delete_not_found(self, mock_get_doc):
        """Deleting a non-existent document shows error."""
        mock_get_doc.return_value = None

        result = runner.invoke(app, ["delete", "999", "--force"])
        out = _out(result)
        assert result.exit_code != 0
        assert "not found" in out.lower() or "No valid" in out

    @patch("emdx.commands.core.get_document")
    def test_delete_dry_run(self, mock_get_doc):
        """--dry-run shows what would be deleted without deleting."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Dry Run Doc",
                "project": "p",
                "created_at": datetime(2024, 1, 1),
                "access_count": 0,
            }
        )

        result = runner.invoke(app, ["delete", "1", "--dry-run"])
        assert result.exit_code == 0
        assert "dry run" in _out(result).lower()

    @patch("emdx.commands.core.delete_document")
    @patch("emdx.commands.core.get_document")
    def test_delete_multiple(self, mock_get_doc, mock_delete):
        """Delete multiple documents at once."""

        def side_effect(identifier):
            docs = {
                "1": Document.from_row(
                    {
                        "id": 1,
                        "title": "Doc 1",
                        "project": None,
                        "created_at": datetime(2024, 1, 1),
                        "access_count": 0,
                    }
                ),
                "2": Document.from_row(
                    {
                        "id": 2,
                        "title": "Doc 2",
                        "project": None,
                        "created_at": datetime(2024, 1, 2),
                        "access_count": 0,
                    }
                ),
            }
            return docs.get(identifier)

        mock_get_doc.side_effect = side_effect
        mock_delete.return_value = True

        result = runner.invoke(app, ["delete", "1", "2", "--force"])
        assert result.exit_code == 0
        assert mock_delete.call_count == 2

    def test_delete_missing_id(self):
        """Delete with no ID should fail."""
        result = runner.invoke(app, ["delete"])
        assert result.exit_code != 0

    @patch("emdx.commands.core.delete_document")
    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.is_non_interactive", return_value=True)
    def test_delete_auto_confirms_when_non_tty(self, mock_isatty, mock_get_doc, mock_delete):
        """Delete skips confirmation when stdin is not a TTY (agent mode)."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Agent Delete",
                "project": "p",
                "created_at": datetime(2024, 1, 1),
                "access_count": 0,
            }
        )
        mock_delete.return_value = True

        # No --force flag, but should still proceed without prompting
        result = runner.invoke(app, ["delete", "1"])
        out = _out(result)
        assert result.exit_code == 0
        assert "Moved" in out or "trash" in out
        mock_delete.assert_called_once_with("1", hard_delete=False)

    @patch("emdx.commands.core.delete_document")
    @patch("emdx.commands.core.get_document")
    @patch("emdx.commands.core.is_non_interactive", return_value=True)
    def test_delete_hard_auto_confirms_when_non_tty(self, mock_isatty, mock_get_doc, mock_delete):
        """Hard delete skips confirmation when stdin is not a TTY (agent mode)."""
        mock_get_doc.return_value = Document.from_row(
            {
                "id": 1,
                "title": "Agent Hard Delete",
                "project": None,
                "created_at": datetime(2024, 1, 1),
                "access_count": 0,
            }
        )
        mock_delete.return_value = True

        # No --force flag, --hard, should still proceed without prompting
        result = runner.invoke(app, ["delete", "1", "--hard"])
        assert result.exit_code == 0
        assert "Permanently deleted" in _out(result)
        mock_delete.assert_called_once_with("1", hard_delete=True)


# ---------------------------------------------------------------------------
# trash command (now a subcommand group: emdx trash [list|restore|purge])
# Uses main_app since trash is registered as a typer subgroup there.
# Late import to avoid circular dependency with main module
# ---------------------------------------------------------------------------
from emdx.main import app as main_app  # noqa: E402


class TestTrashCommand:
    """Tests for the trash command."""

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_trash_empty(self, mock_list_deleted):
        """Empty trash shows message."""
        mock_list_deleted.return_value = []

        result = runner.invoke(main_app, ["trash"])
        assert result.exit_code == 0
        assert "No documents in trash" in _out(result)

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_trash_with_items(self, mock_list_deleted):
        """Trash with items shows table."""
        mock_list_deleted.return_value = [
            Document.from_row(
                {
                    "id": 1,
                    "title": "Deleted Doc",
                    "project": "proj",
                    "deleted_at": datetime(2024, 6, 1, 10, 0),
                    "access_count": 3,
                }
            )
        ]

        result = runner.invoke(main_app, ["trash"])
        assert result.exit_code == 0
        assert "Deleted Doc" in _out(result)

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_trash_with_days_filter(self, mock_list_deleted):
        """Trash --days filters by age."""
        mock_list_deleted.return_value = []

        result = runner.invoke(main_app, ["trash", "--days", "7"])
        assert result.exit_code == 0
        mock_list_deleted.assert_called_once_with(days=7, limit=50)


# ---------------------------------------------------------------------------
# trash restore command
# ---------------------------------------------------------------------------
class TestRestoreCommand:
    """Tests for the trash restore command."""

    @patch("emdx.commands.trash.restore_document")
    def test_restore_by_id(self, mock_restore):
        """Restore a specific document."""
        mock_restore.return_value = True

        result = runner.invoke(main_app, ["trash", "restore", "1"])
        assert result.exit_code == 0
        assert "Restored" in _out(result)

    @patch("emdx.commands.trash.restore_document")
    def test_restore_not_found(self, mock_restore):
        """Restore a document not in trash."""
        mock_restore.return_value = False

        result = runner.invoke(main_app, ["trash", "restore", "999"])
        assert result.exit_code == 0
        assert "Could not restore" in _out(result)

    def test_restore_no_args(self):
        """Restore with no ID and no --all should error."""

        result = runner.invoke(main_app, ["trash", "restore"])
        assert result.exit_code != 0

    @patch("emdx.commands.trash.list_deleted_documents")
    @patch("emdx.commands.trash.restore_document")
    def test_restore_all(self, mock_restore, mock_list_deleted):
        """Restore --all restores all deleted documents."""
        mock_list_deleted.return_value = [
            Document.from_row({"id": 1, "title": "D1"}),
            Document.from_row({"id": 2, "title": "D2"}),
        ]
        mock_restore.return_value = True

        with patch("emdx.commands.trash.is_non_interactive", return_value=False):
            result = runner.invoke(main_app, ["trash", "restore", "--all"], input="y\n")
        assert result.exit_code == 0
        assert "Restored 2" in _out(result)


# ---------------------------------------------------------------------------
# trash purge command
# ---------------------------------------------------------------------------
class TestPurgeCommand:
    """Tests for the trash purge command."""

    @patch("emdx.commands.trash.list_deleted_documents")
    def test_purge_empty_trash(self, mock_list_deleted):
        """Purge with empty trash shows message."""
        mock_list_deleted.return_value = []

        result = runner.invoke(main_app, ["trash", "purge"])
        assert result.exit_code == 0
        assert "No documents in trash" in _out(result)

    @patch("emdx.commands.trash.purge_deleted_documents")
    @patch("emdx.commands.trash.list_deleted_documents")
    def test_purge_with_force(self, mock_list_deleted, mock_purge):
        """Purge --force skips confirmation."""
        mock_list_deleted.return_value = [
            Document.from_row({"id": 1, "title": "D", "deleted_at": datetime(2024, 1, 1)})
        ]
        mock_purge.return_value = 1

        result = runner.invoke(main_app, ["trash", "purge", "--force"])
        assert result.exit_code == 0
        assert "Permanently deleted" in _out(result)
