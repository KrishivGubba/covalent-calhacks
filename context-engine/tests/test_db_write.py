#!/usr/bin/env python3
"""
Quick test to verify database write permissions
"""
import sys
import os

# Add the parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from graph_dao import GraphDAO
import uuid

db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'graph.db')

print(f"Testing database write permissions for: {db_path}")
print(f"File exists: {os.path.exists(db_path)}")
print(f"File permissions: {oct(os.stat(db_path).st_mode)[-3:]}")

try:
    # Create DAO instance
    dao = GraphDAO(db_path)
    print("✓ Successfully opened database connection")
    
    # Try to write a test action
    test_node_uuid = str(uuid.uuid4())
    test_action_name = "TEST_ACTION_DELETE_ME"
    test_action_plan = "This is a test action to verify write permissions"
    test_action_prompt = "Test prompt"
    
    print(f"\nAttempting to insert test action...")
    action_uuid = dao.add_action(
        node_uuid=test_node_uuid,
        action_name=test_action_name,
        action_plan=test_action_plan,
        action_prompt=test_action_prompt
    )
    
    print(f"✅ SUCCESS! Action inserted with UUID: {action_uuid}")
    print(f"\nDatabase is now writable! You can restart your app.")
    
    # Clean up test data
    print(f"\nCleaning up test action...")
    dao.execute_query("DELETE FROM action_table WHERE UUID = ?", (action_uuid,))
    print(f"✓ Test action removed")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
