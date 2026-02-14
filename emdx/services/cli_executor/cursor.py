"""Cursor CLI executor implementation."""

import json
import logging
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from ...config.cli_config import CLI_CONFIGS, CliTool, resolve_model_alias
from ...config.constants import CLI_AUTH_CHECK_TIMEOUT, CLI_VERSION_CHECK_TIMEOUT
from .base import CliCommand, CliExecutor, CliResult

logger = logging.getLogger(__name__)


class CursorCliExecutor(CliExecutor):
    """Executor for Cursor Agent CLI."""

    def __init__(self):
        self.config = CLI_CONFIGS[CliTool.CURSOR]

    @property
    def name(self) -> str:
        return "Cursor Agent"

    def build_command(
        self,
        prompt: str,
        model: Optional[str] = None,
        allowed_tools: Optional[List[str]] = None,
        output_format: str = "stream-json",
        working_dir: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> CliCommand:
        """Build Cursor CLI command.

        Cursor command format:
            cursor agent -p --output-format <format> --model <model> [--force] [--workspace <path>] "prompt"

        Note: Cursor uses positional prompt at the end with -p flag.
        """
        # Start with binary (cursor agent)
        cmd = list(self.config.binary)

        # Add print flag (enables non-interactive mode)
        cmd.append(self.config.prompt_flag)

        # Add output format
        cmd.extend([self.config.output_format_flag, output_format])

        # Add model
        resolved_model = resolve_model_alias(
            model or self.config.default_model, CliTool.CURSOR
        )
        cmd.extend([self.config.model_flag, resolved_model])

        # Cursor doesn't have --allowedTools, use --force for full tool access
        # Only add --force if tools are requested (implies full access needed)
        if allowed_tools and self.config.force_flag:
            cmd.append(self.config.force_flag)

        # Add workspace if specified
        if working_dir and self.config.workspace_flag:
            cmd.extend([self.config.workspace_flag, working_dir])

        # Add prompt as positional argument at the end (Cursor style)
        cmd.append(prompt)

        return CliCommand(args=cmd, cwd=working_dir)

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> CliResult:
        """Parse Cursor CLI output.

        Cursor's output format is very similar to Claude's stream-json.
        Key differences:
        - Cursor echoes user messages
        - Cursor doesn't include cost/token info in result
        - Cursor uses request_id instead of detailed usage
        """
        if exit_code != 0:
            # Check for specific Cursor errors
            error_msg = stderr or stdout
            if "ActionRequiredError" in error_msg:
                # Premium model or auth error
                error_msg = self._extract_cursor_error(error_msg)
            return CliResult(
                success=False,
                output=stdout,
                error=error_msg or f"Exit code {exit_code}",
                exit_code=exit_code,
            )

        # Parse stream-json output
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
                continue

        # Build result
        if result_data:
            return CliResult(
                success=not result_data.get("is_error", False),
                output=result_data.get("result", "\n".join(assistant_text)),
                exit_code=exit_code,
                # Cursor doesn't provide token/cost info
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
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

    def _extract_cursor_error(self, error_text: str) -> str:
        """Extract meaningful error message from Cursor output."""
        # Look for ActionRequiredError pattern
        if "Premium Model Upgrade Required" in error_text:
            return "Cursor requires a paid plan for this model. Try --model auto"
        if "Authentication required" in error_text:
            return "Cursor authentication required. Run 'cursor agent login'"
        if "Cannot use this model" in error_text:
            # Extract available models hint
            if "Available models:" in error_text:
                start = error_text.find("Available models:")
                return error_text[start:].split("\n")[0]
            return "Model not available for your account"
        return error_text

    def parse_stream_line(self, line: str) -> Optional[Dict[str, Any]]:
        """Parse a single line from Cursor's stream-json output."""
        if not line.strip():
            return None

        try:
            data = json.loads(line)
            msg_type = data.get("type")

            if msg_type == "system":
                return {
                    "type": "system",
                    "subtype": data.get("subtype"),
                    "session_id": data.get("session_id"),
                    "model": data.get("model"),
                    "cwd": data.get("cwd"),
                    "api_key_source": data.get("apiKeySource"),
                }

            elif msg_type == "user":
                # Cursor echoes user input (Claude doesn't)
                message = data.get("message", {})
                content = message.get("content", [])
                return {
                    "type": "user",
                    "text": self.extract_text_content(content),
                }

            elif msg_type == "assistant":
                message = data.get("message", {})
                content = message.get("content", [])
                return {
                    "type": "assistant",
                    "text": self.extract_text_content(content),
                    "tool_uses": [
                        item for item in content if item.get("type") == "tool_use"
                    ],
                }

            elif msg_type == "tool_call":
                # Cursor has explicit tool_call messages
                return {
                    "type": "tool_call",
                    "subtype": data.get("subtype"),  # "started" or "completed"
                    "call_id": data.get("call_id"),
                    "tool_call": data.get("tool_call", {}),
                }

            elif msg_type == "result":
                return {
                    "type": "result",
                    "success": not data.get("is_error", False),
                    "result": data.get("result"),
                    "duration_ms": data.get("duration_ms", 0),
                    "request_id": data.get("request_id"),
                    # Cursor doesn't provide cost info
                    "cost_usd": 0.0,
                }

            return data

        except json.JSONDecodeError:
            logger.debug(f"Failed to parse line as JSON: {line[:100]}")
            return None

    def validate_environment(self) -> tuple[bool, Dict[str, Any]]:
        """Validate Cursor CLI is installed and authenticated."""
        info: Dict[str, Any] = {"cli": "cursor", "errors": [], "warnings": []}

        # Check if binary exists
        binary_path = self.get_binary_path()
        if not binary_path:
            info["errors"].append("Cursor CLI not found in PATH")
            return False, info

        info["binary_path"] = binary_path

        # Check version
        try:
            result = subprocess.run(
                ["cursor", "agent", "--version"],
                capture_output=True,
                text=True,
                timeout=CLI_VERSION_CHECK_TIMEOUT,
            )
            if result.returncode == 0:
                info["version"] = result.stdout.strip()
        except Exception as e:
            info["warnings"].append(f"Could not get version: {e}")

        # Check authentication status
        try:
            result = subprocess.run(
                ["cursor", "agent", "status"],
                capture_output=True,
                text=True,
                timeout=CLI_AUTH_CHECK_TIMEOUT,
            )
            if "Not logged in" in result.stdout:
                info["warnings"].append(
                    "Not authenticated. Run 'cursor agent login' to authenticate."
                )
                info["authenticated"] = False
            else:
                info["authenticated"] = True
        except Exception as e:
            info["warnings"].append(f"Could not check auth status: {e}")

        return len(info["errors"]) == 0, info

    def get_binary_path(self) -> Optional[str]:
        """Get path to cursor binary."""
        return shutil.which("cursor")
