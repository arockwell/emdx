"""Claude CLI executor implementation."""

import json
import logging
import shutil
import subprocess
from pathlib import Path

from ...config.cli_config import CLI_CONFIGS, CliTool, resolve_model_alias
from .base import CliCommand, CliExecutor, CliResult
from .types import (
    AssistantMessage,
    EnvironmentInfo,
    ErrorMessage,
    ResultMessage,
    StreamMessage,
    SystemMessage,
    ThinkingMessage,
    ToolCallMessage,
)

logger = logging.getLogger(__name__)


class ClaudeCliExecutor(CliExecutor):
    """Executor for Claude Code CLI."""

    def __init__(self) -> None:
        self.config = CLI_CONFIGS[CliTool.CLAUDE]

    @property
    def name(self) -> str:
        return "Claude Code"

    def build_command(
        self,
        prompt: str,
        model: str | None = None,
        allowed_tools: list[str] | None = None,
        output_format: str = "stream-json",
        working_dir: str | None = None,
        timeout: int | None = None,
    ) -> CliCommand:
        """Build Claude CLI command.

        Prompt is piped via stdin to avoid OS argument length limits.
        Claude command format:
            echo "prompt" | claude --print --model <model> --output-format <format>
                                   [--verbose] [--allowedTools X,Y,Z]
        """
        # Start with binary
        cmd = list(self.config.binary)

        # --print flag without a value; prompt will arrive via stdin
        cmd.append(self.config.prompt_flag)

        # Add model
        resolved_model = resolve_model_alias(model or self.config.default_model, CliTool.CLAUDE)
        cmd.extend([self.config.model_flag, resolved_model])

        # Add output format
        cmd.extend([self.config.output_format_flag, output_format])

        # Claude requires --verbose for stream-json output
        if self.config.requires_verbose_for_stream and output_format == "stream-json":
            cmd.append("--verbose")

        # Add allowed tools if supported and provided
        if allowed_tools and self.config.supports_allowed_tools and self.config.allowed_tools_flag:
            cmd.extend([self.config.allowed_tools_flag, ",".join(allowed_tools)])

        return CliCommand(args=cmd, cwd=working_dir, stdin_data=prompt)

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> CliResult:
        """Parse Claude CLI output.

        For text format, output is plain text.
        For stream-json, we need to find the result message.
        """
        if exit_code != 0:
            return CliResult(
                success=False,
                output=stdout,
                error=stderr or f"Exit code {exit_code}",
                exit_code=exit_code,
            )

        # Try to parse as stream-json (look for result line)
        result_data = None
        assistant_text = []

        for line in stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                msg_type = data.get("type")

                if msg_type == "assistant":
                    # Extract text content
                    message = data.get("message", {})
                    content = message.get("content", [])
                    text = self.extract_text_content(content)
                    if text:
                        assistant_text.append(text)

                elif msg_type == "result":
                    result_data = data

            except json.JSONDecodeError:
                # Not JSON, might be plain text output
                continue

        # Build result
        if result_data:
            usage = result_data.get("usage", {})
            return CliResult(
                success=not result_data.get("is_error", False),
                output=result_data.get("result", "\n".join(assistant_text)),
                exit_code=exit_code,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                cache_read_tokens=usage.get("cache_read_input_tokens", 0),
                cache_create_tokens=usage.get("cache_creation_input_tokens", 0),
                cost_usd=result_data.get("total_cost_usd", 0.0),
                duration_ms=result_data.get("duration_ms", 0),
                duration_api_ms=result_data.get("duration_api_ms", 0),
                session_id=result_data.get("session_id"),
            )

        # Fallback: treat entire output as text
        return CliResult(
            success=exit_code == 0,
            output=stdout,
            exit_code=exit_code,
        )

    def parse_stream_line(self, line: str) -> StreamMessage | None:
        """Parse a single line from Claude's stream-json output."""
        if not line.strip():
            return None

        try:
            data = json.loads(line)
            msg_type = data.get("type")

            if msg_type == "system":
                msg: SystemMessage = {
                    "type": "system",
                    "subtype": data.get("subtype"),
                    "session_id": data.get("session_id"),
                    "model": data.get("model"),
                    "cwd": data.get("cwd"),
                    "tools": data.get("tools", []),
                }
                return msg

            elif msg_type == "assistant":
                message = data.get("message", {})
                content = message.get("content", [])
                msg_a: AssistantMessage = {
                    "type": "assistant",
                    "text": self.extract_text_content(content),
                    "tool_uses": [item for item in content if item.get("type") == "tool_use"],
                    "usage": message.get("usage", {}),
                }
                return msg_a

            elif msg_type == "tool_call":
                msg_tc: ToolCallMessage = {
                    "type": "tool_call",
                    "subtype": data.get("subtype"),
                    "call_id": data.get("call_id"),
                    "tool_call": data.get("tool_call", {}),
                }
                return msg_tc

            elif msg_type == "thinking":
                msg_th: ThinkingMessage = {
                    "type": "thinking",
                    "subtype": data.get("subtype"),
                    "text": data.get("text", ""),
                }
                return msg_th

            elif msg_type == "result":
                msg_r: ResultMessage = {
                    "type": "result",
                    "success": not data.get("is_error", False),
                    "result": data.get("result"),
                    "duration_ms": data.get("duration_ms", 0),
                    "cost_usd": data.get("total_cost_usd", 0.0),
                    "usage": data.get("usage", {}),
                    "raw_line": line.strip(),
                }
                return msg_r

            elif msg_type == "error":
                msg_e: ErrorMessage = {
                    "type": "error",
                    "error": data.get("error", {}),
                }
                return msg_e

            # Unknown type — return as-is with type preserved
            return data  # type: ignore[no-any-return]

        except json.JSONDecodeError:
            logger.debug(f"Failed to parse line as JSON: {line[:100]}")
            return None

    def validate_environment(self) -> tuple[bool, EnvironmentInfo]:
        """Validate Claude CLI is installed and configured."""
        info: EnvironmentInfo = {"cli": "claude", "errors": [], "warnings": []}

        # Check if binary exists
        binary_path = self.get_binary_path()
        if not binary_path:
            info["errors"].append("Claude CLI not found in PATH")
            return False, info

        info["binary_path"] = binary_path

        # Check version
        try:
            result = subprocess.run(
                ["claude", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                info["version"] = result.stdout.strip()
        except Exception as e:
            info["warnings"].append(f"Could not get version: {e}")

        # Check config file
        config_path = Path(self.config.config_path or "~/.claude").expanduser()
        if config_path.exists():
            info["config_path"] = str(config_path)
        else:
            info["warnings"].append(f"Config file not found: {config_path}")

        return len(info["errors"]) == 0, info

    def get_binary_path(self) -> str | None:
        """Get path to claude binary."""
        return shutil.which("claude")
