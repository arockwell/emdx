# New Avenue: Memory + Actions Reframe

## The Insight

What if we stopped thinking "KB vs Workflows" and instead reframed EMDX as:
- **MEMORY**: Persistent knowledge (documents, tags, search, links)
- **ACTIONS**: Things you can DO with memory (execute, transform, synthesize)

This is like:
- A browser: Memory = DOM/State, Actions = JavaScript
- A shell: Memory = Filesystem, Actions = Commands/Scripts
- A database: Memory = Tables, Actions = Stored Procedures

---

## Philosophical Analysis

### Why This Reframe Is Profound

The current split decision struggles because KB and Workflows feel like **competitors for the same conceptual space**. But Memory and Actions are **complementary by definition**:

1. **Actions read from Memory** - Every workflow, cascade, or execution starts by reading documents
2. **Actions write to Memory** - Every result gets saved back as a document
3. **Memory is passive** - It just stores and retrieves
4. **Actions are active** - They transform, combine, and execute

This is the classic **data vs. compute** separation that has proven successful everywhere:
- In architecture: REST (resources) vs RPC (operations)
- In databases: Tables (storage) vs Functions (logic)
- In React: State vs Effects
- In Redux: Store vs Actions

### The Tension That Disappears

The original split question was: "Should Workflows be separate from the KB?"

With the Memory+Actions reframe, this becomes meaningless. Of course Actions are "separate" from Memory - they have to be! They operate ON Memory, not WITHIN it. Just like JavaScript is separate from the DOM, but they work together seamlessly.

---

## Concrete API Design

### Memory API

The Memory layer provides **read, write, search, link, tag** operations:

```python
class MemoryAPI:
    # Core CRUD
    def read(self, doc_id: int) -> Document
    def write(self, content: str, title: str, tags: list[str] = None) -> int
    def update(self, doc_id: int, content: str) -> bool
    def delete(self, doc_id: int) -> bool

    # Search
    def search(self, query: str) -> list[Document]
    def search_by_tags(self, tags: list[str], mode: str = "all") -> list[Document]
    def find_similar(self, doc_id: int) -> list[Document]

    # Links (relationships between documents)
    def link(self, parent_id: int, child_id: int, relationship: str) -> bool
    def get_children(self, doc_id: int) -> list[Document]
    def get_parent(self, doc_id: int) -> Document | None

    # Tags
    def tag(self, doc_id: int, tags: list[str]) -> bool
    def untag(self, doc_id: int, tags: list[str]) -> bool
    def get_tags(self, doc_id: int) -> list[str]

    # Bulk operations
    def bulk_read(self, doc_ids: list[int]) -> list[Document]
    def bulk_tag(self, doc_ids: list[int], tags: list[str]) -> bool
```

**Key insight**: Memory is **dumb by design**. It just stores and retrieves. All intelligence lives in Actions.

### Actions API

The Actions layer provides **execute, transform, synthesize** operations:

```python
class ActionsAPI:
    # Execute: Run a document through an agent
    def execute(self, doc_id: int) -> ActionResult
    def execute_with_prompt(self, prompt: str) -> ActionResult

    # Transform: Convert documents through stages
    def transform(self, doc_id: int, transformation: str) -> int  # Returns new doc_id
    def cascade(self, doc_id: int, stages: list[str]) -> int  # Multi-stage transform

    # Synthesize: Combine multiple documents
    def synthesize(self, doc_ids: list[int], prompt: str = None) -> int
    def merge(self, doc_ids: list[int]) -> int  # Simple concatenation

    # Parallel execution
    def execute_parallel(self, prompts: list[str]) -> list[ActionResult]
    def execute_each(self, items: list[str], prompt_template: str) -> list[ActionResult]

    # Discovery + Action (dynamic)
    def discover_and_execute(self, discovery_cmd: str, action_template: str) -> list[ActionResult]
```

**Key insight**: Actions are **pure transforms**. They take Memory as input and produce Memory as output. No side effects beyond Memory.

### The Interaction Contract

```
Actions never store internal state - they read and write to Memory

Memory -> Action -> Memory
  ^                   |
  |___________________|
       (feedback loop)
```

This creates a beautiful **append-only audit trail**:
1. Every action reads existing documents
2. Every action creates new documents
3. Nothing is ever truly lost (soft delete, versioning via supersedes)
4. You can always trace back to see what happened

---

## How This Reframe Helps the Split Decision

### Before: "Should Workflows be a separate package?"

This question has no clear answer because it depends on arbitrary definitions of "separate."

### After: "Are Actions and Memory separate conceptual layers?"

Yes, obviously. And the code should reflect this.

### The New Architecture

```
emdx/
├── memory/               # Pure data layer
│   ├── documents.py     # Document CRUD
│   ├── tags.py          # Tag management
│   ├── search.py        # FTS and similarity
│   ├── links.py         # Document relationships
│   └── groups.py        # Collections of documents
│
├── actions/             # Pure transformation layer
│   ├── execute.py       # Single document execution
│   ├── transform.py     # Stage-based transformation
│   ├── synthesize.py    # Multi-doc combination
│   ├── discover.py      # Discovery operations
│   └── parallel.py      # Concurrent execution
│
├── orchestration/       # Composition of actions
│   ├── cascade.py       # idea → prompt → analyzed → planned → done
│   ├── workflows.py     # Custom multi-stage workflows
│   ├── each.py         # For-each patterns
│   └── run.py          # Quick parallel execution
│
├── interface/           # How users interact
│   ├── cli/            # CLI commands
│   ├── tui/            # Terminal UI
│   └── api/            # Programmatic API
```

### What This Implies for Splitting

1. **Memory should be the core package** (`emdx-core` or just `emdx`)
   - Minimal dependencies
   - Can be used standalone for simple note-taking

2. **Actions can be a separate package** (`emdx-actions`)
   - Depends on core
   - Brings in Claude CLI, worktrees, etc.

3. **Orchestration is part of Actions** (not separate)
   - Cascade, workflows, each - these are just compositions of Actions
   - No reason to split them further

4. **Interface is flexible**
   - CLI and TUI can live together (they share nothing but imports)
   - Could be split if needed, but no strong reason

---

## Why This Model Is Powerful

### 1. Reasoning by Analogy

Once you understand Memory+Actions, you can reason about EMDX by analogy:

| Concept | Browser | Shell | EMDX |
|---------|---------|-------|------|
| Memory | DOM | Filesystem | Documents |
| Actions | JavaScript | Commands | Transforms |
| State | HTML | Files | Content |
| Links | Hyperlinks | Symlinks | Parent/Child |
| Search | querySelector | find/grep | FTS5 |

### 2. Composability

Actions compose naturally:
```python
# This is just data flow
doc_id = memory.write("Initial idea")
analyzed_id = actions.transform(doc_id, "analyze")
planned_id = actions.transform(analyzed_id, "plan")
result = actions.execute(planned_id)
```

### 3. Testability

- Memory is trivial to test (pure CRUD)
- Actions are testable in isolation (mock Memory)
- Orchestration is just composition (test the pieces)

### 4. Extensibility

Want to add a new transformation? Just add an Action.
Want new storage? Just extend Memory.
Want new orchestration patterns? Compose existing Actions.

---

## Mapping Current Code to the Model

### Memory (already exists, scattered)

- `emdx/database/documents.py` → `memory/documents.py`
- `emdx/database/search.py` → `memory/search.py`
- `emdx/models/tags.py` → `memory/tags.py`
- `emdx/database/groups.py` → `memory/groups.py`

### Actions (partially exists, needs consolidation)

- `emdx/services/unified_executor.py` → `actions/execute.py`
- `emdx/services/document_executor.py` → `actions/execute.py`
- `emdx/workflows/synthesis.py` → `actions/synthesize.py`
- Stage transformations → `actions/transform.py`

### Orchestration (exists, mostly well-organized)

- `emdx/commands/cascade.py` → `orchestration/cascade.py`
- `emdx/workflows/executor.py` → `orchestration/workflows.py`
- `emdx/commands/each.py` → `orchestration/each.py`
- `emdx/commands/run.py` → `orchestration/run.py`

---

## The Deeper Philosophy: Data as the Lingua Franca

The reason Memory+Actions works so well is that **Memory (documents) becomes the universal interface** between all parts of the system:

1. **Human -> Memory**: User writes a document
2. **Memory -> Action**: Action reads the document
3. **Action -> Memory**: Action writes new document
4. **Memory -> Human**: User reads the result

Every interaction flows through Memory. This means:
- Actions don't need to know about each other (loose coupling)
- New actions can be added without changing existing ones
- The system is debuggable (just look at the documents)
- History is preserved (append-only)

This is exactly how Unix works with the filesystem, how the web works with URLs, and how databases work with tables. EMDX adopts this proven pattern.

---

## Conclusion

The Memory+Actions reframe:

1. **Provides conceptual clarity** - No more debating what belongs where
2. **Aligns with proven patterns** - Browser, shell, databases all work this way
3. **Suggests natural splitting points** - Memory is core, Actions are extension
4. **Makes the system more predictable** - Actions transform Memory, period
5. **Enables better testing** - Clear interfaces, easy mocking
6. **Supports future growth** - New actions compose with existing ones

The split decision becomes simple:
- **Split along the Memory/Actions boundary**, not the KB/Workflow boundary
- This gives you a solid core (Memory) that works standalone
- And a powerful extension (Actions) that brings AI transformation

---

**Tags**: gameplan, analysis, architecture, active
