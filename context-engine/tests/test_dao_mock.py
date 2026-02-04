"""
Comprehensive tests for TestGraphDAO in-memory mock.

This module tests all TestGraphDAO methods independently and their interactions.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from graph_dao import TestGraphDAO
from datetime import datetime, timedelta


def test_add_and_get_action():
    """Test adding actions and retrieving them."""
    print("\n" + "="*50)
    print("Testing add and get action:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['summer2026']

    # Add action
    action_uuid = dao.add_action(
        node_uuid=node_uuid,
        action_name="Test Action",
        action_plan="Test Plan",
        action_prompt="Test Prompt"
    )

    assert action_uuid is not None
    print(f"Added action: {action_uuid}")

    # Get action by ID
    action = dao.get_action_by_id(action_uuid)
    assert action is not None
    assert action[1] == "Test Action"
    print(f"✓ Retrieved action by ID: {action[1]}")


def test_update_action():
    """Test updating action fields."""
    print("\n" + "="*50)
    print("Testing update action:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['recruiting']

    action_uuid = dao.add_action(node_uuid, "Original Name", "Original Plan", "Original Prompt")

    # Update action
    success = dao.update_action(action_uuid, "Updated Name", "Updated Plan", "Updated Prompt")
    assert success is True

    # Verify update
    actions = dao.get_actions_for_node(node_uuid)
    assert len(actions) == 1
    assert actions[0][1] == "Updated Name"
    assert actions[0][2] == "Updated Plan"
    assert actions[0][3] == "Updated Prompt"

    print("✓ Action updated successfully")


def test_update_action_last_selected():
    """Test updating last_selected timestamp."""
    print("\n" + "="*50)
    print("Testing update action last_selected:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['intern']

    action_uuid = dao.add_action(node_uuid, "Action 1")

    # Update with automatic timestamp
    success = dao.update_action_last_selected(action_uuid)
    assert success is True

    # Verify timestamp was set
    actions = dao.get_actions_for_node(node_uuid)
    assert actions[0][5] is not None
    print(f"✓ Timestamp updated: {actions[0][5][:19]}")

    # Update with specific timestamp
    specific_time = "2025-01-15T12:00:00"
    success = dao.update_action_last_selected(action_uuid, specific_time)
    assert success is True

    actions = dao.get_actions_for_node(node_uuid)
    assert actions[0][5] == specific_time
    print(f"✓ Specific timestamp set: {actions[0][5]}")


def test_get_actions_sorted_by_last_selected():
    """Test getting actions sorted by last_selected with NULLs last."""
    print("\n" + "="*50)
    print("Testing actions sorted by last_selected:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['new_grad']

    # Add actions with different timestamps
    old_time = (datetime.now() - timedelta(days=5)).isoformat()
    recent_time = datetime.now().isoformat()

    uuid1 = dao.add_action(node_uuid, "Old Action", last_selected=old_time)
    uuid2 = dao.add_action(node_uuid, "Recent Action", last_selected=recent_time)
    uuid3 = dao.add_action(node_uuid, "Never Selected")  # NULL timestamp

    # Get sorted actions
    actions = dao.get_actions_for_node(node_uuid, order_by_last_selected=True)

    assert len(actions) == 3
    assert actions[0][0] == uuid2  # Most recent first
    assert actions[1][0] == uuid1  # Older second
    assert actions[2][0] == uuid3  # NULL last

    print(f"✓ Order correct: Recent -> Old -> NULL")


def test_get_recent_actions():
    """Test getting N most recent actions."""
    print("\n" + "="*50)
    print("Testing get recent actions:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['events']

    # Add 6 actions with timestamps
    for i in range(6):
        timestamp = (datetime.now() - timedelta(days=i)).isoformat()
        dao.add_action(node_uuid, f"Action {i}", last_selected=timestamp)

    # Add one without timestamp
    dao.add_action(node_uuid, "Never Selected")

    # Get 4 most recent
    recent = dao.get_recent_actions_for_node(node_uuid, limit=4)

    assert len(recent) == 4
    # Should be sorted newest first
    for i in range(3):
        assert recent[i][5] > recent[i+1][5]

    print(f"✓ Got {len(recent)} most recent actions")


def test_delete_stale_actions():
    """Test deleting stale actions based on date threshold."""
    print("\n" + "="*50)
    print("Testing delete stale actions:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['onboarding']

    # Add actions with different ages
    very_old = (datetime.now() - timedelta(days=10)).isoformat()
    old = (datetime.now() - timedelta(days=5)).isoformat()
    recent = datetime.now().isoformat()

    uuid1 = dao.add_action(node_uuid, "Very Old", last_selected=very_old)
    uuid2 = dao.add_action(node_uuid, "Old", last_selected=old)
    uuid3 = dao.add_action(node_uuid, "Recent", last_selected=recent)
    uuid4 = dao.add_action(node_uuid, "Never Selected")  # NULL - should NOT be deleted

    # Delete actions older than 3 days
    deleted = dao.delete_stale_actions(node_uuid, days_threshold=3)

    assert deleted == 2  # very_old and old
    remaining = dao.get_actions_for_node(node_uuid)
    assert len(remaining) == 2

    # Verify correct ones remain
    remaining_uuids = [action[0] for action in remaining]
    assert uuid3 in remaining_uuids  # Recent still there
    assert uuid4 in remaining_uuids  # Never selected still there
    assert uuid1 not in remaining_uuids  # Very old deleted
    assert uuid2 not in remaining_uuids  # Old deleted

    print(f"✓ Deleted {deleted} stale actions, kept 2")


def test_add_and_get_data():
    """Test adding data entries and retrieving them."""
    print("\n" + "="*50)
    print("Testing add and get data:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['issues']

    # Add data
    data_uuid = dao.add_data(
        node_uuid=node_uuid,
        key="test_key",
        data_type="text",
        info="Test information"
    )

    assert data_uuid is not None

    # Get data
    data_list = dao.get_data_for_node(node_uuid)
    assert len(data_list) == 1
    assert data_list[0][2] == "test_key"
    assert data_list[0][4] == "Test information"

    print("✓ Data added and retrieved successfully")


def test_add_data_with_category():
    """Test adding data with category."""
    print("\n" + "="*50)
    print("Testing add data with category:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['career_fair']

    # Add data with category
    uuid1 = dao.add_data_with_category(
        node_uuid, "emails", "key1", "text", "Email content 1"
    )
    uuid2 = dao.add_data_with_category(
        node_uuid, "emails", "key2", "text", "Email content 2"
    )
    uuid3 = dao.add_data_with_category(
        node_uuid, "meetings", "key3", "text", "Meeting notes"
    )

    # Get categories
    categories = dao.get_categories_for_node(node_uuid)
    assert "emails" in categories
    assert "meetings" in categories
    assert len(categories) == 2

    print(f"✓ Categories: {categories}")


def test_get_data_by_category():
    """Test getting data grouped by category."""
    print("\n" + "="*50)
    print("Testing get data by category:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['2026']

    # Add data in multiple categories
    dao.add_data(node_uuid, "k1", "text", "Info 1", "cat1")
    dao.add_data(node_uuid, "k2", "text", "Info 2", "cat1")
    dao.add_data(node_uuid, "k3", "text", "Info 3", "cat1")
    dao.add_data(node_uuid, "k4", "text", "Info 4", "cat2")
    dao.add_data(node_uuid, "k5", "text", "Info 5")  # No category

    # Get grouped data
    grouped = dao.get_data_for_node_by_category(node_uuid)

    assert "cat1" in grouped
    assert "cat2" in grouped
    assert "uncategorized" in grouped

    assert len(grouped["cat1"]) == 3
    assert len(grouped["cat2"]) == 1
    assert len(grouped["uncategorized"]) == 1

    print(f"✓ Data grouped correctly: {list(grouped.keys())}")


def test_delete_data_by_category():
    """Test deleting all data in a category."""
    print("\n" + "="*50)
    print("Testing delete data by category:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['online_webinar']

    # Add data
    dao.add_data_with_category(node_uuid, "temp", "k1", "text", "Temp 1")
    dao.add_data_with_category(node_uuid, "temp", "k2", "text", "Temp 2")
    dao.add_data_with_category(node_uuid, "temp", "k3", "text", "Temp 3")
    dao.add_data_with_category(node_uuid, "keep", "k4", "text", "Keep me")

    # Delete temp category
    deleted = dao.delete_data_by_category(node_uuid, "temp")
    assert deleted == 3

    # Verify deletion
    grouped = dao.get_data_for_node_by_category(node_uuid)
    assert "temp" not in grouped
    assert "keep" in grouped
    assert len(grouped["keep"]) == 1

    print(f"✓ Deleted {deleted} entries from 'temp' category")


def test_node_counter_operations():
    """Test increment, get, and reset counter."""
    print("\n" + "="*50)
    print("Testing node counter operations:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['career_conference']

    # Initial count should be 0
    assert dao.get_node_counter(node_uuid) == 0

    # Increment
    count = dao.increment_node_counter(node_uuid)
    assert count == 1
    assert dao.get_node_counter(node_uuid) == 1

    # Increment multiple times
    for i in range(9):
        dao.increment_node_counter(node_uuid)

    assert dao.get_node_counter(node_uuid) == 10

    # Reset
    success = dao.reset_node_counter(node_uuid)
    assert success is True
    assert dao.get_node_counter(node_uuid) == 0

    # Verify last_cleanup was set
    assert 'last_cleanup' in dao.node_counters[node_uuid]
    assert dao.node_counters[node_uuid]['last_cleanup'] is not None

    print("✓ Counter operations work correctly")


def test_get_nodes_needing_cleanup():
    """Test identifying nodes that need cleanup."""
    print("\n" + "="*50)
    print("Testing get nodes needing cleanup:")
    print("="*50)

    dao = TestGraphDAO()

    node1 = dao.node_uuids['summer2026']
    node2 = dao.node_uuids['fall2026']
    node3 = dao.node_uuids['2025']

    # Set different counter values
    for _ in range(15):
        dao.increment_node_counter(node1)

    for _ in range(5):
        dao.increment_node_counter(node2)

    for _ in range(2):
        dao.increment_node_counter(node3)

    # Get nodes needing cleanup with threshold=5
    nodes = dao.get_nodes_needing_cleanup(threshold=5)

    assert node1 in nodes  # 15 >= 5
    assert node2 in nodes  # 5 >= 5
    assert node3 not in nodes  # 2 < 5

    # Try different threshold
    nodes_high = dao.get_nodes_needing_cleanup(threshold=10)
    assert node1 in nodes_high  # 15 >= 10
    assert node2 not in nodes_high  # 5 < 10
    assert node3 not in nodes_high  # 2 < 10

    print(f"✓ Threshold 5: {len(nodes)} nodes")
    print(f"✓ Threshold 10: {len(nodes_high)} nodes")


def test_edge_case_empty_results():
    """Test methods with empty results."""
    print("\n" + "="*50)
    print("Testing edge cases - empty results:")
    print("="*50)

    dao = TestGraphDAO()
    nonexistent_uuid = "nonexistent-uuid-12345"

    # Get actions for nonexistent node
    actions = dao.get_actions_for_node(nonexistent_uuid)
    assert actions == []

    # Get data for nonexistent node
    data = dao.get_data_for_node(nonexistent_uuid)
    assert data == []

    # Get categories for nonexistent node
    categories = dao.get_categories_for_node(nonexistent_uuid)
    assert categories == []

    # Get counter for nonexistent node
    counter = dao.get_node_counter(nonexistent_uuid)
    assert counter == 0

    # Update nonexistent action
    success = dao.update_action(nonexistent_uuid, "Name", "Plan", "Prompt")
    assert success is False

    # Get action by nonexistent ID
    action = dao.get_action_by_id(nonexistent_uuid)
    assert action is None

    print("✓ All empty result cases handled correctly")


def test_edge_case_nonexistent_uuid():
    """Test operations on nonexistent UUIDs."""
    print("\n" + "="*50)
    print("Testing edge cases - nonexistent UUIDs:")
    print("="*50)

    dao = TestGraphDAO()
    fake_uuid = "fake-uuid-999"

    # Try to update last_selected on nonexistent action
    success = dao.update_action_last_selected(fake_uuid)
    assert success is False

    # Delete data from nonexistent category
    deleted = dao.delete_data_by_category(fake_uuid, "nonexistent_category")
    assert deleted == 0

    # Delete stale actions from nonexistent node
    deleted = dao.delete_stale_actions(fake_uuid, days_threshold=3)
    assert deleted == 0

    print("✓ Nonexistent UUID operations handled gracefully")


def test_interaction_add_update_retrieve():
    """Test interaction between add, update, and retrieve."""
    print("\n" + "="*50)
    print("Testing interaction - add, update, retrieve:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['recruiting']

    # Add action
    action_uuid = dao.add_action(
        node_uuid, "Initial Action", "Initial Plan", "Initial Prompt"
    )

    # Update it
    dao.update_action(action_uuid, "Updated Action", "Updated Plan", "Updated Prompt")

    # Update timestamp
    timestamp = "2025-01-20T10:00:00"
    dao.update_action_last_selected(action_uuid, timestamp)

    # Retrieve and verify all fields
    action = dao.get_action_by_id(action_uuid)
    assert action[1] == "Updated Action"

    actions = dao.get_actions_for_node(node_uuid)
    assert len(actions) == 1
    assert actions[0][1] == "Updated Action"
    assert actions[0][2] == "Updated Plan"
    assert actions[0][3] == "Updated Prompt"
    assert actions[0][5] == timestamp

    print("✓ Add -> Update -> Retrieve works correctly")


def test_get_all_nodes():
    """Test getting all nodes from test graph."""
    print("\n" + "="*50)
    print("Testing get_all_nodes:")
    print("="*50)

    dao = TestGraphDAO()

    nodes = dao.get_all_nodes()
    assert len(nodes) > 0

    # Verify structure
    for node in nodes:
        assert len(node) >= 6  # Should have at least 6 fields
        assert node[0] is not None  # UUID
        assert node[1] is not None  # Metadata

    print(f"✓ Retrieved {len(nodes)} nodes")


def test_get_node_by_id():
    """Test getting node by UUID."""
    print("\n" + "="*50)
    print("Testing get_node_by_id:")
    print("="*50)

    dao = TestGraphDAO()

    # Get existing node
    node_uuid = dao.node_uuids['summer2026']
    node = dao.get_node_by_id(node_uuid)

    assert node is not None
    assert node[0] == node_uuid
    assert node[1] == "Summer 2026"

    # Try nonexistent node
    fake_node = dao.get_node_by_id("fake-node-uuid")
    assert fake_node is None

    print("✓ Node retrieval works correctly")


def run_all_tests():
    """Run all TestGraphDAO tests."""
    print("\n" + "="*70)
    print("RUNNING ALL TESTGRAPHDAO TESTS")
    print("="*70)

    # Basic CRUD tests
    test_add_and_get_action()
    test_update_action()
    test_update_action_last_selected()
    test_add_and_get_data()
    test_add_data_with_category()

    # Sorting and filtering tests
    test_get_actions_sorted_by_last_selected()
    test_get_recent_actions()
    test_delete_stale_actions()
    test_get_data_by_category()
    test_delete_data_by_category()

    # Counter tests
    test_node_counter_operations()
    test_get_nodes_needing_cleanup()

    # Edge case tests
    test_edge_case_empty_results()
    test_edge_case_nonexistent_uuid()

    # Interaction tests
    test_interaction_add_update_retrieve()

    # Node tests
    test_get_all_nodes()
    test_get_node_by_id()

    print("\n" + "="*70)
    print("ALL TESTGRAPHDAO TESTS COMPLETED")
    print("="*70)


if __name__ == "__main__":
    run_all_tests()
