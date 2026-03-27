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

# Add llm-interactions to path for GatewayClient
sys.path.insert(0, str(Path(__file__).parent / "llm-interactions"))
from gateway_client import GatewayClient, GatewayError

# Add server to path for AuthDAO
sys.path.insert(0, str(Path(__file__).parent / "server"))
from auth_dao import AuthDAO

# Add project root for logger
sys.path.insert(0, str(Path(__file__).resolve().parent))
from logger import get_logger

# Add covalent_mcp for passable outputs registry
from covalent_mcp.tools import format_passable_outputs_for_prompt, get_passable_outputs

load_dotenv()

log = get_logger()

# Project root for MCP server
if getattr(sys, 'frozen', False):
    _PROJECT_ROOT = Path(sys._MEIPASS)
else:
    _PROJECT_ROOT = Path(__file__).resolve().parent

def _resolve_db_path() -> Path:
    """
    Resolve DB path at call time so late env-var initialization is respected.
    This is important in bundled Flask startup where GRAPH_DB_PATH may be set
    after module import.
    """
    return Path(os.environ.get('GRAPH_DB_PATH', str(_PROJECT_ROOT / "context-engine" / "graph.db")))

# Initialize the Gateway Client (talks to Lambda -> Bedrock)
_gateway_client = None


def _get_access_token_from_db() -> Optional[str]:
    """
    Get the access token from the user_sessions table.
    Returns the first available access token, or None if no sessions exist.
    """
    db_path = _resolve_db_path()
    try:
        auth_dao = AuthDAO(str(db_path))
        
        sessions = auth_dao.get_all_sessions()
        if not sessions:
            print(f"⚠️  No user sessions found in DB at {db_path}")
            return None
        
        first_user_id = sessions[0]["user_id"]
        session = auth_dao.get_session(first_user_id)
        
        if session and session.get("access_token"):
            return session["access_token"]
        
        print(f"⚠️  User session for {first_user_id} exists but has no access_token")
        return None
        
    except Exception as e:
        print(f"❌ Failed to read access token from DB ({db_path}): {e}")
        return None


def get_gateway_client() -> GatewayClient:
    """Get or create the Gateway client, always refreshing the access token."""
    global _gateway_client
    access_token = _get_access_token_from_db()

    if _gateway_client is None:
        _gateway_client = GatewayClient(
            access_token=access_token,
            default_model="claude-4-sonnet",
            default_max_tokens=4096,
            default_temperature=0.0,
        )
    else:
        _gateway_client.access_token = access_token
    
    return _gateway_client

# MCP Server Configuration
# Uses HTTP transport - MCP server must be running
# In merged mode (MOUNT_MCP_SERVER=true), MCP is at the same port as FastAPI
# In split mode, MCP runs on its own port (MCP_PORT)
_MOUNT_MCP = os.getenv("MOUNT_MCP_SERVER", "true").lower() in ("true", "1", "yes")
_FASTAPI_PORT = int(os.getenv("VITE_FLASK_PORT", "15001"))
_MCP_PORT = int(os.getenv("MCP_PORT", "8001"))

# Use FastAPI port if MCP is mounted there, otherwise use separate MCP_PORT
MCP_PORT = _FASTAPI_PORT if _MOUNT_MCP else _MCP_PORT
MCP_SERVERS = {
    "covalent": {
        "transport": "streamable_http",
        "url": f"http://localhost:{MCP_PORT}/mcp",
    },
}

# Tool Routing Configuration
TOOL_CACHE_DIR = Path.home() / ".cache" / "covalent_action_executor"
TOP_K_TOOLS = 25  # Number of relevant tools/resources to select

# =============================================================================
# MCP CLIENT MANAGEMENT
# =============================================================================
_mcp_client = None
_all_tools = None      # LangChain BaseTool objects (write operations)
_all_resources = None   # ResourceItem objects (read-only operations)
_client_lock = None


class ResourceItem:
    """
    Lightweight wrapper for an MCP resource template.
    Provides .name and .description for semantic search compatibility,
    plus .uri_template for invocation via session.read_resource().
    """
    def __init__(self, name: str, description: str, uri_template: str):
        self.name = name
        self.description = description
        self.uri_template = uri_template

    def __repr__(self) -> str:
        return f"ResourceItem({self.name!r})"


def _expand_uri_template(template: str, params: dict) -> str:
    """
    Expand a URI template with parameters (simple subset of RFC 6570).

    Supports:
      - Path expansion:  {name} → URL-encoded value
      - Query expansion: {?a,b,c} → ?a=val_a&b=val_b (only non-None params)
    """
    import re as _re
    from urllib.parse import quote as _quote

    result = template

    # 1. Handle query expansion {?param1,param2,...}
    qm = _re.search(r'\{\?([^}]+)\}', result)
    if qm:
        keys = [k.strip() for k in qm.group(1).split(',')]
        parts = []
        for k in keys:
            v = params.get(k)
            if v is not None:
                parts.append(f"{k}={_quote(str(v), safe='')}")
        replacement = ('?' + '&'.join(parts)) if parts else ''
        result = result[:qm.start()] + replacement + result[qm.end():]

    # 2. Handle path expansion {name}
    def _replace_path_param(m):
        key = m.group(1)
        v = params.get(key)
        if v is not None:
            return _quote(str(v), safe='')
        return m.group(0)  # leave as-is if not in params

    result = _re.sub(r'\{(\w+)\}', _replace_path_param, result)
    return result


async def get_mcp_client(max_retries: int = 3):
    """
    Get or create the MCP client.

    Returns (client, tools, resources) where:
      - tools: list[BaseTool] from get_tools() — write/action operations
      - resources: list[ResourceItem] from list_resource_templates() — read-only operations
    """
    global _mcp_client, _all_tools, _all_resources, _client_lock

    if _client_lock is None:
        _client_lock = asyncio.Lock()

    async with _client_lock:
        for attempt in range(max_retries):
            try:
                if _mcp_client is None:
                    _mcp_client = MultiServerMCPClient(MCP_SERVERS)

                    # Fetch tools (write operations)
                    _all_tools = await _mcp_client.get_tools()

                    # Fetch resource templates (read-only operations)
                    async with _mcp_client.session("covalent") as session:
                        templates_result = await session.list_resource_templates()
                        # Handle different SDK attribute naming (camelCase vs snake_case)
                        if hasattr(templates_result, 'resourceTemplates'):
                            templates = templates_result.resourceTemplates
                        elif hasattr(templates_result, 'resource_templates'):
                            templates = templates_result.resource_templates
                        else:
                            templates = list(templates_result)

                        _all_resources = []
                        for t in templates:
                            uri_tmpl = t.uriTemplate if hasattr(t, 'uriTemplate') else t.uri_template
                            _all_resources.append(
                                ResourceItem(
                                    name=t.name,
                                    description=t.description or "",
                                    uri_template=uri_tmpl,
                                )
                            )

                    log.info(f"✅ MCP client initialized: {len(_all_tools)} tools, {len(_all_resources)} resources")

                return _mcp_client, _all_tools, _all_resources
            except Exception as e:
                _mcp_client = None
                _all_tools = None
                _all_resources = None
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))
                else:
                    raise ConnectionError(f"Failed to connect to MCP server after {max_retries} attempts: {e}")


async def reset_mcp_client():
    """Reset the MCP client connection."""
    global _mcp_client, _all_tools, _all_resources
    _mcp_client = None
    _all_tools = None
    _all_resources = None


# =============================================================================
# SEMANTIC ROUTING (SEPARATE FOR TOOLS AND RESOURCES)
# =============================================================================

# Cache files for tools and resources
TOOL_CACHE_FILE = TOOL_CACHE_DIR / "tool_embeddings.pkl"
RESOURCE_CACHE_FILE = TOOL_CACHE_DIR / "resource_embeddings.pkl"


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
        """Cache embeddings for a list of items via the Lambda gateway."""
        self._ensure_cache_dir()

        descriptions = [f"{item.name}: {item.description}" for item in items]
        
        # Use the gateway client to generate embeddings via Lambda -> Bedrock
        gateway = get_gateway_client()
        response = gateway.embed_documents(descriptions)
        item_embeddings = response.embeddings

        cache_data = {
            'names': [item.name for item in items],
            'descriptions': descriptions,
            'embeddings': item_embeddings,
            'embedding_model': response.model,  # Track which model generated these
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
            
            # Invalidate cache if it was generated by a different model
            # (e.g. switching from OpenAI to Titan Embed)
            if 'embedding_model' not in cache_data:
                return None  # Old cache from OpenAI - force rebuild

            return items, np.array(cache_data['embeddings']), cache_data['names']

        except Exception:
            return None

    def initialize(self, tools: list, resources: list):
        """
        Initialize the router with pre-separated tools and resources.

        Args:
            tools: list of LangChain BaseTool objects (write/action operations)
            resources: list of ResourceItem objects (read-only operations)
        """
        if self._initialized:
            return

        tools_list = list(tools)
        resources_list = list(resources)
        
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
        
        # Embed the query via the Lambda gateway
        gateway = get_gateway_client()
        query_embedding = np.array(gateway.embed_query(query))

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
        # Get MCP client, tools, and resources separately
        client, tools, resources = await get_mcp_client()
        
        # Initialize tool router if not already done
        if not tool_router._initialized:
            tool_router.initialize(tools, resources)
        
        # Get relevant RESOURCES only (semantic search on resources, not tools)
        relevant_resources = tool_router.get_relevant_resources(
            action_text + " " + existing_context[:500],
            top_k=TOP_K_TOOLS
        )
        
        # Log which resources were shortlisted for research
        log.info(f"📚 Shortlisted {len(relevant_resources)} resources for research:")
        for i, res in enumerate(relevant_resources, 1):
            log.info(f"   {i}. {res.name}")
        
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
3. Be selective - only query what's needed (max 5 resources for complex multi-step actions)
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
        
        log.debug(f"\n{'='*60}")
        log.debug(f"LLM OUTPUT (RESEARCH PHASE)")
        log.debug(f"{'='*60}")
        log.debug(str(response.content))
        log.debug(f"{'='*60}\n")
        
        # Parse which resources to read
        resources_to_read = _parse_resource_selection(response.content)
        
        if not resources_to_read:
            log.info("ℹ️ LLM decided no additional context needed")
            return {
                "status": "success",
                "context": existing_context,
                "resources_read": [],
                "error": None
            }
        
        # Execute resource reads
        gathered_context = []
        resources_read = []
        
        # Build a resource lookup by name for URI expansion
        resource_lookup = {r.name: r for r in resources}
        
        for resource_spec in resources_to_read[:5]:  # Max 5 resources for complex multi-step actions
            resource_name = resource_spec.get("name", "")
            params = resource_spec.get("parameters", {})
            reason = resource_spec.get("reason", "")
            
            try:
                resource_item = resource_lookup.get(resource_name)
                if resource_item is None:
                    log.warning(f"⚠️ Resource '{resource_name}' not found")
                    continue
                
                # Expand URI template with the LLM-provided params
                uri = _expand_uri_template(resource_item.uri_template, params)
                log.info(f"📖 Reading resource: {resource_name} -> {uri}")
                
                # Read the resource via MCP session
                async with client.session("covalent") as session:
                    read_result = await session.read_resource(uri)
                    if read_result.contents:
                        content = read_result.contents[0]
                        text = content.text if hasattr(content, 'text') else str(content)
                    else:
                        text = ""

                # Research phase: log Perplexity (Lambda → api.perplexity.ai) responses for debugging
                if uri.startswith("perplexity://"):
                    _max = 24_000
                    try:
                        _parsed = json.loads(text)
                        _body = json.dumps(_parsed, indent=2, default=str)
                    except (json.JSONDecodeError, TypeError):
                        _body = text
                    if len(_body) > _max:
                        _body = _body[:_max] + f"\n... [truncated for log, total chars={len(text)}]"
                    log.info(
                        "[research/pplx] response from read_resource — "
                        f"name={resource_name!r} uri={uri!r} reason={reason!r}\n{_body}"
                    )
                
                gathered_context.append(f"--- {resource_name} ---\n{text}")
                resources_read.append(resource_name)
                log.info(f"✅ Successfully read {resource_name}")
                
            except Exception as e:
                log.warning(f"⚠️ Failed to read {resource_name}: {e}")
                # Continue with other resources
        
        # Combine all context
        combined_context = existing_context
        if gathered_context:
            combined_context += "\n\n=== Gathered Context ===\n" + "\n\n".join(gathered_context)
        
        log.info(f"✅ Research complete: read {len(resources_read)} resources")
        
        return {
            "status": "success",
            "context": combined_context,
            "resources_read": resources_read,
            "error": None
        }
        
    except GatewayError as e:
        log.error(f"❌ Gateway error during research: {e}")
        return {
            "status": "error",
            "context": existing_context,
            "resources_read": [],
            "error": f"Gateway error: {str(e)}"
        }
    except Exception as e:
        log.error(f"❌ Error in gather_context: {e}")
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
    Parse the LLM response to extract tool call(s) JSON.
    
    Supports two formats:
    1. Multi-action format (preferred):
       {"actions": [{"tool_name": ..., "parameters": {...}, "reasoning": ...}, ...]}
    
    2. Legacy single-action format (backward compatible):
       {"tool_name": ..., "parameters": {...}, "reasoning": ...}
    
    Returns:
        Dict with:
        - "is_multi_action": bool
        - "actions": List[Dict] with tool_name, parameters, reasoning for each action
        Or None if parsing fails
    """
    # Try to find JSON in the response
    # First, try to find a JSON code block
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find JSON with nested objects
        # Match from first { to last }
        start = response_text.find('{')
        end = response_text.rfind('}')
        if start != -1 and end != -1 and end > start:
            json_str = response_text[start:end + 1]
        else:
            return None
    
    try:
        parsed = json.loads(json_str)
        
        # Check for multi-action format
        if "actions" in parsed and isinstance(parsed["actions"], list):
            actions = []
            for i, action in enumerate(parsed["actions"]):
                if isinstance(action, dict) and "tool_name" in action:
                    actions.append({
                        "step_id": i + 1,
                        "tool_name": action.get("tool_name"),
                        "parameters": action.get("parameters", {}),
                        "reasoning": action.get("reasoning", f"Step {i + 1}")
                    })
            
            if actions:
                return {
                    "is_multi_action": len(actions) > 1,
                    "actions": actions,
                    "overall_reasoning": parsed.get("overall_reasoning", "")
                }
            return None
        
        # Legacy single-action format
        if "tool_name" not in parsed:
            return None
        
        return {
            "is_multi_action": False,
            "actions": [{
                "step_id": 1,
                "tool_name": parsed.get("tool_name"),
                "parameters": parsed.get("parameters", {}),
                "reasoning": parsed.get("reasoning", "Action proposed by agent")
            }],
            "overall_reasoning": parsed.get("reasoning", "")
        }
    except json.JSONDecodeError:
        return None


MAX_CONTEXT_CHARS = 30_000

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
        # Truncate context to avoid exceeding API Gateway's 30s timeout.
        # 223K chars caused a 503; 30K keeps the call well under 29s.
        if len(context_data) > MAX_CONTEXT_CHARS:
            log.warning(
                f"⚠️ Truncating context_data from {len(context_data)} to {MAX_CONTEXT_CHARS} chars "
                f"to stay within API Gateway timeout"
            )
            context_data = context_data[:MAX_CONTEXT_CHARS] + "\n\n[... context truncated for length ...]"
        
        # Get MCP client, tools, and resources
        client, tools, resources = await get_mcp_client()
        
        # Initialize tool router if not already done
        if not tool_router._initialized:
            tool_router.initialize(tools, resources)
        
        # Get relevant TOOLS only (semantic search on tools, not resources)
        relevant_tools = tool_router.get_relevant_tools(
            action_text + " " + context_data[:500],  # Include some context in routing
            top_k=TOP_K_TOOLS
        )
        
        # Log which tools were shortlisted for the LLM
        log.info(f"🔧 Shortlisted {len(relevant_tools)} tools for planning:")
        for i, tool in enumerate(relevant_tools, 1):
            log.info(f"   {i}. {tool.name}")
        
        if not relevant_tools:
            return {
                "status": "error",
                "proposed_action": None,
                "error": "No relevant tools found for this action"
            }
        
        # Build tool descriptions for the prompt with explicit required/optional marking
        def format_tool_params(tool):
            """Format tool parameters, clearly marking required vs optional."""
            try:
                schema = None
                
                # Try to get schema from args_schema
                if hasattr(tool, 'args_schema') and tool.args_schema is not None:
                    if hasattr(tool.args_schema, 'model_json_schema'):
                        # It's a Pydantic model class
                        schema = tool.args_schema.model_json_schema()
                    elif isinstance(tool.args_schema, dict):
                        # It's already a dict schema
                        schema = tool.args_schema
                
                # If we have a proper schema with properties, format nicely
                if schema and isinstance(schema, dict) and 'properties' in schema:
                    required_set = set(schema.get('required', []))
                    props = schema.get('properties', {})
                    
                    param_strs = []
                    for name, info in props.items():
                        param_type = info.get('type', 'any')
                        desc = info.get('description', '')
                        if name in required_set:
                            param_strs.append(f"{name} (REQUIRED, {param_type}): {desc}")
                        else:
                            default = info.get('default', 'None')
                            param_strs.append(f"{name} (optional, {param_type}, default={default}): {desc}")
                    
                    return "\n    ".join(param_strs) if param_strs else str(tool.args)
                
                # Fallback: try to format tool.args directly
                if hasattr(tool, 'args') and isinstance(tool.args, dict):
                    param_strs = []
                    for name, info in tool.args.items():
                        if isinstance(info, dict):
                            param_type = info.get('type', 'any')
                            desc = info.get('description', '')
                            # Check if optional via anyOf/oneOf with null
                            is_optional = False
                            if 'anyOf' in info or 'oneOf' in info:
                                types = info.get('anyOf', info.get('oneOf', []))
                                is_optional = any(t.get('type') == 'null' for t in types)
                            if 'default' in info:
                                is_optional = True
                            
                            if is_optional:
                                param_strs.append(f"{name} (optional, {param_type}): {desc}")
                            else:
                                param_strs.append(f"{name} (REQUIRED, {param_type}): {desc}")
                        else:
                            param_strs.append(f"{name}: {info}")
                    return "\n    ".join(param_strs) if param_strs else str(tool.args)
                
                return str(tool.args)
            except Exception:
                return str(tool.args)
        
        tool_descriptions = "\n".join([
            f"- {tool.name}: {tool.description}\n  Parameters:\n    {format_tool_params(tool)}"
            for tool in relevant_tools
        ])
        
        # Log tool descriptions for debugging (truncated)
        log.info(f"📋 Tool descriptions for planning (first 2000 chars):\n{tool_descriptions[:2000]}")
        
        # #region agent log
        import time as _time_mod
        _debug_log_path = "/Users/hem/Downloads/covalent-new/.cursor/debug.log"
        _dl_ts = int(_time_mod.time() * 1000)
        _dl_tool_desc_len = len(tool_descriptions)
        _dl_context_len = len(context_data)
        _dl_action_len = len(action_text)
        try:
            with open(_debug_log_path, "a") as _dlf:
                _dlf.write(json.dumps({"id":f"log_{_dl_ts}_prompt_sizes","timestamp":_dl_ts,"location":"action_executor.py:plan_action","message":"Prompt sizes before gateway call","data":{"tool_desc_chars":_dl_tool_desc_len,"context_data_chars":_dl_context_len,"action_text_chars":_dl_action_len,"max_tokens_configured":3072},"runId":"post-fix-v2","hypothesisId":"H1,H3,H4"}) + "\n")
        except: pass
        # #endregion
        
        # Get passable outputs info for the prompt
        passable_outputs_info = format_passable_outputs_for_prompt()
        
        system_prompt = f"""You are an action planning assistant.

Your task is to analyze the user's action and propose the tool(s) needed to accomplish it.
Make sure you include ALL actions that are needed to accomplish the user's action. For example, if you need 
to edit a specific document, you should include the action to fetch the document (to get the document ID) and the action to edit the document with
the desired content. 
ENSURE THAT THE ENTIRE CHAIN OF ACTIONS IS COMPLETE. THERE'S NO MISSING PARAMETER THAT ANY OF THE ACTIONS FURTHER REQUIRES
Every parameter that an action requires either must be provided directly or should be passed in as a cross-step dependency
unless this is something that the user is expected to fill in directly.

CRITICAL - KEEP OUTPUT CONCISE:
- Keep ALL parameters SHORT and compact (under 500 chars each)
- For document content: provide a BRIEF outline/summary (2-3 sentences max), NOT full document text
- For text/content parameters: use "[Content to be generated]" placeholder if content is long
- The user will fill in detailed content after reviewing the plan
- Prefer SINGLE actions when possible - avoid multi-step plans unless absolutely necessary

EMAIL FORMATTING:
- For email body content (send_email, create_draft), use PLAIN TEXT only
- Do NOT use markdown formatting (no **bold**, no *italic*, no bullet points with -)
- Use simple line breaks and plain dashes for lists if needed
- Keep emails professional and readable as plain text

IMPORTANT INSTRUCTIONS:
1. Analyze if the action requires ONE or MULTIPLE tools
2. If the action involves multiple distinct operations (e.g., "create a doc AND add content to it"), propose MULTIPLE actions
3. If the action is simple and requires only one tool, propose just that one
4. **CRITICAL**: You MUST fill in ALL parameters marked as REQUIRED - the action WILL FAIL if any required parameter is missing
5. Use the context data to infer missing information (emails, names, dates, etc.)
6. If a REQUIRED parameter's value is unknown, use a placeholder like "[FILL IN: description]" - NEVER omit it
7. DO NOT execute any tools - just propose them with all parameters filled

PARAMETER REQUIREMENTS:
- Every parameter marked "(REQUIRED, ...)" in the tool description MUST appear in your output
- If you see 3 required parameters, your output MUST have all 3 - no exceptions
- Missing required parameters will cause execution to fail

CROSS-STEP DEPENDENCIES:
When a later step needs output from an earlier step (e.g., step 2 needs the document ID from step 1),
use variable references with this syntax: {{{{$N.field_name}}}}
  - N is the step number (1-indexed)
  - field_name is the output field from that step

Example: If step 1 creates a document, step 2 can reference its ID as: {{{{$1.id}}}}

AVAILABLE PASSABLE OUTPUTS BY TOOL:
{passable_outputs_info}

The user will review and can edit your proposed parameters before execution.

OUTPUT FORMAT - Return ONLY valid JSON with NO additional text:
{{
    "actions": [
        {{
            "tool_name": "first_tool_name",
            "parameters": {{
                "param1": "value1"
            }},
            "reasoning": "Brief explanation for this action"
        }},
        {{
            "tool_name": "second_tool_name",
            "parameters": {{
                "document_id": "{{{{$1.id}}}}",
                "other_param": "value"
            }},
            "reasoning": "Brief explanation - uses document ID from step 1"
        }}
    ],
    "overall_reasoning": "Brief explanation of the overall plan"
}}

For SINGLE actions, still use the same format with just one item in the actions array."""

        user_prompt = f"""Available tools:
{tool_descriptions}

Action to plan: {action_text}

Context available:
{context_data}

Analyze this action and output a single JSON object with the tool call."""

        # Call the Gateway (Lambda -> Bedrock)
        gateway = get_gateway_client()
        
        # #region agent log
        import time as _time_mod2
        _dl_pre_call_ts = int(_time_mod2.time() * 1000)
        _dl_sys_prompt_len = len(system_prompt)
        _dl_user_prompt_len = len(user_prompt)
        _dl_total_prompt_chars = _dl_sys_prompt_len + _dl_user_prompt_len
        try:
            with open(_debug_log_path, "a") as _dlf:
                _dlf.write(json.dumps({"id":f"log_{_dl_pre_call_ts}_pre_gateway","timestamp":_dl_pre_call_ts,"location":"action_executor.py:plan_action:pre_gateway","message":"About to call gateway.generate","data":{"system_prompt_chars":_dl_sys_prompt_len,"user_prompt_chars":_dl_user_prompt_len,"total_prompt_chars":_dl_total_prompt_chars,"gateway_timeout":gateway.timeout,"gateway_model":gateway.default_model},"runId":"post-fix-v2","hypothesisId":"H1,H3"}) + "\n")
        except: pass
        # #endregion
        
        response = gateway.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=3072,
            temperature=0.0,  # Deterministic
        )
        
        # #region agent log
        _dl_post_call_ts = int(_time_mod2.time() * 1000)
        _dl_gateway_duration = _dl_post_call_ts - _dl_pre_call_ts
        try:
            with open(_debug_log_path, "a") as _dlf:
                _dlf.write(json.dumps({"id":f"log_{_dl_post_call_ts}_post_gateway","timestamp":_dl_post_call_ts,"location":"action_executor.py:plan_action:post_gateway","message":"Gateway call completed","data":{"duration_ms":_dl_gateway_duration,"response_len":len(response.content),"input_tokens":response.input_tokens,"output_tokens":response.output_tokens,"stop_reason":response.stop_reason,"response_preview":response.content[:500],"response_tail":response.content[-200:] if len(response.content) > 200 else ""},"runId":"post-fix-v2","hypothesisId":"H1,H2,H3,H4,H5"}) + "\n")
        except: pass
        # #endregion
        
        log.debug(f"\n{'='*60}")
        log.debug(f"LLM OUTPUT (PLANNING PHASE)")
        log.debug(f"{'='*60}")
        log.debug(str(response.content))
        log.debug(f"{'='*60}\n")
        
        # Parse the response (now supports multi-action)
        parsed_response = _parse_tool_response(response.content)
        
        if not parsed_response:
            # #region agent log
            try:
                import time as _time_mod_parse
                _dl_parse_fail_ts = int(_time_mod_parse.time() * 1000)
                with open(_debug_log_path, "a") as _dlf:
                    _dlf.write(json.dumps({"id":f"log_{_dl_parse_fail_ts}_parse_fail","timestamp":_dl_parse_fail_ts,"location":"action_executor.py:plan_action:parse_fail","message":"Failed to parse tool response","data":{"full_response":response.content,"response_len":len(response.content),"stop_reason":response.stop_reason,"input_tokens":response.input_tokens,"output_tokens":response.output_tokens,"has_closing_brace":response.content.rstrip().endswith("}")},"runId":"post-fix-v2","hypothesisId":"H1,H2,H3,H4,H5"}) + "\n")
            except: pass
            # #endregion
            return {
                "status": "error",
                "proposed_actions": None,
                "is_multi_action": False,
                "error": f"Failed to parse tool call from LLM response. Response: {response.content[:200]}"
            }
        
        return {
            "status": "success",
            "proposed_actions": parsed_response["actions"],
            "is_multi_action": parsed_response["is_multi_action"],
            "overall_reasoning": parsed_response.get("overall_reasoning", ""),
            "error": None
        }
        
    except GatewayError as e:
        log.error(f"❌ Gateway error: {e}")
        # #region agent log
        try:
            import time as _time_mod3
            _dl_err_ts = int(_time_mod3.time() * 1000)
            with open("/Users/hem/Downloads/covalent-new/.cursor/debug.log", "a") as _dlf:
                _dlf.write(json.dumps({"id":f"log_{_dl_err_ts}_gateway_error","timestamp":_dl_err_ts,"location":"action_executor.py:plan_action:except","message":"GatewayError caught in plan_action","data":{"error_message":str(e),"status_code":getattr(e,'status_code',None)},"runId":"run1","hypothesisId":"H1,H2,H3,H4,H5"}) + "\n")
        except: pass
        # #endregion
        return {
            "status": "error",
            "proposed_action": None,
            "error": f"Gateway error: {str(e)}"
        }
    except ConnectionError as e:
        log.error(f"❌ MCP connection error: {e}")
        return {
            "status": "error",
            "proposed_action": None,
            "error": f"Connection error: {str(e)}"
        }
    except Exception as e:
        log.error(f"❌ Error in plan_action: {e}")
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
        client, tools, resources = await get_mcp_client()
        
        log.info(f"🚀 Executing {tool_name} with parameters: {parameters}")
        
        # Find the tool by name
        tool_lookup = {t.name: t for t in tools}
        tool = tool_lookup.get(tool_name)
        
        if tool is None:
            return {
                "status": "error",
                "result": None,
                "error": f"Tool '{tool_name}' not found"
            }
        
        # Validate required parameters before execution
        # LangChain MCP tools store param info in tool.args (dict with JSON schema info)
        missing_params = []
        try:
            schema = None
            
            # Try to get schema from args_schema if it's a Pydantic model
            if hasattr(tool, 'args_schema') and tool.args_schema is not None:
                if hasattr(tool.args_schema, 'model_json_schema'):
                    # It's a Pydantic model class
                    schema = tool.args_schema.model_json_schema()
                elif isinstance(tool.args_schema, dict):
                    # It's already a dict schema
                    schema = tool.args_schema
            
            # If we got a schema, extract required params from it
            if schema and isinstance(schema, dict):
                required_params = schema.get('required', [])
                for param_name in required_params:
                    if param_name not in parameters:
                        missing_params.append(param_name)
            elif hasattr(tool, 'args') and isinstance(tool.args, dict):
                # Fallback: check args dict structure (JSON schema format)
                # tool.args is typically {'param_name': {'type': '...', ...}, ...}
                for param_name, param_info in tool.args.items():
                    is_required = True
                    if isinstance(param_info, dict):
                        # Check various ways a param might be marked optional
                        if 'default' in param_info:
                            is_required = False
                        # Check if type is Optional (contains 'null' in anyOf/oneOf)
                        elif 'anyOf' in param_info or 'oneOf' in param_info:
                            types = param_info.get('anyOf', param_info.get('oneOf', []))
                            if any(t.get('type') == 'null' for t in types):
                                is_required = False
                    
                    if is_required and param_name not in parameters:
                        missing_params.append(param_name)
        except Exception as e:
            log.warning(f"⚠️ Could not validate parameters for {tool_name}: {e}")
        
        if missing_params:
            return {
                "status": "error",
                "result": None,
                "error": f"Missing required parameters for '{tool_name}': {', '.join(missing_params)}. "
                         f"Provided: {list(parameters.keys())}"
            }
        
        # Execute the tool via LangChain's ainvoke
        result = await tool.ainvoke(parameters)
        
        # Check if the tool itself reported a failure (MCP tools can return
        # {success: false, ...} without raising an exception).
        result_data = None
        if isinstance(result, dict):
            result_data = result
        elif isinstance(result, str):
            try:
                result_data = json.loads(result)
            except (ValueError, TypeError):
                pass

        if isinstance(result_data, dict) and result_data.get("success") is False:
            error_msg = (
                result_data.get("error")
                or result_data.get("message")
                or result_data.get("detail")
                or "Tool execution failed"
            )
            log.error(f"❌ Tool returned failure response: {error_msg}")
            return {
                "status": "error",
                "result": None,
                "error": error_msg,
            }

        # Handle list-of-content-blocks response from some MCP adapters:
        # langchain_mcp_adapters sometimes returns [TextContent(type='text', text='{"..."}')]
        if isinstance(result, list) and result_data is None:
            texts = []
            for item in result:
                text = getattr(item, 'text', None) or (item.get('text') if isinstance(item, dict) else None)
                if text:
                    texts.append(text)
            combined = "\n".join(texts) if texts else str(result)
            try:
                result_data = json.loads(combined)
            except (ValueError, TypeError):
                result_data = {"message": combined} if combined else None

        # Prefer the parsed/structured result over the raw string
        final_result = result_data if result_data is not None else result

        log.info(f"✅ Tool execution completed")
        
        return {
            "status": "success",
            "result": final_result,
            "error": None
        }
        
    except Exception as e:
        log.error(f"❌ Error executing action: {e}")
        import traceback
        traceback.print_exc()
        _err_msg = str(e)
        _is_connect_err = "ConnectError" in type(e).__name__ or "connection" in _err_msg.lower() or "All connection attempts failed" in _err_msg
        if _is_connect_err:
            if _MOUNT_MCP:
                _hint = f"MCP server unreachable at http://localhost:{MCP_PORT}/mcp. Ensure FastAPI server is running with MCP mounted."
            else:
                _hint = f"MCP server unreachable at http://localhost:{MCP_PORT}/mcp. Start it with: bash covalent_mcp/start_mcp.sh (or use start_servers.sh)"
            return {"status": "error", "result": None, "error": _hint}
        return {
            "status": "error",
            "result": None,
            "error": f"Execution error: {str(e)}"
        }


def resolve_variables(params: Any, step_outputs: Dict[str, Dict[str, Any]]) -> Any:
    """
    Resolve variable references in parameters using outputs from previous steps.
    
    Variable syntax: {{$N.field_name}} where N is the step number (1-indexed)
    
    Args:
        params: Parameters dict (or any nested structure) that may contain variable refs
        step_outputs: Dict mapping step number (as string) to that step's output dict
                      e.g. {"1": {"id": "abc123", "url": "..."}, "2": {...}}
    
    Returns:
        A new structure with all variable references replaced with actual values
    """
    if isinstance(params, str):
        # Replace all {{$N.field}} patterns
        def replacer(match):
            step_num = match.group(1)
            field = match.group(2)
            step_data = step_outputs.get(step_num, {})
            value = step_data.get(field)
            if value is not None:
                return str(value)
            # Keep the original if not found (will show as unresolved)
            log.warning(f"⚠️ Variable reference {{{{${step_num}.{field}}}}} not found in step outputs")
            return match.group(0)
        
        return re.sub(r'\{\{\$(\d+)\.(\w+)\}\}', replacer, params)
    
    elif isinstance(params, dict):
        return {k: resolve_variables(v, step_outputs) for k, v in params.items()}
    
    elif isinstance(params, list):
        return [resolve_variables(v, step_outputs) for v in params]
    
    else:
        return params


def extract_passable_outputs(result: Any, tool_name: str) -> Dict[str, Any]:
    """
    Extract passable output fields from a tool's result.
    
    Uses the declared passable_outputs from the tool's display schema,
    but falls back to all top-level keys if none declared.
    
    Args:
        result: The tool's execution result
        tool_name: Name of the tool (to look up passable_outputs)
    
    Returns:
        Dict of field_name -> value for passable outputs
    """
    if result is None:
        return {}
    
    # Ensure result is a dict
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return {"_raw": result}
    
    if not isinstance(result, dict):
        return {"_raw": str(result)}
    
    # Get declared passable outputs for this tool
    declared_outputs = get_passable_outputs(tool_name)
    
    if declared_outputs:
        # Only extract declared fields
        extracted = {}
        for output in declared_outputs:
            if output.key in result:
                extracted[output.key] = result[output.key]
        return extracted
    else:
        # Fallback: extract all top-level keys except 'success' and 'message'
        return {k: v for k, v in result.items() if k not in ('success', 'message')}


async def execute_action_chain(actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Execute a sequence of approved actions sequentially with variable passing.
    
    Actions are executed in order. If one fails, execution STOPS immediately (fail-fast).
    Outputs from each step are accumulated and can be referenced by subsequent steps
    using variable syntax: {{$N.field_name}}
    
    Args:
        actions: List of action dicts, each with:
            - step_id: int
            - tool_name: str
            - parameters: dict (may contain {{$N.field}} variable references)
            
    Returns:
        {
            "status": "success" | "error",
            "results": [
                {"step_id": 1, "tool_name": "...", "status": "success", "result": {...}},
                ...
            ],
            "summary": {
                "total": int,
                "succeeded": int,
                "failed": int
            },
            "failed_at_step": int | None  (only set if status is "error")
        }
    """
    results = []
    succeeded = 0
    failed = 0
    step_outputs = {}  # Accumulated outputs: {"1": {...}, "2": {...}}
    
    log.info(f"\n{'='*60}")
    log.info(f"🚀 EXECUTING ACTION CHAIN ({len(actions)} actions)")
    log.info(f"{'='*60}")
    
    for action in actions:
        step_id = action.get("step_id", len(results) + 1)
        tool_name = action.get("tool_name", "")
        raw_parameters = action.get("parameters", {})
        
        # Resolve variable references from previous steps
        resolved_parameters = resolve_variables(raw_parameters, step_outputs)
        
        # Log what we're doing
        log.info(f"\n📌 Step {step_id}: {tool_name}")
        if raw_parameters != resolved_parameters:
            log.info(f"   📎 Resolved variables from previous steps")
            log.debug(f"   Raw params: {raw_parameters}")
            log.debug(f"   Resolved params: {resolved_parameters}")
        
        try:
            exec_result = await execute_action(tool_name, resolved_parameters)
            
            if exec_result["status"] == "success":
                succeeded += 1
                
                # Extract and store passable outputs for subsequent steps
                passable = extract_passable_outputs(exec_result["result"], tool_name)
                step_outputs[str(step_id)] = passable
                log.info(f"   ✅ Step {step_id} succeeded")
                if passable:
                    log.info(f"   📤 Passable outputs: {list(passable.keys())}")
                
                results.append({
                    "step_id": step_id,
                    "tool_name": tool_name,
                    "status": "success",
                    "result": exec_result["result"],
                    "passable_outputs": passable
                })
            else:
                failed += 1
                results.append({
                    "step_id": step_id,
                    "tool_name": tool_name,
                    "status": "error",
                    "error": exec_result["error"]
                })
                log.error(f"   ❌ Step {step_id} failed: {exec_result['error']}")
                
                # FAIL-FAST: Stop immediately on error
                log.info(f"\n{'='*60}")
                log.info(f"⛔ CHAIN ABORTED at step {step_id}: {exec_result['error']}")
                log.info(f"📊 Completed {succeeded}/{len(actions)} steps before failure")
                log.info(f"{'='*60}\n")
                
                return {
                    "status": "error",
                    "results": results,
                    "summary": {
                        "total": len(actions),
                        "succeeded": succeeded,
                        "failed": 1
                    },
                    "failed_at_step": step_id,
                    "error": exec_result["error"]
                }
                
        except Exception as e:
            failed += 1
            results.append({
                "step_id": step_id,
                "tool_name": tool_name,
                "status": "error",
                "error": str(e)
            })
            log.error(f"   ❌ Step {step_id} exception: {e}")
            
            # FAIL-FAST: Stop immediately on exception
            log.info(f"\n{'='*60}")
            log.info(f"⛔ CHAIN ABORTED at step {step_id}: {e}")
            log.info(f"📊 Completed {succeeded}/{len(actions)} steps before failure")
            log.info(f"{'='*60}\n")
            
            return {
                "status": "error",
                "results": results,
                "summary": {
                    "total": len(actions),
                    "succeeded": succeeded,
                    "failed": 1
                },
                "failed_at_step": step_id,
                "error": str(e)
            }
    
    # All steps succeeded!
    log.info(f"\n{'='*60}")
    log.info(f"✅ CHAIN COMPLETE: All {len(actions)} steps succeeded!")
    log.info(f"{'='*60}\n")
    
    return {
        "status": "success",
        "results": results,
        "summary": {
            "total": len(actions),
            "succeeded": succeeded,
            "failed": 0
        }
    }


# =============================================================================
# COMBINED FLOW FUNCTIONS
# =============================================================================

async def research_and_plan(action_text: str, initial_context: str = "") -> Dict[str, Any]:
    """
    Combined research + planning flow.
    
    This is the main entry point for the action executor.
    1. Gathers context by reading relevant resources
    2. Plans the action(s) using gathered context
    
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
            "proposed_actions": [
                {
                    "step_id": int,
                    "tool_name": str,
                    "parameters": dict,
                    "reasoning": str
                }, ...
            ] | None,
            "is_multi_action": bool,
            "overall_reasoning": str,
            "error": str | None
        }
    """
    # Phase 0: Research
    log.info("=" * 40)
    log.info("🔍 PHASE 0: RESEARCH")
    log.info("=" * 40)
    
    research_result = await gather_context(action_text, initial_context)
    
    research_info = {
        "resources_read": research_result.get("resources_read", []),
        "context_gathered": research_result.get("context", initial_context)
    }
    
    if research_result["status"] == "error":
        log.warning(f"⚠️ Research had issues (continuing): {research_result['error']}")
    
    # Phase 1: Planning
    log.info("\n" + "=" * 40)
    log.info("📋 PHASE 1: PLANNING")
    log.info("=" * 40)
    
    plan_result = await plan_action(action_text, research_info["context_gathered"])
    
    if plan_result["status"] == "error":
        return {
            "status": "error",
            "research": research_info,
            "proposed_actions": None,
            "is_multi_action": False,
            "overall_reasoning": "",
            "error": plan_result["error"]
        }
    
    num_actions = len(plan_result.get("proposed_actions", []))
    log.info(f"✅ Planning complete: {num_actions} action(s) proposed")
    
    return {
        "status": "success",
        "research": research_info,
        "proposed_actions": plan_result["proposed_actions"],
        "is_multi_action": plan_result.get("is_multi_action", False),
        "overall_reasoning": plan_result.get("overall_reasoning", ""),
        "error": None
    }


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

async def rebuild_tool_cache():
    """Rebuild the tool embedding cache. Run when adding new tools."""
    log.info("🔄 Rebuilding tool cache...")
    client, tools, resources = await get_mcp_client()
    tool_router._initialized = False  # Force re-initialization
    tool_router.initialize(tools, resources)
    log.info("✅ Tool cache rebuilt successfully!")


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
        client, tools, resources = await get_mcp_client()
        result["mcp_status"] = "healthy"
        result["tools_count"] = len(tools)
        result["resources_count"] = len(resources)
        result["tool_names"] = [t.name for t in tools]
        result["resource_names"] = [r.name for r in resources]
        log.info(f"✅ MCP health check passed: {len(tools)} tools, {len(resources)} resources")
    except Exception as e:
        result["mcp_status"] = "unhealthy"
        result["mcp_error"] = str(e)
        log.error(f"❌ MCP health check failed: {e}")
    
    # Check Gateway
    try:
        gateway = get_gateway_client()
        gateway_health = gateway.health()
        result["gateway_status"] = gateway_health.get("status", "unknown")
        result["gateway_model"] = gateway_health.get("default_model", "unknown")
        log.info(f"✅ Gateway health check passed: {result['gateway_model']}")
    except GatewayError as e:
        result["gateway_status"] = "unhealthy"
        result["gateway_error"] = str(e)
        log.error(f"❌ Gateway health check failed: {e}")
    except Exception as e:
        result["gateway_status"] = "unhealthy"
        result["gateway_error"] = str(e)
        log.error(f"❌ Gateway health check failed: {e}")
    
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
    """Test the action executor with full 3-phase flow (multi-action support)."""
    
    # Test action - this one could trigger multi-action
    action_text = "Reply to Ritesh's latest email about the project update"
    
    # Initial context (could come from the graph or be empty)
    initial_context = """
    Known information:
    - Ritesh is a team member (ritesh@example.com)
    - We're working on Q1 roadmap
    """
    
    log.info("=" * 60)
    log.info("PHASE 0: RESEARCH (Context Gathering)")
    log.info("=" * 60)
    
    # Phase 0: Gather context by reading relevant resources
    research_result = await gather_context(action_text, initial_context)
    
    if research_result["status"] == "error":
        log.warning(f"⚠️ Research had issues: {research_result['error']}")
        # Continue anyway with whatever context we have
    
    log.info(f"\n📚 Resources read: {research_result['resources_read']}")
    log.info(f"   Context length: {len(research_result['context'])} chars")
    
    log.info("\n" + "=" * 60)
    log.info("PHASE 1: PLANNING")
    log.info("=" * 60)
    
    # Phase 1: Plan the action(s) using gathered context
    plan_result = await plan_action(action_text, research_result["context"])
    
    if plan_result["status"] == "error":
        log.error(f"❌ Planning failed: {plan_result['error']}")
        return
    
    proposed_actions = plan_result["proposed_actions"]
    is_multi = plan_result.get("is_multi_action", False)
    
    log.info(f"\n📋 Proposed Actions ({len(proposed_actions)} action(s), multi={is_multi}):")
    for action in proposed_actions:
        log.info(f"\n   Step {action['step_id']}: {action['tool_name']}")
        log.info(f"   Parameters: {json.dumps(action['parameters'], indent=4)}")
        log.info(f"   Reasoning: {action['reasoning']}")
    
    log.info("\n" + "=" * 60)
    log.info("PHASE 2: EXECUTION (simulated approval)")
    log.info("=" * 60)
    
    # In real app, we'd wait for user approval here
    log.info("⏸️  [In real app: User reviews and approves/edits parameters here]")
    
    # Phase 2: Execute the action(s)
    if len(proposed_actions) == 1:
        # Single action
        action = proposed_actions[0]
        exec_result = await execute_action(action['tool_name'], action['parameters'])
        
        if exec_result["status"] == "error":
            log.error(f"❌ Execution failed: {exec_result['error']}")
            return
        
        log.info(f"\n✅ Action executed successfully!")
        log.info(f"   Result: {exec_result['result']}")
    else:
        # Multi-action chain
        chain_result = await execute_action_chain(proposed_actions)
        
        log.info(f"\n📊 Chain execution complete:")
        log.info(f"   Status: {chain_result['status']}")
        log.info(f"   Summary: {chain_result['summary']['succeeded']}/{chain_result['summary']['total']} succeeded")
        
        for result in chain_result['results']:
            status_icon = "✅" if result['status'] == "success" else "❌"
            log.info(f"\n   {status_icon} Step {result['step_id']} ({result['tool_name']}): {result['status']}")
            if result['status'] == 'success':
                log.info(f"      Result: {str(result.get('result', ''))[:100]}...")
            else:
                log.info(f"      Error: {result.get('error', 'Unknown')}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "--cache":
            asyncio.run(rebuild_tool_cache())
        elif command == "--health":
            result = asyncio.run(health_check())
            log.info(str(result))
        elif command == "--help":
            log.info("""
Usage: python action_executor.py [command]

Commands:
  (no args)   Run test example
  --cache     Rebuild tool embedding cache
  --health    Check MCP server health
  --help      Show this help message
            """)
        else:
            log.error(f"Unknown command: {command}")
            log.info("Use --help for usage information")
    else:
        asyncio.run(main())
