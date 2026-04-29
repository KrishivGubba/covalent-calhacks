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
import time
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
            default_model="claude-4.6-sonnet",
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
# ITERATIVE RESEARCH LOOP CONFIGURATION
# =============================================================================
# Budgets for the agentic research+plan loop. Each is env-overridable.
# When any of these is exhausted we return an error to the caller instead of
# forcing a (potentially incomplete) plan.

MAX_RESEARCH_TURNS = int(os.getenv("RESEARCH_MAX_TURNS", "20"))
MAX_RESOURCE_READS = int(os.getenv("RESEARCH_MAX_READS", "20"))
RESEARCH_WALL_CLOCK_S = float(os.getenv("RESEARCH_WALL_CLOCK_S", "90"))
MAX_DRAFT_ATTEMPTS = int(os.getenv("RESEARCH_MAX_DRAFTS", "6"))

# Outer plan->execute->continue meta-loop budget. Caps how many iterations of
# (plan, approve, execute) we'll run against a single higher-level task before
# forcing termination with an error. Iteration 1 is the initial /plan_action
# call; iterations 2..N are subsequent /continue_task calls.
MAX_OUTER_ITERATIONS = int(os.getenv("RESEARCH_MAX_OUTER_ITERATIONS", "5"))

# Scratchpad bounds (keeps the rolling prompt below MAX_CONTEXT_CHARS).
SCRATCHPAD_PER_READ_CHARS = 6_000
SCRATCHPAD_TOTAL_CHARS = 30_000

# Prior-iterations bounds — keep the journal compact in the prompt so the
# planner still has room for resources + scratchpad.
PRIOR_ITERATION_PER_RESULT_CHARS = 1_500
PRIOR_ITERATIONS_TOTAL_CHARS = 12_000

# Strict policy: these markers indicate an unfinished / placeholder value and
# should cause plan validation to fail.
FORBIDDEN_PLACEHOLDER_MARKERS = (
    "[FILL IN",
    "[Content to be generated",
    "TODO:",
    "TBD",
    "<placeholder",
    "REPLACE_ME",
)

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
# ITERATIVE RESEARCH LOOP HELPERS
# =============================================================================

def format_tool_params(tool) -> str:
    """
    Format a tool's parameter schema as a human-readable multi-line string,
    clearly marking REQUIRED vs optional parameters.

    Shared between `plan_action` (single-shot path) and the iterative research
    loop, so both use an identical representation of the tool surface.
    """
    try:
        schema = None

        if hasattr(tool, 'args_schema') and tool.args_schema is not None:
            if hasattr(tool.args_schema, 'model_json_schema'):
                schema = tool.args_schema.model_json_schema()
            elif isinstance(tool.args_schema, dict):
                schema = tool.args_schema

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

        if hasattr(tool, 'args') and isinstance(tool.args, dict):
            param_strs = []
            for name, info in tool.args.items():
                if isinstance(info, dict):
                    param_type = info.get('type', 'any')
                    desc = info.get('description', '')
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
        return str(getattr(tool, 'args', ''))


def _tool_required_params(tool) -> List[str]:
    """
    Return the list of REQUIRED parameter names for an MCP tool.

    Mirrors the logic in `format_tool_params()` / `execute_action()`:
      1. Prefer `tool.args_schema.model_json_schema()["required"]` if available.
      2. Otherwise walk `tool.args` (JSON schema dict) and treat a param as
         required unless it has a `default` or its anyOf/oneOf contains `null`.
    """
    try:
        schema = None
        if hasattr(tool, 'args_schema') and tool.args_schema is not None:
            if hasattr(tool.args_schema, 'model_json_schema'):
                schema = tool.args_schema.model_json_schema()
            elif isinstance(tool.args_schema, dict):
                schema = tool.args_schema
        if schema and isinstance(schema, dict):
            return list(schema.get('required', []) or [])

        if hasattr(tool, 'args') and isinstance(tool.args, dict):
            required = []
            for name, info in tool.args.items():
                if not isinstance(info, dict):
                    required.append(name)
                    continue
                if 'default' in info:
                    continue
                types = info.get('anyOf', info.get('oneOf', []))
                if any(isinstance(t, dict) and t.get('type') == 'null' for t in types):
                    continue
                required.append(name)
            return required
    except Exception as e:
        log.warning(f"⚠️ Could not introspect required params for tool {getattr(tool, 'name', '?')}: {e}")
    return []


_VARIABLE_REF_RE = re.compile(r'\{\{\$(\d+)\.(\w+)\}\}')


def _contains_forbidden_placeholder(value: Any) -> Optional[str]:
    """Return the first forbidden marker found in a string-like value, else None."""
    if not isinstance(value, str):
        return None
    for marker in FORBIDDEN_PLACEHOLDER_MARKERS:
        if marker in value:
            return marker
    return None


def _is_empty_value(value: Any) -> bool:
    """A param counts as empty if it's None, or an empty string/list/dict after stripping."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, dict)) and len(value) == 0:
        return True
    return False


def _validate_plan(actions: List[Dict[str, Any]], tool_lookup: Dict[str, Any]) -> List[str]:
    """
    Strict programmatic validation of a drafted plan.

    Returns a list of human-readable issues. Empty list means the plan passes.

    Rules:
      1. Every action must have a known tool_name.
      2. Every REQUIRED parameter of that tool must be present, non-empty, and
         free of forbidden placeholder markers (FILL IN, TODO, TBD, etc.).
      3. Cross-step refs `{{$N.field}}` are permitted, but must reference a
         strictly earlier step AND a field declared passable by that step's
         tool (per `get_passable_outputs()`).
    """
    issues: List[str] = []
    if not actions:
        return ["Plan contains no actions."]

    # Precompute each step's passable output keys so we can validate $N.field refs.
    step_passable_keys: Dict[int, set] = {}

    for idx, action in enumerate(actions, start=1):
        step_id = action.get("step_id", idx)
        prefix = f"Step {step_id}"

        tool_name = action.get("tool_name")
        if not tool_name:
            issues.append(f"{prefix}: missing `tool_name`.")
            continue

        tool = tool_lookup.get(tool_name)
        if tool is None:
            issues.append(f"{prefix}: unknown tool `{tool_name}`.")
            continue

        params = action.get("parameters") or {}
        if not isinstance(params, dict):
            issues.append(f"{prefix}: `parameters` must be an object.")
            continue

        # Required-param validation.
        required = _tool_required_params(tool)
        for req in required:
            if req not in params:
                issues.append(
                    f"{prefix} ({tool_name}): missing required parameter `{req}`."
                )
                continue
            value = params[req]
            if _is_empty_value(value):
                issues.append(
                    f"{prefix} ({tool_name}): required parameter `{req}` is empty."
                )
                continue
            marker = _contains_forbidden_placeholder(value)
            if marker:
                issues.append(
                    f"{prefix} ({tool_name}): required parameter `{req}` contains "
                    f"forbidden placeholder `{marker}`. Look up the real value via a "
                    "read-only resource or write the final content."
                )

        # Placeholder scan across ALL params (not just required), since optional
        # text fields with placeholders would also be broken if submitted.
        for pname, pvalue in params.items():
            marker = _contains_forbidden_placeholder(pvalue)
            if marker and pname not in required:
                issues.append(
                    f"{prefix} ({tool_name}): parameter `{pname}` contains forbidden "
                    f"placeholder `{marker}`."
                )

        # Cross-step variable reference validation.
        def _walk_for_refs(node):
            if isinstance(node, str):
                for m in _VARIABLE_REF_RE.finditer(node):
                    yield int(m.group(1)), m.group(2), m.group(0)
            elif isinstance(node, dict):
                for v in node.values():
                    yield from _walk_for_refs(v)
            elif isinstance(node, list):
                for v in node:
                    yield from _walk_for_refs(v)

        for ref_step, ref_field, ref_literal in _walk_for_refs(params):
            if ref_step >= step_id:
                issues.append(
                    f"{prefix} ({tool_name}): reference `{ref_literal}` points to a "
                    f"non-earlier step (step {ref_step} must be < {step_id})."
                )
                continue
            allowed = step_passable_keys.get(ref_step)
            if allowed is None:
                issues.append(
                    f"{prefix} ({tool_name}): reference `{ref_literal}` points to "
                    f"step {ref_step} which does not exist earlier in the plan."
                )
                continue
            if ref_field not in allowed:
                issues.append(
                    f"{prefix} ({tool_name}): reference `{ref_literal}` uses field "
                    f"`{ref_field}` which is not a declared passable output of step "
                    f"{ref_step}. Allowed fields: {sorted(allowed) or '(none)'}."
                )

        # Record this step's passable outputs for any later-step refs.
        try:
            declared = get_passable_outputs(tool_name) or []
            step_passable_keys[step_id] = {o.key for o in declared}
        except Exception as e:
            log.warning(f"⚠️ Could not fetch passable outputs for {tool_name}: {e}")
            step_passable_keys[step_id] = set()

    return issues


def _truncate(text: str, n: int) -> str:
    """Truncate a string to at most n chars, with a marker suffix when clipped."""
    if text is None:
        return ""
    if len(text) <= n:
        return text
    return text[:n] + f"\n... [truncated, total chars={len(text)}]"


def _scratchpad_as_text(scratchpad: List[str]) -> str:
    """Join scratchpad entries with a hard cap to keep the prompt bounded."""
    joined = "\n\n".join(scratchpad)
    if len(joined) <= SCRATCHPAD_TOTAL_CHARS:
        return joined
    # Keep the tail (most recent entries matter most for the next decision).
    return "... [earlier scratchpad truncated]\n\n" + joined[-SCRATCHPAD_TOTAL_CHARS:]


def _format_resource_descriptions(resources: list) -> str:
    """Format resources for the research prompt with scheme-level guidance."""
    tavily = []
    perplexity = []
    other = []
    for r in resources:
        line = f"- {r.name}: {r.description}\n  URI: {r.uri_template}"
        uri = (r.uri_template or "").lower()
        if uri.startswith("tavily://"):
            tavily.append(line)
        elif uri.startswith("perplexity://"):
            perplexity.append(line)
        else:
            other.append(line)

    sections = []
    if tavily:
        sections.append("FAST WEB SEARCH (preferred, sub-second):\n" + "\n".join(tavily))
    if perplexity:
        sections.append(
            "DEEP RESEARCH (slow, use sparingly — 15s+ per call):\n"
            + "\n".join(perplexity)
        )
    if other:
        sections.append("OTHER READ-ONLY RESOURCES:\n" + "\n".join(other))
    return "\n\n".join(sections) if sections else "(no resources available)"


async def _read_resource_safely(
    client,
    resource_lookup: Dict[str, Any],
    decision: Dict[str, Any],
) -> str:
    """
    Execute a single resource read and return its textual body.

    Never raises - on failure, returns an error string that gets appended to
    the scratchpad so the LLM can react.
    """
    resource_name = decision.get("name", "")
    params = decision.get("parameters") or {}

    resource_item = resource_lookup.get(resource_name)
    if resource_item is None:
        return f"ERROR: resource `{resource_name}` not found."

    try:
        uri = _expand_uri_template(resource_item.uri_template, params)
    except Exception as e:
        return f"ERROR: failed to expand URI for `{resource_name}` with params={params}: {e}"

    log.info(f"📖 Reading resource: {resource_name} -> {uri}")

    try:
        async with client.session("covalent") as session:
            read_result = await session.read_resource(uri)
            if read_result.contents:
                content = read_result.contents[0]
                text = content.text if hasattr(content, 'text') else str(content)
            else:
                text = ""
    except Exception as e:
        log.warning(f"⚠️ Resource read failed for {resource_name}: {e}")
        return f"ERROR: resource read for `{resource_name}` failed: {e}"

    # Pretty-print the big search responses for easier log scanning (same policy
    # as the single-shot gather_context used for perplexity).
    if uri.startswith("perplexity://") or uri.startswith("tavily://"):
        _max = 24_000
        try:
            _parsed = json.loads(text)
            _body = json.dumps(_parsed, indent=2, default=str)
        except (json.JSONDecodeError, TypeError):
            _body = text
        if len(_body) > _max:
            _body = _body[:_max] + f"\n... [truncated for log, total chars={len(text)}]"
        scheme = "tavily" if uri.startswith("tavily://") else "pplx"
        log.info(
            f"[research/{scheme}] response from read_resource — "
            f"name={resource_name!r} uri={uri!r}\n{_body}"
        )

    return text


def _parse_research_decision(response_text: str) -> Dict[str, Any]:
    """
    Parse one turn's LLM output.

    Expected shape:
      {
        "thought": "...",
        "action": {
          "type": "read_resource",
          "name": "...",
          "parameters": {...},
          "reason": "..."
        }
      }
    OR:
      {
        "thought": "...",
        "action": {
          "type": "draft_plan",
          "actions": [ {tool_name, parameters, reasoning}, ... ],
          "overall_reasoning": "..."
        }
      }
    OR:
      {
        "thought": "...",
        "action": {
          "type": "task_complete",
          "summary": "..."
        }
      }

    Returns a dict with at least `{"type": ...}`; on parse failure returns
    `{"type": "invalid", "raw": <text>}` so the loop can re-prompt.
    """
    # Try fenced JSON block first.
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        start = response_text.find('{')
        end = response_text.rfind('}')
        if start == -1 or end == -1 or end <= start:
            return {"type": "invalid", "raw": response_text}
        json_str = response_text[start:end + 1]

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return {"type": "invalid", "raw": response_text}

    action = parsed.get("action") if isinstance(parsed, dict) else None
    if not isinstance(action, dict):
        return {"type": "invalid", "raw": response_text}

    atype = action.get("type")
    thought = parsed.get("thought", "") if isinstance(parsed, dict) else ""

    if atype == "read_resource":
        return {
            "type": "read_resource",
            "thought": thought,
            "name": action.get("name", ""),
            "parameters": action.get("parameters", {}) or {},
            "reason": action.get("reason", ""),
        }
    if atype == "draft_plan":
        raw_actions = action.get("actions") or []
        normalized = []
        for i, a in enumerate(raw_actions, start=1):
            if not isinstance(a, dict):
                continue
            normalized.append({
                "step_id": a.get("step_id", i),
                "tool_name": a.get("tool_name"),
                "parameters": a.get("parameters", {}) or {},
                "reasoning": a.get("reasoning", f"Step {i}"),
            })
        return {
            "type": "draft_plan",
            "thought": thought,
            "actions": normalized,
            "overall_reasoning": action.get("overall_reasoning", ""),
        }
    if atype == "task_complete":
        return {
            "type": "task_complete",
            "thought": thought,
            "summary": action.get("summary", "") or "",
        }

    return {"type": "invalid", "raw": response_text}


def _build_research_system_prompt() -> str:
    """System prompt used for every turn of the iterative research loop."""
    return """You are an agentic research + action planner operating inside a multi-iteration meta-loop.

The caller drives an outer loop of: plan -> user approval -> execute -> call you again with the execution results -> decide.

Each turn you must emit EXACTLY ONE of THREE actions, as JSON:

1. Read a read-only resource to gather more context:
   {
     "thought": "<why you're reading this>",
     "action": {
       "type": "read_resource",
       "name": "<resource name>",
       "parameters": { ... },
       "reason": "<what you hope to learn>"
     }
   }

2. Draft the next plan (only when you have EVERYTHING you need to execute immediately):
   {
     "thought": "<why the plan is complete>",
     "action": {
       "type": "draft_plan",
       "actions": [
         {
           "tool_name": "<tool>",
           "parameters": { ... },
           "reasoning": "<brief explanation>"
         }
       ],
       "overall_reasoning": "<brief overall plan>"
     }
   }

3. Declare the higher-level task complete (only when the PRIOR ITERATIONS' results clearly satisfy the original user action):
   {
     "thought": "<why the task is already done>",
     "action": {
       "type": "task_complete",
       "summary": "<1-3 sentence summary of what was accomplished across all iterations>"
     }
   }

META-LOOP POLICY (when to draft another plan vs. declare complete):
- If PRIOR ITERATIONS is empty, you MUST either read a resource or draft a plan. Do NOT emit task_complete on iteration 1.
- PREFER finishing in ONE iteration. Only decompose into multiple iterations when a later step strictly depends on the runtime output of a prior step AND that dependency cannot be expressed via the {{$N.field}} cross-step variable syntax within a single plan (e.g., you need to SEE content a tool returned before you know which subsequent tool to call).
- After at least one iteration, if the prior results clearly satisfy the original user action, emit task_complete with a short summary.
- If prior steps failed in a way that makes further progress impossible, emit task_complete with a summary explaining the partial outcome — do not loop indefinitely on unrecoverable errors.
- Otherwise, emit draft_plan with the next concrete batch of actions to execute.

STRICT PLAN POLICY:
- Every REQUIRED parameter MUST be a concrete, final value.
- Placeholders such as [FILL IN ...], [Content to be generated], TODO, TBD, <placeholder>, REPLACE_ME are FORBIDDEN and will cause the plan to be rejected.
- If you don't know a value, CALL A READ-ONLY RESOURCE to look it up before drafting the plan.
- For long-form content (email bodies, doc bodies), write the full final text.
- Cross-step variables use the syntax {{$N.field}} where N is a strictly-earlier step and `field` is a declared passable output of that step's tool.
- Cross-step variables reference steps WITHIN the current plan only — they CANNOT reference prior iterations. If you need output from a prior iteration, read it from PRIOR ITERATIONS and hardcode the value.

SEARCH POLICY:
- For web/fact lookups, PREFER `tavily://search/...` — it returns in <1s and is the default.
- Use `perplexity://search/...` ONLY for deep research that benefits from multi-source synthesis (e.g., market analysis, biographies, literature reviews). It takes 15+ seconds per call. Use Perplexity calls sparingly.
- Before planning, exhaust cheap Tavily lookups first; only escalate to Perplexity when Tavily results are insufficient.

EMAIL FORMATTING (when the plan includes send_email / create_draft):
- Email body content must be PLAIN TEXT (no markdown, no bullet points with '-').
- Use simple line breaks; keep it professional.

Output ONLY the JSON object. No prose outside it."""


def _format_prior_iterations(prior_iterations: Optional[List[Dict[str, Any]]]) -> str:
    """
    Render prior plan+execution iterations as a compact journal for the prompt.

    `prior_iterations` is a list of `{plan: [...], results: [...]}` dicts, where:
      - `plan` is a list of drafted actions (step_id, tool_name, parameters, ...)
      - `results` is a list of per-step execution results (step_id, tool_name,
        status, result | error, ...)

    We truncate each result body and then apply a total character cap so this
    section cannot crowd out the rest of the prompt.
    """
    if not prior_iterations:
        return "(none — this is iteration 1)"

    rendered_iters: List[str] = []
    for idx, iteration in enumerate(prior_iterations, start=1):
        plan = iteration.get("plan") or []
        results = iteration.get("results") or []

        plan_lines: List[str] = []
        for step in plan:
            if not isinstance(step, dict):
                continue
            tool_name = step.get("tool_name", "<unknown>")
            params = step.get("parameters", {})
            try:
                params_str = json.dumps(params, default=str)
            except (TypeError, ValueError):
                params_str = str(params)
            if len(params_str) > 400:
                params_str = params_str[:400] + "...[truncated]"
            plan_lines.append(
                f"      step {step.get('step_id', '?')}: {tool_name}({params_str})"
            )
        plan_block = "\n".join(plan_lines) if plan_lines else "      (no plan recorded)"

        result_lines: List[str] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            status = r.get("status", "?")
            tool_name = r.get("tool_name", "<unknown>")
            step_id = r.get("step_id", "?")
            if status == "success":
                body = r.get("result", "")
                try:
                    body_str = (
                        json.dumps(body, default=str)
                        if not isinstance(body, str) else body
                    )
                except (TypeError, ValueError):
                    body_str = str(body)
                body_str = _truncate(body_str, PRIOR_ITERATION_PER_RESULT_CHARS)
                result_lines.append(
                    f"      step {step_id} {tool_name} -> SUCCESS: {body_str}"
                )
            else:
                err = r.get("error", "unknown error")
                err_str = _truncate(str(err), PRIOR_ITERATION_PER_RESULT_CHARS)
                result_lines.append(
                    f"      step {step_id} {tool_name} -> FAILED: {err_str}"
                )
        results_block = "\n".join(result_lines) if result_lines else "      (no results recorded)"

        rendered_iters.append(
            f"  Iteration {idx}:\n"
            f"    Plan:\n{plan_block}\n"
            f"    Results:\n{results_block}"
        )

    joined = "\n\n".join(rendered_iters)
    if len(joined) > PRIOR_ITERATIONS_TOTAL_CHARS:
        # Keep the TAIL (most recent iterations matter most for deciding what to do next).
        joined = (
            "... [earlier iterations truncated]\n\n"
            + joined[-PRIOR_ITERATIONS_TOTAL_CHARS:]
        )
    return joined


def _build_research_user_prompt(
    action_text: str,
    initial_context: str,
    relevant_resources: list,
    relevant_tools: list,
    scratchpad: List[str],
    reads_done: int,
    reads_budget: int,
    turns_left: int,
    last_issues: List[str],
    prior_iterations: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Assemble the user-message for one turn of the loop."""
    if len(initial_context) > MAX_CONTEXT_CHARS:
        initial_context = initial_context[:MAX_CONTEXT_CHARS] + "\n\n[... context truncated ...]"

    resource_block = _format_resource_descriptions(relevant_resources)

    def _format_tool(tool):
        return f"- {tool.name}: {tool.description}\n  Parameters:\n    {format_tool_params(tool)}"

    tool_block = "\n".join(_format_tool(t) for t in relevant_tools)

    passable_info = format_passable_outputs_for_prompt()
    scratchpad_text = _scratchpad_as_text(scratchpad) if scratchpad else "(empty)"
    issues_block = (
        "\n".join(f"- {i}" for i in last_issues)
        if last_issues else "(none — last draft either passed or there was none)"
    )
    prior_block = _format_prior_iterations(prior_iterations)
    outer_iteration_index = (len(prior_iterations) + 1) if prior_iterations else 1

    return f"""USER ACTION TO ACCOMPLISH (higher-level goal, same across all iterations):
{action_text}

EXISTING CONTEXT:
{initial_context if initial_context else "(none)"}

PRIOR ITERATIONS (plans already approved + executed; you are now on iteration {outer_iteration_index}):
{prior_block}

READ-ONLY RESOURCES YOU CAN CALL (choose ONE per read_resource turn):
{resource_block}

WRITE TOOLS YOU CAN PROPOSE IN THE NEXT PLAN:
{tool_block}

PASSABLE OUTPUTS BY TOOL (for cross-step {{{{$N.field}}}} references WITHIN the next plan):
{passable_info}

BUDGET:
- Turns remaining (including this one): {turns_left}
- Resource reads remaining: {reads_budget - reads_done}

SCRATCHPAD (chronological notes from previous turns THIS iteration):
{scratchpad_text}

LATEST VALIDATION ISSUES FROM YOUR PREVIOUS DRAFT (address these before retrying):
{issues_block}

Now emit ONE JSON object per the system prompt's schema (read_resource, draft_plan, or task_complete)."""


async def _llm_research_turn(
    action_text: str,
    initial_context: str,
    relevant_resources: list,
    relevant_tools: list,
    scratchpad: List[str],
    reads_done: int,
    reads_budget: int,
    turns_left: int,
    last_issues: List[str],
    prior_iterations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run a single LLM turn of the research loop and return the parsed decision."""
    system_prompt = _build_research_system_prompt()
    user_prompt = _build_research_user_prompt(
        action_text=action_text,
        initial_context=initial_context,
        relevant_resources=relevant_resources,
        relevant_tools=relevant_tools,
        scratchpad=scratchpad,
        reads_done=reads_done,
        reads_budget=reads_budget,
        turns_left=turns_left,
        last_issues=last_issues,
        prior_iterations=prior_iterations,
    )

    gateway = get_gateway_client()
    response = gateway.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=3072,
        temperature=0.0,
    )
    log.debug(f"\n{'='*60}\nLLM OUTPUT (RESEARCH TURN)\n{'='*60}\n{response.content}\n{'='*60}\n")
    return _parse_research_decision(response.content)


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

STRICT PLAN POLICY:
- Every REQUIRED parameter MUST be a concrete, final value.
- Placeholders such as [FILL IN ...], [Content to be generated], TODO, TBD, <placeholder>, REPLACE_ME are FORBIDDEN and will cause the plan to be rejected.
- For long-form content (email bodies, doc bodies), write the full final text.
- Prefer SINGLE actions when possible - avoid multi-step plans unless absolutely necessary.

SEARCH POLICY (for context gathering, if any is done upstream):
- Fast lookups belong on `tavily://search/...` (sub-second).
- `perplexity://search/...` is for deep multi-source synthesis only (15s+ per call); use sparingly.

EMAIL FORMATTING:
- For email body content (send_email, create_draft), use PLAIN TEXT only
- Do NOT use markdown formatting (no **bold**, no *italic*, no bullet points with -)
- Use simple line breaks and plain dashes for lists if needed
- Keep emails professional and readable as plain text

IMPORTANT INSTRUCTIONS:
1. Analyze if the action requires ONE or MULTIPLE tools
2. If the action involves multiple distinct operations (e.g., "create a doc AND add content to it"), propose MULTIPLE actions
3. If the action is simple and requires only one tool, propose just that one
4. **CRITICAL**: You MUST fill in ALL parameters marked as REQUIRED with concrete, final values - placeholders are forbidden
5. Use the context data to infer missing information (emails, names, dates, etc.)
6. If a REQUIRED parameter's value is unknown, do NOT invent a placeholder - the plan will be rejected. Instead, the calling code should have already gathered that context upstream.
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
                _hint = f"MCP server unreachable at http://localhost:{MCP_PORT}/mcp. Start the API with mounted MCP via: bash start_servers.sh"
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

def _build_research_error_payload(
    reason: str,
    resources_read: List[str],
    scratchpad: List[str],
    last_draft: Optional[Dict[str, Any]],
    last_issues: List[str],
) -> Dict[str, Any]:
    """Construct the error payload returned when the loop exhausts a budget."""
    reason_messages = {
        "turns": "Research loop exhausted its turn budget before producing a valid plan.",
        "reads": "Research loop exhausted its read-resource budget. Aborting without forcing an incomplete plan.",
        "wall_clock": "Research loop exceeded its wall-clock budget before producing a valid plan.",
        "drafts": "Research loop produced too many invalid drafts in a row.",
    }
    human = reason_messages.get(reason, f"Research loop aborted: {reason}.")
    if last_issues:
        human = f"{human} Last validation issues: {'; '.join(last_issues[:5])}"

    return {
        "status": "error",
        "research": {
            "resources_read": resources_read,
            "context_gathered": _scratchpad_as_text(scratchpad),
        },
        "proposed_actions": None,
        "is_multi_action": False,
        "overall_reasoning": "",
        "error": human,
        "error_reason": reason,
        "last_draft": last_draft,
        "last_issues": last_issues,
    }


async def iterative_research_and_plan(
    action_text: str,
    initial_context: str = "",
    prior_iterations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Agentic research + planning loop.

    Each turn, the LLM picks ONE of:
      - `read_resource`: read a read-only MCP resource, append to scratchpad.
      - `draft_plan`: propose a next plan; we validate it programmatically.
      - `task_complete`: declare the higher-level task satisfied (only allowed
        when `prior_iterations` is non-empty).

    The loop exits successfully (status="success") when a drafted plan passes
    strict validation (all REQUIRED parameters present, no forbidden
    placeholders, cross-step refs valid). It exits with status="complete" when
    the planner declares the task done. It exits with an error when ANY of the
    four inner budgets is exhausted or the outer-iteration budget has been
    reached — we never silently force an incomplete plan.

    `prior_iterations` — optional list of prior executed iterations used by the
    outer plan->execute->continue meta-loop. Each element is
    `{plan: [action...], results: [result...]}`. Ignored on iteration 1.
    """
    outer_iteration_index = (len(prior_iterations) + 1) if prior_iterations else 1
    log.info("=" * 40)
    log.info(f"🔁 ITERATIVE RESEARCH + PLANNING LOOP (outer iteration {outer_iteration_index})")
    log.info("=" * 40)

    # Outer-iteration budget: refuse to plan iteration N+1 once we've hit the cap.
    if prior_iterations and len(prior_iterations) >= MAX_OUTER_ITERATIONS:
        log.warning(
            f"⛔ Outer-iteration budget exhausted: {len(prior_iterations)} prior "
            f"iteration(s) >= MAX_OUTER_ITERATIONS={MAX_OUTER_ITERATIONS}. "
            "Aborting without producing another plan."
        )
        human = (
            f"Meta-loop exhausted its outer-iteration budget "
            f"({MAX_OUTER_ITERATIONS} iterations). The task could not be completed "
            "within the allowed number of plan/execute cycles."
        )
        return {
            "status": "error",
            "research": {"resources_read": [], "context_gathered": ""},
            "proposed_actions": None,
            "is_multi_action": False,
            "overall_reasoning": "",
            "error": human,
            "error_reason": "outer_iterations",
            "last_draft": None,
            "last_issues": [],
        }

    try:
        client, tools, resources = await get_mcp_client()
    except Exception as e:
        log.error(f"❌ MCP connection error: {e}")
        return {
            "status": "error",
            "research": {"resources_read": [], "context_gathered": initial_context},
            "proposed_actions": None,
            "is_multi_action": False,
            "overall_reasoning": "",
            "error": f"Connection error: {str(e)}",
        }

    if not tool_router._initialized:
        tool_router.initialize(tools, resources)

    routing_query = action_text + " " + initial_context[:500]
    relevant_resources = tool_router.get_relevant_resources(routing_query, top_k=TOP_K_TOOLS)
    relevant_tools = tool_router.get_relevant_tools(routing_query, top_k=TOP_K_TOOLS)

    log.info(f"📚 Shortlisted {len(relevant_resources)} resources for research:")
    for i, res in enumerate(relevant_resources, 1):
        log.info(f"   {i}. {res.name}")
    log.info(f"🔧 Shortlisted {len(relevant_tools)} tools for planning:")
    for i, tool in enumerate(relevant_tools, 1):
        log.info(f"   {i}. {tool.name}")

    resource_lookup = {r.name: r for r in resources}
    tool_lookup = {t.name: t for t in tools}

    scratchpad: List[str] = []
    resources_read: List[str] = []
    reads_done = 0
    draft_attempts = 0
    last_draft: Optional[Dict[str, Any]] = None
    last_issues: List[str] = []
    start = time.monotonic()

    for turn in range(1, MAX_RESEARCH_TURNS + 1):
        elapsed = time.monotonic() - start
        if elapsed > RESEARCH_WALL_CLOCK_S:
            log.warning(
                f"⛔ Wall-clock budget exhausted after {elapsed:.1f}s "
                f"(>{RESEARCH_WALL_CLOCK_S}s). Aborting."
            )
            return _build_research_error_payload(
                "wall_clock", resources_read, scratchpad, last_draft, last_issues,
            )

        turns_left = MAX_RESEARCH_TURNS - turn + 1
        log.info(
            f"🔁 Turn {turn}/{MAX_RESEARCH_TURNS} — "
            f"reads_done={reads_done}/{MAX_RESOURCE_READS}, "
            f"drafts={draft_attempts}/{MAX_DRAFT_ATTEMPTS}, "
            f"elapsed={elapsed:.1f}s"
        )

        try:
            decision = await _llm_research_turn(
                action_text=action_text,
                initial_context=initial_context,
                relevant_resources=relevant_resources,
                relevant_tools=relevant_tools,
                scratchpad=scratchpad,
                reads_done=reads_done,
                reads_budget=MAX_RESOURCE_READS,
                turns_left=turns_left,
                last_issues=last_issues,
                prior_iterations=prior_iterations,
            )
        except GatewayError as e:
            log.error(f"❌ Gateway error during research turn: {e}")
            return {
                "status": "error",
                "research": {
                    "resources_read": resources_read,
                    "context_gathered": _scratchpad_as_text(scratchpad),
                },
                "proposed_actions": None,
                "is_multi_action": False,
                "overall_reasoning": "",
                "error": f"Gateway error: {str(e)}",
            }
        except Exception as e:
            log.error(f"❌ Unexpected error during research turn: {e}")
            import traceback
            traceback.print_exc()
            return {
                "status": "error",
                "research": {
                    "resources_read": resources_read,
                    "context_gathered": _scratchpad_as_text(scratchpad),
                },
                "proposed_actions": None,
                "is_multi_action": False,
                "overall_reasoning": "",
                "error": f"Research turn error: {str(e)}",
            }

        dtype = decision.get("type")

        if dtype == "read_resource":
            if reads_done >= MAX_RESOURCE_READS:
                log.warning("⛔ Read budget exhausted. Aborting without forcing a plan.")
                return _build_research_error_payload(
                    "reads", resources_read, scratchpad, last_draft, last_issues,
                )
            log.info(
                f"   ↪ read_resource name={decision.get('name')!r} "
                f"params={decision.get('parameters')} "
                f"reason={(decision.get('reason') or '')[:120]!r}"
            )
            text = await _read_resource_safely(client, resource_lookup, decision)
            scratchpad.append(
                f"TURN {turn} READ {decision.get('name')}({decision.get('parameters')}) ->\n"
                f"{_truncate(text, SCRATCHPAD_PER_READ_CHARS)}"
            )
            resources_read.append(decision.get("name", ""))
            reads_done += 1
            continue

        if dtype == "task_complete":
            # Guardrail: block task_complete on iteration 1 — the planner MUST
            # produce at least one plan before it can declare the task done.
            if not prior_iterations:
                log.warning(
                    "   ✗ task_complete emitted on iteration 1 (forbidden). "
                    "Nudging LLM to draft a plan or read a resource instead."
                )
                scratchpad.append(
                    f"TURN {turn} INVALID task_complete — you cannot declare the task "
                    "complete on iteration 1 (there are no prior iterations whose "
                    "results could satisfy the goal). Emit read_resource or "
                    "draft_plan instead."
                )
                continue

            summary = decision.get("summary", "") or ""
            log.info(
                f"✅ task_complete after {outer_iteration_index - 1} prior iteration(s). "
                f"Summary: {summary[:200]}"
            )
            return {
                "status": "complete",
                "research": {
                    "resources_read": resources_read,
                    "context_gathered": _scratchpad_as_text(scratchpad),
                },
                "proposed_actions": None,
                "is_multi_action": False,
                "overall_reasoning": summary,
                "summary": summary,
                "error": None,
            }

        if dtype == "draft_plan":
            actions = decision.get("actions") or []
            last_draft = {
                "actions": actions,
                "overall_reasoning": decision.get("overall_reasoning", ""),
            }
            last_issues = _validate_plan(actions, tool_lookup)
            log.info(f"   ↪ draft_plan with {len(actions)} action(s) — issues={len(last_issues)}")

            if not last_issues:
                log.info(
                    f"✅ Plan validated after {turn} turn(s), {reads_done} read(s). "
                    f"{len(actions)} action(s) proposed (outer iteration {outer_iteration_index})."
                )
                return {
                    "status": "success",
                    "research": {
                        "resources_read": resources_read,
                        "context_gathered": _scratchpad_as_text(scratchpad),
                    },
                    "proposed_actions": actions,
                    "is_multi_action": len(actions) > 1,
                    "overall_reasoning": decision.get("overall_reasoning", ""),
                    "iteration_index": outer_iteration_index,
                    "error": None,
                }

            draft_attempts += 1
            log.warning(
                f"   ✗ Draft rejected (attempt {draft_attempts}/{MAX_DRAFT_ATTEMPTS}). Issues:"
            )
            for issue in last_issues:
                log.warning(f"     - {issue}")

            if draft_attempts >= MAX_DRAFT_ATTEMPTS:
                return _build_research_error_payload(
                    "drafts", resources_read, scratchpad, last_draft, last_issues,
                )

            scratchpad.append(
                f"TURN {turn} DRAFT REJECTED — issues:\n- "
                + "\n- ".join(last_issues)
                + "\nResolve by reading more resources or rewriting the plan. "
                "Placeholders like [FILL IN ...] are FORBIDDEN."
            )
            continue

        # Invalid / unparseable output — tell the LLM to retry on the next turn.
        log.warning(
            "   ✗ Invalid turn output (not a valid read_resource/draft_plan/task_complete JSON); "
            "nudging LLM to retry."
        )
        raw = (decision.get("raw") or "")[:500]
        scratchpad.append(
            f"TURN {turn} INVALID OUTPUT — your previous response was not valid JSON "
            f"matching the schema. Emit exactly one action per the system prompt. "
            f"First 500 chars of your output were:\n{raw}"
        )

    # Turn budget exhausted.
    log.warning(f"⛔ Turn budget exhausted after {MAX_RESEARCH_TURNS} turn(s).")
    return _build_research_error_payload(
        "turns", resources_read, scratchpad, last_draft, last_issues,
    )


async def research_and_plan(
    action_text: str,
    initial_context: str = "",
    prior_iterations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Combined research + planning flow.

    Thin wrapper over `iterative_research_and_plan` — preserves the public
    contract consumed by `server/fastapi_app/routers/actions.py` and
    `server/app.py`.

    `prior_iterations` lets the outer plan->execute->continue meta-loop feed
    the journal of previously-executed plans back into the planner so it can
    either draft the next step or declare the task complete.

    Returns:
        {
            "status": "success" | "complete" | "error",
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
            # Present when status == "success":
            "iteration_index": int,
            # Present when status == "complete":
            "summary": str,
            "error": str | None,
            # Present on loop-exhaustion errors:
            "error_reason": "turns" | "reads" | "wall_clock" | "drafts" | "outer_iterations",
            "last_draft": {...} | None,
            "last_issues": list[str] | None,
        }
    """
    result = await iterative_research_and_plan(
        action_text, initial_context, prior_iterations=prior_iterations,
    )
    status = result.get("status")
    if status == "success":
        num_actions = len(result.get("proposed_actions") or [])
        log.info(f"✅ Planning complete: {num_actions} action(s) proposed")
    elif status == "complete":
        log.info(f"🏁 Task declared complete: {result.get('summary', '')[:200]}")
    return result


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
    """Exercise the iterative research + planning loop end-to-end."""

    action_text = "Reply to Ritesh's latest email about the project update"
    initial_context = """
    Known information:
    - Ritesh is a team member (ritesh@example.com)
    - We're working on Q1 roadmap
    """

    log.info("=" * 60)
    log.info("ITERATIVE RESEARCH + PLANNING")
    log.info("=" * 60)

    result = await research_and_plan(action_text, initial_context)

    research = result.get("research") or {}
    log.info(f"\n📚 Resources read: {research.get('resources_read', [])}")
    log.info(f"   Scratchpad length: {len(research.get('context_gathered') or '')} chars")

    if result["status"] == "error":
        log.error(f"❌ Research + planning failed: {result.get('error')}")
        if result.get("error_reason"):
            log.error(f"   Reason: {result['error_reason']}")
        if result.get("last_issues"):
            log.error("   Last validation issues:")
            for issue in result["last_issues"]:
                log.error(f"     - {issue}")
        if result.get("last_draft"):
            log.error(f"   Last draft actions: {json.dumps(result['last_draft'], indent=2, default=str)[:1000]}")
        return

    proposed_actions = result.get("proposed_actions") or []
    is_multi = result.get("is_multi_action", False)

    log.info(f"\n📋 Proposed Actions ({len(proposed_actions)} action(s), multi={is_multi}):")
    for action in proposed_actions:
        log.info(f"\n   Step {action['step_id']}: {action['tool_name']}")
        log.info(f"   Parameters: {json.dumps(action['parameters'], indent=4)}")
        log.info(f"   Reasoning: {action['reasoning']}")

    log.info("\n" + "=" * 60)
    log.info("EXECUTION (simulated approval)")
    log.info("=" * 60)
    log.info("⏸️  [In real app: User reviews and approves/edits parameters here]")

    if len(proposed_actions) == 1:
        action = proposed_actions[0]
        exec_result = await execute_action(action['tool_name'], action['parameters'])
        if exec_result["status"] == "error":
            log.error(f"❌ Execution failed: {exec_result['error']}")
            return
        log.info(f"\n✅ Action executed successfully!")
        log.info(f"   Result: {exec_result['result']}")
    else:
        chain_result = await execute_action_chain(proposed_actions)
        log.info(f"\n📊 Chain execution complete:")
        log.info(f"   Status: {chain_result['status']}")
        log.info(f"   Summary: {chain_result['summary']['succeeded']}/{chain_result['summary']['total']} succeeded")
        for r in chain_result['results']:
            status_icon = "✅" if r['status'] == "success" else "❌"
            log.info(f"\n   {status_icon} Step {r['step_id']} ({r['tool_name']}): {r['status']}")
            if r['status'] == 'success':
                log.info(f"      Result: {str(r.get('result', ''))[:100]}...")
            else:
                log.info(f"      Error: {r.get('error', 'Unknown')}")


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
