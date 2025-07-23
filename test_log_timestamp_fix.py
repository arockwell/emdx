#!/usr/bin/env python3
"""
Test script to verify log browser timestamp fix.
Creates test log files with known timestamps to verify they display correctly.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import time
import json

# Find the EMDX database
db_path = Path.home() / ".emdx.db"
if not db_path.exists():
    print(f"EMDX database not found at {db_path}")
    exit(1)

# Create test log directory
log_dir = Path.home() / ".config" / "emdx" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

# Create test log with both timestamp formats
test_time = datetime.now() - timedelta(hours=2)  # 2 hours ago
test_log = log_dir / f"test_timestamp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Write test log content with various timestamp formats
log_content = f"""=== EMDX Claude Execution ===
Version: 1.0.0
Build ID: test
Doc ID: 999
Execution ID: test-timestamp-{int(time.time())}
Started: {test_time.strftime('%Y-%m-%d %H:%M:%S')}
==================================================

[{test_time.strftime('%H:%M:%S')}] 🚀 Claude Code session started
[{test_time.strftime('%H:%M:%S')}] 📋 Available tools: Read, Write, Edit
[{test_time.strftime('%H:%M:%S')}] 📝 Prompt being sent to Claude:
------------------------------------------------------------
Test task for timestamp verification
------------------------------------------------------------

[{(test_time + timedelta(seconds=1)).strftime('%H:%M:%S')}] 🤖 Claude: Starting task...
[{(test_time + timedelta(seconds=2)).strftime('%H:%M:%S')}] 📖 Using tool: Read
[{(test_time + timedelta(seconds=3)).strftime('%H:%M:%S')}] 📄 Tool result: File content...
Some multi-line output without timestamp
that should inherit the previous timestamp
[{(test_time + timedelta(seconds=5)).strftime('%H:%M:%S')}] 🤖 Claude: Processing file...
[{(test_time + timedelta(seconds=10)).strftime('%H:%M:%S')}] ✏️ Using tool: Edit
[{(test_time + timedelta(seconds=15)).strftime('%H:%M:%S')}] 📄 Tool result: Edit successful
[{(test_time + timedelta(seconds=20)).strftime('%H:%M:%S')}] ✅ Task completed successfully!

[{test_time.strftime('%Y-%m-%d %H:%M:%S')}] Test with full datetime format
[{(test_time + timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S')}] Another full datetime entry
"""

# Write test log
test_log.write_text(log_content)
print(f"Created test log: {test_log}")

# Create test execution entry in the database
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
            working_dir TEXT,
            pid INTEGER,
            FOREIGN KEY (doc_id) REFERENCES documents(id)
        )
    """)

# Insert test execution
execution_id = f"test-timestamp-{int(time.time())}"
cursor.execute("""
    INSERT OR REPLACE INTO executions 
    (id, doc_id, doc_title, started_at, completed_at, status, log_file, duration, working_dir)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    execution_id,
    999,  # Dummy doc_id
    "Timestamp Fix Test Document",
    test_time.isoformat(),
    (test_time + timedelta(seconds=20)).isoformat(),
    "completed",
    str(test_log),
    20.0,  # 20 second duration
    "/test/working/dir"
))

conn.commit()
conn.close()

print(f"Created test execution: {execution_id}")
print("\nTo test the timestamp fix:")
print("1. Run: emdx gui")
print("2. Press 'l' to enter log browser mode")
print("3. Look for 'Timestamp Fix Test Document' in the list")
print("4. Select it and verify that:")
print(f"   - Timestamps show times from ~2 hours ago ({test_time.strftime('%H:%M:%S')})")
print("   - NOT the current time when viewing")
print("   - Multi-line entries preserve the last known timestamp")
print("5. Press 'q' to exit log browser mode")
print("\nExpected behavior:")
print("- All log entries should show their original timestamps")
print("- Not the current time when viewed")
print("- This confirms the fix is working correctly")