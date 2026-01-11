"""Tests for export profile system."""

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


class ExportProfileTestDatabase:
    """Test database with export profile tables."""

    def __init__(self, db_path=":memory:"):
        self.db_path = db_path
        if db_path == ":memory:":
            self.conn = sqlite3.connect(":memory:")
        else:
            self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def get_connection(self):
        """Get a database connection."""
        return self.conn

    def _create_schema(self):
        """Create the database schema with export profile tables."""
        conn = self.conn

        # Create documents table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                project TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                deleted_at TIMESTAMP,
                is_deleted BOOLEAN DEFAULT FALSE
            )
        """)

        # Create export_profiles table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS export_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                display_name TEXT NOT NULL,
                description TEXT,
                format TEXT NOT NULL DEFAULT 'markdown',
                strip_tags TEXT,
                add_frontmatter BOOLEAN DEFAULT FALSE,
                frontmatter_fields TEXT,
                header_template TEXT,
                footer_template TEXT,
                tag_to_label TEXT,
                dest_type TEXT NOT NULL DEFAULT 'clipboard',
                dest_path TEXT,
                gdoc_folder TEXT,
                gist_public BOOLEAN DEFAULT FALSE,
                post_actions TEXT,
                project TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                is_builtin BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                use_count INTEGER DEFAULT 0,
                last_used_at TIMESTAMP
            )
        """)

        # Create export_history table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS export_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                profile_id INTEGER NOT NULL,
                dest_type TEXT NOT NULL,
                dest_url TEXT,
                exported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (document_id) REFERENCES documents(id),
                FOREIGN KEY (profile_id) REFERENCES export_profiles(id)
            )
        """)

        conn.commit()

    def save_document(self, title, content, project=None):
        """Save a document to the database."""
        cursor = self.conn.execute(
            "INSERT INTO documents (title, content, project) VALUES (?, ?, ?)",
            (title, content, project),
        )
        self.conn.commit()
        return cursor.lastrowid

    def close(self):
        """Close the database connection."""
        if self.conn:
            self.conn.close()


@pytest.fixture
def test_db():
    """Create a test database with export profile tables."""
    db = ExportProfileTestDatabase()
    yield db
    db.close()


@pytest.fixture
def mock_db_connection(test_db):
    """Mock the db_connection to use our test database."""
    with patch("emdx.models.export_profiles.db_connection") as mock:
        mock.get_connection.return_value.__enter__ = lambda s: test_db.get_connection()
        mock.get_connection.return_value.__exit__ = lambda s, *args: None

        # Make it a proper context manager
        class MockContextManager:
            def __enter__(self):
                return test_db.get_connection()
            def __exit__(self, *args):
                pass

        mock.get_connection.return_value = MockContextManager()

        yield mock


class TestContentTransformer:
    """Tests for ContentTransformer service."""

    def test_basic_transform(self):
        """Test basic content transformation without any transforms."""
        from emdx.services.content_transformer import ContentTransformer

        document = {
            "id": 1,
            "title": "Test Document",
            "content": "This is test content.",
            "project": "test-project",
        }
        profile = {
            "format": "markdown",
            "dest_type": "clipboard",
        }

        transformer = ContentTransformer(document, profile)
        ctx = transformer.transform()

        assert ctx.original_content == "This is test content."
        assert ctx.transformed_content == "This is test content."

    def test_strip_tags(self):
        """Test stripping emoji tags from content."""
        from emdx.services.content_transformer import ContentTransformer

        document = {
            "id": 1,
            "title": "Test Document",
            "content": "🚧 Work in progress 🐛 Bug found",
            "project": "test-project",
        }
        profile = {
            "format": "markdown",
            "strip_tags": ["🚧", "🐛"],
        }

        transformer = ContentTransformer(document, profile)
        ctx = transformer.transform()

        assert "🚧" not in ctx.transformed_content
        assert "🐛" not in ctx.transformed_content
        assert "Work in progress" in ctx.transformed_content

    def test_strip_tags_json_string(self):
        """Test stripping tags when provided as JSON string."""
        from emdx.services.content_transformer import ContentTransformer

        document = {
            "id": 1,
            "title": "Test Document",
            "content": "🚧 Work in progress",
            "project": "test-project",
        }
        profile = {
            "format": "markdown",
            "strip_tags": '["🚧"]',
        }

        transformer = ContentTransformer(document, profile)
        ctx = transformer.transform()

        assert "🚧" not in ctx.transformed_content

    def test_tag_to_label_mapping(self):
        """Test converting emoji tags to text labels."""
        from emdx.services.content_transformer import ContentTransformer

        document = {
            "id": 1,
            "title": "Test Document",
            "content": "🐛 Bug report: Something is broken",
            "project": "test-project",
        }
        profile = {
            "format": "markdown",
            "tag_to_label": {"🐛": "bug"},
        }

        transformer = ContentTransformer(document, profile)
        ctx = transformer.transform()

        assert "[bug]" in ctx.transformed_content
        assert "🐛" not in ctx.transformed_content

    def test_header_template(self):
        """Test adding header template."""
        from emdx.services.content_transformer import ContentTransformer

        document = {
            "id": 42,
            "title": "My Document",
            "content": "Content here.",
            "project": "my-project",
        }
        profile = {
            "format": "markdown",
            "header_template": "# {{title}}\n\nDocument ID: {{id}}",
        }

        transformer = ContentTransformer(document, profile)
        ctx = transformer.transform()

        assert ctx.transformed_content.startswith("# My Document")
        assert "Document ID: 42" in ctx.transformed_content
        assert "Content here." in ctx.transformed_content

    def test_footer_template(self):
        """Test adding footer template."""
        from emdx.services.content_transformer import ContentTransformer

        document = {
            "id": 1,
            "title": "Test",
            "content": "Content.",
            "project": "test",
        }
        profile = {
            "format": "markdown",
            "footer_template": "---\nGenerated from {{project}}",
        }

        transformer = ContentTransformer(document, profile)
        ctx = transformer.transform()

        assert ctx.transformed_content.endswith("Generated from test")

    def test_frontmatter(self):
        """Test adding YAML frontmatter."""
        from emdx.services.content_transformer import ContentTransformer

        document = {
            "id": 1,
            "title": "My Blog Post",
            "content": "Content here.",
            "project": "blog",
        }
        profile = {
            "format": "markdown",
            "add_frontmatter": True,
            "frontmatter_fields": ["title", "date"],
        }

        transformer = ContentTransformer(document, profile)
        ctx = transformer.transform()

        assert ctx.transformed_content.startswith("---\n")
        assert "title: My Blog Post" in ctx.transformed_content
        assert "date:" in ctx.transformed_content
        # Content should come after frontmatter
        assert "Content here." in ctx.transformed_content

    def test_full_pipeline(self):
        """Test full transform pipeline with multiple transforms."""
        from emdx.services.content_transformer import ContentTransformer

        document = {
            "id": 42,
            "title": "Feature Request",
            "content": "✨ Add dark mode support\n\n🚧 In progress",
            "project": "my-app",
        }
        profile = {
            "format": "markdown",
            "strip_tags": ["🚧"],
            "tag_to_label": {"✨": "feature"},
            "add_frontmatter": True,
            "frontmatter_fields": ["title", "date"],
            "footer_template": "---\nExported from EMDX",
        }

        transformer = ContentTransformer(document, profile)
        ctx = transformer.transform()

        # Check frontmatter
        assert ctx.transformed_content.startswith("---\n")
        assert "title: Feature Request" in ctx.transformed_content

        # Check stripped tags
        assert "🚧" not in ctx.transformed_content

        # Check label mapping
        assert "[feature]" in ctx.transformed_content
        assert "✨" not in ctx.transformed_content

        # Check footer
        assert "Exported from EMDX" in ctx.transformed_content


class TestExportDestinations:
    """Tests for export destination handlers."""

    def test_clipboard_destination_interface(self):
        """Test ClipboardDestination has correct interface."""
        from emdx.services.export_destinations import ClipboardDestination

        dest = ClipboardDestination()
        assert hasattr(dest, "export")
        assert callable(dest.export)

    def test_file_destination_interface(self):
        """Test FileDestination has correct interface."""
        from emdx.services.export_destinations import FileDestination

        dest = FileDestination()
        assert hasattr(dest, "export")
        assert callable(dest.export)

    def test_file_destination_path_expansion(self):
        """Test FileDestination expands template variables in path."""
        from emdx.services.export_destinations import FileDestination

        dest = FileDestination()

        document = {"id": 42, "title": "My Document", "project": "test"}
        path = dest._expand_path("~/exports/{{title}}.md", document)

        assert "My-Document" in path or "My Document" in path
        assert "{{title}}" not in path

    def test_file_destination_sanitize_filename(self):
        """Test FileDestination sanitizes filenames."""
        from emdx.services.export_destinations import FileDestination

        dest = FileDestination()

        # Test with invalid characters
        sanitized = dest._sanitize_filename("File: With \"Special\" Chars?")
        assert ":" not in sanitized
        assert '"' not in sanitized
        assert "?" not in sanitized

    def test_get_destination_clipboard(self):
        """Test getting clipboard destination."""
        from emdx.services.export_destinations import get_destination

        dest = get_destination("clipboard")
        assert dest is not None

    def test_get_destination_file(self):
        """Test getting file destination."""
        from emdx.services.export_destinations import get_destination

        dest = get_destination("file")
        assert dest is not None

    def test_get_destination_invalid(self):
        """Test getting invalid destination raises error."""
        from emdx.services.export_destinations import get_destination

        with pytest.raises(ValueError):
            get_destination("invalid_dest_type")

    def test_file_destination_export(self):
        """Test FileDestination actually writes file."""
        from emdx.services.export_destinations import FileDestination

        with tempfile.TemporaryDirectory() as tmpdir:
            dest = FileDestination()
            document = {"id": 1, "title": "Test", "project": "test"}
            profile = {"dest_path": f"{tmpdir}/test_export.md"}

            result = dest.export("Test content", document, profile)

            assert result.success
            assert Path(f"{tmpdir}/test_export.md").exists()
            assert Path(f"{tmpdir}/test_export.md").read_text() == "Test content"

    def test_file_destination_no_path(self):
        """Test FileDestination fails without path."""
        from emdx.services.export_destinations import FileDestination

        dest = FileDestination()
        document = {"id": 1, "title": "Test"}
        profile = {}  # No dest_path

        result = dest.export("Content", document, profile)

        assert not result.success
        assert "No destination path" in result.message


class TestExportProfileModel:
    """Tests for export profile model operations."""

    def test_create_profile(self, test_db, mock_db_connection):
        """Test creating a new export profile."""
        from emdx.models.export_profiles import create_profile, get_profile

        profile_id = create_profile(
            name="test-profile",
            display_name="Test Profile",
            description="A test profile",
            format="markdown",
            dest_type="clipboard",
        )

        assert profile_id > 0

        # Verify profile was created
        conn = test_db.get_connection()
        cursor = conn.execute("SELECT * FROM export_profiles WHERE id = ?", (profile_id,))
        row = cursor.fetchone()

        assert row is not None
        assert row["name"] == "test-profile"
        assert row["display_name"] == "Test Profile"

    def test_get_profile_by_name(self, test_db, mock_db_connection):
        """Test getting a profile by name."""
        from emdx.models.export_profiles import create_profile, get_profile

        create_profile(
            name="my-profile",
            display_name="My Profile",
        )

        profile = get_profile("my-profile")

        assert profile is not None
        assert profile["name"] == "my-profile"

    def test_get_profile_by_id(self, test_db, mock_db_connection):
        """Test getting a profile by ID."""
        from emdx.models.export_profiles import create_profile, get_profile

        profile_id = create_profile(
            name="id-test",
            display_name="ID Test",
        )

        profile = get_profile(profile_id)

        assert profile is not None
        assert profile["id"] == profile_id

    def test_list_profiles(self, test_db, mock_db_connection):
        """Test listing profiles."""
        from emdx.models.export_profiles import create_profile, list_profiles

        create_profile(name="profile-1", display_name="Profile 1")
        create_profile(name="profile-2", display_name="Profile 2")

        profiles = list_profiles()

        assert len(profiles) >= 2
        names = [p["name"] for p in profiles]
        assert "profile-1" in names
        assert "profile-2" in names

    def test_update_profile(self, test_db, mock_db_connection):
        """Test updating a profile."""
        from emdx.models.export_profiles import create_profile, update_profile, get_profile

        profile_id = create_profile(
            name="update-test",
            display_name="Original Name",
        )

        update_profile(profile_id, display_name="Updated Name")

        profile = get_profile(profile_id)
        assert profile["display_name"] == "Updated Name"

    def test_delete_profile(self, test_db, mock_db_connection):
        """Test soft-deleting a profile."""
        from emdx.models.export_profiles import create_profile, delete_profile, get_profile

        profile_id = create_profile(
            name="delete-test",
            display_name="To Delete",
        )

        result = delete_profile(profile_id)
        assert result

        # Profile should not be found (soft deleted)
        profile = get_profile(profile_id)
        assert profile is None

    def test_delete_builtin_profile_fails(self, test_db, mock_db_connection):
        """Test that built-in profiles cannot be deleted."""
        from emdx.models.export_profiles import delete_profile

        # Insert a built-in profile
        conn = test_db.get_connection()
        conn.execute("""
            INSERT INTO export_profiles (name, display_name, is_builtin, is_active)
            VALUES ('builtin-profile', 'Built-in', TRUE, TRUE)
        """)
        conn.commit()

        with pytest.raises(ValueError, match="Cannot delete built-in"):
            delete_profile("builtin-profile")

    def test_record_export(self, test_db, mock_db_connection):
        """Test recording export history."""
        from emdx.models.export_profiles import create_profile, record_export, get_export_history

        # Create a document
        doc_id = test_db.save_document("Test Doc", "Content", "test")

        # Create a profile
        profile_id = create_profile(
            name="history-test",
            display_name="History Test",
        )

        # Record export
        history_id = record_export(
            document_id=doc_id,
            profile_id=profile_id,
            dest_type="clipboard",
            dest_url=None,
        )

        assert history_id > 0

        # Verify history was recorded
        conn = test_db.get_connection()
        cursor = conn.execute("SELECT * FROM export_history WHERE id = ?", (history_id,))
        row = cursor.fetchone()

        assert row is not None
        assert row["document_id"] == doc_id
        assert row["profile_id"] == profile_id

    def test_increment_use_count(self, test_db, mock_db_connection):
        """Test incrementing profile use count."""
        from emdx.models.export_profiles import create_profile, record_export, get_profile

        profile_id = create_profile(
            name="count-test",
            display_name="Count Test",
        )

        doc_id = test_db.save_document("Doc", "Content", None)

        # Record should increment use count
        record_export(doc_id, profile_id, "clipboard")
        record_export(doc_id, profile_id, "clipboard")

        profile = get_profile(profile_id)
        assert profile["use_count"] == 2

    def test_profile_json_fields_parsed(self, test_db, mock_db_connection):
        """Test that JSON fields are properly parsed when retrieved."""
        from emdx.models.export_profiles import create_profile, get_profile

        create_profile(
            name="json-test",
            display_name="JSON Test",
            strip_tags=["🚧", "🐛"],
            tag_to_label={"🐛": "bug"},
            frontmatter_fields=["title", "date"],
        )

        profile = get_profile("json-test")

        assert isinstance(profile["strip_tags"], list)
        assert "🚧" in profile["strip_tags"]
        assert isinstance(profile["tag_to_label"], dict)
        assert profile["tag_to_label"]["🐛"] == "bug"
        assert isinstance(profile["frontmatter_fields"], list)


class TestExportProfilesCLI:
    """Integration tests for export-profile CLI commands."""

    def test_import_cli_modules(self):
        """Test that CLI modules can be imported."""
        from emdx.commands.export_profiles import app
        from emdx.commands.export import app as export_app

        assert app is not None
        assert export_app is not None

    def test_export_profiles_app_has_commands(self):
        """Test that export_profiles app has expected commands."""
        from emdx.commands.export_profiles import app

        command_names = [cmd.name for cmd in app.registered_commands]

        assert "create" in command_names
        assert "list" in command_names
        assert "show" in command_names
        assert "delete" in command_names

    def test_export_app_has_commands(self):
        """Test that export app has expected commands."""
        from emdx.commands.export import app

        command_names = [cmd.name for cmd in app.registered_commands]

        assert "export" in command_names
        assert "quick" in command_names


class TestMigration:
    """Tests for database migration."""

    def test_migration_creates_tables(self):
        """Test that migration creates required tables."""
        import sqlite3
        from emdx.database.migrations import migration_015_add_export_profiles

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        # Create prerequisite documents table
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT
            )
        """)

        # Run migration
        migration_015_add_export_profiles(conn)

        # Check tables exist
        cursor = conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name IN ('export_profiles', 'export_history')
        """)
        tables = [row["name"] for row in cursor.fetchall()]

        assert "export_profiles" in tables
        assert "export_history" in tables

    def test_migration_creates_builtin_profiles(self):
        """Test that migration creates built-in profiles."""
        import sqlite3
        from emdx.database.migrations import migration_015_add_export_profiles

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        # Create prerequisite documents table
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT
            )
        """)

        # Run migration
        migration_015_add_export_profiles(conn)

        # Check built-in profiles
        cursor = conn.execute("""
            SELECT name FROM export_profiles WHERE is_builtin = TRUE
        """)
        profiles = [row["name"] for row in cursor.fetchall()]

        assert "blog-post" in profiles
        assert "github-issue" in profiles
        assert "share-external" in profiles
        assert "quick-gist" in profiles

    def test_migration_is_idempotent(self):
        """Test that running migration twice doesn't cause errors."""
        import sqlite3
        from emdx.database.migrations import migration_015_add_export_profiles

        conn = sqlite3.connect(":memory:")

        # Create prerequisite documents table
        conn.execute("""
            CREATE TABLE documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT
            )
        """)

        # Run migration twice
        migration_015_add_export_profiles(conn)
        migration_015_add_export_profiles(conn)  # Should not raise

        # Count builtin profiles (should still be 5)
        cursor = conn.execute("SELECT COUNT(*) FROM export_profiles WHERE is_builtin = TRUE")
        count = cursor.fetchone()[0]

        assert count == 5
