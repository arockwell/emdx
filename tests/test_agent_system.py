#!/usr/bin/env python3
"""Test script for EMDX agent system."""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from emdx.database.migrations import run_migrations
from emdx.database.connection import db_connection
from emdx.agents.registry import agent_registry


def test_migration():
    """Test that the migration creates agent tables."""
    print("Running migrations...")
    run_migrations()
    
    print("\nChecking agent tables...")
    with db_connection.get_connection() as conn:
        cursor = conn.cursor()
        
        # Check that tables exist
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name IN ('agents', 'agent_executions', 'agent_pipelines', 'agent_templates')
            ORDER BY name
        """)
        tables = [row['name'] for row in cursor.fetchall()]
        print(f"Found tables: {tables}")
        
        # Check default agents
        cursor.execute("SELECT id, name, display_name, category FROM agents WHERE is_builtin = TRUE")
        agents = cursor.fetchall()
        print(f"\nFound {len(agents)} built-in agents:")
        for agent in agents:
            print(f"  - {agent['display_name']} ({agent['name']}) - {agent['category']}")


def test_agent_list():
    """Test listing agents via registry."""
    print("\n\nTesting agent registry...")
    agents = agent_registry.list_agents()
    print(f"Registry found {len(agents)} agents")
    
    for agent in agents:
        print(f"\nAgent: {agent['display_name']}")
        print(f"  Name: {agent['name']}")
        print(f"  Category: {agent['category']}")
        print(f"  Tools: {agent['allowed_tools']}")


def test_agent_load():
    """Test loading an agent."""
    print("\n\nTesting agent loading...")
    
    # Try loading by name
    agent = agent_registry.get_agent_by_name('doc-generator')
    if agent:
        print(f"Successfully loaded agent: {agent.config.display_name}")
        print(f"  System prompt preview: {agent.config.system_prompt[:100]}...")
        print(f"  User prompt preview: {agent.config.user_prompt_template[:100]}...")
    else:
        print("Failed to load doc-generator agent")


if __name__ == "__main__":
    print("EMDX Agent System Test")
    print("=" * 50)
    
    try:
        test_migration()
        test_agent_list()
        test_agent_load()
        print("\n✅ All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()