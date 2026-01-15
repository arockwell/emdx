"""Tests for document groups functionality.

Tests the hierarchical document grouping system that allows organizing
related documents into batches, rounds, and initiatives.
"""

import pytest


@pytest.fixture(autouse=True)
def clean_groups_table(isolate_test_database):
    """Clean up groups tables before each test.

    This fixture runs automatically before each test in this module,
    ensuring tests don't interfere with each other.
    """
    from emdx.database.connection import db_connection

    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM document_group_members")
        conn.execute("DELETE FROM document_groups")
        conn.commit()

    yield

    # Also clean up after (in case test creates data that could affect other test files)
    with db_connection.get_connection() as conn:
        conn.execute("DELETE FROM document_group_members")
        conn.execute("DELETE FROM document_groups")
        conn.commit()


class TestGroupCreation:
    """Test group creation and retrieval."""

    def test_create_group_basic(self, isolate_test_database):
        """Test creating a basic group."""
        from emdx.database import groups as groups_db

        group_id = groups_db.create_group(
            name="Test Group",
            group_type="batch",
        )

        assert group_id > 0

        group = groups_db.get_group(group_id)
        assert group is not None
        assert group["name"] == "Test Group"
        assert group["group_type"] == "batch"
        assert group["is_active"] == 1

    def test_create_group_with_all_fields(self, isolate_test_database):
        """Test creating a group with all optional fields."""
        from emdx.database import groups as groups_db

        group_id = groups_db.create_group(
            name="Full Group",
            group_type="initiative",
            project="test-project",
            description="A test initiative",
            created_by="test-user",
        )

        group = groups_db.get_group(group_id)
        assert group["name"] == "Full Group"
        assert group["group_type"] == "initiative"
        assert group["project"] == "test-project"
        assert group["description"] == "A test initiative"
        assert group["created_by"] == "test-user"

    def test_create_nested_group(self, isolate_test_database):
        """Test creating a nested group hierarchy."""
        from emdx.database import groups as groups_db

        # Create parent
        parent_id = groups_db.create_group(
            name="Parent Initiative",
            group_type="initiative",
        )

        # Create child
        child_id = groups_db.create_group(
            name="Child Round",
            group_type="round",
            parent_group_id=parent_id,
        )

        child = groups_db.get_group(child_id)
        assert child["parent_group_id"] == parent_id

    def test_get_nonexistent_group(self, isolate_test_database):
        """Test getting a group that doesn't exist."""
        from emdx.database import groups as groups_db

        group = groups_db.get_group(99999)
        assert group is None


class TestGroupListing:
    """Test group listing and filtering."""

    def test_list_all_groups(self, isolate_test_database):
        """Test listing all groups."""
        from emdx.database import groups as groups_db

        # Get baseline count
        baseline = len(groups_db.list_groups())

        groups_db.create_group(name="Group 1", group_type="batch")
        groups_db.create_group(name="Group 2", group_type="round")
        groups_db.create_group(name="Group 3", group_type="initiative")

        groups = groups_db.list_groups()
        assert len(groups) == baseline + 3

    def test_list_top_level_only(self, isolate_test_database):
        """Test listing only top-level groups."""
        from emdx.database import groups as groups_db

        # Get baseline count of top-level groups
        baseline = len(groups_db.list_groups(top_level_only=True))

        parent_id = groups_db.create_group(name="Parent", group_type="initiative")
        groups_db.create_group(name="Child", group_type="round", parent_group_id=parent_id)
        groups_db.create_group(name="Another Top", group_type="batch")

        groups = groups_db.list_groups(top_level_only=True)
        assert len(groups) == baseline + 2
        names = {g["name"] for g in groups}
        assert "Parent" in names
        assert "Another Top" in names

    def test_list_by_group_type(self, isolate_test_database):
        """Test filtering by group type."""
        from emdx.database import groups as groups_db

        # Get baseline count of batches
        baseline = len(groups_db.list_groups(group_type="batch"))

        groups_db.create_group(name="Batch 1", group_type="batch")
        groups_db.create_group(name="Batch 2", group_type="batch")
        groups_db.create_group(name="Round 1", group_type="round")

        batches = groups_db.list_groups(group_type="batch")
        assert len(batches) == baseline + 2
        assert all(g["group_type"] == "batch" for g in batches)

    def test_list_by_project(self, isolate_test_database):
        """Test filtering by project."""
        from emdx.database import groups as groups_db

        groups_db.create_group(name="Project A Group", project="project-a")
        groups_db.create_group(name="Project B Group", project="project-b")

        groups = groups_db.list_groups(project="project-a")
        assert len(groups) == 1
        assert groups[0]["name"] == "Project A Group"

    def test_list_children_of_parent(self, isolate_test_database):
        """Test listing children of a parent group."""
        from emdx.database import groups as groups_db

        parent_id = groups_db.create_group(name="Parent", group_type="initiative")
        groups_db.create_group(name="Child 1", group_type="round", parent_group_id=parent_id)
        groups_db.create_group(name="Child 2", group_type="batch", parent_group_id=parent_id)
        groups_db.create_group(name="Other", group_type="batch")

        children = groups_db.list_groups(parent_group_id=parent_id)
        assert len(children) == 2

    def test_list_excludes_inactive(self, isolate_test_database):
        """Test that inactive groups are excluded by default."""
        from emdx.database import groups as groups_db

        # Get baseline counts
        active_baseline = len(groups_db.list_groups())
        all_baseline = len(groups_db.list_groups(include_inactive=True))

        group_id = groups_db.create_group(name="Active Group")
        inactive_id = groups_db.create_group(name="Inactive Group")
        groups_db.delete_group(inactive_id, hard=False)  # Soft delete

        groups = groups_db.list_groups()
        # Only 1 new active group (the other was soft-deleted)
        assert len(groups) == active_baseline + 1
        active_names = {g["name"] for g in groups}
        assert "Active Group" in active_names
        assert "Inactive Group" not in active_names

        # Include inactive - should have both new groups
        all_groups = groups_db.list_groups(include_inactive=True)
        assert len(all_groups) == all_baseline + 2


class TestGroupUpdate:
    """Test group update operations."""

    def test_update_group_name(self, isolate_test_database):
        """Test updating group name."""
        from emdx.database import groups as groups_db

        group_id = groups_db.create_group(name="Original Name")
        groups_db.update_group(group_id, name="Updated Name")

        group = groups_db.get_group(group_id)
        assert group["name"] == "Updated Name"

    def test_update_group_description(self, isolate_test_database):
        """Test updating group description."""
        from emdx.database import groups as groups_db

        group_id = groups_db.create_group(name="Test Group")
        groups_db.update_group(group_id, description="New description")

        group = groups_db.get_group(group_id)
        assert group["description"] == "New description"

    def test_update_group_type(self, isolate_test_database):
        """Test changing group type."""
        from emdx.database import groups as groups_db

        group_id = groups_db.create_group(name="Test", group_type="batch")
        groups_db.update_group(group_id, group_type="round")

        group = groups_db.get_group(group_id)
        assert group["group_type"] == "round"

    def test_update_ignores_invalid_fields(self, isolate_test_database):
        """Test that update ignores fields not in allowed list."""
        from emdx.database import groups as groups_db

        group_id = groups_db.create_group(name="Test")
        result = groups_db.update_group(group_id, invalid_field="value")
        assert result is False


class TestGroupDeletion:
    """Test group deletion."""

    def test_soft_delete(self, isolate_test_database):
        """Test soft delete sets is_active to False."""
        from emdx.database import groups as groups_db

        group_id = groups_db.create_group(name="To Delete")
        groups_db.delete_group(group_id, hard=False)

        # Group still exists but is inactive
        group = groups_db.get_group(group_id)
        assert group is not None
        assert group["is_active"] == 0

    def test_hard_delete(self, isolate_test_database):
        """Test hard delete removes group completely."""
        from emdx.database import groups as groups_db

        group_id = groups_db.create_group(name="To Delete")
        groups_db.delete_group(group_id, hard=True)

        group = groups_db.get_group(group_id)
        assert group is None


class TestGroupHierarchy:
    """Test group hierarchy and cycle detection."""

    def test_get_child_groups(self, isolate_test_database):
        """Test getting child groups."""
        from emdx.database import groups as groups_db

        parent_id = groups_db.create_group(name="Parent", group_type="initiative")
        child1_id = groups_db.create_group(name="Child 1", parent_group_id=parent_id)
        child2_id = groups_db.create_group(name="Child 2", parent_group_id=parent_id)

        children = groups_db.get_child_groups(parent_id)
        assert len(children) == 2
        child_ids = {c["id"] for c in children}
        assert child1_id in child_ids
        assert child2_id in child_ids

    def test_three_level_hierarchy(self, isolate_test_database):
        """Test three-level group hierarchy."""
        from emdx.database import groups as groups_db

        initiative_id = groups_db.create_group(name="Initiative", group_type="initiative")
        round_id = groups_db.create_group(
            name="Round 1",
            group_type="round",
            parent_group_id=initiative_id,
        )
        batch_id = groups_db.create_group(
            name="Batch 1",
            group_type="batch",
            parent_group_id=round_id,
        )

        batch = groups_db.get_group(batch_id)
        round_group = groups_db.get_group(round_id)

        assert batch["parent_group_id"] == round_id
        assert round_group["parent_group_id"] == initiative_id

    def test_cycle_detection_direct(self, isolate_test_database):
        """Test that direct cycles are prevented."""
        from emdx.database import groups as groups_db

        group_id = groups_db.create_group(name="Self")

        with pytest.raises(ValueError, match="cycle"):
            groups_db.update_group(group_id, parent_group_id=group_id)

    def test_cycle_detection_indirect(self, isolate_test_database):
        """Test that indirect cycles are prevented."""
        from emdx.database import groups as groups_db

        # Create A -> B -> C hierarchy
        a_id = groups_db.create_group(name="A")
        b_id = groups_db.create_group(name="B", parent_group_id=a_id)
        c_id = groups_db.create_group(name="C", parent_group_id=b_id)

        # Try to make A a child of C (would create C -> A -> B -> C cycle)
        with pytest.raises(ValueError, match="cycle"):
            groups_db.update_group(a_id, parent_group_id=c_id)


class TestDocumentMembership:
    """Test adding and removing documents from groups."""

    def test_add_document_to_group(self, isolate_test_database):
        """Test adding a document to a group."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        # Create a document
        doc_id = save_document(
            title="Test Document",
            content="Test content",
            project="test",
        )

        # Create a group
        group_id = groups_db.create_group(name="Test Group")

        # Add document to group
        result = groups_db.add_document_to_group(group_id, doc_id)
        assert result is True

        # Verify membership
        members = groups_db.get_group_members(group_id)
        assert len(members) == 1
        assert members[0]["id"] == doc_id

    def test_add_document_with_role(self, isolate_test_database):
        """Test adding a document with a specific role."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        doc_id = save_document(
            title="Synthesis Document",
            content="Synthesis content",
            project="test",
        )
        group_id = groups_db.create_group(name="Test Group")

        groups_db.add_document_to_group(group_id, doc_id, role="synthesis")

        members = groups_db.get_group_members(group_id)
        assert members[0]["role"] == "synthesis"

    def test_add_duplicate_document(self, isolate_test_database):
        """Test adding the same document twice returns False."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        doc_id = save_document(
            title="Test Document",
            content="Test content",
            project="test",
        )
        group_id = groups_db.create_group(name="Test Group")

        result1 = groups_db.add_document_to_group(group_id, doc_id)
        result2 = groups_db.add_document_to_group(group_id, doc_id)

        assert result1 is True
        assert result2 is False

    def test_remove_document_from_group(self, isolate_test_database):
        """Test removing a document from a group."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        doc_id = save_document(
            title="Test Document",
            content="Test content",
            project="test",
        )
        group_id = groups_db.create_group(name="Test Group")

        groups_db.add_document_to_group(group_id, doc_id)
        result = groups_db.remove_document_from_group(group_id, doc_id)

        assert result is True
        members = groups_db.get_group_members(group_id)
        assert len(members) == 0

    def test_remove_nonexistent_membership(self, isolate_test_database):
        """Test removing a document that isn't in the group."""
        from emdx.database import groups as groups_db

        group_id = groups_db.create_group(name="Test Group")
        result = groups_db.remove_document_from_group(group_id, 99999)

        assert result is False

    def test_get_document_groups(self, isolate_test_database):
        """Test getting all groups a document belongs to."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        doc_id = save_document(
            title="Test Document",
            content="Test content",
            project="test",
        )

        group1_id = groups_db.create_group(name="Group 1")
        group2_id = groups_db.create_group(name="Group 2")
        group3_id = groups_db.create_group(name="Group 3")

        groups_db.add_document_to_group(group1_id, doc_id, role="primary")
        groups_db.add_document_to_group(group2_id, doc_id, role="exploration")

        doc_groups = groups_db.get_document_groups(doc_id)
        assert len(doc_groups) == 2

        group_ids = {g["id"] for g in doc_groups}
        assert group1_id in group_ids
        assert group2_id in group_ids
        assert group3_id not in group_ids


class TestGroupMetrics:
    """Test group metrics tracking."""

    def test_doc_count_updates_on_add(self, isolate_test_database):
        """Test that doc_count updates when adding documents."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        group_id = groups_db.create_group(name="Test Group")

        doc1_id = save_document(title="Doc 1", content="Content", project="test")
        doc2_id = save_document(title="Doc 2", content="Content", project="test")

        groups_db.add_document_to_group(group_id, doc1_id)
        group = groups_db.get_group(group_id)
        assert group["doc_count"] == 1

        groups_db.add_document_to_group(group_id, doc2_id)
        group = groups_db.get_group(group_id)
        assert group["doc_count"] == 2

    def test_doc_count_updates_on_remove(self, isolate_test_database):
        """Test that doc_count updates when removing documents."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        group_id = groups_db.create_group(name="Test Group")

        doc1_id = save_document(title="Doc 1", content="Content", project="test")
        doc2_id = save_document(title="Doc 2", content="Content", project="test")

        groups_db.add_document_to_group(group_id, doc1_id)
        groups_db.add_document_to_group(group_id, doc2_id)

        groups_db.remove_document_from_group(group_id, doc1_id)
        group = groups_db.get_group(group_id)
        assert group["doc_count"] == 1

    def test_token_and_cost_metrics_from_workflow_sources(self, isolate_test_database):
        """Test that total_tokens and total_cost_usd are calculated from document sources."""
        from emdx.database import groups as groups_db
        from emdx.database.connection import db_connection
        from emdx.models.documents import save_document

        # Create documents
        doc1_id = save_document(title="Doc 1", content="Content", project="test")
        doc2_id = save_document(title="Doc 2", content="Content", project="test")
        doc3_id = save_document(title="Doc 3 (no source)", content="Content", project="test")

        # Create workflow infrastructure directly in db for testing
        with db_connection.get_connection() as conn:
            # Create workflow first (required for workflow_runs)
            cursor = conn.execute(
                """INSERT INTO workflows (name, display_name, definition_json)
                   VALUES ('test-workflow', 'Test Workflow', '{}')"""
            )
            workflow_id = cursor.lastrowid

            # Create workflow run
            cursor = conn.execute(
                """INSERT INTO workflow_runs (workflow_id, status)
                   VALUES (?, 'completed')""",
                (workflow_id,),
            )
            workflow_run_id = cursor.lastrowid

            # Create stage run
            cursor = conn.execute(
                """INSERT INTO workflow_stage_runs (workflow_run_id, stage_name, mode, status)
                   VALUES (?, 'test-stage', 'single', 'completed')""",
                (workflow_run_id,),
            )
            stage_run_id = cursor.lastrowid

            # Create individual runs with tokens and cost
            cursor = conn.execute(
                """INSERT INTO workflow_individual_runs
                   (stage_run_id, run_number, status, output_doc_id, tokens_used, cost_usd)
                   VALUES (?, 1, 'completed', ?, 100, 0.005)""",
                (stage_run_id, doc1_id),
            )
            individual_run1_id = cursor.lastrowid

            cursor = conn.execute(
                """INSERT INTO workflow_individual_runs
                   (stage_run_id, run_number, status, output_doc_id, tokens_used, cost_usd)
                   VALUES (?, 2, 'completed', ?, 250, 0.012)""",
                (stage_run_id, doc2_id),
            )
            individual_run2_id = cursor.lastrowid

            # Create document sources linking documents to individual runs
            conn.execute(
                """INSERT INTO document_sources
                   (document_id, workflow_run_id, workflow_individual_run_id, source_type)
                   VALUES (?, ?, ?, 'individual_output')""",
                (doc1_id, workflow_run_id, individual_run1_id),
            )
            conn.execute(
                """INSERT INTO document_sources
                   (document_id, workflow_run_id, workflow_individual_run_id, source_type)
                   VALUES (?, ?, ?, 'individual_output')""",
                (doc2_id, workflow_run_id, individual_run2_id),
            )
            conn.commit()

        # Create a group and add documents
        group_id = groups_db.create_group(name="Test Group")
        groups_db.add_document_to_group(group_id, doc1_id)
        groups_db.add_document_to_group(group_id, doc2_id)
        groups_db.add_document_to_group(group_id, doc3_id)  # No workflow source

        # Verify metrics
        group = groups_db.get_group(group_id)
        assert group["doc_count"] == 3
        # Only doc1 and doc2 have workflow sources, so:
        # total_tokens = 100 + 250 = 350
        # total_cost_usd = 0.005 + 0.012 = 0.017
        assert group["total_tokens"] == 350
        assert abs(group["total_cost_usd"] - 0.017) < 0.0001

    def test_metrics_zero_when_no_workflow_sources(self, isolate_test_database):
        """Test that metrics are 0 when documents have no workflow sources."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        # Create document without any workflow source
        doc_id = save_document(title="Manual Doc", content="Content", project="test")

        # Create group and add document
        group_id = groups_db.create_group(name="Test Group")
        groups_db.add_document_to_group(group_id, doc_id)

        # Verify metrics are 0
        group = groups_db.get_group(group_id)
        assert group["doc_count"] == 1
        assert group["total_tokens"] == 0
        assert group["total_cost_usd"] == 0.0


class TestGetAllGroupedDocumentIds:
    """Test getting all grouped document IDs."""

    def test_get_all_grouped_document_ids(self, isolate_test_database):
        """Test getting all document IDs that belong to groups."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        # Create some documents
        doc1_id = save_document(title="Grouped 1", content="Content", project="test")
        doc2_id = save_document(title="Grouped 2", content="Content", project="test")
        doc3_id = save_document(title="Ungrouped", content="Content", project="test")

        # Create groups and add some documents
        group1_id = groups_db.create_group(name="Group 1")
        group2_id = groups_db.create_group(name="Group 2")

        groups_db.add_document_to_group(group1_id, doc1_id)
        groups_db.add_document_to_group(group2_id, doc2_id)

        grouped_ids = groups_db.get_all_grouped_document_ids()

        assert doc1_id in grouped_ids
        assert doc2_id in grouped_ids
        assert doc3_id not in grouped_ids

    def test_document_in_multiple_groups(self, isolate_test_database):
        """Test that a document in multiple groups only appears once."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        doc_id = save_document(title="Multi-group Doc", content="Content", project="test")

        group1_id = groups_db.create_group(name="Group 1")
        group2_id = groups_db.create_group(name="Group 2")

        groups_db.add_document_to_group(group1_id, doc_id)
        groups_db.add_document_to_group(group2_id, doc_id)

        grouped_ids = groups_db.get_all_grouped_document_ids()

        # Should only appear once even though in two groups
        assert doc_id in grouped_ids
        assert len([x for x in grouped_ids if x == doc_id]) == 1


class TestGroupRoles:
    """Test different document roles within groups."""

    def test_all_role_types(self, isolate_test_database):
        """Test that all role types can be assigned."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        group_id = groups_db.create_group(name="Role Test Group")
        roles = ["primary", "exploration", "synthesis", "variant", "member"]

        for i, role in enumerate(roles):
            doc_id = save_document(
                title=f"Doc with {role} role",
                content="Content",
                project="test",
            )
            result = groups_db.add_document_to_group(group_id, doc_id, role=role)
            assert result is True

        members = groups_db.get_group_members(group_id)
        assigned_roles = {m["role"] for m in members}
        assert assigned_roles == set(roles)

    def test_multiple_documents_same_role(self, isolate_test_database):
        """Test that multiple documents can have the same role."""
        from emdx.database import groups as groups_db
        from emdx.models.documents import save_document

        group_id = groups_db.create_group(name="Exploration Group")

        doc1_id = save_document(title="Exploration 1", content="Content", project="test")
        doc2_id = save_document(title="Exploration 2", content="Content", project="test")
        doc3_id = save_document(title="Exploration 3", content="Content", project="test")

        groups_db.add_document_to_group(group_id, doc1_id, role="exploration")
        groups_db.add_document_to_group(group_id, doc2_id, role="exploration")
        groups_db.add_document_to_group(group_id, doc3_id, role="exploration")

        members = groups_db.get_group_members(group_id)
        assert len(members) == 3
        assert all(m["role"] == "exploration" for m in members)
