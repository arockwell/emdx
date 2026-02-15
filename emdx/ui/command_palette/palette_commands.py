"""
Command registry for the command palette.

Manages available commands that can be invoked from the palette.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum

logger = logging.getLogger(__name__)

class CommandContext(Enum):
    """Contexts where commands are available."""

    GLOBAL = "global"  # Available everywhere
    DOCUMENT_BROWSER = "document_browser"
    ACTIVITY = "activity"

@dataclass
class PaletteCommand:
    """A command that can be executed from the palette."""

    id: str  # Unique identifier, e.g., "nav.activity"
    name: str  # Display name: "Go to Activity"
    description: str  # What it does
    keywords: list[str] = field(default_factory=list)  # For fuzzy matching
    action: Callable | None = None  # Function to execute (app) -> None
    context: CommandContext = CommandContext.GLOBAL  # Where available
    shortcut: str | None = None  # Keyboard shortcut hint
    category: str = "General"  # For grouping in UI

class CommandRegistry:
    """Registry of available commands for the palette."""

    def __init__(self):
        self._commands: dict[str, PaletteCommand] = {}
        self._register_defaults()

    def register(self, command: PaletteCommand) -> None:
        """Register a command."""
        self._commands[command.id] = command
        logger.debug(f"Registered command: {command.id}")

    def unregister(self, command_id: str) -> bool:
        """Unregister a command. Returns True if found."""
        if command_id in self._commands:
            del self._commands[command_id]
            return True
        return False

    def get(self, command_id: str) -> PaletteCommand | None:
        """Get a command by ID."""
        return self._commands.get(command_id)

    def get_all(self, context: CommandContext | None = None) -> list[PaletteCommand]:
        """Get all commands, optionally filtered by context."""
        commands = list(self._commands.values())
        if context:
            commands = [
                c for c in commands if c.context == CommandContext.GLOBAL or c.context == context
            ]
        return sorted(commands, key=lambda c: (c.category, c.name))

    def search(
        self,
        query: str,
        context: CommandContext | None = None,
        limit: int = 10,
        threshold: float = 0.3,
    ) -> list[PaletteCommand]:
        """
        Fuzzy search commands by name and keywords.

        Args:
            query: Search query
            context: Optional context filter
            limit: Max results
            threshold: Minimum match score (0-1)

        Returns:
            List of matching commands, sorted by relevance
        """
        if not query.strip():
            return self.get_all(context)[:limit]

        query_lower = query.lower().strip()
        scored: list[tuple[float, PaletteCommand]] = []

        for cmd in self._commands.values():
            # Filter by context
            if context and cmd.context != CommandContext.GLOBAL and cmd.context != context:
                continue

            # Calculate match score
            name_lower = cmd.name.lower()

            # Check exact substring match (high score)
            if query_lower in name_lower:
                score = 0.9 + (len(query_lower) / len(name_lower)) * 0.1
            else:
                # Fuzzy match on name
                name_score = SequenceMatcher(None, query_lower, name_lower).ratio()

                # Fuzzy match on keywords
                keyword_scores = [
                    SequenceMatcher(None, query_lower, kw.lower()).ratio()
                    for kw in cmd.keywords
                ]
                keyword_score = max(keyword_scores) if keyword_scores else 0.0

                # Check if query words appear in keywords
                query_words = query_lower.split()
                word_match_bonus = 0.0
                for qw in query_words:
                    for kw in cmd.keywords:
                        if qw in kw.lower():
                            word_match_bonus += 0.15

                score = max(name_score, keyword_score) + word_match_bonus

            if score >= threshold:
                scored.append((score, cmd))

        # Sort by score descending
        scored.sort(key=lambda x: -x[0])

        return [cmd for _, cmd in scored[:limit]]

    def _register_defaults(self) -> None:
        """Register default commands."""
        # Navigation commands
        self.register(
            PaletteCommand(
                id="nav.activity",
                name="Go to Activity",
                description="Switch to Activity view (Mission Control)",
                keywords=["home", "dashboard", "activity", "mission", "main"],
                context=CommandContext.GLOBAL,
                shortcut="1",
                category="Navigation",
            )
        )

        self.register(
            PaletteCommand(
                id="nav.cascade",
                name="Go to Cascade",
                description="Switch to Cascade browser",
                keywords=["cascade", "pipeline", "stages", "flow"],
                context=CommandContext.GLOBAL,
                shortcut="2",
                category="Navigation",
            )
        )

        self.register(
            PaletteCommand(
                id="nav.search",
                name="Go to Search",
                description="Switch to Search screen",
                keywords=["search", "find", "query", "lookup"],
                context=CommandContext.GLOBAL,
                shortcut="3",
                category="Navigation",
            )
        )

        self.register(
            PaletteCommand(
                id="nav.documents",
                name="Go to Documents",
                description="Switch to Document browser",
                keywords=["document", "docs", "knowledge", "notes", "browse"],
                context=CommandContext.GLOBAL,
                shortcut="4",
                category="Navigation",
            )
        )

        # Appearance commands
        self.register(
            PaletteCommand(
                id="theme.select",
                name="Select Theme",
                description="Open theme selector",
                keywords=["theme", "color", "dark", "light", "appearance", "style"],
                context=CommandContext.GLOBAL,
                shortcut="\\",
                category="Appearance",
            )
        )

        # Document commands
        self.register(
            PaletteCommand(
                id="doc.new",
                name="New Document",
                description="Create a new document",
                keywords=["new", "create", "document", "add", "write"],
                context=CommandContext.DOCUMENT_BROWSER,
                shortcut="n",
                category="Documents",
            )
        )

        self.register(
            PaletteCommand(
                id="doc.edit",
                name="Edit Document",
                description="Edit the selected document",
                keywords=["edit", "modify", "change", "update"],
                context=CommandContext.DOCUMENT_BROWSER,
                shortcut="e",
                category="Documents",
            )
        )

        self.register(
            PaletteCommand(
                id="doc.tag",
                name="Add Tags",
                description="Add tags to the selected document",
                keywords=["tag", "tags", "label", "category"],
                context=CommandContext.DOCUMENT_BROWSER,
                shortcut="t",
                category="Documents",
            )
        )

        # Search commands
        self.register(
            PaletteCommand(
                id="search.semantic",
                name="Semantic Search",
                description="Search documents by meaning (AI-powered)",
                keywords=["semantic", "ai", "meaning", "similar", "embeddings"],
                context=CommandContext.GLOBAL,
                category="Search",
            )
        )

        self.register(
            PaletteCommand(
                id="search.tags",
                name="Search by Tags",
                description="Find documents with specific tags",
                keywords=["tags", "tag", "filter", "label"],
                context=CommandContext.GLOBAL,
                category="Search",
            )
        )

        # General commands
        self.register(
            PaletteCommand(
                id="app.refresh",
                name="Refresh",
                description="Refresh the current view",
                keywords=["refresh", "reload", "update"],
                context=CommandContext.GLOBAL,
                shortcut="r",
                category="General",
            )
        )

        self.register(
            PaletteCommand(
                id="app.help",
                name="Show Help",
                description="Show keybindings help",
                keywords=["help", "keybindings", "shortcuts", "keys"],
                context=CommandContext.GLOBAL,
                shortcut="?",
                category="General",
            )
        )

        self.register(
            PaletteCommand(
                id="app.quit",
                name="Quit",
                description="Exit the application",
                keywords=["quit", "exit", "close", "bye"],
                context=CommandContext.GLOBAL,
                shortcut="q",
                category="General",
            )
        )

# Global registry instance
_registry: CommandRegistry | None = None

def get_command_registry() -> CommandRegistry:
    """Get the global command registry instance."""
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
    return _registry
