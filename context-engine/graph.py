import os
import json
import uuid
import sys
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from graph_dao import GraphDAO, TestGraphDAO
from model_interface import ModelFactory

# Add parent directory to path to import LLMGraph
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from LLMGraph import run_graph

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

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
    def __init__(self, db_path, config_path=None):
        self.nodes = {}  # Dictionary to store nodes by UUID for easy lookup
        self.root = None

        self.dao = GraphDAO(db_path)

        # Initialize model factory with configuration
        try:
            self.model_factory = ModelFactory(config_path)
            self.embedding_model = self.model_factory.get_embedding_model("embedding")
            self.traversal_model = self.model_factory.get_chat_model("traversal")
            self.action_model = self.model_factory.get_chat_model("action_creation")
            self.condensation_model = self.model_factory.get_chat_model("data_condensation")
        except Exception as e:
            print(f"Warning: Failed to initialize model factory: {e}")
            print("Models will not be available for this session.")
            self.model_factory = None
            self.embedding_model = None
            self.traversal_model = None
            self.action_model = None
            self.condensation_model = None

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
        
        action_uuid_db, action_name, action_prompt, node_uuid = action_data
        
        # Use action_prompt if available, otherwise fall back to action_name
        action_text = action_prompt if action_prompt else action_name
        
        print(f"Found action: {action_name}")
        print(f"Action prompt: {action_text[:200]}..." if len(action_text) > 200 else f"Action prompt: {action_text}")
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
        
        # Run the graph and capture the result
        result = asyncio.run(run_graph(action_text, collected_data_string))
        print(f"✅ [graph.py] run_graph() call completed")
        print(f"📊 [graph.py] Result from run_graph: {result}")
        
        print(f"Would execute: {action_text}")
        print(f"With context data string of length: {len(collected_data_string)}")
        # ================================================================
        
        return action_text, collected_data_string, result



        

    def vectorize_text(self, text):
        """
        Vectorize a piece of text using the configured embedding model.
        
        Args:
            text (str): The text to vectorize
            
        Returns:
            numpy.ndarray: The embedding vector, or None if vectorization fails
        """
        if not self.embedding_model or not text:
            return None
            
        try:
            return self.embedding_model.embed(text)
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
        # prompt = f"screen: {screen}\nselected_node: {self.get_parent_metadata(best_node)}"
        # if self.traversal_model:
        #     response = self.traversal_model.generate(prompt)

        return best_node

    def _generate_learning_prompt(self, node, summary, existing_actions, existing_categories):
        """
        Generate a prompt for the LLM to decide on action and data insertion.

        Args:
            node (Node): The current node we're learning into
            summary (str): Description of what the user is doing on screen
            existing_actions (list): List of action tuples from get_actions_for_node()
            existing_categories (list): List of category names from get_categories_for_node()

        Returns:
            str: The prompt to send to the LLM
        """
        # Get metadata chain for context
        metadata_chain = self.get_parent_metadata(node)

        # Format existing actions
        actions_text = ""
        if existing_actions:
            actions_text = "EXISTING ACTIONS for this node:\n"
            for idx, action in enumerate(existing_actions, 1):
                uuid, name, plan, prompt, node_uuid, last_selected = action
                actions_text += f"{idx}. UUID: {uuid}\n"
                actions_text += f"   Name: {name}\n"
                actions_text += f"   Plan: {plan or 'N/A'}\n"
                actions_text += f"   Last Selected: {last_selected or 'Never'}\n\n"
        else:
            actions_text = "EXISTING ACTIONS: None - this node has no actions yet.\n"

        # Format existing categories
        categories_text = ""
        if existing_categories:
            categories_text = f"EXISTING DATA CATEGORIES: {', '.join(existing_categories)}\n"
        else:
            categories_text = "EXISTING DATA CATEGORIES: None - this node has no data categories yet.\n"

        prompt = f"""{self.BASE_PROMPT}

CURRENT CONTEXT:
Node Path (from root): {metadata_chain}
Current Node: {node.metadata}

{actions_text}
{categories_text}

USER'S CURRENT ACTIVITY:
{summary}

YOUR TASK:
You are an AI Desktop Agent that learns from user behavior and suggests proactive actions.

You have access to:
- User's computer screen (for screen control actions)
- GSuite (Email, Calendar, Docs, Sheets, etc.)
- Ability to define series of tasks

Based on the user's current activity, you must:

1. **ACTION DECISION** - Choose ONE of these three options:

   a) **CREATE** - Generate a completely new action
      - Use when: Current activity represents a new workflow or task type
      - Provide: action_name (short UI display), action_plan (detailed user-facing description), action_prompt (full technical prompt for MCP execution)

   b) **MODIFY** - Update an existing action to better match current context
      - Use when: An existing action is close but needs refinement
      - Provide: action_uuid (from list above), updated action_name, action_plan, action_prompt

   c) **SELECT** - Use an existing action exactly as-is
      - Use when: An existing action perfectly matches the current activity
      - Provide: action_uuid (from list above)

2. **DATA INSERTION** - Extract and categorize relevant information:
   - Condense the screen summary to preserve ONLY relevant information
   - Remove UI noise (cursor positions, visual elements, temporary states)
   - Keep essential context (names, dates, email addresses, decisions, outcomes)
   - Assign data to categories (can use existing or create new ones)
   - Can split data across multiple categories if appropriate

OUTPUT FORMAT - Return ONLY valid JSON with NO markdown formatting:
{{
  "action_decision": {{
    "type": "create" | "modify" | "select",
    "action_uuid": "uuid-here-if-modify-or-select-otherwise-null",
    "action_name": "Short name for UI display (20-40 chars)",
    "action_plan": "Detailed plan shown on hover - exact content of what will happen",
    "action_prompt": "Full technical prompt for MCP orchestration - include all context needed for execution"
  }},
  "data_insertions": [
    {{
      "category": "category_name",
      "is_new_category": true | false,
      "condensed_data": "The actual data to store - detailed but concise"
    }}
  ]
}}

IMPORTANT:
- action_name: Concise UI label (e.g., "Schedule Interview with Ritesh")
- action_plan: User-facing details (e.g., exact email content, meeting times)
- action_prompt: Technical execution details (e.g., full instructions for LangGraph/MCP)
- Output ONLY the JSON object - no explanations, no markdown code blocks
- Ensure all JSON is properly formatted and valid
"""
        return prompt

    def _parse_learning_response(self, response_text):
        """
        Parse the JSON response from the LLM.

        Args:
            response_text (str): Raw response from LLM

        Returns:
            dict: Parsed response with action_decision and data_insertions

        Raises:
            ValueError: If response is not valid JSON or missing required fields
        """
        import re

        # Try to extract JSON from potential markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find raw JSON
            json_match = re.search(r'\{.*"action_decision".*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                raise ValueError(f"Could not find valid JSON in LLM response: {response_text[:200]}")

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in LLM response: {e}\nJSON string: {json_str[:200]}")

        # Validate required fields
        if "action_decision" not in parsed:
            raise ValueError("Missing required field: action_decision")
        if "data_insertions" not in parsed:
            raise ValueError("Missing required field: data_insertions")

        action_decision = parsed["action_decision"]
        if "type" not in action_decision:
            raise ValueError("Missing required field: action_decision.type")

        if action_decision["type"] not in ["create", "modify", "select"]:
            raise ValueError(f"Invalid action type: {action_decision['type']}")

        if action_decision["type"] in ["modify", "select"] and not action_decision.get("action_uuid"):
            raise ValueError(f"action_uuid required for type '{action_decision['type']}'")

        if action_decision["type"] in ["create", "modify"]:
            required = ["action_name", "action_plan", "action_prompt"]
            for field in required:
                if not action_decision.get(field):
                    raise ValueError(f"Missing required field for {action_decision['type']}: action_decision.{field}")

        return parsed

    def learn(self, summary, data, key=None, data_type="text"):
        """
        Learn new information by intelligently managing actions and data insertion.

        Args:
            summary (str): Description of what the user is doing on screen
            data (str): Additional context/data (used in prompt, not stored directly)
            key (str, optional): Deprecated - keys are auto-generated per category
            data_type (str): Deprecated - type determined by LLM

        Returns:
            list: List of up to 4 most recently selected actions (tuples)
        """
        try:
            # 1. Find the relevant node using traverse
            node = self.traverse(summary)
            if node is None:
                print("Warning: Could not find suitable node, using root")
                node = self.root

            print(f"\n{'='*60}")
            print(f"LEARN - Selected Node: {node.metadata} (UUID: {node.node_uuid})")
            print(f"{'='*60}")

            # 2. Gather context
            existing_actions = self.dao.get_actions_for_node(node.node_uuid, order_by_last_selected=True)
            existing_categories = self.dao.get_categories_for_node(node.node_uuid)

            print(f"Existing actions: {len(existing_actions)}")
            print(f"Existing categories: {existing_categories}")

            # 3. Generate and send LLM prompt
            prompt = self._generate_learning_prompt(node, summary, existing_actions, existing_categories)

            if not self.action_model:
                print("Error: Action model not initialized")
                return []
            
            llm_response = self.action_model.generate(prompt)

            print(f"\n{'='*60}")
            print(f"Raw LLM Response:")
            print(f"{llm_response[:500]}...")
            print(f"{'='*60}\n")

            # Parse response
            parsed = self._parse_learning_response(llm_response)

            # 4. Process action decision
            action_decision = parsed["action_decision"]
            action_type = action_decision["type"]
            current_timestamp = datetime.now().isoformat()

            selected_action_uuid = None

            if action_type == "create":
                print(f"Creating new action: {action_decision['action_name']}")
                selected_action_uuid = self.dao.add_action(
                    node_uuid=node.node_uuid,
                    action_name=action_decision["action_name"],
                    action_plan=action_decision["action_plan"],
                    action_prompt=action_decision["action_prompt"],
                    last_selected=current_timestamp
                )
                print(f"Created action UUID: {selected_action_uuid}")

            elif action_type == "modify":
                print(f"Modifying action: {action_decision['action_uuid']}")
                self.dao.update_action(
                    action_uuid=action_decision["action_uuid"],
                    action_name=action_decision["action_name"],
                    action_plan=action_decision["action_plan"],
                    action_prompt=action_decision["action_prompt"]
                )
                self.dao.update_action_last_selected(action_decision["action_uuid"], current_timestamp)
                selected_action_uuid = action_decision["action_uuid"]
                print(f"Modified action UUID: {selected_action_uuid}")

            elif action_type == "select":
                print(f"Selecting existing action: {action_decision['action_uuid']}")
                self.dao.update_action_last_selected(action_decision["action_uuid"], current_timestamp)
                selected_action_uuid = action_decision["action_uuid"]
                print(f"Selected action UUID: {selected_action_uuid}")

            # 5. Process data insertions
            data_insertions = parsed.get("data_insertions", [])
            print(f"\nProcessing {len(data_insertions)} data insertions...")

            for insertion in data_insertions:
                category = insertion["category"]
                condensed_data = insertion["condensed_data"]

                # Generate a unique key for this data entry
                timestamp_key = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
                data_key = f"{category}_{timestamp_key}"

                self.dao.add_data_with_category(
                    node_uuid=node.node_uuid,
                    category=category,
                    key=data_key,
                    data_type="text",
                    info=condensed_data
                )
                print(f"  - Inserted into category '{category}': {condensed_data[:100]}...")

                # Increment node counter for each insertion
                self.dao.increment_node_counter(node.node_uuid)

            # 6. Cleanup stale actions
            deleted_count = self.dao.delete_stale_actions(node.node_uuid, days_threshold=3)
            if deleted_count > 0:
                print(f"\nDeleted {deleted_count} stale actions (>3 days old)")

            # 7. Return recent actions
            recent_actions = self.dao.get_recent_actions_for_node(node.node_uuid, limit=4)
            print(f"\nReturning {len(recent_actions)} recent actions")

            return recent_actions

        except Exception as e:
            print(f"Error in learn(): {e}")
            import traceback
            traceback.print_exc()
            # Return empty list on error - don't crash
            return []

    @staticmethod
    def cleanup_node_data(dao, node_uuid, config_path=None):
        """
        Static method to condense data within a node by category.
        This method operates directly on the database and is designed to be called
        by external cleanup threads.

        Args:
            dao: GraphDAO instance for database operations
            node_uuid (str): UUID of the node to clean up
            config_path (str, optional): Path to model config file. Defaults to repo root.

        Returns:
            bool: True if cleanup succeeded for all categories, False otherwise
        """
        try:
            # Initialize model factory
            model_factory = ModelFactory(config_path)
            condensation_model = model_factory.get_chat_model("data_condensation")
        except Exception as e:
            print(f"Error: Failed to initialize condensation model: {e}")
            return False

        try:
            # Get all data grouped by category
            data_by_category = dao.get_data_for_node_by_category(node_uuid)

            if not data_by_category:
                print(f"No data to clean for node {node_uuid}")
                return False

            print(f"\n{'='*60}")
            print(f"CLEANUP - Node UUID: {node_uuid}")
            print(f"Categories to process: {list(data_by_category.keys())}")
            print(f"{'='*60}")

            all_succeeded = True

            for category, data_entries in data_by_category.items():
                # Skip categories with only 1 entry - nothing to condense
                if len(data_entries) <= 1:
                    print(f"Skipping category '{category}' - only {len(data_entries)} entry")
                    continue

                print(f"\nProcessing category '{category}' with {len(data_entries)} entries...")

                # Collect all data info from entries
                data_texts = []
                for entry in data_entries:
                    uuid, node_uuid_db, key, data_type, info, cat = entry
                    data_texts.append(f"- {info}")

                # Create condensation prompt
                condensation_prompt = f"""You are a data condensation system. Your task is to condense multiple related data entries into a single comprehensive entry.

CATEGORY: {category}

EXISTING DATA ENTRIES:
{chr(10).join(data_texts)}

YOUR TASK:
Condense these {len(data_texts)} entries into a SINGLE comprehensive entry that:
1. Preserves ALL important information from all entries
2. Removes duplicate or redundant information
3. If newer information supersedes older information, keep only the newer info
4. Maintains clarity and usefulness for future reference
5. Organizes the information logically

IMPORTANT:
- Output ONLY the condensed text - no explanations, no JSON, no markdown
- Be thorough but concise
- Do not lose any important details
- The output will replace all existing entries for this category

CONDENSED ENTRY:"""

                try:
                    # Call the configured model to condense the data
                    condensed_data = condensation_model.generate(condensation_prompt).strip()

                    print(f"Original entries: {len(data_entries)}")
                    print(f"Condensed to: {len(condensed_data)} chars")
                    print(f"Preview: {condensed_data[:200]}...")

                    # Delete all existing entries for this category
                    deleted_count = dao.delete_data_by_category(node_uuid, category)
                    print(f"Deleted {deleted_count} original entries")

                    # Insert the condensed entry
                    timestamp_key = datetime.now().strftime('%Y%m%d_%H%M%S')
                    data_key = f"{category}_condensed_{timestamp_key}"
                    dao.add_data_with_category(
                        node_uuid=node_uuid,
                        category=category,
                        key=data_key,
                        data_type="text",
                        info=condensed_data
                    )
                    print(f"Inserted condensed entry for category '{category}'")

                except Exception as e:
                    print(f"Error condensing category '{category}': {e}")
                    import traceback
                    traceback.print_exc()
                    all_succeeded = False
                    # Don't delete original data if condensation fails
                    continue

            # Reset the node counter after successful cleanup
            dao.reset_node_counter(node_uuid)
            print(f"\nReset node counter for {node_uuid}")

            return all_succeeded

        except Exception as e:
            print(f"Error in cleanup_node_data: {e}")
            import traceback
            traceback.print_exc()
            return False

    @staticmethod
    def cleanup_nodes_batch(dao, threshold, config_path=None):
        """
        Static method to perform batch cleanup on nodes that need it.

        Args:
            dao: GraphDAO instance for database operations
            threshold (int): Insertion count threshold for cleanup
            config_path (str, optional): Path to model config file. Defaults to repo root.

        Returns:
            list: List of node UUIDs that were successfully cleaned
        """

        try:
            # Get all nodes that need cleanup
            nodes_needing_cleanup = dao.get_nodes_needing_cleanup(threshold)

            if not nodes_needing_cleanup:
                print(f"No nodes need cleanup (threshold: {threshold})")
                return []

            print(f"\n{'='*60}")
            print(f"BATCH CLEANUP - Found {len(nodes_needing_cleanup)} nodes needing cleanup")
            print(f"Threshold: {threshold} insertions")
            print(f"{'='*60}")

            successfully_cleaned = []

            for node_uuid in nodes_needing_cleanup:
                counter = dao.get_node_counter(node_uuid)
                print(f"\nCleaning node {node_uuid} (insertion count: {counter})...")

                success = Tree.cleanup_node_data(dao, node_uuid, config_path)

                if success:
                    successfully_cleaned.append(node_uuid)
                    print(f"✓ Successfully cleaned node {node_uuid}")
                else:
                    print(f"✗ Failed to clean node {node_uuid}")

            print(f"\n{'='*60}")
            print(f"Batch cleanup complete: {len(successfully_cleaned)}/{len(nodes_needing_cleanup)} nodes cleaned")
            print(f"{'='*60}")

            return successfully_cleaned

        except Exception as e:
            print(f"Error in cleanup_nodes_batch: {e}")
            import traceback
            traceback.print_exc()
            return []


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
# call the cleanup method in the main function 
if __name__ == "__main__":
    
    dao = GraphDAO("graph.db")
    
    Tree.cleanup_nodes_batch(dao, 10)
