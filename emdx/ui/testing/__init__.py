"""
Testing utilities for EMDX browser and panel development.

This module provides test harnesses, mocks, fixtures, and integration testing
utilities for testing browser components.

Two approaches are available:

1. **Unit Testing (without Textual runtime)**:
   Use BrowserTestHarness and mock panels for fast, isolated tests.

   ```python
   from emdx.ui.testing import BrowserTestHarness, MockListPanel

   @pytest.fixture
   def harness():
       browser = MyBrowser()
       return BrowserTestHarness(browser)

   @pytest.mark.asyncio
   async def test_navigation(harness):
       await harness.mount()
       await harness.press("j")
       assert harness.get_selected_index() == 1
   ```

2. **Integration Testing (with full Textual runtime)**:
   Use PilotIntegrationHarness for real app testing with Pilot.

   ```python
   from emdx.ui.testing import PilotIntegrationHarness

   @pytest.fixture
   async def harness():
       async with PilotIntegrationHarness.create(MyBrowser) as h:
           yield h

   @pytest.mark.asyncio
   async def test_navigation(harness):
       await harness.press("j")
       harness.assert_selected_index(1)
   ```
"""

# Unit testing utilities (no Textual runtime)
from .harness import BrowserTestHarness
from .mocks import MockListPanel, MockPreviewPanel, MockStatusPanel

# Integration testing utilities (with Textual Pilot)
from .integration import (
    # Core harness
    PilotIntegrationHarness,
    TestApp,
    create_test_app,
    # Snapshot testing
    WidgetSnapshot,
    SnapshotManager,
    # Message testing
    CapturedMessage,
    MessageCapture,
    # Mock data generation
    MockDataGenerator,
    # Async helpers
    wait_for_condition,
    wait_for_message,
    AsyncTestContext,
)

__all__ = [
    # Unit testing
    "BrowserTestHarness",
    "MockListPanel",
    "MockPreviewPanel",
    "MockStatusPanel",
    # Integration testing - core
    "PilotIntegrationHarness",
    "TestApp",
    "create_test_app",
    # Integration testing - snapshots
    "WidgetSnapshot",
    "SnapshotManager",
    # Integration testing - messages
    "CapturedMessage",
    "MessageCapture",
    # Integration testing - data generation
    "MockDataGenerator",
    # Integration testing - async helpers
    "wait_for_condition",
    "wait_for_message",
    "AsyncTestContext",
]
