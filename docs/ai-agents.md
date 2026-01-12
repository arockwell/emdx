# EMDX Agent System

## Overview

The EMDX Agent System brings AI-powered task automation directly into your knowledge base. Similar to Claude Code's `/agents` feature, EMDX agents can perform complex, multi-step tasks while leveraging your entire knowledge base.

## Quick Start

```bash
# List available agents
emdx agent list

# Run an agent on a document (background with monitoring)
emdx agent run doc-generator --doc 123 --background
emdx log --live  # Monitor real-time progress

# Run an agent with a query (background with monitoring)  
emdx agent run code-reviewer --query "Review the auth implementation" --background
emdx log --live  # See what the agent is doing

# Create a custom agent
emdx agent create --name my-analyzer --prompt analyzer.md --category analysis
```

## Built-in Agents

### Documentation Generator
- **Name**: `doc-generator`
- **Category**: generation
- **Purpose**: Analyzes code and generates comprehensive documentation
- **Tools**: Glob, Grep, Read, Write, Task

### Code Reviewer
- **Name**: `code-reviewer`
- **Category**: analysis
- **Purpose**: Reviews code changes and provides feedback
- **Tools**: Read, Grep, Glob

## Creating Custom Agents

### Prompt File Format

Create a prompt file with system and user sections separated by `---`:

```markdown
You are an expert Python developer specializing in testing.
Your role is to analyze code and generate comprehensive test cases.
---
Analyze {{target}} and generate unit tests.
Focus on edge cases and error handling.
```

### Create Agent Command

```bash
emdx agent create \
  --name test-generator \
  --display-name "Test Generator" \
  --description "Generates comprehensive test cases" \
  --category generation \
  --prompt test-prompt.md \
  --tool Read --tool Write --tool Grep \
  --tag test --tag generated
```

## Agent Execution

### Input Types

1. **Document Input**: Process an existing EMDX document
   ```bash
   emdx agent run doc-generator --doc 456
   ```

2. **Query Input**: Process a text query
   ```bash
   emdx agent run code-reviewer --query "Review security in auth.py"
   ```

3. **Template Variables**: Pass custom variables
   ```bash
   emdx agent run doc-generator --doc 456 --var doc_type=API --var format=OpenAPI
   ```

### Background Execution

Run agents in the background for long tasks with real-time monitoring:

```bash
# Start agent in background
emdx agent run doc-generator --doc 789 --background
# ✓ Agent started in background (execution #123)
# Use emdx log to monitor progress

# Monitor live output to see what the agent is doing
emdx log --live
# Shows real-time formatted output with timestamps and emojis:
# [10:30:15] 🤖 Starting agent execution: Documentation Generator
# [10:30:16] 🔧 Tools: Glob, Grep, Read, Write, Task  
# [10:30:18] 🚀 Claude Code session started
# [10:30:22] 📋 Using tool: Glob
# [10:30:25] 📖 Using tool: Read
```

## Managing Agents

### View Agent Details
```bash
emdx agent info doc-generator
```

### Edit Agent Configuration
```bash
emdx agent edit my-agent --tool NewTool --timeout 7200
```

### Delete Agent
```bash
emdx agent delete my-agent  # Soft delete (deactivate)
emdx agent delete my-agent --hard  # Permanent delete
```

### View Usage Statistics
```bash
emdx agent stats  # Overall stats
emdx agent stats doc-generator  # Specific agent stats
```

## Architecture

### Database Schema

The agent system adds four new tables:
- **agents**: Agent configurations and prompts
- **agent_executions**: Execution history and metrics
- **agent_pipelines**: Multi-agent workflow definitions
- **agent_templates**: Shareable agent blueprints

### Execution Flow

1. Agent loads configuration from database
2. Executor creates isolated working directory
3. Context documents loaded based on configuration
4. Prompt formatted with variables and context
5. Claude executes with configured tool restrictions
6. Outputs saved as EMDX documents with tags
7. Execution metrics tracked for analysis

### Integration Points

- Leverages existing Claude execution infrastructure
- Uses EMDX tagging system for output organization
- Integrates with document relationships (parent/child)
- Compatible with existing log browser

## Planned Features

> **Note:** These features are planned but not yet implemented. The database schema includes tables for these features (`agent_pipelines`, `agent_templates`) to support future development.

### Agent Pipelines (Planned)
Chain multiple agents for complex workflows:
```bash
# Future syntax - not yet available
emdx agent pipeline create "full-analysis" \
  --step "code-analyzer" \
  --step "test-suggester" \
  --step "doc-generator"
```

### Agent Templates (Planned)
Share and reuse agent configurations:
```bash
# Future syntax - not yet available
emdx agent template export my-agent > my-agent.json
emdx agent template import colleague-agent.json
```

**Current workaround:** Export agent configurations manually from the database or version control your prompt files.


## Technical Details

### Agent Base Class
```python
class Agent:
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent with given context."""
        # Custom execution logic goes here
        return AgentResult(status='completed')
```

### Creating Custom Agent Types
```python
from emdx.agents import Agent, agent_registry

class MyCustomAgent(Agent):
    async def execute(self, context):
        # Custom execution logic
        return AgentResult(status='completed')

# Register the agent type
agent_registry.register('my-custom-type', MyCustomAgent)
```

### Tool Configuration
Agents have flexible tool access that can be customized per use case:

```bash
# Default tools for analysis agents
emdx agent run code-reviewer --doc 123  # Uses: Read, Grep, Glob

# Add tools for more powerful agents
emdx agent run doc-generator --doc 123 --tools "Read,Write,Bash,Glob,Grep,Task"

# Create agents with custom tool sets
emdx agent create --name security-scanner \
  --tools "Read,Grep,Bash,WebSearch,Task" \
  --description "Security analysis with web research"
```

Tool restrictions are minimal by design - agents can be granted most tools based on trust level and use case.

## Best Practices

1. **Start with built-in agents** to understand the system
2. **Use specific tool sets** - only include necessary tools
3. **Tag outputs appropriately** for organization
4. **Monitor execution logs** for debugging
5. **Set reasonable timeouts** for long-running tasks
6. **Test agents thoroughly** before production use
7. **Version your prompts** in version control

## Troubleshooting

### Agent Not Found
```bash
emdx agent list --all  # Include inactive agents
```

### Execution Fails
```bash
emdx log  # View execution logs
emdx exec list --limit 5  # Check recent executions
```

### Tool Access Denied
Ensure the tool is in the agent's `allowed_tools` list.

### Output Not Saved
Check that `save_outputs` is true and `output_format` is set correctly.