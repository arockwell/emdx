#!/usr/bin/env python3
"""
Agent browser - UI for managing and viewing agents.

Uses mixins for:
- Agent listing and table navigation (AgentListingMixin)
- Agent execution (AgentExecutionMixin)
- Agent config display (AgentConfigHandlerMixin)
"""

import logging
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Static

from .agent_listing import AgentListingMixin
from .agent_execution import AgentExecutionMixin
from .agent_config_handler import AgentConfigHandlerMixin

logger = logging.getLogger(__name__)

# Import agent registry with fallback
try:
    from ..agents.registry import agent_registry
    logger.info("Successfully imported agent_registry")

    try:
        test_agents = agent_registry.list_agents()
        logger.info(f"Database check: Found {len(test_agents)} agents")
    except Exception as e:
        logger.warning(f"Database may not be initialized: {e}")
        from ..database.connection import db_connection
        from ..database.migrations import run_migrations
        logger.info("Running database migrations...")
        with db_connection.get_connection() as conn:
            run_migrations()
        logger.info("Migrations complete")

except Exception as e:
    logger.error(f"Failed to import agent_registry: {e}", exc_info=True)
    agent_registry = None


class AgentBrowser(
    AgentListingMixin,
    AgentExecutionMixin,
    AgentConfigHandlerMixin,
    Widget
):
    """Agent browser widget with listing, execution, and config display.

    Combines functionality from:
    - AgentListingMixin: Table navigation and agent list management
    - AgentExecutionMixin: Agent execution handling
    - AgentConfigHandlerMixin: Agent details and config display
    """

    BINDINGS = [
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
        Binding("g", "cursor_top", "Top"),
        Binding("G", "cursor_bottom", "Bottom"),
        Binding("r", "run_agent", "Run"),
        Binding("n", "new_agent", "New"),
        Binding("e", "edit_agent", "Edit"),
        Binding("d", "delete_agent", "Delete"),
    ]

    DEFAULT_CSS = """
    AgentBrowser {
        layout: vertical;
        height: 100%;
    }

    .agent-status {
        height: 1;
        background: $boost;
        color: $text;
        padding: 0 1;
        text-align: center;
    }

    .agent-content {
        height: 1fr;
    }

    #agent-sidebar {
        width: 50%;
        height: 100%;
    }

    #agent-table {
        height: 66%;
    }

    #agent-details {
        height: 34%;
        border: solid $primary;
        padding: 1;
    }

    #agent-preview-container {
        width: 50%;
        height: 100%;
    }

    #agent-preview {
        height: 100%;
        padding: 1;
    }

    #agent-content {
        height: 100%;
        border: solid $primary;
    }
    """

    def __init__(self):
        super().__init__()
        self.agents_list = []
        self.current_agent_id = None

        # Form mode state
        self.form_mode = False
        self.editing_agent_id = None

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Static("Agent Browser - Minimal Test", classes="agent-status")

        with Horizontal(classes="agent-content"):
            with Vertical(id="agent-sidebar"):
                yield DataTable(id="agent-table", cursor_type="row")
                yield Static("", id="agent-details", markup=True)

            with Vertical(id="agent-preview-container"):
                with ScrollableContainer(id="agent-preview"):
                    yield Static("", id="agent-content", markup=True)

    def on_mount(self) -> None:
        """Set up when mounted."""
        try:
            self.update_status("Agent browser mounted - minimal version")

            table = self.query_one("#agent-table", DataTable)
            table.add_column("ID", width=8)
            table.add_column("Name", width=30)
            table.add_column("Status", width=10)

            self.load_agents_into_table(table)
            table.focus()

        except Exception as e:
            logger.error(f"AgentBrowser on_mount failed: {e}", exc_info=True)
            self.update_status(f"Error: {str(e)}")

    def update_status(self, text: str) -> None:
        """Update status bar."""
        logger.info(f"Agent status: {text}")
        status = self.query_one(".agent-status", Static)
        status.update(text)

    def update_content_widget(self, lines: list[str]) -> None:
        """Helper to update the agent content widget with multiple lines."""
        content = self.query_one("#agent-content", Static)
        content.update("\n".join(lines))

    def on_data_table_row_highlighted(self, event) -> None:
        """Handle row selection in the table."""
        table = self.query_one("#agent-table", DataTable)
        if table.cursor_coordinate and self.agents_list:
            row_index = table.cursor_coordinate[0]
            if 0 <= row_index < len(self.agents_list):
                agent = self.agents_list[row_index]
                self.current_agent_id = agent["id"]
                self.update_details(agent)
            else:
                self.current_agent_id = None
                self.show_welcome_screen()
        else:
            self.current_agent_id = None
            self.show_welcome_screen()

    async def action_edit_agent(self) -> None:
        """Start editing the selected agent using new form."""
        if not self.current_agent_id:
            self.update_status("No agent selected")
            return

        agent = self.find_agent_by_id(self.current_agent_id)
        if not agent:
            self.update_status("Agent not found")
            return

        if agent["is_builtin"]:
            self.update_status("Cannot edit built-in agents")
            return

        full_agent = agent_registry.get_agent(self.current_agent_id)
        if not full_agent:
            self.update_status("Failed to load agent")
            return

        agent_data = {
            "id": self.current_agent_id,
            "name": full_agent.config.name,
            "display_name": full_agent.config.display_name,
            "description": full_agent.config.description,
            "category": full_agent.config.category,
            "system_prompt": full_agent.config.system_prompt,
            "user_prompt_template": full_agent.config.user_prompt_template,
        }

        await self.enter_agent_form_mode(edit_mode=True, agent_data=agent_data)

    async def action_new_agent(self) -> None:
        """Start interactive agent creation using tabbed form."""
        logger.info("action_new_agent called")

        try:
            await self.enter_agent_form_mode(edit_mode=False)
            logger.info("action_new_agent completed successfully")
        except Exception as e:
            logger.error(f"Error in action_new_agent: {e}", exc_info=True)
            self.update_status(f"Error: {str(e)}")

    async def action_delete_agent(self) -> None:
        """Start agent deletion with confirmation dialog."""
        if not self.current_agent_id:
            self.update_status("No agent selected")
            return

        agent = self.find_agent_by_id(self.current_agent_id)
        if not agent:
            self.update_status("Agent not found")
            return

        if agent["is_builtin"]:
            self.update_status("Cannot delete built-in agents")
            return

        from .agent_form import DeleteConfirmationDialog

        dialog = DeleteConfirmationDialog(
            agent_name=agent["name"],
            agent_display_name=agent["display_name"],
            usage_count=agent["usage_count"]
        )

        result = await self.app.push_screen_wait(dialog)

        if result:
            try:
                if agent_registry.delete_agent(self.current_agent_id, hard_delete=False):
                    self.update_status(f"✅ Deleted agent '{agent['display_name']}'")
                    self.current_agent_id = None
                    self.update_table()
                    self.show_welcome_screen()
                else:
                    self.update_status("❌ Failed to delete agent")
            except Exception as e:
                logger.error(f"Failed to delete agent: {e}", exc_info=True)
                self.update_status(f"❌ Error: {str(e)}")
        else:
            self.update_status("Agent deletion cancelled")

    async def on_key(self, event) -> None:
        """Handle key events."""
        if getattr(self, 'form_mode', False):
            return

    async def enter_agent_form_mode(self, edit_mode=False, agent_data=None) -> None:
        """Enter agent form mode."""
        logger.info(
            f"Entering agent form mode: edit_mode={edit_mode}, agent_data={agent_data}"
        )

        self.editing_agent_id = (
            agent_data.get("id") if agent_data and isinstance(agent_data, dict) else None
        )
        self.form_mode = True
        self.edit_mode = edit_mode

        try:
            content_container = self.query_one("#agent-preview-container", Vertical)
            logger.info(f"Found content container: {content_container}")
        except Exception as e:
            logger.error(f"Could not find content container: {e}")
            return

        try:
            for child in list(content_container.children):
                await child.remove()
            logger.info("Removed existing content children")
        except Exception as e:
            logger.error(f"Error removing content: {e}")

        try:
            from .agent_form import AgentForm
            logger.info("Creating AgentForm...")

            agent_form = AgentForm(
                self,
                agent_registry,
                edit_mode=edit_mode,
                agent_data=agent_data,
                id="agent-form"
            )
            logger.info(f"Created form: {agent_form}")

            logger.info("Mounting form...")
            await content_container.mount(agent_form)
            logger.info("Form mounted successfully")

            logger.info("Focusing form...")
            agent_form.focus()
            logger.info("Form focused")

        except Exception as e:
            logger.error(f"Error creating/mounting form: {e}", exc_info=True)
            error_widget = Static(
                f"[red]Failed to create agent form:[/red]\n{str(e)}\n\n"
                "Press ESC to cancel",
                id="agent-form"
            )
            await content_container.mount(error_widget)
            self.update_status(f"❌ Failed to create form: {str(e)}")

        action = "editing" if edit_mode else "creating"
        self.update_status(f"Agent {action} mode | Ctrl+S=save | ESC=cancel")

    async def exit_agent_form_mode(self) -> None:
        """Exit agent form mode and restore normal view."""
        self.form_mode = False
        self.edit_mode = False
        self.editing_agent_id = None

        content_container = self.query_one("#agent-preview-container", Vertical)

        try:
            agent_form = self.query_one("#agent-form")
            await agent_form.remove()
        except Exception as e:
            logger.error(f"Error removing agent form: {e}")

        try:
            content_scroll = ScrollableContainer(id="agent-preview")
            content_log = Static("", id="agent-content", markup=True)

            await content_container.mount(content_scroll)
            await content_scroll.mount(content_log)
            logger.info("Recreated content area")
        except Exception as e:
            logger.error(f"Error recreating content: {e}")

        self.update_table()

        if self.current_agent_id:
            if self.select_agent_by_id(self.current_agent_id):
                selected_agent = self.find_agent_by_id(self.current_agent_id)
                if selected_agent:
                    self.update_details(selected_agent)
                else:
                    self.show_welcome_screen()
            else:
                self.show_welcome_screen()
        else:
            self.show_welcome_screen()

        table = self.query_one("#agent-table", DataTable)
        table.focus()

        if self.current_agent_id:
            self.on_data_table_row_highlighted(None)

    async def save_agent_form(self) -> None:
        """Save agent form data - called by the tabbed form."""
        try:
            agent_form = self.query_one("#agent-form")
            form_data = agent_form.get_form_data()

            if not form_data.get("name", "").strip():
                self.update_status("❌ Agent name is required")
                return
            if not form_data.get("display_name", "").strip():
                self.update_status("❌ Display name is required")
                return

            form_data.update({
                "allowed_tools": ["Read", "Grep", "Glob"],
                "timeout_seconds": 3600,
                "created_by": "user"
            })

            if self.edit_mode:
                agent_id = self.editing_agent_id
                if agent_registry.update_agent(agent_id, form_data):
                    self.update_status(f"✅ Updated agent '{form_data['display_name']}'")
                    self.current_agent_id = agent_id
                    await self.exit_agent_form_mode()
                else:
                    self.update_status("❌ Failed to update agent")
            else:
                agent_id = agent_registry.create_agent(form_data)
                self.update_status(
                    f"✅ Created agent '{form_data['display_name']}' (ID: {agent_id})"
                )
                self.current_agent_id = agent_id
                await self.exit_agent_form_mode()

        except Exception as e:
            logger.error(f"Error saving agent form: {e}", exc_info=True)
            self.update_status(f"❌ Error: {str(e)}")

    async def cancel_agent_form(self) -> None:
        """Cancel agent form - called by the tabbed form."""
        action = "edit" if self.edit_mode else "creation"
        self.update_status(f"Agent {action} cancelled")
        await self.exit_agent_form_mode()

    def action_save_and_exit_edit(self) -> None:
        """Save and exit edit mode - called by VimEditTextArea."""
        try:
            self.call_after_refresh(self._async_save_agent_form)
        except Exception as e:
            logger.error(f"Error in action_save_and_exit_edit: {e}")
            try:
                import asyncio
                asyncio.create_task(self.save_agent_form())
            except Exception as fallback_e:
                logger.error(f"Fallback save also failed: {fallback_e}")
                self.update_status("❌ Failed to save agent form")

    def _async_save_agent_form(self) -> None:
        """Async wrapper for save_agent_form."""
        import asyncio
        asyncio.create_task(self.save_agent_form())
