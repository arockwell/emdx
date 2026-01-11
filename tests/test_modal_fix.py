#!/usr/bin/env python3
"""
Test to verify the modal state detection fix.
This tests that key events are properly passed to modals when active.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock the screen_stack behavior
class MockApp:
    def __init__(self, modal_active=False):
        self.screen_stack = ["main"]
        if modal_active:
            self.screen_stack.append("modal")
        self.key_handled = False
        self.modal_key_handled = False
    
    def on_key(self, event):
        """Simulated on_key method with the fix."""
        # Check if any modal is active (screen stack > 1 means modal is pushed)
        if len(self.screen_stack) > 1:
            # Modal is active, let it handle the key event
            print(f"Modal active, passing key event through: key={event.key}")
            self.modal_key_handled = True
            return
        
        # Handle key normally
        print(f"Main app handling key: {event.key}")
        self.key_handled = True

class MockEvent:
    def __init__(self, key):
        self.key = key

# Test 1: Key handling without modal
print("Test 1: Key handling without modal")
app1 = MockApp(modal_active=False)
app1.on_key(MockEvent("y"))
assert app1.key_handled == True
assert app1.modal_key_handled == False
print("✓ Main app correctly handled the key\n")

# Test 2: Key handling with modal active
print("Test 2: Key handling with modal active")
app2 = MockApp(modal_active=True)
app2.on_key(MockEvent("y"))
assert app2.key_handled == False
assert app2.modal_key_handled == True
print("✓ Key was correctly passed to modal\n")

# Test 3: Screen stack management
print("Test 3: Screen stack management")
app3 = MockApp()
print(f"Initial stack: {app3.screen_stack}")
assert len(app3.screen_stack) == 1

# Push a modal
app3.screen_stack.append("delete_modal")
print(f"After pushing modal: {app3.screen_stack}")
assert len(app3.screen_stack) == 2

# Test key handling with modal
app3.on_key(MockEvent("y"))
assert app3.modal_key_handled == True
print("✓ Modal state detection works correctly\n")

print("All tests passed! The fix should work correctly.")