"""Generic agent implementation that executes via Claude."""

import subprocess
import json
import os
import tempfile
import time
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from .base import Agent, AgentContext, AgentResult
from ..models.documents import get_document, save_document
from ..utils.logging import get_logger
from ..utils.structured_logger import StructuredLogger, ProcessType
from ..commands.claude_execute import format_claude_output, format_timestamp

logger = get_logger(__name__)


class GenericAgent(Agent):
    """Generic agent that executes via Claude with configured constraints."""
    
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute agent using Claude process."""
        start_time = datetime.now()
        
        try:
            # Build the full prompt
            full_prompt = self._build_full_prompt(context)
            
            # Write prompt to temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                prompt_file = f.name
                f.write(full_prompt)
            
            # Prepare Claude command using same format as claude_execute.py
            cmd = [
                "claude",
                "--print", full_prompt,
                "--allowedTools", ",".join(self.config.allowed_tools),
                "--output-format", "stream-json",
                "--model", "claude-sonnet-4-20250514",  # Force Sonnet 4 as default
                "--verbose"
            ]
            
            logger.info(f"Executing agent {self.config.name} with command: {' '.join(cmd)}")
            
            # Set up log file path
            log_file = Path(context.log_file) if context.log_file else Path(context.working_dir) / "agent.log"
            
            # Write initial header like execute system does
            with open(log_file, 'a') as f:
                f.write(f"{format_timestamp()} 🤖 Starting agent execution: {self.config.display_name}\n")
                f.write(f"{format_timestamp()} 🔧 Tools: {', '.join(self.config.allowed_tools)}\n")
            
            # Execute Claude
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # Combine stderr into stdout
                text=True,
                bufsize=0,  # Unbuffered
                universal_newlines=True,
                cwd=context.working_dir,
                env={**os.environ, 'PYTHONUNBUFFERED': '1'}
            )
            
            # Stream output to log file with pretty formatting
            output_lines = []
            with open(log_file, 'a') as log_handle:
                while True:
                    line = process.stdout.readline()
                    if not line and process.poll() is not None:
                        break
                    if line:
                        output_lines.append(line.rstrip())
                        stripped = line.strip()
                        
                        # Use format_claude_output for pretty formatting (like execute system)
                        if stripped:
                            formatted = format_claude_output(stripped, time.time())
                            if formatted:
                                log_handle.write(formatted + "\n")
                            else:
                                # Fallback for non-JSON lines
                                log_handle.write(line)
                        
                        log_handle.flush()
            
            stdout = '\n'.join(output_lines)
            stderr = ""  # Already combined with stdout
            
            # Clean up prompt file
            os.unlink(prompt_file)
            
            # Calculate execution time
            execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            if process.returncode == 0:
                # Parse output and create documents
                output_doc_ids = await self._save_outputs(context, stdout)
                
                # Extract tools used from output (simplified for now)
                tools_used = self._extract_tools_used(stdout)
                
                return AgentResult(
                    status='completed',
                    output_doc_ids=output_doc_ids,
                    tools_used=tools_used,
                    execution_time_ms=execution_time_ms,
                    metadata={
                        'stdout_length': len(stdout),
                        'exit_code': 0
                    }
                )
            else:
                error_msg = stderr or stdout or f"Process exited with code {process.returncode}"
                logger.error(f"Agent execution failed: {error_msg}")
                
                return AgentResult(
                    status='failed',
                    error_message=error_msg,
                    execution_time_ms=execution_time_ms,
                    metadata={
                        'exit_code': process.returncode,
                        'stderr': stderr
                    }
                )
                
        except FileNotFoundError:
            error_msg = "Claude command not found. Make sure Claude Code is installed."
            logger.error(error_msg)
            return AgentResult(
                status='failed',
                error_message=error_msg,
                execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000)
            )
            
        except Exception as e:
            error_msg = f"Agent execution error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return AgentResult(
                status='failed',
                error_message=error_msg,
                execution_time_ms=int((datetime.now() - start_time).total_seconds() * 1000)
            )
    
    def _build_full_prompt(self, context: AgentContext) -> str:
        """Build complete prompt including system prompt and context."""
        parts = []
        
        # Add system prompt
        parts.append("# System Instructions")
        parts.append(self.config.system_prompt)
        parts.append("")
        
        # Add tool restrictions if any
        if self.config.allowed_tools:
            parts.append("# Allowed Tools")
            parts.append(f"You may ONLY use the following tools: {', '.join(self.config.allowed_tools)}")
            parts.append("")
        
        # Add context documents if configured
        if context.context_docs and self.config.include_doc_content:
            parts.append("# Context Documents")
            parts.append("")
            
            for doc_id in context.context_docs[:self.config.max_context_docs]:
                try:
                    doc = get_document(doc_id)
                    if doc:
                        parts.append(f"## Document #{doc.id}: {doc.title}")
                        parts.append(doc.content)
                        parts.append("")
                except Exception as e:
                    logger.warning(f"Failed to load context document {doc_id}: {e}")
        
        # Add user prompt
        parts.append("# Task")
        
        # Prepare template variables
        template_vars = dict(context.variables)  # Start with any provided variables
        
        if context.input_type == 'document' and context.input_doc_id:
            try:
                doc = get_document(context.input_doc_id)
                if doc:
                    template_vars.update({
                        'content': doc.content,
                        'title': doc.title,
                        'doc_id': doc.id
                    })
            except Exception as e:
                logger.warning(f"Failed to load input document {context.input_doc_id}: {e}")
        elif context.input_type == 'query':
            template_vars['query'] = context.input_query
        
        # Format the user prompt with variables
        user_prompt = self.format_prompt(**template_vars)
        parts.append(user_prompt)
        
        # Add output format instructions if specified
        if self.config.output_format:
            parts.append("")
            parts.append("# Output Format")
            parts.append(f"Please format your output as: {self.config.output_format}")
        
        return "\n".join(parts)
    
    async def _save_outputs(self, context: AgentContext, output: str) -> List[int]:
        """Save agent outputs as EMDX documents."""
        if not self.config.save_outputs or not output.strip():
            return []
        
        doc_ids = []
        
        try:
            # Generate title for output document
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
            
            if context.input_type == 'document' and context.input_doc_id:
                try:
                    input_doc = get_document(context.input_doc_id)
                    base_title = f"{self.config.display_name}: {input_doc.title}"
                except:
                    base_title = f"{self.config.display_name} Output"
            elif context.input_type == 'query' and context.input_query:
                query_preview = context.input_query[:50] + "..." if len(context.input_query) > 50 else context.input_query
                base_title = f"{self.config.display_name}: {query_preview}"
            else:
                base_title = f"{self.config.display_name} Output"
            
            title = f"{base_title} - {timestamp}"
            
            # Prepare tags
            tags = list(self.config.output_tags or [])
            
            # Add agent category as tag
            category_tag_map = {
                'generation': '✨',  # feature/new
                'analysis': '🔍',    # analysis
                'research': '📚',    # docs
                'maintenance': '🔧'  # refactor
            }
            if self.config.category in category_tag_map:
                tags.append(category_tag_map[self.config.category])
            
            # Save the document
            doc_id = save_document(
                title=title,
                content=output,
                tags=tags,
                parent_id=context.input_doc_id if context.input_type == 'document' else None
            )
            
            doc_ids.append(doc_id)
            logger.info(f"Saved agent output as document #{doc_id}: {title}")
            
        except Exception as e:
            logger.error(f"Failed to save agent output: {e}", exc_info=True)
        
        return doc_ids
    
    def _extract_tools_used(self, output: str) -> List[str]:
        """Extract list of tools used from Claude output."""
        tools = []
        
        # Simple pattern matching for now
        # In a real implementation, we'd parse Claude's structured output
        tool_patterns = [
            "Using tool:",
            "Tool:",
            "Calling tool:",
            "Executing tool:"
        ]
        
        lines = output.split('\n')
        for line in lines:
            for pattern in tool_patterns:
                if pattern in line:
                    # Extract tool name (simplified)
                    parts = line.split(pattern)
                    if len(parts) > 1:
                        tool_name = parts[1].strip().split()[0].strip('`"\'')
                        if tool_name and tool_name not in tools:
                            tools.append(tool_name)
        
        return tools


class SimplePromptAgent(GenericAgent):
    """Simplified agent that just runs a prompt without the full agent framework."""
    
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute a simple prompt via Claude."""
        # For simple prompts, we just use the user prompt template directly
        prompt = self.format_prompt(**context.variables)
        
        # Save prompt as temporary context
        temp_context = AgentContext(
            execution_id=context.execution_id,
            working_dir=context.working_dir,
            input_type='query',
            input_query=prompt,
            context_docs=[],
            variables={}
        )
        
        # Use parent's execute method with simplified prompt
        self.config.system_prompt = ""  # No system prompt for simple mode
        self.config.user_prompt_template = prompt
        
        return await super().execute(temp_context)