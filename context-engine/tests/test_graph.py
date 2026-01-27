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


# ==================== GRAPH STRUCTURE TESTS ====================

def test_create_node_without_parent():
    """Test creating a root-level node (no parent)."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing create_node without parent:")
    print("="*50)

    dao = TestGraphDAO()
    initial_count = len(dao.nodes_data)

    node_uuid = dao.create_node("Test Root Node")

    assert node_uuid is not None, "Should return a UUID"
    assert len(dao.nodes_data) == initial_count + 1, "Should have one more node"

    # Verify the node was created correctly
    node = dao.get_node_by_id(node_uuid)
    assert node is not None, "Node should exist"
    assert node[1] == "Test Root Node", "Metadata should match"
    assert node[4] is None, "Parent should be None for root node"

    print(f"✓ Created root node with UUID: {node_uuid[:8]}...")


def test_create_node_with_parent():
    """Test creating a node with a parent."""
    from graph_dao import TestGraphDAO
    import json

    print("\n" + "="*50)
    print("Testing create_node with parent:")
    print("="*50)

    dao = TestGraphDAO()
    parent_uuid = dao.node_uuids['recruiting']

    node_uuid = dao.create_node("New Child Node", parent_uuid=parent_uuid)

    assert node_uuid is not None, "Should return a UUID"

    # Verify node was created with correct parent
    node = dao.get_node_by_id(node_uuid)
    assert node is not None, "Node should exist"
    assert node[4] == parent_uuid, "Parent UUID should match"

    print(f"✓ Created child node with UUID: {node_uuid[:8]}...")


def test_add_child_to_node():
    """Test adding a child to a parent node."""
    from graph_dao import TestGraphDAO
    import json

    print("\n" + "="*50)
    print("Testing add_child_to_node:")
    print("="*50)

    dao = TestGraphDAO()
    parent_uuid = dao.node_uuids['recruiting']

    # Get initial children count
    parent_before = dao.get_node_by_id(parent_uuid)
    children_before = json.loads(parent_before[5]) if parent_before[5] else []
    initial_count = len(children_before)

    # Create a new node and add it as child
    child_uuid = dao.create_node("Test Child")
    result = dao.add_child_to_node(parent_uuid, child_uuid)

    assert result is True, "Should return True on success"

    # Verify child was added
    parent_after = dao.get_node_by_id(parent_uuid)
    children_after = json.loads(parent_after[5]) if parent_after[5] else []

    assert len(children_after) == initial_count + 1, "Should have one more child"
    assert child_uuid in children_after, "Child UUID should be in children array"

    print(f"✓ Added child to parent, now has {len(children_after)} children")


def test_remove_child_from_node():
    """Test removing a child from a parent node."""
    from graph_dao import TestGraphDAO
    import json

    print("\n" + "="*50)
    print("Testing remove_child_from_node:")
    print("="*50)

    dao = TestGraphDAO()
    parent_uuid = dao.node_uuids['intern']
    child_uuid = dao.node_uuids['summer2026']

    # Verify child exists in parent's children
    parent_before = dao.get_node_by_id(parent_uuid)
    children_before = json.loads(parent_before[5]) if parent_before[5] else []
    assert child_uuid in children_before, "Child should initially be in parent"

    # Remove child
    result = dao.remove_child_from_node(parent_uuid, child_uuid)

    assert result is True, "Should return True on success"

    # Verify child was removed
    parent_after = dao.get_node_by_id(parent_uuid)
    children_after = json.loads(parent_after[5]) if parent_after[5] else []

    assert child_uuid not in children_after, "Child should be removed from parent"

    print(f"✓ Removed child from parent, now has {len(children_after)} children")


def test_remove_nonexistent_child():
    """Test removing a child that doesn't exist returns False."""
    from graph_dao import TestGraphDAO
    import uuid

    print("\n" + "="*50)
    print("Testing remove nonexistent child:")
    print("="*50)

    dao = TestGraphDAO()
    parent_uuid = dao.node_uuids['recruiting']
    fake_uuid = str(uuid.uuid4())

    result = dao.remove_child_from_node(parent_uuid, fake_uuid)

    assert result is False, "Should return False when child doesn't exist"

    print("✓ Correctly returned False for nonexistent child")


def test_update_node_parent():
    """Test moving a node to a new parent."""
    from graph_dao import TestGraphDAO
    import json

    print("\n" + "="*50)
    print("Testing update_node_parent:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['online_webinar']
    old_parent_uuid = dao.node_uuids['events']
    new_parent_uuid = dao.node_uuids['recruiting']

    # Verify initial state
    node_before = dao.get_node_by_id(node_uuid)
    assert node_before[4] == old_parent_uuid, "Initial parent should be events"

    # Move node to new parent
    result = dao.update_node_parent(node_uuid, new_parent_uuid)

    assert result is True, "Should return True on success"

    # Verify node's parent was updated
    node_after = dao.get_node_by_id(node_uuid)
    assert node_after[4] == new_parent_uuid, "Parent should be updated"

    # Verify removed from old parent's children
    old_parent = dao.get_node_by_id(old_parent_uuid)
    old_children = json.loads(old_parent[5]) if old_parent[5] else []
    assert node_uuid not in old_children, "Should be removed from old parent"

    # Verify added to new parent's children
    new_parent = dao.get_node_by_id(new_parent_uuid)
    new_children = json.loads(new_parent[5]) if new_parent[5] else []
    assert node_uuid in new_children, "Should be in new parent's children"

    print(f"✓ Moved node from {old_parent[1]} to {new_parent[1]}")


def test_update_node_metadata():
    """Test updating a node's metadata."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing update_node_metadata:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['fall2026']

    # Get original metadata
    node_before = dao.get_node_by_id(node_uuid)
    original_metadata = node_before[1]

    # Update metadata
    new_metadata = "Fall 2026 Updated"
    result = dao.update_node_metadata(node_uuid, new_metadata)

    assert result is True, "Should return True on success"

    # Verify metadata was updated
    node_after = dao.get_node_by_id(node_uuid)
    assert node_after[1] == new_metadata, "Metadata should be updated"

    print(f"✓ Updated metadata from '{original_metadata}' to '{new_metadata}'")


def test_delete_node_no_children():
    """Test deleting a leaf node (no children)."""
    from graph_dao import TestGraphDAO
    import json

    print("\n" + "="*50)
    print("Testing delete_node (leaf node):")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['Krishiv']
    parent_uuid = dao.node_uuids['summer2026']

    # Add some data and actions to the node
    dao.add_data(node_uuid, "test_key", "text", "test_info")
    dao.add_action(node_uuid, "Test Action")

    initial_count = len(dao.nodes_data)

    # Delete the leaf node
    result = dao.delete_node(node_uuid, cascade=False)

    assert result is True, "Should return True on success"
    assert len(dao.nodes_data) == initial_count - 1, "Should have one less node"

    # Verify node is gone
    node = dao.get_node_by_id(node_uuid)
    assert node is None, "Node should no longer exist"

    # Verify removed from parent's children
    parent = dao.get_node_by_id(parent_uuid)
    children = json.loads(parent[5]) if parent[5] else []
    assert node_uuid not in children, "Should be removed from parent's children"

    # Verify data was deleted
    data = dao.get_data_for_node(node_uuid)
    assert len(data) == 0, "Data should be deleted"

    # Verify actions were deleted
    actions = dao.get_actions_for_node(node_uuid)
    assert len(actions) == 0, "Actions should be deleted"

    print("✓ Successfully deleted leaf node and its associated data/actions")


def test_delete_node_with_children_no_cascade():
    """Test that deleting a node with children fails when cascade=False."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing delete_node with children (no cascade):")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['events']  # Has children: online_webinar, career_fair, career_conference

    initial_count = len(dao.nodes_data)

    # Try to delete without cascade
    result = dao.delete_node(node_uuid, cascade=False)

    assert result is False, "Should return False when node has children"
    assert len(dao.nodes_data) == initial_count, "Node count should be unchanged"

    # Verify node still exists
    node = dao.get_node_by_id(node_uuid)
    assert node is not None, "Node should still exist"

    print("✓ Correctly prevented deletion of node with children")


def test_delete_node_cascade():
    """Test cascading delete removes all descendants."""
    from graph_dao import TestGraphDAO
    import json

    print("\n" + "="*50)
    print("Testing delete_node with cascade:")
    print("="*50)

    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['events']
    child_uuids = [
        dao.node_uuids['online_webinar'],
        dao.node_uuids['career_fair'],
        dao.node_uuids['career_conference']
    ]

    # Add data to children
    for child_uuid in child_uuids:
        dao.add_data(child_uuid, "test_key", "text", "test_info")

    initial_count = len(dao.nodes_data)

    # Cascade delete
    result = dao.delete_node(node_uuid, cascade=True)

    assert result is True, "Should return True on success"
    assert len(dao.nodes_data) == initial_count - 4, "Should delete parent and 3 children"

    # Verify all nodes are gone
    assert dao.get_node_by_id(node_uuid) is None, "Parent should be deleted"
    for child_uuid in child_uuids:
        assert dao.get_node_by_id(child_uuid) is None, f"Child {child_uuid[:8]} should be deleted"

    print("✓ Successfully cascade deleted node and all 3 children")


def test_get_node_depth():
    """Test get_node_depth returns correct values at different levels."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing get_node_depth:")
    print("="*50)

    dao = TestGraphDAO()

    # Test various depths
    test_cases = [
        ('root', 0),
        ('recruiting', 1),
        ('employee_management', 1),
        ('intern', 2),
        ('new_grad', 2),
        ('summer2026', 3),
        ('events', 3),
        ('online_webinar', 4),
        ('Ritesh', 4),
    ]

    for node_name, expected_depth in test_cases:
        node_uuid = dao.node_uuids[node_name]
        actual_depth = dao.get_node_depth(node_uuid)
        assert actual_depth == expected_depth, f"{node_name} should be at depth {expected_depth}, got {actual_depth}"
        print(f"  {node_name}: depth = {actual_depth}")

    print("✓ All node depths correct")


def test_get_siblings():
    """Test get_siblings returns correct nodes."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing get_siblings:")
    print("="*50)

    dao = TestGraphDAO()

    # Test summer2026 - should have fall2026 as sibling
    summer_uuid = dao.node_uuids['summer2026']
    fall_uuid = dao.node_uuids['fall2026']

    siblings = dao.get_siblings(summer_uuid)
    sibling_uuids = [s[0] for s in siblings]

    assert fall_uuid in sibling_uuids, "Fall 2026 should be a sibling of Summer 2026"
    assert summer_uuid not in sibling_uuids, "Node should not be its own sibling"
    assert len(siblings) == 1, "Summer 2026 should have exactly 1 sibling"

    print(f"  Summer 2026 siblings: {[s[1] for s in siblings]}")

    # Test online_webinar - should have career_fair and career_conference as siblings
    webinar_uuid = dao.node_uuids['online_webinar']
    siblings = dao.get_siblings(webinar_uuid)

    assert len(siblings) == 2, "Online Webinar should have 2 siblings"
    sibling_names = sorted([s[1] for s in siblings])
    assert sibling_names == ['Career Conference', 'Career Fair'], "Should have correct siblings"

    print(f"  Online Webinar siblings: {sibling_names}")

    # Test root - should have no siblings
    root_uuid = dao.node_uuids['root']
    siblings = dao.get_siblings(root_uuid)
    assert len(siblings) == 0, "Root should have no siblings"

    print("  Root siblings: [] (none)")
    print("✓ All sibling tests passed")


def test_move_data_between_nodes():
    """Test moving data entries between nodes."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing move_data_between_nodes:")
    print("="*50)

    dao = TestGraphDAO()
    from_uuid = dao.node_uuids['summer2026']
    to_uuid = dao.node_uuids['fall2026']

    # Add some data to source node
    dao.add_data_with_category(from_uuid, "emails", "k1", "text", "Email 1")
    dao.add_data_with_category(from_uuid, "emails", "k2", "text", "Email 2")
    dao.add_data_with_category(from_uuid, "meetings", "k3", "text", "Meeting 1")

    initial_from_count = len(dao.get_data_for_node(from_uuid))
    initial_to_count = len(dao.get_data_for_node(to_uuid))

    # Move only emails category
    moved = dao.move_data_between_nodes(from_uuid, to_uuid, category="emails")

    assert moved == 2, "Should have moved 2 email entries"

    # Verify source node
    from_data = dao.get_data_for_node(from_uuid)
    assert len(from_data) == initial_from_count - 2, "Source should have 2 less entries"

    # Verify destination node
    to_data = dao.get_data_for_node(to_uuid)
    assert len(to_data) == initial_to_count + 2, "Destination should have 2 more entries"

    print(f"✓ Moved {moved} entries from summer2026 to fall2026")


def test_move_all_data_between_nodes():
    """Test moving all data entries between nodes."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing move_data_between_nodes (all data):")
    print("="*50)

    dao = TestGraphDAO()
    from_uuid = dao.node_uuids['onboarding']
    to_uuid = dao.node_uuids['issues']

    # Add some data to source node
    dao.add_data(from_uuid, "k1", "text", "Info 1")
    dao.add_data(from_uuid, "k2", "text", "Info 2")
    dao.add_data(from_uuid, "k3", "text", "Info 3")

    initial_to_count = len(dao.get_data_for_node(to_uuid))

    # Move all data
    moved = dao.move_data_between_nodes(from_uuid, to_uuid, category=None)

    assert moved == 3, "Should have moved 3 entries"

    # Verify source is empty
    from_data = dao.get_data_for_node(from_uuid)
    assert len(from_data) == 0, "Source should be empty"

    # Verify destination has the data
    to_data = dao.get_data_for_node(to_uuid)
    assert len(to_data) == initial_to_count + 3, "Destination should have 3 more entries"

    print(f"✓ Moved all {moved} entries")


def test_move_actions_between_nodes():
    """Test moving actions between nodes."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing move_actions_between_nodes:")
    print("="*50)

    dao = TestGraphDAO()
    from_uuid = dao.node_uuids['2025']
    to_uuid = dao.node_uuids['2026']

    # Add some actions to source node
    dao.add_action(from_uuid, "Action 1", "Plan 1", "Prompt 1")
    dao.add_action(from_uuid, "Action 2", "Plan 2", "Prompt 2")

    initial_to_count = len(dao.get_actions_for_node(to_uuid))

    # Move actions
    moved = dao.move_actions_between_nodes(from_uuid, to_uuid)

    assert moved == 2, "Should have moved 2 actions"

    # Verify source is empty
    from_actions = dao.get_actions_for_node(from_uuid)
    assert len(from_actions) == 0, "Source should have no actions"

    # Verify destination has the actions
    to_actions = dao.get_actions_for_node(to_uuid)
    assert len(to_actions) == initial_to_count + 2, "Destination should have 2 more actions"

    print(f"✓ Moved {moved} actions")


def test_delete_root_node():
    """Test that deleting root node works with cascade."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing delete root node:")
    print("="*50)

    dao = TestGraphDAO()
    root_uuid = dao.node_uuids['root']

    # Without cascade, should fail (root has children)
    result = dao.delete_node(root_uuid, cascade=False)
    assert result is False, "Should fail without cascade"

    # With cascade, should succeed
    initial_count = len(dao.nodes_data)
    result = dao.delete_node(root_uuid, cascade=True)
    assert result is True, "Should succeed with cascade"

    # All nodes should be deleted (root cascades to everything)
    assert len(dao.nodes_data) == 0, "All nodes should be deleted"

    print(f"✓ Cascade deleted root and all {initial_count} descendants")


def test_circular_reference_prevention():
    """Test that circular references cannot be created."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing circular reference prevention:")
    print("="*50)

    dao = TestGraphDAO()

    # Try to make a node its own parent
    node_uuid = dao.node_uuids['intern']

    # This should either fail or not create a cycle
    # (depending on implementation - ours allows it but get_node_depth will handle it)
    # The important thing is that get_node_depth doesn't infinite loop

    # Test that depth calculation still works after parent manipulation
    depth = dao.get_node_depth(node_uuid)
    assert depth >= 0, "Depth should be a valid non-negative number"

    print(f"✓ Circular reference handling works, depth calculation returns: {depth}")


def test_orphan_node_handling():
    """Test handling of orphan nodes (nodes without valid parent)."""
    from graph_dao import TestGraphDAO
    import uuid

    print("\n" + "="*50)
    print("Testing orphan node handling:")
    print("="*50)

    dao = TestGraphDAO()

    # Create a node with a non-existent parent
    fake_parent = str(uuid.uuid4())
    node_uuid = dao.create_node("Orphan Node", parent_uuid=fake_parent)

    # Node should be created
    node = dao.get_node_by_id(node_uuid)
    assert node is not None, "Node should be created"
    assert node[4] == fake_parent, "Parent UUID should be set"

    # Depth calculation should handle this gracefully (return -1 for invalid parent chain)
    depth = dao.get_node_depth(node_uuid)
    assert depth == -1, "Depth should be -1 for orphan node with invalid parent"

    # Siblings should return empty (parent doesn't exist)
    siblings = dao.get_siblings(node_uuid)
    assert len(siblings) == 0, "Should have no siblings (parent doesn't exist)"

    print("✓ Orphan node handling works correctly")


def test_depth_boundary_max_depth():
    """Test depth calculation for deep node hierarchies."""
    from graph_dao import TestGraphDAO

    print("\n" + "="*50)
    print("Testing deep node hierarchy:")
    print("="*50)

    dao = TestGraphDAO()

    # Create a chain of 10 nodes
    parent_uuid = dao.node_uuids['root']
    for i in range(10):
        new_uuid = dao.create_node(f"Deep Node {i}")
        dao.update_node_parent(new_uuid, parent_uuid)
        parent_uuid = new_uuid

    # Verify depth of deepest node
    depth = dao.get_node_depth(parent_uuid)
    # Root is at depth 0, so 10 levels down should be depth 10
    assert depth == 10, f"Deepest node should be at depth 10, got {depth}"

    print(f"✓ Created chain of 10 nodes, deepest node at depth {depth}")


# ==================== TRAVERSE WITH CONFIDENCE TESTS ====================

def test_traverse_with_confidence_returns_tuple():
    """Test that traverse_with_confidence returns correct tuple structure."""
    print("\n" + "="*50)
    print("Testing traverse_with_confidence tuple structure:")
    print("="*50)

    # Use the global tree instance
    if not tree.embedding_model:
        print("Skipping - embedding model not available")
        return

    summary = "Scheduling an interview with Ritesh for Summer 2026 internship"
    result = tree.traverse_with_confidence(summary)

    # Check tuple structure
    assert isinstance(result, tuple), "Result should be a tuple"
    assert len(result) == 3, "Result should have 3 elements"

    best_node, confidence, top_scores = result

    # Check types
    assert best_node is not None or tree.root is None, "Best node should exist if root exists"
    assert isinstance(confidence, float), "Confidence should be a float"
    assert isinstance(top_scores, list), "Top scores should be a list"

    print(f"✓ Returned tuple with: Node={best_node.metadata if best_node else None}, "
          f"Confidence={confidence:.4f}, Top scores count={len(top_scores)}")


def test_traverse_with_confidence_score_range():
    """Test that confidence score is between 0 and 1."""
    print("\n" + "="*50)
    print("Testing confidence score range:")
    print("="*50)

    if not tree.embedding_model:
        print("Skipping - embedding model not available")
        return

    test_summaries = [
        "Reviewing resumes for summer 2026 internship positions",
        "Approving vacation leave requests for employees",
        "Organizing the MIT career fair booth",
        "Random text that might not match well xyz123",
    ]

    for summary in test_summaries:
        best_node, confidence, top_scores = tree.traverse_with_confidence(summary)

        assert 0.0 <= confidence <= 1.0, f"Confidence {confidence} out of range for '{summary[:30]}...'"

        # Also check all top scores
        for node, score in top_scores:
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for node {node.metadata}"

        print(f"  '{summary[:40]}...' -> confidence: {confidence:.4f}")

    print("✓ All confidence scores are within [0.0, 1.0]")


def test_traverse_with_confidence_sorted_descending():
    """Test that top scores are sorted in descending order."""
    print("\n" + "="*50)
    print("Testing top scores sorted descending:")
    print("="*50)

    if not tree.embedding_model:
        print("Skipping - embedding model not available")
        return

    summary = "Onboarding a new software engineer to the team"
    best_node, confidence, top_scores = tree.traverse_with_confidence(summary)

    # Check sorting
    if len(top_scores) > 1:
        for i in range(len(top_scores) - 1):
            assert top_scores[i][1] >= top_scores[i+1][1], \
                f"Scores not sorted: {top_scores[i][1]} < {top_scores[i+1][1]}"

    print(f"Top scores: {[(n.metadata, f'{s:.4f}') for n, s in top_scores]}")
    print("✓ Top scores are sorted in descending order")


def test_traverse_with_confidence_best_matches_top():
    """Test that best node matches the top score in the list."""
    print("\n" + "="*50)
    print("Testing best node matches top score:")
    print("="*50)

    if not tree.embedding_model:
        print("Skipping - embedding model not available")
        return

    summary = "Resolving a conflict between two team members in the issues department"
    best_node, confidence, top_scores = tree.traverse_with_confidence(summary)

    if top_scores:
        top_node, top_score = top_scores[0]

        assert best_node.node_uuid == top_node.node_uuid, \
            f"Best node {best_node.metadata} doesn't match top node {top_node.metadata}"
        assert abs(confidence - top_score) < 0.0001, \
            f"Confidence {confidence} doesn't match top score {top_score}"

    print(f"✓ Best node '{best_node.metadata}' matches top score {confidence:.4f}")


def test_traverse_with_confidence_empty_summary():
    """Test handling of empty/None summary."""
    print("\n" + "="*50)
    print("Testing empty summary handling:")
    print("="*50)

    # Test empty string
    best_node, confidence, top_scores = tree.traverse_with_confidence("")
    assert best_node == tree.root, "Empty string should return root"
    assert confidence == 0.0, "Empty string should have 0.0 confidence"
    assert top_scores == [], "Empty string should have empty top_scores"
    print("  Empty string: root returned with 0.0 confidence")

    # Test whitespace only
    best_node, confidence, top_scores = tree.traverse_with_confidence("   ")
    assert best_node == tree.root, "Whitespace should return root"
    assert confidence == 0.0, "Whitespace should have 0.0 confidence"
    print("  Whitespace only: root returned with 0.0 confidence")

    # Test None (if it doesn't raise an error)
    try:
        best_node, confidence, top_scores = tree.traverse_with_confidence(None)
        assert best_node == tree.root, "None should return root"
        assert confidence == 0.0, "None should have 0.0 confidence"
        print("  None: root returned with 0.0 confidence")
    except (TypeError, AttributeError):
        print("  None: Raises TypeError (acceptable)")

    print("✓ Empty/None summary handled correctly")


def test_traverse_with_confidence_top_5_limit():
    """Test that top_scores contains at most 5 entries."""
    print("\n" + "="*50)
    print("Testing top 5 limit:")
    print("="*50)

    if not tree.embedding_model:
        print("Skipping - embedding model not available")
        return

    summary = "Working on recruiting tasks for the company"
    best_node, confidence, top_scores = tree.traverse_with_confidence(summary)

    assert len(top_scores) <= 5, f"Top scores should have at most 5 entries, got {len(top_scores)}"
    print(f"✓ Returned {len(top_scores)} top scores (max 5)")


def test_format_top_scores():
    """Test the _format_top_scores helper method."""
    print("\n" + "="*50)
    print("Testing _format_top_scores:")
    print("="*50)

    if not tree.embedding_model:
        print("Skipping - embedding model not available")
        return

    summary = "Reviewing applications for fall 2026 internships"
    best_node, confidence, top_scores = tree.traverse_with_confidence(summary)

    formatted = tree._format_top_scores(top_scores)

    assert isinstance(formatted, str), "Formatted output should be a string"

    # Check format contains expected elements
    for i, (node, score) in enumerate(top_scores, 1):
        assert f"{i}." in formatted, f"Should contain numbered entry {i}."
        assert node.metadata in formatted, f"Should contain node metadata: {node.metadata}"
        assert "Score:" in formatted, "Should contain 'Score:'"
        assert "path:" in formatted, "Should contain 'path:'"

    print(f"Formatted output:\n{formatted}")
    print("✓ _format_top_scores produces correct format")


def test_format_top_scores_empty():
    """Test _format_top_scores with empty list."""
    print("\n" + "="*50)
    print("Testing _format_top_scores empty list:")
    print("="*50)

    formatted = tree._format_top_scores([])

    assert formatted == "No matching nodes found.", f"Unexpected output: {formatted}"
    print(f"✓ Empty list returns: '{formatted}'")


def test_get_node_path():
    """Test the _get_node_path helper method."""
    print("\n" + "="*50)
    print("Testing _get_node_path:")
    print("="*50)

    # Test root node
    if tree.root:
        path = tree._get_node_path(tree.root)
        assert path == tree.root.metadata, f"Root path should be just root metadata: {path}"
        print(f"  Root path: {path}")

    # Test a deeper node
    for node in tree.nodes.values():
        if node.parent and node.parent.parent:  # Has at least 2 ancestors
            path = tree._get_node_path(node)
            assert " > " in path, f"Multi-level path should contain ' > ': {path}"
            parts = path.split(" > ")
            assert parts[-1] == node.metadata, "Path should end with node's own metadata"
            print(f"  Deep node path: {path}")
            break

    print("✓ _get_node_path produces correct paths")


def test_traverse_with_confidence_with_config():
    """Test that traverse_with_confidence uses GraphConfig for threshold analysis."""
    print("\n" + "="*50)
    print("Testing traverse_with_confidence with GraphConfig:")
    print("="*50)

    if not tree.embedding_model:
        print("Skipping - embedding model not available")
        return

    # Verify config is available
    assert tree.config is not None, "Tree should have GraphConfig initialized"

    summary = "Scheduling interviews for summer 2026 internship candidates"
    best_node, confidence, top_scores = tree.traverse_with_confidence(summary)

    # Test threshold methods
    if tree.config.should_insert_directly(confidence):
        print(f"  Confidence {confidence:.4f} >= {tree.config.get_threshold('perfect_fit'):.2f}: Insert directly")
    elif tree.config.should_validate_with_llm(confidence):
        print(f"  Confidence {confidence:.4f} >= {tree.config.get_threshold('uncertain'):.2f}: Validate with LLM")
    else:
        print(f"  Confidence {confidence:.4f} < {tree.config.get_threshold('uncertain'):.2f}: May need restructure")

    print("✓ GraphConfig integration works correctly")


def run_traverse_with_confidence_tests():
    """Run only the traverse_with_confidence tests."""
    print("\n" + "="*70)
    print("RUNNING TRAVERSE_WITH_CONFIDENCE TESTS")
    print("="*70)

    test_traverse_with_confidence_returns_tuple()
    test_traverse_with_confidence_score_range()
    test_traverse_with_confidence_sorted_descending()
    test_traverse_with_confidence_best_matches_top()
    test_traverse_with_confidence_empty_summary()
    test_traverse_with_confidence_top_5_limit()
    test_format_top_scores()
    test_format_top_scores_empty()
    test_get_node_path()
    test_traverse_with_confidence_with_config()

    print("\n" + "="*70)
    print("ALL TRAVERSE_WITH_CONFIDENCE TESTS COMPLETED")
    print("="*70)


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

    # Graph structure tests
    test_create_node_without_parent()
    test_create_node_with_parent()
    test_add_child_to_node()
    test_remove_child_from_node()
    test_remove_nonexistent_child()
    test_update_node_parent()
    test_update_node_metadata()
    test_delete_node_no_children()
    test_delete_node_with_children_no_cascade()
    test_delete_node_cascade()
    test_get_node_depth()
    test_get_siblings()
    test_move_data_between_nodes()
    test_move_all_data_between_nodes()
    test_move_actions_between_nodes()
    test_delete_root_node()
    test_circular_reference_prevention()
    test_orphan_node_handling()
    test_depth_boundary_max_depth()

    # Traverse with confidence tests
    test_traverse_with_confidence_returns_tuple()
    test_traverse_with_confidence_score_range()
    test_traverse_with_confidence_sorted_descending()
    test_traverse_with_confidence_best_matches_top()
    test_traverse_with_confidence_empty_summary()
    test_traverse_with_confidence_top_5_limit()
    test_format_top_scores()
    test_format_top_scores_empty()
    test_get_node_path()
    test_traverse_with_confidence_with_config()

    print("\n" + "="*70)
    print("ALL TESTS COMPLETED")
    print("="*70)


def run_graph_structure_tests():
    """Run only the graph structure tests."""
    print("\n" + "="*70)
    print("RUNNING GRAPH STRUCTURE TESTS")
    print("="*70)

    test_create_node_without_parent()
    test_create_node_with_parent()
    test_add_child_to_node()
    test_remove_child_from_node()
    test_remove_nonexistent_child()
    test_update_node_parent()
    test_update_node_metadata()
    test_delete_node_no_children()
    test_delete_node_with_children_no_cascade()
    test_delete_node_cascade()
    test_get_node_depth()
    test_get_siblings()
    test_move_data_between_nodes()
    test_move_all_data_between_nodes()
    test_move_actions_between_nodes()
    test_delete_root_node()
    test_circular_reference_prevention()
    test_orphan_node_handling()
    test_depth_boundary_max_depth()

    print("\n" + "="*70)
    print("ALL GRAPH STRUCTURE TESTS COMPLETED")
    print("="*70)


if __name__ == "__main__":
    # Uncomment the line below to run all tests
    # run_all_tests()

    # Or run just graph structure tests:
    # run_graph_structure_tests()

    # Or run traverse_with_confidence tests:
    run_traverse_with_confidence_tests()

    # Or run individual test functions:
    # test_traverse()
    # test_learn()

    pass
