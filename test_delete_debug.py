#!/usr/bin/env python3
"""
Debug script to test the delete functionality in EMDX TUI.
This script simulates the key press sequence and checks the modal behavior.

DEPRECATED: This test file is no longer relevant since MinimalDocumentBrowser
has been removed as part of technical debt cleanup. The modern GUI uses
DocumentBrowser from document_browser.py via BrowserContainer.
"""

import asyncio
import warnings
from textual import events
from textual.app import App
from textual.pilot import Pilot

# Deprecated import - will generate warnings
try:
    from emdx.ui.main_browser import MinimalDocumentBrowser
except RuntimeError as e:
    print(f"❌ {e}")
    print("✅ Use 'emdx gui' for the modern interface.")
    exit(1)
    
from emdx.ui.modals import DeleteConfirmScreen

async def test_delete_flow():
    """Test the delete key flow in the TUI."""
    print("Testing EMDX delete functionality...")
    
    # Create the app
    app = MinimalDocumentBrowser()
    
    async with app.run_test() as pilot:
        # Wait for app to load
        await pilot.pause(0.5)
        
        # Check if documents are loaded
        try:
            table = app.query_one("#doc-table")
            print(f"Found table with {table.row_count} rows")
            
            if table.row_count > 0:
                # Press 'd' to trigger delete
                print("Pressing 'd' key...")
                await pilot.press("d")
                await pilot.pause(0.2)
                
                # Check if modal is shown
                screens = app.screen_stack
                print(f"Screen stack: {[type(s).__name__ for s in screens]}")
                
                # Look for DeleteConfirmScreen
                delete_screen = None
                for screen in screens:
                    if isinstance(screen, DeleteConfirmScreen):
                        delete_screen = screen
                        break
                
                if delete_screen:
                    print(f"DeleteConfirmScreen found for doc #{delete_screen.doc_id}: {delete_screen.doc_title}")
                    
                    # Press 'y' to confirm
                    print("Pressing 'y' to confirm...")
                    await pilot.press("y")
                    await pilot.pause(0.2)
                    
                    # Check if screen was dismissed
                    screens_after = app.screen_stack
                    print(f"Screen stack after 'y': {[type(s).__name__ for s in screens_after]}")
                else:
                    print("DeleteConfirmScreen not found in screen stack!")
            else:
                print("No documents in table to test with")
                
        except Exception as e:
            print(f"Error during test: {e}")
            import traceback
            traceback.print_exc()

async def test_delete_modal_directly():
    """Test the DeleteConfirmScreen modal directly."""
    print("\nTesting DeleteConfirmScreen directly...")
    
    class TestApp(App):
        def on_mount(self):
            def handle_result(result):
                print(f"Modal dismissed with result: {result}")
                self.exit()
            
            self.push_screen(DeleteConfirmScreen(123, "Test Document"), handle_result)
    
    app = TestApp()
    async with app.run_test() as pilot:
        await pilot.pause(0.2)
        print("Modal should be visible now")
        
        # Test 'y' key binding
        print("Pressing 'y' key...")
        await pilot.press("y")
        await pilot.pause(0.2)

if __name__ == "__main__":
    print("Running delete functionality tests...\n")
    asyncio.run(test_delete_flow())
    asyncio.run(test_delete_modal_directly())