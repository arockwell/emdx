"""First-run onboarding — seed tutorial content for new users.

Creates welcome documents and getting-started tasks so the TUI
isn't a blank screen on first launch.  The schema_flags table
tracks whether seeding has already run, preventing re-seeding
if a user later deletes all their content.
"""

from __future__ import annotations

import logging
import textwrap

from emdx.database import db

logger = logging.getLogger(__name__)


def _already_seeded() -> bool:
    """Check if onboarding has already been seeded."""
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT 1 FROM schema_flags WHERE key = 'onboarding_seeded'")
        return cursor.fetchone() is not None


def _set_seeded() -> None:
    """Record that onboarding has been seeded."""
    with db.get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO schema_flags (key, value) VALUES ('onboarding_seeded', '1')"
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Tutorial content
# ---------------------------------------------------------------------------

_WELCOME_DOC = textwrap.dedent("""\
    # Welcome to emdx

    emdx is a knowledge base that **AI agents populate and humans curate**.

    ## Quick command reference

    | Command | What it does |
    |---------|-------------|
    | `emdx save file.md` | Save a markdown file |
    | `echo "note" \\| emdx save --title "Note"` | Save text from stdin |
    | `emdx find "query"` | Full-text search |
    | `emdx view <id>` | View a document |
    | `emdx tag <id> notes` | Tag a document |
    | `emdx task ready` | Show tasks ready to work on |

    ## TUI navigation

    - **j / k** — move up and down
    - **Enter** or **f** — open the selected document in full view
    - **Escape** — go back
    - **Tab** — switch between Docs and Tasks views
    - **Ctrl+K** — open the command palette
    - **q** — quit

    Head over to the **Tasks** tab to find your Getting Started checklist!
""")

_SHORTCUTS_DOC = textwrap.dedent("""\
    # Keyboard Shortcuts

    ## Document Browser

    | Key | Action |
    |-----|--------|
    | j / k | Move cursor down / up |
    | Enter / f | Open document |
    | Escape | Close document |
    | r | Refresh list |
    | / | Filter documents |
    | z | Toggle zoom (hide sidebar) |

    ## Task Browser

    | Key | Action |
    |-----|--------|
    | j / k | Move cursor down / up |
    | d | Mark task done |
    | a | Mark task active |
    | b | Mark task blocked |
    | u | Reopen task |
    | / | Filter tasks |

    ## Global

    | Key | Action |
    |-----|--------|
    | Tab | Switch views (Docs / Tasks) |
    | Ctrl+K | Command palette |
    | q | Quit |
""")

_TASKS: list[tuple[str, str]] = [
    (
        "Navigate the document browser",
        "Use **j** and **k** to move through the document list. "
        "Press **Enter** or **f** to open a document. "
        "Press **Escape** to go back.",
    ),
    (
        "Save your first document",
        'Run `echo "Hello world" | emdx save --title "My First Note"` '
        "in your terminal, then press **r** in the TUI to refresh.",
    ),
    (
        "Search your knowledge base",
        "Press **Ctrl+K** to open the command palette and search "
        "for documents by title or content.",
    ),
    (
        "Tag a document",
        "Run `emdx tag <id> notes` to add a tag to a document. "
        "Use `emdx tag list` to see all tags.",
    ),
    (
        "Clean up this tutorial",
        "When you're done exploring, delete the tutorial docs with "
        "`emdx delete <id>` and mark these tasks done with "
        "`emdx task done <id>`. The tutorial won't come back — "
        "your real knowledge base starts here!",
    ),
]


def maybe_seed_onboarding() -> None:
    """Seed tutorial content on first run.  No-op if already seeded."""
    # Fast path — check flag before importing anything heavy
    try:
        if _already_seeded():
            return
    except Exception:
        # schema_flags table may not exist yet (migration hasn't run)
        logger.debug("schema_flags table not yet available, skipping onboarding check")
        return

    # Check if the database already has content (existing user)
    with db.get_connection() as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM documents WHERE is_deleted = FALSE")
        doc_count = cursor.fetchone()[0]
        if doc_count > 0:
            # Existing user — mark as seeded and skip
            _set_seeded()
            return

    logger.info("First run detected — seeding onboarding content")

    from emdx.database.documents import save_document
    from emdx.models.categories import ensure_category
    from emdx.models.tasks import create_epic, create_task

    # --- Documents ---
    save_document(
        title="Welcome to emdx",
        content=_WELCOME_DOC,
        tags=["tutorial", "onboarding"],
    )
    save_document(
        title="Keyboard Shortcuts",
        content=_SHORTCUTS_DOC,
        tags=["tutorial", "onboarding"],
    )

    # --- Tasks ---
    ensure_category("START")
    epic_id = create_epic(
        name="Getting Started",
        category_key="START",
        description="Tutorial tasks to learn emdx basics",
    )

    for title, description in _TASKS:
        create_task(
            title=title,
            description=description,
            parent_task_id=epic_id,
            epic_key="START",
        )

    _set_seeded()
    logger.info("Onboarding content seeded successfully")
