"""Cross-platform file watching with fallback to polling."""

import logging
import threading
from collections.abc import Callable
from pathlib import Path

# Try to use watchdog for efficient file watching
try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

logger = logging.getLogger(__name__)


class FileWatcher:
    """Cross-platform file watching with fallback to polling."""

    def __init__(self, file_path: Path, callback: Callable[[], None]):
        self.file_path = file_path
        self.callback = callback
        self.observer = None
        self.polling_thread = None
        self.stop_event = threading.Event()

    def start(self) -> None:
        """Start watching the file."""
        if WATCHDOG_AVAILABLE:
            self._start_watchdog()
        else:
            self._start_polling()

    def stop(self) -> None:
        """Stop watching the file."""
        self.stop_event.set()

        if self.observer:
            self.observer.stop()
            self.observer.join()

        if self.polling_thread:
            self.polling_thread.join(timeout=1.0)

    def _start_watchdog(self) -> None:
        """Use watchdog for efficient file watching."""
        class LogFileHandler(FileSystemEventHandler):
            def __init__(self, file_path: Path, callback: Callable):
                self.file_path = file_path
                self.callback = callback

            def on_modified(self, event):
                if not event.is_directory and Path(event.src_path) == self.file_path:
                    self.callback()

        try:
            handler = LogFileHandler(self.file_path, self.callback)
            self.observer = Observer()
            self.observer.schedule(handler, str(self.file_path.parent), recursive=False)
            self.observer.start()
            logger.debug(f"Started watchdog monitoring for {self.file_path}")
        except Exception as e:
            logger.warning(f"Watchdog failed, falling back to polling: {e}")
            self._start_polling()

    def _start_polling(self) -> None:
        """Fallback to polling-based watching."""
        def poll():
            last_mtime = 0
            last_size = 0
            while not self.stop_event.is_set():
                try:
                    if self.file_path.exists():
                        stat_result = self.file_path.stat()
                        current_mtime = stat_result.st_mtime
                        current_size = stat_result.st_size

                        # Trigger callback if file changed
                        if current_mtime > last_mtime or current_size != last_size:
                            last_mtime = current_mtime
                            last_size = current_size
                            self.callback()
                except Exception as e:
                    logger.error(f"Error in polling: {e}")

                # Poll every 0.5 seconds (faster than current 1s)
                self.stop_event.wait(0.5)

        self.polling_thread = threading.Thread(target=poll, daemon=True)
        self.polling_thread.start()
        logger.debug(f"Started polling monitoring for {self.file_path}")
