"""Obsidian vault export service.

Exports emdx documents as Obsidian-compatible markdown files with:
  - YAML frontmatter (title, tags, emdx_id, project, dates)
  - [[wikilinks]] from document_links for graph view
  - Task checklists grouped by epic
  - Incremental export via SHA256 manifest
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from ..database.document_links import get_links_for_documents_batch
from ..database.documents import get_documents_for_export
from ..database.types import DocumentLinkDetail, DocumentRow
from ..models.tags import get_tags_for_documents
from ..models.tasks import list_epics, list_tasks
from ..models.types import EpicTaskDict, TaskDict

logger = logging.getLogger(__name__)

MANIFEST_FILE = ".emdx-export.json"


@dataclass
class ExportResult:
    """Result of an Obsidian export operation."""

    output_dir: Path
    docs_exported: int = 0
    docs_skipped: int = 0
    task_files_exported: int = 0
    errors: list[str] = field(default_factory=list)


def _slugify(text: str) -> str:
    """Convert text to a filename-safe slug."""
    slug = text.strip()
    # Replace path-unsafe chars but keep spaces (Obsidian handles them)
    slug = re.sub(r'[<>:"/\\|?*]', "", slug)
    # Collapse whitespace
    slug = re.sub(r"\s+", " ", slug)
    return slug[:120].strip()


def _doc_filename(doc: DocumentRow) -> str:
    """Generate a filename for a document."""
    slug = _slugify(doc["title"])
    if not slug:
        slug = f"untitled-{doc['id']}"
    return f"{slug}.md"


def _content_hash(content: str) -> str:
    """SHA256 hash of content for incremental export."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _format_datetime(dt: datetime | None) -> str | None:
    """Format a datetime for YAML frontmatter."""
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _render_frontmatter(
    doc: DocumentRow,
    tags: list[str],
) -> str:
    """Render YAML frontmatter for a document."""
    fm: dict[str, Any] = {
        "title": doc["title"],
        "emdx_id": doc["id"],
    }
    if tags:
        fm["tags"] = tags
    if doc["project"]:
        fm["aliases"] = [f"emdx-{doc['id']}"]
        fm["project"] = doc["project"]
    created = _format_datetime(doc["created_at"])
    if created:
        fm["created"] = created
    updated = _format_datetime(doc["updated_at"])
    if updated:
        fm["updated"] = updated

    # Build YAML manually to avoid adding a pyyaml dependency
    lines = ["---"]
    for key, value in fm.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {item}")
        elif isinstance(value, int):
            lines.append(f"{key}: {value}")
        elif value is not None:
            # Quote strings that contain YAML-special chars
            if any(c in str(value) for c in ":{}[]#&*!|>'\"%@`"):
                lines.append(f'{key}: "{value}"')
            else:
                lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def _render_related_section(
    doc_id: int,
    links: list[DocumentLinkDetail],
    filename_map: dict[int, str],
) -> str:
    """Render a Related section with [[wikilinks]]."""
    if not links:
        return ""

    seen: set[int] = set()
    wiki_links: list[str] = []
    for link in links:
        # Determine the "other" document
        if link["source_doc_id"] == doc_id:
            other_id = link["target_doc_id"]
            other_title = link["target_title"]
        else:
            other_id = link["source_doc_id"]
            other_title = link["source_title"]

        if other_id in seen:
            continue
        seen.add(other_id)

        # Use filename (without .md) as wikilink target
        fname = filename_map.get(other_id)
        if fname:
            link_target = fname.removesuffix(".md")
            wiki_links.append(f"- [[{link_target}|{other_title}]]")

    if not wiki_links:
        return ""

    return "\n## Related\n\n" + "\n".join(wiki_links) + "\n"


def _render_document(
    doc: DocumentRow,
    tags: list[str],
    links: list[DocumentLinkDetail],
    filename_map: dict[int, str],
) -> str:
    """Render a full Obsidian markdown file for a document."""
    parts = [_render_frontmatter(doc, tags)]
    parts.append("")  # blank line after frontmatter

    content = doc["content"]
    if content:
        parts.append(content.rstrip())

    related = _render_related_section(doc["id"], links, filename_map)
    if related:
        parts.append("")
        parts.append(related)

    return "\n".join(parts) + "\n"


def _render_task_line(task: TaskDict) -> str:
    """Render a single task as a markdown checklist item."""
    done = task["status"] in ("done", "wontdo")
    check = "x" if done else " "
    line = f"- [{check}] {task['title']}"
    if task["status"] == "active":
        line += " *(in progress)*"
    elif task["status"] == "blocked":
        line += " *(blocked)*"
    elif task["status"] == "wontdo":
        line += " ~~(won't do)~~"
    desc_raw = task.get("description")
    if desc_raw:
        # Add first line of description as indented text
        desc = desc_raw.split("\n")[0][:120]
        line += f"\n  {desc}"
    return line


def _render_epic_file(epic: EpicTaskDict, children: list[TaskDict]) -> str:
    """Render an epic + its children as a task checklist file."""
    parts: list[str] = []
    # Frontmatter
    parts.append("---")
    parts.append(f'title: "{epic["title"]}"')
    parts.append(f"emdx_task_id: {epic['id']}")
    if epic.get("epic_key"):
        parts.append(f"category: {epic['epic_key']}")
    parts.append(f"status: {epic['status']}")
    parts.append("---")
    parts.append("")

    # Epic description
    epic_desc = epic.get("description")
    if epic_desc:
        parts.append(epic_desc)
        parts.append("")

    # Progress
    done = sum(1 for t in children if t["status"] in ("done", "wontdo"))
    total = len(children)
    if total > 0:
        parts.append(f"**Progress:** {done}/{total} tasks")
        parts.append("")

    # Task checklist
    for task in children:
        parts.append(_render_task_line(task))

    parts.append("")
    return "\n".join(parts)


def _load_manifest(output_dir: Path) -> dict[str, str]:
    """Load the export manifest (filename -> content hash)."""
    manifest_path = output_dir / MANIFEST_FILE
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "files" in data:
                return cast(dict[str, str], data["files"])
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def _save_manifest(output_dir: Path, files: dict[str, str]) -> None:
    """Save the export manifest."""
    manifest_path = output_dir / MANIFEST_FILE
    data = {
        "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "version": 1,
        "files": files,
    }
    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def export_obsidian(
    output_dir: Path,
    project: str | None = None,
    tags: list[str] | None = None,
    incremental: bool = False,
    include_tasks: bool = True,
    organize_by_project: bool = False,
    dry_run: bool = False,
) -> ExportResult:
    """Export emdx documents as an Obsidian vault.

    Args:
        output_dir: Directory to write markdown files into.
        project: Filter to a single project.
        tags: Filter by tags (AND — must have all).
        incremental: Only re-export changed docs (via SHA256 manifest).
        include_tasks: Whether to export task/epic files.
        organize_by_project: Create subdirectories per project.
        dry_run: Preview without writing files.

    Returns:
        ExportResult with counts and errors.
    """
    result = ExportResult(output_dir=output_dir)

    # ── Fetch documents ──────────────────────────────────────────────
    docs = get_documents_for_export(project=project, tags=tags)
    if not docs:
        return result

    doc_ids = [d["id"] for d in docs]

    # Batch-fetch tags and links (avoids N+1)
    all_tags = get_tags_for_documents(doc_ids)
    all_links = get_links_for_documents_batch(doc_ids)

    # Build filename map (id -> filename) for wikilinks
    filename_map: dict[int, str] = {}
    # Track filenames to handle collisions
    used_filenames: dict[str, int] = {}
    for doc in docs:
        fname = _doc_filename(doc)
        lower = fname.lower()
        if lower in used_filenames:
            # Collision — append ID
            fname = f"{fname.removesuffix('.md')}-{doc['id']}.md"
        used_filenames[fname.lower()] = doc["id"]
        filename_map[doc["id"]] = fname

    # Load manifest for incremental mode
    manifest = _load_manifest(output_dir) if incremental else {}
    new_manifest: dict[str, str] = {}

    # ── Render and write documents ───────────────────────────────────
    for doc in docs:
        doc_tags = all_tags.get(doc["id"], [])
        doc_links = all_links.get(doc["id"], [])
        fname = filename_map[doc["id"]]

        rendered = _render_document(doc, doc_tags, doc_links, filename_map)
        content_sha = _content_hash(rendered)
        new_manifest[fname] = content_sha

        # Skip unchanged files in incremental mode
        if incremental and manifest.get(fname) == content_sha:
            result.docs_skipped += 1
            continue

        if dry_run:
            result.docs_exported += 1
            continue

        # Determine output path
        if organize_by_project and doc["project"]:
            subdir = output_dir / _slugify(doc["project"])
        else:
            subdir = output_dir

        try:
            subdir.mkdir(parents=True, exist_ok=True)
            file_path = subdir / fname
            file_path.write_text(rendered, encoding="utf-8")
            result.docs_exported += 1
        except OSError as e:
            result.errors.append(f"{fname}: {e}")
            logger.warning("Failed to write %s: %s", fname, e)

    # ── Export tasks ─────────────────────────────────────────────────
    if include_tasks:
        tasks_dir = output_dir / "tasks"

        # Export epics with their children
        epics = list_epics(status=["open", "active", "blocked"])
        for epic in epics:
            children = list_tasks(parent_task_id=epic["id"])
            if not children and epic["status"] != "active":
                continue

            cat = epic.get("epic_key") or "MISC"
            epic_slug = _slugify(epic["title"])
            fname = f"{cat}--{epic_slug}.md"
            rendered = _render_epic_file(epic, children)
            new_manifest[f"tasks/{fname}"] = _content_hash(rendered)

            if dry_run:
                result.task_files_exported += 1
                continue

            try:
                tasks_dir.mkdir(parents=True, exist_ok=True)
                (tasks_dir / fname).write_text(rendered, encoding="utf-8")
                result.task_files_exported += 1
            except OSError as e:
                result.errors.append(f"tasks/{fname}: {e}")

        # Standalone tasks (no epic)
        # Standalone tasks (no parent epic)
        orphan_tasks = [
            t
            for t in list_tasks(status=["open", "active", "blocked"])
            if t["parent_task_id"] is None and t["type"] != "epic"
        ]
        if orphan_tasks:
            lines = ["---", "title: Standalone Tasks", "---", ""]
            for task in orphan_tasks:
                lines.append(_render_task_line(task))
            lines.append("")
            rendered = "\n".join(lines)
            new_manifest["tasks/_standalone-tasks.md"] = _content_hash(rendered)

            if not dry_run:
                try:
                    tasks_dir.mkdir(parents=True, exist_ok=True)
                    (tasks_dir / "_standalone-tasks.md").write_text(rendered, encoding="utf-8")
                    result.task_files_exported += 1
                except OSError as e:
                    result.errors.append(f"tasks/_standalone-tasks.md: {e}")
            else:
                result.task_files_exported += 1

    # ── Save manifest ────────────────────────────────────────────────
    if not dry_run:
        _save_manifest(output_dir, new_manifest)

    return result
