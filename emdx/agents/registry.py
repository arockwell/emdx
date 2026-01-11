"""Agent registry for managing agent types and instances."""

from typing import Dict, Type, Optional, List, Any
import json
from ..database.connection import db_connection
from .base import Agent, AgentConfig
from ..utils.logging import get_logger

logger = get_logger(__name__)


class AgentRegistry:
    """Registry for managing agent types and instances."""
    
    _instance = None
    _agents: Dict[str, Type[Agent]] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def register(self, name: str, agent_class: Type[Agent]) -> None:
        """Register an agent implementation."""
        if not issubclass(agent_class, Agent):
            raise ValueError(f"{agent_class} must be a subclass of Agent")
        
        self._agents[name] = agent_class
        logger.info(f"Registered agent: {name}")
    
    def get_agent(self, agent_id: int) -> Optional[Agent]:
        """Load agent from database and instantiate."""
        with db_connection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM agents WHERE id = ? AND is_active = TRUE
            """, (agent_id,))
            row = cursor.fetchone()
            
            if not row:
                logger.warning(f"Agent {agent_id} not found or inactive")
                return None
                
            # Convert row to dict
            row_dict = dict(row)
            config = AgentConfig.from_db_row(row_dict)
            
            # Use specific implementation if registered, else use generic
            from .generic import GenericAgent  # Import here to avoid circular imports
            agent_class = self._agents.get(config.name, GenericAgent)
            
            logger.info(f"Instantiating agent {config.name} with class {agent_class.__name__}")
            return agent_class(config)
    
    def get_agent_by_name(self, name: str) -> Optional[Agent]:
        """Load agent by name from database and instantiate."""
        with db_connection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM agents WHERE name = ? AND is_active = TRUE
            """, (name,))
            row = cursor.fetchone()
            
            if not row:
                logger.warning(f"Agent '{name}' not found or inactive")
                return None
                
            # Convert row to dict
            row_dict = dict(row)
            config = AgentConfig.from_db_row(row_dict)
            
            # Use specific implementation if registered, else use generic
            from .generic import GenericAgent  # Import here to avoid circular imports
            agent_class = self._agents.get(config.name, GenericAgent)
            
            logger.info(f"Instantiating agent {config.name} with class {agent_class.__name__}")
            return agent_class(config)
    
    def list_agents(self, category: Optional[str] = None, include_inactive: bool = False) -> List[Dict]:
        """List all available agents."""
        with db_connection.get_connection() as conn:
            query_parts = ["SELECT * FROM agents"]
            params = []
            conditions = []
            
            if not include_inactive:
                conditions.append("is_active = TRUE")
            
            if category:
                conditions.append("category = ?")
                params.append(category)
            
            if conditions:
                query_parts.append("WHERE " + " AND ".join(conditions))
            
            query_parts.append("ORDER BY category, name")
            query = " ".join(query_parts)
            
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            agents = []
            for row in cursor.fetchall():
                row_dict = dict(row)
                # Parse JSON fields for display
                row_dict['allowed_tools'] = json.loads(row_dict['allowed_tools']) if row_dict['allowed_tools'] else []
                if row_dict.get('output_tags'):
                    row_dict['output_tags'] = json.loads(row_dict['output_tags'])
                agents.append(row_dict)
            
            return agents
    
    def create_agent(self, config: Dict[str, Any]) -> int:
        """Create a new agent in the database."""
        with db_connection.get_connection() as conn:
            cursor = conn.cursor()
            
            # Convert lists to JSON
            allowed_tools_json = json.dumps(config.get('allowed_tools', []))
            output_tags_json = json.dumps(config.get('output_tags', [])) if config.get('output_tags') else None
            tool_restrictions_json = json.dumps(config.get('tool_restrictions', {})) if config.get('tool_restrictions') else None
            
            cursor.execute("""
                INSERT INTO agents (
                    name, display_name, description, category,
                    system_prompt, user_prompt_template,
                    allowed_tools, tool_restrictions,
                    max_iterations, timeout_seconds, requires_confirmation,
                    max_context_docs, context_search_query, include_doc_content,
                    output_format, save_outputs, output_tags,
                    created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                config['name'],
                config['display_name'],
                config['description'],
                config['category'],
                config['system_prompt'],
                config['user_prompt_template'],
                allowed_tools_json,
                tool_restrictions_json,
                config.get('max_iterations', 10),
                config.get('timeout_seconds', 3600),
                config.get('requires_confirmation', False),
                config.get('max_context_docs', 5),
                config.get('context_search_query'),
                config.get('include_doc_content', True),
                config.get('output_format', 'markdown'),
                config.get('save_outputs', True),
                output_tags_json,
                config.get('created_by', 'unknown')
            ))
            
            agent_id = cursor.lastrowid
            conn.commit()
            
            logger.info(f"Created agent {config['name']} with ID {agent_id}")
            return agent_id
    
    def update_agent(self, agent_id: int, updates: Dict[str, Any]) -> bool:
        """Update an existing agent."""
        with db_connection.get_connection() as conn:
            cursor = conn.cursor()
            
            # Build update query dynamically
            set_parts = []
            values = []
            
            # Handle JSON fields
            if 'allowed_tools' in updates:
                set_parts.append("allowed_tools = ?")
                values.append(json.dumps(updates['allowed_tools']))
            
            if 'output_tags' in updates:
                set_parts.append("output_tags = ?")
                values.append(json.dumps(updates['output_tags']) if updates['output_tags'] else None)
            
            if 'tool_restrictions' in updates:
                set_parts.append("tool_restrictions = ?")
                values.append(json.dumps(updates['tool_restrictions']) if updates['tool_restrictions'] else None)
            
            # Handle other fields
            simple_fields = [
                'display_name', 'description', 'category',
                'system_prompt', 'user_prompt_template',
                'max_iterations', 'timeout_seconds', 'requires_confirmation',
                'max_context_docs', 'context_search_query', 'include_doc_content',
                'output_format', 'save_outputs'
            ]
            
            for field in simple_fields:
                if field in updates:
                    set_parts.append(f"{field} = ?")
                    values.append(updates[field])
            
            if not set_parts:
                return True  # Nothing to update
            
            # Always update updated_at
            set_parts.append("updated_at = CURRENT_TIMESTAMP")
            
            # Add agent_id for WHERE clause
            values.append(agent_id)
            
            query = f"UPDATE agents SET {', '.join(set_parts)} WHERE id = ?"
            cursor.execute(query, values)
            conn.commit()
            
            logger.info(f"Updated agent {agent_id}")
            return cursor.rowcount > 0
    
    def delete_agent(self, agent_id: int, hard_delete: bool = False) -> bool:
        """Delete an agent (soft delete by default)."""
        with db_connection.get_connection() as conn:
            cursor = conn.cursor()
            
            if hard_delete:
                cursor.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            else:
                cursor.execute(
                    "UPDATE agents SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (agent_id,)
                )
            
            conn.commit()
            logger.info(f"{'Hard' if hard_delete else 'Soft'} deleted agent {agent_id}")
            return cursor.rowcount > 0


# Global registry instance
agent_registry = AgentRegistry()