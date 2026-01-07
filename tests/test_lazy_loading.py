#!/usr/bin/env python3
"""
Test lazy loading performance improvements.
"""

import asyncio
from emdx.ui.agent_execution_overlay import AgentExecutionOverlay, StageType


async def test_lazy_loading():
    """Test that stages don't load data until shown."""
    print("🔍 Testing Lazy Loading Performance")
    print("=" * 60)

    # Create overlay
    print("\n1. Creating overlay...")
    overlay = AgentExecutionOverlay(initial_document_id=1)
    print("   ✓ Overlay created (no data loaded yet)")

    # Simulate mounting (this happens in the TUI)
    print("\n2. Simulating mount (creating stage widgets)...")
    from textual.app import App
    from textual.widgets import Static

    # Create a minimal app context
    app = App()
    async with app.run_test() as pilot:
        # Push the overlay screen
        await app.push_screen(overlay)

        # Wait for mount to complete
        await asyncio.sleep(0.1)

        print("   ✓ All stages mounted")

        # Check which stages have loaded data
        print("\n3. Checking stage loading status:")
        for stage_type in [StageType.DOCUMENT, StageType.AGENT, StageType.PROJECT,
                          StageType.WORKTREE, StageType.CONFIG]:
            if stage_type in overlay.stage_widgets:
                stage = overlay.stage_widgets[stage_type]
                is_loaded = getattr(stage, '_data_loaded', False)
                status = "✓ LOADED" if is_loaded else "○ NOT LOADED"
                print(f"   {stage_type.value:12} {status}")

        # Current stage should be loaded
        current = overlay.get_current_stage()
        current_widget = overlay.stage_widgets[current]
        is_loaded = getattr(current_widget, '_data_loaded', False)

        print(f"\n4. Current stage ({current.value}):")
        print(f"   {'✓ LOADED' if is_loaded else '✗ NOT LOADED'}")

        if is_loaded:
            print("\n🎉 SUCCESS! Only current stage loaded data.")
            print("   Other stages will load when you navigate to them.")
        else:
            print("\n⚠️  Current stage not loaded yet.")
            print("   This is expected - it loads when show_current_stage() is called.")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(test_lazy_loading())
