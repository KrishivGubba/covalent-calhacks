"""
Simple Action Executor - Single-shot action planning with human approval.

This replaces the complex LangGraph setup with a simple two-phase approach:
1. Plan phase: Agent proposes ONE action with parameters
2. Execute phase: User approves/edits parameters, then executes

No screen controller, no complex graphs - just simple, effective execution.
Uses the GatewayClient to talk to AWS Bedrock via Lambda.
"""
import os
import sys
import asyncio
import pickle
import json
import re
from pathlib import Path
from typing import Optional, Dict, Any, List
import numpy as np
from dotenv import load_dotenv

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import OpenAIEmbeddings

# Add llm-interactions to path for GatewayClient
sys.path.insert(0, str(Path(__file__).parent / "llm-interactions"))
from gateway_client import GatewayClient, GatewayError

# Add server to path for AuthDAO
sys.path.insert(0, str(Path(__file__).parent / "server"))
from auth_dao import AuthDAO

load_dotenv()

# Project root for MCP server
_PROJECT_ROOT = Path(__file__).resolve().parent

# Database path for auth
_DB_PATH = _PROJECT_ROOT / "context-engine" / "graph.db"

# Initialize the Gateway Client (talks to Lambda -> Bedrock)
_gateway_client = None


def _get_access_token_from_db() -> Optional[str]:
    """
    Get the access token from the user_sessions table.
    Returns the first available access token, or None if no sessions exist.
    """
    try:
        auth_dao = AuthDAO(str(_DB_PATH))
        
        # Get all sessions and find the first one with an access token
        sessions = auth_dao.get_all_sessions()
        if not sessions:
            return None
        
        # Get the first user's full session (get_all_sessions doesn't return access_token)
        first_user_id = sessions[0]["user_id"]
        session = auth_dao.get_session(first_user_id)
        
        if session and session.get("access_token"):
            return session["access_token"]
        
        return None
        
    except Exception:
        return None


def get_gateway_client() -> GatewayClient:
    """Get or create the Gateway client with access token from DB."""
    global _gateway_client
    if _gateway_client is None:
        # Get access token from database
        access_token = _get_access_token_from_db()
        
        _gateway_client = GatewayClient(
            access_token=access_token,  # Auth0 JWT for Lambda authentication
            default_model="claude-4-sonnet",  # Use alias from MODELS dict
            default_max_tokens=4096,
            default_temperature=0.0,  # Deterministic for tool selection
        )
    
    return _gateway_client

# MCP Server Configuration
# Uses HTTP transport - MCP server must be running (use covalent_mcp/start_mcp.sh)
MCP_PORT = int(os.getenv("MCP_PORT", "8001"))
MCP_SERVERS = {
    "covalent": {
        "transport": "http",
        "url": f"http://localhost:{MCP_PORT}/mcp",
    },
}

# Tool Routing Configuration
TOOL_CACHE_DIR = Path.home() / ".cache" / "covalent_action_executor"
TOP_K_TOOLS = 15  # Number of relevant tools/resources to select

# Initialize embeddings model
embeddings = OpenAIEmbeddings()

# =============================================================================
# MCP CLIENT MANAGEMENT
# =============================================================================
_mcp_client = None
_all_tools = None
_client_lock = None


async def get_mcp_client(max_retries: int = 3):
    """Get or create the MCP client with connection pooling and retry logic."""
    global _mcp_client, _all_tools, _client_lock

    if _client_lock is None:
        _client_lock = asyncio.Lock()

    async with _client_lock:
        for attempt in range(max_retries):
            try:
                if _mcp_client is None:
                    _mcp_client = MultiServerMCPClient(MCP_SERVERS)
                    _all_tools = await _mcp_client.get_tools()
                return _mcp_client, _all_tools
            except Exception as e:
                _mcp_client = None
                _all_tools = None
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    raise ConnectionError(f"Failed to connect to MCP server after {max_retries} attempts: {e}")


async def reset_mcp_client():
    """Reset the MCP client connection."""
    global _mcp_client, _all_tools
    _mcp_client = None
    _all_tools = None


# =============================================================================
# SEMANTIC ROUTING (SEPARATE FOR TOOLS AND RESOURCES)
# =============================================================================

# Cache files for tools and resources
TOOL_CACHE_FILE = TOOL_CACHE_DIR / "tool_embeddings.pkl"
RESOURCE_CACHE_FILE = TOOL_CACHE_DIR / "resource_embeddings.pkl"

# Resource name patterns (read-only operations)
RESOURCE_PATTERNS = ['list_', 'get_', 'search_', 'read_', 'fetch_', 'query_']


def _is_resource(item) -> bool:
    """Check if an MCP item is a resource (read-only) vs a tool (write/action)."""
    # Resources have URI attribute
    if hasattr(item, 'uri'):
        return True
    # Or match read-only naming patterns
    name_lower = item.name.lower()
    return any(pattern in name_lower for pattern in RESOURCE_PATTERNS)


class ToolRouter:
    """Routes queries to the most relevant tools OR resources using semantic similarity."""

    def __init__(self):
        # Tools (write/action operations)
        self.tools = None
        self.tool_embeddings = None
        self.tool_names = None
        
        # Resources (read-only operations)
        self.resources = None
        self.resource_embeddings = None
        self.resource_names = None
        
        self._initialized = False

    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        TOOL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_items(self, items: list, cache_file: Path) -> tuple:
        """Cache embeddings for a list of items."""
        self._ensure_cache_dir()

        descriptions = [f"{item.name}: {item.description}" for item in items]
        item_embeddings = embeddings.embed_documents(descriptions)

        cache_data = {
            'names': [item.name for item in items],
            'descriptions': descriptions,
            'embeddings': item_embeddings,
        }

        with open(cache_file, 'wb') as f:
            pickle.dump(cache_data, f)

        return items, np.array(item_embeddings), [item.name for item in items]

    def _load_cache(self, items: list, cache_file: Path) -> Optional[tuple]:
        """Load cached embeddings if available and valid."""
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'rb') as f:
                cache_data = pickle.load(f)

            current_names = set(item.name for item in items)
            cached_names = set(cache_data['names'])

            if current_names != cached_names:
                return None

            return items, np.array(cache_data['embeddings']), cache_data['names']

        except Exception:
            return None

    def initialize(self, all_items: list):
        """
        Initialize the router by separating tools and resources,
        then caching embeddings for each.
        """
        if self._initialized:
            return
            
        # Separate tools from resources
        tools_list = [item for item in all_items if not _is_resource(item)]
        resources_list = [item for item in all_items if _is_resource(item)]
        
        # Cache/load tools
        cached = self._load_cache(tools_list, TOOL_CACHE_FILE)
        if cached:
            self.tools, self.tool_embeddings, self.tool_names = cached
        else:
            self.tools, self.tool_embeddings, self.tool_names = self._cache_items(tools_list, TOOL_CACHE_FILE)
        
        # Cache/load resources
        if resources_list:
            cached = self._load_cache(resources_list, RESOURCE_CACHE_FILE)
            if cached:
                self.resources, self.resource_embeddings, self.resource_names = cached
            else:
                self.resources, self.resource_embeddings, self.resource_names = self._cache_items(resources_list, RESOURCE_CACHE_FILE)
        else:
            self.resources = []
            self.resource_embeddings = None
            self.resource_names = []
        
        self._initialized = True

    def _semantic_search(self, query: str, items: list, item_embeddings: np.ndarray, top_k: int) -> list:
        """Perform semantic search on a set of items."""
        if not items or item_embeddings is None or len(item_embeddings) == 0:
            return []
        
        # Embed the query
        query_embedding = np.array(embeddings.embed_query(query))

        # Calculate cosine similarity
        similarities = np.dot(item_embeddings, query_embedding) / (
            np.linalg.norm(item_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )

        # Get top-k indices
        top_k = min(top_k, len(items))
        top_indices = np.argsort(similarities)[-top_k:][::-1]

        return [items[i] for i in top_indices]

    def get_relevant_tools(self, query: str, top_k: int = TOP_K_TOOLS) -> list:
        """
        Find the most relevant TOOLS (write/action operations) for a query.
        Used in the PLANNING phase.
        """
        if not self._initialized:
            raise ValueError("ToolRouter not initialized. Call initialize() first.")

        return self._semantic_search(query, self.tools, self.tool_embeddings, top_k)

    def get_relevant_resources(self, query: str, top_k: int = TOP_K_TOOLS) -> list:
        """
        Find the most relevant RESOURCES (read-only operations) for a query.
        Used in the RESEARCH phase.
        """
        if not self._initialized:
            raise ValueError("ToolRouter not initialized. Call initialize() first.")

        return self._semantic_search(query, self.resources, self.resource_embeddings, top_k)


# Global tool router instance
tool_router = ToolRouter()


# =============================================================================
# CONTEXT GATHERING (RESEARCH PHASE)
# =============================================================================

def _parse_resource_selection(response_text: str) -> List[Dict[str, Any]]:
    """
    Parse LLM response to extract which resources/tools to call.
    
    Expected format:
    {
        "resources": [
            {"name": "search_web", "parameters": {"query": "..."}, "reason": "..."},
            {"name": "list_messages", "parameters": {"query": "from:ritesh"}, "reason": "..."}
        ],
        "reasoning": "Overall explanation"
    }
    
    Returns list of resource dicts, or empty list if none needed.
    """
    # Try to find JSON in the response
    start = response_text.find('{')
    end = response_text.rfind('}')
    
    if start == -1 or end == -1 or end <= start:
        return []
    
    json_str = response_text[start:end + 1]
    
    try:
        parsed = json.loads(json_str)
        resources = parsed.get("resources", [])
        
        # Validate each resource has required fields
        valid_resources = []
        for r in resources:
            if isinstance(r, dict) and "name" in r:
                # Ensure parameters is a dict
                if "parameters" not in r:
                    r["parameters"] = {}
                valid_resources.append(r)
        
        return valid_resources
    except json.JSONDecodeError:
        return []


async def gather_context(action_text: str, existing_context: str = "") -> Dict[str, Any]:
    """
    Research phase: Gather context by reading relevant resources.
    
    The LLM decides which resources to read based on the action.
    Resources are READ-ONLY operations (safe to execute without approval).
    
    Args:
        action_text: The action description from the user
        existing_context: Any context already available (from graph, etc.)
        
    Returns:
        {
            "status": "success" | "error",
            "context": str,  # Combined context from all resources
            "resources_read": list,  # URIs that were read
            "error": str | None
        }
    """
    try:
        # Get MCP client and all items
        client, all_items = await get_mcp_client()
        
        # Initialize tool router if not already done
        if not tool_router._initialized:
            tool_router.initialize(all_items)
        
        # Get relevant RESOURCES only (semantic search on resources, not tools)
        relevant_resources = tool_router.get_relevant_resources(
            action_text + " " + existing_context[:500],
            top_k=TOP_K_TOOLS
        )
        
        if not relevant_resources:
            return {
                "status": "success",
                "context": existing_context,
                "resources_read": [],
                "error": None
            }
        
        # Build resource descriptions for the prompt
        resource_descriptions = "\n".join([
            f"- {r.name}: {r.description}"
            for r in relevant_resources
        ])
        
        system_prompt = """You are a research assistant that gathers context before taking actions.

Your task is to decide which READ-ONLY resources to query to gather information needed for the action.

IMPORTANT:
1. Only select resources that will provide USEFUL context for the action
2. Don't select resources if the existing context is sufficient
3. Be selective - only query what's needed (max 3 resources)
4. Resources are READ-ONLY and safe to execute

OUTPUT FORMAT - Return ONLY valid JSON:
{
    "resources": [
        {"name": "resource_name", "parameters": {"param1": "value1"}, "reason": "why this helps"}
    ],
    "reasoning": "Overall explanation of what context is needed"
}

If NO resources are needed (existing context is sufficient), return:
{
    "resources": [],
    "reasoning": "Existing context is sufficient"
}"""

        user_prompt = f"""Action to perform: {action_text}

Existing context:
{existing_context if existing_context else "(none)"}

Available read-only resources:
{resource_descriptions}

Which resources should I query to gather context for this action?"""

        # Call the Gateway (Lambda -> Bedrock)
        gateway = get_gateway_client()
        
        response = gateway.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=1024,
            temperature=0.0,
        )
        
        print(f"\n{'='*60}")
        print(f"LLM OUTPUT (RESEARCH PHASE)")
        print(f"{'='*60}")
        print(response.content)
        print(f"{'='*60}\n")
        
        # Parse which resources to read
        resources_to_read = _parse_resource_selection(response.content)
        
        if not resources_to_read:
            print("ℹ️ LLM decided no additional context needed")
            return {
                "status": "success",
                "context": existing_context,
                "resources_read": [],
                "error": None
            }
        
        # Execute resource reads
        gathered_context = []
        resources_read = []
        
        # Build a tool lookup dict for invoking by name
        tool_lookup = {t.name: t for t in all_items}
        
        for resource_spec in resources_to_read[:3]:  # Max 3 resources
            resource_name = resource_spec.get("name", "")
            params = resource_spec.get("parameters", {})
            reason = resource_spec.get("reason", "")
            
            try:
                print(f"📖 Reading resource: {resource_name} with params {params}")
                
                # Find the tool by name and invoke it
                tool = tool_lookup.get(resource_name)
                if tool is None:
                    print(f"⚠️ Tool/resource '{resource_name}' not found")
                    continue
                
                # Invoke the tool (LangChain tools use .ainvoke())
                result = await tool.ainvoke(params)
                
                gathered_context.append(f"--- {resource_name} ---\n{result}")
                resources_read.append(resource_name)
                print(f"✅ Successfully read {resource_name}")
                
            except Exception as e:
                print(f"⚠️ Failed to read {resource_name}: {e}")
                # Continue with other resources
        
        # Combine all context
        combined_context = existing_context
        if gathered_context:
            combined_context += "\n\n=== Gathered Context ===\n" + "\n\n".join(gathered_context)
        
        print(f"✅ Research complete: read {len(resources_read)} resources")
        
        return {
            "status": "success",
            "context": combined_context,
            "resources_read": resources_read,
            "error": None
        }
        
    except GatewayError as e:
        print(f"❌ Gateway error during research: {e}")
        return {
            "status": "error",
            "context": existing_context,
            "resources_read": [],
            "error": f"Gateway error: {str(e)}"
        }
    except Exception as e:
        print(f"❌ Error in gather_context: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "context": existing_context,
            "resources_read": [],
            "error": f"Research error: {str(e)}"
        }


# =============================================================================
# ACTION PLANNING AND EXECUTION
# =============================================================================

def _parse_tool_response(response_text: str) -> Optional[Dict[str, Any]]:
    """
    Parse the LLM response to extract the tool call JSON.
    
    Returns:
        Dict with tool_name, parameters, reasoning or None if parsing fails
    """
    # Try to find JSON in the response
    # First, try to find a JSON code block
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON object
        json_match = re.search(r'\{[^{}]*"tool_name"[^{}]*\}', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            # Try to find JSON with nested objects (parameters)
            # Match from first { to last }
            start = response_text.find('{')
            end = response_text.rfind('}')
            if start != -1 and end != -1 and end > start:
                json_str = response_text[start:end + 1]
            else:
                return None
    
    try:
        parsed = json.loads(json_str)
        
        # Validate required fields
        if "tool_name" not in parsed:
            return None
        
        return {
            "tool_name": parsed.get("tool_name"),
            "parameters": parsed.get("parameters", {}),
            "reasoning": parsed.get("reasoning", "Action proposed by agent")
        }
    except json.JSONDecodeError:
        return None


async def plan_action(action_text: str, context_data: str) -> Dict[str, Any]:
    """
    Plan a single action based on the action text and context.
    
    Uses the GatewayClient to call AWS Bedrock via Lambda.
    The LLM outputs structured JSON with the proposed tool call.
    
    Args:
        action_text: The action description from the user
        context_data: All collected context data from the graph
        
    Returns:
        {
            "status": "success" | "error",
            "proposed_action": {
                "tool_name": str,
                "parameters": dict,
                "reasoning": str
            } | None,
            "error": str | None
        }
    """
    try:
        # Get MCP client and all items
        client, all_items = await get_mcp_client()
        
        # Initialize tool router if not already done
        if not tool_router._initialized:
            tool_router.initialize(all_items)
        
        # Get relevant TOOLS only (semantic search on tools, not resources)
        relevant_tools = tool_router.get_relevant_tools(
            action_text + " " + context_data[:500],  # Include some context in routing
            top_k=TOP_K_TOOLS
        )
        
        if not relevant_tools:
            return {
                "status": "error",
                "proposed_action": None,
                "error": "No relevant tools found for this action"
            }
        
        # Build tool descriptions for the prompt
        tool_descriptions = "\n".join([
            f"- {tool.name}: {tool.description}\n  Parameters: {tool.args}"
            for tool in relevant_tools
        ])
        
        system_prompt = """You are an action planning assistant.

Your task is to analyze the user's action and propose ONE TOOL to execute.

IMPORTANT INSTRUCTIONS:
1. Choose ONLY ONE tool that best accomplishes the action
2. Fill in ALL required parameters based on the provided context
3. Use the context data to infer missing information (emails, names, dates, etc.)
4. If information is missing, make reasonable assumptions or use placeholders like "[FILL IN]"
5. DO NOT execute the tool - just propose it with all parameters filled
6. Provide brief reasoning for your choice

The user will review and can edit your proposed parameters before execution.

OUTPUT FORMAT - Return ONLY valid JSON with NO additional text:
{
    "tool_name": "the_tool_name",
    "parameters": {
        "param1": "value1",
        "param2": "value2"
    },
    "reasoning": "Brief explanation of why this tool and these parameters"
}"""

        user_prompt = f"""Available tools:
{tool_descriptions}

Action to plan: {action_text}

Context available:
{context_data}

Analyze this action and output a single JSON object with the tool call."""

        # Call the Gateway (Lambda -> Bedrock)
        gateway = get_gateway_client()
        
        response = gateway.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=2048,
            temperature=0.0,  # Deterministic
        )
        
        print(f"\n{'='*60}")
        print(f"LLM OUTPUT (PLANNING PHASE)")
        print(f"{'='*60}")
        print(response.content)
        print(f"{'='*60}\n")
        
        # Parse the response
        proposed_action = _parse_tool_response(response.content)
        
        if not proposed_action:
            return {
                "status": "error",
                "proposed_action": None,
                "error": f"Failed to parse tool call from LLM response. Response: {response.content[:200]}"
            }
        
        return {
            "status": "success",
            "proposed_action": proposed_action,
            "error": None
        }
        
    except GatewayError as e:
        print(f"❌ Gateway error: {e}")
        return {
            "status": "error",
            "proposed_action": None,
            "error": f"Gateway error: {str(e)}"
        }
    except ConnectionError as e:
        print(f"❌ MCP connection error: {e}")
        return {
            "status": "error",
            "proposed_action": None,
            "error": f"Connection error: {str(e)}"
        }
    except Exception as e:
        print(f"❌ Error in plan_action: {e}")
        import traceback
        traceback.print_exc()
        await reset_mcp_client()
        return {
            "status": "error",
            "proposed_action": None,
            "error": f"Planning error: {str(e)}"
        }


async def execute_action(tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute an approved action with user-edited parameters.
    
    Args:
        tool_name: Name of the tool to execute
        parameters: User-approved/edited parameters
        
    Returns:
        {
            "status": "success" | "error",
            "result": Any,
            "error": str | None
        }
    """
    try:
        client, all_tools = await get_mcp_client()
        
        print(f"🚀 Executing {tool_name} with parameters: {parameters}")
        
        # Find the tool by name
        tool_lookup = {t.name: t for t in all_tools}
        tool = tool_lookup.get(tool_name)
        
        if tool is None:
            return {
                "status": "error",
                "result": None,
                "error": f"Tool '{tool_name}' not found"
            }
        
        # Execute the tool via LangChain's ainvoke
        result = await tool.ainvoke(parameters)
        
        print(f"✅ Tool execution completed")
        
        return {
            "status": "success",
            "result": result,
            "error": None
        }
        
    except Exception as e:
        print(f"❌ Error executing action: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "result": None,
            "error": f"Execution error: {str(e)}"
        }


# =============================================================================
# COMBINED FLOW FUNCTIONS
# =============================================================================

async def research_and_plan(action_text: str, initial_context: str = "") -> Dict[str, Any]:
    """
    Combined research + planning flow.
    
    This is the main entry point for the action executor.
    1. Gathers context by reading relevant resources
    2. Plans the action using gathered context
    
    Args:
        action_text: The action description from the user
        initial_context: Any context already available (from graph, etc.)
        
    Returns:
        {
            "status": "success" | "error",
            "research": {
                "resources_read": list,
                "context_gathered": str
            },
            "proposed_action": {
                "tool_name": str,
                "parameters": dict,
                "reasoning": str
            } | None,
            "error": str | None
        }
    """
    # Phase 0: Research
    print("=" * 40)
    print("🔍 PHASE 0: RESEARCH")
    print("=" * 40)
    
    research_result = await gather_context(action_text, initial_context)
    
    research_info = {
        "resources_read": research_result.get("resources_read", []),
        "context_gathered": research_result.get("context", initial_context)
    }
    
    if research_result["status"] == "error":
        print(f"⚠️ Research had issues (continuing): {research_result['error']}")
    
    # Phase 1: Planning
    print("\n" + "=" * 40)
    print("📋 PHASE 1: PLANNING")
    print("=" * 40)
    
    plan_result = await plan_action(action_text, research_info["context_gathered"])
    
    if plan_result["status"] == "error":
        return {
            "status": "error",
            "research": research_info,
            "proposed_action": None,
            "error": plan_result["error"]
        }
    
    return {
        "status": "success",
        "research": research_info,
        "proposed_action": plan_result["proposed_action"],
        "error": None
    }


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

async def rebuild_tool_cache():
    """Rebuild the tool embedding cache. Run when adding new tools."""
    print("🔄 Rebuilding tool cache...")
    client, all_tools = await get_mcp_client()
    tool_router.cache_tools(all_tools)
    print("✅ Tool cache rebuilt successfully!")


async def health_check():
    """Check if MCP servers and Gateway are healthy."""
    result = {
        "mcp_status": "unknown",
        "gateway_status": "unknown",
        "tools_count": 0,
        "tool_names": []
    }
    
    # Check MCP
    try:
        client, tools = await get_mcp_client()
        result["mcp_status"] = "healthy"
        result["tools_count"] = len(tools)
        result["tool_names"] = [t.name for t in tools]
        print(f"✅ MCP health check passed: {len(tools)} tools available")
    except Exception as e:
        result["mcp_status"] = "unhealthy"
        result["mcp_error"] = str(e)
        print(f"❌ MCP health check failed: {e}")
    
    # Check Gateway
    try:
        gateway = get_gateway_client()
        gateway_health = gateway.health()
        result["gateway_status"] = gateway_health.get("status", "unknown")
        result["gateway_model"] = gateway_health.get("default_model", "unknown")
        print(f"✅ Gateway health check passed: {result['gateway_model']}")
    except GatewayError as e:
        result["gateway_status"] = "unhealthy"
        result["gateway_error"] = str(e)
        print(f"❌ Gateway health check failed: {e}")
    except Exception as e:
        result["gateway_status"] = "unhealthy"
        result["gateway_error"] = str(e)
        print(f"❌ Gateway health check failed: {e}")
    
    # Overall status
    if result["mcp_status"] == "healthy" and result["gateway_status"] == "healthy":
        result["status"] = "healthy"
    else:
        result["status"] = "unhealthy"
    
    return result


# =============================================================================
# MAIN / TESTING
# =============================================================================

async def main():
    """Test the action executor with full 3-phase flow."""
    
    # Test action - this one benefits from context gathering
    action_text = "Reply to Ritesh's latest email about the project update"
    
    # Initial context (could come from the graph or be empty)
    initial_context = """
    Known information:
    - Ritesh is a team member (ritesh@example.com)
    - We're working on Q1 roadmap
    """
    
    print("=" * 60)
    print("PHASE 0: RESEARCH (Context Gathering)")
    print("=" * 60)
    
    # Phase 0: Gather context by reading relevant resources
    research_result = await gather_context(action_text, initial_context)
    
    if research_result["status"] == "error":
        print(f"⚠️ Research had issues: {research_result['error']}")
        # Continue anyway with whatever context we have
    
    print(f"\n📚 Resources read: {research_result['resources_read']}")
    print(f"   Context length: {len(research_result['context'])} chars")
    
    print("\n" + "=" * 60)
    print("PHASE 1: PLANNING")
    print("=" * 60)
    
    # Phase 1: Plan the action using gathered context
    plan_result = await plan_action(action_text, research_result["context"])
    
    if plan_result["status"] == "error":
        print(f"❌ Planning failed: {plan_result['error']}")
        return
    
    proposed = plan_result["proposed_action"]
    print(f"\n📋 Proposed Action:")
    print(f"   Tool: {proposed['tool_name']}")
    print(f"   Parameters: {json.dumps(proposed['parameters'], indent=4)}")
    print(f"   Reasoning: {proposed['reasoning']}")
    
    print("\n" + "=" * 60)
    print("PHASE 2: EXECUTION (simulated approval)")
    print("=" * 60)
    
    # Simulate user approval (in real app, user would edit these)
    approved_params = proposed['parameters']
    
    # In real app, we'd wait for user approval here
    print("⏸️  [In real app: User reviews and approves/edits parameters here]")
    
    # Phase 2: Execute the action
    exec_result = await execute_action(proposed['tool_name'], approved_params)
    
    if exec_result["status"] == "error":
        print(f"❌ Execution failed: {exec_result['error']}")
        return
    
    print(f"\n✅ Action executed successfully!")
    print(f"   Result: {exec_result['result']}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "--cache":
            asyncio.run(rebuild_tool_cache())
        elif command == "--health":
            result = asyncio.run(health_check())
            print(result)
        elif command == "--help":
            print("""
Usage: python action_executor.py [command]

Commands:
  (no args)   Run test example
  --cache     Rebuild tool embedding cache
  --health    Check MCP server health
  --help      Show this help message
            """)
        else:
            print(f"Unknown command: {command}")
            print("Use --help for usage information")
    else:
        asyncio.run(main())
