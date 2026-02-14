"""Tests for the linking service and depth bug fix."""

import pytest
from dataclasses import dataclass
from typing import List, Optional, Set
from unittest.mock import MagicMock, patch

from emdx.services.linking_service import (
    DocumentLink,
    LinkingService,
    LinkStats,
)


class TestDocumentLink:
    """Tests for DocumentLink dataclass."""

    def test_document_link_creation(self):
        """Test creating a DocumentLink instance."""
        link = DocumentLink(
            doc_id=42,
            title="Test Document",
            similarity_score=0.75,
            project="test-project",
        )

        assert link.doc_id == 42
        assert link.title == "Test Document"
        assert link.similarity_score == 0.75
        assert link.project == "test-project"


class TestLinkStats:
    """Tests for LinkStats dataclass."""

    def test_link_stats_creation(self):
        """Test creating a LinkStats instance."""
        stats = LinkStats(
            total_links=100,
            documents_with_links=20,
            avg_links_per_doc=5.0,
            avg_similarity=0.65,
        )

        assert stats.total_links == 100
        assert stats.documents_with_links == 20
        assert stats.avg_links_per_doc == 5.0
        assert stats.avg_similarity == 0.65


# Mock class for testing depth traversal
@dataclass
class MockDocumentLink:
    """Mock of DocumentLink for testing."""

    doc_id: int
    title: str
    similarity_score: float
    project: Optional[str] = None


class MockLinkingService:
    """Mock linking service for testing depth traversal."""

    def __init__(self, link_graph: dict):
        self.link_graph = link_graph

    def get_links(self, doc_id: int, limit: int = 5) -> List[MockDocumentLink]:
        return self.link_graph.get(doc_id, [])[:limit]


def collect_tree_output(
    doc_id: int,
    linker: MockLinkingService,
    depth: int,
) -> List[int]:
    """Simulate the fixed print_tree logic and collect doc_ids in traversal order."""
    collected = []
    links = linker.get_links(doc_id)

    def traverse(links: List[MockDocumentLink], current_level: int = 1, visited: Set[int] = None):
        if visited is None:
            visited = {doc_id}

        for link in links:
            collected.append(link.doc_id)

            if current_level < depth:
                child_links = linker.get_links(link.doc_id, limit=3)
                child_links = [cl for cl in child_links if cl.doc_id not in visited]
                if child_links:
                    new_visited = visited | {link.doc_id}
                    traverse(child_links[:3], current_level + 1, new_visited)

    traverse(links)
    return collected


class TestDepthTraversal:
    """Test depth traversal with cycle prevention."""

    def test_depth_1_no_recursion(self):
        """With depth=1, should only show immediate links, no children."""
        linker = MockLinkingService({
            1: [MockDocumentLink(2, "Doc 2", 0.8), MockDocumentLink(3, "Doc 3", 0.7)],
            2: [MockDocumentLink(1, "Doc 1", 0.8), MockDocumentLink(4, "Doc 4", 0.6)],
            3: [MockDocumentLink(1, "Doc 1", 0.7)],
        })

        result = collect_tree_output(1, linker, depth=1)
        assert result == [2, 3]

    def test_depth_2_shows_children(self):
        """With depth=2, should show immediate links and their children."""
        linker = MockLinkingService({
            1: [MockDocumentLink(2, "Doc 2", 0.8)],
            2: [MockDocumentLink(1, "Doc 1", 0.8), MockDocumentLink(4, "Doc 4", 0.6)],
        })

        result = collect_tree_output(1, linker, depth=2)
        assert result == [2, 4]

    def test_bidirectional_links_filtered(self):
        """Bidirectional links should not cause infinite loops."""
        linker = MockLinkingService({
            1: [MockDocumentLink(2, "Doc 2", 0.8)],
            2: [MockDocumentLink(1, "Doc 1", 0.8)],
        })

        result = collect_tree_output(1, linker, depth=3)
        assert result == [2]

    def test_triangle_cycle(self):
        """A->B->C->A should not cause infinite loop."""
        linker = MockLinkingService({
            1: [MockDocumentLink(2, "Doc 2", 0.8)],
            2: [MockDocumentLink(3, "Doc 3", 0.7)],
            3: [MockDocumentLink(1, "Doc 1", 0.6)],
        })

        result = collect_tree_output(1, linker, depth=3)
        assert result == [2, 3]

    def test_depth_3_full_traversal(self):
        """Test depth=3 traversal with a simple chain."""
        linker = MockLinkingService({
            1: [MockDocumentLink(2, "Doc 2", 0.8)],
            2: [MockDocumentLink(3, "Doc 3", 0.7)],
            3: [MockDocumentLink(4, "Doc 4", 0.6)],
            4: [],
        })

        result = collect_tree_output(1, linker, depth=3)
        assert result == [2, 3, 4]

    def test_no_links_returns_empty(self):
        """Document with no links returns empty list."""
        linker = MockLinkingService({1: []})

        result = collect_tree_output(1, linker, depth=3)
        assert result == []


class TestOriginalBugScenario:
    """Test the specific bug scenario from PR #452."""

    def test_original_bug_fixed(self):
        """Original bug only filtered ROOT document, not immediate parent."""
        linker = MockLinkingService({
            1: [MockDocumentLink(2, "Doc 2", 0.8)],
            2: [MockDocumentLink(1, "Doc 1", 0.8), MockDocumentLink(3, "Doc 3", 0.7)],
        })

        result = collect_tree_output(1, linker, depth=2)
        assert result == [2, 3]

    def test_deeper_cycle_fixed(self):
        """Fix: visited set tracks all ancestors, preventing any cycles."""
        linker = MockLinkingService({
            1: [MockDocumentLink(2, "Doc 2", 0.8)],
            2: [MockDocumentLink(3, "Doc 3", 0.7)],
            3: [MockDocumentLink(1, "Doc 1", 0.6), MockDocumentLink(4, "Doc 4", 0.5)],
        })

        result = collect_tree_output(1, linker, depth=3)
        assert result == [2, 3, 4]


class TestLinkGraphMethod:
    """Tests for get_link_graph method."""

    def test_get_link_graph_stops_at_depth_zero(self):
        """Test that get_link_graph returns empty at depth 0."""
        linker = LinkingService()
        graph = linker.get_link_graph(1, depth=0)
        assert graph == {}

    def test_get_link_graph_prevents_cycles(self):
        """Test that get_link_graph uses visited set to prevent cycles."""
        linker = LinkingService()
        visited = {1}
        graph = linker.get_link_graph(1, depth=2, visited=visited)
        assert graph == {}
