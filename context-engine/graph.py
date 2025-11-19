import os
import json
import uuid
import sys
from datetime import datetime
import google.generativeai as genai
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from graph_dao import GraphDAO, TestGraphDAO
from anthropic import Anthropic

# Add parent directory to path to import LLMGraph
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from LLMGraph import run_graph

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

    def trigger_action(self, action_uuid):
        """
        Trigger an action by its UUID, gathering all relevant context data from the node 
        and its ancestors into a single concatenated string.
        
        Args:
            action_uuid (str): UUID of the action to trigger
            
        Returns:
            tuple: (action_text, collected_data_string) - The action description and all collected data as a single string
        """
        # Get the action from the database
        action_data = self.dao.get_action_by_id(action_uuid)
        if not action_data:
            print(f"Error: Action with UUID {action_uuid} not found")
            return None, None
        
        action_uuid_db, action_text, node_uuid = action_data
        print(f"Found action: {action_text}")
        print(f"Associated with node UUID: {node_uuid}")
        
        # Collect all data into a list to be concatenated later
        data_parts = []
        data_parts.append(f"ACTION TO EXECUTE: {action_text}\n")
        data_parts.append("="*60 + "\n")
        
        def collect_ancestor_data(current_node_uuid, depth=0):
            """Recursively collect data from a node and all its ancestors"""
            if not current_node_uuid:
                return
            
            # Get data for current node
            node_data_entries = self.dao.get_data_for_node(current_node_uuid)
            
            # Get node info to find parent
            node_info = self.dao.get_node_by_id(current_node_uuid)
            if not node_info:
                return
            
            node_uuid_db, metadata, created, last_modified, parent_uuid, children_uuid_arr = node_info
            
            # Add node metadata to the string
            indent = "  " * depth
            if metadata:
                data_parts.append(f"\n{indent}NODE: {metadata}\n")
                data_parts.append(f"{indent}NODE_UUID: {current_node_uuid}\n")
            
            # Add all data entries for this node
            if node_data_entries:
                data_parts.append(f"{indent}DATA ENTRIES:\n")
                for data_entry in node_data_entries:
                    data_uuid, data_node_uuid, key, data_type, info = data_entry
                    # Use key if available, otherwise use data_uuid
                    data_key = key if key else f"data_{data_uuid}"
                    data_parts.append(f"{indent}  - KEY: {data_key}\n")
                    data_parts.append(f"{indent}    TYPE: {data_type}\n")
                    data_parts.append(f"{indent}    INFO: {info}\n")
            
            # Recursively collect from parent
            if parent_uuid:
                data_parts.append(f"{indent}PARENT CONTEXT:\n")
                collect_ancestor_data(parent_uuid, depth + 1)
        
        # Start collection from the action's node
        collect_ancestor_data(node_uuid)
        
        # Concatenate all parts into a single string
        collected_data_string = "".join(data_parts)
        
        print(f"\n{'='*60}")
        print(f"Collected context data (first 1000 chars):")
        print(collected_data_string[:1000])
        if len(collected_data_string) > 1000:
            print("...")
        print(f"Total data length: {len(collected_data_string)} characters")
        print(f"{'='*60}\n")
        
        # ================================================================
        # SPACE FOR ACTION EXECUTION
        # ================================================================
        # TODO: Add your action execution logic here
        # You can call external functions/modules to perform the actual action
        # 
        # Example structure:
        # if "send email" in action_text.lower():
        #     from email_handler import send_email
        #     result = send_email(action_text, collected_data_string)
        # elif "schedule meeting" in action_text.lower():
        #     from calendar_handler import schedule_meeting
        #     result = schedule_meeting(action_text, collected_data_string)
        # 
        # For now, just print what would be executed
        print("ACTION EXECUTION PLACEHOLDER")
        print(f"🚀 [graph.py] About to call run_graph() with action_text: {action_text[:100]}...")
        print(f"🚀 [graph.py] Data length being passed: {len(collected_data_string)} characters")
        run_graph(action_text, collected_data_string)
        print(f"✅ [graph.py] run_graph() call completed")
        
        print(f"Would execute: {action_text}")
        print(f"With context data string of length: {len(collected_data_string)}")
        # ================================================================
        
        return action_text, collected_data_string



        

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
        similarity_scores = {}
        
        for node_uuid, node in self.nodes.items():
            if node.embedding is not None:
                try:
                    # Calculate cosine similarity
                    similarity = cosine_similarity(screen_embedding, node.embedding)[0][0]
                    similarity_scores[node.metadata] = similarity
                    
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_node = node
                        
                except Exception as e:
                    print(f"Error calculating similarity for node {node_uuid}: {e}")
                    continue
        
        print(f"🔍 traverse() - Screen input: '{screen[:100]}...'")
        print(f"🔍 traverse() - Top 5 similarity scores:")
        sorted_scores = sorted(similarity_scores.items(), key=lambda x: x[1], reverse=True)[:5]
        for node_name, score in sorted_scores:
            print(f"   - {node_name}: {score:.4f}")
        
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
            tuple: (action_name, action_plan, action_prompt, action_uuid) - The suggested action details and UUID
        """
        # Find the most relevant node using traverse
        node = self.traverse(summary)
        print(f"DEBUG learn(): traverse() returned node={node}")

        # Initialize variables for return
        action_name = None
        action_plan = None
        action_prompt = None
        action_uuid = None

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
            For example the action prompt could be: "Send an email to Ritesh - rneela@wisc.edu confirming the meeting at 10am. Schedule this meeting on my calendar from 10am - 11am"

            Note that when an action is performed, you will be given all context so don't worry about providing too much context
            Focus on being clear what action is to be performed

            The action name is a very high level description of what the action is that will be displayed on the UI. It should be very short and summarize what the action will do.
           
            When the user hovers over this action, the entire action plan will be displayed. this should be a more detailed description of what the action will do. For example if you're sending
            an email, this action plan should contain the exact email that will be sent.

            The actions prompt is an even more detailed description of what the action will do. It should be a more detailed description of what the action will do. This is what will be
            send to the langraph to perform the action via MCP calls. It's fine if the action plan and action prompt are of similar length but keep any information that the user doesn't really need to see
            but is necessary to take the action over here.

            here is an example of the output:
            {{
                "action_name": "Schedule Interview with Ritesh",
                "action_plan": "Send email to Ritesh (rneela@wisc.edu) confirming interview on Monday 11/04 at 12:30pm CDT. Add calendar event for 12:30pm-1:30pm with meeting link.",
                "action_prompt": "Schedule an interview with candidate Ritesh Neela (rneela@wisc.edu) for the Software Engineering Intern - Summer 2026 position. Based on his availability email, schedule the interview for Monday, November 4th at 12:30pm Central Daylight Time. Send him a confirmation email with the interview details and create a calendar event from 12:30pm-1:30pm. Include a Google Meet link in the calendar invite. The interviewer should be John Smith from the engineering team."
            }}

            Output in the following format as a JSON object:
            {{
                "action_name": "<action_name>",
                "action_plan": "<action_plan>"
                "action_prompt": "<action_prompt>"
            }}

        """
        
        # Call Claude Sonnet 4.5 with the action prompt
        try:
            print(f"DEBUG learn(): Creating Anthropic client...")
            anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            print(f"DEBUG learn(): Sending prompt to Claude...")
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": ACTION_CREATION_PROMPT}
                ]
            )
            llm_response = response.content[0].text
            print(f"\n{'='*60}")
            print(f"Raw LLM Response from Claude:")
            print(f"{llm_response}")
            print(f"{'='*60}\n")
            
            # Parse the JSON response from the LLM
            try:
                # Extract JSON from the response (handle potential markdown code blocks)
                import re
                json_match = re.search(r'\{[^{}]*"action_name"[^{}]*\}', llm_response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    action_data = json.loads(json_str)
                    action_name = action_data.get("action_name")
                    action_plan = action_data.get("action_plan")
                    action_prompt = action_data.get("action_prompt")
                    
                    print(f"Parsed action_name: {action_name}")
                    print(f"Parsed action_plan: {action_plan}")
                    print(f"Parsed action_prompt: {action_prompt}")
                else:
                    print("Warning: Could not find valid JSON in LLM response")
                    action_name = None
                    action_plan = None
                    action_prompt = None
            except json.JSONDecodeError as json_error:
                print(f"Error parsing JSON from LLM response: {json_error}")
                action_name = None
                action_plan = None
                action_prompt = None
            
            # Insert the suggested action into the database if it was generated successfully
            if action_name and node:
                print(f"DEBUG learn(): action_name and node are valid, inserting into DB...")
                try:
                    action_uuid = self.dao.add_action(
                        node_uuid=node.node_uuid,
                        action_name=action_name,
                        action_plan=action_plan,
                        action_prompt=action_prompt
                    )
                    print(f"Successfully inserted action into database with UUID: {action_uuid}")
                except Exception as action_error:
                    print(f"Error inserting action into database: {action_error}")
                    action_uuid = None
            else:
                print(f"DEBUG learn(): Skipping insertion - action_name={action_name}, node={node}")
        except Exception as e:
            print(f"Error calling Claude API: {e}")
            import traceback
            traceback.print_exc()
            action_name = None
            action_plan = None
            action_prompt = None
            action_uuid = None
        
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
            return action_name, action_plan, action_prompt, action_uuid
        except Exception as e:
            print(f"Error inserting data: {e}")
            return action_name, action_plan, action_prompt, action_uuid
        

    
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

# Initialize tree when module is imported
# Uncomment the lines below to initialize the tree on import
# print("Initializing graph from database...")
# tree = Tree("../context-engine/graph.db")
# print("Graph structure:")
# print(tree)