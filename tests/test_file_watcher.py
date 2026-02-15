"""Tests for file_watcher.py with mock filesystem events."""

import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from emdx.services.file_watcher import FileWatcher, WATCHDOG_AVAILABLE


class TestFileWatcherPolling:
    """Test FileWatcher polling fallback mechanism."""

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("initial content\n")
            temp_path = Path(f.name)

        yield temp_path

        # Cleanup after test
        if temp_path.exists():
            temp_path.unlink()

    def test_polling_detects_file_modification(self, temp_file):
        """Test that polling detects file modifications."""
        callback_called = threading.Event()
        callback_count = [0]

        def callback():
            callback_count[0] += 1
            if callback_count[0] >= 2:  # Initial + modification
                callback_called.set()

        # Force polling mode by mocking WATCHDOG_AVAILABLE
        with patch('emdx.services.file_watcher.WATCHDOG_AVAILABLE', False):
            watcher = FileWatcher(temp_file, callback)
            watcher.start()

            try:
                # Wait for initial poll cycle (poll interval is 0.5s)
                time.sleep(0.55)

                # Modify the file
                with open(temp_file, 'a') as f:
                    f.write("new content\n")

                # Wait for callback to be triggered
                result = callback_called.wait(timeout=2.0)
                assert result, "Callback was not triggered after file modification"
                assert callback_count[0] >= 2, "Expected at least 2 callbacks (initial + modification)"
            finally:
                watcher.stop()

    def test_polling_detects_size_change(self, temp_file):
        """Test that polling detects file size changes."""
        callback_called = threading.Event()
        callback_count = [0]

        def callback():
            callback_count[0] += 1
            if callback_count[0] >= 2:
                callback_called.set()

        with patch('emdx.services.file_watcher.WATCHDOG_AVAILABLE', False):
            watcher = FileWatcher(temp_file, callback)
            watcher.start()

            try:
                # Wait for initial poll cycle (poll interval is 0.5s)
                time.sleep(0.55)

                # Append to file to change size
                with open(temp_file, 'a') as f:
                    f.write("x" * 100)

                result = callback_called.wait(timeout=2.0)
                assert result, "Callback was not triggered after size change"
            finally:
                watcher.stop()

    def test_polling_handles_nonexistent_file(self):
        """Test that polling handles non-existent files gracefully."""
        nonexistent = Path("/tmp/nonexistent_file_12345.txt")
        callback = MagicMock()

        with patch('emdx.services.file_watcher.WATCHDOG_AVAILABLE', False):
            watcher = FileWatcher(nonexistent, callback)
            watcher.start()

            try:
                # Let polling run for one cycle (poll interval is 0.5s)
                time.sleep(0.55)
                # Should not crash
            finally:
                watcher.stop()

    def test_stop_terminates_polling_thread(self, temp_file):
        """Test that stop() properly terminates the polling thread."""
        callback = MagicMock()

        with patch('emdx.services.file_watcher.WATCHDOG_AVAILABLE', False):
            watcher = FileWatcher(temp_file, callback)
            watcher.start()

            assert watcher.polling_thread is not None
            assert watcher.polling_thread.is_alive()

            watcher.stop()

            # Wait for thread to terminate (use join instead of sleep)
            watcher.polling_thread.join(timeout=1.0)
            assert not watcher.polling_thread.is_alive()


class TestFileWatcherWatchdog:
    """Test FileWatcher with watchdog (when available)."""

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("initial content\n")
            temp_path = Path(f.name)

        yield temp_path

        if temp_path.exists():
            temp_path.unlink()

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_watchdog_starts_observer(self, temp_file):
        """Test that watchdog observer is started when available."""
        callback = MagicMock()

        watcher = FileWatcher(temp_file, callback)
        watcher.start()

        try:
            assert watcher.observer is not None
            assert watcher.observer.is_alive()
        finally:
            watcher.stop()

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_watchdog_stop_terminates_observer(self, temp_file):
        """Test that stop() properly terminates the watchdog observer."""
        callback = MagicMock()

        watcher = FileWatcher(temp_file, callback)
        watcher.start()

        assert watcher.observer is not None
        watcher.stop()

        # Observer should be stopped
        assert not watcher.observer.is_alive()

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_watchdog_detects_modification(self, temp_file):
        """Test that watchdog detects file modifications."""
        callback_called = threading.Event()

        def callback():
            callback_called.set()

        watcher = FileWatcher(temp_file, callback)
        watcher.start()

        try:
            # Modify the file
            time.sleep(0.1)  # Give observer time to start
            with open(temp_file, 'a') as f:
                f.write("new content\n")

            # Wait for callback
            result = callback_called.wait(timeout=2.0)
            assert result, "Callback was not triggered after file modification"
        finally:
            watcher.stop()


class TestFileWatcherFallback:
    """Test FileWatcher fallback from watchdog to polling."""

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("initial content\n")
            temp_path = Path(f.name)

        yield temp_path

        if temp_path.exists():
            temp_path.unlink()

    @pytest.mark.skipif(not WATCHDOG_AVAILABLE, reason="watchdog not installed")
    def test_fallback_to_polling_on_watchdog_failure(self, temp_file):
        """Test fallback to polling when watchdog fails."""
        from watchdog.observers import Observer
        callback = MagicMock()

        # Mock the Observer to fail on start
        with patch.object(Observer, 'start', side_effect=Exception("Watchdog failed")):
            watcher = FileWatcher(temp_file, callback)
            watcher.start()

            try:
                # Should have fallen back to polling
                assert watcher.polling_thread is not None
                assert watcher.polling_thread.is_alive()
            finally:
                watcher.stop()

    def test_uses_polling_when_watchdog_unavailable(self, temp_file):
        """Test that polling is used when watchdog is not available."""
        callback = MagicMock()

        with patch('emdx.services.file_watcher.WATCHDOG_AVAILABLE', False):
            watcher = FileWatcher(temp_file, callback)
            watcher.start()

            try:
                # Should use polling (not watchdog)
                assert watcher.polling_thread is not None
                assert watcher.polling_thread.is_alive()
                assert watcher.observer is None
            finally:
                watcher.stop()


class TestFileWatcherInitialization:
    """Test FileWatcher initialization."""

    def test_initialization_sets_attributes(self):
        """Test that FileWatcher properly initializes attributes."""
        file_path = Path("/tmp/test.txt")
        callback = MagicMock()

        watcher = FileWatcher(file_path, callback)

        assert watcher.file_path == file_path
        assert watcher.callback == callback
        assert watcher.observer is None
        assert watcher.polling_thread is None
        assert not watcher.stop_event.is_set()

    def test_stop_event_initially_not_set(self):
        """Test that stop_event is initially not set."""
        watcher = FileWatcher(Path("/tmp/test.txt"), MagicMock())
        assert not watcher.stop_event.is_set()


class TestFileWatcherIntegration:
    """Integration tests for FileWatcher with real file operations."""

    @pytest.fixture
    def temp_file(self):
        """Create a temporary file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("initial content\n")
            temp_path = Path(f.name)

        yield temp_path

        if temp_path.exists():
            temp_path.unlink()

    def test_multiple_modifications_trigger_multiple_callbacks(self, temp_file):
        """Test that multiple file modifications trigger multiple callbacks."""
        callback_count = [0]
        lock = threading.Lock()

        def callback():
            with lock:
                callback_count[0] += 1

        with patch('emdx.services.file_watcher.WATCHDOG_AVAILABLE', False):
            watcher = FileWatcher(temp_file, callback)
            watcher.start()

            try:
                # Wait for initial poll cycle (poll interval is 0.5s)
                time.sleep(0.55)
                initial_count = callback_count[0]

                # Make multiple modifications
                for i in range(3):
                    time.sleep(0.55)  # Wait for one poll cycle
                    with open(temp_file, 'a') as f:
                        f.write(f"modification {i}\n")

                # Wait for final poll cycle
                time.sleep(0.55)

                # Should have more callbacks than initial
                assert callback_count[0] > initial_count, "Expected callbacks for modifications"
            finally:
                watcher.stop()

    def test_start_stop_cycle(self, temp_file):
        """Test that watcher can be started and stopped multiple times."""
        callback = MagicMock()

        with patch('emdx.services.file_watcher.WATCHDOG_AVAILABLE', False):
            watcher = FileWatcher(temp_file, callback)

            # First cycle
            watcher.start()
            time.sleep(0.1)  # Brief delay to ensure thread starts
            watcher.stop()
            if watcher.polling_thread:
                watcher.polling_thread.join(timeout=1.0)

            # Reset stop event for second cycle
            watcher.stop_event.clear()
            watcher.polling_thread = None

            # Second cycle
            watcher.start()
            time.sleep(0.1)  # Brief delay to ensure thread starts
            watcher.stop()

            # Should not crash


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
