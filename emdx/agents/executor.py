"""Agent executor for managing agent execution lifecycle."""

import asyncio
import os
import tempfile
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from .base import AgentContext, AgentResult
from .registry import agent_registry
from ..models.executions import create_execution, update_execution_status
from ..models.documents import get_document, save_document
from ..models.tags import search_by_tags
from ..database.connection import db_connection
from ..database.search import search_documents
from ..utils.logging import get_logger
from ..utils.text_formatting import truncate_title

logger = get_logger(__name__)


class AgentExecutor:
    """Executes agents with proper isolation and tracking."""
    
    async def execute_agent(
        self,
        agent_id: int,
        input_type: str,
        input_doc_id: Optional[int] = None,
        input_query: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        background: bool = False
    ) -> int:
        """Execute an agent and return execution ID."""
        
        # Load agent
        agent = agent_registry.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")
        
        # Validate input
        if input_type == 'document' and not input_doc_id:
            raise ValueError("Document ID required for document input type")
        elif input_type == 'query' and not input_query:
            raise ValueError("Query required for query input type")
        elif input_type not in ['document', 'query', 'pipeline']:
            raise ValueError(f"Invalid input type: {input_type}")
        
        # Create execution record
        doc_title = f"Agent: {agent.config.display_name}"
        if input_doc_id:
            try:
                doc = get_document(input_doc_id)
                doc_title += f" - {doc.title}"
            except (KeyError, ValueError) as e:
                logger.debug(f"Could not fetch document {input_doc_id} for title: {e}")
                doc_title += f" - Document #{input_doc_id}"
        elif input_query:
            query_preview = truncate_title(input_query)
            doc_title += f" - {query_preview}"
            
        # Create working directory
        work_dir = tempfile.mkdtemp(prefix=f"emdx-agent-{agent.config.name}-")
        
        # Create log file path
        log_dir = Path.home() / ".config" / "emdx" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"agent-{agent_id}-{datetime.now().timestamp()}.log"
        
        # Create execution record
        execution_id = create_execution(
            doc_id=input_doc_id or 0,
            doc_title=doc_title,
            log_file=str(log_file),
            working_dir=work_dir
        )
        
        # Create agent execution record
        agent_execution_id = self._create_agent_execution(
            agent_id=agent_id,
            execution_id=execution_id,
            input_type=input_type,
            input_doc_id=input_doc_id,
            input_query=input_query
        )
        
        # Load context documents if configured
        context_docs = []
        if agent.config.max_context_docs > 0:
            context_docs = await self._load_context_docs(
                agent.config,
                input_doc_id,
                input_query
            )
        
        # Create context
        context = AgentContext(
            execution_id=execution_id,
            working_dir=work_dir,
            input_type=input_type,
            input_doc_id=input_doc_id,
            input_query=input_query,
            context_docs=context_docs,
            variables=variables or {},
            log_file=str(log_file)
        )
        
        if background:
            # Use the existing claude execute detached infrastructure
            self._execute_with_claude_detached(agent, context, execution_id)
            logger.info(f"Launched agent {agent.config.name} in background (execution #{execution_id})")
        else:
            # Use the existing claude execute infrastructure for synchronous execution too
            self._execute_with_claude_sync(agent, context, execution_id)
            
        return execution_id
    
    async def execute_agent_by_name(
        self,
        agent_name: str,
        input_type: str,
        input_doc_id: Optional[int] = None,
        input_query: Optional[str] = None,
        variables: Optional[Dict[str, Any]] = None,
        background: bool = False
    ) -> int:
        """Execute an agent by name and return execution ID."""
        
        # Look up agent ID by name
        with db_connection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM agents WHERE name = ? AND is_active = TRUE", (agent_name,))
            row = cursor.fetchone()
            
            if not row:
                raise ValueError(f"Agent '{agent_name}' not found")
            
            agent_id = row['id']
        
        return await self.execute_agent(
            agent_id=agent_id,
            input_type=input_type,
            input_doc_id=input_doc_id,
            input_query=input_query,
            variables=variables,
            background=background
        )
    
    async def _run_agent(
        self,
        agent,
        context: AgentContext,
        agent_execution_id: int,
        execution_id: int
    ):
        """Run the agent and update records."""
        start_time = datetime.now()
        
        try:
            # Update status to running
            self._update_agent_execution(agent_execution_id, {'status': 'running'})
            logger.info(f"Starting agent execution for {agent.config.name}")
            
            # Execute agent
            result = await agent.execute(context)
            
            # Update records with results
            execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            updates = {
                'status': result.status,
                'completed_at': datetime.now(),
                'output_doc_ids': json.dumps(result.output_doc_ids),
                'error_message': result.error_message,
                'execution_time_ms': execution_time_ms,
                'total_tokens_used': result.total_tokens_used,
                'iterations_used': result.iterations_used,
                'tools_used': json.dumps(result.tools_used),
                'context_doc_ids': json.dumps(context.context_docs or [])
            }
            
            self._update_agent_execution(agent_execution_id, updates)
            
            # Update main execution status
            update_execution_status(
                execution_id,
                'completed' if result.status == 'completed' else 'failed',
                0 if result.status == 'completed' else 1
            )
            
            # Update agent usage stats
            self._update_agent_stats(agent.config.id, result.status == 'completed')
            
            logger.info(
                f"Agent execution completed for {agent.config.name}: "
                f"{result.status} in {execution_time_ms}ms"
            )
            
        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            
            execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            self._update_agent_execution(agent_execution_id, {
                'status': 'failed',
                'completed_at': datetime.now(),
                'error_message': str(e),
                'execution_time_ms': execution_time_ms
            })
            
            update_execution_status(execution_id, 'failed', 1)
            self._update_agent_stats(agent.config.id, False)
    
    async def _load_context_docs(
        self,
        config,
        input_doc_id: Optional[int],
        input_query: Optional[str]
    ) -> List[int]:
        """Load relevant context documents."""
        context_docs = []
        
        try:
            if config.context_search_query:
                # Use configured search query template
                search_query = config.context_search_query
                
                # Replace variables in search query
                if input_doc_id:
                    try:
                        doc = get_document(input_doc_id)
                        search_query = search_query.replace("{{title}}", doc.title)
                        search_query = search_query.replace("{{project}}", doc.project or "")
                    except (KeyError, ValueError) as e:
                        logger.debug(f"Could not fetch document {input_doc_id} for template vars: {e}")
                
                if input_query:
                    search_query = search_query.replace("{{query}}", input_query)
                
                # Perform search using the proper search function
                try:
                    search_results = search_documents(
                        query=search_query,
                        limit=config.max_context_docs
                    )
                    context_docs = [doc['id'] for doc in search_results]
                except Exception as e:
                    logger.warning(f"Search failed, falling back to recent documents: {e}")
                    # Fallback to recent documents if search fails
                    with db_connection.get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT id FROM documents
                            WHERE is_deleted = FALSE
                            ORDER BY accessed_at DESC
                            LIMIT ?
                        """, (config.max_context_docs,))
                        context_docs = [row['id'] for row in cursor.fetchall()]
            
            elif input_doc_id:
                # If no search query, try to find related documents
                # For now, just include the input document itself
                context_docs = [input_doc_id]
        
        except Exception as e:
            logger.warning(f"Failed to load context documents: {e}")
        
        return context_docs
    
    def _create_agent_execution(
        self,
        agent_id: int,
        execution_id: int,
        input_type: str,
        input_doc_id: Optional[int],
        input_query: Optional[str]
    ) -> int:
        """Create agent execution record."""
        with db_connection.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO agent_executions 
                (agent_id, execution_id, input_type, input_doc_id, input_query, status)
                VALUES (?, ?, ?, ?, ?, 'pending')
            """, (agent_id, execution_id, input_type, input_doc_id, input_query))
            
            agent_execution_id = cursor.lastrowid
            conn.commit()
            
            return agent_execution_id
    
    def _update_agent_execution(self, agent_execution_id: int, updates: Dict[str, Any]):
        """Update agent execution record."""
        with db_connection.get_connection() as conn:
            set_parts = []
            values = []
            
            for key, value in updates.items():
                set_parts.append(f"{key} = ?")
                values.append(value)
            
            if not set_parts:
                return
            
            values.append(agent_execution_id)
            query = f"UPDATE agent_executions SET {', '.join(set_parts)} WHERE id = ?"
            
            conn.execute(query, values)
            conn.commit()
    
    def _update_agent_stats(self, agent_id: int, success: bool):
        """Update agent usage statistics."""
        with db_connection.get_connection() as conn:
            if success:
                conn.execute("""
                    UPDATE agents 
                    SET usage_count = usage_count + 1,
                        success_count = success_count + 1,
                        last_used_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (agent_id,))
            else:
                conn.execute("""
                    UPDATE agents 
                    SET usage_count = usage_count + 1,
                        failure_count = failure_count + 1,
                        last_used_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (agent_id,))
            
            conn.commit()
    
    def _build_agent_prompt(self, agent, context: AgentContext) -> str:
        """Build the prompt for agent execution."""
        prompt = agent.format_prompt(**context.variables)
        if context.input_type == 'document' and context.input_doc_id:
            try:
                from ..models.documents import get_document
                doc = get_document(context.input_doc_id)
                if doc:
                    prompt = agent.format_prompt(content=doc.content, **context.variables)
            except Exception as e:
                logger.warning(f"Failed to load input document {context.input_doc_id}: {e}")
        elif context.input_type == 'query' and context.input_query:
            prompt = agent.format_prompt(query=context.input_query, **context.variables)
        return prompt
    
    def _execute_with_claude_detached(self, agent, context: AgentContext, execution_id: int) -> None:
        """Execute agent using the existing claude execute detached infrastructure."""
        from ..commands.claude_execute import execute_with_claude_detached
        from pathlib import Path
        
        prompt = self._build_agent_prompt(agent, context)
        
        # Use the existing claude execute detached function
        execute_with_claude_detached(
            task=prompt,
            execution_id=execution_id,
            log_file=Path(context.log_file),
            allowed_tools=agent.config.allowed_tools,
            working_dir=context.working_dir,
            doc_id=str(context.input_doc_id) if context.input_doc_id else None,
            context=None  # Agent context is different from execute context
        )
    
    def _execute_with_claude_sync(self, agent, context: AgentContext, execution_id: int) -> None:
        """Execute agent synchronously using the existing claude execute infrastructure."""
        from ..commands.claude_execute import execute_with_claude
        from pathlib import Path
        
        prompt = self._build_agent_prompt(agent, context)
        
        # Use the existing claude execute function
        execute_with_claude(
            task=prompt,
            execution_id=execution_id,
            log_file=Path(context.log_file),
            allowed_tools=agent.config.allowed_tools,
            verbose=True,
            working_dir=context.working_dir,
            doc_id=str(context.input_doc_id) if context.input_doc_id else None,
            context=None  # Agent context is different from execute context
        )


# Global executor instance
agent_executor = AgentExecutor()