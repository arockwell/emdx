"""Wiki export service — dump articles as MkDocs site.

Exports wiki articles and entity pages as a MkDocs-ready directory structure:
    output_dir/
        mkdocs.yml
        docs/
            index.md
            articles/
                <topic-slug>.md
            entities/
                <entity-slug>.md
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from ..database import db
from .wiki_entity_service import (
    EntityPage,
    get_entity_detail,
    get_entity_pages,
    render_entity_page,
)

logger = logging.getLogger(__name__)


@dataclass
class ExportedArticle:
    """An article prepared for export."""

    topic_id: int
    topic_slug: str
    topic_label: str
    content: str
    version: int
    generated_at: str
    model: str
    rating: int | None
    member_count: int
    source_titles: list[str] = field(default_factory=list)


@dataclass
class ExportResult:
    """Result of an export operation."""

    output_dir: Path
    articles_exported: int
    entity_pages_exported: int
    mkdocs_yml_generated: bool
    errors: list[str] = field(default_factory=list)


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s-]+", "-", slug)
    return slug[:80].strip("-")


def get_exportable_articles() -> list[ExportedArticle]:
    """Fetch all non-stale wiki articles with metadata.

    Returns articles joined with their topic info, member counts,
    and source document titles.
    """
    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT wa.topic_id, t.topic_slug, t.topic_label, "
            "d.content, wa.version, wa.generated_at, wa.model, wa.rating, "
            "COUNT(DISTINCT m.document_id) as member_count "
            "FROM wiki_articles wa "
            "JOIN documents d ON wa.document_id = d.id "
            "JOIN wiki_topics t ON wa.topic_id = t.id "
            "LEFT JOIN wiki_topic_members m ON t.id = m.topic_id "
            "WHERE d.is_deleted = 0 AND t.status != 'skipped' "
            "GROUP BY wa.id "
            "ORDER BY t.topic_label"
        ).fetchall()

    articles: list[ExportedArticle] = []
    for row in rows:
        article = ExportedArticle(
            topic_id=row[0],
            topic_slug=row[1],
            topic_label=row[2],
            content=row[3] or "",
            version=row[4] or 1,
            generated_at=row[5] or "",
            model=row[6] or "",
            rating=row[7],
            member_count=row[8] or 0,
        )

        # Fetch source titles for this article
        with db.get_connection() as conn:
            source_rows = conn.execute(
                "SELECT d.title FROM wiki_article_sources was "
                "JOIN documents d ON was.document_id = d.id "
                "JOIN wiki_articles wa ON was.article_id = wa.id "
                "WHERE wa.topic_id = ? "
                "ORDER BY d.title",
                (article.topic_id,),
            ).fetchall()
            article.source_titles = [r[0] for r in source_rows if r[0]]

        articles.append(article)

    return articles


def _render_article_md(article: ExportedArticle) -> str:
    """Render an article as markdown with front matter."""
    front_matter = {
        "title": article.topic_label,
        "topic_id": article.topic_id,
        "version": article.version,
        "model": article.model,
        "sources": article.member_count,
    }
    if article.rating:
        front_matter["rating"] = article.rating
    if article.generated_at:
        front_matter["generated_at"] = article.generated_at

    lines: list[str] = []
    lines.append("---")
    lines.append(yaml.dump(front_matter, default_flow_style=False).strip())
    lines.append("---")
    lines.append("")

    # The article content is already markdown with a # heading
    lines.append(article.content)

    # Add source attribution footer
    if article.source_titles:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(f"*Generated from {len(article.source_titles)} source documents*")

    lines.append("")
    return "\n".join(lines)


def _render_entity_md(page: EntityPage) -> str:
    """Render an entity page as markdown with front matter."""
    front_matter = {
        "title": page.entity,
        "entity_type": page.entity_type,
        "tier": page.tier,
        "doc_frequency": page.doc_frequency,
    }

    lines: list[str] = []
    lines.append("---")
    lines.append(yaml.dump(front_matter, default_flow_style=False).strip())
    lines.append("---")
    lines.append("")
    lines.append(render_entity_page(page))
    lines.append("")
    return "\n".join(lines)


def _render_index_md(
    articles: list[ExportedArticle],
    entity_count: int,
) -> str:
    """Render the site index page."""
    lines: list[str] = []
    lines.append("# Knowledge Base Wiki")
    lines.append("")
    lines.append(
        f"Auto-generated wiki with **{len(articles)} articles** "
        f"and **{entity_count} entity pages**."
    )
    lines.append("")

    if articles:
        lines.append("## Articles")
        lines.append("")
        for article in articles:
            rating_str = ""
            if article.rating:
                rating_str = " " + "\u2605" * article.rating + "\u2606" * (5 - article.rating)
            lines.append(
                f"- [{article.topic_label}](articles/{article.topic_slug}.md)"
                f" — {article.member_count} sources{rating_str}"
            )
        lines.append("")

    lines.append("")
    return "\n".join(lines)


def _generate_mkdocs_yml(
    articles: list[ExportedArticle],
    entity_pages: list[EntityPage],
    site_name: str = "Knowledge Base Wiki",
    site_url: str = "",
    repo_url: str = "",
) -> str:
    """Generate mkdocs.yml configuration."""
    # Build nav tree
    nav: list[dict[str, object]] = []

    # Home
    nav.append({"Home": "index.md"})

    # Articles section
    if articles:
        article_nav: list[dict[str, str]] = [
            {a.topic_label: f"articles/{a.topic_slug}.md"} for a in articles
        ]
        nav.append({"Articles": article_nav})

    # Entity glossary section
    if entity_pages:
        entity_nav: list[dict[str, str]] = [
            {p.entity: f"entities/{_slugify(p.entity)}.md"} for p in entity_pages
        ]
        nav.append({"Glossary": entity_nav})

    config: dict[str, object] = {
        "site_name": site_name,
    }
    if site_url:
        config["site_url"] = site_url
    if repo_url:
        config["repo_url"] = repo_url
        config["repo_name"] = repo_url.rstrip("/").rsplit("/", 1)[-1]

    config.update(
        {
            "theme": {
                "name": "material",
                "palette": [
                    {
                        "scheme": "default",
                        "primary": "indigo",
                        "accent": "indigo",
                        "toggle": {
                            "icon": "material/brightness-7",
                            "name": "Switch to dark mode",
                        },
                    },
                    {
                        "scheme": "slate",
                        "primary": "indigo",
                        "accent": "indigo",
                        "toggle": {
                            "icon": "material/brightness-4",
                            "name": "Switch to light mode",
                        },
                    },
                ],
                "features": [
                    "navigation.instant",
                    "navigation.tabs",
                    "navigation.sections",
                    "navigation.expand",
                    "search.suggest",
                    "search.highlight",
                    "content.code.copy",
                ],
            },
            "plugins": ["search"],
            "nav": nav,
            "markdown_extensions": [
                "toc",
                "tables",
                "fenced_code",
                {"toc": {"permalink": True}},
            ],
        }
    )

    result: str = yaml.dump(config, default_flow_style=False, sort_keys=False)
    return result


def export_mkdocs(
    output_dir: Path,
    site_name: str = "Knowledge Base Wiki",
    site_url: str = "",
    repo_url: str = "",
) -> ExportResult:
    """Export wiki articles and entity pages as a MkDocs site.

    Creates:
        output_dir/
            mkdocs.yml
            docs/
                index.md
                articles/<slug>.md
                entities/<slug>.md

    Args:
        output_dir: Directory to write the MkDocs site to.
        site_name: Site name for mkdocs.yml.
        site_url: Base URL for the published site (e.g. https://you.github.io/wiki/).
        repo_url: Repository URL for "edit this page" links.

    Returns:
        ExportResult with counts and any errors.
    """
    result = ExportResult(
        output_dir=output_dir,
        articles_exported=0,
        entity_pages_exported=0,
        mkdocs_yml_generated=False,
    )

    # Create directory structure
    docs_dir = output_dir / "docs"
    articles_dir = docs_dir / "articles"
    entities_dir = docs_dir / "entities"

    articles_dir.mkdir(parents=True, exist_ok=True)
    entities_dir.mkdir(parents=True, exist_ok=True)

    # Export articles
    articles = get_exportable_articles()
    for article in articles:
        try:
            md = _render_article_md(article)
            path = articles_dir / f"{article.topic_slug}.md"
            path.write_text(md, encoding="utf-8")
            result.articles_exported += 1
        except Exception as e:
            result.errors.append(f"Article {article.topic_slug}: {e}")
            logger.warning("Failed to export article %s: %s", article.topic_slug, e)

    # Export entity pages (Tier A only — high-signal entities in 5+ docs)
    entity_pages: list[EntityPage] = get_entity_pages(tier="A")

    for page in entity_pages:
        try:
            detail = get_entity_detail(page.entity)
            if not detail:
                continue
            md = _render_entity_md(detail)
            slug = _slugify(page.entity)
            path = entities_dir / f"{slug}.md"
            path.write_text(md, encoding="utf-8")
            result.entity_pages_exported += 1
        except Exception as e:
            result.errors.append(f"Entity {page.entity}: {e}")
            logger.warning("Failed to export entity %s: %s", page.entity, e)

    # Generate index
    index_md = _render_index_md(articles, len(entity_pages))
    (docs_dir / "index.md").write_text(index_md, encoding="utf-8")

    # Generate mkdocs.yml
    mkdocs_yml = _generate_mkdocs_yml(
        articles, entity_pages, site_name, site_url=site_url, repo_url=repo_url
    )
    (output_dir / "mkdocs.yml").write_text(mkdocs_yml, encoding="utf-8")
    result.mkdocs_yml_generated = True

    return result
