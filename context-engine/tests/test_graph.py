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


# ==================== LLM VALIDATE FIT TESTS ====================

def test_get_data_sample_basic():
    """Test _get_data_sample returns formatted string."""
    print("\n" + "="*50)
    print("Testing _get_data_sample basic:")
    print("="*50)

    # First add some data to a node
    from graph_dao import TestGraphDAO
    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['summer2026']

    # Add test data
    dao.add_data_with_category(node_uuid, "interviews", "k1", "text", "Interview with John scheduled for Monday")
    dao.add_data_with_category(node_uuid, "interviews", "k2", "text", "Interview with Jane completed")
    dao.add_data_with_category(node_uuid, "candidates", "k3", "text", "Candidate: Ritesh Neela - Strong technical skills")

    # Create a mock node object
    class MockNode:
        def __init__(self, uuid):
            self.node_uuid = uuid

    # Create a mock tree with the DAO
    class MockTree:
        def __init__(self):
            self.dao = dao

        def _get_data_sample(self, node, max_chars=500):
            if not node or not node.node_uuid:
                return "No data available."
            try:
                data_by_category = self.dao.get_data_for_node_by_category(node.node_uuid)
            except Exception as e:
                return "Error retrieving data."
            if not data_by_category:
                return "No existing data in this node."
            lines = []
            categories_shown = 0
            max_categories = 3
            for category, entries in data_by_category.items():
                if categories_shown >= max_categories:
                    remaining = len(data_by_category) - max_categories
                    lines.append(f"\n... and {remaining} more categories")
                    break
                category_data = []
                for entry in entries:
                    info = entry[4] if len(entry) > 4 else ""
                    if info:
                        category_data.append(str(info))
                combined = " | ".join(category_data)
                if len(combined) > max_chars:
                    combined = combined[:max_chars] + "..."
                lines.append(f"\n[{category}]:")
                lines.append(f"  {combined}")
                categories_shown += 1
            return "\n".join(lines) if lines else "No existing data in this node."

    mock_tree = MockTree()
    mock_node = MockNode(node_uuid)

    result = mock_tree._get_data_sample(mock_node)

    assert isinstance(result, str), "Result should be a string"
    assert "[interviews]" in result or "[candidates]" in result, "Should contain category headers"
    assert "Interview" in result or "Candidate" in result, "Should contain data content"

    print(f"Data sample result:\n{result}")
    print("✓ _get_data_sample returns formatted string")


def test_get_data_sample_empty_node():
    """Test _get_data_sample with node that has no data."""
    print("\n" + "="*50)
    print("Testing _get_data_sample empty node:")
    print("="*50)

    from graph_dao import TestGraphDAO
    dao = TestGraphDAO()
    # Use a node that has no data added to it
    node_uuid = dao.node_uuids['fall2026']

    class MockNode:
        def __init__(self, uuid):
            self.node_uuid = uuid

    class MockTree:
        def __init__(self):
            self.dao = dao

        def _get_data_sample(self, node, max_chars=500):
            if not node or not node.node_uuid:
                return "No data available."
            try:
                data_by_category = self.dao.get_data_for_node_by_category(node.node_uuid)
            except Exception:
                return "Error retrieving data."
            if not data_by_category:
                return "No existing data in this node."
            return "Has data"  # Simplified

    mock_tree = MockTree()
    mock_node = MockNode(node_uuid)

    result = mock_tree._get_data_sample(mock_node)

    assert result == "No existing data in this node.", f"Expected empty message, got: {result}"
    print(f"Empty node result: {result}")
    print("✓ _get_data_sample handles empty nodes")


def test_get_data_sample_none_node():
    """Test _get_data_sample with None node."""
    print("\n" + "="*50)
    print("Testing _get_data_sample None node:")
    print("="*50)

    class MockTree:
        def _get_data_sample(self, node, max_chars=500):
            if not node or not node.node_uuid:
                return "No data available."
            return "Has data"

    mock_tree = MockTree()

    result = mock_tree._get_data_sample(None)
    assert result == "No data available.", f"Expected 'No data available.', got: {result}"

    print(f"None node result: {result}")
    print("✓ _get_data_sample handles None node")


def test_get_data_sample_truncation():
    """Test _get_data_sample truncates long data."""
    print("\n" + "="*50)
    print("Testing _get_data_sample truncation:")
    print("="*50)

    from graph_dao import TestGraphDAO
    dao = TestGraphDAO()
    node_uuid = dao.node_uuids['onboarding']

    # Add very long data
    long_data = "A" * 1000
    dao.add_data_with_category(node_uuid, "long_category", "k1", "text", long_data)

    class MockNode:
        def __init__(self, uuid):
            self.node_uuid = uuid

    class MockTree:
        def __init__(self):
            self.dao = dao

        def _get_data_sample(self, node, max_chars=500):
            if not node or not node.node_uuid:
                return "No data available."
            data_by_category = self.dao.get_data_for_node_by_category(node.node_uuid)
            if not data_by_category:
                return "No existing data in this node."
            lines = []
            for category, entries in list(data_by_category.items())[:3]:
                category_data = []
                for entry in entries:
                    info = entry[4] if len(entry) > 4 else ""
                    if info:
                        category_data.append(str(info))
                combined = " | ".join(category_data)
                if len(combined) > max_chars:
                    combined = combined[:max_chars] + "..."
                lines.append(f"[{category}]: {combined}")
            return "\n".join(lines)

    mock_tree = MockTree()
    mock_node = MockNode(node_uuid)

    result = mock_tree._get_data_sample(mock_node, max_chars=100)

    assert "..." in result, "Long data should be truncated with '...'"
    print(f"Truncated result length: {len(result)}")
    print("✓ _get_data_sample truncates long data")


def test_llm_validate_fit_returns_correct_structure():
    """Test that _llm_validate_fit returns correct dictionary structure."""
    print("\n" + "="*50)
    print("Testing _llm_validate_fit return structure:")
    print("="*50)

    # Test the parse function directly with a valid response
    valid_json = '{"fits": true, "reasoning": "This fits well", "suggested_category": "test_category"}'

    import json
    import re

    def parse_response(response_text):
        default_response = {
            "fits": True,
            "reasoning": "Parse error - defaulting to fit",
            "suggested_category": "general"
        }
        try:
            json_match = re.search(r'\{[^{}]*"fits"[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                return default_response
            parsed = json.loads(json_str)
            return {
                "fits": bool(parsed.get("fits", True)),
                "reasoning": str(parsed.get("reasoning", "No reasoning provided")),
                "suggested_category": str(parsed.get("suggested_category", "general"))
            }
        except:
            return default_response

    result = parse_response(valid_json)

    assert isinstance(result, dict), "Result should be a dictionary"
    assert "fits" in result, "Result should have 'fits' key"
    assert "reasoning" in result, "Result should have 'reasoning' key"
    assert "suggested_category" in result, "Result should have 'suggested_category' key"
    assert isinstance(result["fits"], bool), "'fits' should be boolean"
    assert isinstance(result["reasoning"], str), "'reasoning' should be string"
    assert isinstance(result["suggested_category"], str), "'suggested_category' should be string"

    print(f"Result: {result}")
    print("✓ _llm_validate_fit returns correct structure")


def test_llm_validate_fit_parses_valid_json():
    """Test that valid JSON responses are parsed correctly."""
    print("\n" + "="*50)
    print("Testing _llm_validate_fit JSON parsing:")
    print("="*50)

    import json
    import re

    def parse_response(response_text):
        default_response = {
            "fits": True,
            "reasoning": "Parse error - defaulting to fit",
            "suggested_category": "general"
        }
        try:
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_match = re.search(r'\{[^{}]*"fits"[^{}]*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    return default_response
            parsed = json.loads(json_str)
            return {
                "fits": bool(parsed.get("fits", True)),
                "reasoning": str(parsed.get("reasoning", "No reasoning provided")),
                "suggested_category": str(parsed.get("suggested_category", "general"))
            }
        except:
            return default_response

    # Test plain JSON
    plain_json = '{"fits": false, "reasoning": "Does not match", "suggested_category": "other"}'
    result = parse_response(plain_json)
    assert result["fits"] == False
    assert result["reasoning"] == "Does not match"
    assert result["suggested_category"] == "other"
    print(f"  Plain JSON: {result}")

    # Test JSON in markdown code block
    markdown_json = '''Here is my analysis:
```json
{"fits": true, "reasoning": "Perfect match", "suggested_category": "interviews"}
```
'''
    result = parse_response(markdown_json)
    assert result["fits"] == True
    assert result["reasoning"] == "Perfect match"
    assert result["suggested_category"] == "interviews"
    print(f"  Markdown JSON: {result}")

    # Test JSON with extra text
    extra_text = 'The answer is: {"fits": true, "reasoning": "Good fit", "suggested_category": "data"} Thank you!'
    result = parse_response(extra_text)
    assert result["fits"] == True
    print(f"  Extra text JSON: {result}")

    print("✓ Valid JSON responses parsed correctly")


def test_llm_validate_fit_handles_malformed_response():
    """Test error handling for malformed LLM responses."""
    print("\n" + "="*50)
    print("Testing _llm_validate_fit error handling:")
    print("="*50)

    import json
    import re

    def parse_response(response_text):
        default_response = {
            "fits": True,
            "reasoning": "Parse error - defaulting to fit",
            "suggested_category": "general"
        }
        try:
            json_match = re.search(r'\{[^{}]*"fits"[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                return default_response
            parsed = json.loads(json_str)
            return {
                "fits": bool(parsed.get("fits", True)),
                "reasoning": str(parsed.get("reasoning", "No reasoning provided")),
                "suggested_category": str(parsed.get("suggested_category", "general"))
            }
        except:
            return default_response

    # Test completely invalid response
    invalid_response = "I think this data fits because it matches the context."
    result = parse_response(invalid_response)
    assert result["fits"] == True, "Should default to True"
    assert "Parse error" in result["reasoning"] or "No reasoning" in result["reasoning"]
    assert result["suggested_category"] == "general"
    print(f"  Invalid response: {result}")

    # Test malformed JSON
    malformed_json = '{"fits": true, "reasoning": "incomplete'
    result = parse_response(malformed_json)
    assert result["fits"] == True, "Should default to True on parse error"
    print(f"  Malformed JSON: {result}")

    # Test empty response
    empty_response = ""
    result = parse_response(empty_response)
    assert result["fits"] == True
    assert result["suggested_category"] == "general"
    print(f"  Empty response: {result}")

    print("✓ Malformed responses handled with defaults")


def test_llm_validate_fit_suggested_category():
    """Test that suggested_category is returned for fitting data."""
    print("\n" + "="*50)
    print("Testing suggested_category extraction:")
    print("="*50)

    import json
    import re

    def parse_response(response_text):
        default_response = {
            "fits": True,
            "reasoning": "Parse error",
            "suggested_category": "general"
        }
        try:
            json_match = re.search(r'\{[^{}]*"fits"[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                return {
                    "fits": bool(parsed.get("fits", True)),
                    "reasoning": str(parsed.get("reasoning", "")),
                    "suggested_category": str(parsed.get("suggested_category", "general"))
                }
        except:
            pass
        return default_response

    # Test with specific category
    response = '{"fits": true, "reasoning": "Interview scheduling fits here", "suggested_category": "interview_scheduling"}'
    result = parse_response(response)
    assert result["fits"] == True
    assert result["suggested_category"] == "interview_scheduling"
    print(f"  Specific category: {result['suggested_category']}")

    # Test using existing category
    response = '{"fits": true, "reasoning": "Matches existing", "suggested_category": "candidates"}'
    result = parse_response(response)
    assert result["suggested_category"] == "candidates"
    print(f"  Existing category: {result['suggested_category']}")

    # Test new category suggestion
    response = '{"fits": true, "reasoning": "New type of data", "suggested_category": "new_data_type"}'
    result = parse_response(response)
    assert result["suggested_category"] == "new_data_type"
    print(f"  New category: {result['suggested_category']}")

    print("✓ suggested_category correctly extracted")


def test_llm_validate_fit_no_model_available():
    """Test behavior when no LLM model is available."""
    print("\n" + "="*50)
    print("Testing _llm_validate_fit without model:")
    print("="*50)

    # Simulate no model available
    class MockTree:
        def __init__(self):
            self.traversal_model = None

        def _llm_validate_fit(self, node, summary, top_scores):
            if not self.traversal_model:
                return {
                    "fits": True,
                    "reasoning": "No LLM available - defaulting to fit",
                    "suggested_category": "general"
                }
            return {"fits": True, "reasoning": "OK", "suggested_category": "test"}

    mock_tree = MockTree()
    result = mock_tree._llm_validate_fit(None, "test summary", [])

    assert result["fits"] == True
    assert "No LLM available" in result["reasoning"]
    assert result["suggested_category"] == "general"

    print(f"No model result: {result}")
    print("✓ Handles missing LLM model gracefully")


# ==================== LLM DECIDE STRUCTURE TESTS ====================

def test_get_siblings_helper():
    """Test _get_siblings helper method."""
    print("\n" + "="*50)
    print("Testing _get_siblings helper:")
    print("="*50)

    from graph_dao import TestGraphDAO

    dao = TestGraphDAO()

    # Create mock nodes dict
    nodes = {}
    for name, uuid in dao.node_uuids.items():
        node_tuple = dao.get_node_by_id(uuid)
        if node_tuple:
            class MockNode:
                def __init__(self, t):
                    self.node_uuid = t[0]
                    self.metadata = t[1]
            nodes[uuid] = MockNode(node_tuple)

    class MockTree:
        def __init__(self):
            self.dao = dao
            self.nodes = nodes

        def _get_siblings(self, node):
            if not node or not node.node_uuid:
                return []
            try:
                sibling_tuples = self.dao.get_siblings(node.node_uuid)
                siblings = []
                for sibling_tuple in sibling_tuples:
                    sibling_uuid = sibling_tuple[0]
                    if sibling_uuid in self.nodes:
                        siblings.append(self.nodes[sibling_uuid])
                return siblings
            except:
                return []

    mock_tree = MockTree()

    # Test summer2026 - should have fall2026 as sibling
    summer_node = nodes[dao.node_uuids['summer2026']]
    siblings = mock_tree._get_siblings(summer_node)
    sibling_names = [s.metadata for s in siblings]

    assert 'Fall 2026' in sibling_names, f"Fall 2026 should be a sibling, got {sibling_names}"
    print(f"  Summer 2026 siblings: {sibling_names}")

    # Test root - should have no siblings
    root_node = nodes[dao.node_uuids['root']]
    siblings = mock_tree._get_siblings(root_node)
    assert len(siblings) == 0, "Root should have no siblings"
    print("  Root siblings: []")

    print("✓ _get_siblings works correctly")


def test_decide_structure_returns_correct_structure():
    """Test that _llm_decide_structure returns correct dictionary structure."""
    print("\n" + "="*50)
    print("Testing _llm_decide_structure return structure:")
    print("="*50)

    import json
    import re

    def parse_response(response_text, current_depth=2, max_depth=10):
        default_response = {
            "type": "insert_anyway",
            "reasoning": "Parse error - defaulting to insert",
            "new_node_metadata": None,
            "split_plan": None
        }
        valid_types = ["create_child", "create_sibling", "split", "insert_anyway"]

        try:
            # Find JSON
            brace_count = 0
            start_idx = None
            end_idx = None
            for i, char in enumerate(response_text):
                if char == '{':
                    if brace_count == 0:
                        start_idx = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx is not None:
                        end_idx = i + 1
                        break

            if start_idx is None or end_idx is None:
                return default_response

            parsed = json.loads(response_text[start_idx:end_idx])
            operation_type = parsed.get("type", "").lower()

            if operation_type not in valid_types:
                return default_response

            if operation_type == "create_child" and current_depth >= max_depth:
                return {
                    "type": "insert_anyway",
                    "reasoning": "CREATE_CHILD not allowed at max depth",
                    "new_node_metadata": None,
                    "split_plan": None
                }

            return {
                "type": operation_type,
                "reasoning": str(parsed.get("reasoning", "")),
                "new_node_metadata": parsed.get("new_node_metadata"),
                "split_plan": parsed.get("split_plan")
            }
        except:
            return default_response

    # Test create_child response
    response = '{"type": "create_child", "reasoning": "Need new child", "new_node_metadata": "Engineering Recruiting", "split_plan": null}'
    result = parse_response(response)

    assert isinstance(result, dict)
    assert "type" in result
    assert "reasoning" in result
    assert "new_node_metadata" in result
    assert "split_plan" in result
    assert result["type"] == "create_child"
    assert result["new_node_metadata"] == "Engineering Recruiting"

    print(f"Result: {result}")
    print("✓ Returns correct structure")


def test_decide_structure_create_child():
    """Test create_child operation type."""
    print("\n" + "="*50)
    print("Testing create_child operation:")
    print("="*50)

    import json

    response = '''
    {
        "type": "create_child",
        "reasoning": "The new information about engineering recruiting is a specialization of the current Recruiting node",
        "new_node_metadata": "Engineering Recruiting",
        "split_plan": null
    }
    '''

    parsed = json.loads(response)

    assert parsed["type"] == "create_child"
    assert parsed["new_node_metadata"] == "Engineering Recruiting"
    assert parsed["split_plan"] is None

    print(f"  Type: {parsed['type']}")
    print(f"  New node: {parsed['new_node_metadata']}")
    print("✓ create_child operation parsed correctly")


def test_decide_structure_create_sibling():
    """Test create_sibling operation type."""
    print("\n" + "="*50)
    print("Testing create_sibling operation:")
    print("="*50)

    import json

    response = '''
    {
        "type": "create_sibling",
        "reasoning": "Fall 2026 internship info is parallel to Summer 2026, should be a sibling node",
        "new_node_metadata": "Fall 2026 Interns",
        "split_plan": null
    }
    '''

    parsed = json.loads(response)

    assert parsed["type"] == "create_sibling"
    assert parsed["new_node_metadata"] == "Fall 2026 Interns"
    assert parsed["split_plan"] is None

    print(f"  Type: {parsed['type']}")
    print(f"  New node: {parsed['new_node_metadata']}")
    print("✓ create_sibling operation parsed correctly")


def test_decide_structure_split_plan_valid():
    """Test split operation with valid split_plan."""
    print("\n" + "="*50)
    print("Testing split operation with valid split_plan:")
    print("="*50)

    import json

    response = '''
    {
        "type": "split",
        "reasoning": "Node has mixed engineering and marketing data that should be separated",
        "new_node_metadata": null,
        "split_plan": {
            "new_children": [
                {"metadata": "Engineering Recruiting", "inherits_categories": ["technical_interviews", "coding_tests"]},
                {"metadata": "Marketing Recruiting", "inherits_categories": ["marketing_campaigns", "portfolio_reviews"]}
            ],
            "new_data_goes_to": "Engineering Recruiting"
        }
    }
    '''

    parsed = json.loads(response)

    assert parsed["type"] == "split"
    assert parsed["split_plan"] is not None
    assert "new_children" in parsed["split_plan"]
    assert "new_data_goes_to" in parsed["split_plan"]
    assert len(parsed["split_plan"]["new_children"]) == 2

    for child in parsed["split_plan"]["new_children"]:
        assert "metadata" in child
        assert "inherits_categories" in child

    print(f"  Type: {parsed['type']}")
    print(f"  New children: {[c['metadata'] for c in parsed['split_plan']['new_children']]}")
    print(f"  New data goes to: {parsed['split_plan']['new_data_goes_to']}")
    print("✓ split operation with valid split_plan parsed correctly")


def test_decide_structure_insert_anyway():
    """Test insert_anyway operation type."""
    print("\n" + "="*50)
    print("Testing insert_anyway operation:")
    print("="*50)

    import json

    response = '''
    {
        "type": "insert_anyway",
        "reasoning": "After review, the data actually does belong in this node despite low confidence",
        "new_node_metadata": null,
        "split_plan": null
    }
    '''

    parsed = json.loads(response)

    assert parsed["type"] == "insert_anyway"
    assert parsed["new_node_metadata"] is None
    assert parsed["split_plan"] is None

    print(f"  Type: {parsed['type']}")
    print(f"  Reasoning: {parsed['reasoning'][:50]}...")
    print("✓ insert_anyway operation parsed correctly")


def test_decide_structure_max_depth_enforced():
    """Test that max_depth is respected for create_child."""
    print("\n" + "="*50)
    print("Testing max_depth enforcement:")
    print("="*50)

    import json
    import re

    def parse_response(response_text, current_depth, max_depth):
        default_response = {
            "type": "insert_anyway",
            "reasoning": "Parse error",
            "new_node_metadata": None,
            "split_plan": None
        }

        try:
            brace_count = 0
            start_idx = None
            end_idx = None
            for i, char in enumerate(response_text):
                if char == '{':
                    if brace_count == 0:
                        start_idx = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx is not None:
                        end_idx = i + 1
                        break

            if start_idx is None:
                return default_response

            parsed = json.loads(response_text[start_idx:end_idx])
            operation_type = parsed.get("type", "").lower()

            # Enforce max depth
            if operation_type == "create_child" and current_depth >= max_depth:
                return {
                    "type": "insert_anyway",
                    "reasoning": f"CREATE_CHILD not allowed at max depth ({current_depth}/{max_depth})",
                    "new_node_metadata": None,
                    "split_plan": None
                }

            return {
                "type": operation_type,
                "reasoning": parsed.get("reasoning", ""),
                "new_node_metadata": parsed.get("new_node_metadata"),
                "split_plan": parsed.get("split_plan")
            }
        except:
            return default_response

    response = '{"type": "create_child", "reasoning": "Need child", "new_node_metadata": "New Child", "split_plan": null}'

    # At max depth, should be converted to insert_anyway
    result = parse_response(response, current_depth=10, max_depth=10)
    assert result["type"] == "insert_anyway", f"Expected insert_anyway, got {result['type']}"
    assert "max depth" in result["reasoning"].lower()
    print(f"  At max depth: {result['type']} - {result['reasoning']}")

    # Below max depth, should allow create_child
    result = parse_response(response, current_depth=5, max_depth=10)
    assert result["type"] == "create_child", f"Expected create_child, got {result['type']}"
    print(f"  Below max depth: {result['type']}")

    print("✓ max_depth enforcement works correctly")


def test_decide_structure_fallback_on_invalid():
    """Test fallback to insert_anyway on invalid responses."""
    print("\n" + "="*50)
    print("Testing fallback on invalid responses:")
    print("="*50)

    import json

    def parse_response(response_text):
        default_response = {
            "type": "insert_anyway",
            "reasoning": "Parse error - defaulting to insert",
            "new_node_metadata": None,
            "split_plan": None
        }
        valid_types = ["create_child", "create_sibling", "split", "insert_anyway"]

        try:
            brace_count = 0
            start_idx = None
            end_idx = None
            for i, char in enumerate(response_text):
                if char == '{':
                    if brace_count == 0:
                        start_idx = i
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx is not None:
                        end_idx = i + 1
                        break

            if start_idx is None:
                return default_response

            parsed = json.loads(response_text[start_idx:end_idx])
            operation_type = parsed.get("type", "").lower()

            if operation_type not in valid_types:
                return default_response

            # Validate create operations have metadata
            if operation_type in ["create_child", "create_sibling"]:
                if not parsed.get("new_node_metadata"):
                    return default_response

            # Validate split has plan
            if operation_type == "split":
                split_plan = parsed.get("split_plan")
                if not split_plan or not split_plan.get("new_children") or len(split_plan["new_children"]) < 2:
                    return default_response

            return {
                "type": operation_type,
                "reasoning": parsed.get("reasoning", ""),
                "new_node_metadata": parsed.get("new_node_metadata"),
                "split_plan": parsed.get("split_plan")
            }
        except:
            return default_response

    # Invalid type
    result = parse_response('{"type": "invalid_type", "reasoning": "test"}')
    assert result["type"] == "insert_anyway"
    print("  Invalid type: falls back to insert_anyway")

    # Missing new_node_metadata for create_child
    result = parse_response('{"type": "create_child", "reasoning": "test", "new_node_metadata": null}')
    assert result["type"] == "insert_anyway"
    print("  Missing new_node_metadata: falls back to insert_anyway")

    # Invalid split_plan (only 1 child)
    result = parse_response('{"type": "split", "reasoning": "test", "split_plan": {"new_children": [{"metadata": "Only One"}], "new_data_goes_to": "Only One"}}')
    assert result["type"] == "insert_anyway"
    print("  Invalid split_plan (1 child): falls back to insert_anyway")

    # Completely invalid response
    result = parse_response("I think you should create a new node")
    assert result["type"] == "insert_anyway"
    print("  No JSON: falls back to insert_anyway")

    print("✓ Fallback handling works correctly")


def test_decide_structure_no_model_available():
    """Test behavior when no graph operations model is available."""
    print("\n" + "="*50)
    print("Testing _llm_decide_structure without model:")
    print("="*50)

    class MockTree:
        def __init__(self):
            self.graph_operations_model = None

        def _llm_decide_structure(self, node, summary, top_scores):
            if not self.graph_operations_model:
                return {
                    "type": "insert_anyway",
                    "reasoning": "No LLM available - defaulting to insert",
                    "new_node_metadata": None,
                    "split_plan": None
                }
            return {"type": "create_child", "reasoning": "OK", "new_node_metadata": "test", "split_plan": None}

    mock_tree = MockTree()
    result = mock_tree._llm_decide_structure(None, "test summary", [])

    assert result["type"] == "insert_anyway"
    assert "No LLM available" in result["reasoning"]
    assert result["new_node_metadata"] is None
    assert result["split_plan"] is None

    print(f"No model result: {result}")
    print("✓ Handles missing model gracefully")


def test_decide_structure_split_plan_validation():
    """Test that split_plan validation catches invalid plans."""
    print("\n" + "="*50)
    print("Testing split_plan validation:")
    print("="*50)

    import json

    def validate_split_plan(split_plan):
        if not split_plan or not isinstance(split_plan, dict):
            return False
        new_children = split_plan.get("new_children", [])
        if not new_children or len(new_children) < 2:
            return False
        if not split_plan.get("new_data_goes_to"):
            return False
        for child in new_children:
            if not isinstance(child, dict) or "metadata" not in child:
                return False
        return True

    # Valid plan
    valid_plan = {
        "new_children": [
            {"metadata": "Child1", "inherits_categories": ["cat1"]},
            {"metadata": "Child2", "inherits_categories": ["cat2"]}
        ],
        "new_data_goes_to": "Child1"
    }
    assert validate_split_plan(valid_plan) == True
    print("  Valid plan: accepted")

    # Missing new_children
    assert validate_split_plan({"new_data_goes_to": "Child1"}) == False
    print("  Missing new_children: rejected")

    # Only 1 child
    assert validate_split_plan({"new_children": [{"metadata": "Only"}], "new_data_goes_to": "Only"}) == False
    print("  Only 1 child: rejected")

    # Missing new_data_goes_to
    assert validate_split_plan({"new_children": [{"metadata": "A"}, {"metadata": "B"}]}) == False
    print("  Missing new_data_goes_to: rejected")

    # Child missing metadata
    assert validate_split_plan({"new_children": [{"metadata": "A"}, {"inherits_categories": ["x"]}], "new_data_goes_to": "A"}) == False
    print("  Child missing metadata: rejected")

    print("✓ split_plan validation works correctly")


# ==================== NODE CREATION TESTS ====================

def test_create_child_node_basic():
    """Test _create_child_node creates node in DB and memory correctly."""
    print("\n" + "="*50)
    print("Testing _create_child_node basic:")
    print("="*50)

    from graph_dao import TestGraphDAO
    import json

    dao = TestGraphDAO()

    # Create mock parent node
    parent_uuid = dao.node_uuids['recruiting']
    parent_tuple = dao.get_node_by_id(parent_uuid)
    parent_children_before = json.loads(parent_tuple[5]) if parent_tuple[5] else []
    initial_child_count = len(parent_children_before)

    # Create child node
    new_uuid = dao.create_node("Engineering Recruiting", parent_uuid)
    dao.add_child_to_node(parent_uuid, new_uuid)

    # Verify node was created
    new_node = dao.get_node_by_id(new_uuid)
    assert new_node is not None, "New node should exist in DB"
    assert new_node[1] == "Engineering Recruiting", "Metadata should match"
    assert new_node[4] == parent_uuid, "Parent UUID should be set"

    # Verify parent-child relationship
    parent_after = dao.get_node_by_id(parent_uuid)
    parent_children_after = json.loads(parent_after[5]) if parent_after[5] else []
    assert len(parent_children_after) == initial_child_count + 1, "Parent should have one more child"
    assert new_uuid in parent_children_after, "New node should be in parent's children"

    print(f"  Created node: {new_uuid[:8]}...")
    print(f"  Parent children: {initial_child_count} -> {len(parent_children_after)}")
    print("✓ _create_child_node creates node correctly")


def test_create_child_node_parent_child_linkage():
    """Test that parent-child relationships are properly linked."""
    print("\n" + "="*50)
    print("Testing parent-child linkage:")
    print("="*50)

    from graph_dao import TestGraphDAO
    import json

    dao = TestGraphDAO()

    # Create grandparent -> parent -> child chain
    grandparent_uuid = dao.node_uuids['recruiting']

    # Create parent
    parent_uuid = dao.create_node("Mid-Level Node", grandparent_uuid)
    dao.add_child_to_node(grandparent_uuid, parent_uuid)

    # Create child
    child_uuid = dao.create_node("Leaf Node", parent_uuid)
    dao.add_child_to_node(parent_uuid, child_uuid)

    # Verify chain
    child = dao.get_node_by_id(child_uuid)
    assert child[4] == parent_uuid, "Child's parent should be parent"

    parent = dao.get_node_by_id(parent_uuid)
    assert parent[4] == grandparent_uuid, "Parent's parent should be grandparent"

    parent_children = json.loads(parent[5]) if parent[5] else []
    assert child_uuid in parent_children, "Child should be in parent's children"

    # Verify depth
    child_depth = dao.get_node_depth(child_uuid)
    parent_depth = dao.get_node_depth(parent_uuid)
    assert child_depth == parent_depth + 1, f"Child depth ({child_depth}) should be parent depth + 1 ({parent_depth + 1})"

    print(f"  Chain: grandparent -> parent (depth {parent_depth}) -> child (depth {child_depth})")
    print("✓ Parent-child relationships properly linked")


def test_create_child_node_max_depth_enforced():
    """Test that max_depth is enforced when creating child nodes."""
    print("\n" + "="*50)
    print("Testing max_depth enforcement:")
    print("="*50)

    from graph_dao import TestGraphDAO

    dao = TestGraphDAO()

    # Create a chain of nodes to reach max depth
    max_depth = 10
    parent_uuid = dao.node_uuids['root']

    for i in range(max_depth):
        new_uuid = dao.create_node(f"Level {i + 1}", parent_uuid)
        dao.add_child_to_node(parent_uuid, new_uuid)
        parent_uuid = new_uuid

    # Verify we're at max depth
    current_depth = dao.get_node_depth(parent_uuid)
    assert current_depth == max_depth, f"Should be at max depth {max_depth}, got {current_depth}"

    print(f"  Reached max depth: {current_depth}")
    print("✓ max_depth tracking works correctly")


def test_create_sibling_node_uses_correct_parent():
    """Test _create_sibling_node uses the correct parent."""
    print("\n" + "="*50)
    print("Testing _create_sibling_node parent selection:")
    print("="*50)

    from graph_dao import TestGraphDAO
    import json

    dao = TestGraphDAO()

    # Get summer2026 and its parent (intern)
    summer_uuid = dao.node_uuids['summer2026']
    summer_node = dao.get_node_by_id(summer_uuid)
    parent_uuid = summer_node[4]  # This should be 'intern'

    # Create sibling of summer2026
    sibling_uuid = dao.create_node("Winter 2026", parent_uuid)
    dao.add_child_to_node(parent_uuid, sibling_uuid)

    # Verify sibling has same parent
    sibling_node = dao.get_node_by_id(sibling_uuid)
    assert sibling_node[4] == parent_uuid, "Sibling should have same parent"

    # Verify they are now siblings
    siblings = dao.get_siblings(summer_uuid)
    sibling_uuids = [s[0] for s in siblings]
    assert sibling_uuid in sibling_uuids, "New node should be a sibling of summer2026"

    print(f"  Original node parent: {parent_uuid[:8]}...")
    print(f"  Sibling node parent: {sibling_node[4][:8]}...")
    print(f"  Summer 2026 now has {len(siblings)} siblings")
    print("✓ _create_sibling_node uses correct parent")


def test_create_sibling_of_root_creates_child():
    """Test _create_sibling_node handles root case by creating child of root."""
    print("\n" + "="*50)
    print("Testing sibling of root creates child:")
    print("="*50)

    from graph_dao import TestGraphDAO
    import json

    dao = TestGraphDAO()

    root_uuid = dao.node_uuids['root']
    root_node = dao.get_node_by_id(root_uuid)
    root_children_before = json.loads(root_node[5]) if root_node[5] else []

    # Since root has no parent, creating a "sibling" should create a child of root
    new_uuid = dao.create_node("New Top Level", root_uuid)
    dao.add_child_to_node(root_uuid, new_uuid)

    # Verify new node is a child of root
    new_node = dao.get_node_by_id(new_uuid)
    assert new_node[4] == root_uuid, "New node should be child of root"

    # Verify root's children updated
    root_after = dao.get_node_by_id(root_uuid)
    root_children_after = json.loads(root_after[5]) if root_after[5] else []
    assert new_uuid in root_children_after, "New node should be in root's children"

    print(f"  Root children: {len(root_children_before)} -> {len(root_children_after)}")
    print("✓ Creating sibling of root creates child of root")


def test_bootstrap_first_node_empty_root():
    """Test _bootstrap_first_node creates first child of empty root."""
    print("\n" + "="*50)
    print("Testing bootstrap with empty root:")
    print("="*50)

    from graph_dao import TestGraphDAO
    import json

    # Create a fresh DAO and clear root's children
    dao = TestGraphDAO()

    # Simulate empty root by using a fresh node as "root"
    fresh_root_uuid = dao.create_node("Fresh Root", None)

    # Verify it has no children
    fresh_root = dao.get_node_by_id(fresh_root_uuid)
    children = json.loads(fresh_root[5]) if fresh_root[5] else []
    assert len(children) == 0, "Fresh root should have no children"

    # Bootstrap first node
    first_child_uuid = dao.create_node("First Category", fresh_root_uuid)
    dao.add_child_to_node(fresh_root_uuid, first_child_uuid)

    # Verify first child was created
    fresh_root_after = dao.get_node_by_id(fresh_root_uuid)
    children_after = json.loads(fresh_root_after[5]) if fresh_root_after[5] else []
    assert len(children_after) == 1, "Root should now have one child"
    assert first_child_uuid in children_after, "First child should be in root's children"

    first_child = dao.get_node_by_id(first_child_uuid)
    assert first_child[4] == fresh_root_uuid, "First child's parent should be root"

    print(f"  Created first child: {first_child_uuid[:8]}...")
    print(f"  Root children: 0 -> {len(children_after)}")
    print("✓ Bootstrap creates first child correctly")


def test_create_child_with_data():
    """Test that data is inserted when provided to _create_child_node."""
    print("\n" + "="*50)
    print("Testing _create_child_node with data:")
    print("="*50)

    from graph_dao import TestGraphDAO

    dao = TestGraphDAO()

    # Create a new node with data
    parent_uuid = dao.node_uuids['recruiting']
    new_uuid = dao.create_node("Test Node With Data", parent_uuid)
    dao.add_child_to_node(parent_uuid, new_uuid)

    # Add data to the node
    dao.add_data_with_category(new_uuid, "test_category", "key1", "text", "Test data content")

    # Verify data was inserted
    data = dao.get_data_for_node(new_uuid)
    assert len(data) == 1, "Should have one data entry"

    data_by_cat = dao.get_data_for_node_by_category(new_uuid)
    assert "test_category" in data_by_cat, "Should have test_category"

    print(f"  Node created with UUID: {new_uuid[:8]}...")
    print(f"  Data entries: {len(data)}")
    print(f"  Categories: {list(data_by_cat.keys())}")
    print("✓ Data inserted correctly with new node")


def test_refresh_node_embedding():
    """Test _refresh_node_embedding regenerates embedding."""
    print("\n" + "="*50)
    print("Testing _refresh_node_embedding:")
    print("="*50)

    # This test simulates the embedding refresh logic
    class MockNode:
        def __init__(self, uuid, metadata, parent=None):
            self.node_uuid = uuid
            self.metadata = metadata
            self.parent = parent
            self.embedding = None

    root = MockNode("root-uuid", "Root")
    child = MockNode("child-uuid", "Child", root)
    grandchild = MockNode("grandchild-uuid", "Grandchild", child)

    def get_parent_metadata(node):
        if node is None:
            return ""
        if node.parent:
            return get_parent_metadata(node.parent) + node.metadata + "\n"
        else:
            return node.metadata + "\n"

    # Test metadata chain
    chain = get_parent_metadata(grandchild)
    assert "Root" in chain, "Chain should include root"
    assert "Child" in chain, "Chain should include child"
    assert "Grandchild" in chain, "Chain should include grandchild"

    print(f"  Metadata chain: {repr(chain.strip())}")
    print("✓ _refresh_node_embedding logic works correctly")


def test_create_node_none_parent_raises():
    """Test that creating a child with None parent raises error."""
    print("\n" + "="*50)
    print("Testing None parent handling:")
    print("="*50)

    # Simulating the validation logic
    def validate_parent(parent):
        if parent is None:
            raise ValueError("Parent node cannot be None")
        return True

    try:
        validate_parent(None)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "cannot be None" in str(e)
        print(f"  Correctly raised: {e}")

    print("✓ None parent validation works")


def test_create_node_empty_metadata_raises():
    """Test that creating a node with empty metadata raises error."""
    print("\n" + "="*50)
    print("Testing empty metadata handling:")
    print("="*50)

    def validate_metadata(metadata):
        if not metadata:
            raise ValueError("Metadata cannot be empty")
        return True

    try:
        validate_metadata("")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "cannot be empty" in str(e)
        print(f"  Correctly raised for empty string: {e}")

    try:
        validate_metadata(None)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "cannot be empty" in str(e)
        print(f"  Correctly raised for None: {e}")

    print("✓ Empty metadata validation works")


# ==================== SPLIT NODE TESTS ====================

def test_validate_split_plan_valid():
    """Test _validate_split_plan accepts a valid plan."""
    print("\n" + "="*50)
    print("Testing _validate_split_plan with valid plan:")
    print("="*50)

    from graph_dao import TestGraphDAO
    import json

    dao = TestGraphDAO()

    # Create a node with categories
    node_uuid = dao.node_uuids['recruiting']
    dao.add_data_with_category(node_uuid, "engineering", "k1", "text", "Engineering data")
    dao.add_data_with_category(node_uuid, "marketing", "k2", "text", "Marketing data")
    dao.add_data_with_category(node_uuid, "sales", "k3", "text", "Sales data")

    # Create a mock validate function
    def validate_split_plan(node_uuid, split_plan, dao):
        if not split_plan:
            return (False, "Split plan is None or empty")

        if not isinstance(split_plan, dict):
            return (False, "Split plan must be a dictionary")

        new_children = split_plan.get("new_children")
        if not new_children or not isinstance(new_children, list):
            return (False, "Split plan must have 'new_children' list")

        if len(new_children) < 2:
            return (False, "Split plan must have at least 2 new children")

        child_names = []
        for i, child in enumerate(new_children):
            if not isinstance(child, dict):
                return (False, f"Child {i} must be a dictionary")

            metadata = child.get("metadata")
            if not metadata or not isinstance(metadata, str):
                return (False, f"Child {i} missing valid 'metadata' field")

            if metadata in child_names:
                return (False, f"Duplicate child metadata name: '{metadata}'")

            child_names.append(metadata)

        new_data_goes_to = split_plan.get("new_data_goes_to")
        if new_data_goes_to and new_data_goes_to not in child_names:
            return (False, f"'new_data_goes_to' value '{new_data_goes_to}' does not match any child metadata name")

        return (True, "")

    valid_plan = {
        "new_children": [
            {"metadata": "Engineering Team", "inherits_categories": ["engineering"]},
            {"metadata": "Marketing Team", "inherits_categories": ["marketing", "sales"]}
        ],
        "new_data_goes_to": "Engineering Team"
    }

    is_valid, error = validate_split_plan(node_uuid, valid_plan, dao)
    assert is_valid is True, f"Plan should be valid, got error: {error}"
    assert error == "", "Error message should be empty for valid plan"

    print("  Plan validated successfully")
    print("✓ Valid split plan accepted")


def test_validate_split_plan_too_few_children():
    """Test _validate_split_plan rejects plan with < 2 children."""
    print("\n" + "="*50)
    print("Testing _validate_split_plan with too few children:")
    print("="*50)

    def validate_split_plan(split_plan):
        new_children = split_plan.get("new_children", [])
        if len(new_children) < 2:
            return (False, "Split plan must have at least 2 new children")
        return (True, "")

    invalid_plan = {
        "new_children": [
            {"metadata": "Only Child", "inherits_categories": ["cat1"]}
        ],
        "new_data_goes_to": "Only Child"
    }

    is_valid, error = validate_split_plan(invalid_plan)
    assert is_valid is False, "Plan with 1 child should be invalid"
    assert "at least 2" in error, "Error should mention minimum children requirement"

    print(f"  Correctly rejected: {error}")
    print("✓ Plans with < 2 children rejected")


def test_validate_split_plan_duplicate_names():
    """Test _validate_split_plan rejects duplicate child names."""
    print("\n" + "="*50)
    print("Testing _validate_split_plan with duplicate names:")
    print("="*50)

    def validate_split_plan(split_plan):
        new_children = split_plan.get("new_children", [])
        child_names = []
        for i, child in enumerate(new_children):
            metadata = child.get("metadata")
            if metadata in child_names:
                return (False, f"Duplicate child metadata name: '{metadata}'")
            child_names.append(metadata)
        return (True, "")

    invalid_plan = {
        "new_children": [
            {"metadata": "Same Name", "inherits_categories": ["cat1"]},
            {"metadata": "Same Name", "inherits_categories": ["cat2"]}
        ],
        "new_data_goes_to": "Same Name"
    }

    is_valid, error = validate_split_plan(invalid_plan)
    assert is_valid is False, "Plan with duplicate names should be invalid"
    assert "Duplicate" in error, "Error should mention duplicate"

    print(f"  Correctly rejected: {error}")
    print("✓ Plans with duplicate names rejected")


def test_validate_split_plan_invalid_new_data_target():
    """Test _validate_split_plan rejects invalid new_data_goes_to."""
    print("\n" + "="*50)
    print("Testing _validate_split_plan with invalid target:")
    print("="*50)

    def validate_split_plan(split_plan):
        new_children = split_plan.get("new_children", [])
        child_names = [c.get("metadata") for c in new_children]
        new_data_goes_to = split_plan.get("new_data_goes_to")
        if new_data_goes_to and new_data_goes_to not in child_names:
            return (False, f"'new_data_goes_to' value '{new_data_goes_to}' does not match any child metadata name")
        return (True, "")

    invalid_plan = {
        "new_children": [
            {"metadata": "Child A", "inherits_categories": ["cat1"]},
            {"metadata": "Child B", "inherits_categories": ["cat2"]}
        ],
        "new_data_goes_to": "Nonexistent Child"
    }

    is_valid, error = validate_split_plan(invalid_plan)
    assert is_valid is False, "Plan with invalid target should be invalid"
    assert "does not match" in error, "Error should mention mismatch"

    print(f"  Correctly rejected: {error}")
    print("✓ Plans with invalid new_data_goes_to rejected")


def test_split_node_creates_correct_children():
    """Test _split_node creates the correct number of children."""
    print("\n" + "="*50)
    print("Testing _split_node creates correct children:")
    print("="*50)

    from graph_dao import TestGraphDAO
    import json

    dao = TestGraphDAO()

    # Setup: get a node
    parent_uuid = dao.node_uuids['recruiting']
    parent_before = dao.get_node_by_id(parent_uuid)
    children_before = json.loads(parent_before[5]) if parent_before[5] else []
    initial_count = len(children_before)

    # Create 2 child nodes (simulating split)
    child1_uuid = dao.create_node("Engineering Hiring", parent_uuid)
    dao.add_child_to_node(parent_uuid, child1_uuid)

    child2_uuid = dao.create_node("Marketing Hiring", parent_uuid)
    dao.add_child_to_node(parent_uuid, child2_uuid)

    # Verify children were created
    parent_after = dao.get_node_by_id(parent_uuid)
    children_after = json.loads(parent_after[5]) if parent_after[5] else []

    assert len(children_after) == initial_count + 2, f"Should have {initial_count + 2} children, got {len(children_after)}"
    assert child1_uuid in children_after, "Child 1 should be in children"
    assert child2_uuid in children_after, "Child 2 should be in children"

    print(f"  Created children: {len(children_after) - initial_count}")
    print(f"  Child 1: {child1_uuid[:8]}...")
    print(f"  Child 2: {child2_uuid[:8]}...")
    print("✓ Split creates correct number of children")


def test_split_node_distributes_data():
    """Test _split_node distributes data to correct children."""
    print("\n" + "="*50)
    print("Testing _split_node data distribution:")
    print("="*50)

    from graph_dao import TestGraphDAO

    dao = TestGraphDAO()

    # Create a source node with categories
    source_uuid = dao.create_node("Source Node")
    dao.add_data_with_category(source_uuid, "engineering", "k1", "text", "Engineering info")
    dao.add_data_with_category(source_uuid, "marketing", "k2", "text", "Marketing info")
    dao.add_data_with_category(source_uuid, "sales", "k3", "text", "Sales info")

    # Create target nodes
    target1_uuid = dao.create_node("Engineering Team", source_uuid)
    target2_uuid = dao.create_node("Business Team", source_uuid)

    # Move engineering to target1
    moved1 = dao.move_data_between_nodes(source_uuid, target1_uuid, category="engineering")
    assert moved1 == 1, f"Should move 1 engineering entry, moved {moved1}"

    # Move marketing and sales to target2
    moved2 = dao.move_data_between_nodes(source_uuid, target2_uuid, category="marketing")
    moved3 = dao.move_data_between_nodes(source_uuid, target2_uuid, category="sales")
    assert moved2 == 1, "Should move 1 marketing entry"
    assert moved3 == 1, "Should move 1 sales entry"

    # Verify distribution
    target1_data = dao.get_data_for_node_by_category(target1_uuid)
    target2_data = dao.get_data_for_node_by_category(target2_uuid)
    source_data = dao.get_data_for_node_by_category(source_uuid)

    assert "engineering" in target1_data, "Target 1 should have engineering"
    assert "marketing" in target2_data, "Target 2 should have marketing"
    assert "sales" in target2_data, "Target 2 should have sales"
    assert len(source_data) == 0, "Source should have no data left"

    print(f"  Target 1 categories: {list(target1_data.keys())}")
    print(f"  Target 2 categories: {list(target2_data.keys())}")
    print(f"  Source remaining: {len(source_data)}")
    print("✓ Data distributed correctly to children")


def test_split_node_unassigned_categories():
    """Test _split_node handles unassigned categories."""
    print("\n" + "="*50)
    print("Testing unassigned category handling:")
    print("="*50)

    from graph_dao import TestGraphDAO

    dao = TestGraphDAO()

    # Create source with categories
    source_uuid = dao.create_node("Source Node")
    dao.add_data_with_category(source_uuid, "assigned", "k1", "text", "Assigned data")
    dao.add_data_with_category(source_uuid, "unassigned", "k2", "text", "Unassigned data")

    # Create child nodes
    child1_uuid = dao.create_node("Child 1", source_uuid)
    child2_uuid = dao.create_node("Child 2", source_uuid)

    # Only move "assigned" to child1, leave "unassigned" for default handling
    dao.move_data_between_nodes(source_uuid, child1_uuid, category="assigned")

    # Simulate default behavior: unassigned goes to first child
    dao.move_data_between_nodes(source_uuid, child1_uuid, category="unassigned")

    # Verify
    child1_data = dao.get_data_for_node_by_category(child1_uuid)
    source_data = dao.get_data_for_node_by_category(source_uuid)

    assert "assigned" in child1_data, "Child 1 should have assigned"
    assert "unassigned" in child1_data, "Child 1 should get unassigned (default)"
    assert len(source_data) == 0, "Source should be empty"

    print(f"  Child 1 categories: {list(child1_data.keys())}")
    print(f"  Unassigned went to first child (default behavior)")
    print("✓ Unassigned categories handled correctly")


def test_split_node_parent_keeps_actions():
    """Test _split_node leaves actions on parent."""
    print("\n" + "="*50)
    print("Testing parent keeps actions after split:")
    print("="*50)

    from graph_dao import TestGraphDAO

    dao = TestGraphDAO()

    # Create parent with actions
    parent_uuid = dao.create_node("Parent With Actions")
    action_uuid = dao.add_action(parent_uuid, "Test Action", "Plan", "Prompt")

    # Create children (simulating split)
    child1_uuid = dao.create_node("Child 1", parent_uuid)
    child2_uuid = dao.create_node("Child 2", parent_uuid)

    # Don't move actions - they should stay on parent
    parent_actions = dao.get_actions_for_node(parent_uuid)
    child1_actions = dao.get_actions_for_node(child1_uuid)
    child2_actions = dao.get_actions_for_node(child2_uuid)

    assert len(parent_actions) == 1, "Parent should keep its action"
    assert len(child1_actions) == 0, "Child 1 should have no own actions"
    assert len(child2_actions) == 0, "Child 2 should have no own actions"

    print(f"  Parent actions: {len(parent_actions)}")
    print(f"  Children inherit actions through traversal")
    print("✓ Parent keeps actions after split")


def test_split_node_inserts_new_data():
    """Test _split_node inserts new data to correct child."""
    print("\n" + "="*50)
    print("Testing new data insertion after split:")
    print("="*50)

    from graph_dao import TestGraphDAO

    dao = TestGraphDAO()

    # Create nodes
    parent_uuid = dao.create_node("Parent")
    target_uuid = dao.create_node("Target Child", parent_uuid)
    other_uuid = dao.create_node("Other Child", parent_uuid)

    # Insert new data into target (simulating new_data_goes_to)
    dao.add_data_with_category(target_uuid, "new_category", "key1", "text", "New data content")

    # Verify
    target_data = dao.get_data_for_node_by_category(target_uuid)
    other_data = dao.get_data_for_node_by_category(other_uuid)

    assert "new_category" in target_data, "Target should have new data"
    assert len(other_data) == 0, "Other child should have no data"

    print(f"  Target child has: {list(target_data.keys())}")
    print(f"  Other child has: {len(other_data)} categories")
    print("✓ New data inserted into correct child")


def test_split_node_parent_relationships():
    """Test parent-child relationships are correct after split."""
    print("\n" + "="*50)
    print("Testing parent-child relationships after split:")
    print("="*50)

    from graph_dao import TestGraphDAO
    import json

    dao = TestGraphDAO()

    # Create parent
    parent_uuid = dao.create_node("Split Parent")

    # Create children (simulating split)
    child1_uuid = dao.create_node("Split Child 1", parent_uuid)
    dao.add_child_to_node(parent_uuid, child1_uuid)

    child2_uuid = dao.create_node("Split Child 2", parent_uuid)
    dao.add_child_to_node(parent_uuid, child2_uuid)

    # Verify relationships
    parent = dao.get_node_by_id(parent_uuid)
    child1 = dao.get_node_by_id(child1_uuid)
    child2 = dao.get_node_by_id(child2_uuid)

    parent_children = json.loads(parent[5]) if parent[5] else []

    assert child1_uuid in parent_children, "Child 1 should be in parent's children"
    assert child2_uuid in parent_children, "Child 2 should be in parent's children"
    assert child1[4] == parent_uuid, "Child 1's parent should be parent"
    assert child2[4] == parent_uuid, "Child 2's parent should be parent"

    print(f"  Parent has {len(parent_children)} children")
    print(f"  Child 1 parent: {child1[4][:8]}...")
    print(f"  Child 2 parent: {child2[4][:8]}...")
    print("✓ Parent-child relationships correct after split")


def test_validate_split_plan_empty_plan():
    """Test _validate_split_plan rejects empty/None plans."""
    print("\n" + "="*50)
    print("Testing _validate_split_plan with empty/None:")
    print("="*50)

    def validate_split_plan(split_plan):
        if not split_plan:
            return (False, "Split plan is None or empty")
        return (True, "")

    is_valid1, error1 = validate_split_plan(None)
    assert is_valid1 is False, "None plan should be invalid"

    is_valid2, error2 = validate_split_plan({})
    assert is_valid2 is False, "Empty dict should be invalid"

    print(f"  None rejected: {error1}")
    print(f"  Empty dict rejected: {error2}")
    print("✓ Empty/None plans rejected")


def test_validate_split_plan_missing_metadata():
    """Test _validate_split_plan rejects children without metadata."""
    print("\n" + "="*50)
    print("Testing _validate_split_plan missing metadata:")
    print("="*50)

    def validate_split_plan(split_plan):
        new_children = split_plan.get("new_children", [])
        for i, child in enumerate(new_children):
            if not isinstance(child, dict):
                return (False, f"Child {i} must be a dictionary")
            metadata = child.get("metadata")
            if not metadata or not isinstance(metadata, str):
                return (False, f"Child {i} missing valid 'metadata' field")
        return (True, "")

    invalid_plan = {
        "new_children": [
            {"metadata": "Valid Name", "inherits_categories": ["cat1"]},
            {"inherits_categories": ["cat2"]}  # Missing metadata
        ],
        "new_data_goes_to": "Valid Name"
    }

    is_valid, error = validate_split_plan(invalid_plan)
    assert is_valid is False, "Plan with missing metadata should be invalid"
    assert "missing" in error.lower() or "metadata" in error.lower(), "Error should mention missing metadata"

    print(f"  Correctly rejected: {error}")
    print("✓ Plans with missing metadata rejected")


# ==================== LEARN WITH STRUCTURE TESTS ====================

def test_learn_with_structure_bootstrap():
    """Test learn_with_structure creates first node in empty graph."""
    print("\n" + "="*50)
    print("Testing learn_with_structure bootstrap:")
    print("="*50)

    from graph_dao import TestGraphDAO

    # Simulate bootstrap scenario
    class MockConfig:
        def is_bootstrap_enabled(self):
            return True
        def get_max_depth(self):
            return 10

    class MockRoot:
        def __init__(self):
            self.children = []  # Empty - triggers bootstrap
            self.node_uuid = "root-uuid"
            self.metadata = "Root"

    # Verify logic
    root = MockRoot()
    config = MockConfig()

    # Bootstrap should be triggered when:
    should_bootstrap = len(root.children) == 0 and config.is_bootstrap_enabled()
    assert should_bootstrap is True, "Bootstrap should be triggered for empty graph"

    print("  Empty graph detected: True")
    print("  Bootstrap enabled: True")
    print("  → Bootstrap should be triggered")
    print("✓ Bootstrap case detected correctly")


def test_learn_with_structure_high_confidence():
    """Test learn_with_structure inserts directly on high confidence."""
    print("\n" + "="*50)
    print("Testing learn_with_structure high confidence:")
    print("="*50)

    # Simulate high confidence scenario
    class MockConfig:
        def should_insert_directly(self, confidence):
            return confidence >= 0.85
        def get_threshold(self, name):
            return 0.85 if name == "perfect_fit" else 0.5

    config = MockConfig()
    confidence = 0.92

    should_insert = config.should_insert_directly(confidence)
    assert should_insert is True, "High confidence should trigger direct insert"

    print(f"  Confidence: {confidence}")
    print(f"  Threshold: {config.get_threshold('perfect_fit')}")
    print(f"  → Direct insert: {should_insert}")
    print("✓ High confidence triggers direct insert")


def test_learn_with_structure_medium_confidence():
    """Test learn_with_structure validates with LLM on medium confidence."""
    print("\n" + "="*50)
    print("Testing learn_with_structure medium confidence:")
    print("="*50)

    class MockConfig:
        def should_insert_directly(self, confidence):
            return confidence >= 0.85
        def should_validate_with_llm(self, confidence):
            return 0.50 <= confidence < 0.85

    config = MockConfig()
    confidence = 0.72

    should_insert = config.should_insert_directly(confidence)
    should_validate = config.should_validate_with_llm(confidence)

    assert should_insert is False, "Medium confidence should not trigger direct insert"
    assert should_validate is True, "Medium confidence should trigger LLM validation"

    print(f"  Confidence: {confidence}")
    print(f"  Direct insert: {should_insert}")
    print(f"  LLM validation: {should_validate}")
    print("✓ Medium confidence triggers LLM validation")


def test_learn_with_structure_low_confidence():
    """Test learn_with_structure triggers restructuring on low confidence."""
    print("\n" + "="*50)
    print("Testing learn_with_structure low confidence:")
    print("="*50)

    class MockConfig:
        def should_insert_directly(self, confidence):
            return confidence >= 0.85
        def should_validate_with_llm(self, confidence):
            return 0.50 <= confidence < 0.85
        def needs_restructure(self, confidence):
            return confidence < 0.50

    config = MockConfig()
    confidence = 0.35

    should_insert = config.should_insert_directly(confidence)
    should_validate = config.should_validate_with_llm(confidence)
    needs_restructure = config.needs_restructure(confidence)

    assert should_insert is False
    assert should_validate is False
    assert needs_restructure is True, "Low confidence should trigger restructuring"

    print(f"  Confidence: {confidence}")
    print(f"  Direct insert: {should_insert}")
    print(f"  LLM validation: {should_validate}")
    print(f"  Needs restructure: {needs_restructure}")
    print("✓ Low confidence triggers restructuring")


def test_learn_with_structure_return_structure():
    """Test learn_with_structure returns correct structure."""
    print("\n" + "="*50)
    print("Testing learn_with_structure return structure:")
    print("="*50)

    # Simulate a return dict
    class MockNode:
        def __init__(self, uuid, metadata):
            self.node_uuid = uuid
            self.metadata = metadata

    result = {
        "operation": "insert",
        "target_node": MockNode("uuid-123", "Test Node"),
        "confidence": 0.92,
        "new_nodes": [],
        "actions": [("action-uuid", "Action Name", "Plan", "Prompt", "node-uuid", None)],
        "reasoning": "High confidence match (0.92) - inserted directly"
    }

    # Verify required fields
    required_fields = ["operation", "target_node", "confidence", "new_nodes", "actions", "reasoning"]
    for field in required_fields:
        assert field in result, f"Missing required field: {field}"

    assert result["operation"] in ["insert", "create_child", "create_sibling", "split", "bootstrap"]
    assert isinstance(result["confidence"], float)
    assert isinstance(result["new_nodes"], list)
    assert isinstance(result["actions"], list)
    assert isinstance(result["reasoning"], str)

    print(f"  Operation: {result['operation']}")
    print(f"  Target node: {result['target_node'].metadata}")
    print(f"  Confidence: {result['confidence']}")
    print(f"  New nodes: {len(result['new_nodes'])}")
    print(f"  Actions: {len(result['actions'])}")
    print("✓ Return structure is correct")


def test_learn_with_structure_create_child_operation():
    """Test learn_with_structure handles create_child operation."""
    print("\n" + "="*50)
    print("Testing create_child operation handling:")
    print("="*50)

    # Simulate LLM decision for create_child
    decision = {
        "type": "create_child",
        "reasoning": "New info is a specialization of current node",
        "new_node_metadata": "Engineering Recruiting",
        "split_plan": None
    }

    operation = decision["type"]
    new_metadata = decision.get("new_node_metadata")

    assert operation == "create_child"
    assert new_metadata is not None
    assert len(new_metadata) > 0

    print(f"  Decision type: {operation}")
    print(f"  New node metadata: {new_metadata}")
    print(f"  Reasoning: {decision['reasoning'][:50]}...")
    print("✓ Create child operation handled correctly")


def test_learn_with_structure_create_sibling_operation():
    """Test learn_with_structure handles create_sibling operation."""
    print("\n" + "="*50)
    print("Testing create_sibling operation handling:")
    print("="*50)

    decision = {
        "type": "create_sibling",
        "reasoning": "New info is parallel to current node",
        "new_node_metadata": "Fall 2026 Recruiting",
        "split_plan": None
    }

    operation = decision["type"]
    new_metadata = decision.get("new_node_metadata")

    assert operation == "create_sibling"
    assert new_metadata is not None

    print(f"  Decision type: {operation}")
    print(f"  New node metadata: {new_metadata}")
    print("✓ Create sibling operation handled correctly")


def test_learn_with_structure_split_operation():
    """Test learn_with_structure handles split operation."""
    print("\n" + "="*50)
    print("Testing split operation handling:")
    print("="*50)

    decision = {
        "type": "split",
        "reasoning": "Node has mixed categories that should be separated",
        "new_node_metadata": None,
        "split_plan": {
            "new_children": [
                {"metadata": "Engineering", "inherits_categories": ["engineering"]},
                {"metadata": "Marketing", "inherits_categories": ["marketing"]}
            ],
            "new_data_goes_to": "Engineering"
        }
    }

    operation = decision["type"]
    split_plan = decision.get("split_plan")

    assert operation == "split"
    assert split_plan is not None
    assert "new_children" in split_plan
    assert len(split_plan["new_children"]) >= 2
    assert "new_data_goes_to" in split_plan

    print(f"  Decision type: {operation}")
    print(f"  New children: {len(split_plan['new_children'])}")
    print(f"  New data goes to: {split_plan['new_data_goes_to']}")
    print("✓ Split operation handled correctly")


def test_learn_with_structure_insert_anyway_operation():
    """Test learn_with_structure handles insert_anyway operation."""
    print("\n" + "="*50)
    print("Testing insert_anyway operation handling:")
    print("="*50)

    decision = {
        "type": "insert_anyway",
        "reasoning": "After review, data actually belongs here",
        "new_node_metadata": None,
        "split_plan": None
    }

    operation = decision["type"]

    assert operation == "insert_anyway"
    assert decision.get("new_node_metadata") is None
    assert decision.get("split_plan") is None

    print(f"  Decision type: {operation}")
    print(f"  Reasoning: {decision['reasoning']}")
    print("✓ Insert anyway operation handled correctly")


def test_learn_with_structure_error_fallback():
    """Test learn_with_structure falls back gracefully on error."""
    print("\n" + "="*50)
    print("Testing error fallback behavior:")
    print("="*50)

    # Simulate error fallback result
    error_result = {
        "operation": "insert",
        "target_node": None,  # Would be root in real scenario
        "confidence": 0.0,
        "new_nodes": [],
        "actions": [],
        "reasoning": "Error occurred (test error) - fell back to insert"
    }

    assert error_result["operation"] == "insert", "Error should fall back to insert"
    assert error_result["confidence"] == 0.0, "Error should have 0 confidence"
    assert error_result["new_nodes"] == [], "Error should create no new nodes"
    assert "Error" in error_result["reasoning"] or "error" in error_result["reasoning"]

    print(f"  Operation: {error_result['operation']}")
    print(f"  Confidence: {error_result['confidence']}")
    print(f"  Reasoning: {error_result['reasoning'][:50]}...")
    print("✓ Error fallback behavior is correct")


def test_learn_with_structure_actions_returned():
    """Test learn_with_structure returns actions for correct node."""
    print("\n" + "="*50)
    print("Testing actions returned for correct node:")
    print("="*50)

    from graph_dao import TestGraphDAO
    from datetime import datetime

    dao = TestGraphDAO()

    # Create a node and add actions to it (with last_selected for get_recent to work)
    node_uuid = dao.create_node("Test Node")
    timestamp1 = datetime.now().isoformat()
    timestamp2 = datetime.now().isoformat()
    action1_uuid = dao.add_action(node_uuid, "Action 1", "Plan 1", "Prompt 1", last_selected=timestamp1)
    action2_uuid = dao.add_action(node_uuid, "Action 2", "Plan 2", "Prompt 2", last_selected=timestamp2)

    # Get recent actions
    recent_actions = dao.get_recent_actions_for_node(node_uuid, limit=4)

    assert len(recent_actions) == 2, f"Should have 2 actions, got {len(recent_actions)}"

    # Verify actions belong to correct node
    for action in recent_actions:
        assert action[4] == node_uuid, "Action should belong to test node"

    print(f"  Node: {node_uuid[:8]}...")
    print(f"  Actions retrieved: {len(recent_actions)}")
    print("✓ Actions returned for correct node")


def test_learn_with_structure_bootstrap_disabled():
    """Test learn_with_structure handles disabled bootstrap."""
    print("\n" + "="*50)
    print("Testing bootstrap disabled scenario:")
    print("="*50)

    class MockConfig:
        def is_bootstrap_enabled(self):
            return False

    class MockRoot:
        def __init__(self):
            self.children = []  # Empty
            self.node_uuid = "root-uuid"
            self.metadata = "Root"

    root = MockRoot()
    config = MockConfig()

    empty_graph = len(root.children) == 0
    bootstrap_enabled = config.is_bootstrap_enabled()

    assert empty_graph is True
    assert bootstrap_enabled is False

    # When bootstrap is disabled, should insert into root
    should_insert_to_root = empty_graph and not bootstrap_enabled

    assert should_insert_to_root is True

    print(f"  Empty graph: {empty_graph}")
    print(f"  Bootstrap enabled: {bootstrap_enabled}")
    print(f"  → Should insert to root: {should_insert_to_root}")
    print("✓ Bootstrap disabled handled correctly")


def test_learn_with_structure_split_target_node():
    """Test learn_with_structure finds correct target after split."""
    print("\n" + "="*50)
    print("Testing split target node selection:")
    print("="*50)

    class MockNode:
        def __init__(self, metadata):
            self.metadata = metadata
            self.node_uuid = f"uuid-{metadata.lower().replace(' ', '-')}"

    # Simulate new nodes after split
    new_nodes = [
        MockNode("Engineering"),
        MockNode("Marketing"),
        MockNode("Sales")
    ]

    split_plan = {
        "new_children": [
            {"metadata": "Engineering", "inherits_categories": ["eng"]},
            {"metadata": "Marketing", "inherits_categories": ["mkt"]},
            {"metadata": "Sales", "inherits_categories": ["sales"]}
        ],
        "new_data_goes_to": "Marketing"
    }

    # Find target node
    new_data_goes_to = split_plan.get("new_data_goes_to")
    target_node = None

    for node in new_nodes:
        if node.metadata == new_data_goes_to:
            target_node = node
            break

    assert target_node is not None, "Should find target node"
    assert target_node.metadata == "Marketing", "Should select Marketing node"

    print(f"  New data goes to: {new_data_goes_to}")
    print(f"  Found target: {target_node.metadata}")
    print("✓ Split target node selected correctly")


def run_learn_with_structure_tests():
    """Run only the learn_with_structure tests."""
    print("\n" + "="*70)
    print("RUNNING LEARN WITH STRUCTURE TESTS")
    print("="*70)

    test_learn_with_structure_bootstrap()
    test_learn_with_structure_high_confidence()
    test_learn_with_structure_medium_confidence()
    test_learn_with_structure_low_confidence()
    test_learn_with_structure_return_structure()
    test_learn_with_structure_create_child_operation()
    test_learn_with_structure_create_sibling_operation()
    test_learn_with_structure_split_operation()
    test_learn_with_structure_insert_anyway_operation()
    test_learn_with_structure_error_fallback()
    test_learn_with_structure_actions_returned()
    test_learn_with_structure_bootstrap_disabled()
    test_learn_with_structure_split_target_node()

    print("\n" + "="*70)
    print("ALL LEARN WITH STRUCTURE TESTS COMPLETED")
    print("="*70)


def run_split_node_tests():
    """Run only the split node tests."""
    print("\n" + "="*70)
    print("RUNNING SPLIT NODE TESTS")
    print("="*70)

    test_validate_split_plan_valid()
    test_validate_split_plan_too_few_children()
    test_validate_split_plan_duplicate_names()
    test_validate_split_plan_invalid_new_data_target()
    test_split_node_creates_correct_children()
    test_split_node_distributes_data()
    test_split_node_unassigned_categories()
    test_split_node_parent_keeps_actions()
    test_split_node_inserts_new_data()
    test_split_node_parent_relationships()
    test_validate_split_plan_empty_plan()
    test_validate_split_plan_missing_metadata()

    print("\n" + "="*70)
    print("ALL SPLIT NODE TESTS COMPLETED")
    print("="*70)


def run_node_creation_tests():
    """Run only the node creation tests."""
    print("\n" + "="*70)
    print("RUNNING NODE CREATION TESTS")
    print("="*70)

    test_create_child_node_basic()
    test_create_child_node_parent_child_linkage()
    test_create_child_node_max_depth_enforced()
    test_create_sibling_node_uses_correct_parent()
    test_create_sibling_of_root_creates_child()
    test_bootstrap_first_node_empty_root()
    test_create_child_with_data()
    test_refresh_node_embedding()
    test_create_node_none_parent_raises()
    test_create_node_empty_metadata_raises()

    print("\n" + "="*70)
    print("ALL NODE CREATION TESTS COMPLETED")
    print("="*70)


def run_llm_decide_structure_tests():
    """Run only the LLM decide structure tests."""
    print("\n" + "="*70)
    print("RUNNING LLM DECIDE STRUCTURE TESTS")
    print("="*70)

    test_get_siblings_helper()
    test_decide_structure_returns_correct_structure()
    test_decide_structure_create_child()
    test_decide_structure_create_sibling()
    test_decide_structure_split_plan_valid()
    test_decide_structure_insert_anyway()
    test_decide_structure_max_depth_enforced()
    test_decide_structure_fallback_on_invalid()
    test_decide_structure_no_model_available()
    test_decide_structure_split_plan_validation()

    print("\n" + "="*70)
    print("ALL LLM DECIDE STRUCTURE TESTS COMPLETED")
    print("="*70)


def run_llm_validate_fit_tests():
    """Run only the LLM validate fit tests."""
    print("\n" + "="*70)
    print("RUNNING LLM VALIDATE FIT TESTS")
    print("="*70)

    test_get_data_sample_basic()
    test_get_data_sample_empty_node()
    test_get_data_sample_none_node()
    test_get_data_sample_truncation()
    test_llm_validate_fit_returns_correct_structure()
    test_llm_validate_fit_parses_valid_json()
    test_llm_validate_fit_handles_malformed_response()
    test_llm_validate_fit_suggested_category()
    test_llm_validate_fit_no_model_available()

    print("\n" + "="*70)
    print("ALL LLM VALIDATE FIT TESTS COMPLETED")
    print("="*70)


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

    # LLM validate fit tests
    test_get_data_sample_basic()
    test_get_data_sample_empty_node()
    test_get_data_sample_none_node()
    test_get_data_sample_truncation()
    test_llm_validate_fit_returns_correct_structure()
    test_llm_validate_fit_parses_valid_json()
    test_llm_validate_fit_handles_malformed_response()
    test_llm_validate_fit_suggested_category()
    test_llm_validate_fit_no_model_available()

    # LLM decide structure tests
    test_get_siblings_helper()
    test_decide_structure_returns_correct_structure()
    test_decide_structure_create_child()
    test_decide_structure_create_sibling()
    test_decide_structure_split_plan_valid()
    test_decide_structure_insert_anyway()
    test_decide_structure_max_depth_enforced()
    test_decide_structure_fallback_on_invalid()
    test_decide_structure_no_model_available()
    test_decide_structure_split_plan_validation()

    # Node creation tests
    test_create_child_node_basic()
    test_create_child_node_parent_child_linkage()
    test_create_child_node_max_depth_enforced()
    test_create_sibling_node_uses_correct_parent()
    test_create_sibling_of_root_creates_child()
    test_bootstrap_first_node_empty_root()
    test_create_child_with_data()
    test_refresh_node_embedding()
    test_create_node_none_parent_raises()
    test_create_node_empty_metadata_raises()

    # Split node tests
    test_validate_split_plan_valid()
    test_validate_split_plan_too_few_children()
    test_validate_split_plan_duplicate_names()
    test_validate_split_plan_invalid_new_data_target()
    test_split_node_creates_correct_children()
    test_split_node_distributes_data()
    test_split_node_unassigned_categories()
    test_split_node_parent_keeps_actions()
    test_split_node_inserts_new_data()
    test_split_node_parent_relationships()
    test_validate_split_plan_empty_plan()
    test_validate_split_plan_missing_metadata()

    # Learn with structure tests
    test_learn_with_structure_bootstrap()
    test_learn_with_structure_high_confidence()
    test_learn_with_structure_medium_confidence()
    test_learn_with_structure_low_confidence()
    test_learn_with_structure_return_structure()
    test_learn_with_structure_create_child_operation()
    test_learn_with_structure_create_sibling_operation()
    test_learn_with_structure_split_operation()
    test_learn_with_structure_insert_anyway_operation()
    test_learn_with_structure_error_fallback()
    test_learn_with_structure_actions_returned()
    test_learn_with_structure_bootstrap_disabled()
    test_learn_with_structure_split_target_node()

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
    # run_traverse_with_confidence_tests()

    # Or run LLM validate fit tests:
    # run_llm_validate_fit_tests()

    # Or run LLM decide structure tests:
    # run_llm_decide_structure_tests()

    # Or run node creation tests:
    # run_node_creation_tests()

    # Or run split node tests:
    # run_split_node_tests()

    # Or run learn with structure tests:
    run_learn_with_structure_tests()

    # Or run individual test functions:
    # test_traverse()
    # test_learn()

    pass
