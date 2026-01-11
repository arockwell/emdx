#!/usr/bin/env python3
"""
Agent config handler module - handles agent details display and configuration.

Extracted from AgentBrowser to improve maintainability.
"""

import logging
from typing import Optional

from textual.widgets import Static

logger = logging.getLogger(__name__)


class AgentConfigHandlerMixin:
    """Mixin class providing agent configuration display functionality.

    This mixin should be used with a Widget that has:
    - agents_list: list - List of agent dictionaries
    - form_mode: bool - Whether form mode is active
    - An "#agent-details" Static widget
    - An "#agent-content" Static widget
    """

    def update_details(self, agent_info: dict) -> None:
        """Update the details panel with agent information.

        Args:
            agent_info: Dictionary containing agent data
        """
        details = self.query_one("#agent-details", Static)

        content_lines = [
            f"[bold yellow]Agent: {agent_info['display_name']}[/bold yellow]",
            f"ID: {agent_info['id']}",
            f"Category: {agent_info['category']}",
            f"Active: {agent_info['is_active']}",
            f"Usage: {agent_info['usage_count']} times"
        ]

        if agent_info['description']:
            content_lines.append(f"\n[dim]{agent_info['description']}[/dim]")

        details.update("\n".join(content_lines))

        self.update_agent_content(agent_info)

    def update_agent_content(self, agent_info: dict) -> None:
        """Update the main RHS content area with full agent details.

        Args:
            agent_info: Dictionary containing agent data
        """
        if self.form_mode:
            return

        try:
            content = self.query_one("#agent-content", Static)
        except Exception:
            return

        full_agent = self._load_full_agent(agent_info['id'])

        lines = self._build_agent_content_lines(agent_info, full_agent)
        content.update("\n".join(lines))

    def _load_full_agent(self, agent_id: int) -> Optional[object]:
        """Load full agent configuration from registry.

        Args:
            agent_id: The agent ID

        Returns:
            Full agent object or None
        """
        from ..agents.registry import agent_registry

        if agent_registry and agent_id:
            try:
                return agent_registry.get_agent(agent_id)
            except Exception as e:
                logger.error(f"Failed to load full agent: {e}")
        return None

    def _build_agent_content_lines(self, agent_info: dict,
                                    full_agent: Optional[object]) -> list[str]:
        """Build content lines for agent display.

        Args:
            agent_info: Basic agent info dictionary
            full_agent: Full agent object or None

        Returns:
            List of formatted content lines
        """
        lines = []

        # Header
        lines.append(f"[bold cyan]🤖 {agent_info['display_name']}[/bold cyan]")
        lines.append("=" * 60)
        lines.append("")

        # Basic info
        lines.append(f"[bold]Name:[/bold] {agent_info.get('name', 'N/A')}")
        lines.append(f"[bold]Category:[/bold] {agent_info['category']}")
        lines.append(
            f"[bold]Status:[/bold] "
            f"{'Active' if agent_info['is_active'] else 'Inactive'}"
        )
        lines.append(f"[bold]Usage:[/bold] {agent_info['usage_count']} executions")
        lines.append("")

        # Description
        if agent_info.get('description'):
            lines.append("[bold]Description:[/bold]")
            lines.append(f"[dim]{agent_info['description']}[/dim]")
            lines.append("")

        # Full configuration if available
        if full_agent and hasattr(full_agent, 'config'):
            lines.extend(self._build_config_lines(full_agent.config))
        else:
            lines.append("[dim]Full configuration not available[/dim]")

        lines.append("")
        lines.append("─" * 60)
        lines.append("[dim]Press 'e' to edit • 'd' to delete • 'r' to run[/dim]")

        return lines

    def _build_config_lines(self, config: object) -> list[str]:
        """Build configuration display lines.

        Args:
            config: Agent configuration object

        Returns:
            List of formatted config lines
        """
        lines = []

        # System prompt
        lines.append("[bold]System Prompt:[/bold]")
        lines.append("[green]" + "─" * 50 + "[/green]")
        system_prompt = getattr(config, 'system_prompt', 'N/A')
        if len(system_prompt) > 200:
            lines.append(f"{system_prompt[:200]}...")
            lines.append(f"[dim](truncated - {len(system_prompt)} chars total)[/dim]")
        else:
            lines.append(system_prompt)
        lines.append("")

        # User prompt template
        lines.append("[bold]User Prompt Template:[/bold]")
        lines.append("[blue]" + "─" * 50 + "[/blue]")
        user_prompt = getattr(config, 'user_prompt_template', 'N/A')
        lines.append(user_prompt)
        lines.append("")

        # Tools and settings
        lines.append("[bold]Configuration:[/bold]")
        allowed_tools = getattr(config, 'allowed_tools', [])
        lines.append(f"• [bold]Allowed Tools:[/bold] {', '.join(allowed_tools)}")
        lines.append(
            f"• [bold]Timeout:[/bold] "
            f"{getattr(config, 'timeout_seconds', 3600)} seconds"
        )
        lines.append(
            f"• [bold]Created By:[/bold] {getattr(config, 'created_by', 'Unknown')}"
        )

        if hasattr(config, 'created_at'):
            lines.append(f"• [bold]Created:[/bold] {config.created_at}")

        return lines

    def show_welcome_screen(self) -> None:
        """Show welcome screen when no agent is selected."""
        logger.info("Showing welcome screen")
        content = self.query_one("#agent-content", Static)

        lines = self._build_welcome_lines()
        content.update("\n".join(lines))

    def _build_welcome_lines(self) -> list[str]:
        """Build welcome screen content lines.

        Returns:
            List of formatted welcome lines
        """
        lines = []

        # Header
        lines.append("[bold cyan]🤖 EMDX Agent System[/bold cyan]")
        lines.append("=" * 60)
        lines.append("")

        # Overview
        lines.append("[bold]Welcome to the Agent Management Interface[/bold]")
        lines.append("")
        lines.append("Agents are specialized AI assistants that can help with:")
        lines.append("• [green]Research[/green] - Information gathering and analysis")
        lines.append("• [blue]Generation[/blue] - Creating content and code")
        lines.append("• [yellow]Analysis[/yellow] - Code review and examination")
        lines.append("• [magenta]Maintenance[/magenta] - System upkeep and optimization")
        lines.append("")

        # Quick stats
        agent_count = len(self.agents_list) if self.agents_list else 0
        active_count = sum(
            1 for a in self.agents_list if a.get('is_active', False)
        ) if self.agents_list else 0
        builtin_count = sum(
            1 for a in self.agents_list if a.get('is_builtin', False)
        ) if self.agents_list else 0

        lines.append("[bold]System Status:[/bold]")
        lines.append(f"• Total Agents: {agent_count}")
        lines.append(f"• Active Agents: {active_count}")
        lines.append(f"• Built-in Agents: {builtin_count}")
        lines.append("")

        # Getting started
        lines.append("[bold]Getting Started:[/bold]")
        lines.append("")
        if agent_count == 0:
            lines.append(
                "🚀 [bold yellow]No agents found - Create your first agent![/bold yellow]"
            )
            lines.append("")
            lines.append("1. Press [bold green]'n'[/bold green] to create a new agent")
            lines.append("2. Fill in the agent details")
            lines.append("3. Press [bold green]Ctrl+S[/bold green] or click Create")
        else:
            lines.append(
                "📋 [bold green]Select an agent[/bold green] from the table to view details"
            )
            lines.append("")
            lines.append("• Use [bold]j/k[/bold] or arrow keys to navigate")
            lines.append("• Press [bold green]'n'[/bold green] to create a new agent")
            lines.append("• Press [bold blue]'e'[/bold blue] to edit the selected agent")
            lines.append("• Press [bold red]'d'[/bold red] to delete the selected agent")
            lines.append(
                "• Press [bold yellow]'r'[/bold yellow] to run the selected agent"
            )

        lines.append("")
        lines.append("─" * 60)

        # Key bindings reminder
        lines.append("[bold]Key Bindings:[/bold]")
        lines.append("• [green]n[/green] - New agent")
        lines.append("• [blue]e[/blue] - Edit agent")
        lines.append("• [red]d[/red] - Delete agent")
        lines.append("• [yellow]r[/yellow] - Run agent")
        lines.append("• [cyan]j/k[/cyan] - Navigate")
        lines.append("• [magenta]g/G[/magenta] - Go to top/bottom")

        lines.append("")
        lines.append("─" * 60)
        lines.append("[dim]Select an agent to see its configuration and details[/dim]")

        return lines
