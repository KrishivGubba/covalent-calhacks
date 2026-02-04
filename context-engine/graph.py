import os
import json
import uuid
import sys
import asyncio
from datetime import datetime
from typing import Tuple, List, Optional
from dotenv import load_dotenv
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from graph_dao import GraphDAO, TestGraphDAO
from model_interface import ModelFactory
from graph_config import GraphConfig

# Add parent directory to path to import LLMGraph
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

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
    def __init__(self, db_path, config_path=None):
        self.nodes = {}  # Dictionary to store nodes by UUID for easy lookup
        self.root = None

        self.dao = GraphDAO(db_path)

        # Initialize graph configuration for thresholds
        try:
            self.config = GraphConfig(config_path)
        except Exception as e:
            print(f"Warning: Failed to initialize GraphConfig: {e}")
            self.config = None

        # Initialize model factory with configuration
        try:
            self.model_factory = ModelFactory(config_path)
        except Exception as e:
            print(f"Warning: Failed to initialize model factory: {e}")
            print("Models will not be available for this session.")
            self.model_factory = None
        
        # Initialize each model independently
        self.embedding_model = None
        self.traversal_model = None
        self.action_model = None
        self.condensation_model = None
        self.fit_validation_model = None
        self.graph_operations_model = None

        if self.model_factory:
            try:
                self.embedding_model = self.model_factory.get_embedding_model("embedding")
            except Exception as e:
                print(f"Warning: Failed to initialize embedding model: {e}")

            try:
                self.traversal_model = self.model_factory.get_chat_model("traversal")
            except Exception as e:
                print(f"Warning: Failed to initialize traversal model: {e}")

            try:
                self.action_model = self.model_factory.get_chat_model("action_creation")
            except Exception as e:
                print(f"Warning: Failed to initialize action model: {e}")

            try:
                self.condensation_model = self.model_factory.get_chat_model("data_condensation")
            except Exception as e:
                print(f"Warning: Failed to initialize condensation model: {e}")

            try:
                self.fit_validation_model = self.model_factory.get_chat_model("fit_validation")
            except Exception as e:
                print(f"Warning: Failed to initialize fit validation model: {e}")

            try:
                self.graph_operations_model = self.model_factory.get_chat_model("graph_operations")
            except Exception as e:
                print(f"Warning: Failed to initialize graph operations model: {e}")

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
        
        SAMPLE GRAPH STRUCTURE (showing proper parent-child relationships):
        
        Root Node
        ├── Recruiting
        │   ├── Intern
        │   │   ├── Summer 2026
        │   │   │   ├── Ritesh (individual applicant)
        │   │   │   ├── Siddharth (individual applicant)
        │   │   │   ├── Hemant (individual applicant)
        │   │   │   └── Krishiv (individual applicant)
        │   │   └── Fall 2026
        │   └── New Grad
        │       ├── 2025
        │       ├── 2026
        │       └── Events
        │           ├── Online Webinar
        │           ├── Career Fair
        │           └── Career Conference
        └── Employee Management
            ├── Onboarding
            ├── Issues
            └── Questions/Requests
                ├── Answer Questions
                ├── Approve Timesheets
                └── Approve Leave Requests
        
        KEY PRINCIPLES FROM THIS EXAMPLE:
        - When you have a task with subtasks (e.g., "Summer 2026" interns → individual applicants like Ritesh), CREATE CHILD NODES
        - When you have parallel tasks of the same type (e.g., "Summer 2026" and "Fall 2026"), CREATE SIBLING NODES
        - When you have a category that contains multiple specific items (e.g., "Events" → "Online Webinar", "Career Fair"), use PARENT-CHILD relationships
        - Leaf nodes represent the most specific tasks (e.g., "Ritesh", "Schedule Interview", "Send Email")
        - Internal nodes represent categories or groupings (e.g., "Recruiting", "Employee Management", "Events")
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
        result = "MCP not set up yet"
        # result = asyncio.run(run_graph(action_text, collected_data_string))
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

    def traverse_with_confidence(self, summary: str) -> Tuple[Optional['Node'], float, List[Tuple['Node', float]]]:
        """
        Traverse the graph to find the most relevant node with confidence scoring.

        Args:
            summary: Text describing what the user is currently doing

        Returns:
            Tuple containing:
            - best_node: The node with highest similarity to the summary
            - confidence: The similarity score (0.0 to 1.0) of the best match
            - top_scores: List of (node, score) tuples for top 5 matches, sorted descending
        """
        # Handle edge cases
        if not summary or not summary.strip():
            print("⚠️ traverse_with_confidence() - Empty or None summary provided")
            return (self.root, 0.0, [])

        # Handle empty graph (only root or no nodes)
        if not self.nodes or len(self.nodes) == 0:
            print("⚠️ traverse_with_confidence() - Empty graph")
            return (self.root, 0.0, [(self.root, 0.0)] if self.root else [])

        # Vectorize the input summary
        summary_embedding = self.vectorize_text(summary)
        if summary_embedding is None:
            print("⚠️ traverse_with_confidence() - Vectorization failed")
            return (self.root, 0.0, [])

        # Calculate cosine similarity against ALL nodes
        scores = []  # List of (node, score) tuples

        for node_uuid, node in self.nodes.items():
            if node.embedding is not None:
                try:
                    # Calculate cosine similarity
                    similarity = cosine_similarity(summary_embedding, node.embedding)[0][0]
                    # Ensure score is between 0 and 1
                    similarity = max(0.0, min(1.0, float(similarity)))
                    scores.append((node, similarity))
                except Exception as e:
                    print(f"Error calculating similarity for node {node_uuid}: {e}")
                    continue

        # Handle case where no valid scores were computed
        if not scores:
            print("⚠️ traverse_with_confidence() - No valid similarity scores computed")
            return (self.root, 0.0, [(self.root, 0.0)] if self.root else [])

        # Sort all scores descending
        scores.sort(key=lambda x: x[1], reverse=True)

        # Get top 5
        top_scores = scores[:5]

        # Best node is the first one
        best_node, confidence = top_scores[0]

        # Log results
        summary_preview = summary[:100] + "..." if len(summary) > 100 else summary
        print(f"\n🎯 traverse_with_confidence() - Summary: '{summary_preview}'")
        print(f"🎯 Top 5 matches:")
        for i, (node, score) in enumerate(top_scores, 1):
            path = self._get_node_path(node)
            print(f"   {i}. {node.metadata} (path: {path}) - Score: {score:.4f}")
        print(f"🎯 Selected: {best_node.metadata} with confidence {confidence:.4f}")

        # Log threshold analysis if config is available
        if self.config:
            if self.config.should_insert_directly(confidence):
                print(f"   → Confidence >= {self.config.get_threshold('perfect_fit'):.2f}: Insert directly (no LLM validation)")
            elif self.config.should_validate_with_llm(confidence):
                print(f"   → Confidence >= {self.config.get_threshold('uncertain'):.2f}: Validate with LLM")
            else:
                print(f"   → Confidence < {self.config.get_threshold('uncertain'):.2f}: May need restructure")

        return (best_node, confidence, top_scores)

    def _get_node_path(self, node: 'Node') -> str:
        """
        Get the path from root to a node as a string.

        Args:
            node: The node to get the path for

        Returns:
            str: Path string like "Root > Parent > Node"
        """
        path_parts = []
        current = node

        while current is not None:
            path_parts.append(current.metadata)
            current = current.parent

        # Reverse to get root-to-node order
        path_parts.reverse()
        return " > ".join(path_parts)

    def _format_top_scores(self, top_scores: List[Tuple['Node', float]]) -> str:
        """
        Format the top scores list as a readable string for LLM prompts.

        Args:
            top_scores: List of (node, score) tuples sorted descending

        Returns:
            str: Formatted string with numbered entries showing node metadata, path, and score
        """
        if not top_scores:
            return "No matching nodes found."

        lines = []
        for i, (node, score) in enumerate(top_scores, 1):
            path = self._get_node_path(node)
            lines.append(f"{i}. {node.metadata} (path: {path}) - Score: {score:.2f}")

        return "\n".join(lines)

    def _get_data_sample(self, node: 'Node', max_chars: int = 500) -> str:
        """
        Get a sample of existing data in a node, grouped by category.

        Args:
            node: The node to get data samples from
            max_chars: Maximum characters to show per category

        Returns:
            str: Formatted string showing category names and truncated data samples
        """
        if not node or not node.node_uuid:
            return "No data available."

        try:
            data_by_category = self.dao.get_data_for_node_by_category(node.node_uuid)
        except Exception as e:
            print(f"Error getting data for node {node.node_uuid}: {e}")
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

            # Collect data from entries in this category
            category_data = []
            for entry in entries:
                # entry format: (uuid, node_uuid, key, type, info, category)
                info = entry[4] if len(entry) > 4 else ""
                if info:
                    category_data.append(str(info))

            # Combine and truncate
            combined = " | ".join(category_data)
            if len(combined) > max_chars:
                combined = combined[:max_chars] + "..."

            lines.append(f"\n[{category}]:")
            lines.append(f"  {combined}")
            categories_shown += 1

        return "\n".join(lines) if lines else "No existing data in this node."

    def _llm_validate_fit(self, node: 'Node', summary: str, top_scores: List[Tuple['Node', float]]) -> dict:
        """
        Ask LLM to validate whether the summary fits in the given node.

        Args:
            node: The node being considered for insertion
            summary: Description of what the user is doing
            top_scores: Top 5 alternative nodes with scores for context

        Returns:
            dict: {
                "fits": bool,           # Whether data fits in this node
                "reasoning": str,       # Brief explanation
                "suggested_category": str  # If fits, which category to use
            }
        """
        default_response = {
            "fits": True,
            "reasoning": "Parse error - defaulting to fit",
            "suggested_category": "general"
        }

        # Check if fit validation model is available
        if not self.fit_validation_model:
            print("⚠️ _llm_validate_fit: Fit validation model not available, defaulting to fit")
            return {
                "fits": True,
                "reasoning": "No LLM available - defaulting to fit",
                "suggested_category": "general"
            }

        try:
            # Build the prompt
            node_path = self.get_parent_metadata(node)
            existing_categories = self.dao.get_categories_for_node(node.node_uuid)
            data_sample = self._get_data_sample(node)
            alternatives_text = self._format_top_scores(top_scores)

            prompt = f"""{self.BASE_PROMPT}

TASK: Validate whether new information fits in the selected node.

SELECTED NODE:
- Path from root: {node_path}
- Current node: {node.metadata}
- Existing categories: {', '.join(existing_categories) if existing_categories else 'None'}

EXISTING DATA SAMPLE:
{data_sample}

NEW INFORMATION TO INSERT:
{summary}

ALTERNATIVE NODES (with similarity scores):
{alternatives_text}

DECISION CRITERIA:
1. Is this new information a natural sub-topic of what "{node.metadata}" represents?
2. Would someone looking for this information expect to find it in "{node.metadata}"?
3. Is there a better fit among the alternative nodes listed above?
4. IMPORTANT FOR SUBTASKS: If the new information is about a SPECIFIC INSTANCE or SUBTASK, it may need its own child node
   - Example: If "{node.metadata}" is "Summer 2026 Interns" and new info is about a specific intern named "Ritesh", 
     it should NOT fit here - it should trigger creation of a child node for "Ritesh"
   - Example: If "{node.metadata}" is "Events" and new info is about organizing a specific "Career Fair",
     it should NOT fit here - it should trigger creation of a child node for "Career Fair"
   - Think: Does this represent a new specific instance that deserves its own node?

INSTRUCTIONS:
- If the information fits well in "{node.metadata}" AND is not about a specific subtask/instance, set "fits" to true
- If another node would be significantly better, OR if this is a specific subtask that needs its own child node, set "fits" to false
- Provide a brief reasoning (1-2 sentences) - if it's a subtask, mention that explicitly
- If it fits, suggest an appropriate category name (use existing category if applicable, or suggest a new one)

OUTPUT FORMAT - Return ONLY valid JSON with NO markdown formatting:
{{
    "fits": true or false,
    "reasoning": "Brief explanation of why it fits or doesn't fit",
    "suggested_category": "category_name_if_fits"
}}
"""

            # Call the LLM
            print(f"🤖 _llm_validate_fit: Calling fit validation model for node '{node.metadata}'")
            response = self.fit_validation_model.generate(prompt)

            # Parse the response
            return self._parse_validate_fit_response(response)

        except Exception as e:
            print(f"❌ _llm_validate_fit: Error during validation: {e}")
            import traceback
            traceback.print_exc()
            return default_response

    def _parse_validate_fit_response(self, response_text: str) -> dict:
        """
        Parse the JSON response from the LLM validation.

        Args:
            response_text: Raw response from LLM

        Returns:
            dict: Parsed response with fits, reasoning, suggested_category
        """
        import re

        default_response = {
            "fits": True,
            "reasoning": "Parse error - defaulting to fit",
            "suggested_category": "general"
        }

        try:
            # Try to extract JSON from potential markdown code blocks
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find raw JSON
                json_match = re.search(r'\{[^{}]*"fits"[^{}]*\}', response_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    print(f"⚠️ _parse_validate_fit_response: Could not find JSON in response")
                    print(f"   Response preview: {response_text[:200]}...")
                    return default_response

            parsed = json.loads(json_str)

            # Validate required fields
            if "fits" not in parsed:
                print("⚠️ _parse_validate_fit_response: Missing 'fits' field")
                return default_response

            # Ensure correct types
            result = {
                "fits": bool(parsed.get("fits", True)),
                "reasoning": str(parsed.get("reasoning", "No reasoning provided")),
                "suggested_category": str(parsed.get("suggested_category", "general"))
            }

            print(f"✅ _llm_validate_fit result: fits={result['fits']}, category='{result['suggested_category']}'")
            print(f"   Reasoning: {result['reasoning'][:100]}...")

            return result

        except json.JSONDecodeError as e:
            print(f"⚠️ _parse_validate_fit_response: JSON decode error: {e}")
            print(f"   Response preview: {response_text[:200]}...")
            return default_response
        except Exception as e:
            print(f"⚠️ _parse_validate_fit_response: Unexpected error: {e}")
            return default_response

    def _get_siblings(self, node: 'Node') -> List['Node']:
        """
        Get sibling nodes (same parent, excluding self).

        Args:
            node: The node to find siblings for

        Returns:
            List[Node]: List of sibling Node objects
        """
        if not node or not node.node_uuid:
            return []

        try:
            sibling_tuples = self.dao.get_siblings(node.node_uuid)
            siblings = []

            for sibling_tuple in sibling_tuples:
                # sibling_tuple format: (uuid, metadata, created, last_modified, parent_uuid, children_uuid_arr)
                sibling_uuid = sibling_tuple[0]
                if sibling_uuid in self.nodes:
                    siblings.append(self.nodes[sibling_uuid])

            return siblings
        except Exception as e:
            print(f"Error getting siblings for node {node.node_uuid}: {e}")
            return []

    def _llm_decide_structure(self, node: 'Node', summary: str, top_scores: List[Tuple['Node', float]]) -> list:
        """
        Ask LLM to decide what graph structural changes are needed.
        Can return MULTIPLE operations to be executed in sequence.

        Args:
            node: The current best-match node
            summary: Description of what the user is doing
            top_scores: Top 5 nodes with scores for context

        Returns:
            list: List of operation dicts, each with:
                {
                    "type": "create_child" | "create_sibling" | "split" | "insert_anyway",
                    "reasoning": str,
                    "new_node_metadata": str | None,
                    "split_plan": {...} | None,
                    "target_ref": str | None  # References which previously created node to operate on
                }
        """
        default_response = [{
            "type": "insert_anyway",
            "reasoning": "Error during structure decision - defaulting to insert",
            "new_node_metadata": None,
            "split_plan": None,
            "target_ref": None
        }]

        # Check if graph operations model is available
        if not self.graph_operations_model:
            print("⚠️ _llm_decide_structure: Graph operations model not available, defaulting to insert")
            return [{
                "type": "insert_anyway",
                "reasoning": "No LLM available - defaulting to insert",
                "new_node_metadata": None,
                "split_plan": None,
                "target_ref": None
            }]

        try:
            # Gather context
            node_path = self.get_parent_metadata(node)
            existing_categories = self.dao.get_categories_for_node(node.node_uuid)
            data_sample = self._get_data_sample(node)
            alternatives_text = self._format_top_scores(top_scores)

            # Get siblings
            siblings = self._get_siblings(node)
            siblings_text = "None" if not siblings else "\n".join(
                [f"  - {s.metadata}" for s in siblings]
            )

            # Get children
            children_text = "None" if not node.children else "\n".join(
                [f"  - {c.metadata}" for c in node.children]
            )

            # Get parent
            parent_text = "None (this is root)" if not node.parent else node.parent.metadata

            # Get current depth and max depth from config
            current_depth = self.dao.get_node_depth(node.node_uuid)
            max_depth = self.config.get_max_depth() if self.config else 10

            # Get split thresholds from config
            min_categories = self.config.get_split_min_categories() if self.config else 3
            min_entries = self.config.get_split_min_entries() if self.config else 5

            # Count current entries
            data_by_category = self.dao.get_data_for_node_by_category(node.node_uuid)
            current_categories_count = len(data_by_category) if data_by_category else 0
            current_entries_count = sum(len(entries) for entries in data_by_category.values()) if data_by_category else 0

            # Determine if split is allowed
            split_allowed = (current_categories_count >= min_categories and
                           current_entries_count >= min_entries)
            split_note = ""
            if not split_allowed:
                split_note = f"\nNOTE: SPLIT is NOT recommended for this node (has {current_categories_count} categories and {current_entries_count} entries, needs >= {min_categories} categories and >= {min_entries} entries)"

            # Check if we're at max depth
            depth_note = ""
            if current_depth >= max_depth:
                depth_note = f"\nNOTE: This node is at maximum depth ({current_depth}/{max_depth}). CREATE_CHILD is not allowed - consider CREATE_SIBLING instead."

            prompt = f"""{self.BASE_PROMPT}

TASK: Decide what structural change is needed to accommodate new information that doesn't fit well in existing nodes.

CURRENT NODE CONTEXT:
- Path from root: {node_path}
- Current node: {node.metadata}
- Current depth: {current_depth} (max allowed: {max_depth})
- Parent: {parent_text}
- Siblings:
{siblings_text}
- Children:
{children_text}
- Existing categories ({current_categories_count}): {', '.join(existing_categories) if existing_categories else 'None'}
- Total data entries: {current_entries_count}

EXISTING DATA SAMPLE:
{data_sample}

NEW INFORMATION THAT DOESN'T FIT WELL:
{summary}

ALTERNATIVE NODES (with similarity scores):
{alternatives_text}

{depth_note}
{split_note}

AVAILABLE OPERATIONS:

1. **CREATE_CHILD** - Create a new child node under "{node.metadata}"
   - Use when: New info is a specialization/subset/subtask of the current node
   - IMPORTANT: When you have a specific task that is part of a broader task, create a CHILD node
   - Examples from sample graph:
     * "Summer 2026" (parent) → "Ritesh" (child - specific applicant)
     * "Events" (parent) → "Online Webinar" (child - specific event type)
     * "Questions/Requests" (parent) → "Answer Questions" (child - specific request type)
   - Use for: Individual items within a category, specific tasks within a project, subtasks
   - NOT allowed if current depth >= max_depth

2. **CREATE_SIBLING** - Create a new sibling node (same parent as "{node.metadata}")
   - Use when: New info is parallel to current node (same parent, different category)
   - Examples from sample graph:
     * "Summer 2026" and "Fall 2026" are siblings (both under "Intern")
     * "Recruiting" and "Employee Management" are siblings (both under "Root")
     * "Answer Questions", "Approve Timesheets", and "Approve Leave Requests" are siblings (all under "Questions/Requests")
   - Use for: Similar level tasks that belong to the same parent category

3. **SPLIT** - Divide "{node.metadata}" into multiple child nodes
   - Use when: Current node has become too broad with mixed categories that should be separated
   - Example: Node has mixed engineering and marketing data that should be separate nodes
   - Only recommend if node has >= {min_categories} categories AND >= {min_entries} entries
   - Must provide complete split_plan with new children and category assignments

4. **INSERT_ANYWAY** - Insert into "{node.metadata}" despite low confidence
   - Use when: After review, the data actually does belong here
   - Or when none of the other options make sense

CRITICAL GUIDANCE FOR SUBTASKS:
- If the new information is about a SUBTASK or SPECIFIC INSTANCE of what the current node represents, CREATE_CHILD is usually correct
- Example: If current node is "Summer 2026 Interns" and new info is about scheduling an interview with one intern, that should be a CHILD node for that specific intern

MULTIPLE OPERATIONS:
You can return MULTIPLE operations if the new information requires a sequence of structural changes.
For example:
1. First create a child node for a category
2. Then create another child under that new node for a specific item
3. Then insert the data into the final node

Operations will be executed IN THE ORDER you specify them. Each operation can reference previously created nodes using target_ref.

TARGET REFERENCES:
- "current": The node passed in (current best match)
- "op1", "op2", "op3", etc.: Nodes created by previous operations in this sequence
- Only operations that CREATE nodes (create_child, create_sibling, split) can be referenced

OUTPUT FORMAT - Return ONLY valid JSON with NO markdown formatting:
{{
    "operations": [
        {{
            "type": "create_child" | "create_sibling" | "split" | "insert_anyway",
            "target_ref": "current" | "op1" | "op2" | null,
            "reasoning": "Explanation of why this operation is needed",
            "new_node_metadata": "Name for the new node (required for create_child/create_sibling, null otherwise)",
            "split_plan": {{
                "new_children": [
                    {{"metadata": "Child1 Name", "inherits_categories": ["category1", "category2"]}},
                    {{"metadata": "Child2 Name", "inherits_categories": ["category3"]}}
                ],
                "new_data_goes_to": "Child1 Name"
            }}
        }}
    ]
}}

EXAMPLES:

Single operation:
{{
    "operations": [
        {{"type": "create_child", "target_ref": "current", "reasoning": "...", "new_node_metadata": "New Node", "split_plan": null}}
    ]
}}

Multiple operations (create parent, then child, then insert):
{{
    "operations": [
        {{"type": "create_child", "target_ref": "current", "reasoning": "First create category", "new_node_metadata": "Events", "split_plan": null}},
        {{"type": "create_child", "target_ref": "op1", "reasoning": "Then create specific event", "new_node_metadata": "Career Fair", "split_plan": null}},
        {{"type": "insert_anyway", "target_ref": "op2", "reasoning": "Insert data into Career Fair", "new_node_metadata": null, "split_plan": null}}
    ]
}}

IMPORTANT:
- split_plan is ONLY required when type is "split", otherwise set to null
- target_ref defaults to "current" if not specified
- For most cases, a single operation is sufficient
- Only use multiple operations when you need to create a hierarchy (e.g., category → subcategory → specific item)
"""

            # Call the LLM
            print(f"🏗️ _llm_decide_structure: Calling graph operations model for node '{node.metadata}'")
            response = self.graph_operations_model.generate(prompt)

            # Parse and validate the response
            return self._parse_structure_decision_response(response, current_depth, max_depth)

        except Exception as e:
            print(f"❌ _llm_decide_structure: Error during structure decision: {e}")
            import traceback
            traceback.print_exc()
            return default_response

    def _parse_structure_decision_response(self, response_text: str, current_depth: int, max_depth: int) -> list:
        """
        Parse and validate the JSON response from the LLM structure decision.
        Can handle both single operation (legacy) and multiple operations (new format).

        Args:
            response_text: Raw response from LLM
            current_depth: Current depth of the node
            max_depth: Maximum allowed depth from config

        Returns:
            list: List of validated operations, each with type, reasoning, new_node_metadata, split_plan, target_ref
        """
        import re

        default_response = [{
            "type": "insert_anyway",
            "reasoning": "Parse error - defaulting to insert",
            "new_node_metadata": None,
            "split_plan": None,
            "target_ref": "current"
        }]

        valid_types = ["create_child", "create_sibling", "split", "insert_anyway"]

        try:
            # Try to extract JSON from potential markdown code blocks
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find raw JSON - need to handle nested objects
                # Find the outermost JSON object
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

                if start_idx is not None and end_idx is not None:
                    json_str = response_text[start_idx:end_idx]
                else:
                    print(f"⚠️ _parse_structure_decision_response: Could not find JSON in response")
                    print(f"   Response preview: {response_text[:300]}...")
                    return default_response

            parsed = json.loads(json_str)

            # Check if we have the new format with "operations" key
            operations_list = []
            
            if "operations" in parsed:
                # New format: multiple operations
                operations_list = parsed["operations"]
                if not isinstance(operations_list, list) or len(operations_list) == 0:
                    print(f"⚠️ _parse_structure_decision_response: Invalid operations list")
                    return default_response
            elif "type" in parsed:
                # Legacy format: single operation
                operations_list = [parsed]
            else:
                print(f"⚠️ _parse_structure_decision_response: Response has neither 'operations' nor 'type'")
                return default_response

            # Validate and process each operation
            validated_operations = []
            
            for idx, operation in enumerate(operations_list):
                operation_type = operation.get("type", "").lower()
                
                # Validate type
                if operation_type not in valid_types:
                    print(f"⚠️ _parse_structure_decision_response: Invalid type '{operation_type}' in operation {idx}")
                    continue

                # Get target_ref (defaults to "current")
                target_ref = operation.get("target_ref", "current")
                if target_ref is None:
                    target_ref = "current"

                # Enforce max_depth constraint for CREATE_CHILD
                # Note: Only check depth for operations targeting "current" node
                if operation_type == "create_child" and target_ref == "current" and current_depth >= max_depth:
                    print(f"⚠️ Operation {idx}: CREATE_CHILD not allowed at max depth, converting to INSERT_ANYWAY")
                    validated_operations.append({
                        "type": "insert_anyway",
                        "reasoning": f"CREATE_CHILD requested but node is at max depth ({current_depth}/{max_depth}). Inserting anyway.",
                        "new_node_metadata": None,
                        "split_plan": None,
                        "target_ref": target_ref
                    })
                    continue

                # Validate new_node_metadata for create operations
                new_node_metadata = operation.get("new_node_metadata")
                if operation_type in ["create_child", "create_sibling"]:
                    if not new_node_metadata or not isinstance(new_node_metadata, str):
                        print(f"⚠️ Operation {idx}: Missing new_node_metadata for {operation_type}")
                        continue

                # Validate split_plan for split operations
                split_plan = operation.get("split_plan")
                if operation_type == "split":
                    if not split_plan or not isinstance(split_plan, dict):
                        print(f"⚠️ Operation {idx}: Missing split_plan for split operation")
                        continue

                    new_children = split_plan.get("new_children", [])
                    if not new_children or len(new_children) < 2:
                        print(f"⚠️ Operation {idx}: split_plan must have at least 2 children")
                        continue

                    new_data_goes_to = split_plan.get("new_data_goes_to")
                    if not new_data_goes_to:
                        print(f"⚠️ Operation {idx}: split_plan missing new_data_goes_to")
                        continue

                    # Validate each child in the plan
                    valid_children = True
                    for child in new_children:
                        if not isinstance(child, dict) or "metadata" not in child:
                            print(f"⚠️ Operation {idx}: Invalid child in split_plan")
                            valid_children = False
                            break
                    
                    if not valid_children:
                        continue

                # Operation is valid, add to results
                validated_operations.append({
                    "type": operation_type,
                    "reasoning": str(operation.get("reasoning", "No reasoning provided")),
                    "new_node_metadata": new_node_metadata if operation_type in ["create_child", "create_sibling"] else None,
                    "split_plan": split_plan if operation_type == "split" else None,
                    "target_ref": target_ref
                })

            # If no valid operations, return default
            if not validated_operations:
                print(f"⚠️ _parse_structure_decision_response: No valid operations found")
                return default_response

            # Print summary
            print(f"✅ _llm_decide_structure parsed {len(validated_operations)} operation(s):")
            for idx, op in enumerate(validated_operations):
                print(f"   Op {idx + 1}: {op['type']} (target: {op['target_ref']})")
                if op['new_node_metadata']:
                    print(f"         New node: {op['new_node_metadata']}")
                print(f"         Reasoning: {op['reasoning'][:80]}...")

            return validated_operations

        except json.JSONDecodeError as e:
            print(f"⚠️ _parse_structure_decision_response: JSON decode error: {e}")
            print(f"   Response preview: {response_text[:300]}...")
            return default_response
        except Exception as e:
            print(f"⚠️ _parse_structure_decision_response: Unexpected error: {e}")
            return default_response

    # ==================== NODE CREATION METHODS ====================

    def _refresh_node_embedding(self, node: 'Node') -> None:
        """
        Regenerate a node's embedding based on its current metadata chain.
        Call this after moving a node or changing its metadata.

        Args:
            node: The node to refresh the embedding for
        """
        if not node:
            return

        try:
            metadata_chain = self.get_parent_metadata(node)
            if metadata_chain:
                node.embedding = self.vectorize_text(metadata_chain)
                print(f"🔄 Refreshed embedding for node '{node.metadata}'")
        except Exception as e:
            print(f"⚠️ Failed to refresh embedding for node {node.node_uuid}: {e}")

    def _create_child_node(self, parent: 'Node', metadata: str, summary: str = None, data: str = None) -> 'Node':
        """
        Create a new child node under the given parent.

        Args:
            parent: The parent node
            metadata: Name/description for the new node
            summary: Optional - description of data to insert
            data: Optional - actual data to insert into the new node

        Returns:
            The newly created Node object

        Raises:
            ValueError: If parent is at max_depth or parent is invalid
        """
        if not parent:
            raise ValueError("Parent node cannot be None")

        if not metadata:
            raise ValueError("Metadata cannot be empty")

        # Check max depth
        max_depth = self.config.get_max_depth() if self.config else 10
        current_depth = self.dao.get_node_depth(parent.node_uuid)

        if current_depth >= max_depth:
            raise ValueError(f"Cannot create child: parent is at maximum depth ({current_depth}/{max_depth})")

        print(f"🌱 Creating child node '{metadata}' under '{parent.metadata}'")

        try:
            # Create node in database
            new_uuid = self.dao.create_node(metadata, parent.node_uuid)
            if not new_uuid:
                raise RuntimeError("Failed to create node in database")

            # Add child to parent in database
            self.dao.add_child_to_node(parent.node_uuid, new_uuid)

            # Create Node object in memory
            from datetime import datetime
            current_time = datetime.now().isoformat()

            new_node = Node(
                node_uuid=new_uuid,
                metadata=metadata,
                created=current_time,
                last_modified=current_time,
                parent_uuid=parent.node_uuid,
                children_uuid_arr=[],
                actions=[],
                data=None,
                embedding=None
            )

            # Link in memory
            new_node.parent = parent
            parent.children.append(new_node)
            if new_uuid not in parent.children_uuid_arr:
                parent.children_uuid_arr.append(new_uuid)
            self.nodes[new_uuid] = new_node

            # Generate embedding
            self._refresh_node_embedding(new_node)

            print(f"✅ Created child node '{metadata}' with UUID: {new_uuid[:8]}...")

            # Insert data if provided
            if summary and data:
                print(f"📝 Inserting initial data into new node...")
                # Use _learn_into_node for full action processing, or fall back to simple insert
                if self.action_model:
                    self._learn_into_node(new_node, summary, data)
                else:
                    # No action model - use simple insert
                    self._insert_data_to_node(new_node, summary, data)

            return new_node

        except Exception as e:
            print(f"❌ Failed to create child node: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _insert_data_to_node(self, node: 'Node', summary: str, data: str) -> None:
        """
        Insert data directly into a specific node without traversal.
        Uses comprehensive category creation logic matching learn() method.

        Args:
            node: The node to insert data into
            summary: Description of the data
            data: The data to insert
        """
        try:
            from datetime import datetime
            import re

            # Get existing context
            existing_categories = self.dao.get_categories_for_node(node.node_uuid)
            metadata_chain = self.get_parent_metadata(node)

            # Format existing categories
            categories_text = ""
            if existing_categories:
                categories_text = f"EXISTING DATA CATEGORIES: {', '.join(existing_categories)}\n"
            else:
                categories_text = "EXISTING DATA CATEGORIES: None - this node has no data categories yet.\n"

            # If we have an action model, use it to categorize with comprehensive logic
            if self.action_model:
                prompt = f"""{self.BASE_PROMPT}

CURRENT CONTEXT:
Node Path (from root): {metadata_chain}
Current Node: {node.metadata}

{categories_text}

USER'S CURRENT ACTIVITY:
{summary}

ADDITIONAL DATA:
{data}

YOUR TASK:
Extract and categorize relevant information from the user's activity and data.

**DATA INSERTION** - Extract and categorize relevant information:
   - Condense the screen summary to preserve ONLY relevant information
   - Remove UI noise (cursor positions, visual elements, temporary states)
   - Keep essential context (names, dates, email addresses, decisions, outcomes)
   - Assign data to categories (can use existing or create new ones)
   - Can split data across multiple categories if appropriate

OUTPUT FORMAT - Return ONLY valid JSON with NO markdown formatting:
{{
  "data_insertions": [
    {{
      "category": "category_name",
      "is_new_category": true | false,
      "condensed_data": "The actual data to store - detailed but concise"
    }}
  ]
}}

IMPORTANT:
- Output ONLY the JSON object - no explanations, no markdown code blocks
- Ensure all JSON is properly formatted and valid
- You can create multiple data_insertions if the information naturally splits across categories
"""
                try:
                    response = self.action_model.generate(prompt)
                    
                    # Try to extract JSON from potential markdown code blocks
                    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
                    if json_match:
                        json_str = json_match.group(1)
                    else:
                        # Try to find raw JSON
                        json_match = re.search(r'\{.*"data_insertions".*\}', response, re.DOTALL)
                        if json_match:
                            json_str = json_match.group(0)
                        else:
                            raise ValueError("Could not find valid JSON in response")
                    
                    parsed = json.loads(json_str)
                    data_insertions = parsed.get("data_insertions", [])
                    
                    if not data_insertions:
                        # Fallback to single category
                        data_insertions = [{
                            "category": "general",
                            "is_new_category": "general" not in existing_categories,
                            "condensed_data": data
                        }]
                    
                except Exception as e:
                    print(f"⚠️ LLM parsing failed: {e}, using fallback")
                    # Fallback to single category
                    data_insertions = [{
                        "category": "general",
                        "is_new_category": "general" not in existing_categories,
                        "condensed_data": data
                    }]
            else:
                # No LLM available, use simple fallback
                data_insertions = [{
                    "category": "general",
                    "is_new_category": "general" not in existing_categories,
                    "condensed_data": data
                }]

            # Process all data insertions
            print(f"   → Processing {len(data_insertions)} data insertion(s)...")
            
            for insertion in data_insertions:
                category = insertion.get("category", "general")
                condensed_data = insertion.get("condensed_data", data)
                is_new = insertion.get("is_new_category", False)
                
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
                
                new_indicator = " (new)" if is_new else ""
                print(f"   → Inserted into category '{category}'{new_indicator}: {condensed_data[:100]}...")

                # Increment counter for each insertion
                self.dao.increment_node_counter(node.node_uuid)

        except Exception as e:
            print(f"⚠️ Failed to insert data: {e}")
            import traceback
            traceback.print_exc()

    def _create_sibling_node(self, sibling_of: 'Node', metadata: str, summary: str = None, data: str = None) -> 'Node':
        """
        Create a new node at the same level as the given node (same parent).

        Args:
            sibling_of: The node to create a sibling of
            metadata: Name/description for the new node
            summary: Optional - description of data to insert
            data: Optional - actual data to insert

        Returns:
            The newly created Node object
        """
        if not sibling_of:
            raise ValueError("sibling_of node cannot be None")

        if not metadata:
            raise ValueError("Metadata cannot be empty")

        # Get the parent
        parent = sibling_of.parent

        # If no parent (sibling_of is root), create as child of root instead
        if parent is None:
            print(f"⚠️ Node '{sibling_of.metadata}' is root - creating as child of root instead")
            return self._create_child_node(sibling_of, metadata, summary, data)

        print(f"🌿 Creating sibling node '{metadata}' next to '{sibling_of.metadata}'")

        # Create as child of the parent
        return self._create_child_node(parent, metadata, summary, data)

    def _bootstrap_first_node(self, summary: str, data: str) -> 'Node':
        """
        Create the first real node when graph only has root.

        Args:
            summary: Description of what the user is doing
            data: The data to insert

        Returns:
            The newly created first child node of root

        Raises:
            ValueError: If root already has children or if root doesn't exist
        """
        if not self.root:
            raise ValueError("Root node doesn't exist - cannot bootstrap")

        if self.root.children and len(self.root.children) > 0:
            raise ValueError("Root already has children - bootstrap not needed")

        # Check if bootstrap is enabled
        if self.config and not self.config.is_bootstrap_enabled():
            raise ValueError("Bootstrap is disabled in configuration")

        print(f"🚀 Bootstrapping first node from root...")

        # Build prompt to determine first category
        prompt = f"""{self.BASE_PROMPT}

TASK: Create the first category node for this knowledge graph.

The graph is currently empty (only has a root node). Based on the user's activity, suggest what the first top-level category should be.

USER'S CURRENT ACTIVITY:
{summary}

DATA TO STORE:
{data}

Consider:
- What broad category does this activity fall under?
- What would be a good umbrella term for similar activities?
- Categories should be broad enough to contain subcategories later
- Examples: "Recruiting", "Development", "Finance", "Operations", "Marketing", "HR"

Return ONLY a JSON object:
{{
    "node_metadata": "Broad category name (1-3 words)",
    "initial_category": "First data category within this node",
    "reasoning": "Brief explanation of why this category"
}}
"""

        node_metadata = "General"
        initial_category = "general"

        # Try to get LLM suggestion
        if self.graph_operations_model:
            try:
                response = self.graph_operations_model.generate(prompt)
                import re
                json_match = re.search(r'\{[^{}]*"node_metadata"[^{}]*\}', response, re.DOTALL)
                if json_match:
                    parsed = json.loads(json_match.group(0))
                    node_metadata = parsed.get("node_metadata", "General")
                    initial_category = parsed.get("initial_category", "general")
                    reasoning = parsed.get("reasoning", "")
                    print(f"   LLM suggested: '{node_metadata}' - {reasoning[:100]}...")
            except Exception as e:
                print(f"⚠️ LLM bootstrap suggestion failed: {e}")
                # Fall back to defaults
        else:
            print("⚠️ No graph operations model available, using default category")

        # Create the first child node
        new_node = self._create_child_node(
            parent=self.root,
            metadata=node_metadata,
            summary=summary,
            data=data
        )

        print(f"✅ Bootstrapped first node: '{node_metadata}'")

        return new_node

    # ==================== NODE SPLIT METHODS ====================

    def _validate_split_plan(self, node: 'Node', split_plan: dict) -> Tuple[bool, str]:
        """
        Validate a split plan before executing it.

        Args:
            node: The node to be split
            split_plan: Plan with structure:
                {
                    "new_children": [
                        {"metadata": "Child 1 Name", "inherits_categories": ["cat1", "cat2"]},
                        {"metadata": "Child 2 Name", "inherits_categories": ["cat3"]}
                    ],
                    "new_data_goes_to": "Child 1 Name"
                }

        Returns:
            Tuple of (is_valid, error_message)
            - (True, "") if valid
            - (False, "error message") if invalid
        """
        if not split_plan:
            return (False, "Split plan is None or empty")

        if not isinstance(split_plan, dict):
            return (False, "Split plan must be a dictionary")

        # Check for new_children
        new_children = split_plan.get("new_children")
        if not new_children:
            return (False, "Split plan must have 'new_children' list")

        if not isinstance(new_children, list):
            return (False, "'new_children' must be a list")

        if len(new_children) < 2:
            return (False, "Split plan must have at least 2 new children")

        # Validate each child has metadata
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

            # Validate inherits_categories is a list (can be empty)
            inherits = child.get("inherits_categories")
            if inherits is not None and not isinstance(inherits, list):
                return (False, f"Child '{metadata}' has invalid 'inherits_categories' (must be list)")

        # Check new_data_goes_to
        new_data_goes_to = split_plan.get("new_data_goes_to")
        if new_data_goes_to:
            if new_data_goes_to not in child_names:
                return (False, f"'new_data_goes_to' value '{new_data_goes_to}' does not match any child metadata name")

        # Get existing categories in the node
        try:
            existing_categories = self.dao.get_categories_for_node(node.node_uuid)
        except Exception as e:
            return (False, f"Failed to get node categories: {e}")

        # Validate that inherits_categories reference existing categories (warning only)
        all_inherited_categories = set()
        for child in new_children:
            inherits = child.get("inherits_categories", [])
            for cat in inherits:
                if cat not in existing_categories:
                    print(f"⚠️ Warning: Category '{cat}' in split plan does not exist in node (will be ignored)")
                all_inherited_categories.add(cat)

        # Check for overlapping categories (warning only)
        category_assignments = {}
        for child in new_children:
            child_name = child.get("metadata")
            inherits = child.get("inherits_categories", [])
            for cat in inherits:
                if cat in category_assignments:
                    print(f"⚠️ Warning: Category '{cat}' is assigned to multiple children: '{category_assignments[cat]}' and '{child_name}'")
                else:
                    category_assignments[cat] = child_name

        # Check for unassigned categories (warning only)
        unassigned = set(existing_categories) - all_inherited_categories
        if unassigned:
            print(f"⚠️ Warning: Categories not assigned to any child (will stay on parent or go to first child): {unassigned}")

        return (True, "")

    def _split_node(self, node: 'Node', split_plan: dict, new_summary: str = None, new_data: str = None) -> List['Node']:
        """
        Split a node into multiple children based on the plan.

        Args:
            node: The node to split
            split_plan: Plan from LLM with structure:
                {
                    "new_children": [
                        {"metadata": "Child 1 Name", "inherits_categories": ["cat1", "cat2"]},
                        {"metadata": "Child 2 Name", "inherits_categories": ["cat3"]}
                    ],
                    "new_data_goes_to": "Child 1 Name"
                }
            new_summary: Optional - summary of new data that triggered the split
            new_data: Optional - new data to insert after split

        Returns:
            List of newly created Node objects

        Raises:
            ValueError: If split plan is invalid
            RuntimeError: If split operation fails
        """
        print(f"\n{'='*60}")
        print(f"SPLIT NODE - Splitting '{node.metadata}'")
        print(f"{'='*60}")

        # 1. Validate the split plan
        is_valid, error_msg = self._validate_split_plan(node, split_plan)
        if not is_valid:
            raise ValueError(f"Invalid split plan: {error_msg}")

        new_children_plan = split_plan.get("new_children", [])
        new_data_goes_to = split_plan.get("new_data_goes_to")

        print(f"📋 Split plan validated: {len(new_children_plan)} new children")
        for child in new_children_plan:
            print(f"   - {child['metadata']}: inherits {child.get('inherits_categories', [])}")
        if new_data_goes_to:
            print(f"   New data goes to: '{new_data_goes_to}'")

        # 2. Get existing data before making changes
        try:
            existing_data = self.dao.get_data_for_node_by_category(node.node_uuid)
        except Exception as e:
            raise RuntimeError(f"Failed to get existing data: {e}")

        existing_categories = list(existing_data.keys()) if existing_data else []
        total_entries = sum(len(entries) for entries in existing_data.values()) if existing_data else 0
        print(f"📊 Existing data: {total_entries} entries across {len(existing_categories)} categories")

        # 3. Get existing actions (they stay on parent - children inherit them)
        try:
            existing_actions = self.dao.get_actions_for_node(node.node_uuid)
        except Exception as e:
            print(f"⚠️ Warning: Failed to get existing actions: {e}")
            existing_actions = []

        print(f"📋 Existing actions: {len(existing_actions)} (will remain on parent)")

        # 4. Create each new child node
        created_nodes = []
        name_to_node = {}  # Map metadata name to Node for easy lookup

        try:
            for child_plan in new_children_plan:
                child_metadata = child_plan["metadata"]
                print(f"\n🌱 Creating child node: '{child_metadata}'")

                # Create child without data - we'll move data after
                new_node = self._create_child_node(node, child_metadata)
                created_nodes.append(new_node)
                name_to_node[child_metadata] = new_node

                print(f"   ✅ Created with UUID: {new_node.node_uuid[:8]}...")

        except Exception as e:
            # Rollback: delete any created nodes
            print(f"❌ Error creating child nodes: {e}")
            for created_node in created_nodes:
                try:
                    self.dao.delete_node(created_node.node_uuid, cascade=True)
                    if created_node.node_uuid in self.nodes:
                        del self.nodes[created_node.node_uuid]
                    if created_node in node.children:
                        node.children.remove(created_node)
                except Exception as del_e:
                    print(f"   ⚠️ Failed to rollback node: {del_e}")
            raise RuntimeError(f"Failed to create child nodes: {e}")

        # 5. Distribute data to children based on category assignments
        print(f"\n📦 Distributing data to children...")

        # Build category -> child mapping
        category_to_child = {}
        for child_plan in new_children_plan:
            child_metadata = child_plan["metadata"]
            for cat in child_plan.get("inherits_categories", []):
                if cat in existing_categories:
                    category_to_child[cat] = name_to_node[child_metadata]

        # Determine first child for unassigned categories
        first_child = created_nodes[0] if created_nodes else None

        # Move data by category
        categories_moved = 0
        entries_moved = 0

        for category in existing_categories:
            target_node = category_to_child.get(category)

            if target_node is None:
                # Category not assigned - move to first child
                target_node = first_child
                print(f"   ⚠️ Category '{category}' not assigned, moving to first child '{first_child.metadata if first_child else 'N/A'}'")

            if target_node:
                try:
                    count = self.dao.move_data_between_nodes(
                        node.node_uuid,
                        target_node.node_uuid,
                        category=category
                    )
                    if count > 0:
                        entries_moved += count
                        categories_moved += 1
                        print(f"   ✅ Moved {count} entries from category '{category}' to '{target_node.metadata}'")
                except Exception as e:
                    print(f"   ⚠️ Failed to move category '{category}': {e}")

        print(f"📊 Moved {entries_moved} entries across {categories_moved} categories")

        # 6. Insert new data if provided
        target_child = None
        if new_data_goes_to and new_data_goes_to in name_to_node:
            target_child = name_to_node[new_data_goes_to]
        elif created_nodes:
            target_child = created_nodes[0]  # Default to first child

        if new_summary and new_data and target_child:
            print(f"\n📝 Inserting new data into '{target_child.metadata}'...")
            try:
                self._insert_data_to_node(target_child, new_summary, new_data)
                print(f"   ✅ New data inserted")
            except Exception as e:
                print(f"   ⚠️ Failed to insert new data: {e}")

        # 7. Clean up parent node
        # Data should now be moved - verify parent is empty
        remaining_data = self.dao.get_data_for_node_by_category(node.node_uuid)
        remaining_count = sum(len(entries) for entries in remaining_data.values()) if remaining_data else 0

        if remaining_count > 0:
            print(f"\n⚠️ Parent node still has {remaining_count} data entries (unassigned categories)")
        else:
            print(f"\n✅ Parent node '{node.metadata}' now has no data (organizational node)")

        print(f"📋 Parent keeps {len(existing_actions)} actions (children inherit them)")

        # 8. Refresh embeddings for all new children
        print(f"\n🔄 Refreshing embeddings...")
        for child_node in created_nodes:
            self._refresh_node_embedding(child_node)

        # Optionally refresh parent embedding too
        self._refresh_node_embedding(node)

        print(f"\n{'='*60}")
        print(f"SPLIT COMPLETE - Created {len(created_nodes)} children under '{node.metadata}'")
        for child_node in created_nodes:
            child_data = self.dao.get_data_for_node_by_category(child_node.node_uuid)
            child_entries = sum(len(entries) for entries in child_data.values()) if child_data else 0
            print(f"   - {child_node.metadata}: {child_entries} entries")
        print(f"{'='*60}\n")

        return created_nodes

    # ==================== MAIN LEARNING WITH STRUCTURE METHOD ====================

    def learn_with_structure(self, summary: str, data: str) -> dict:
        """
        Learn new information, potentially restructuring the graph.

        This method:
        1. Finds the best matching node using vector similarity
        2. Evaluates confidence in the match
        3. Either inserts directly, validates with LLM, or restructures the graph
        4. Returns information about what was done

        Args:
            summary: Description of what the user is currently doing
            data: The actual data/information to store

        Returns:
            {
                "operation": "insert" | "create_child" | "create_sibling" | "split" | "bootstrap",
                "target_node": Node,          # The node where data was ultimately inserted
                "confidence": float,          # The similarity score
                "new_nodes": [Node],          # List of any new nodes created (empty if just insert)
                "actions": [action_tuples],   # 4 most recent actions for the target node
                "reasoning": str              # Why this operation was chosen
            }
        """
        print(f"\n{'='*70}")
        print("LEARN WITH STRUCTURE")
        print(f"{'='*70}")
        summary_preview = summary[:100] + "..." if len(summary) > 100 else summary
        print(f"📝 Summary: {summary_preview}")
        print(f"📊 Data length: {len(data)} chars")

        try:
            # ============================================================
            # 0. CREATE ROOT IF IT DOESN'T EXIST
            # ============================================================
            if self.root is None:
                print("\n🌱 No root node found - creating root in database")
                root_uuid = self.dao.create_node("Root", parent_uuid=None)
                if not root_uuid:
                    raise RuntimeError("Failed to create root node in database")
                
                from datetime import datetime
                current_time = datetime.now().isoformat()
                
                self.root = Node(
                    node_uuid=root_uuid,
                    metadata="Root",
                    created=current_time,
                    last_modified=current_time,
                    parent_uuid=None,
                    children_uuid_arr=[],
                    actions=[],
                    data=None,
                    embedding=None
                )
                self.nodes[root_uuid] = self.root
                print(f"✅ Created root node with UUID: {root_uuid[:8]}...")
            
            # ============================================================
            # 1. CHECK FOR EMPTY GRAPH (BOOTSTRAP CASE)
            # ============================================================
            if not self.root.children or len(self.root.children) == 0:
                print("\n🚀 Empty graph detected - bootstrap case")

                # Check if bootstrap is enabled
                if self.config and not self.config.is_bootstrap_enabled():
                    print("   Bootstrap disabled - inserting into root")
                    recent_actions = self.learn(summary, data)
                    return {
                        "operation": "insert",
                        "target_node": self.root,
                        "confidence": 1.0,
                        "new_nodes": [],
                        "actions": recent_actions,
                        "reasoning": "Bootstrap disabled - inserted into root node"
                    }

                # Bootstrap - create first node
                new_node = self._bootstrap_first_node(summary, data)
                recent_actions = self.dao.get_recent_actions_for_node(new_node.node_uuid, limit=4)
                print(f"✅ Bootstrapped first node: '{new_node.metadata}'")
                return {
                    "operation": "bootstrap",
                    "target_node": new_node,
                    "confidence": 1.0,
                    "new_nodes": [new_node],
                    "actions": recent_actions,
                    "reasoning": "Created first node in empty graph"
                }

            # ============================================================
            # 2. TRAVERSE WITH CONFIDENCE
            # ============================================================
            print("\n🔍 Traversing graph to find best match...")
            best_node, confidence, top_scores = self.traverse_with_confidence(summary)

            if best_node is None:
                print("⚠️ No matching node found, using root")
                best_node = self.root
                confidence = 0.0

            print(f"   Best match: '{best_node.metadata}' with confidence {confidence:.4f}")

            # ============================================================
            # 3. HIGH CONFIDENCE - DIRECT INSERT
            # ============================================================
            if self.config and self.config.should_insert_directly(confidence):
                print(f"\n✅ HIGH CONFIDENCE ({confidence:.2f} >= {self.config.get_threshold('perfect_fit'):.2f})")
                print("   → Inserting directly without LLM validation")

                # Use existing learn() method which handles actions and data
                recent_actions = self.learn(summary, data)
                return {
                    "operation": "insert",
                    "target_node": best_node,
                    "confidence": confidence,
                    "new_nodes": [],
                    "actions": recent_actions,
                    "reasoning": f"High confidence match ({confidence:.2f}) - inserted directly"
                }

            # ============================================================
            # 4. MEDIUM CONFIDENCE - LLM VALIDATES
            # ============================================================
            if self.config and self.config.should_validate_with_llm(confidence):
                print(f"\n🤔 MEDIUM CONFIDENCE ({confidence:.2f})")
                print(f"   → Validating fit with LLM...")

                validation = self._llm_validate_fit(best_node, summary, top_scores)

                if validation["fits"]:
                    print(f"   ✅ LLM validated: {validation['reasoning'][:100]}...")
                    recent_actions = self.learn(summary, data)
                    return {
                        "operation": "insert",
                        "target_node": best_node,
                        "confidence": confidence,
                        "new_nodes": [],
                        "actions": recent_actions,
                        "reasoning": f"LLM validated fit: {validation['reasoning']}"
                    }
                else:
                    print(f"   ❌ LLM rejected fit: {validation['reasoning'][:100]}...")
                    print("   → Falling through to restructuring...")
                    # Fall through to restructuring

            # ============================================================
            # 5. LOW CONFIDENCE OR VALIDATION FAILED - RESTRUCTURE
            # ============================================================
            print(f"\n🏗️ LOW CONFIDENCE or validation failed")
            print("   → Asking LLM for structural decision...")

            operations = self._llm_decide_structure(best_node, summary, top_scores)
            
            # Execute operations sequentially
            print(f"\n🔄 Executing {len(operations)} operation(s) in sequence...")
            
            # Track created nodes by operation reference (op1, op2, etc.)
            node_refs = {"current": best_node}
            all_new_nodes = []
            final_target_node = best_node
            all_reasoning = []
            
            for idx, decision in enumerate(operations):
                operation_type = decision["type"]
                reasoning = decision.get("reasoning", "No reasoning provided")
                target_ref = decision.get("target_ref", "current")
                
                all_reasoning.append(f"Op{idx + 1}: {reasoning}")
                
                print(f"\n   [{idx + 1}/{len(operations)}] {operation_type.upper()} (target: {target_ref})")
                print(f"   Reasoning: {reasoning[:100]}...")
                
                # Resolve target node
                target_node = node_refs.get(target_ref, best_node)
                if target_node is None:
                    print(f"   ⚠️ Invalid target_ref '{target_ref}', using 'current' instead")
                    target_node = best_node
                
                # Determine if this is the last operation (where we insert data)
                is_last_operation = (idx == len(operations) - 1)
                
                # Only pass summary/data to the last operation
                op_summary = summary if is_last_operation else None
                op_data = data if is_last_operation else None
                
                # ---------------------------------------------------------
                # Execute operation based on type
                # ---------------------------------------------------------
                
                if operation_type == "insert_anyway":
                    print("   📥 INSERT ANYWAY")
                    if is_last_operation:
                        self._learn_into_node(target_node, summary, data)
                    final_target_node = target_node
                
                # ---------------------------------------------------------
                # CREATE CHILD
                # ---------------------------------------------------------
                elif operation_type == "create_child":
                    new_metadata = decision.get("new_node_metadata", "New Category")
                    print(f"   🌱 CREATE CHILD: '{new_metadata}' under '{target_node.metadata}'")
                    
                    new_node = self._create_child_node(
                        parent=target_node,
                        metadata=new_metadata,
                        summary=op_summary,
                        data=op_data
                    )
                    
                    # Store reference for subsequent operations
                    node_refs[f"op{idx + 1}"] = new_node
                    all_new_nodes.append(new_node)
                    final_target_node = new_node
                    print(f"   ✅ Created child node, stored as 'op{idx + 1}'")
                
                # ---------------------------------------------------------
                # CREATE SIBLING
                # ---------------------------------------------------------
                elif operation_type == "create_sibling":
                    new_metadata = decision.get("new_node_metadata", "New Category")
                    print(f"   🌿 CREATE SIBLING: '{new_metadata}' next to '{target_node.metadata}'")
                    
                    new_node = self._create_sibling_node(
                        sibling_of=target_node,
                        metadata=new_metadata,
                        summary=op_summary,
                        data=op_data
                    )
                    
                    # Store reference for subsequent operations
                    node_refs[f"op{idx + 1}"] = new_node
                    all_new_nodes.append(new_node)
                    final_target_node = new_node
                    print(f"   ✅ Created sibling node, stored as 'op{idx + 1}'")
                
                # ---------------------------------------------------------
                # SPLIT
                # ---------------------------------------------------------
                elif operation_type == "split":
                    split_plan = decision.get("split_plan")
                    if not split_plan:
                        print("   ⚠️ Split decision but no split_plan - skipping")
                        continue
                    
                    print(f"   ✂️ SPLIT '{target_node.metadata}' into {len(split_plan.get('new_children', []))} children")
                    
                    new_nodes = self._split_node(
                        node=target_node,
                        split_plan=split_plan,
                        new_summary=op_summary,
                        new_data=op_data
                    )
                    
                    # Find the target node where new data was inserted
                    new_data_goes_to = split_plan.get("new_data_goes_to")
                    target_for_data = None
                    
                    if new_data_goes_to:
                        for node in new_nodes:
                            if node.metadata == new_data_goes_to:
                                target_for_data = node
                                break
                    
                    if target_for_data is None and new_nodes:
                        target_for_data = new_nodes[0]  # Default to first child
                    
                    # Store the primary result node as reference
                    node_refs[f"op{idx + 1}"] = target_for_data
                    all_new_nodes.extend(new_nodes)
                    final_target_node = target_for_data
                    print(f"   ✅ Split completed, primary node stored as 'op{idx + 1}'")
                
                # ---------------------------------------------------------
                # UNKNOWN OPERATION
                # ---------------------------------------------------------
                else:
                    print(f"   ⚠️ Unknown operation type: {operation_type} - skipping")
                    continue
            
            # After all operations complete, return result
            recent_actions = self.dao.get_recent_actions_for_node(
                final_target_node.node_uuid if final_target_node else best_node.node_uuid,
                limit=4
            )
            
            # Determine primary operation for result
            primary_operation = operations[-1]["type"] if operations else "insert"
            combined_reasoning = " → ".join(all_reasoning)
            
            return {
                "operation": primary_operation,
                "target_node": final_target_node,
                "confidence": confidence,
                "new_nodes": all_new_nodes,
                "actions": recent_actions,
                "reasoning": combined_reasoning
            }

        except Exception as e:
            # ============================================================
            # ERROR HANDLING - GRACEFUL FALLBACK
            # ============================================================
            print(f"\n❌ ERROR in learn_with_structure: {e}")
            import traceback
            traceback.print_exc()

            # Try to fall back gracefully
            fallback_node = self.root
            try:
                # Try to find best node for fallback
                if hasattr(self, 'nodes') and self.nodes:
                    fallback_node = self.traverse(summary) or self.root
            except:
                pass

            print(f"🔄 Falling back to simple insert into '{fallback_node.metadata if fallback_node else 'root'}'")

            try:
                recent_actions = self.learn(summary, data)
            except Exception as learn_error:
                print(f"❌ Fallback learn() also failed: {learn_error}")
                recent_actions = []

            return {
                "operation": "insert",
                "target_node": fallback_node,
                "confidence": 0.0,
                "new_nodes": [],
                "actions": recent_actions,
                "reasoning": f"Error occurred ({str(e)[:50]}) - fell back to insert"
            }

        finally:
            print(f"\n{'='*70}")
            print("LEARN WITH STRUCTURE COMPLETE")
            print(f"{'='*70}\n")

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

    def learn(self, summary: str, data: str, key: str = None, data_type: str = "text") -> list:
        """
        Learn new information by finding the best node and inserting data.
        This is the simple version that doesn't restructure the graph.

        For learning that can restructure the graph, use learn_with_structure().

        Args:
            summary: Description of what the user is doing
            data: The data to store
            key: Optional key for the data (deprecated - auto-generated)
            data_type: Type of data (default: "text", deprecated)

        Returns:
            List of 4 most recently selected actions for the target node
        """
        # Find the best node
        best_node = self.traverse(summary)
        if best_node is None:
            print("Warning: Could not find suitable node, using root")
            best_node = self.root

        # Insert into that node
        return self._learn_into_node(best_node, summary, data, key, data_type)

    def learn_simple(self, summary: str, data: str, node: 'Node' = None, category: str = "general") -> bool:
        """
        Simple learning that just inserts data without action processing.
        Useful for bulk imports or when you don't need action suggestions.

        Args:
            summary: Description for finding the right node/category
            data: The data to store
            node: Optional specific node to insert into (uses traverse if None)
            category: Category for the data (default: "general")

        Returns:
            True on success, False on failure
        """
        try:
            # Find node if not provided
            if node is None:
                node = self.traverse(summary)
                if node is None:
                    node = self.root

            print(f"📝 learn_simple: Inserting into '{node.metadata}'")

            # Generate unique key
            timestamp_key = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            data_key = f"{category}_{timestamp_key}"

            # Insert data directly
            self.dao.add_data_with_category(
                node_uuid=node.node_uuid,
                category=category,
                key=data_key,
                data_type="text",
                info=data
            )

            # Increment counter
            self.dao.increment_node_counter(node.node_uuid)

            print(f"   ✅ Inserted into category '{category}'")
            return True

        except Exception as e:
            print(f"❌ learn_simple error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _learn_into_node(self, node: 'Node', summary: str, data: str, key: str = None, data_type: str = "text") -> list:
        """
        Internal method: Learn new information into a specific node.
        Handles action creation/modification/selection and data insertion.

        This method does NOT call traverse() - it receives the target node directly.
        Use learn() for automatic node selection, or learn_with_structure() for
        learning that can restructure the graph.

        Args:
            node: The target node to insert data into
            summary: Description of what the user is doing on screen
            data: Additional context/data (used in prompt)
            key: Deprecated - keys are auto-generated per category
            data_type: Deprecated - type determined by LLM

        Returns:
            list: List of up to 4 most recently selected actions (tuples)
        """
        try:
            if node is None:
                print("Warning: Node is None, using root")
                node = self.root

            print(f"\n{'='*60}")
            print(f"LEARN INTO NODE: {node.metadata} (UUID: {node.node_uuid})")
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
            print(f"Error in _learn_into_node(): {e}")
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
