"""
Log parsing utilities for the TUI browser.

Supports both structured JSON logs and legacy text format.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class LogEntry:
    """Represents a parsed log entry."""
    
    def __init__(self, timestamp: datetime, level: str, process_type: str, 
                 process_pid: int, message: str, context: Optional[Dict[str, Any]] = None):
        self.timestamp = timestamp
        self.level = level
        self.process_type = process_type
        self.process_pid = process_pid
        self.message = message
        self.context = context or {}
    
    @property
    def formatted_time(self) -> str:
        """Get formatted timestamp for display."""
        return self.timestamp.strftime("[%H:%M:%S]")
    
    @property
    def process_name(self) -> str:
        """Get process name for display."""
        return f"{self.process_type}-{self.process_pid}"
    
    def is_wrapper_noise(self) -> bool:
        """Check if this is wrapper orchestration noise."""
        if self.process_type != "wrapper":
            return False
        
        # Filter out lifecycle events
        if self.context.get("event") in ["process_start", "execution_start"]:
            return True
        
        # Filter out specific messages
        noise_patterns = [
            "Database updated successfully",
            "Process start",
            "Starting Claude process",
        ]
        
        return any(pattern in self.message for pattern in noise_patterns)
    
    def is_claude_content(self) -> bool:
        """Check if this is actual Claude output content."""
        return (self.process_type == "claude" or 
                self.context.get("claude_type") in ["content", "tool_use", "tool_result"])
    
    def format_for_display(self, show_process: bool = False) -> str:
        """Format entry for display in TUI."""
        prefix = self.formatted_time
        
        if show_process:
            prefix += f" [{self.process_type}]"
        
        # Handle special formatting for different types
        if self.context.get("claude_type") == "tool_use":
            tool = self.context.get("tool", "unknown")
            emoji = {
                "Read": "📖", "Write": "📝", "Edit": "✏️",
                "Bash": "💻", "Grep": "🔍", "Task": "📋"
            }.get(tool, "🛠️")
            return f"{prefix} {emoji} Using tool: {tool}"
        
        elif self.context.get("claude_type") == "tool_result":
            tool = self.context.get("tool", "unknown")
            return f"{prefix} 📊 Result from {tool}"
        
        elif self.level == "ERROR":
            return f"{prefix} ❌ {self.message}"
        
        elif self.level == "WARNING":
            return f"{prefix} ⚠️  {self.message}"
        
        elif self.message.startswith("Claude:"):
            # Claude content
            content = self.message.replace("Claude: ", "")
            return f"{prefix} 💬 {content}"
        
        else:
            return f"{prefix} {self.message}"


class LogParser:
    """Parser for EMDX log files supporting both formats."""
    
    def __init__(self, log_file: Union[str, Path]):
        self.log_file = Path(log_file)
        self._entries: List[LogEntry] = []
        self._parsed = False
    
    def parse(self) -> List[LogEntry]:
        """Parse the log file and return entries."""
        if self._parsed:
            return self._entries
        
        self._entries = []
        
        if not self.log_file.exists():
            return self._entries
        
        try:
            with open(self.log_file, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    entry = self._parse_line(line)
                    if entry:
                        self._entries.append(entry)
        except Exception as e:
            print(f"Error parsing log file: {e}")
        
        self._parsed = True
        return self._entries
    
    def _parse_line(self, line: str) -> Optional[LogEntry]:
        """Parse a single log line."""
        line = line.strip()
        if not line:
            return None
        
        # Try JSON format first
        if line.startswith("{"):
            try:
                data = json.loads(line)
                return self._parse_json_entry(data)
            except json.JSONDecodeError:
                pass
        
        # Fall back to legacy format
        return self._parse_legacy_line(line)
    
    def _parse_json_entry(self, data: Dict[str, Any]) -> LogEntry:
        """Parse a structured JSON log entry."""
        # Parse timestamp
        timestamp_str = data.get("timestamp", "")
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
        except:
            timestamp = datetime.now(timezone.utc)
        
        # Extract process info
        process_info = data.get("process", {})
        process_type = process_info.get("type", "unknown")
        process_pid = process_info.get("pid", 0)
        
        # Create entry
        return LogEntry(
            timestamp=timestamp,
            level=data.get("level", "INFO"),
            process_type=process_type,
            process_pid=process_pid,
            message=data.get("message", ""),
            context=data.get("context", {})
        )
    
    def _parse_legacy_line(self, line: str) -> LogEntry:
        """Parse a legacy format log line."""
        # Extract timestamp if present
        timestamp_match = re.match(r'(\[\d{2}:\d{2}:\d{2}\])\s+(.*)', line)
        if timestamp_match:
            timestamp_str, content = timestamp_match.groups()
            # Parse time and use today's date
            hour, minute, second = map(int, re.findall(r'\d{2}', timestamp_str))
            timestamp = datetime.now(timezone.utc).replace(
                hour=hour, minute=minute, second=second, microsecond=0
            )
        else:
            timestamp = datetime.now(timezone.utc)
            content = line
        
        # Determine process type from content
        process_type = "legacy"
        level = "INFO"
        
        if "❌" in content:
            level = "ERROR"
        elif "⚠️" in content:
            level = "WARNING"
        
        # Create entry
        return LogEntry(
            timestamp=timestamp,
            level=level,
            process_type=process_type,
            process_pid=0,
            message=content,
            context={}
        )
    
    def get_filtered_entries(self, 
                           show_wrapper_noise: bool = False,
                           process_filter: Optional[str] = None,
                           level_filter: Optional[str] = None) -> List[LogEntry]:
        """Get filtered log entries."""
        entries = self.parse()
        
        # Apply filters
        filtered = []
        for entry in entries:
            # Filter wrapper noise
            if not show_wrapper_noise and entry.is_wrapper_noise():
                continue
            
            # Filter by process
            if process_filter and entry.process_type != process_filter:
                continue
            
            # Filter by level
            if level_filter and entry.level != level_filter:
                continue
            
            filtered.append(entry)
        
        return filtered
    
    def get_execution_summary(self) -> Dict[str, Any]:
        """Get summary information about the execution."""
        entries = self.parse()
        
        if not entries:
            return {
                "total_entries": 0,
                "start_time": None,
                "end_time": None,
                "duration": None,
                "processes": {},
                "error_count": 0
            }
        
        # Count by process type
        processes = {}
        error_count = 0
        
        for entry in entries:
            # Count processes
            if entry.process_type not in processes:
                processes[entry.process_type] = 0
            processes[entry.process_type] += 1
            
            # Count errors
            if entry.level == "ERROR":
                error_count += 1
        
        # Calculate duration
        start_time = entries[0].timestamp
        end_time = entries[-1].timestamp
        duration = (end_time - start_time).total_seconds()
        
        return {
            "total_entries": len(entries),
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
            "processes": processes,
            "error_count": error_count
        }
