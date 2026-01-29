# New Avenue: EMDX as MCP Server

## Executive Summary

Transforming EMDX into an MCP (Model Context Protocol) server would fundamentally change its position in the AI ecosystem. Instead of being a CLI tool that AI agents call via shell commands, EMDX would become **native infrastructure** that any MCP-compatible AI client can use directly. This is the difference between Claude shelling out to `emdx find` and Claude having EMDX knowledge as a first-class capability.

## What is MCP?

The **Model Context Protocol** is an open standard created by Anthropic in November 2024 that has achieved industry-wide adoption:

- **Adopted by**: OpenAI (March 2025), Google DeepMind (April 2025), Microsoft/GitHub (May 2025)
- **Scale**: 8+ million server downloads, 5,800+ MCP servers, 300+ clients
- **Governance**: Donated to Linux Foundation's Agentic AI Foundation (December 2025)
- **Transport**: JSON-RPC 2.0 over stdio, SSE, or HTTP

### MCP Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         MCP Host                                 │
│  (Claude Desktop, VS Code, Cursor, ChatGPT Desktop, etc.)       │
├─────────────────────────────────────────────────────────────────┤
│                         MCP Client                               │
│  (Built into the host - manages server connections)             │
├─────────────────────────────────────────────────────────────────┤
│                    Transport Layer                               │
│  (stdio for local servers, SSE/HTTP for remote)                 │
├─────────────────────────────────────────────────────────────────┤
│                      MCP Servers                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   EMDX       │  │   GitHub     │  │  Filesystem  │          │
│  │  Knowledge   │  │    Server    │  │    Server    │          │
│  │    Base      │  │              │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### What MCP Servers Expose

1. **Resources**: Read-only data (documents, search results, statistics)
2. **Tools**: Actions the model can invoke (save, tag, search, create task)
3. **Prompts**: Reusable interaction templates

## EMDX as an MCP Server - Concrete Design

### MCP Server Interface

```python
# emdx/mcp_server.py
from mcp.server import MCPServer
from mcp.types import Resource, Tool

mcp = MCPServer("emdx")

# =============================================================================
# RESOURCES - What the AI can read
# =============================================================================

@mcp.resource("emdx://documents/{doc_id}")
async def get_document(doc_id: int) -> str:
    """Get a specific document by ID.

    Returns the full document content with metadata.
    """
    from emdx.database.documents import get_document
    doc = get_document(doc_id)
    if not doc:
        raise ValueError(f"Document {doc_id} not found")
    return f"""# {doc['title']}

**Project:** {doc.get('project', 'None')}
**Tags:** {', '.join(doc.get('tags', []))}
**Created:** {doc.get('created_at')}

---

{doc['content']}
"""

@mcp.resource("emdx://search/{query}")
async def search_resource(query: str) -> str:
    """Search results as a browsable resource."""
    from emdx.database.search import search_documents
    results = search_documents(query, limit=20)
    lines = [f"# Search Results for: {query}", ""]
    for r in results:
        lines.append(f"- **#{r['id']}** {r['title']} ({r.get('project', 'no project')})")
        if r.get('snippet'):
            lines.append(f"  > {r['snippet'][:100]}...")
    return "\n".join(lines)

@mcp.resource("emdx://tags")
async def list_tags() -> str:
    """All available tags with usage counts."""
    from emdx.models.tags import list_all_tags
    tags = list_all_tags()
    lines = ["# EMDX Tags", "", "| Tag | Count | Last Used |", "|-----|-------|-----------|" ]
    for t in tags:
        lines.append(f"| {t['name']} | {t['count']} | {t.get('last_used', 'never')} |")
    return "\n".join(lines)

@mcp.resource("emdx://tasks/ready")
async def ready_tasks() -> str:
    """Tasks ready to work on (no blockers)."""
    from emdx.models.tasks import get_ready_tasks
    tasks = get_ready_tasks()
    lines = ["# Ready Tasks", ""]
    for t in tasks:
        priority = ['P0-CRITICAL', 'P1-HIGH', 'P2-MEDIUM', 'P3-LOW'][min(t['priority'], 3)]
        lines.append(f"- **#{t['id']}** [{priority}] {t['title']}")
        if t.get('description'):
            lines.append(f"  {t['description'][:100]}...")
    return "\n".join(lines)

@mcp.resource("emdx://prime")
async def prime_context() -> str:
    """Full priming context - inject this at session start."""
    from emdx.commands.prime import _get_ready_tasks, _get_in_progress_tasks
    # Essentially what 'emdx prime' outputs
    tasks = _get_ready_tasks()
    in_progress = _get_in_progress_tasks()
    # ... format and return

@mcp.resource("emdx://cascade/status")
async def cascade_status() -> str:
    """Current cascade pipeline status."""
    from emdx.database.documents import get_cascade_stats
    stats = get_cascade_stats()
    lines = ["# Cascade Status", ""]
    for stage, count in stats.items():
        emoji = {'idea': '💡', 'prompt': '📝', 'analyzed': '🔍', 'planned': '📋', 'done': '✅'}
        lines.append(f"{emoji.get(stage, '•')} **{stage}**: {count} documents")
    return "\n".join(lines)

# =============================================================================
# TOOLS - What the AI can do
# =============================================================================

@mcp.tool()
async def save_document(
    title: str,
    content: str,
    tags: list[str] | None = None,
    project: str | None = None
) -> dict:
    """Save a new document to the EMDX knowledge base.

    Args:
        title: Document title
        content: Document content (markdown supported)
        tags: Optional list of tags (emojis or text aliases like 'gameplan', 'active')
        project: Optional project name (auto-detected from git if not provided)

    Returns:
        The saved document's ID and URI
    """
    from emdx.database.documents import save_document
    from emdx.utils.git import get_git_project

    if not project:
        project = get_git_project()

    doc_id = save_document(title, content, project, tags)
    return {
        "success": True,
        "doc_id": doc_id,
        "uri": f"emdx://documents/{doc_id}",
        "message": f"Saved document #{doc_id}: {title}"
    }

@mcp.tool()
async def search(
    query: str,
    tags: list[str] | None = None,
    project: str | None = None,
    limit: int = 10
) -> list[dict]:
    """Search the EMDX knowledge base.

    Args:
        query: Full-text search query (uses FTS5)
        tags: Filter by tags (prefix matching supported)
        project: Filter by project
        limit: Maximum results to return

    Returns:
        List of matching documents with ID, title, snippet, and relevance score
    """
    from emdx.database.search import search_documents
    from emdx.models.tags import search_by_tags

    if tags:
        # Tag-based search
        results = search_by_tags(tags, project=project, limit=limit)
    else:
        # Full-text search
        results = search_documents(query, project=project, limit=limit)

    return [{
        "doc_id": r['id'],
        "title": r['title'],
        "project": r.get('project'),
        "snippet": r.get('snippet', '')[:150],
        "uri": f"emdx://documents/{r['id']}"
    } for r in results]

@mcp.tool()
async def semantic_search(query: str, limit: int = 10) -> list[dict]:
    """Semantic search using embeddings.

    Finds conceptually related documents even if they don't contain
    the exact search terms.

    Args:
        query: Natural language query
        limit: Maximum results

    Returns:
        Documents ranked by semantic similarity
    """
    from emdx.services.embedding_service import EmbeddingService
    svc = EmbeddingService()
    results = svc.search(query, limit=limit)
    return [{
        "doc_id": r.doc_id,
        "title": r.title,
        "similarity": round(r.similarity, 3),
        "snippet": r.snippet,
        "uri": f"emdx://documents/{r.doc_id}"
    } for r in results]

@mcp.tool()
async def tag_document(doc_id: int, tags: list[str]) -> dict:
    """Add tags to a document.

    Args:
        doc_id: Document ID
        tags: Tags to add (text aliases like 'gameplan', 'active', 'done' auto-expand to emojis)
    """
    from emdx.models.tags import add_tags_to_document
    added = add_tags_to_document(doc_id, tags)
    return {
        "success": True,
        "doc_id": doc_id,
        "added_tags": added,
        "message": f"Added {len(added)} tags to document #{doc_id}"
    }

@mcp.tool()
async def create_task(
    title: str,
    description: str = "",
    priority: int = 2,
    depends_on: list[int] | None = None
) -> dict:
    """Create a new task in the EMDX task system.

    Args:
        title: Task title
        description: Detailed description
        priority: 0=critical, 1=high, 2=medium, 3=low
        depends_on: List of task IDs this depends on

    Returns:
        The created task's ID
    """
    from emdx.models.tasks import create_task
    task_id = create_task(title, description, priority, depends_on=depends_on)
    return {
        "success": True,
        "task_id": task_id,
        "message": f"Created task #{task_id}: {title}"
    }

@mcp.tool()
async def update_task_status(task_id: int, status: str) -> dict:
    """Update a task's status.

    Args:
        task_id: Task ID
        status: New status (open, active, blocked, done, failed)
    """
    from emdx.models.tasks import update_task
    if status not in ('open', 'active', 'blocked', 'done', 'failed'):
        return {"success": False, "error": f"Invalid status: {status}"}

    success = update_task(task_id, status=status)
    return {
        "success": success,
        "task_id": task_id,
        "new_status": status
    }

@mcp.tool()
async def add_to_cascade(
    idea: str,
    stage: str = "idea"
) -> dict:
    """Add an idea to the cascade pipeline for autonomous processing.

    The cascade transforms ideas through stages:
    idea -> prompt -> analyzed -> planned -> done (with PR)

    Args:
        idea: The idea text
        stage: Starting stage (usually 'idea')
    """
    from emdx.database.documents import save_document_to_cascade
    doc_id = save_document_to_cascade(
        title=f"Cascade: {idea[:50]}...",
        content=idea,
        stage=stage
    )
    return {
        "success": True,
        "doc_id": doc_id,
        "stage": stage,
        "message": f"Added to cascade at '{stage}' stage"
    }

@mcp.tool()
async def get_context_for_query(query: str, limit: int = 5) -> str:
    """Get relevant context for answering a question.

    Combines semantic search results into a context block
    suitable for RAG-style question answering.

    Args:
        query: The question or topic
        limit: How many documents to include

    Returns:
        Formatted context string with relevant document excerpts
    """
    from emdx.services.embedding_service import EmbeddingService
    svc = EmbeddingService()
    results = svc.search(query, limit=limit)

    context_parts = [f"# Context for: {query}", ""]
    for r in results:
        from emdx.database.documents import get_document
        doc = get_document(r.doc_id)
        context_parts.append(f"## {doc['title']} (similarity: {r.similarity:.2f})")
        context_parts.append(doc['content'][:1000])
        context_parts.append("")

    return "\n".join(context_parts)

# =============================================================================
# PROMPTS - Reusable interaction templates
# =============================================================================

@mcp.prompt()
async def session_start() -> str:
    """Priming prompt for starting a new session."""
    from emdx.commands.prime import _get_ready_tasks
    tasks = _get_ready_tasks()
    return f"""You are working in a codebase with EMDX knowledge management.

Current ready tasks:
{chr(10).join(f'- #{t["id"]} {t["title"]}' for t in tasks[:5])}

Always:
1. Save significant findings with save_document()
2. Create tasks for discovered work with create_task()
3. Update task status when work is done
"""

@mcp.prompt()
async def research_pattern(topic: str) -> str:
    """Start a research session on a topic."""
    return f"""Research task: {topic}

1. Search existing knowledge: search("{topic}")
2. Do semantic search: semantic_search("{topic}")
3. Synthesize findings into a new document
4. Save with appropriate tags
"""
```

### Resource URI Scheme

EMDX would use a custom `emdx://` URI scheme:

| URI Pattern | Description | Example |
|-------------|-------------|---------|
| `emdx://documents/{id}` | Single document | `emdx://documents/1234` |
| `emdx://documents` | Recent documents list | |
| `emdx://search/{query}` | Search results | `emdx://search/auth+module` |
| `emdx://tags` | All tags | |
| `emdx://tags/{tag}` | Documents with tag | `emdx://tags/gameplan` |
| `emdx://tasks/ready` | Ready tasks | |
| `emdx://tasks/{id}` | Single task | |
| `emdx://cascade/status` | Cascade pipeline status | |
| `emdx://prime` | Full priming context | |
| `emdx://projects` | All projects | |
| `emdx://projects/{name}` | Project documents | |

### Tools Summary

| Tool | Purpose | Input | Output |
|------|---------|-------|--------|
| `save_document` | Save to knowledge base | title, content, tags, project | doc_id, uri |
| `search` | Full-text search (FTS5) | query, tags, project, limit | list of matches |
| `semantic_search` | Embedding-based search | query, limit | similar docs |
| `get_document` | Read specific doc | doc_id | full content |
| `tag_document` | Add tags | doc_id, tags | confirmation |
| `create_task` | Create task | title, description, priority | task_id |
| `update_task_status` | Update task | task_id, status | confirmation |
| `add_to_cascade` | Add to pipeline | idea, stage | doc_id |
| `get_context_for_query` | RAG context | query, limit | context string |

## Architecture Changes

### Current Architecture (CLI-based)
```
┌──────────────────┐     shell commands      ┌──────────────────┐
│   Claude Code    │ ───────────────────────→│   emdx CLI       │
│   (AI Agent)     │ ←─────────────────────── │   (Typer)        │
└──────────────────┘     stdout/stderr        └──────────────────┘
                                                       │
                                                       ▼
                                              ┌──────────────────┐
                                              │   SQLite + FTS5  │
                                              └──────────────────┘
```

**Limitations:**
- Requires shell access
- Text parsing of output
- No streaming/subscriptions
- Single client at a time

### MCP Architecture
```
┌──────────────────┐     JSON-RPC 2.0        ┌──────────────────┐
│   Claude Code    │ ───────────────────────→│   EMDX MCP       │
│   VS Code        │ ←─────────────────────── │   Server         │
│   Cursor         │     typed responses      │                  │
│   ChatGPT        │                          │ ┌──────────────┐ │
│   Any MCP Client │                          │ │ Resources    │ │
└──────────────────┘                          │ │ Tools        │ │
                                              │ │ Prompts      │ │
                                              │ └──────────────┘ │
                                              └────────┬─────────┘
                                                       │
                         ┌─────────────────────────────┼─────────────────────────────┐
                         ▼                             ▼                             ▼
                ┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
                │   SQLite + FTS5  │        │   Embeddings     │        │   Task System    │
                │   (Documents)    │        │   (Semantic)     │        │   (Workflow)     │
                └──────────────────┘        └──────────────────┘        └──────────────────┘
```

**Benefits:**
- **Universal access**: Any MCP client gets EMDX capabilities
- **Type safety**: JSON Schema validation on inputs/outputs
- **Streaming**: Real-time updates via subscriptions
- **Multi-client**: Multiple AI tools sharing the same knowledge base
- **VS Code extension**: Trivial to build with MCP client
- **Discovery**: Clients can list available tools/resources

### Dual-Mode Operation

EMDX would support **both** interfaces:

```python
# emdx/main.py

def run():
    """Entry point supporting CLI or MCP mode."""
    import sys

    if '--mcp' in sys.argv:
        # MCP server mode - communicate via JSON-RPC
        from emdx.mcp_server import mcp
        mcp.run(transport='stdio')
    else:
        # Traditional CLI mode
        from emdx.commands import app
        app()
```

Configuration example (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "emdx": {
      "command": "emdx",
      "args": ["--mcp"],
      "env": {
        "EMDX_DB_PATH": "~/.emdx/emdx.db"
      }
    }
  }
}
```

## Implementation Path

### Phase 1: Core MCP Server (1-2 weeks)

1. **Add MCP SDK dependency**
   ```toml
   # pyproject.toml
   mcp = "^1.0.0"  # Official Python SDK
   ```

2. **Create basic server** with essential tools:
   - `save_document`
   - `search`
   - `get_document`
   - `tag_document`

3. **Add essential resources**:
   - `emdx://documents/{id}`
   - `emdx://search/{query}`
   - `emdx://prime`

4. **Test with Claude Desktop** (stdio transport)

### Phase 2: Full Feature Parity (2-3 weeks)

1. **Complete tool coverage**:
   - Task operations
   - Cascade operations
   - Semantic search
   - Groups

2. **Complete resource coverage**:
   - Tags
   - Tasks
   - Projects
   - Statistics

3. **Add subscriptions**:
   - Document changes
   - Task updates
   - Cascade progress

### Phase 3: Advanced Features (2-3 weeks)

1. **HTTP/SSE transport** for remote access
2. **VS Code extension** using MCP client
3. **Authentication** for multi-user scenarios
4. **MCP Registry submission** for discoverability

## Python MCP SDK Reference

The official Python SDK makes implementation straightforward:

```python
# Installation
pip install mcp

# Basic server setup
from mcp.server import MCPServer

mcp = MCPServer("my-server")

# Define a tool with automatic schema generation
@mcp.tool()
def my_tool(param1: str, param2: int = 10) -> dict:
    """Tool description (becomes the tool's help text).

    Args:
        param1: Description of param1
        param2: Description of param2
    """
    return {"result": f"Processed {param1} with {param2}"}

# Define a resource
@mcp.resource("myscheme://path/{id}")
def my_resource(id: str) -> str:
    return f"Content for {id}"

# Run the server
if __name__ == "__main__":
    mcp.run()  # Defaults to stdio transport
```

Key features:
- **Type annotations** become JSON Schema automatically
- **Docstrings** become descriptions
- **Decorators** handle all protocol plumbing
- **Async support** built-in
- **Multiple transports**: stdio, SSE, HTTP

## Competitive Analysis

### Existing Knowledge Base MCP Servers

1. **kb-mcp-server (txtai-powered)**
   - Uses txtai for embeddings
   - Full-text + semantic search
   - Graph capabilities
   - *EMDX advantage*: Task system, cascade pipeline, project organization

2. **memory-mcp (Anthropic reference)**
   - Simple key-value memory
   - Knowledge graph structure
   - *EMDX advantage*: Rich document model, FTS5, hierarchy

3. **notion-mcp, obsidian-mcp**
   - Connect to existing platforms
   - *EMDX advantage*: Local-first, SQLite, no account needed

### EMDX Differentiators as MCP Server

1. **Task-aware memory**: Not just documents, but actionable work items
2. **Cascade pipeline**: Autonomous idea-to-code transformation
3. **Project-scoped**: Git-aware organization
4. **Emoji tag system**: Visual, efficient categorization
5. **Dual-mode**: CLI for humans, MCP for AI

## Strategic Implications

### Short Term
- **Immediate value**: Claude Desktop users get EMDX without shell commands
- **Developer experience**: VS Code extension becomes trivial
- **Multi-agent**: Different AI tools share the same knowledge base

### Medium Term
- **Ecosystem presence**: Listed in MCP Registry
- **Platform agnostic**: Works with OpenAI, Google, Microsoft AI tools
- **Enterprise ready**: HTTP transport enables centralized deployment

### Long Term
- **Standard infrastructure**: EMDX becomes the knowledge layer for AI workflows
- **Federation**: Multiple EMDX servers can share knowledge
- **Agent memory standard**: Sets patterns for how AI remembers

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| MCP spec changes | Pin to stable spec version, abstract transport layer |
| Performance overhead | JSON-RPC is lightweight; batch operations where needed |
| Complexity increase | Keep CLI as primary; MCP is additional interface |
| Security exposure | Localhost-only by default; explicit auth for remote |

## Conclusion

Transforming EMDX into an MCP server is a **high-value, moderate-effort** initiative that:

1. **Expands reach** from Claude Code users to the entire MCP ecosystem
2. **Reduces friction** by eliminating shell command parsing
3. **Enables new features** like subscriptions and streaming
4. **Future-proofs** against AI tool proliferation
5. **Positions EMDX** as infrastructure rather than just a CLI tool

The implementation is well-defined, the SDK is mature, and the existing EMDX architecture maps cleanly to MCP concepts. This is a natural evolution of the project.

---

**Recommended Next Step**: Create Phase 1 implementation as a proof-of-concept:
- Add `mcp` dependency
- Implement `save_document`, `search`, and `get_document` tools
- Implement `emdx://documents/{id}` and `emdx://prime` resources
- Test with Claude Desktop

**Sources**:
- [MCP Specification (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25)
- [Official Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [FastMCP (simplified SDK)](https://github.com/jlowin/fastmcp)
- [MCP Example Servers](https://modelcontextprotocol.io/examples)
- [kb-mcp-server (Knowledge Base)](https://playbooks.com/mcp/geeksfino-knowledge-base)
- [SQLite MCP Servers](https://mcpservers.org/servers/panasenco/mcp-sqlite)
- [A Year of MCP (2025 Review)](https://www.pento.ai/blog/a-year-of-mcp-2025-review)
- [Why MCP Won](https://thenewstack.io/why-the-model-context-protocol-won/)
