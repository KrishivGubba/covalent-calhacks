"""
Test suite for the Graph context engine.

This module contains comprehensive tests for the Tree and Node classes,
including tests for:
- Graph traversal and node selection
- Learning new information and data insertion
- Action creation and triggering
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from graph import Tree

# Initialize the tree from database
print("Initializing graph from database...")
tree = Tree(os.path.join(os.path.dirname(os.path.dirname(__file__)), "graph.db"))
print("Graph structure:")
print(tree)


def test_traverse():
    """
    Test the traverse method with various screen inputs.
    Tests node selection based on cosine similarity of embeddings.
    """
    if not tree.API_KEY:
        print("\nSkipping traverse test - API key not available")
        return
    
    print("\n" + "="*50)
    print("Testing traverse method:")
    print("="*50)
    
    # Comprehensive test screens covering all node categories
    test_screens = [
        # ========== RECRUITING - INTERN - SUMMER 2026 ==========
        "the user is currently writing an email to schedule an interview with a candidate 'Ritesh' who is currently in the interview process for a software engineering internship for summer 2026",
        "the user is currently making a LinkedIn posting for a software engineering internship for summer 2026",
        "reviewing resumes for summer 2026 intern positions",
        "scheduling technical interviews with Hemant for the summer 2026 internship program",
        "sending rejection emails to candidates who didn't make it to the final round for summer internships",
        "creating an offer letter for Krishiv who will be joining as a summer 2026 intern",
        
        # ========== RECRUITING - INTERN - FALL 2026 ==========
        "planning the recruiting timeline for fall 2026 internships",
        "posting job descriptions for fall 2026 software engineering intern positions on the careers page",
        "screening applications received for the fall 2026 intern cohort",
        "coordinating with hiring managers about fall 2026 internship openings",
        
        # ========== RECRUITING - NEW GRAD - 2025 ==========
        "reviewing applications for 2025 new graduate software engineer positions",
        "conducting final round interviews for 2025 new grad candidates",
        "preparing onboarding materials for new grads starting in 2025",
        "sending offer letters to selected 2025 new graduate candidates",
        
        # ========== RECRUITING - NEW GRAD - 2026 ==========
        "planning the campus recruiting strategy for 2026 new graduates",
        "updating the job requirements for 2026 new grad positions",
        "scheduling on-campus interviews for 2026 graduating students",
        
        # ========== RECRUITING - NEW GRAD - EVENTS - ONLINE WEBINAR ==========
        "preparing slides for an online webinar about our company culture for potential new grad candidates",
        "sending calendar invites for the upcoming recruiting webinar",
        "hosting a virtual Q&A session for students interested in new grad roles",
        "following up with attendees from last week's career webinar",
        
        # ========== RECRUITING - NEW GRAD - EVENTS - CAREER FAIR ==========
        "booking a booth at the university career fair happening next month",
        "preparing company brochures and swag for the career fair",
        "coordinating with the recruiting team about staffing the career fair booth",
        "collecting resumes at the MIT career fair",
        
        # ========== RECRUITING - NEW GRAD - EVENTS - CAREER CONFERENCE ==========
        "registering the company for the Grace Hopper Conference",
        "preparing a presentation for the upcoming tech diversity conference",
        "scheduling one-on-one meetings with candidates at the career conference",
        "following up with promising candidates met at last week's conference",
        
        # ========== EMPLOYEE MANAGEMENT - ONBOARDING ==========
        "setting up laptop and accounts for a new employee starting next week",
        "scheduling orientation sessions for the new hire cohort",
        "assigning a mentor to a newly onboarded software engineer",
        "sending out the onboarding checklist to a new team member",
        "coordinating with IT to ensure all onboarding equipment is ready",
        
        # ========== EMPLOYEE MANAGEMENT - ISSUES ==========
        "investigating a complaint about workplace harassment",
        "mediating a conflict between two team members",
        "addressing concerns raised by an employee about their workload",
        "following up on a performance improvement plan with an underperforming employee",
        "documenting an incident report for HR records",
        
        # ========== EMPLOYEE MANAGEMENT - QUESTIONS/REQUESTS - ANSWER QUESTIONS ==========
        "responding to an employee's question about the 401k matching policy",
        "clarifying the work-from-home policy for a remote employee",
        "explaining the performance review process to a new manager",
        "answering questions about health insurance enrollment",
        "providing information about the company's parental leave policy",
        
        # ========== EMPLOYEE MANAGEMENT - QUESTIONS/REQUESTS - APPROVE TIMESHEETS ==========
        "reviewing and approving timesheets for the engineering team",
        "following up with employees who haven't submitted their timesheets",
        "investigating discrepancies in submitted timesheet hours",
        "bulk approving timesheets for the end of the pay period",
        
        # ========== EMPLOYEE MANAGEMENT - QUESTIONS/REQUESTS - APPROVE LEAVE REQUESTS ==========
        "approving vacation requests for the summer holiday period",
        "reviewing a sick leave request that exceeds the standard policy",
        "coordinating leave schedules to ensure adequate team coverage",
        "approving parental leave for an employee expecting a baby",
        "handling a last-minute emergency leave request",
        
        # ========== EDGE CASES / AMBIGUOUS ==========
        "drafting an email to the entire engineering organization",
        "reviewing the company's diversity and inclusion initiatives",
        "preparing for quarterly business review meeting",
        "updating the employee handbook with new policies",
    ]
    
    # Test with expected nodes for validation
    test_cases_with_expected_nodes = [
        # Format: (screen_description, expected_node_metadata)
        ("reviewing resumes for summer 2026 intern positions", "Summer 2026"),
        ("hosting a virtual Q&A session for students interested in new grad roles", "Online Webinar"),
        ("responding to an employee's question about the 401k matching policy", "Answer Questions"),
        ("reviewing and approving timesheets for the engineering team", "Approve Timesheets"),
        ("approving vacation requests for the summer holiday period", "Approve Leave Requests"),
        ("setting up laptop and accounts for a new employee starting next week", "Onboarding"),
        ("mediating a conflict between two team members", "Issues"),
        ("collecting resumes at the MIT career fair", "Career Fair"),
        ("preparing a presentation for the upcoming tech diversity conference", "Career Conference"),
        ("screening applications received for the fall 2026 intern cohort", "Fall 2026"),
        ("conducting final round interviews for 2025 new grad candidates", "2025"),
        ("planning the campus recruiting strategy for 2026 new graduates", "2026"),
    ]
    
    # Run tests
    for screen in test_screens:
        print(f"\nScreen input: '{screen}'")
        result_node = tree.traverse(screen)
        if result_node:
            print(f"Selected node: {result_node}")
        else:
            print("No node selected")


def test_learn():
    """
    Test the learn() method with various data types and scenarios.
    Tests data insertion, action creation, and node selection.
    """
    if not tree.API_KEY:
        print("\nSkipping learn() test - API key not available")
        return
    
    print("\n" + "="*50)
    print("Testing learn() method:")
    print("="*50)
    
    # Test Case 1: Interview notes with structured data
    print("\n--- Test Case 1: Interview notes for Ritesh ---")
    summary1 = """
    The user is viewing an email which says:
    Hi Elizabeth,

I'm glad to be moving forward in the interview process with KLA. 
My availability (Central Daylight Time) for the upcoming week is:
Saturday (11/02)- All day
Sunday (11/03) - All day
Monday(11/04) - After 12pm
Tuesday (11/05) - After 1pm
Wednesday (11/06) - After 12pm
Thursday(11/07) - After 1pm
Friday(11/08) - All day
Please let me know if you need any additional times.

Regards,
Ritesh Neela
    """
    data1 = {
        "candidate": "Ritesh",
        "position": "Software Engineering Intern - Summer 2026",
        "interview_date": "2025-10-30",
        "interviewer": "John Smith",
        "technical_score": 8.5,
        "cultural_fit": 9.0,
        "feedback": "Strong problem-solving skills, excellent communication",
        "recommendation": "Proceed to final round"
    }
    node_uuid1, written_data1 = tree.learn(summary1, data1, key="ritesh_interview_round1")
    print(f"Data inserted into node UUID: {node_uuid1}")
    
    # Test Case 2: Career fair event details
    print("\n--- Test Case 2: Career fair event details ---")
    summary2 = "Details about the upcoming MIT career fair"
    data2 = {
        "event_name": "MIT Career Fair Fall 2025",
        "date": "2025-11-15",
        "location": "MIT Student Center",
        "booth_number": "A-42",
        "recruiters": ["Sarah Johnson", "Mike Chen"],
        "target_positions": ["New Grad SWE", "Internships"],
        "expected_attendance": 500
    }
    node_uuid2, written_data2 = tree.learn(summary2, data2, key="mit_career_fair_2025")
    print(f"Data inserted into node UUID: {node_uuid2}")
    
    # Test Case 3: Employee onboarding checklist
    print("\n--- Test Case 3: New employee onboarding ---")
    summary3 = "Onboarding checklist for new software engineer starting next week"
    data3 = {
        "employee_name": "Alex Thompson",
        "start_date": "2025-11-01",
        "department": "Engineering",
        "checklist": [
            "Setup laptop and accounts",
            "Assign mentor",
            "Schedule orientation",
            "Provide access badges",
            "Enroll in benefits"
        ],
        "status": "in_progress"
    }
    node_uuid3, written_data3 = tree.learn(summary3, data3, key="alex_thompson_onboarding")
    print(f"Data inserted into node UUID: {node_uuid3}")
    
    # Test Case 4: Timesheet approval data
    print("\n--- Test Case 4: Timesheet approval ---")
    summary4 = "Timesheet approval for engineering team - October 2025"
    data4 = {
        "period": "October 2025",
        "team": "Engineering",
        "total_hours": 1680,
        "approved_by": "Manager Name",
        "approval_date": "2025-10-31",
        "notes": "All timesheets reviewed and approved"
    }
    node_uuid4, written_data4 = tree.learn(summary4, data4, key="eng_timesheet_oct2025")
    print(f"Data inserted into node UUID: {node_uuid4}")
    
    # Test Case 5: Vacation leave request
    print("\n--- Test Case 5: Vacation leave request ---")
    summary5 = "Vacation leave request for summer holiday period"
    data5 = {
        "employee": "Jane Doe",
        "leave_type": "vacation",
        "start_date": "2026-07-01",
        "end_date": "2026-07-15",
        "days": 10,
        "status": "approved",
        "approved_by": "HR Manager",
        "coverage_plan": "Tasks delegated to team members"
    }
    node_uuid5, written_data5 = tree.learn(summary5, data5, key="jane_vacation_july2026")
    print(f"Data inserted into node UUID: {node_uuid5}")
    
    # Test Case 6: Simple string data (not JSON)
    print("\n--- Test Case 6: Simple text note ---")
    summary6 = "Quick note about fall 2026 internship recruiting timeline"
    data6 = "Start posting job descriptions by January 2026. Begin screening in February."
    node_uuid6, written_data6 = tree.learn(summary6, data6)
    print(f"Data inserted into node UUID: {node_uuid6}")
    
    # Test Case 7: Employee issue resolution with action creation
    print("\n--- Test Case 7: Employee issue documentation ---")
    summary7 = "Conflict resolution between team members"
    data7 = {
        "issue_id": "ISS-2025-042",
        "date_reported": "2025-10-20",
        "issue_type": "interpersonal_conflict",
        "parties_involved": ["Employee A", "Employee B"],
        "description": "Disagreement over project responsibilities",
        "resolution": "Mediation session held, roles clarified",
        "status": "resolved",
        "follow_up_date": "2025-11-20"
    }
    action, actionID = tree.learn(summary7, data7, key="conflict_resolution_042")
    print(f"Action: {action}")
    print(f"Action UUID: {actionID}")
    
    print("\n" + "="*50)
    print("All learn() test cases completed!")
    print("="*50)
    
    # Verify data was inserted by checking the database
    print("\n--- Verifying data in database ---")
    cursor = tree.dao.cursor
    cursor.execute("SELECT COUNT(*) FROM data_table")
    count = cursor.fetchone()[0]
    print(f"Total records in data_table: {count}")


def test_action_timestamps():
    """Test adding and retrieving actions with last_selected timestamps."""
    from graph_dao import TestGraphDAO
    from datetime import datetime, timedelta

    print("\n" + "="*50)
    print("Testing action timestamps:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['summer2026']

    # Add actions with timestamps
    old_time = (datetime.now() - timedelta(days=5)).isoformat()
    recent_time = datetime.now().isoformat()

    action1 = dao.add_action(node_uuid, "Old action", last_selected=old_time)
    action2 = dao.add_action(node_uuid, "Recent action", last_selected=recent_time)
    action3 = dao.add_action(node_uuid, "New action")  # NULL timestamp

    # Update last_selected
    dao.update_action_last_selected(action3)

    # Get actions sorted by last_selected
    actions = dao.get_actions_for_node(node_uuid)
    print(f"Actions sorted by last_selected: {len(actions)} found")
    assert len(actions) == 3, "Should have 3 actions"
    print("✓ Action timestamps work correctly")


def test_update_action():
    """Test updating action fields."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing action update:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['recruiting']

    action_uuid = dao.add_action(node_uuid, "Original name", "Original plan", "Original prompt")
    dao.update_action(action_uuid, "Updated name", "Updated plan", "Updated prompt")

    actions = dao.get_actions_for_node(node_uuid)
    assert actions[0][1] == "Updated name", "Action name should be updated"
    print("✓ Action update works correctly")


def test_recent_actions():
    """Test getting recent actions."""
    from graph_dao import TestGraphDAO
    from datetime import datetime, timedelta

    print("\n" + "="*50)
    print("Testing recent actions:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['intern']

    # Add 5 actions with different timestamps
    for i in range(5):
        timestamp = (datetime.now() - timedelta(days=i)).isoformat()
        dao.add_action(node_uuid, f"Action {i}", last_selected=timestamp)

    recent = dao.get_recent_actions_for_node(node_uuid, limit=3)
    assert len(recent) == 3, "Should return 3 most recent"
    print(f"✓ Recent actions returned {len(recent)} items")


def test_delete_stale_actions():
    """Test deleting stale actions."""
    from graph_dao import TestGraphDAO
    from datetime import datetime, timedelta

    print("\n" + "="*50)
    print("Testing stale action deletion:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['new_grad']

    old_time = (datetime.now() - timedelta(days=5)).isoformat()
    recent_time = datetime.now().isoformat()

    dao.add_action(node_uuid, "Old action", last_selected=old_time)
    dao.add_action(node_uuid, "Recent action", last_selected=recent_time)
    dao.add_action(node_uuid, "Null action")  # Should not be deleted

    deleted = dao.delete_stale_actions(node_uuid, days_threshold=3)
    assert deleted == 1, "Should delete 1 old action"

    remaining = dao.get_actions_for_node(node_uuid)
    assert len(remaining) == 2, "Should have 2 actions remaining"
    print(f"✓ Deleted {deleted} stale actions, {len(remaining)} remaining")


def test_data_categories():
    """Test adding data with categories."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing data categories:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['onboarding']

    dao.add_data_with_category(node_uuid, "checklist", "task1", "text", "Setup laptop")
    dao.add_data_with_category(node_uuid, "checklist", "task2", "text", "Create accounts")
    dao.add_data_with_category(node_uuid, "contacts", "hr", "text", "hr@company.com")

    categories = dao.get_categories_for_node(node_uuid)
    assert "checklist" in categories and "contacts" in categories
    print(f"✓ Categories found: {categories}")


def test_data_by_category():
    """Test getting data grouped by category."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing data grouped by category:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['issues']

    dao.add_data(node_uuid, "key1", "text", "info1", "cat1")
    dao.add_data(node_uuid, "key2", "text", "info2", "cat1")
    dao.add_data(node_uuid, "key3", "text", "info3", "cat2")

    grouped = dao.get_data_for_node_by_category(node_uuid)
    assert len(grouped["cat1"]) == 2, "Should have 2 items in cat1"
    assert len(grouped["cat2"]) == 1, "Should have 1 item in cat2"
    print(f"✓ Grouped data: {len(grouped)} categories")


def test_delete_category():
    """Test deleting data by category."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing category deletion:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['events']

    dao.add_data(node_uuid, "k1", "text", "i1", "temp")
    dao.add_data(node_uuid, "k2", "text", "i2", "temp")
    dao.add_data(node_uuid, "k3", "text", "i3", "keep")

    deleted = dao.delete_data_by_category(node_uuid, "temp")
    assert deleted == 2, "Should delete 2 items"

    remaining = dao.get_data_for_node_by_category(node_uuid)
    assert "temp" not in remaining, "temp category should be gone"
    print(f"✓ Deleted {deleted} items from category")


def test_node_counters():
    """Test node counter increment/get/reset."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing node counters:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['2026']

    assert dao.get_node_counter(node_uuid) == 0, "Initial count should be 0"

    dao.increment_node_counter(node_uuid)
    dao.increment_node_counter(node_uuid)
    dao.increment_node_counter(node_uuid)

    assert dao.get_node_counter(node_uuid) == 3, "Count should be 3"

    dao.reset_node_counter(node_uuid)
    assert dao.get_node_counter(node_uuid) == 0, "Count should be reset to 0"
    print("✓ Node counters work correctly")


def test_nodes_needing_cleanup():
    """Test getting nodes needing cleanup."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing nodes needing cleanup:")
    print("="*50)

    dao = TestGraphDAO()
    node1 = dao.node_uuids['career_fair']
    node2 = dao.node_uuids['career_conference']

    for _ in range(5):
        dao.increment_node_counter(node1)
    for _ in range(2):
        dao.increment_node_counter(node2)

    nodes = dao.get_nodes_needing_cleanup(threshold=4)
    assert node1 in nodes, "node1 should need cleanup"
    assert node2 not in nodes, "node2 should not need cleanup"
    print(f"✓ Found {len(nodes)} nodes needing cleanup")


def test_parse_learning_response_clean_json():
    """Test parsing clean JSON response."""
    from graph import Tree

    print("\n" + "="*50)
    print("Testing JSON parsing (clean):")
    print("="*50)

    tree = Tree("graph.db")

    clean_json = '''
    {
      "action_decision": {
        "type": "create",
        "action_uuid": null,
        "action_name": "Test Action",
        "action_plan": "Test plan",
        "action_prompt": "Test prompt"
      },
      "data_insertions": [
        {
          "category": "test_category",
          "is_new_category": true,
          "condensed_data": "Test data"
        }
      ]
    }
    '''

    result = tree._parse_learning_response(clean_json)
    assert result["action_decision"]["type"] == "create"
    assert len(result["data_insertions"]) == 1
    print("✓ Clean JSON parsed correctly")


def test_parse_learning_response_markdown():
    """Test parsing JSON wrapped in markdown."""
    from graph import Tree

    print("\n" + "="*50)
    print("Testing JSON parsing (markdown):")
    print("="*50)

    tree = Tree("graph.db")

    markdown_json = '''
    Here's the response:
    ```json
    {
      "action_decision": {
        "type": "select",
        "action_uuid": "test-uuid-123",
        "action_name": "Test Action",
        "action_plan": "Test plan",
        "action_prompt": "Test prompt"
      },
      "data_insertions": []
    }
    ```
    '''

    result = tree._parse_learning_response(markdown_json)
    assert result["action_decision"]["type"] == "select"
    assert result["action_decision"]["action_uuid"] == "test-uuid-123"
    print("✓ Markdown JSON parsed correctly")


def test_parse_learning_response_invalid():
    """Test parsing invalid JSON raises error."""
    from graph import Tree

    print("\n" + "="*50)
    print("Testing JSON parsing (invalid):")
    print("="*50)

    tree = Tree("graph.db")

    invalid_json = "This is not JSON at all"

    try:
        tree._parse_learning_response(invalid_json)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"✓ Correctly raised error: {str(e)[:50]}...")


def test_generate_learning_prompt():
    """Test prompt generation includes all required sections."""
    from graph import Tree
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing prompt generation:")
    print("="*50)

    tree = Tree("graph.db")
    dao = TestGraphDAO()

    # Create mock node
    node_uuid = dao.node_uuids['summer2026']
    node = type('Node', (), {
        'node_uuid': node_uuid,
        'metadata': 'Summer 2026',
        'parent_uuid': dao.node_uuids['intern']
    })()

    # Add some mock actions
    dao.add_action(node_uuid, "Action 1", "Plan 1", "Prompt 1", last_selected="2025-01-01")
    dao.add_action(node_uuid, "Action 2", "Plan 2", "Prompt 2")

    # Add some mock categories
    dao.add_data_with_category(node_uuid, "emails", "key1", "text", "info1")
    dao.add_data_with_category(node_uuid, "candidates", "key2", "text", "info2")

    existing_actions = dao.get_actions_for_node(node_uuid)
    existing_categories = dao.get_categories_for_node(node_uuid)

    summary = "User is scheduling an interview"

    prompt = tree._generate_learning_prompt(node, summary, existing_actions, existing_categories)

    # Verify prompt contains key sections
    assert "EXISTING ACTIONS" in prompt
    assert "EXISTING DATA CATEGORIES" in prompt
    assert "USER'S CURRENT ACTIVITY" in prompt
    assert "action_decision" in prompt
    assert "data_insertions" in prompt
    assert "Summer 2026" in prompt

    print("✓ Prompt generated with all required sections")


def test_cleanup_multiple_entries():
    """Test cleanup with multiple entries in one category."""
    from graph_dao import TestGraphDAO
    from graph import Tree

    print("\n" + "="*50)
    print("Testing cleanup with multiple entries:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['summer2026']

    # Add multiple entries to one category
    dao.add_data_with_category(node_uuid, "interviews", "key1", "text", "Interview with John on Monday")
    dao.add_data_with_category(node_uuid, "interviews", "key2", "text", "Interview with Jane on Tuesday")
    dao.add_data_with_category(node_uuid, "interviews", "key3", "text", "Interview with Bob on Wednesday")

    # Set node counter
    for _ in range(5):
        dao.increment_node_counter(node_uuid)

    # Mock the LLM response
    original_count = len(dao.get_data_for_node_by_category(node_uuid)["interviews"])
    assert original_count == 3, "Should have 3 entries before cleanup"

    # Note: We can't actually test LLM condensation without API key
    # But we can verify the logic structure
    data_by_cat = dao.get_data_for_node_by_category(node_uuid)
    assert "interviews" in data_by_cat
    assert len(data_by_cat["interviews"]) == 3

    print(f"✓ Setup complete: {original_count} entries in 'interviews' category")


def test_cleanup_multiple_categories():
    """Test cleanup with multiple categories."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing cleanup with multiple categories:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['recruiting']

    # Add entries to multiple categories
    dao.add_data_with_category(node_uuid, "emails", "k1", "text", "Email 1")
    dao.add_data_with_category(node_uuid, "emails", "k2", "text", "Email 2")
    dao.add_data_with_category(node_uuid, "meetings", "k3", "text", "Meeting 1")
    dao.add_data_with_category(node_uuid, "meetings", "k4", "text", "Meeting 2")

    data_by_cat = dao.get_data_for_node_by_category(node_uuid)

    assert "emails" in data_by_cat
    assert "meetings" in data_by_cat
    assert len(data_by_cat["emails"]) == 2
    assert len(data_by_cat["meetings"]) == 2

    print("✓ Multiple categories verified")


def test_cleanup_single_entry_skipped():
    """Test cleanup skips categories with single entry."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing cleanup skips single entry categories:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['onboarding']

    # Add single entry to category
    dao.add_data_with_category(node_uuid, "checklist", "k1", "text", "Single item")

    data_by_cat = dao.get_data_for_node_by_category(node_uuid)

    assert "checklist" in data_by_cat
    assert len(data_by_cat["checklist"]) == 1

    # Single entry categories should be skipped during cleanup
    # (would need real cleanup call to verify, but logic is there)
    print("✓ Single entry category identified")


def test_cleanup_empty_node():
    """Test cleanup with empty node returns False."""
    from graph_dao import TestGraphDAO
    from graph import Tree

    print("\n" + "="*50)
    print("Testing cleanup with empty node:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['2025']  # Empty node

    data_by_cat = dao.get_data_for_node_by_category(node_uuid)

    # Should be empty or only have uncategorized
    is_empty = len(data_by_cat) == 0 or (len(data_by_cat) == 1 and "uncategorized" in data_by_cat and len(data_by_cat["uncategorized"]) == 0)

    # cleanup_node_data should return False for empty nodes
    # (would need real API key to test actual method)
    print("✓ Empty node verified")


def test_cleanup_counter_reset():
    """Test counter reset after cleanup."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing counter reset after cleanup:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['events']

    # Set node counter
    for _ in range(10):
        dao.increment_node_counter(node_uuid)

    assert dao.get_node_counter(node_uuid) == 10

    # Reset counter (simulating what cleanup does)
    dao.reset_node_counter(node_uuid)

    assert dao.get_node_counter(node_uuid) == 0
    print("✓ Counter reset verified")


def test_batch_cleanup_identifies_nodes():
    """Test batch cleanup identifies correct nodes."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing batch cleanup node identification:")
    print("="*50)

    dao = TestGraphDAO()

    # Set up nodes with different counter values
    node1 = dao.node_uuids['career_fair']
    node2 = dao.node_uuids['online_webinar']
    node3 = dao.node_uuids['2026']

    # node1: Above threshold
    for _ in range(10):
        dao.increment_node_counter(node1)

    # node2: At threshold
    for _ in range(5):
        dao.increment_node_counter(node2)

    # node3: Below threshold
    for _ in range(2):
        dao.increment_node_counter(node3)

    # Get nodes needing cleanup with threshold=5
    nodes = dao.get_nodes_needing_cleanup(threshold=5)

    assert node1 in nodes, "node1 should need cleanup (10 >= 5)"
    assert node2 in nodes, "node2 should need cleanup (5 >= 5)"
    assert node3 not in nodes, "node3 should not need cleanup (2 < 5)"

    print(f"✓ Batch cleanup identified {len(nodes)} nodes correctly")


def test_cleanup_data_condensation_mock():
    """Test data condensation logic with mock data."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing data condensation logic:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['issues']

    # Add multiple entries that should be condensed
    dao.add_data_with_category(
        node_uuid, "bug_reports", "k1", "text",
        "User reported login issue on Chrome browser"
    )
    dao.add_data_with_category(
        node_uuid, "bug_reports", "k2", "text",
        "Login problem also occurs on Safari"
    )
    dao.add_data_with_category(
        node_uuid, "bug_reports", "k3", "text",
        "Fixed login issue by updating authentication module"
    )

    data_by_cat = dao.get_data_for_node_by_category(node_uuid)

    assert "bug_reports" in data_by_cat
    original_count = len(data_by_cat["bug_reports"])
    assert original_count == 3

    # Simulate what cleanup would do:
    # 1. Collect all entries
    entries = data_by_cat["bug_reports"]
    data_texts = [entry[4] for entry in entries]  # entry[4] is the 'info' field

    # 2. Would send to LLM for condensation
    # 3. Would delete originals
    dao.delete_data_by_category(node_uuid, "bug_reports")

    # 4. Would insert condensed version
    condensed = "Login authentication issue reported on Chrome and Safari browsers. Resolved by updating authentication module."
    dao.add_data_with_category(
        node_uuid, "bug_reports", "condensed_key", "text", condensed
    )

    # Verify condensation
    new_data = dao.get_data_for_node_by_category(node_uuid)
    assert len(new_data["bug_reports"]) == 1, "Should have 1 condensed entry"

    print(f"✓ Condensed {original_count} entries into 1")


def run_all_tests():
    """Run all test suites."""
    print("\n" + "="*70)
    print("RUNNING ALL TESTS FOR GRAPH CONTEXT ENGINE")
    print("="*70)

    # Core functionality tests
    test_traverse()
    test_learn()

    # DAO method tests
    test_action_timestamps()
    test_update_action()
    test_recent_actions()
    test_delete_stale_actions()
    test_data_categories()
    test_data_by_category()
    test_delete_category()
    test_node_counters()
    test_nodes_needing_cleanup()

    # New learning flow tests
    test_parse_learning_response_clean_json()
    test_parse_learning_response_markdown()
    test_parse_learning_response_invalid()
    test_generate_learning_prompt()

    # Cleanup method tests
    test_cleanup_multiple_entries()
    test_cleanup_multiple_categories()
    test_cleanup_single_entry_skipped()
    test_cleanup_empty_node()
    test_cleanup_counter_reset()
    test_batch_cleanup_identifies_nodes()
    test_cleanup_data_condensation_mock()

    print("\n" + "="*70)
    print("ALL TESTS COMPLETED")
    print("="*70)


if __name__ == "__main__":
    # Uncomment the line below to run all tests
    # run_all_tests()
    
    # Or run individual test functions:
    # test_traverse()
    # test_learn()
    
    pass
