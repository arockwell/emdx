"""Workflow execution context.

Provides explicit, typed context for workflow execution instead of
magic dictionary keys. This makes the available variables discoverable
and prevents typos.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class StageOutput:
    """Output from a completed workflow stage."""

    doc_id: int
    content: str
    title: str
    synthesis_doc_id: Optional[int] = None
    synthesis_content: Optional[str] = None
    individual_doc_ids: List[int] = field(default_factory=list)


@dataclass
class WorkflowContext:
    """Explicit workflow execution context.

    Replaces the magic Dict[str, Any] context with typed fields.
    This makes available variables discoverable and prevents errors
    from typos in variable names.

    Attributes:
        input_doc_id: ID of the input document (if any)
        input_content: Content of the input document
        input_title: Title of the input document
        working_dir: Working directory for agent execution
        max_concurrent: Maximum concurrent agent runs
        base_branch: Git base branch for worktree operations
        variables: User-provided variables (from --var flags and presets)
        loaded_docs: Auto-loaded document content (doc_N -> content, title, id)
        stage_outputs: Output from completed stages
        workflow_run_id: Database ID of the workflow run
        workflow_name: Name of the workflow being executed
    """

    # Input document
    input_doc_id: Optional[int] = None
    input_content: str = ""
    input_title: str = ""

    # Execution settings
    working_dir: Path = field(default_factory=Path.cwd)
    max_concurrent: int = 10
    base_branch: str = "main"

    # User-provided variables (from --var flags and presets)
    variables: Dict[str, Any] = field(default_factory=dict)

    # Auto-loaded document content (doc_N -> {content, title, id})
    loaded_docs: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Stage outputs (populated during execution)
    stage_outputs: Dict[str, StageOutput] = field(default_factory=dict)

    # Internal state
    workflow_run_id: Optional[int] = None
    workflow_name: str = ""

    def get_variable(self, name: str, default: Any = None) -> Any:
        """Get a user variable.

        Args:
            name: Variable name
            default: Default value if not found

        Returns:
            Variable value or default
        """
        return self.variables.get(name, default)

    def get_stage_output(self, stage_name: str) -> Optional[StageOutput]:
        """Get output from a completed stage.

        Args:
            stage_name: Name of the stage

        Returns:
            StageOutput if stage completed, None otherwise
        """
        return self.stage_outputs.get(stage_name)

    def set_stage_output(
        self,
        stage_name: str,
        doc_id: int,
        content: str,
        title: str,
        synthesis_doc_id: Optional[int] = None,
        synthesis_content: Optional[str] = None,
        individual_doc_ids: Optional[List[int]] = None,
    ) -> None:
        """Record output from a completed stage.

        Args:
            stage_name: Name of the stage
            doc_id: Primary output document ID
            content: Primary output content
            title: Primary output title
            synthesis_doc_id: Synthesis document ID (for parallel mode)
            synthesis_content: Synthesis content
            individual_doc_ids: Individual output doc IDs (for parallel mode)
        """
        self.stage_outputs[stage_name] = StageOutput(
            doc_id=doc_id,
            content=content,
            title=title,
            synthesis_doc_id=synthesis_doc_id,
            synthesis_content=synthesis_content,
            individual_doc_ids=individual_doc_ids or [],
        )

    def load_document(self, key: str, doc_id: int, content: str, title: str) -> None:
        """Load a document's content for use in templates.

        Args:
            key: Variable name prefix (e.g., "doc_1")
            doc_id: Document ID
            content: Document content
            title: Document title
        """
        self.loaded_docs[key] = {
            "id": doc_id,
            "content": content,
            "title": title,
        }

    def to_template_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for template resolution.

        This maintains backwards compatibility with existing templates
        that use {{variable}} syntax.

        Returns:
            Dictionary with all context variables expanded
        """
        ctx: Dict[str, Any] = {}

        # Input document
        ctx["input"] = self.input_content
        ctx["input_title"] = self.input_title
        ctx["input_doc_id"] = self.input_doc_id

        # User variables
        ctx.update(self.variables)

        # Loaded documents (doc_N_content, doc_N_title, doc_N_id)
        for key, doc_data in self.loaded_docs.items():
            ctx[f"{key}_content"] = doc_data.get("content", "")
            ctx[f"{key}_title"] = doc_data.get("title", "")
            ctx[f"{key}_id"] = doc_data.get("id")

        # Stage outputs (stage_name.output, stage_name.output_id, etc.)
        for stage_name, output in self.stage_outputs.items():
            ctx[f"{stage_name}.output"] = output.content
            ctx[f"{stage_name}.output_id"] = output.doc_id
            if output.synthesis_content:
                ctx[f"{stage_name}.synthesis"] = output.synthesis_content
                ctx[f"{stage_name}.synthesis_id"] = output.synthesis_doc_id
            if output.individual_doc_ids:
                ctx[f"{stage_name}.outputs"] = output.individual_doc_ids

        # Internal state (underscore prefix for private)
        ctx["_working_dir"] = str(self.working_dir)
        ctx["_max_concurrent_override"] = self.max_concurrent
        ctx["workflow_name"] = self.workflow_name
        ctx["run_id"] = self.workflow_run_id
        ctx["base_branch"] = self.base_branch

        return ctx

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowContext":
        """Create WorkflowContext from a legacy dictionary.

        This enables gradual migration from Dict[str, Any] to WorkflowContext.

        Args:
            data: Legacy context dictionary

        Returns:
            WorkflowContext instance
        """
        ctx = cls()

        # Input document
        ctx.input_content = data.get("input", "")
        ctx.input_title = data.get("input_title", "")
        ctx.input_doc_id = data.get("input_doc_id")

        # Execution settings
        if "_working_dir" in data:
            ctx.working_dir = Path(data["_working_dir"])
        if "_max_concurrent_override" in data:
            ctx.max_concurrent = data["_max_concurrent_override"]
        if "base_branch" in data:
            ctx.base_branch = data["base_branch"]

        # Internal state
        ctx.workflow_run_id = data.get("run_id")
        ctx.workflow_name = data.get("workflow_name", "")

        # User variables - anything not in known keys
        known_keys = {
            "input", "input_title", "input_doc_id",
            "_working_dir", "_max_concurrent_override", "base_branch",
            "run_id", "workflow_name",
        }
        for key, value in data.items():
            if key not in known_keys and not key.endswith(("_content", "_title", "_id", ".output", ".synthesis", ".outputs")):
                ctx.variables[key] = value

        return ctx
