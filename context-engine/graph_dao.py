
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
        # Ensure the database file has write permissions
        if os.path.exists(db_path):
            os.chmod(db_path, 0o666)
        
        # Open database with write access
        self.conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            timeout=10.0  # Wait up to 10 seconds if database is locked
        )
        # Enable WAL mode for better concurrent access
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.cursor = self.conn.cursor()

    def get_all_nodes(self):
        '''Retrieve all nodes from the database with their associated actions.'''
        query = """
        SELECT 
            n.UUID as node_uuid,
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

    def add_data(self, node_uuid, key, data_type, info, category=None):
        '''
        Insert data into the data_table associated with a specific node.

        Args:
            node_uuid (str): UUID of the node to associate this data with
            key (str): Key/name for this piece of data
            data_type (str): Type of data (e.g., 'text', 'json', 'url', etc.)
            info (str): The actual data content
            category (str, optional): Category/folder for this data

        Returns:
            str: UUID of the inserted data record
        '''
        import uuid
        data_uuid = str(uuid.uuid4())
        query = """
            INSERT INTO data_table (UUID, Node_UUID, key, type, info, category)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        self.execute_query(query, (data_uuid, node_uuid, key, data_type, info, category))
        return data_uuid

    def add_action(self, node_uuid, action_name, action_plan=None, action_prompt=None, last_selected=None):
        '''
        Insert an action into the action_table associated with a specific node.

        Args:
            node_uuid (str): UUID of the node to associate this action with
            action_name (str): Name/description of the action
            action_plan (str, optional): Detailed plan for the action (user-facing)
            action_prompt (str, optional): Full prompt for LangGraph execution
            last_selected (str, optional): ISO format timestamp of last selection

        Returns:
            str: UUID of the inserted action record
        '''
        import uuid
        action_uuid = str(uuid.uuid4())

        print(f"🔧 add_action() called:")
        print(f"  - node_uuid: {node_uuid}")
        print(f"  - action_name: {action_name[:50]}..." if len(action_name) > 50 else f"  - action_name: {action_name}")
        print(f"  - Generated action_uuid: {action_uuid}")

        query = """
            INSERT INTO action_table (UUID, Action_name, Action_plan, Action_prompt, Node_UUID, last_selected)
            VALUES (?, ?, ?, ?, ?, ?)
        """

        try:
            self.execute_query(query, (action_uuid, action_name, action_plan, action_prompt, node_uuid, last_selected))
            print(f"  ✅ Successfully inserted action into database")
            return action_uuid
        except Exception as e:
            print(f"  ❌ Failed to insert action: {e}")
            print(f"  Database path: {self.conn}")
            import traceback
            traceback.print_exc()
            raise

    def get_action_by_id(self, action_uuid):
        '''
        Retrieve an action by its UUID.
        
        Args:
            action_uuid (str): UUID of the action to retrieve
            
        Returns:
            tuple: (action_uuid, action_name, action_prompt, node_uuid) or None if not found
        '''
        query = """
            SELECT UUID, Action_name, Action_prompt, Node_UUID 
            FROM action_table 
            WHERE UUID = ?
        """
        result = self.execute_query(query, (action_uuid,))
        return result[0] if result else None

    def get_node_by_id(self, node_uuid):
        '''
        Retrieve a node by its UUID.
        
        Args:
            node_uuid (str): UUID of the node to retrieve
            
        Returns:
            tuple: Node data or None if not found
        '''
        query = """
            SELECT UUID, Metadata, created, last_modified, parent_uuid, children_uuid_arr
            FROM node_table 
            WHERE UUID = ?
        """
        result = self.execute_query(query, (node_uuid,))
        return result[0] if result else None

    def get_data_for_node(self, node_uuid):
        '''
        Retrieve all data entries for a specific node.

        Args:
            node_uuid (str): UUID of the node

        Returns:
            list: List of tuples containing (uuid, node_uuid, key, type, info)
        '''
        query = """
            SELECT UUID, Node_UUID, key, type, info
            FROM data_table
            WHERE Node_UUID = ?
        """
        return self.execute_query(query, (node_uuid,))

    def update_action_last_selected(self, action_uuid, timestamp=None):
        '''
        Update the last_selected timestamp for an action.

        Args:
            action_uuid (str): UUID of the action
            timestamp (str, optional): ISO format timestamp. Uses current time if None.

        Returns:
            None
        '''
        if timestamp is None:
            from datetime import datetime
            timestamp = datetime.now().isoformat()

        query = """
            UPDATE action_table
            SET last_selected = ?
            WHERE UUID = ?
        """
        self.execute_query(query, (timestamp, action_uuid))

    def update_action(self, action_uuid, action_name, action_plan, action_prompt):
        '''
        Update an existing action's fields.

        Args:
            action_uuid (str): UUID of the action to update
            action_name (str): New action name
            action_plan (str): New action plan
            action_prompt (str): New action prompt

        Returns:
            None
        '''
        query = """
            UPDATE action_table
            SET Action_name = ?, Action_plan = ?, Action_prompt = ?
            WHERE UUID = ?
        """
        self.execute_query(query, (action_name, action_plan, action_prompt, action_uuid))

    def get_actions_for_node(self, node_uuid, order_by_last_selected=True):
        '''
        Get all actions for a node, optionally sorted by last_selected.

        Args:
            node_uuid (str): UUID of the node
            order_by_last_selected (bool): If True, sort by last_selected DESC (NULLs last)

        Returns:
            list: List of tuples (UUID, Action_name, Action_plan, Action_prompt, Node_UUID, last_selected)
        '''
        if order_by_last_selected:
            query = """
                SELECT UUID, Action_name, Action_plan, Action_prompt, Node_UUID, last_selected
                FROM action_table
                WHERE Node_UUID = ?
                ORDER BY last_selected IS NULL, last_selected DESC
            """
        else:
            query = """
                SELECT UUID, Action_name, Action_plan, Action_prompt, Node_UUID, last_selected
                FROM action_table
                WHERE Node_UUID = ?
            """
        return self.execute_query(query, (node_uuid,))

    def get_recent_actions_for_node(self, node_uuid, limit=4):
        '''
        Get the N most recently selected actions for a node.

        Args:
            node_uuid (str): UUID of the node
            limit (int): Maximum number of actions to return

        Returns:
            list: List of tuples (UUID, Action_name, Action_plan, Action_prompt, Node_UUID, last_selected)
        '''
        query = """
            SELECT UUID, Action_name, Action_plan, Action_prompt, Node_UUID, last_selected
            FROM action_table
            WHERE Node_UUID = ? AND last_selected IS NOT NULL
            ORDER BY last_selected DESC
            LIMIT ?
        """
        return self.execute_query(query, (node_uuid, limit))

    def delete_stale_actions(self, node_uuid, days_threshold=3):
        '''
        Delete actions where last_selected is older than threshold days.
        Does NOT delete actions where last_selected is NULL.

        Args:
            node_uuid (str): UUID of the node
            days_threshold (int): Number of days threshold

        Returns:
            int: Number of actions deleted
        '''
        from datetime import datetime, timedelta
        threshold_date = (datetime.now() - timedelta(days=days_threshold)).isoformat()

        query = """
            DELETE FROM action_table
            WHERE Node_UUID = ?
            AND last_selected IS NOT NULL
            AND last_selected < ?
        """
        self.cursor.execute(query, (node_uuid, threshold_date))
        deleted_count = self.cursor.rowcount
        self.conn.commit()
        return deleted_count

    def get_data_for_node_by_category(self, node_uuid):
        '''
        Get data for a node grouped by category.

        Args:
            node_uuid (str): UUID of the node

        Returns:
            dict: {category_name: [(uuid, node_uuid, key, type, info, category)], ...}
        '''
        query = """
            SELECT UUID, Node_UUID, key, type, info, category
            FROM data_table
            WHERE Node_UUID = ?
            ORDER BY category
        """
        results = self.execute_query(query, (node_uuid,))

        # Group by category
        grouped = {}
        for row in results:
            category = row[5] if row[5] else "uncategorized"
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(row)

        return grouped

    def get_categories_for_node(self, node_uuid):
        '''
        Get list of unique category names for a node.

        Args:
            node_uuid (str): UUID of the node

        Returns:
            list: List of category names
        '''
        query = """
            SELECT DISTINCT category
            FROM data_table
            WHERE Node_UUID = ? AND category IS NOT NULL
        """
        results = self.execute_query(query, (node_uuid,))
        return [row[0] for row in results]

    def add_data_with_category(self, node_uuid, category, key, data_type, info):
        '''
        Insert data with a category.

        Args:
            node_uuid (str): UUID of the node
            category (str): Category name
            key (str): Data key
            data_type (str): Type of data
            info (str): Data content

        Returns:
            str: UUID of the inserted data
        '''
        import uuid
        data_uuid = str(uuid.uuid4())
        query = """
            INSERT INTO data_table (UUID, Node_UUID, key, type, info, category)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        self.execute_query(query, (data_uuid, node_uuid, key, data_type, info, category))
        return data_uuid

    def delete_data_by_category(self, node_uuid, category):
        '''
        Delete all data entries for a specific category in a node.

        Args:
            node_uuid (str): UUID of the node
            category (str): Category to delete

        Returns:
            int: Number of entries deleted
        '''
        query = """
            DELETE FROM data_table
            WHERE Node_UUID = ? AND category = ?
        """
        self.cursor.execute(query, (node_uuid, category))
        deleted_count = self.cursor.rowcount
        self.conn.commit()
        return deleted_count

    def increment_node_counter(self, node_uuid):
        '''
        Increment the insertion_count for a node.

        Args:
            node_uuid (str): UUID of the node

        Returns:
            None
        '''
        # Try to insert first, if exists then update
        query_insert = """
            INSERT OR IGNORE INTO node_counters (node_uuid, insertion_count)
            VALUES (?, 1)
        """
        self.execute_query(query_insert, (node_uuid,))

        query_update = """
            UPDATE node_counters
            SET insertion_count = insertion_count + 1
            WHERE node_uuid = ? AND insertion_count > 0
        """
        self.execute_query(query_update, (node_uuid,))

    def get_node_counter(self, node_uuid):
        '''
        Get the current insertion_count for a node.

        Args:
            node_uuid (str): UUID of the node

        Returns:
            int: Current insertion count (0 if not found)
        '''
        query = """
            SELECT insertion_count
            FROM node_counters
            WHERE node_uuid = ?
        """
        result = self.execute_query(query, (node_uuid,))
        return result[0][0] if result else 0

    def reset_node_counter(self, node_uuid):
        '''
        Reset counter to 0 and update last_cleanup timestamp.

        Args:
            node_uuid (str): UUID of the node

        Returns:
            None
        '''
        from datetime import datetime
        timestamp = datetime.now().isoformat()

        query = """
            INSERT OR REPLACE INTO node_counters (node_uuid, insertion_count, last_cleanup)
            VALUES (?, 0, ?)
        """
        self.execute_query(query, (node_uuid, timestamp))

    def get_nodes_needing_cleanup(self, threshold):
        '''
        Get list of node_uuids where insertion_count >= threshold.

        Args:
            threshold (int): Insertion count threshold

        Returns:
            list: List of node UUIDs needing cleanup
        '''
        query = """
            SELECT node_uuid
            FROM node_counters
            WHERE insertion_count >= ?
        """
        results = self.execute_query(query, (threshold,))
        return [row[0] for row in results]

    # ==================== GRAPH STRUCTURE METHODS ====================

    def create_node(self, metadata, parent_uuid=None):
        '''
        Create a new node with the given metadata.

        Args:
            metadata (str): Metadata/name for the node
            parent_uuid (str, optional): UUID of parent node (None for root-level)

        Returns:
            str: UUID of the newly created node
        '''
        import uuid
        import json
        from datetime import datetime

        node_uuid = str(uuid.uuid4())
        current_time = datetime.now().isoformat()
        children_uuid_arr = json.dumps([])

        query = """
            INSERT INTO node_table (UUID, Metadata, created, last_modified, parent_uuid, children_uuid_arr)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        self.execute_query(query, (node_uuid, metadata, current_time, current_time, parent_uuid, children_uuid_arr))
        return node_uuid

    def add_child_to_node(self, parent_uuid, child_uuid):
        '''
        Add a child UUID to a parent node's children array.

        Args:
            parent_uuid (str): UUID of the parent node
            child_uuid (str): UUID of the child node to add

        Returns:
            bool: True on success, False on failure
        '''
        import json
        from datetime import datetime

        try:
            # Get current children array
            node = self.get_node_by_id(parent_uuid)
            if node is None:
                return False

            children = json.loads(node[5]) if node[5] else []
            if child_uuid not in children:
                children.append(child_uuid)

            # Update parent node
            current_time = datetime.now().isoformat()
            query = """
                UPDATE node_table
                SET children_uuid_arr = ?, last_modified = ?
                WHERE UUID = ?
            """
            self.execute_query(query, (json.dumps(children), current_time, parent_uuid))
            return True
        except Exception:
            return False

    def remove_child_from_node(self, parent_uuid, child_uuid):
        '''
        Remove a child UUID from a parent node's children array.

        Args:
            parent_uuid (str): UUID of the parent node
            child_uuid (str): UUID of the child node to remove

        Returns:
            bool: True if child was found and removed, False otherwise
        '''
        import json
        from datetime import datetime

        try:
            # Get current children array
            node = self.get_node_by_id(parent_uuid)
            if node is None:
                return False

            children = json.loads(node[5]) if node[5] else []
            if child_uuid not in children:
                return False

            children.remove(child_uuid)

            # Update parent node
            current_time = datetime.now().isoformat()
            query = """
                UPDATE node_table
                SET children_uuid_arr = ?, last_modified = ?
                WHERE UUID = ?
            """
            self.execute_query(query, (json.dumps(children), current_time, parent_uuid))
            return True
        except Exception:
            return False

    def update_node_parent(self, node_uuid, new_parent_uuid):
        '''
        Update a node's parent, handling all relationship updates.

        Args:
            node_uuid (str): UUID of the node to move
            new_parent_uuid (str): UUID of the new parent node

        Returns:
            bool: True on success, False on failure
        '''
        import json
        from datetime import datetime

        try:
            # Get the node's current parent
            node = self.get_node_by_id(node_uuid)
            if node is None:
                return False

            old_parent_uuid = node[4]
            current_time = datetime.now().isoformat()

            # Remove from old parent's children (if it has one)
            if old_parent_uuid:
                self.remove_child_from_node(old_parent_uuid, node_uuid)

            # Add to new parent's children (if provided)
            if new_parent_uuid:
                self.add_child_to_node(new_parent_uuid, node_uuid)

            # Update the node's parent_uuid
            query = """
                UPDATE node_table
                SET parent_uuid = ?, last_modified = ?
                WHERE UUID = ?
            """
            self.execute_query(query, (new_parent_uuid, current_time, node_uuid))
            return True
        except Exception:
            return False

    def update_node_metadata(self, node_uuid, new_metadata):
        '''
        Update a node's metadata field.

        Args:
            node_uuid (str): UUID of the node
            new_metadata (str): New metadata value

        Returns:
            bool: True on success, False on failure
        '''
        from datetime import datetime

        try:
            current_time = datetime.now().isoformat()
            query = """
                UPDATE node_table
                SET Metadata = ?, last_modified = ?
                WHERE UUID = ?
            """
            self.execute_query(query, (new_metadata, current_time, node_uuid))
            return True
        except Exception:
            return False

    def delete_node(self, node_uuid, cascade=False):
        '''
        Delete a node from the graph.

        Args:
            node_uuid (str): UUID of the node to delete
            cascade (bool): If True, delete all descendants. If False, fail if node has children.

        Returns:
            bool: True on success, False on failure
        '''
        import json

        try:
            node = self.get_node_by_id(node_uuid)
            if node is None:
                return False

            children = json.loads(node[5]) if node[5] else []

            # If has children and not cascading, fail
            if children and not cascade:
                return False

            # Cascade delete children first
            if cascade:
                for child_uuid in children:
                    self.delete_node(child_uuid, cascade=True)

            # Remove from parent's children array
            parent_uuid = node[4]
            if parent_uuid:
                self.remove_child_from_node(parent_uuid, node_uuid)

            # Delete associated data
            query_data = "DELETE FROM data_table WHERE Node_UUID = ?"
            self.execute_query(query_data, (node_uuid,))

            # Delete associated actions
            query_actions = "DELETE FROM action_table WHERE Node_UUID = ?"
            self.execute_query(query_actions, (node_uuid,))

            # Delete the node itself
            query_node = "DELETE FROM node_table WHERE UUID = ?"
            self.execute_query(query_node, (node_uuid,))

            return True
        except Exception:
            return False

    def get_node_depth(self, node_uuid):
        '''
        Get the depth of a node in the tree (root = 0).

        Args:
            node_uuid (str): UUID of the node

        Returns:
            int: Depth of the node (0 for root, -1 if node not found)
        '''
        depth = 0
        current_uuid = node_uuid

        while current_uuid:
            node = self.get_node_by_id(current_uuid)
            if node is None:
                return -1

            parent_uuid = node[4]
            if parent_uuid is None:
                # Reached root
                return depth

            depth += 1
            current_uuid = parent_uuid

        return depth

    def get_siblings(self, node_uuid):
        '''
        Get all sibling nodes (nodes with the same parent).

        Args:
            node_uuid (str): UUID of the node

        Returns:
            list: List of node tuples for siblings (excludes the node itself)
        '''
        import json

        node = self.get_node_by_id(node_uuid)
        if node is None:
            return []

        parent_uuid = node[4]
        if parent_uuid is None:
            # Root node has no siblings
            return []

        parent_node = self.get_node_by_id(parent_uuid)
        if parent_node is None:
            return []

        children = json.loads(parent_node[5]) if parent_node[5] else []
        siblings = []

        for child_uuid in children:
            if child_uuid != node_uuid:
                sibling = self.get_node_by_id(child_uuid)
                if sibling:
                    siblings.append(sibling)

        return siblings

    def move_data_between_nodes(self, from_node_uuid, to_node_uuid, category=None):
        '''
        Move data entries from one node to another.

        Args:
            from_node_uuid (str): Source node UUID
            to_node_uuid (str): Destination node UUID
            category (str, optional): If specified, only move data in this category

        Returns:
            int: Number of entries moved
        '''
        if category:
            # Count entries to move
            count_query = """
                SELECT COUNT(*) FROM data_table
                WHERE Node_UUID = ? AND category = ?
            """
            result = self.execute_query(count_query, (from_node_uuid, category))
            count = result[0][0] if result else 0

            # Move entries
            query = """
                UPDATE data_table
                SET Node_UUID = ?
                WHERE Node_UUID = ? AND category = ?
            """
            self.execute_query(query, (to_node_uuid, from_node_uuid, category))
        else:
            # Count all entries
            count_query = """
                SELECT COUNT(*) FROM data_table
                WHERE Node_UUID = ?
            """
            result = self.execute_query(count_query, (from_node_uuid,))
            count = result[0][0] if result else 0

            # Move all entries
            query = """
                UPDATE data_table
                SET Node_UUID = ?
                WHERE Node_UUID = ?
            """
            self.execute_query(query, (to_node_uuid, from_node_uuid))

        return count

    def move_actions_between_nodes(self, from_node_uuid, to_node_uuid):
        '''
        Move all actions from one node to another.

        Args:
            from_node_uuid (str): Source node UUID
            to_node_uuid (str): Destination node UUID

        Returns:
            int: Number of actions moved
        '''
        # Count actions to move
        count_query = """
            SELECT COUNT(*) FROM action_table
            WHERE Node_UUID = ?
        """
        result = self.execute_query(count_query, (from_node_uuid,))
        count = result[0][0] if result else 0

        # Move actions
        query = """
            UPDATE action_table
            SET Node_UUID = ?
            WHERE Node_UUID = ?
        """
        self.execute_query(query, (to_node_uuid, from_node_uuid))

        return count

    # ========================
    # Action History Methods
    # ========================

    def insert_action_history(
        self,
        action_uuid,
        action_type,
        action_data=None,
        node_uuid=None,
        status="completed",
        result=None,
        error_message=None,
        duration_ms=None
    ):
        """
        Insert a record into the action_history table.
        
        Args:
            action_uuid: Unique identifier for the action
            action_type: Type of action (e.g., "calendar_create", "email_send")
            action_data: JSON string with action parameters
            node_uuid: Associated node UUID (optional)
            status: "completed", "failed", or "pending"
            result: JSON string with action output
            error_message: Error details if failed
            duration_ms: Execution time in milliseconds
        
        Returns:
            The inserted row ID
        """
        query = """
            INSERT INTO action_history 
            (action_uuid, action_type, action_data, node_uuid, status, result, error_message, duration_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.execute_query(
            query,
            (action_uuid, action_type, action_data, node_uuid, status, result, error_message, duration_ms)
        )
        return self.cursor.lastrowid

    def get_action_history(self, limit=50, offset=0, status=None, action_type=None):
        """
        Retrieve action history records.
        
        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip (for pagination)
            status: Filter by status (optional)
            action_type: Filter by action type (optional)
        
        Returns:
            List of action history records as tuples
        """
        query = """
            SELECT id, action_uuid, action_type, action_data, creation_timestamp, 
                   node_uuid, status, result, error_message, duration_ms
            FROM action_history
            WHERE 1=1
        """
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        if action_type:
            query += " AND action_type = ?"
            params.append(action_type)
        
        query += " ORDER BY creation_timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        return self.execute_query(query, tuple(params))

    def get_action_history_by_uuid(self, action_uuid):
        """
        Get a specific action history record by action_uuid.
        
        Args:
            action_uuid: The action UUID to look up
        
        Returns:
            Action history record or None
        """
        query = """
            SELECT id, action_uuid, action_type, action_data, creation_timestamp,
                   node_uuid, status, result, error_message, duration_ms
            FROM action_history
            WHERE action_uuid = ?
            ORDER BY creation_timestamp DESC
            LIMIT 1
        """
        result = self.execute_query(query, (action_uuid,))
        return result[0] if result else None

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

        # In-memory storage for mock data
        self.actions_data = []  # List of tuples: (uuid, action_name, action_plan, action_prompt, node_uuid, last_selected)
        self.data_entries = []  # List of tuples: (uuid, node_uuid, key, data_type, info, category)
        self.node_counters = {}  # Dict: node_uuid -> {insertion_count: int, last_cleanup: str}
        
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

    def get_node_by_id(self, node_uuid):
        '''Get node by UUID from test graph data.'''
        for node in self.nodes_data:
            if node[0] == node_uuid:
                # Return tuple: (UUID, Metadata, created, last_modified, parent_uuid, children_uuid_arr)
                return (node[0], node[1], node[2], node[3], node[4], node[5])
        return None

    # ==================== ACTION METHODS ====================

    def add_action(self, node_uuid, action_name, action_plan=None, action_prompt=None, last_selected=None):
        '''Add an action to the in-memory store.'''
        import uuid
        action_uuid = str(uuid.uuid4())
        action_tuple = (action_uuid, action_name, action_plan, action_prompt, node_uuid, last_selected)
        self.actions_data.append(action_tuple)
        return action_uuid

    def update_action(self, action_uuid, action_name, action_plan, action_prompt):
        '''Update an existing action's fields.'''
        for i, action in enumerate(self.actions_data):
            if action[0] == action_uuid:
                # Replace with updated tuple
                self.actions_data[i] = (action_uuid, action_name, action_plan, action_prompt, action[4], action[5])
                return True
        return False

    def update_action_last_selected(self, action_uuid, timestamp=None):
        '''Update the last_selected timestamp for an action.'''
        if timestamp is None:
            from datetime import datetime
            timestamp = datetime.now().isoformat()

        for i, action in enumerate(self.actions_data):
            if action[0] == action_uuid:
                # Replace with updated tuple
                self.actions_data[i] = (action[0], action[1], action[2], action[3], action[4], timestamp)
                return True
        return False

    def get_action_by_id(self, action_uuid):
        '''Retrieve an action by UUID.'''
        for action in self.actions_data:
            if action[0] == action_uuid:
                # Return tuple: (UUID, Action_name, Action_plan, Action_prompt, Node_UUID)
                return (action[0], action[1], action[2], action[3], action[4])
        return None

    def get_actions_for_node(self, node_uuid, order_by_last_selected=True):
        '''Get all actions for a node, optionally sorted by last_selected.'''
        actions = [action for action in self.actions_data if action[4] == node_uuid]

        if order_by_last_selected:
            # Sort by last_selected DESC, NULLs last
            # Use (x[5] is not None, x[5]) as key:
            # - Non-NULL values: (True, date_string) - sorts by date DESC when reversed
            # - NULL values: (False, None) - sorts last when reversed
            actions.sort(key=lambda x: (x[5] is not None, x[5] if x[5] else ''), reverse=True)

        return actions

    def get_recent_actions_for_node(self, node_uuid, limit=4):
        '''Get the N most recently selected actions for a node.'''
        # Filter actions with non-NULL last_selected
        actions = [action for action in self.actions_data
                  if action[4] == node_uuid and action[5] is not None]

        # Sort by last_selected DESC
        actions.sort(key=lambda x: x[5], reverse=True)

        return actions[:limit]

    def delete_stale_actions(self, node_uuid, days_threshold=3):
        '''Delete actions where last_selected is older than threshold days.'''
        from datetime import datetime, timedelta
        threshold_date = (datetime.now() - timedelta(days=days_threshold)).isoformat()

        # Find actions to delete
        initial_count = len(self.actions_data)
        self.actions_data = [
            action for action in self.actions_data
            if not (action[4] == node_uuid and
                   action[5] is not None and
                   action[5] < threshold_date)
        ]

        deleted_count = initial_count - len(self.actions_data)
        return deleted_count

    # ==================== DATA METHODS ====================

    def add_data(self, node_uuid, key, data_type, info, category=None):
        '''Add data entry to the in-memory store.'''
        import uuid
        data_uuid = str(uuid.uuid4())
        data_tuple = (data_uuid, node_uuid, key, data_type, info, category)
        self.data_entries.append(data_tuple)
        return data_uuid

    def add_data_with_category(self, node_uuid, category, key, data_type, info):
        '''Add data with a specific category.'''
        return self.add_data(node_uuid, key, data_type, info, category)

    def get_data_for_node(self, node_uuid):
        '''Get all data entries for a node.'''
        return [data for data in self.data_entries if data[1] == node_uuid]

    def get_data_for_node_by_category(self, node_uuid):
        '''Get data for a node grouped by category.'''
        grouped = {}
        for data in self.data_entries:
            if data[1] == node_uuid:
                category = data[5] if data[5] else "uncategorized"
                if category not in grouped:
                    grouped[category] = []
                grouped[category].append(data)
        return grouped

    def get_categories_for_node(self, node_uuid):
        '''Get list of unique category names for a node.'''
        categories = set()
        for data in self.data_entries:
            if data[1] == node_uuid and data[5] is not None:
                categories.add(data[5])
        return list(categories)

    def delete_data_by_category(self, node_uuid, category):
        '''Delete all data entries for a specific category in a node.'''
        initial_count = len(self.data_entries)
        self.data_entries = [
            data for data in self.data_entries
            if not (data[1] == node_uuid and data[5] == category)
        ]
        deleted_count = initial_count - len(self.data_entries)
        return deleted_count

    # ==================== NODE COUNTER METHODS ====================

    def increment_node_counter(self, node_uuid):
        '''Increment the insertion_count for a node.'''
        if node_uuid not in self.node_counters:
            self.node_counters[node_uuid] = {'insertion_count': 0, 'last_cleanup': None}
        self.node_counters[node_uuid]['insertion_count'] += 1
        return self.node_counters[node_uuid]['insertion_count']

    def get_node_counter(self, node_uuid):
        '''Get the current insertion_count for a node.'''
        if node_uuid in self.node_counters:
            return self.node_counters[node_uuid]['insertion_count']
        return 0

    def reset_node_counter(self, node_uuid):
        '''Reset counter to 0 and update last_cleanup timestamp.'''
        from datetime import datetime
        timestamp = datetime.now().isoformat()
        self.node_counters[node_uuid] = {'insertion_count': 0, 'last_cleanup': timestamp}
        return True

    def get_nodes_needing_cleanup(self, threshold):
        '''Get list of node_uuids where insertion_count >= threshold.'''
        nodes = []
        for node_uuid, data in self.node_counters.items():
            if data['insertion_count'] >= threshold:
                nodes.append(node_uuid)
        return nodes

    # ==================== GRAPH STRUCTURE METHODS ====================

    def create_node(self, metadata, parent_uuid=None):
        '''Create a new node with the given metadata.'''
        import uuid
        import json
        from datetime import datetime

        node_uuid = str(uuid.uuid4())
        current_time = datetime.now().isoformat()
        children_uuid_arr = json.dumps([])

        # Create node tuple matching the structure of nodes_data
        node_tuple = (node_uuid, metadata, current_time, current_time, parent_uuid, children_uuid_arr, None)
        self.nodes_data.append(node_tuple)

        # Add to node_uuids dict for easy lookup (using metadata as key if unique)
        self.node_uuids[metadata.lower().replace(' ', '_')] = node_uuid

        return node_uuid

    def add_child_to_node(self, parent_uuid, child_uuid):
        '''Add a child UUID to a parent node's children array.'''
        import json
        from datetime import datetime

        for i, node in enumerate(self.nodes_data):
            if node[0] == parent_uuid:
                children = json.loads(node[5]) if node[5] else []
                if child_uuid not in children:
                    children.append(child_uuid)

                current_time = datetime.now().isoformat()
                # Update node tuple
                self.nodes_data[i] = (node[0], node[1], node[2], current_time, node[4], json.dumps(children), node[6])
                return True
        return False

    def remove_child_from_node(self, parent_uuid, child_uuid):
        '''Remove a child UUID from a parent node's children array.'''
        import json
        from datetime import datetime

        for i, node in enumerate(self.nodes_data):
            if node[0] == parent_uuid:
                children = json.loads(node[5]) if node[5] else []
                if child_uuid not in children:
                    return False

                children.remove(child_uuid)
                current_time = datetime.now().isoformat()
                # Update node tuple
                self.nodes_data[i] = (node[0], node[1], node[2], current_time, node[4], json.dumps(children), node[6])
                return True
        return False

    def update_node_parent(self, node_uuid, new_parent_uuid):
        '''Update a node's parent, handling all relationship updates.'''
        import json
        from datetime import datetime

        # Find the node
        node_index = None
        old_parent_uuid = None
        for i, node in enumerate(self.nodes_data):
            if node[0] == node_uuid:
                node_index = i
                old_parent_uuid = node[4]
                break

        if node_index is None:
            return False

        # Remove from old parent's children
        if old_parent_uuid:
            self.remove_child_from_node(old_parent_uuid, node_uuid)

        # Add to new parent's children
        if new_parent_uuid:
            self.add_child_to_node(new_parent_uuid, node_uuid)

        # Update the node's parent_uuid
        current_time = datetime.now().isoformat()
        node = self.nodes_data[node_index]
        self.nodes_data[node_index] = (node[0], node[1], node[2], current_time, new_parent_uuid, node[5], node[6])
        return True

    def update_node_metadata(self, node_uuid, new_metadata):
        '''Update a node's metadata field.'''
        from datetime import datetime

        for i, node in enumerate(self.nodes_data):
            if node[0] == node_uuid:
                current_time = datetime.now().isoformat()
                self.nodes_data[i] = (node[0], new_metadata, node[2], current_time, node[4], node[5], node[6])
                return True
        return False

    def delete_node(self, node_uuid, cascade=False):
        '''Delete a node from the graph.'''
        import json

        # Find the node
        node_index = None
        node_data = None
        for i, node in enumerate(self.nodes_data):
            if node[0] == node_uuid:
                node_index = i
                node_data = node
                break

        if node_index is None:
            return False

        children = json.loads(node_data[5]) if node_data[5] else []

        # If has children and not cascading, fail
        if children and not cascade:
            return False

        # Cascade delete children first
        if cascade:
            for child_uuid in list(children):  # Use list() to avoid modification during iteration
                self.delete_node(child_uuid, cascade=True)

        # Remove from parent's children array
        parent_uuid = node_data[4]
        if parent_uuid:
            self.remove_child_from_node(parent_uuid, node_uuid)

        # Delete associated data
        self.data_entries = [d for d in self.data_entries if d[1] != node_uuid]

        # Delete associated actions
        self.actions_data = [a for a in self.actions_data if a[4] != node_uuid]

        # Delete the node itself - need to find it again as index may have changed
        for i, node in enumerate(self.nodes_data):
            if node[0] == node_uuid:
                self.nodes_data.pop(i)
                break

        return True

    def get_node_depth(self, node_uuid):
        '''Get the depth of a node in the tree (root = 0).'''
        depth = 0
        current_uuid = node_uuid

        while current_uuid:
            node = self.get_node_by_id(current_uuid)
            if node is None:
                return -1

            parent_uuid = node[4]
            if parent_uuid is None:
                # Reached root
                return depth

            depth += 1
            current_uuid = parent_uuid

        return depth

    def get_siblings(self, node_uuid):
        '''Get all sibling nodes (nodes with the same parent).'''
        import json

        node = self.get_node_by_id(node_uuid)
        if node is None:
            return []

        parent_uuid = node[4]
        if parent_uuid is None:
            # Root node has no siblings
            return []

        parent_node = self.get_node_by_id(parent_uuid)
        if parent_node is None:
            return []

        children = json.loads(parent_node[5]) if parent_node[5] else []
        siblings = []

        for child_uuid in children:
            if child_uuid != node_uuid:
                sibling = self.get_node_by_id(child_uuid)
                if sibling:
                    siblings.append(sibling)

        return siblings

    def move_data_between_nodes(self, from_node_uuid, to_node_uuid, category=None):
        '''Move data entries from one node to another.'''
        count = 0
        for i, data in enumerate(self.data_entries):
            if data[1] == from_node_uuid:
                if category is None or data[5] == category:
                    # Update the node_uuid (index 1) in the tuple
                    self.data_entries[i] = (data[0], to_node_uuid, data[2], data[3], data[4], data[5])
                    count += 1
        return count

    def move_actions_between_nodes(self, from_node_uuid, to_node_uuid):
        '''Move all actions from one node to another.'''
        count = 0
        for i, action in enumerate(self.actions_data):
            if action[4] == from_node_uuid:
                # Update the node_uuid (index 4) in the tuple
                self.actions_data[i] = (action[0], action[1], action[2], action[3], to_node_uuid, action[5])
                count += 1
        return count


# The main method for this adds the testing data into the graph
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
