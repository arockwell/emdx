"""
Central keybinding registry with conflict detection.

The registry collects all keybindings from widgets and detects conflicts
at startup before they can cause runtime crashes.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Set

from .context import Context

logger = logging.getLogger(__name__)


class ConflictType(Enum):
    """Types of keybinding conflicts."""

    SAME_CONTEXT = "same_context"  # Two bindings for same key in same context
    PARENT_CHILD = "parent_child"  # Child overrides parent (usually OK)
    SIBLING = "sibling"  # Different contexts that might overlap


class ConflictSeverity(Enum):
    """Severity levels for conflicts."""

    CRITICAL = "critical"  # Will likely crash
    WARNING = "warning"  # Might cause issues
    INFO = "info"  # Intentional override, just informational


@dataclass
class KeybindingEntry:
    """Represents a single keybinding in the registry."""

    key: str  # e.g., "t", "ctrl+s", "j"
    action: str  # e.g., "add_tags", "cursor_down"
    context: Context  # Where this binding applies
    widget_class: str  # e.g., "DocumentBrowser"
    description: str = ""  # User-visible description
    priority: bool = False  # Textual's priority flag
    show: bool = True  # Whether to show in help
    allow_override: bool = True  # Can user override in config

    def __hash__(self):
        return hash((self.key, self.action, self.context.value, self.widget_class))

    def __eq__(self, other):
        if not isinstance(other, KeybindingEntry):
            return False
        return (
            self.key == other.key
            and self.action == other.action
            and self.context == other.context
            and self.widget_class == other.widget_class
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "key": self.key,
            "action": self.action,
            "context": self.context.value,
            "widget": self.widget_class,
            "description": self.description,
            "priority": self.priority,
        }


@dataclass
class ConflictReport:
    """Describes a keybinding conflict."""

    key: str
    context1: Context
    context2: Context
    binding1: KeybindingEntry
    binding2: KeybindingEntry
    conflict_type: ConflictType
    severity: ConflictSeverity = ConflictSeverity.WARNING

    def to_string(self) -> str:
        """Format conflict for logging/display."""
        return (
            f"[{self.severity.value.upper()}] Key '{self.key}' conflict:\n"
            f"  {self.binding1.widget_class}.{self.binding1.action} "
            f"({self.context1.value})\n"
            f"  {self.binding2.widget_class}.{self.binding2.action} "
            f"({self.context2.value})\n"
            f"  Type: {self.conflict_type.value}"
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "key": self.key,
            "severity": self.severity.value,
            "type": self.conflict_type.value,
            "binding1": self.binding1.to_dict(),
            "binding2": self.binding2.to_dict(),
        }


@dataclass
class KeybindingRegistry:
    """
    Central registry for all keybindings with conflict detection.

    Usage:
        registry = KeybindingRegistry()

        # Register bindings (usually done by extractor)
        registry.register(KeybindingEntry(
            key="t",
            action="add_tags",
            context=Context.DOCUMENT_NORMAL,
            widget_class="DocumentBrowser"
        ))

        # Detect conflicts
        conflicts = registry.detect_conflicts()
        for conflict in conflicts:
            logger.warning(conflict.to_string())

        # Get bindings for a context
        bindings = registry.get_bindings_for_context(Context.DOCUMENT_NORMAL)
    """

    # All registered bindings
    bindings: List[KeybindingEntry] = field(default_factory=list)

    # Bindings indexed by context for fast lookup
    by_context: Dict[Context, List[KeybindingEntry]] = field(default_factory=dict)

    # Bindings indexed by key for conflict detection
    by_key: Dict[str, List[KeybindingEntry]] = field(default_factory=dict)

    # Detected conflicts
    conflicts: List[ConflictReport] = field(default_factory=list)

    # User overrides from config
    overrides: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def register(self, entry: KeybindingEntry) -> None:
        """
        Register a keybinding.

        Args:
            entry: The keybinding to register
        """
        # Avoid duplicates
        if entry in self.bindings:
            return

        self.bindings.append(entry)

        # Index by context
        if entry.context not in self.by_context:
            self.by_context[entry.context] = []
        self.by_context[entry.context].append(entry)

        # Index by key
        if entry.key not in self.by_key:
            self.by_key[entry.key] = []
        self.by_key[entry.key].append(entry)

    def register_many(self, entries: List[KeybindingEntry]) -> None:
        """Register multiple keybindings at once."""
        for entry in entries:
            self.register(entry)

    def _are_actions_similar(self, action1: str, action2: str) -> bool:
        """
        Check if two actions are semantically similar.

        Returns True if actions do essentially the same thing
        (e.g., cursor_down vs scroll_down vs move_down).
        """
        # Normalize action names
        a1 = action1.lower().replace("_", "").replace("-", "")
        a2 = action2.lower().replace("_", "").replace("-", "")

        # Direct match after normalization
        if a1 == a2:
            return True

        # Common synonyms for navigation
        synonyms = {
            "cursordown": {"scrolldown", "movedown", "down"},
            "cursorup": {"scrollup", "moveup", "up"},
            "cursorleft": {"scrollleft", "moveleft", "left"},
            "cursorright": {"scrollright", "moveright", "right"},
            "cursortop": {"scrolltop", "scrollhome", "home", "top"},
            "cursorbottom": {"scrollbottom", "scrollend", "end", "bottom"},
            "select": {"selectcursor", "zoomin", "enterdir"},
            "home": {"cursorlinestart"},
            "end": {"cursorlineend"},
            # Text input synonyms
            "cursorwordleft": {"cursorleftword"},
            "cursorwordright": {"cursorrightword"},
            "cursorwordleftselect": {"cursorleftwordselect", "cursorwordleft(true)"},
            "cursorwordrightselect": {"cursorrighttwordselect", "cursorwordright(true)"},
            "cursorlinestartselect": {"hometrue", "home(true)"},
            "cursorlineendselect": {"endtrue", "end(true)"},
            "deletewordleft": {"deleteleftword"},
            "deletewordright": {"deleterightword"},
            "deletetostart": {"deleteleftall", "deletelefttostart"},
            "deletetoend": {"deleterightall", "deleterighttoend"},
        }

        for canonical, variants in synonyms.items():
            all_variants = variants | {canonical}
            if a1 in all_variants and a2 in all_variants:
                return True

        return False

    def detect_conflicts(self) -> List[ConflictReport]:
        """
        Detect all keybinding conflicts.

        Returns:
            List of conflict reports sorted by severity
        """
        self.conflicts = []

        # Check each key that has multiple bindings
        for key, bindings in self.by_key.items():
            if len(bindings) < 2:
                continue

            # Compare each pair of bindings for this key
            for i, binding1 in enumerate(bindings):
                for binding2 in bindings[i + 1 :]:
                    conflict = self._check_conflict(key, binding1, binding2)
                    if conflict:
                        self.conflicts.append(conflict)

        # Sort by severity (critical first)
        severity_order = {
            ConflictSeverity.CRITICAL: 0,
            ConflictSeverity.WARNING: 1,
            ConflictSeverity.INFO: 2,
        }
        self.conflicts.sort(key=lambda c: severity_order[c.severity])

        return self.conflicts

    def _check_conflict(
        self, key: str, binding1: KeybindingEntry, binding2: KeybindingEntry
    ) -> ConflictReport | None:
        """
        Check if two bindings for the same key conflict.

        Returns:
            ConflictReport if there's a conflict, None otherwise
        """
        ctx1 = binding1.context
        ctx2 = binding2.context

        # Same context, same key, different action = CRITICAL
        if ctx1 == ctx2:
            if binding1.action != binding2.action:
                # Check if actions are semantically similar (both do same thing)
                similar_actions = self._are_actions_similar(
                    binding1.action, binding2.action
                )
                return ConflictReport(
                    key=key,
                    context1=ctx1,
                    context2=ctx2,
                    binding1=binding1,
                    binding2=binding2,
                    conflict_type=ConflictType.SAME_CONTEXT,
                    # Downgrade to INFO if actions do the same thing
                    severity=ConflictSeverity.INFO if similar_actions else ConflictSeverity.CRITICAL,
                )
            # Same action = duplicate, not a conflict
            return None

        # Check if contexts can overlap
        if not Context.contexts_can_overlap(ctx1, ctx2):
            # Different non-overlapping contexts = no conflict
            return None

        # One is parent of the other = intentional override (INFO)
        parents1 = Context.get_parent_contexts(ctx1)
        parents2 = Context.get_parent_contexts(ctx2)

        if ctx1 in parents2:
            # ctx2 is a child of ctx1, child overrides parent
            return ConflictReport(
                key=key,
                context1=ctx1,
                context2=ctx2,
                binding1=binding1,
                binding2=binding2,
                conflict_type=ConflictType.PARENT_CHILD,
                severity=ConflictSeverity.INFO,
            )

        if ctx2 in parents1:
            # ctx1 is a child of ctx2
            return ConflictReport(
                key=key,
                context1=ctx1,
                context2=ctx2,
                binding1=binding1,
                binding2=binding2,
                conflict_type=ConflictType.PARENT_CHILD,
                severity=ConflictSeverity.INFO,
            )

        # Sibling contexts that might overlap = WARNING
        return ConflictReport(
            key=key,
            context1=ctx1,
            context2=ctx2,
            binding1=binding1,
            binding2=binding2,
            conflict_type=ConflictType.SIBLING,
            severity=ConflictSeverity.WARNING,
        )

    def get_bindings_for_context(
        self, context: Context, include_parents: bool = True
    ) -> List[KeybindingEntry]:
        """
        Get all bindings active in a context.

        Args:
            context: The context to get bindings for
            include_parents: Whether to include inherited bindings

        Returns:
            List of bindings, sorted by priority
        """
        bindings = list(self.by_context.get(context, []))

        if include_parents:
            for parent in Context.get_parent_contexts(context):
                bindings.extend(self.by_context.get(parent, []))

        # Sort: priority bindings first, then by context specificity
        def sort_key(b: KeybindingEntry) -> tuple:
            # Get context depth (more specific = higher number)
            ctx_order = [context] + Context.get_parent_contexts(context)
            try:
                depth = ctx_order.index(b.context)
            except ValueError:
                depth = 999
            return (-int(b.priority), depth)

        bindings.sort(key=sort_key)

        return bindings

    def get_all_keys(self) -> Set[str]:
        """Get all registered keys."""
        return set(self.by_key.keys())

    def get_binding_for_key(
        self, key: str, context: Context
    ) -> KeybindingEntry | None:
        """
        Get the active binding for a key in a context.

        Returns the most specific binding (child overrides parent).
        """
        bindings = self.get_bindings_for_context(context)
        for binding in bindings:
            if binding.key == key:
                return binding
        return None

    def get_conflicts_by_severity(
        self, severity: ConflictSeverity
    ) -> List[ConflictReport]:
        """Get conflicts filtered by severity."""
        return [c for c in self.conflicts if c.severity == severity]

    def has_critical_conflicts(self) -> bool:
        """Check if there are any critical conflicts."""
        return any(c.severity == ConflictSeverity.CRITICAL for c in self.conflicts)

    def summary(self) -> str:
        """Get a summary of the registry state."""
        lines = [
            "Keybinding Registry Summary:",
            f"  Total bindings: {len(self.bindings)}",
            f"  Unique keys: {len(self.by_key)}",
            f"  Contexts: {len(self.by_context)}",
            f"  Conflicts: {len(self.conflicts)}",
        ]

        if self.conflicts:
            critical = len(self.get_conflicts_by_severity(ConflictSeverity.CRITICAL))
            warning = len(self.get_conflicts_by_severity(ConflictSeverity.WARNING))
            info = len(self.get_conflicts_by_severity(ConflictSeverity.INFO))
            lines.append(f"    Critical: {critical}, Warning: {warning}, Info: {info}")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Convert registry to dictionary for serialization."""
        return {
            "bindings": [b.to_dict() for b in self.bindings],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "summary": {
                "total_bindings": len(self.bindings),
                "unique_keys": len(self.by_key),
                "contexts": len(self.by_context),
                "conflicts": len(self.conflicts),
            },
        }
