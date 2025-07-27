"""
Migration utilities for transitioning to structured logging.

This module provides compatibility layers and migration tools to ensure
smooth transition from the old logging format to the new structured format.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Union

from .structured_logger import LogLevel, ProcessType


def parse_legacy_timestamp(timestamp_str: str) -> Optional[datetime]:
    """Parse legacy timestamp format [HH:MM:SS] to datetime.
    
    Args:
        timestamp_str: Timestamp string in format [HH:MM:SS]
        
    Returns:
        Parsed datetime or None if parsing fails
    """
    match = re.match(r'\[(\d{2}):(\d{2}):(\d{2})\]', timestamp_str)
    if match:
        hour, minute, second = map(int, match.groups())
        # Use today's date with the parsed time
        now = datetime.now(timezone.utc)
        return now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    return None


def convert_legacy_line(line: str) -> Optional[Dict[str, Any]]:
    """Convert a legacy log line to structured format.
    
    Args:
        line: Legacy format log line
        
    Returns:
        Structured log entry or None if line should be skipped
    """
    line = line.strip()
    if not line:
        return None
    
    # Try to parse timestamp
    timestamp_match = re.match(r'(\[\d{2}:\d{2}:\d{2}\])\s+(.*)', line)
    if timestamp_match:
        timestamp_str, content = timestamp_match.groups()
        timestamp = parse_legacy_timestamp(timestamp_str)
    else:
        timestamp = datetime.now(timezone.utc)
        content = line
    
    # Determine process type and level based on content patterns
    process_type = ProcessType.WRAPPER  # Default
    level = LogLevel.INFO
    
    # Wrapper lifecycle patterns
    if any(pattern in content for pattern in [
        "🚀 Starting Claude process",
        "✅ Claude process finished",
        "❌ Command not found",
        "⏱️ Process timed out",
        "⚠️ Process interrupted"
    ]):
        process_type = ProcessType.WRAPPER
        if "❌" in content:
            level = LogLevel.ERROR
        elif "⚠️" in content:
            level = LogLevel.WARNING
    
    # Claude output patterns
    elif any(pattern in content for pattern in [
        "💬", "🛠️", "📊", "✅ Task completed", "❌ Task failed"
    ]):
        process_type = ProcessType.CLAUDE
        if "❌" in content:
            level = LogLevel.ERROR
    
    # Tool usage patterns
    elif "🛠️ Using tool:" in content:
        process_type = ProcessType.CLAUDE
        # Extract tool name
        tool_match = re.search(r'Using tool: (\w+)', content)
        if tool_match:
            tool_name = tool_match.group(1)
            return {
                "timestamp": timestamp.isoformat(),
                "level": level.value,
                "process": {"type": process_type.value, "pid": 0, "name": "legacy-claude"},
                "message": f"Tool use: {tool_name}",
                "context": {"claude_type": "tool_use", "tool": tool_name}
            }
    
    # Create structured entry
    return {
        "timestamp": timestamp.isoformat(),
        "level": level.value,
        "process": {"type": process_type.value, "pid": 0, "name": f"legacy-{process_type.value}"},
        "message": content
    }


def migrate_log_file(legacy_log: Union[str, Path], structured_log: Union[str, Path]) -> int:
    """Migrate a legacy log file to structured format.
    
    Args:
        legacy_log: Path to legacy format log file
        structured_log: Path to output structured log file
        
    Returns:
        Number of entries migrated
    """
    legacy_path = Path(legacy_log)
    structured_path = Path(structured_log)
    
    if not legacy_path.exists():
        return 0
    
    # Ensure output directory exists
    structured_path.parent.mkdir(parents=True, exist_ok=True)
    
    entries_migrated = 0
    
    with open(legacy_path, 'r', encoding='utf-8', errors='replace') as infile:
        with open(structured_path, 'w', encoding='utf-8') as outfile:
            for line in infile:
                entry = convert_legacy_line(line)
                if entry:
                    json_line = json.dumps(entry, separators=(',', ':')) + '\n'
                    outfile.write(json_line)
                    entries_migrated += 1
    
    return entries_migrated


class LegacyLogAdapter:
    """Adapter to make old logging code work with structured logger.
    
    This allows gradual migration by intercepting old-style log calls
    and converting them to structured format.
    """
    
    def __init__(self, structured_logger):
        """Initialize adapter with a structured logger instance."""
        self.logger = structured_logger
    
    def log_to_file(self, log_path: Path, message: str) -> None:
        """Legacy log_to_file function replacement.
        
        Args:
            log_path: Log file path (ignored - uses structured logger's path)
            message: Message to log
        """
        # Parse message for level indicators
        level = LogLevel.INFO
        if message.startswith("❌"):
            level = LogLevel.ERROR
        elif message.startswith("⚠️"):
            level = LogLevel.WARNING
        elif message.startswith("🔍") or message.startswith("🔧"):
            level = LogLevel.DEBUG
        
        self.logger.log(level, message)
    
    def format_timestamp(self) -> str:
        """Legacy timestamp formatter."""
        return datetime.now().strftime("[%H:%M:%S]")
    
    def format_claude_output(self, line: str, timestamp: float) -> Optional[str]:
        """Legacy Claude output formatter.
        
        Args:
            line: Raw output line from Claude
            timestamp: Unix timestamp
            
        Returns:
            None - logging is handled internally
        """
        line = line.strip()
        if not line:
            return None
        
        try:
            # Try to parse as JSON
            data = json.loads(line)
            self.logger.log_claude_output(data)
        except json.JSONDecodeError:
            # Not JSON - log as plain text
            if line and not line.startswith("{"):
                self.logger.info(f"Claude: {line}")
        
        return None  # Don't return anything - logging is handled