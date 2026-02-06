#!/usr/bin/env python3
"""
Seed dummy action history records for testing the History Page UI.

Usage:
    python tests/seed_action_history.py
    
    # Clear existing and add fresh:
    python tests/seed_action_history.py --clear
"""

import argparse
import json
import os
import random
import sqlite3
import sys
import uuid
from datetime import datetime, timedelta

# Add context-engine to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'context-engine'))

# Database path
DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'context-engine', 'graph.db')


# Sample action types
ACTION_TYPES = [
    "Create Calendar Event",
    "Send Email",
    "Search Files",
    "Create GitHub Issue",
    "Update Notion Page",
    "List Drive Files",
    "Schedule Meeting",
    "Search Perplexity",
    "Read Gmail",
    "Create Task",
]

# Sample action data templates
ACTION_DATA_TEMPLATES = [
    {
        "action_name": "Create Calendar Event",
        "action_plan": "Create a meeting on the user's calendar",
        "action_prompt": "Create a calendar event titled 'Team Standup' for tomorrow at 10am"
    },
    {
        "action_name": "Send Email",
        "action_plan": "Send an email to the specified recipient",
        "action_prompt": "Send an email to team@company.com with subject 'Weekly Update'"
    },
    {
        "action_name": "Search Files",
        "action_plan": "Search for files in Google Drive",
        "action_prompt": "Find all PDF files modified in the last week"
    },
    {
        "action_name": "Create GitHub Issue",
        "action_plan": "Create a new issue in the repository",
        "action_prompt": "Create an issue titled 'Bug: Login not working' in covalent-calhacks repo"
    },
    {
        "action_name": "Update Notion Page",
        "action_plan": "Update content in a Notion page",
        "action_prompt": "Add a new section to the project roadmap page"
    },
]

# Sample result templates
RESULT_TEMPLATES = [
    {"status": "success", "event_id": "evt_abc123", "link": "https://calendar.google.com/event/abc123"},
    {"status": "success", "message_id": "msg_xyz789", "recipients": ["user@example.com"]},
    {"status": "success", "files_found": 15, "total_size_mb": 42.5},
    {"status": "success", "issue_number": 123, "url": "https://github.com/user/repo/issues/123"},
    {"status": "success", "page_id": "page_12345", "last_edited": "2024-01-15T10:30:00Z"},
]

# Sample error messages
ERROR_MESSAGES = [
    "API rate limit exceeded. Please try again later.",
    "Authentication failed: Token expired",
    "Network timeout after 30 seconds",
    "Permission denied: Insufficient scopes",
    "Resource not found: The specified file does not exist",
    "Invalid request: Missing required field 'title'",
]


def create_dummy_actions(count: int = 20, include_failures: bool = True):
    """Generate dummy action history records."""
    actions = []
    now = datetime.now()
    
    for i in range(count):
        # Random time in the past (up to 7 days)
        random_hours = random.randint(0, 168)
        timestamp = now - timedelta(hours=random_hours, minutes=random.randint(0, 59))
        
        # Pick random action type
        action_idx = random.randint(0, len(ACTION_TYPES) - 1)
        action_type = ACTION_TYPES[action_idx]
        
        # Determine status (80% success, 20% failure if include_failures)
        if include_failures and random.random() < 0.2:
            status = "failed"
            result = None
            error_message = random.choice(ERROR_MESSAGES)
            duration_ms = random.randint(100, 30000)  # Failures often timeout
        else:
            status = "completed"
            result = json.dumps(random.choice(RESULT_TEMPLATES))
            error_message = None
            duration_ms = random.randint(50, 5000)  # Successful actions are usually faster
        
        # Pick action data
        action_data_template = ACTION_DATA_TEMPLATES[action_idx % len(ACTION_DATA_TEMPLATES)]
        action_data = json.dumps({
            **action_data_template,
            "action_name": action_type,
        })
        
        actions.append({
            "action_uuid": str(uuid.uuid4()),
            "action_type": action_type,
            "action_data": action_data,
            "creation_timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "node_uuid": str(uuid.uuid4()) if random.random() > 0.3 else None,
            "status": status,
            "result": result,
            "error_message": error_message,
            "duration_ms": duration_ms,
        })
    
    # Sort by timestamp (newest first for consistency)
    actions.sort(key=lambda x: x["creation_timestamp"], reverse=True)
    
    return actions


def insert_actions(conn: sqlite3.Connection, actions: list):
    """Insert action records into the database."""
    cursor = conn.cursor()
    
    for action in actions:
        cursor.execute(
            """
            INSERT INTO action_history 
            (action_uuid, action_type, action_data, creation_timestamp, node_uuid, status, result, error_message, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                action["action_uuid"],
                action["action_type"],
                action["action_data"],
                action["creation_timestamp"],
                action["node_uuid"],
                action["status"],
                action["result"],
                action["error_message"],
                action["duration_ms"],
            )
        )
    
    conn.commit()
    return len(actions)


def clear_action_history(conn: sqlite3.Connection):
    """Clear all action history records."""
    cursor = conn.cursor()
    cursor.execute("DELETE FROM action_history")
    deleted = cursor.rowcount
    conn.commit()
    return deleted


def main():
    parser = argparse.ArgumentParser(description="Seed dummy action history for testing")
    parser.add_argument("--count", type=int, default=25, help="Number of dummy actions to create (default: 25)")
    parser.add_argument("--clear", action="store_true", help="Clear existing action history before seeding")
    parser.add_argument("--no-failures", action="store_true", help="Only create successful actions (no failures)")
    parser.add_argument("--db-path", default=DB_PATH, help="Path to the SQLite database")
    args = parser.parse_args()
    
    print(f"📂 Database: {args.db_path}")
    
    if not os.path.exists(args.db_path):
        print("❌ Database file not found. Run init_db.py first.")
        sys.exit(1)
    
    conn = sqlite3.connect(args.db_path, timeout=10.0)
    
    try:
        # Check if table exists
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='action_history'")
        if not cursor.fetchone():
            print("❌ action_history table not found. Run init_db.py first.")
            sys.exit(1)
        
        # Clear if requested
        if args.clear:
            deleted = clear_action_history(conn)
            print(f"🗑️  Cleared {deleted} existing action history records")
        
        # Generate and insert dummy actions
        actions = create_dummy_actions(
            count=args.count,
            include_failures=not args.no_failures
        )
        
        inserted = insert_actions(conn, actions)
        
        # Summary
        success_count = sum(1 for a in actions if a["status"] == "completed")
        failed_count = sum(1 for a in actions if a["status"] == "failed")
        
        print(f"✅ Inserted {inserted} dummy action history records")
        print(f"   - Completed: {success_count}")
        print(f"   - Failed: {failed_count}")
        
        # Show sample
        print("\n📋 Sample actions inserted:")
        for action in actions[:5]:
            status_icon = "✓" if action["status"] == "completed" else "✗"
            print(f"   {status_icon} {action['action_type']} ({action['duration_ms']}ms) - {action['creation_timestamp']}")
        
        if len(actions) > 5:
            print(f"   ... and {len(actions) - 5} more")
        
    finally:
        conn.close()
    
    print("\n🎉 Done! Refresh the History page to see the dummy actions.")


if __name__ == "__main__":
    main()
