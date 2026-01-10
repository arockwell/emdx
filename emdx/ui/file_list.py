"""File list widget for EMDX file browser."""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from textual import events
from textual.reactive import reactive
from textual.widgets import DataTable

from emdx.database import db

logger = logging.getLogger(__name__)


class FileList(DataTable):
    """File listing with icons and metadata."""
    
    selected_index = reactive(0)
    
    def __init__(self, **kwargs):
        """Initialize file list."""
        super().__init__(**kwargs)
        self.files: List[Path] = []
        self.show_header = True
        self.cursor_type = "row"
        self.zebra_stripes = True
        self.add_class("file-list")
    
    def on_mount(self) -> None:
        """Set up the table structure."""
        self.add_columns("", "Name", "Size", "Modified", "EMDX")
        self.styles.width = "50%"
    
    def on_data_table_row_highlighted(self, event) -> None:
        """Handle row selection changes."""
        self.selected_index = event.cursor_row
        # Notify parent FileBrowser of selection change
        self.post_message(self.FileSelected(event.cursor_row))
    
    class FileSelected(events.Event):
        """Event sent when file selection changes."""
        def __init__(self, index: int):
            super().__init__()
            self.index = index
    
    def watch_selected_index(self, old: int, new: int) -> None:
        """Update cursor position when selection changes."""
        if 0 <= new < len(self.files) and self.row_count > 0:
            self.move_cursor(row=new)
    
    def populate_files(self, path: Path, show_hidden: bool = False) -> None:
        """Populate the file list with directory contents.
        
        Args:
            path: Directory path to list
            show_hidden: Whether to show hidden files
        """
        logger.info(f"📁 populate_files called with path={path}, show_hidden={show_hidden}")
        # Clear only rows, not columns
        self.clear(columns=False)
        self.files = []
        logger.info(f"📁 Cleared table, columns={len(self.columns)}")
        
        # Ensure columns are set up AFTER clearing
        if len(self.columns) == 0:
            logger.info("📁 Adding columns")
            self.add_columns("", "Name", "Size", "Modified", "EMDX")
            logger.info(f"📁 Columns added, columns={len(self.columns)}")
        
        try:
            # Get all entries
            entries = list(path.iterdir())
            logger.info(f"📁 Found {len(entries)} entries in directory")
            
            # Filter hidden files if needed
            if not show_hidden:
                entries = [e for e in entries if not e.name.startswith('.')]
                logger.info(f"📁 After filtering hidden files: {len(entries)} entries")
            
            # Sort: directories first, then by name
            entries.sort(key=lambda x: (not x.is_dir(), x.name.lower()))
            logger.info(f"📁 Sorted {len(entries)} entries")
            
            # Add parent directory entry if not at root
            if path.parent != path:
                logger.info("📁 Adding parent directory entry")
                self.add_row(
                    "📁", "..", "", "", "",
                    key="parent"
                )
                self.files.append(path.parent)
            
            # Add entries
            logger.info(f"📁 Adding {len(entries)} entries to table")
            for i, entry in enumerate(entries):
                try:
                    icon = self.get_file_icon(entry)
                    name = entry.name
                    
                    if entry.is_file():
                        size = self.format_size(entry.stat().st_size)
                        modified = self.format_date(entry.stat().st_mtime)
                    else:
                        size = ""
                        modified = ""
                    
                    # Check if file is in EMDX
                    in_emdx = "✅" if self.check_file_in_emdx(entry) else ""
                    
                    self.add_row(
                        icon, name, size, modified, in_emdx,
                        key=str(entry)
                    )
                    self.files.append(entry)
                    
                except (PermissionError, OSError):
                    # Skip files we can't access
                    continue
                    
        except PermissionError as e:
            # Can't read directory
            logger.error(f"📁 Permission error reading directory {path}: {e}")
            self.add_row("❌", "Permission Denied", "", "", "")
            
        logger.info(f"📁 populate_files complete: {len(self.files)} files, {self.row_count} rows")
        # Select first item if any
        if self.files and self.row_count > 0:
            self.selected_index = 0  # Reset selection to top
            self.move_cursor(row=0)
            logger.info("📁 Reset selection to index 0 and moved cursor to row 0")
    
    def get_selected_file(self) -> Optional[Path]:
        """Get the currently selected file path."""
        if 0 <= self.selected_index < len(self.files):
            selected = self.files[self.selected_index]
            return selected
        return None
    
    # File extension to icon mappings
    _EXT_ICONS: dict[str, str] = {
        # Code files
        ".py": "🐍", ".pyw": "🐍",
        ".js": "📜", ".jsx": "📜", ".ts": "📜", ".tsx": "📜",
        ".rs": "🦀",
        ".go": "🐹",
        ".java": "☕", ".class": "☕", ".jar": "☕",
        ".c": "⚙️", ".cpp": "⚙️", ".cc": "⚙️", ".h": "⚙️", ".hpp": "⚙️",
        ".swift": "🦉",
        ".rb": "💎",
        # Web files
        ".html": "🌐", ".htm": "🌐",
        ".css": "🎨", ".scss": "🎨", ".sass": "🎨",
        # Data files
        ".json": "📊", ".yaml": "📊", ".yml": "📊", ".toml": "📊",
        ".xml": "📋",
        ".sql": "🗃️", ".db": "🗃️", ".sqlite": "🗃️",
        # Docs
        ".md": "📝", ".markdown": "📝",
        ".txt": "📄", ".text": "📄",
        ".pdf": "📕",
        ".doc": "📘", ".docx": "📘",
        # Images
        ".png": "🖼️", ".jpg": "🖼️", ".jpeg": "🖼️", ".gif": "🖼️", ".svg": "🖼️", ".ico": "🖼️",
        # Archives
        ".zip": "📦", ".tar": "📦", ".gz": "📦", ".bz2": "📦", ".xz": "📦", ".7z": "📦",
        # Scripts
        ".sh": "🔨", ".bash": "🔨", ".zsh": "🔨", ".fish": "🔨",
        ".bat": "🪟",
    }

    # Special directory name to icon mappings
    _DIR_ICONS: dict[str, str] = {
        ".git": "🔧",
        "node_modules": "📦",
        "__pycache__": "📦",
        ".venv": "📦",
        "venv": "📦",
    }

    # Special file name to icon mappings
    _NAME_ICONS: dict[str, str] = {
        ".gitignore": "⚙️",
        ".env": "⚙️",
        ".editorconfig": "⚙️",
        "Makefile": "🔧",
        "Dockerfile": "🐳",
        "docker-compose.yml": "🐳",
    }

    def get_file_icon(self, path: Path) -> str:
        """Return emoji icon for file type."""
        if path.is_dir():
            return self._DIR_ICONS.get(path.name, "📁")

        # Check special file names first
        if path.name in self._NAME_ICONS:
            return self._NAME_ICONS[path.name]

        # Check extension
        ext = path.suffix.lower()
        return self._EXT_ICONS.get(ext, "📄")
    
    def format_size(self, size: int) -> str:
        """Format file size in human readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                if unit == 'B':
                    return f"{size} {unit}"
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
    
    def format_date(self, timestamp: float) -> str:
        """Format timestamp as relative date."""
        dt = datetime.fromtimestamp(timestamp)
        now = datetime.now()
        diff = now - dt
        
        if diff.days == 0:
            if diff.seconds < 3600:
                mins = diff.seconds // 60
                return f"{mins}m ago" if mins > 0 else "just now"
            else:
                hours = diff.seconds // 3600
                return f"{hours}h ago"
        elif diff.days == 1:
            return "yesterday"
        elif diff.days < 7:
            return f"{diff.days}d ago"
        elif diff.days < 30:
            weeks = diff.days // 7
            return f"{weeks}w ago"
        elif diff.days < 365:
            months = diff.days // 30
            return f"{months}mo ago"
        else:
            years = diff.days // 365
            return f"{years}y ago"
    
    def check_file_in_emdx(self, file_path: Path) -> bool:
        """Check if file content exists in EMDX.
        
        Args:
            file_path: Path to check
            
        Returns:
            True if file is already in EMDX
        """
        if not file_path.is_file():
            return False
            
        try:
            # For now, do a simple content check
            # In future, could use content hash
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            
            # Hash the content for comparison
            content_hash = hashlib.sha256(content.encode()).hexdigest()
            
            # Check if this file is already saved by title match
            # Note: content_hash computed above is unused - dedup uses title only
            with db.get_connection() as conn:
                result = conn.execute(
                    "SELECT id FROM documents WHERE title = ? AND is_deleted = 0",
                    (file_path.name,)
                ).fetchone()
                return result is not None
                
        except Exception:
            return False
