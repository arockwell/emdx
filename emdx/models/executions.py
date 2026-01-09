"""Execution tracking models and database operations."""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ..database.connection import db_connection


def parse_timestamp(ts) -> datetime:
    """Parse a timestamp from the database, ensuring it has timezone info."""
    if isinstance(ts, str):
        # SQLite returns timestamps as strings
        # First try parsing with timezone
        try:
            dt = datetime.fromisoformat(ts.replace(' ', 'T'))
        except ValueError:
            # If that fails, parse as naive and assume UTC
            dt = datetime.strptime(ts, '%Y-%m-%d %H:%M:%S')
        
        # Ensure timezone awareness
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    elif isinstance(ts, datetime):
        # Already a datetime object
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts
    else:
        # Fallback
        return datetime.now(timezone.utc)


@dataclass
class Execution:
    """Represents a Claude execution."""
    id: int  # Now numeric auto-incrementing ID
    doc_id: int
    doc_title: str
    status: str  # 'running', 'completed', 'failed'
    started_at: datetime
    completed_at: Optional[datetime] = None
    log_file: str = ""
    exit_code: Optional[int] = None
    working_dir: Optional[str] = None
    pid: Optional[int] = None

    @property
    def duration(self) -> Optional[float]:
        """Get execution duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def is_running(self) -> bool:
        """Check if execution is still running."""
        return self.status == 'running'
    
    @property
    def is_zombie(self) -> bool:
        """Check if this is a zombie process (marked running but process is dead)."""
        if not self.is_running or not self.pid:
            return False
        
        # Check if process exists
        try:
            # Send signal 0 to check if process exists
            os.kill(self.pid, 0)
            return False  # Process exists
        except ProcessLookupError:
            return True  # Process doesn't exist - zombie!
        except PermissionError:
            # Process exists but we can't access it
            return False

    @property
    def log_path(self) -> Path:
        """Get Path object for log file."""
        return Path(self.log_file).expanduser()


def create_execution(doc_id: int, doc_title: str, log_file: str, 
                    working_dir: Optional[str] = None, pid: Optional[int] = None) -> int:
    """Create a new execution and return its ID."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO executions 
            (doc_id, doc_title, status, started_at, log_file, working_dir, pid)
            VALUES (?, ?, 'running', CURRENT_TIMESTAMP, ?, ?, ?)
        """, (doc_id, doc_title, log_file, working_dir, pid))
        conn.commit()
        return cursor.lastrowid


def save_execution(execution: Execution) -> None:
    """Save execution to database (for backwards compatibility)."""
    # This function is deprecated but kept for compatibility
    # New code should use create_execution instead
    pass


def get_execution(exec_id: str) -> Optional[Execution]:
    """Get execution by ID."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, doc_id, doc_title, status, started_at, completed_at, log_file, exit_code, working_dir, pid
            FROM executions WHERE id = ?
        """, (exec_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
            
        # Handle datetime parsing more robustly
        try:
            started_at = datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4]
            completed_at = datetime.fromisoformat(row[5]) if row[5] and isinstance(row[5], str) else row[5]
        except (ValueError, TypeError):
            # Fallback for any datetime parsing issues
            started_at = datetime.now()
            completed_at = None
            
        return Execution(
            id=row[0],
            doc_id=row[1],
            doc_title=row[2],
            status=row[3],
            started_at=started_at,
            completed_at=completed_at,
            log_file=row[6],
            exit_code=row[7],
            working_dir=row[8],
            pid=row[9] if len(row) > 9 else None  # Handle old records without PID
        )


def get_recent_executions(limit: int = 20) -> List[Execution]:
    """Get recent executions ordered by start time."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, doc_id, doc_title, status, started_at, completed_at, log_file, exit_code, working_dir, pid
            FROM executions 
            ORDER BY id DESC 
            LIMIT ?
        """, (limit,))
        
        executions = []
        for row in cursor.fetchall():
            # Parse timestamps with timezone handling
            started_at = parse_timestamp(row[4])
            completed_at = parse_timestamp(row[5]) if row[5] else None
                
            executions.append(Execution(
                id=int(row[0]),  # Convert to int for numeric ID
                doc_id=row[1],
                doc_title=row[2],
                status=row[3],
                started_at=started_at,
                completed_at=completed_at,
                log_file=row[6],
                exit_code=row[7],
                working_dir=row[8],
                pid=row[9] if len(row) > 9 else None
            ))
        
        return executions


def get_running_executions() -> List[Execution]:
    """Get all currently running executions."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, doc_id, doc_title, status, started_at, completed_at, log_file, exit_code, working_dir, pid
            FROM executions 
            WHERE status = 'running'
            ORDER BY started_at DESC
        """, )
        
        executions = []
        for row in cursor.fetchall():
            # Parse timestamps with timezone handling
            started_at = parse_timestamp(row[4])
            completed_at = parse_timestamp(row[5]) if row[5] else None
                
            executions.append(Execution(
                id=int(row[0]),  # Convert to int for numeric ID
                doc_id=row[1],
                doc_title=row[2],
                status=row[3],
                started_at=started_at,
                completed_at=completed_at,
                log_file=row[6],
                exit_code=row[7],
                working_dir=row[8],
                pid=row[9] if len(row) > 9 else None
            ))
        
        return executions


def update_execution_status(exec_id: int, status: str, exit_code: Optional[int] = None) -> None:
    """Update execution status and completion time."""
    with db_connection.get_connection() as conn:
        if status in ['completed', 'failed']:
            cursor = conn.execute("""
                UPDATE executions 
                SET status = ?, completed_at = CURRENT_TIMESTAMP, exit_code = ?
                WHERE id = ?
            """, (status, exit_code, exec_id))
        else:
            cursor = conn.execute("""
                UPDATE executions 
                SET status = ?
                WHERE id = ?
            """, (status, exec_id))
        
        conn.commit()


def update_execution_pid(exec_id: int, pid: int) -> None:
    """Update execution PID."""
    with db_connection.get_connection() as conn:
        conn.execute("""
            UPDATE executions 
            SET pid = ?
            WHERE id = ?
        """, (pid, exec_id))
        conn.commit()


def update_execution_working_dir(exec_id: int, working_dir: str) -> None:
    """Update execution working directory."""
    with db_connection.get_connection() as conn:
        conn.execute("""
            UPDATE executions 
            SET working_dir = ?
            WHERE id = ?
        """, (working_dir, exec_id))
        conn.commit()


def update_execution_heartbeat(exec_id: int) -> None:
    """Update execution heartbeat timestamp."""
    with db_connection.get_connection() as conn:
        conn.execute("""
            UPDATE executions 
            SET last_heartbeat = CURRENT_TIMESTAMP
            WHERE id = ? AND status = 'running'
        """, (exec_id,))
        conn.commit()


def get_stale_executions(timeout_seconds: int = 1800) -> List[Execution]:
    """Get executions that haven't sent a heartbeat recently.
    
    Args:
        timeout_seconds: Seconds after which an execution is considered stale (default 30 min)
        
    Returns:
        List of stale executions
    """
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        # Build interval string safely - timeout_seconds is validated as int by function signature
        interval = f'+{int(timeout_seconds)} seconds'
        cursor.execute("""
            SELECT id, doc_id, doc_title, status, started_at, completed_at,
                   log_file, exit_code, working_dir, pid
            FROM executions
            WHERE status = 'running'
            AND (
                last_heartbeat IS NULL AND datetime('now') > datetime(started_at, ?)
                OR
                last_heartbeat IS NOT NULL AND datetime('now') > datetime(last_heartbeat, ?)
            )
            ORDER BY started_at DESC
        """, (interval, interval))
        
        executions = []
        for row in cursor.fetchall():
            # Parse timestamps with timezone handling
            started_at = parse_timestamp(row[4])
            completed_at = parse_timestamp(row[5]) if row[5] else None
                
            executions.append(Execution(
                id=int(row[0]),
                doc_id=row[1],
                doc_title=row[2],
                status=row[3],
                started_at=started_at,
                completed_at=completed_at,
                log_file=row[6],
                exit_code=row[7],
                working_dir=row[8],
                pid=row[9] if len(row) > 9 else None
            ))
        
        return executions


def cleanup_old_executions(days: int = 7) -> int:
    """Clean up executions older than specified days."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        # Build interval string safely - days is validated as int by function signature
        interval = f'-{int(days)} days'
        cursor.execute("""
            DELETE FROM executions
            WHERE started_at < datetime('now', ?)
        """, (interval,))
        conn.commit()
        return cursor.rowcount


def get_execution_stats() -> dict:
    """Get execution statistics."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        
        # Count by status
        cursor.execute("""
            SELECT status, COUNT(*) 
            FROM executions 
            GROUP BY status
        """)
        status_counts = dict(cursor.fetchall())
        
        # Total executions
        cursor.execute("SELECT COUNT(*) FROM executions")
        total = cursor.fetchone()[0]
        
        # Recent activity (last 24 hours)
        cursor.execute("""
            SELECT COUNT(*) FROM executions 
            WHERE started_at > datetime('now', '-1 day')
        """)
        recent = cursor.fetchone()[0]
        
        return {
            'total': total,
            'recent_24h': recent,
            'running': status_counts.get('running', 0),
            'completed': status_counts.get('completed', 0),
            'failed': status_counts.get('failed', 0),
        }
