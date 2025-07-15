"""Execution tracking models and database operations."""

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from ..database.connection import db_connection


@dataclass
class Execution:
    """Represents a Claude execution."""
    id: str
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


def save_execution(execution: Execution) -> None:
    """Save execution to database."""
    with db_connection.get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO executions 
            (id, doc_id, doc_title, status, started_at, completed_at, log_file, exit_code, working_dir, pid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            execution.id,
            execution.doc_id,
            execution.doc_title,
            execution.status,
            execution.started_at.isoformat() if execution.started_at else None,
            execution.completed_at.isoformat() if execution.completed_at else None,
            execution.log_file,
            execution.exit_code,
            execution.working_dir,
            execution.pid
        ))
        conn.commit()


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
            ORDER BY started_at DESC 
            LIMIT ?
        """, (limit,))
        
        executions = []
        for row in cursor.fetchall():
            # Handle datetime parsing more robustly
            try:
                started_at = datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4]
                completed_at = datetime.fromisoformat(row[5]) if row[5] and isinstance(row[5], str) else row[5]
            except (ValueError, TypeError):
                # Fallback for any datetime parsing issues
                started_at = datetime.now()
                completed_at = None
                
            executions.append(Execution(
                id=row[0],
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
            # Handle datetime parsing more robustly
            try:
                started_at = datetime.fromisoformat(row[4]) if isinstance(row[4], str) else row[4]
                completed_at = datetime.fromisoformat(row[5]) if row[5] and isinstance(row[5], str) else row[5]
            except (ValueError, TypeError):
                # Fallback for any datetime parsing issues
                started_at = datetime.now()
                completed_at = None
                
            executions.append(Execution(
                id=row[0],
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


def update_execution_status(exec_id: str, status: str, exit_code: Optional[int] = None) -> None:
    """Update execution status and completion time."""
    with db_connection.get_connection() as conn:
        if status in ['completed', 'failed']:
            conn.execute("""
                UPDATE executions 
                SET status = ?, completed_at = CURRENT_TIMESTAMP, exit_code = ?
                WHERE id = ?
            """, (status, exit_code, exec_id))
        else:
            conn.execute("""
                UPDATE executions 
                SET status = ?
                WHERE id = ?
            """, (status, exec_id))
        conn.commit()


def update_execution_pid(exec_id: str, pid: int) -> None:
    """Update execution PID."""
    with db_connection.get_connection() as conn:
        conn.execute("""
            UPDATE executions 
            SET pid = ?
            WHERE id = ?
        """, (pid, exec_id))
        conn.commit()


def cleanup_old_executions(days: int = 7) -> int:
    """Clean up executions older than specified days."""
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM executions 
            WHERE started_at < datetime('now', '-{} days')
        """.format(days))
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