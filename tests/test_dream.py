"""Tests for the Dream Journal command."""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from emdx.commands.dream import (
    DreamDigest,
    HygieneIssue,
    MergeCandidate,
    TagPattern,
    _analyze_tag_patterns,
    _count_recent_docs,
    _find_hygiene_issues,
    _find_merge_candidates,
    _generate_digest_markdown,
    _get_latest_digest,
    _save_digest,
    _setup_cron,
    dream,
)


class TestDataclasses:
    """Tests for dream journal dataclasses."""

    def test_merge_candidate_creation(self):
        """Test creating a MergeCandidate instance."""
        mc = MergeCandidate(
            doc1_id=1,
            doc2_id=2,
            doc1_title="Doc One",
            doc2_title="Doc Two",
            similarity=0.85,
        )

        assert mc.doc1_id == 1
        assert mc.doc2_id == 2
        assert mc.doc1_title == "Doc One"
        assert mc.doc2_title == "Doc Two"
        assert mc.similarity == 0.85

    def test_tag_pattern_creation(self):
        """Test creating a TagPattern instance."""
        tp = TagPattern(
            tag_name="python",
            doc_count=10,
            projects=["project-a", "project-b"],
            insight="Used in 2 projects",
        )

        assert tp.tag_name == "python"
        assert tp.doc_count == 10
        assert tp.projects == ["project-a", "project-b"]
        assert tp.insight == "Used in 2 projects"

    def test_hygiene_issue_creation(self):
        """Test creating a HygieneIssue instance."""
        hi = HygieneIssue(
            issue_type="untagged",
            doc_id=42,
            doc_title="Orphan Document",
            detail="No tags assigned",
        )

        assert hi.issue_type == "untagged"
        assert hi.doc_id == 42
        assert hi.doc_title == "Orphan Document"
        assert hi.detail == "No tags assigned"

    def test_dream_digest_creation_empty(self):
        """Test creating an empty DreamDigest."""
        now = datetime.now()
        dd = DreamDigest(date=now, docs_processed=0)

        assert dd.date == now
        assert dd.docs_processed == 0
        assert dd.merge_candidates == []
        assert dd.tag_patterns == []
        assert dd.hygiene_issues == []
        assert dd.cross_project_patterns == []

    def test_dream_digest_creation_with_data(self):
        """Test creating a DreamDigest with data."""
        now = datetime.now()
        mc = MergeCandidate(1, 2, "Doc1", "Doc2", 0.9)
        tp = TagPattern("python", 5, ["p1"], "Insight")
        hi = HygieneIssue("empty", 10, "Empty Doc", "Only 5 chars")

        dd = DreamDigest(
            date=now,
            docs_processed=100,
            merge_candidates=[mc],
            tag_patterns=[tp],
            hygiene_issues=[hi],
            cross_project_patterns=["Pattern 1"],
        )

        assert dd.docs_processed == 100
        assert len(dd.merge_candidates) == 1
        assert len(dd.tag_patterns) == 1
        assert len(dd.hygiene_issues) == 1
        assert len(dd.cross_project_patterns) == 1


class TestDigestMarkdownGeneration:
    """Tests for markdown digest generation."""

    def test_generate_digest_empty(self):
        """Test generating markdown for empty digest."""
        digest = DreamDigest(
            date=datetime(2024, 1, 15, 10, 30),
            docs_processed=0,
        )

        md = _generate_digest_markdown(digest)

        assert "# 🌙 Dream Journal — January 15, 2024" in md
        assert "Processed 0 recent documents." in md
        assert "✨ No duplicate documents found!" in md
        assert "✨ No hygiene issues found!" in md

    def test_generate_digest_with_merge_candidates(self):
        """Test generating markdown with merge candidates."""
        digest = DreamDigest(
            date=datetime(2024, 1, 15, 10, 30),
            docs_processed=50,
            merge_candidates=[
                MergeCandidate(1, 2, "Python Guide", "Python Tutorial", 0.85),
                MergeCandidate(3, 4, "Docker Notes", "Docker Docs", 0.92),
            ],
        )

        md = _generate_digest_markdown(digest)

        assert "## 🔄 Consolidation Candidates" in md
        assert "**#1** + **#2**" in md
        assert "85%" in md
        assert "**#3** + **#4**" in md
        assert "92%" in md
        assert "emdx maintain --merge" in md

    def test_generate_digest_with_patterns(self):
        """Test generating markdown with cross-project patterns."""
        digest = DreamDigest(
            date=datetime(2024, 1, 15, 10, 30),
            docs_processed=50,
            cross_project_patterns=[
                "'python' spans 3 projects: proj-a, proj-b, proj-c",
                "5 gameplans marked 'done' — consider archiving",
            ],
        )

        md = _generate_digest_markdown(digest)

        assert "## 🔍 Discovered Patterns" in md
        assert "'python' spans 3 projects" in md
        assert "gameplans marked 'done'" in md

    def test_generate_digest_with_hygiene_issues(self):
        """Test generating markdown with hygiene issues."""
        digest = DreamDigest(
            date=datetime(2024, 1, 15, 10, 30),
            docs_processed=50,
            hygiene_issues=[
                HygieneIssue("untagged", 10, "Doc A", "No tags"),
                HygieneIssue("untagged", 11, "Doc B", "No tags"),
                HygieneIssue("empty", 20, "Empty Doc", "Only 5 chars"),
                HygieneIssue("stale", 30, "Old Doc", "Never viewed"),
            ],
        )

        md = _generate_digest_markdown(digest)

        assert "## 🧹 Maintenance Needed" in md
        assert "📑 Untagged Documents (2)" in md
        assert "📄 Empty Documents (1)" in md
        assert "🕸️ Stale Documents (1)" in md
        assert "#10" in md
        assert "#20" in md
        assert "#30" in md


class TestDatabaseQueries:
    """Tests for database query functions."""

    def test_count_recent_docs(self, temp_db):
        """Test counting recent documents."""
        # Add some documents
        conn = temp_db.get_connection()
        for i in range(5):
            temp_db.save_document(f"Doc {i}", "Content " * 20, "test-project")
        conn.commit()

        with patch("emdx.commands.dream.db") as mock_db:

            class MockContextManager:
                def __enter__(self):
                    return conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            count = _count_recent_docs(days=7)
            assert count == 5

    def test_find_hygiene_issues_untagged(self, temp_db):
        """Test finding untagged documents."""
        conn = temp_db.get_connection()
        # Add document without tags
        temp_db.save_document("Untagged Doc", "Content " * 20, "test-project")
        conn.commit()

        with patch("emdx.commands.dream.db") as mock_db:

            class MockContextManager:
                def __enter__(self):
                    return conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            issues = _find_hygiene_issues()

            untagged = [i for i in issues if i.issue_type == "untagged"]
            assert len(untagged) == 1
            assert "Untagged Doc" in untagged[0].doc_title

    def test_find_hygiene_issues_no_project(self, temp_db):
        """Test finding documents with no project."""
        conn = temp_db.get_connection()
        # Add document without project
        temp_db.save_document("No Project Doc", "Content " * 20, None)
        conn.commit()

        with patch("emdx.commands.dream.db") as mock_db:

            class MockContextManager:
                def __enter__(self):
                    return conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            issues = _find_hygiene_issues()

            no_project = [i for i in issues if i.issue_type == "no_project"]
            assert len(no_project) == 1
            assert "No Project Doc" in no_project[0].doc_title

    def test_find_hygiene_issues_empty(self, temp_db):
        """Test finding empty documents."""
        conn = temp_db.get_connection()
        # Add nearly empty document
        conn.execute(
            "INSERT INTO documents (title, content, project) VALUES (?, ?, ?)",
            ("Empty Doc", "Short", "test-project"),
        )
        conn.commit()

        with patch("emdx.commands.dream.db") as mock_db:

            class MockContextManager:
                def __enter__(self):
                    return conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            issues = _find_hygiene_issues()

            empty = [i for i in issues if i.issue_type == "empty"]
            assert len(empty) == 1
            assert "Empty Doc" in empty[0].doc_title

    def test_analyze_tag_patterns_cross_project(self, temp_db):
        """Test finding tags used across multiple projects."""
        conn = temp_db.get_connection()

        # Create documents in different projects with shared tags
        doc1_id = temp_db.save_document("Doc 1", "Content " * 20, "project-a")
        doc2_id = temp_db.save_document("Doc 2", "Content " * 20, "project-b")

        # Add shared tag to both
        conn.execute("INSERT INTO tags (name, usage_count) VALUES (?, ?)", ("python", 2))
        tag_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
            (doc1_id, tag_id),
        )
        conn.execute(
            "INSERT INTO document_tags (document_id, tag_id) VALUES (?, ?)",
            (doc2_id, tag_id),
        )
        conn.commit()

        with patch("emdx.commands.dream.db") as mock_db:

            class MockContextManager:
                def __enter__(self):
                    return conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            patterns, cross_project = _analyze_tag_patterns()

            assert len(patterns) == 1
            assert patterns[0].tag_name == "python"
            assert patterns[0].doc_count == 2
            assert len(cross_project) >= 1
            assert any("python" in p for p in cross_project)

    def test_get_latest_digest_none(self, temp_db):
        """Test getting latest digest when none exists."""
        conn = temp_db.get_connection()

        with patch("emdx.commands.dream.db") as mock_db:

            class MockContextManager:
                def __enter__(self):
                    return conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            result = _get_latest_digest()
            assert result is None


class TestMergeCandidateFinding:
    """Tests for merge candidate detection."""

    def test_find_merge_candidates_no_sklearn(self):
        """Test graceful handling when sklearn is not available."""
        with patch(
            "emdx.commands.dream.SimilarityService",
            side_effect=ImportError("sklearn not installed"),
        ):
            result = _find_merge_candidates()
            assert result == []

    def test_find_merge_candidates_empty_db(self, temp_db):
        """Test finding candidates with empty database."""
        conn = temp_db.get_connection()

        mock_service = MagicMock()
        mock_service.find_all_duplicate_pairs.return_value = []

        with patch("emdx.commands.dream.SimilarityService", return_value=mock_service):
            with patch("emdx.commands.dream.db") as mock_db:

                class MockContextManager:
                    def __enter__(self):
                        return conn

                    def __exit__(self, *args):
                        pass

                mock_db.get_connection.return_value = MockContextManager()

                result = _find_merge_candidates()
                assert result == []


class TestCronSetup:
    """Tests for cron job setup."""

    def test_setup_cron_no_crontab(self):
        """Test handling when crontab is not available."""
        with patch("shutil.which", return_value=None):
            result = _setup_cron()
            assert result is False

    def test_setup_cron_already_scheduled(self):
        """Test detection of already scheduled job."""
        with patch("shutil.which", return_value="/usr/bin/crontab"):
            with patch("subprocess.run") as mock_run:
                # Simulate existing crontab with dream job
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="0 3 * * * emdx dream --quiet"
                )

                result = _setup_cron()
                assert result is True

    def test_setup_cron_success(self):
        """Test successful cron job installation."""
        with patch("shutil.which", return_value="/usr/bin/crontab"):
            with patch("subprocess.run") as mock_run:
                # First call: get existing crontab (empty)
                # Second call: install new crontab
                mock_run.side_effect = [
                    MagicMock(returncode=0, stdout=""),
                    MagicMock(returncode=0),
                ]

                result = _setup_cron()
                assert result is True
                assert mock_run.call_count == 2


class TestDreamCommand:
    """Tests for the dream CLI command."""

    def test_dream_command_help(self):
        """Test that dream command has proper help text."""
        from emdx.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["dream", "--help"])

        assert result.exit_code == 0
        assert "Dream Journal" in result.output
        assert "--schedule" in result.output
        assert "--digest" in result.output
        assert "--latest" in result.output
        assert "--days" in result.output
        assert "--threshold" in result.output
        assert "--quiet" in result.output
        assert "--json" in result.output

    def test_dream_schedule_no_crontab(self):
        """Test schedule flag when crontab unavailable."""
        from emdx.main import app

        runner = CliRunner()
        with patch("emdx.commands.dream._setup_cron", return_value=False):
            result = runner.invoke(app, ["dream", "--schedule"])

            assert result.exit_code == 0
            assert "Could not set up cron job" in result.output

    def test_dream_schedule_success(self):
        """Test successful schedule setup."""
        from emdx.main import app

        runner = CliRunner()
        with patch("emdx.commands.dream._setup_cron", return_value=True):
            result = runner.invoke(app, ["dream", "--schedule"])

            assert result.exit_code == 0
            assert "Cron job scheduled" in result.output

    def test_dream_latest_no_journal(self, temp_db):
        """Test latest flag when no journal exists."""
        from emdx.main import app

        runner = CliRunner()
        conn = temp_db.get_connection()

        with patch("emdx.commands.dream.db") as mock_db:

            class MockContextManager:
                def __enter__(self):
                    return conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            result = runner.invoke(app, ["dream", "--latest"])

            assert result.exit_code == 0
            assert "No dream journal found" in result.output

    def test_dream_json_output(self, temp_db):
        """Test JSON output format."""
        from emdx.main import app

        runner = CliRunner()
        conn = temp_db.get_connection()

        with patch("emdx.commands.dream.db") as mock_db:

            class MockContextManager:
                def __enter__(self):
                    return conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            with patch("emdx.commands.dream._find_merge_candidates", return_value=[]):
                with patch(
                    "emdx.commands.dream._analyze_tag_patterns", return_value=([], [])
                ):
                    with patch(
                        "emdx.commands.dream._find_hygiene_issues", return_value=[]
                    ):
                        result = runner.invoke(app, ["dream", "--json"])

                        assert result.exit_code == 0
                        # Parse the JSON output
                        output = json.loads(result.output)
                        assert "date" in output
                        assert "docs_processed" in output
                        assert "merge_candidates" in output
                        assert "cross_project_patterns" in output
                        assert "hygiene_issues" in output

    def test_dream_digest_only(self, temp_db):
        """Test digest-only mode (no save)."""
        from emdx.main import app

        runner = CliRunner()
        conn = temp_db.get_connection()

        with patch("emdx.commands.dream.db") as mock_db:

            class MockContextManager:
                def __enter__(self):
                    return conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            with patch("emdx.commands.dream._find_merge_candidates", return_value=[]):
                with patch(
                    "emdx.commands.dream._analyze_tag_patterns", return_value=([], [])
                ):
                    with patch(
                        "emdx.commands.dream._find_hygiene_issues", return_value=[]
                    ):
                        # Track if save was called
                        with patch(
                            "emdx.commands.dream._save_digest"
                        ) as mock_save:
                            result = runner.invoke(app, ["dream", "--digest"])

                            assert result.exit_code == 0
                            assert "Digest preview only" in result.output
                            mock_save.assert_not_called()

    def test_dream_quiet_mode(self, temp_db):
        """Test quiet mode suppresses output."""
        from emdx.main import app

        runner = CliRunner()
        conn = temp_db.get_connection()

        with patch("emdx.commands.dream.db") as mock_db:

            class MockContextManager:
                def __enter__(self):
                    return conn

                def __exit__(self, *args):
                    pass

            mock_db.get_connection.return_value = MockContextManager()

            with patch("emdx.commands.dream._find_merge_candidates", return_value=[]):
                with patch(
                    "emdx.commands.dream._analyze_tag_patterns", return_value=([], [])
                ):
                    with patch(
                        "emdx.commands.dream._find_hygiene_issues", return_value=[]
                    ):
                        with patch(
                            "emdx.commands.dream._save_digest", return_value=123
                        ):
                            result = runner.invoke(app, ["dream", "--quiet"])

                            assert result.exit_code == 0
                            # In quiet mode, no progress output
                            assert "Step 1/3" not in result.output
                            assert "Processing" not in result.output


class TestSaveDigest:
    """Tests for digest saving functionality."""

    def test_save_digest(self, temp_db):
        """Test saving a digest to the database."""
        conn = temp_db.get_connection()
        digest = DreamDigest(
            date=datetime(2024, 1, 15, 10, 30),
            docs_processed=50,
        )

        with patch("emdx.commands.dream.save_document") as mock_save:
            mock_save.return_value = 42

            doc_id = _save_digest(digest)

            assert doc_id == 42
            mock_save.assert_called_once()
            call_kwargs = mock_save.call_args[1]
            assert "Dream Journal — January 15, 2024" in call_kwargs["title"]
            assert "dream-journal" in call_kwargs["tags"]
            assert "🌙" in call_kwargs["tags"]
