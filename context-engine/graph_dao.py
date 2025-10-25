
'''
Data Access Object for Graph operations. Used to load graph data from SQlite DB
'''
import os
import sqlite3

class GraphDAO:
    def __init__(self, db_path):
        '''
        Initialize the DAO with a SQLite connection.
        '''
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()

    def get_all_nodes(self):
        '''Retrieve all nodes from the database with their associated actions.'''
        query = """
        SELECT 
            n.Node_UUID as node_uuid,
            n.Metadata,
            n.created,
            n.last_modified,
            n.parent_uuid,
            n.children_uuid_arr,
            GROUP_CONCAT(a.UUID || '|' || a.Action_name) as actions
        FROM node_table n
        LEFT JOIN action_table a ON n.UUID = a.Node_UUID
        GROUP BY n.UUID, n.Metadata, n.created, n.last_modified, n.parent_uuid, n.children_uuid_arr
        """
        # returns a list of tuples
        return self.execute_query(query)

    def execute_query(self, query, params=None):
        '''
        Execute a query with optional parameters and return the result.
        '''
        if params is None:
            params = ()
        self.cursor.execute(query, params)
        self.conn.commit()
        return self.cursor.fetchall()

    def add_node(self, metadata, data):
        '''Insert a node into the database.'''
        query = "INSERT INTO node_table (metadata, data) VALUES (?, ?)"
        self.execute_query(query, (metadata, data))

    def remove_node(self, node_id):
        '''Remove a node from the database by id.'''
        query = "DELETE FROM node_table WHERE node_uuid = ?"
        self.execute_query(query, (node_id,))

    def find_node(self, metadata=None, data=None):
        '''Find nodes by metadata and/or data.'''
        query = "SELECT * FROM node_table WHERE 1=1"
        params = []
        if metadata is not None:
            query += " AND metadata = ?"
            params.append(metadata)
        if data is not None:
            query += " AND data = ?"
            params.append(data)
        return self.execute_query(query, tuple(params))

    def close(self):
        '''Close the database connection.'''
        self.conn.close()


class TestGraphDAO:
    def __init__(self):
        '''
        Initialize the test DAO with a hardcoded graph structure for unit testing.
        '''
        import uuid
        import json
        from datetime import datetime
        
        # Create UUIDs for all nodes
        self.node_uuids = {
            'root': str(uuid.uuid4()),
            'recruiting': str(uuid.uuid4()),
            'employee_management': str(uuid.uuid4()),
            'intern': str(uuid.uuid4()),
            'new_grad': str(uuid.uuid4()),
            'summer2026': str(uuid.uuid4()),
            'fall2026': str(uuid.uuid4()),
            '2025': str(uuid.uuid4()),
            '2026': str(uuid.uuid4()),
            'events': str(uuid.uuid4()),
            'online_webinar': str(uuid.uuid4()),
            'career_fair': str(uuid.uuid4()),
            'career_conference': str(uuid.uuid4()),
            'onboarding': str(uuid.uuid4()),
            'issues': str(uuid.uuid4()),
            'questions_requests': str(uuid.uuid4()),
            'answer_questions': str(uuid.uuid4()),
            'approve_timesheets': str(uuid.uuid4()),
            'approve_leave_requests': str(uuid.uuid4()),
            'Ritesh': str(uuid.uuid4()),
            'Siddharth': str(uuid.uuid4()),
            'Hemant': str(uuid.uuid4()),
            'Krishiv': str(uuid.uuid4())
        }
        
        # Define the adjacency list and create node data
        current_time = datetime.now().isoformat()
        
        self.nodes_data = [
            # root: recruiting, employee management
            (self.node_uuids['root'], 'Root Node', current_time, current_time, None, 
             json.dumps([self.node_uuids['recruiting'], self.node_uuids['employee_management']]), None),
            
            # recruiting: Intern, New Grad
            (self.node_uuids['recruiting'], 'Recruiting', current_time, current_time, self.node_uuids['root'],
             json.dumps([self.node_uuids['intern'], self.node_uuids['new_grad']]), None),
            
            # employee management: onboarding, issues, questions/requests
            (self.node_uuids['employee_management'], 'Employee Management', current_time, current_time, self.node_uuids['root'],
             json.dumps([self.node_uuids['onboarding'], self.node_uuids['issues'], self.node_uuids['questions_requests']]), None),
            
            # Intern: Summer2026, Fall 2026
            (self.node_uuids['intern'], 'Intern', current_time, current_time, self.node_uuids['recruiting'],
             json.dumps([self.node_uuids['summer2026'], self.node_uuids['fall2026']]), None),
            
            # New Grad: 2025, 2026, Events
            (self.node_uuids['new_grad'], 'New Grad', current_time, current_time, self.node_uuids['recruiting'],
             json.dumps([self.node_uuids['2025'], self.node_uuids['2026'], self.node_uuids['events']]), None),
            
            # Summer2026 (leaf node)
            (self.node_uuids['summer2026'], 'Summer 2026', current_time, current_time, self.node_uuids['intern'],
             json.dumps([self.node_uuids['Ritesh'], self.node_uuids['Siddharth'], self.node_uuids['Hemant'], self.node_uuids['Krishiv']]), 'action_summer2026|process_summer_applications'),
            
            # Fall 2026 (leaf node)
            (self.node_uuids['fall2026'], 'Fall 2026', current_time, current_time, self.node_uuids['intern'],
             json.dumps([]), 'action_fall2026|process_fall_applications'),
            
            # 2025 (leaf node)
            (self.node_uuids['2025'], '2025', current_time, current_time, self.node_uuids['new_grad'],
             json.dumps([]), 'action_2025|process_2025_applications'),
            
            # 2026 (leaf node)
            (self.node_uuids['2026'], '2026', current_time, current_time, self.node_uuids['new_grad'],
             json.dumps([]), 'action_2026|process_2026_applications'),
            
            # Events: Online webinar, career fair, career conference
            (self.node_uuids['events'], 'Events', current_time, current_time, self.node_uuids['new_grad'],
             json.dumps([self.node_uuids['online_webinar'], self.node_uuids['career_fair'], self.node_uuids['career_conference']]), None),
            
            # Online webinar (leaf node)
            (self.node_uuids['online_webinar'], 'Online Webinar', current_time, current_time, self.node_uuids['events'],
             json.dumps([]), 'action_webinar|conduct_webinar'),
            
            # Career fair (leaf node)
            (self.node_uuids['career_fair'], 'Career Fair', current_time, current_time, self.node_uuids['events'],
             json.dumps([]), 'action_fair|organize_career_fair'),
            
            # Career conference (leaf node)
            (self.node_uuids['career_conference'], 'Career Conference', current_time, current_time, self.node_uuids['events'],
             json.dumps([]), 'action_conference|organize_conference'),
            
            # Onboarding (leaf node)
            (self.node_uuids['onboarding'], 'Onboarding', current_time, current_time, self.node_uuids['employee_management'],
             json.dumps([]), 'action_onboarding|onboard_new_employees'),
            
            # Issues (leaf node)
            (self.node_uuids['issues'], 'Issues', current_time, current_time, self.node_uuids['employee_management'],
             json.dumps([]), 'action_issues|resolve_employee_issues'),
            
            # questions/requests: answer questions, approve timesheets, approve leave requests
            (self.node_uuids['questions_requests'], 'Questions/Requests', current_time, current_time, self.node_uuids['employee_management'],
             json.dumps([self.node_uuids['answer_questions'], self.node_uuids['approve_timesheets'], self.node_uuids['approve_leave_requests']]), None),
            
            # Answer questions (leaf node)
            (self.node_uuids['answer_questions'], 'Answer Questions', current_time, current_time, self.node_uuids['questions_requests'],
             json.dumps([]), 'action_answer|answer_employee_questions'),
            
            # Approve timesheets (leaf node)
            (self.node_uuids['approve_timesheets'], 'Approve Timesheets', current_time, current_time, self.node_uuids['questions_requests'],
             json.dumps([]), 'action_timesheets|approve_employee_timesheets'),
            
            # Approve leave requests (leaf node)
            (self.node_uuids['approve_leave_requests'], 'Approve Leave Requests', current_time, current_time, self.node_uuids['questions_requests'],
             json.dumps([]), 'action_leave|approve_leave_requests'),

            # Ritesh (leaf node)
            (self.node_uuids['Ritesh'], 'Ritesh', current_time, current_time, self.node_uuids['summer2026'],
             json.dumps([]), 'action_ritesh|process_ritesh_application'),

            # Siddharth (leaf node)
            (self.node_uuids['Siddharth'], 'Siddharth', current_time, current_time, self.node_uuids['summer2026'],
             json.dumps([]), 'action_siddharth|process_siddharth_application'),

            # Hemant (leaf node)
            (self.node_uuids['Hemant'], 'Hemant', current_time, current_time, self.node_uuids['summer2026'],
             json.dumps([]), 'action_hemant|process_hemant_application'),

            # Krishiv (leaf node)
            (self.node_uuids['Krishiv'], 'Krishiv', current_time, current_time, self.node_uuids['summer2026'],
             json.dumps([]), 'action_krishiv|process_krishiv_application')
        ]

    def get_all_nodes(self):
        '''
        Retrieve all nodes from the test graph data.
        Returns data in the same format as GraphDAO: 
        (node_uuid, metadata, created, last_modified, parent_uuid, children_uuid_arr, actions)
        '''
        return self.nodes_data

if __name__ == "__main__":
    # Initialize test data
    test_dao = TestGraphDAO()
    
    # Connect to the database
    db_path = os.path.join(os.path.dirname(__file__), "graph.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # Clear existing data (optional - comment out if you want to keep existing data)
    cursor.execute("DELETE FROM action_table;")
    cursor.execute("DELETE FROM node_table;")
    
    print("Inserting test data into database...")
    
    # Insert all nodes
    for node_data in test_dao.nodes_data:
        node_uuid, metadata, created, last_modified, parent_uuid, children_uuid_arr, actions = node_data
        
        # Insert node into node_table
        cursor.execute(
            """
            INSERT INTO node_table (UUID, Metadata, created, last_modified, parent_uuid, children_uuid_arr)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (node_uuid, metadata, created, last_modified, parent_uuid, children_uuid_arr)
        )
        
        # Insert actions into action_table if they exist
        if actions:
            # Actions are in format: "action_uuid|action_name"
            action_uuid, action_name = actions.split('|')
            cursor.execute(
                """
                INSERT INTO action_table (UUID, Action_name, Node_UUID)
                VALUES (?, ?, ?)
                """,
                (action_uuid, action_name, node_uuid)
            )
    
    # Commit all changes
    conn.commit()
    print(f"Successfully inserted {len(test_dao.nodes_data)} nodes into the database.")
    
    # Verify the data
    cursor.execute("SELECT COUNT(*) FROM node_table;")
    node_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM action_table;")
    action_count = cursor.fetchone()[0]
    
    print(f"Total nodes in database: {node_count}")
    print(f"Total actions in database: {action_count}")
    
    # Close connection
    conn.close()
    print("Database connection closed.")