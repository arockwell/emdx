"""Base class for CLI executors.

This module defines the abstract interface that all CLI executors must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .types import ContentItem, EnvironmentInfo, StreamMessage


@dataclass
class CliCommand:
    """Represents a CLI command to execute."""

    args: list[str]  # Command arguments
    env: dict[str, str] = field(default_factory=dict)  # Additional env vars
    cwd: str | None = None  # Working directory


@dataclass
class CliResult:
    """Result from CLI execution."""

    success: bool
    output: str
    error: str | None = None
    exit_code: int = 0

    # Token usage (may be unavailable for some CLIs)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_create_tokens: int = 0

    # Cost
    cost_usd: float = 0.0

    # Timing
    duration_ms: int = 0
    duration_api_ms: int = 0

    # Session tracking
    session_id: str | None = None

    @property
    def total_tokens(self) -> int:
        """Total tokens used including cache."""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_create_tokens
        )


class CliExecutor(ABC):
    """Abstract base class for CLI executors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this executor."""
        pass

    @abstractmethod
    def build_command(
        self,
        prompt: str,
        model: str | None = None,
        allowed_tools: list[str] | None = None,
        output_format: str = "stream-json",
        working_dir: str | None = None,
        timeout: int | None = None,
    ) -> CliCommand:
        """Build the CLI command to execute.

        Args:
            prompt: The task/prompt to execute
            model: Model to use (None = default)
            allowed_tools: List of allowed tools (may be ignored by some CLIs)
            output_format: Output format ("text", "stream-json", "json")
            working_dir: Working directory for execution
            timeout: Timeout in seconds (optional)

        Returns:
            CliCommand with args, env, and cwd
        """
        pass

    @abstractmethod
    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> CliResult:
        """Parse CLI output into structured result.

        Args:
            stdout: Standard output from the CLI
            stderr: Standard error from the CLI
            exit_code: Process exit code

        Returns:
            CliResult with parsed output and metrics
        """
        pass

    @abstractmethod
    def parse_stream_line(self, line: str) -> StreamMessage | None:
        """Parse a single line from stream-json output.

        Args:
            line: A single JSON line from the stream

        Returns:
            Parsed StreamMessage or None if line should be skipped
        """
        pass

    @abstractmethod
    def validate_environment(self) -> tuple[bool, EnvironmentInfo]:
        """Validate that the CLI is properly installed and configured.

        Returns:
            Tuple of (is_valid, EnvironmentInfo with details/errors)
        """
        pass

    @abstractmethod
    def get_binary_path(self) -> str | None:
        """Get the path to the CLI binary.

        Returns:
            Path to the binary or None if not found
        """
        pass

    def extract_text_content(self, content: list[ContentItem]) -> str:
        """Extract text from message content array.

        Args:
            content: List of content items with type and text fields

        Returns:
            Concatenated text content
        """
        return "".join(item.get("text", "") for item in content if item.get("type") == "text")
