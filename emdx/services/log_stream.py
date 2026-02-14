"""Event-driven log file streaming with file watching."""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from .file_watcher import FileWatcher

logger = logging.getLogger(__name__)


class LogStreamSubscriber(ABC):
    """Interface for components that consume log updates."""

    @abstractmethod
    def on_log_content(self, new_content: str) -> None:
        """Called when new log content is available."""
        pass

    @abstractmethod
    def on_log_error(self, error: Exception) -> None:
        """Called when log reading encounters an error."""
        pass


class LogStream:
    """Event-driven log file streaming with file watching."""

    def __init__(self, log_file_path: Path):
        self.path = log_file_path
        self.position = 0
        self.subscribers: List[LogStreamSubscriber] = []
        self.watcher: Optional[FileWatcher] = None
        self.is_watching = False
        self._polling = False
        self._stopped = False
        self._poll_thread: Optional[threading.Thread] = None
        self._poll_interval = 1.0

    def subscribe(self, subscriber: LogStreamSubscriber) -> None:
        """Subscribe to log updates."""
        if subscriber not in self.subscribers:
            self.subscribers.append(subscriber)

        # Start watching when first subscriber joins
        if not self.is_watching:
            self._start_watching()

    def unsubscribe(self, subscriber: LogStreamSubscriber) -> None:
        """Unsubscribe from log updates."""
        if subscriber in self.subscribers:
            self.subscribers.remove(subscriber)

        # Stop watching when no subscribers remain
        if not self.subscribers and self.is_watching:
            self._stop_watching()

    def get_initial_content(self) -> str:
        """Get current file content for initial display."""
        if not self.path.exists():
            return ""

        try:
            with open(self.path, encoding='utf-8', errors='replace') as f:
                content = f.read()
                self.position = f.tell()
                return content
        except Exception as e:
            logger.error(f"Error reading initial log content: {e}")
            return f"Error reading log: {e}"

    def _start_watching(self) -> None:
        """Start file system watching."""
        try:
            from .file_watcher import FileWatcher
            self.watcher = FileWatcher(self.path, self._on_file_changed)
            self.watcher.start()
            self.is_watching = True
            logger.debug(f"Started watching {self.path}")
        except Exception as e:
            logger.error(f"Failed to start file watching: {e}")
            # Fallback to polling if file watching fails
            self._start_polling_fallback()

    def _stop_watching(self) -> None:
        """Stop file system watching."""
        if self.watcher:
            self.watcher.stop()
            self.watcher = None

        # Stop polling fallback if active
        self._polling = False
        self._stopped = True
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)
            self._poll_thread = None

        self.is_watching = False
        logger.debug(f"Stopped watching {self.path}")

    def _on_file_changed(self) -> None:
        """Called when OS detects file change."""
        try:
            new_content = self._read_new_content()
            if new_content:
                for subscriber in self.subscribers:
                    try:
                        subscriber.on_log_content(new_content)
                    except Exception as e:
                        logger.error(f"Error in subscriber callback: {e}")
        except Exception as e:
            logger.error(f"Error processing file change: {e}")
            for subscriber in self.subscribers:
                try:
                    subscriber.on_log_error(e)
                except Exception as e:
                    # Log subscriber error but continue with others
                    logger.debug(f"Subscriber error in log stream: {e}")

    def _read_new_content(self) -> str:
        """Read only new content since last position."""
        if not self.path.exists():
            return ""

        try:
            with open(self.path, encoding='utf-8', errors='replace') as f:
                f.seek(self.position)
                new_content = f.read()
                self.position = f.tell()
                return new_content
        except Exception as e:
            logger.error(f"Error reading new log content: {e}")
            return ""

    def _start_polling_fallback(self) -> None:
        """Fallback to polling if file watching fails."""
        logger.warning("File watching failed, using polling fallback")

        self._polling = True
        self.is_watching = True

        def poll_loop():
            while self._polling and not self._stopped:
                try:
                    content = self._read_new_content()
                    if content:
                        self._notify_subscribers(content)
                except Exception as e:
                    logger.debug(f"Polling error: {e}")
                time.sleep(self._poll_interval)

        self._poll_thread = threading.Thread(target=poll_loop, daemon=True, name="log-poll")
        self._poll_thread.start()

    def _notify_subscribers(self, content: str) -> None:
        """Notify all subscribers of new content."""
        for subscriber in self.subscribers:
            try:
                subscriber.on_log_content(content)
            except Exception as e:
                logger.error(f"Error in subscriber callback: {e}")
