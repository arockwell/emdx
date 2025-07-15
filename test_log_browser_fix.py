#!/usr/bin/env python3
"""
Test script to verify log browser 'l' key fix.
This creates a test execution entry to ensure log browser has something to display.
"""

import sqlite3
from pathlib import Path
from datetime import datetime
import tempfile
import os

# Find the EMDX database
db_path = Path.home() / ".emdx.db"
if not db_path.exists():
    print(f"EMDX database not found at {db_path}")
    exit(1)

# Create a test log file
log_dir = Path.home() / ".emdx" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

# Create test log content
test_log = log_dir / f"test_execution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
test_log.write_text("""Test Execution Log
==================

This is a test execution log created to verify the log browser functionality.

[2025-07-15 10:00:00] Starting execution...
[2025-07-15 10:00:01] Processing document...
[2025-07-15 10:00:02] Execution completed successfully.

Test Results:
- Log browser 'l' key: Testing...
- Navigation with j/k: Testing...
- Mark complete with 'm': Testing...
""")

print(f"Created test log: {test_log}")

# Create a test execution entry in the database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check if executions table exists
cursor.execute("""
    SELECT name FROM sqlite_master 
    WHERE type='table' AND name='executions'
""")
if not cursor.fetchone():
    print("Creating executions table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS executions (
            id TEXT PRIMARY KEY,
            doc_id INTEGER,
            doc_title TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            status TEXT,
            exit_code INTEGER,
            log_file TEXT,
            duration REAL,
            FOREIGN KEY (doc_id) REFERENCES documents(id)
        )
    """)

# Insert a test execution
execution_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
cursor.execute("""
    INSERT OR REPLACE INTO executions 
    (id, doc_id, doc_title, started_at, status, log_file, duration)
    VALUES (?, ?, ?, ?, ?, ?, ?)
""", (
    execution_id,
    1,  # Dummy doc_id
    "Test Document for Log Browser",
    datetime.now().isoformat(),
    "completed",
    str(test_log),
    5.0  # 5 second duration
))

conn.commit()
conn.close()

print(f"Created test execution: {execution_id}")
print("\nTo test the fix:")
print("1. Run: emdx gui")
print("2. Press 'l' to enter log browser mode")
print("3. You should see the test execution in the list")
print("4. Press 'j'/'k' to navigate between executions")
print("5. Press 'm' to mark an execution as complete")
print("6. Press 'q' to exit log browser mode")