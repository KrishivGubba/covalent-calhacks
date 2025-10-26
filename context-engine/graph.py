import os
import json
import uuid
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from graph_dao import GraphDAO, TestGraphDAO
from anthropic import Anthropic

load_dotenv() 

class Node:
    def __init__(self, node_uuid=None, metadata=None, actions=None,
                 created=None, last_modified=None, parent_uuid=None,
                 children_uuid_arr=None, data=None, embedding=None):
        self.node_uuid = node_uuid
        self.metadata = metadata
        self.created = created
        self.last_modified = last_modified
        self.parent_uuid = parent_uuid
        self.children_uuid_arr = children_uuid_arr if children_uuid_arr else []
        self.actions = actions if actions else []
        self.data = data  # This will be populated lazily when requested
        self.embedding = embedding  # Vector representation of metadata
        self.children = []  # For in-memory tree structure
        self.parent = None   # For easier tree navigation

    def add_child(self, child_node):
        self.children.append(child_node)
        child_node.parent = self

    # clearly show the node's metadata and children
    def __repr__(self):
        return f"Node(metadata='{self.metadata}', children={self.children})"


class Tree:
    def __init__(self, db_path):
        self.nodes = {}  # Dictionary to store nodes by UUID for easy lookup
        self.root = None

        self.dao = GraphDAO(db_path)

        # Initialize Google AI client for embeddings
        self.API_KEY = os.getenv("GOOGLE_API_KEY")
        if self.API_KEY:
            try:
                genai.configure(api_key=self.API_KEY)
                self.model = "gemini-2.5-flash"
                self.embedding_model = "text-embedding-004"  # Updated to a more current embedding model
            except ImportError:
                print("Warning: google.generativeai not available")
                self.API_KEY = None
        else:
            print("Warning: GOOGLE_API_KEY environment variable not set")

        self.construct_graph(self.dao.get_all_nodes())

       
        # This prompt should contain key information about how the graph is structured
        self.BASE_PROMPT = '''
        You are a context engine that retrieves relevant information from a knowledge graph.
        
        The graph is designed such that the children have access to ALL the information contained in
        the parent node. The children can also have additional information that is not present in the parent but is specific
        to the child node.
        
        Each node represents a "task" or "project" (or a category of tasks or projects) that a user might be working on
        The nodes's children represent sub-tasks or related tasks/projects.
        Each node contains metadata, data and actions. Metadata is a brief description of the data contained in the node.

        internal nodes represent broader categories or projects, while leaf nodes represent specific tasks or pieces of information.    
        '''
        string = """this query is part of a traversal algorithm. You will be given the current node's metadata
        and the metadata of its children. You will also be given a user query. Your task is to determine the following:"""

        self.model = "gemini-2.5-flash"

    def vectorize_text(self, text):
        """
        Vectorize a piece of text using Google's embedding model.
        
        Args:
            text (str): The text to vectorize
            
        Returns:
            numpy.ndarray: The embedding vector, or None if vectorization fails
        """
        if not self.API_KEY or not text:
            return None
            
        try:
            result = genai.embed_content(
                model=self.embedding_model,
                content=text,
            )
            embedding = np.array(result['embedding']).reshape(1, -1)
            return embedding
        except Exception as e:
            print(f"Error vectorizing text: {e}")
            return None

    def get_parent_metadata(self, node):
        if node is None:
            return ""
        else:
            if node.parent_uuid:
                return self.get_parent_metadata(self.nodes[node.parent_uuid]) + node.metadata + "\n"
            else:
                return self.get_parent_metadata(None) + node.metadata + "\n"
    def construct_graph(self, node_data):
        """
        Constructs the graph from database data.
        
        Args:
            node_data: List of tuples from database with structure:
                      (node_uuid, metadata, created, last_modified, 
                       parent_uuid, children_uuid_arr, actions)
        """
        # First pass: Create all nodes and store them in the dictionary
        for row in node_data:
            node_uuid = row[0]
            metadata = row[1]
            created = row[2]
            last_modified = row[3]
            parent_uuid = row[4]
            children_uuid_arr_str = row[5]  # This is stored as a string in SQLite
            actions_str = row[6]  # Concatenated actions from the join
            
            # Parse children_uuid_arr from string format (assuming JSON array format)
            children_uuid_arr = []
            if children_uuid_arr_str:
                try:
                    children_uuid_arr = json.loads(children_uuid_arr_str)
                except json.JSONDecodeError:
                    # Handle case where it might be stored differently
                    children_uuid_arr = []
            
            # Parse actions from concatenated string
            actions = []
            if actions_str:
                # Split by comma and parse each action (format: "uuid|action_name")
                action_items = actions_str.split(',')
                for action_item in action_items:
                    if '|' in action_item:
                        action_uuid, action_name = action_item.split('|', 1)
                        actions.append({
                            'uuid': action_uuid,
                            'action_name': action_name
                        })
            
            # Create the node with all database fields
            node = Node(
                node_uuid=node_uuid,
                metadata=metadata,
                created=created,
                last_modified=last_modified,
                parent_uuid=parent_uuid,
                children_uuid_arr=children_uuid_arr,
                actions=actions
            )
            
            # metadata_chain to include parent's metadata (recursively till the root)
        
            
            # Store the node in our dictionary for quick lookup
            self.nodes[node_uuid] = node
            
            # If this node has no parent, it's the root
            if parent_uuid is None:
                self.root = node
        
        # Second pass: Build the parent-child relationships
        for node_uuid, node in self.nodes.items():
            # Set up parent relationship
            if node.parent_uuid is not None and node.parent_uuid in self.nodes:
                parent_node = self.nodes[node.parent_uuid]
                node.parent = parent_node
                parent_node.add_child(node)
                
            
            # Note: children_uuid_arr are already stored in the node, 
            # but the actual child objects are linked via parent relationships above
        # Third pass: Generate embeddings for all nodes

        print("NODES:", self.nodes)
        for node_uuid, node in self.nodes.items():
            metadata_chain = self.get_parent_metadata(node)
            #print("Metadata chain for node", node_uuid, ":", metadata_chain)
            # Vectorize the metadata and store the embedding
            if metadata:
                node.embedding = self.vectorize_text(metadata_chain)
    

    def traverse(self, screen, curr=None):
        """
        Traverse the tree to find the most relevant node based on screen input.
        
        Args:
            screen (str): Text describing what is currently visible on the user's screen
            curr: Current node (optional, defaults to root)
            
        Returns:
            Node: The node with the highest cosine similarity to the screen input
        """
        if not screen:
            return self.root if curr is None else curr
            
        # Vectorize the screen input
        screen_embedding = self.vectorize_text(screen)
        if screen_embedding is None:
            print("Warning: Could not vectorize screen input")
            return self.root if curr is None else curr
        
        # Find the node with highest cosine similarity
        best_node = None # the actual node object
        best_similarity = -1.0 
        
        for node_uuid, node in self.nodes.items():
            if node.embedding is not None:
                try:
                    # Calculate cosine similarity
                    similarity = cosine_similarity(screen_embedding, node.embedding)[0][0]
                    
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_node = node
                        
                except Exception as e:
                    print(f"Error calculating similarity for node {node_uuid}: {e}")
                    continue
        
        # if best_node is not None:
        #     print(f"Best match: Node '{best_node.metadata}' with similarity: {best_similarity:.4f}")
        #     return best_node
        # else:
        #     print("No suitable node found, returning root")
        #     return self.root if curr is None else curr
        if best_node is None:
            print("No suitable node found, returning root")
            return self.root if curr is None else curr
        # sanity check the best node by passing the screen and best_node's metadata to the model
        # if the model agrees, return best_node, else start manual traversal algorithm
        BASE_PROMPT = self.BASE_PROMPT  # Create a local copy to avoid accidental modification

        # Construct the prompt fresh each time
        # prompt = BASE_PROMPT + f'''
        #     This is the current screen content (describing what the user is working on):
        #     {screen}
        #     We have already traversed the graph and found the best matching node based on cosine similarity.
        #     Here are the metadatas of all the nodes connecting the root to the node we selected: "{self.get_parent_metadata(best_node)}"
            
        #     Can you perform a sanity check and confirm if this is the most relevant node for the current screen content?
        #     You don't have to verify if this is the best node, just make sure this is a reasonable node given the current context.
        #     Answer with a simple "yes" or "no". Do not provide any additional explanation.
        # '''
        prompt = f"screen: {screen}\nselected_node: {self.get_parent_metadata(best_node)}"
        model = genai.GenerativeModel(self.model)
        # response = model.generate_content(prompt)

        return best_node
    
    def learn(self, summary, data, key=None, data_type="text"):
        """
        Learn new information by inserting it into the most relevant node.
        
        Args:
            summary (str): Summary/description of the data to help find the right node
            data (str or dict): The actual data to store
            key (str, optional): Key/name for this data. If None, uses a timestamp
            data_type (str): Type of data being stored (default: "text")
            
        Returns:
            tuple: (node, data_uuid) - The node where data was inserted and the data UUID
        """
        # Find the most relevant node using traverse
        node = self.traverse(summary)

        # take the summary of what's going on 
        mtd = self.get_parent_metadata(node)
        ACTION_CREATION_PROMPT = self.BASE_PROMPT[75:] + f"""
            Now, after looking at this graph this is most relevant node that we picked: {mtd}
            You are an AI Desktop Agent whose goal is to automate any tasks for the user. Your goal is to ANTICIPATE ANY ACTIONS
            THAT THE USER MIGHT WANT TO TAKE BASED ON THE CURRENT SCREEN CONTENT.

            You have access to the user's computer screen (if you want to control it and take actions)
            You have access to the GSuite (Email, Calendar, Docs, Sheets, etc)
            You can define a series of tasks as well.

            Here is a description of what the current user is doing:
            {summary}

            Based on what the user is doing, suggest a task that the user might want to perform.
            The task should be a simple action that the user can perform.
            For example: "Send an email to Ritesh - rneela@wisc.edu confirming the meeting at 10am. Schedule this meeting on my calendar from 10am - 11am"

            Note that when an action is performed, you will be given all context so don't worry about providing too much context
            Focus on being clear what action is to be performed
            
            ONLY output the task and nothing else.
        """
        # ALSO ADD THE OCR HERE!!!!! IF I GET THIS FROM SCREEN VIEWING
        
        # Call Claude Sonnet 4.5 with the action prompt
        try:
            anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": ACTION_CREATION_PROMPT}
                ]
            )
            suggested_action = response.content[0].text
            print(f"\n{'='*60}")
            print(f"Suggested Action from Claude:")
            print(f"{suggested_action}")
            print(f"{'='*60}\n")
            
            # Insert the suggested action into the database if it was generated successfully
            if suggested_action and node:
                try:
                    action_uuid = self.dao.add_action(
                        node_uuid=node.node_uuid,
                        action_name=suggested_action
                    )
                    print(f"Successfully inserted action into database with UUID: {action_uuid}")
                except Exception as action_error:
                    print(f"Error inserting action into database: {action_error}")
        except Exception as e:
            print(f"Error calling Claude API: {e}")
            suggested_action = None
        
        if node is None:
            print("Warning: Could not find suitable node, using root")
            node = self.root
        
        # Generate a key if not provided
        if key is None:
            key = f"data_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Convert data to string if it's a dict
        if isinstance(data, dict):
            data_str = json.dumps(data)
            if data_type == "text":
                data_type = "json"
        else:
            data_str = str(data)
        
        # Insert data into the database using the DAO
        try:
            data_uuid = self.dao.add_data(
                node_uuid=node.node_uuid,
                key=key,
                data_type=data_type,
                info=data_str
            )
            print(f"Successfully inserted data into node '{node.metadata}' (UUID: {node.node_uuid})")
            print(f"Data UUID: {data_uuid}")
            return node.node_uuid, data_str
        except Exception as e:
            print(f"Error inserting data: {e}")
            return node.node_uuid, None
        

    
    # show as adjacency list
    def __repr__(self):
        def build_adj_list(node, adj_list=None):
            if adj_list is None:
                adj_list = {}
            adj_list[node.metadata] = [child.metadata for child in node.children]
            for child in node.children:
                build_adj_list(child, adj_list)
            return adj_list

        return str(build_adj_list(self.root))

print("Initializing graph from database...")
tree = Tree("graph.db")
print("Graph structure:")
print(tree)

# Example usage of the traverse method
# if tree.API_KEY:  # Only test if API key is available
#     print("\n" + "="*50)
#     print("Testing traverse method:")
    
#     # Test with some example screen inputs
#     test_screens = [
#         "the user is currently writing an email to schedule an interview with a candidate 'Ritesh' who is currently in the interview process for a software engineering internship for summer 2026",
#         "the user is currently making a LinkedIn posting for a software engineering internship for summer 2026",
#     ]

#     test_screens = [
#         # ========== RECRUITING - INTERN - SUMMER 2026 ==========
#         "the user is currently writing an email to schedule an interview with a candidate 'Ritesh' who is currently in the interview process for a software engineering internship for summer 2026",
#         "the user is currently making a LinkedIn posting for a software engineering internship for summer 2026",
#         "reviewing resumes for summer 2026 intern positions",
#         "scheduling technical interviews with Hemant for the summer 2026 internship program",
#         "sending rejection emails to candidates who didn't make it to the final round for summer internships",
#         "creating an offer letter for Krishiv who will be joining as a summer 2026 intern",
        
#         # ========== RECRUITING - INTERN - FALL 2026 ==========
#         "planning the recruiting timeline for fall 2026 internships",
#         "posting job descriptions for fall 2026 software engineering intern positions on the careers page",
#         "screening applications received for the fall 2026 intern cohort",
#         "coordinating with hiring managers about fall 2026 internship openings",
        
#         # ========== RECRUITING - NEW GRAD - 2025 ==========
#         "reviewing applications for 2025 new graduate software engineer positions",
#         "conducting final round interviews for 2025 new grad candidates",
#         "preparing onboarding materials for new grads starting in 2025",
#         "sending offer letters to selected 2025 new graduate candidates",
        
#         # ========== RECRUITING - NEW GRAD - 2026 ==========
#         "planning the campus recruiting strategy for 2026 new graduates",
#         "updating the job requirements for 2026 new grad positions",
#         "scheduling on-campus interviews for 2026 graduating students",
        
#         # ========== RECRUITING - NEW GRAD - EVENTS - ONLINE WEBINAR ==========
#         "preparing slides for an online webinar about our company culture for potential new grad candidates",
#         "sending calendar invites for the upcoming recruiting webinar",
#         "hosting a virtual Q&A session for students interested in new grad roles",
#         "following up with attendees from last week's career webinar",
        
#         # ========== RECRUITING - NEW GRAD - EVENTS - CAREER FAIR ==========
#         "booking a booth at the university career fair happening next month",
#         "preparing company brochures and swag for the career fair",
#         "coordinating with the recruiting team about staffing the career fair booth",
#         "collecting resumes at the MIT career fair",
        
#         # ========== RECRUITING - NEW GRAD - EVENTS - CAREER CONFERENCE ==========
#         "registering the company for the Grace Hopper Conference",
#         "preparing a presentation for the upcoming tech diversity conference",
#         "scheduling one-on-one meetings with candidates at the career conference",
#         "following up with promising candidates met at last week's conference",
        
#         # ========== EMPLOYEE MANAGEMENT - ONBOARDING ==========
#         "setting up laptop and accounts for a new employee starting next week",
#         "scheduling orientation sessions for the new hire cohort",
#         "assigning a mentor to a newly onboarded software engineer",
#         "sending out the onboarding checklist to a new team member",
#         "coordinating with IT to ensure all onboarding equipment is ready",
        
#         # ========== EMPLOYEE MANAGEMENT - ISSUES ==========
#         "investigating a complaint about workplace harassment",
#         "mediating a conflict between two team members",
#         "addressing concerns raised by an employee about their workload",
#         "following up on a performance improvement plan with an underperforming employee",
#         "documenting an incident report for HR records",
        
#         # ========== EMPLOYEE MANAGEMENT - QUESTIONS/REQUESTS - ANSWER QUESTIONS ==========
#         "responding to an employee's question about the 401k matching policy",
#         "clarifying the work-from-home policy for a remote employee",
#         "explaining the performance review process to a new manager",
#         "answering questions about health insurance enrollment",
#         "providing information about the company's parental leave policy",
        
#         # ========== EMPLOYEE MANAGEMENT - QUESTIONS/REQUESTS - APPROVE TIMESHEETS ==========
#         "reviewing and approving timesheets for the engineering team",
#         "following up with employees who haven't submitted their timesheets",
#         "investigating discrepancies in submitted timesheet hours",
#         "bulk approving timesheets for the end of the pay period",
        
#         # ========== EMPLOYEE MANAGEMENT - QUESTIONS/REQUESTS - APPROVE LEAVE REQUESTS ==========
#         "approving vacation requests for the summer holiday period",
#         "reviewing a sick leave request that exceeds the standard policy",
#         "coordinating leave schedules to ensure adequate team coverage",
#         "approving parental leave for an employee expecting a baby",
#         "handling a last-minute emergency leave request",
        
#         # ========== EDGE CASES / AMBIGUOUS ==========
#         "drafting an email to the entire engineering organization",
#         "reviewing the company's diversity and inclusion initiatives",
#         "preparing for quarterly business review meeting",
#         "updating the employee handbook with new policies",
#     ]

#     # Optional: Organize tests by expected node for easier validation
#     test_cases_with_expected_nodes = [
#         # Format: (screen_description, expected_node_metadata)
#         ("reviewing resumes for summer 2026 intern positions", "Summer 2026"),
#         ("hosting a virtual Q&A session for students interested in new grad roles", "Online Webinar"),
#         ("responding to an employee's question about the 401k matching policy", "Answer Questions"),
#         ("reviewing and approving timesheets for the engineering team", "Approve Timesheets"),
#         ("approving vacation requests for the summer holiday period", "Approve Leave Requests"),
#         ("setting up laptop and accounts for a new employee starting next week", "Onboarding"),
#         ("mediating a conflict between two team members", "Issues"),
#         ("collecting resumes at the MIT career fair", "Career Fair"),
#         ("preparing a presentation for the upcoming tech diversity conference", "Career Conference"),
#         ("screening applications received for the fall 2026 intern cohort", "Fall 2026"),
#         ("conducting final round interviews for 2025 new grad candidates", "2025"),
#         ("planning the campus recruiting strategy for 2026 new graduates", "2026"),
#     ]
    
#     for screen in test_screens:
#         print(f"\nScreen input: '{screen}'")
#         result_node = tree.traverse(screen)
#         if result_node:
#             print(f"Selected node: {result_node}")
#         else:
#             print("No node selected")
# else:
#     print("\nSkipping traverse test - API key not available")

# Test cases for the learn() method
if tree.API_KEY:
    print("\n" + "="*50)
    print("Testing learn() method:")
    print("="*50)
    
    # Test Case 1: Simple text data for a specific candidate
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
    
    # Test Case 2: Career fair information
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
    
    # Test Case 5: Leave request approval
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
    
    # Test Case 7: Employee issue resolution
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
    node_uuid7, written_data7 = tree.learn(summary7, data7, key="conflict_resolution_042")
    print(f"Data inserted into node UUID: {node_uuid7}")
    
    print("\n" + "="*50)
    print("All learn() test cases completed!")
    print("="*50)
    
    # Verify data was inserted by checking the database
    print("\n--- Verifying data in database ---")
    cursor = tree.dao.cursor
    cursor.execute("SELECT COUNT(*) FROM data_table")
    count = cursor.fetchone()[0]
    print(f"Total records in data_table: {count}")
    
else:
    print("\nSkipping learn() test - API key not available")