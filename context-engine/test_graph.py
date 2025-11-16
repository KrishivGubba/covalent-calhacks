"""
Test suite for the Graph context engine.

This module contains comprehensive tests for the Tree and Node classes,
including tests for:
- Graph traversal and node selection
- Learning new information and data insertion
- Action creation and triggering
"""

from graph import Tree

# Initialize the tree from database
print("Initializing graph from database...")
tree = Tree("../context-engine/graph.db")
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


def run_all_tests():
    """Run all test suites."""
    print("\n" + "="*70)
    print("RUNNING ALL TESTS FOR GRAPH CONTEXT ENGINE")
    print("="*70)
    
    test_traverse()
    test_learn()
    
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
