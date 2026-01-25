from typing import TypedDict, Literal, List
from typing_extensions import TypedDict
import asyncio
import os
import pickle
import atexit
import signal
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langchain.chat_models import init_chat_model
from langgraph.types import Send
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, Field
import numpy as np
import dotenv

dotenv.load_dotenv()

model_provider = os.getenv("MODEL_PROVIDER", "openai")
llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")

llm = init_chat_model(
    model_provider=model_provider,
    model=llm_model,
    temperature=0
)

# =============================================================================
# MCP SERVER CONFIGURATION
# =============================================================================
MCP_SERVERS = {
    "google": {
        "transport": "stdio",
        "command": os.getenv("GOOGLE_MCP_COMMAND", "google-mcp"),
        "args": []
    },
}

# =============================================================================
# PERSISTENT MCP CLIENT
# =============================================================================
_mcp_client = None
_all_tools = None
_client_lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None


async def get_mcp_client(max_retries: int = 3):
    """Get or create the MCP client with connection pooling and retry logic."""
    global _mcp_client, _all_tools, _client_lock

    # Create lock if not exists (for async context)
    if _client_lock is None:
        _client_lock = asyncio.Lock()

    async with _client_lock:
        for attempt in range(max_retries):
            try:
                if _mcp_client is None:
                    print("Initializing MCP client...")
                    _mcp_client = MultiServerMCPClient(MCP_SERVERS)
                    _all_tools = await _mcp_client.get_tools()
                    tool_router.initialize(_all_tools)
                    print(f"MCP client initialized with {len(_all_tools)} tools")
                return _mcp_client, _all_tools
            except Exception as e:
                print(f"MCP connection attempt {attempt + 1} failed: {e}")
                _mcp_client = None
                _all_tools = None
                if attempt < max_retries - 1:
                    await asyncio.sleep(1 * (attempt + 1))  # Exponential backoff
                else:
                    raise ConnectionError(f"Failed to connect to MCP server after {max_retries} attempts: {e}")


async def reset_mcp_client():
    """Reset the MCP client connection (useful after errors)."""
    global _mcp_client, _all_tools
    print("Resetting MCP client...")
    _mcp_client = None
    _all_tools = None


def shutdown():
    """Cleanup function for graceful shutdown."""
    global _mcp_client, _all_tools
    print("Shutting down MCP client...")
    _mcp_client = None
    _all_tools = None


# Register cleanup on exit
atexit.register(shutdown)

# =============================================================================
# TOOL ROUTING CONFIGURATION
# =============================================================================
TOOL_CACHE_DIR = Path.home() / ".cache" / "llmgraph"
TOOL_CACHE_FILE = TOOL_CACHE_DIR / "tool_embeddings.pkl"
TOP_K_TOOLS = 10  # Number of relevant tools to select

# Initialize embeddings model
embeddings = OpenAIEmbeddings()


# =============================================================================
# SEMANTIC TOOL ROUTING
# =============================================================================
class ToolRouter:
    """Routes queries to the most relevant tools using semantic similarity."""

    def __init__(self):
        self.tools = None
        self.tool_embeddings = None
        self.tool_names = None

    def _ensure_cache_dir(self):
        """Create cache directory if it doesn't exist."""
        TOOL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def cache_tools(self, tools: list):
        """Cache tool embeddings to disk for faster subsequent loads."""
        self._ensure_cache_dir()

        print(f"Caching embeddings for {len(tools)} tools...")
        tool_descriptions = [
            f"{tool.name}: {tool.description}"
            for tool in tools
        ]
        tool_embeddings = embeddings.embed_documents(tool_descriptions)

        cache_data = {
            'tool_names': [tool.name for tool in tools],
            'tool_descriptions': tool_descriptions,
            'embeddings': tool_embeddings,
        }

        with open(TOOL_CACHE_FILE, 'wb') as f:
            pickle.dump(cache_data, f)

        print(f"Cached {len(tools)} tool embeddings to {TOOL_CACHE_FILE}")

        self.tools = tools
        self.tool_embeddings = np.array(tool_embeddings)
        self.tool_names = [tool.name for tool in tools]

    def load_cache(self, tools: list) -> bool:
        """Load cached embeddings if available and valid."""
        if not TOOL_CACHE_FILE.exists():
            return False

        try:
            with open(TOOL_CACHE_FILE, 'rb') as f:
                cache_data = pickle.load(f)

            # Verify cache matches current tools
            current_names = set(tool.name for tool in tools)
            cached_names = set(cache_data['tool_names'])

            if current_names != cached_names:
                print("Tool set changed, rebuilding cache...")
                return False

            self.tools = tools
            self.tool_embeddings = np.array(cache_data['embeddings'])
            self.tool_names = cache_data['tool_names']
            print(f"Loaded {len(self.tools)} cached tool embeddings")
            return True

        except Exception as e:
            print(f"Error loading cache: {e}")
            return False

    def initialize(self, tools: list):
        """Initialize the router with tools, using cache if available."""
        if not self.load_cache(tools):
            self.cache_tools(tools)

    def get_relevant_tools(self, query: str, top_k: int = TOP_K_TOOLS) -> list:
        """Find the most relevant tools for a query using cosine similarity."""
        if self.tools is None:
            raise ValueError("ToolRouter not initialized. Call initialize() first.")

        # Embed the query
        query_embedding = np.array(embeddings.embed_query(query))

        # Calculate cosine similarity with all tools
        similarities = np.dot(self.tool_embeddings, query_embedding) / (
                np.linalg.norm(self.tool_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )

        # Get top-k indices
        top_indices = np.argsort(similarities)[-top_k:][::-1]

        # Return the relevant tools
        relevant_tools = [self.tools[i] for i in top_indices]

        print(f"Selected {len(relevant_tools)} relevant tools: {[t.name for t in relevant_tools]}")
        return relevant_tools


# Global tool router instance
tool_router = ToolRouter()


# =============================================================================
# STATE AND MODELS
# =============================================================================
class MCPTask(BaseModel):
    prompt: str = Field(
        description="The details of the task that the MCP has to perform",
    )


class SCTask(TypedDict):
    action: str
    details: str


class Output(BaseModel):
    node: Literal["gsuite", "screen controller"]
    result: dict


class State(TypedDict):
    task: str
    data: str
    mcp_tasks: List[MCPTask]
    sc_tasks: List[SCTask]
    mcp_outputs: List[Output]
    final_outputs: str


class LLMTasks(BaseModel):
    mcp_tasks: List[MCPTask]
    sc_tasks: List[SCTask]


model = llm.with_structured_output(LLMTasks)


# =============================================================================
# GRAPH NODES
# =============================================================================
def orchestrator(state: State):
    plan_of_action = model.invoke(
        [
            SystemMessage(content=f"""
            You are an orchestrator agent. Analyze the user's query and assign tasks to the appropriate workers.

            - If the query has multiple parts, parse through it and split it into individual tasks.
            - If the task involves doing an action via the gsuite (calendar, drive, docs, sheets, slides, gmail)
            or anything related (event, task, presentation, email etc.) the task will use the 'gsuite' node
            - If there exists any task that cannot be completed with the gsuite, it should be a screen controller task 
            or sc_task.  
            - A screen controller task must be split into a list of the smallest executable tasks possible 

            Example: 
                User: Write an email to rneela@wisc.edu to follow up with yesterday's meeting, then go to google and search
                up for some videos of kittens playing with puppies

                Output: mcp_tasks = [
                Task(task="Send email to rneela@wisc.edu following up about yesterday's meeting", node="gsuite"),
                ]
                sc_tasks = [
                SCTask(action="Go to google and search for videos of kittens playing with dogs", details=""),
                ]

            Example 2: 
                User: Send a message to Ritesh Neela on LinkedIn telling him how much of a good time the user had during the meeting
                Provided data: The user had a lot of fun at the meeting yesterday and the current screen is the open dm with Ritesh
                Neela.

                Output: sc_tasks = [
                   SCTask(action="Write a message about how much fun you had at the meeting yesterday", details="Current screen is the dm with Ritesh on LinkedIn"),
                   SCTask(action="Press send on the send button", details="")
                ]

            Here is some information about the task that may prove useful: 
            {state['data']}

            """),
            HumanMessage(state['task']),
        ]
    )
    return {
        "mcp_tasks": plan_of_action.mcp_tasks,
        "sc_tasks": plan_of_action.sc_tasks,
        "mcp_outputs": [],
    }


async def gsuite(state: State):
    """GSuite node using MCP servers with semantic tool routing."""
    try:
        print("Using the gsuite node")

        # Get persistent MCP client (reuses connection)
        client, all_tools = await get_mcp_client()
        print(f"Using {len(all_tools)} total tools from MCP servers")

        # Get task content for routing
        mcp_tasks = [task.prompt for task in state['mcp_tasks']]
        task_content = " THEN \n ".join(mcp_tasks) if mcp_tasks else ""

        # Get only relevant tools using semantic similarity
        relevant_tools = tool_router.get_relevant_tools(task_content, top_k=TOP_K_TOOLS)

        # Create agent with only relevant tools
        from langchain.agents import create_agent

        agent = create_agent(
            f"{model_provider}:{llm_model}",
            relevant_tools,
        )

        result = await agent.ainvoke(
            input={"messages": [
                {"role": "system",
                 "content": """
                 - You are a helpful GSuite agent.
                 - Your task is to take the user's query and use the provided tools to do what the user asked.
                 - You do not need to confirm or ask for permission. Just execute the task.
                 - Remember not to leave any fields blank.
                 - If you have to modify something, first check if it's empty or not before trying to delete anything.
                 """},
                {"role": "user",
                 "content": task_content}
            ]},
        )

        messages = result.get('messages', [])
        final_ai_message = None

        for msg in reversed(messages):
            if getattr(msg, 'type', None) == 'ai':
                final_ai_message = msg.content
                break

        return {
            "mcp_outputs": state['mcp_outputs'] + [
                Output(node="gsuite", result={"response": final_ai_message})
            ]
        }

    except ConnectionError as e:
        print(f"MCP connection error: {e}")
        return {
            "mcp_outputs": state['mcp_outputs'] + [
                Output(node="gsuite", result={"response": f"Connection error: {str(e)}"})
            ]
        }
    except Exception as e:
        print(f"Error in gsuite node: {e}")
        # Reset client on unexpected errors
        await reset_mcp_client()
        return {
            "mcp_outputs": state['mcp_outputs'] + [
                Output(node="gsuite", result={"response": f"Error: {str(e)}"})
            ]
        }


def screen_controller(state: State):
    print("Using the screen_controller node")
    tasks = state['sc_tasks']
    from executor.main import thingy
    for task in tasks:
        thingy(task)


def synthesizer(state: State):
    final_outputs = []
    for output in state['mcp_outputs']:
        if isinstance(output.result, dict):
            response = output.result.get('response', str(output.result))
            if isinstance(response, list):
                response = " ".join(
                    item.get('text', str(item)) if isinstance(item, dict) else str(item)
                    for item in response
                )
            final_outputs.append(str(response))
        else:
            final_outputs.append(str(output.result))

    completed_tasks = "\n\n---\n\n".join(final_outputs)
    return {"final_outputs": completed_tasks}


def assign_workers(state: State):
    sends = []
    if len(state['mcp_tasks']) > 0:
        sends.append(Send("gsuite", state))
    if len(state['sc_tasks']) > 0:
        sends.append(Send("screen controller", state))
    return sends


# =============================================================================
# BUILD GRAPH
# =============================================================================
graph = StateGraph(State)

graph.add_node("gsuite", gsuite)
graph.add_node("orchestrator", orchestrator)
graph.add_node("screen controller", screen_controller)
graph.add_node("synthesizer", synthesizer)

graph.add_edge(START, "orchestrator")
graph.add_conditional_edges("orchestrator", assign_workers, ["gsuite", "screen controller"])

graph.add_edge("screen controller", "synthesizer")
graph.add_edge("gsuite", "synthesizer")
graph.add_edge("synthesizer", END)

compiled = graph.compile()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================
async def prebuild_tool_cache():
    """Pre-build the tool embedding cache. Run this once when adding new MCP servers."""
    print("Pre-building tool cache...")
    client, all_tools = await get_mcp_client()
    tool_router.cache_tools(all_tools)
    print("Tool cache built successfully!")


async def health_check():
    """Check if MCP servers are healthy."""
    try:
        client, tools = await get_mcp_client()
        print(f"Health check passed: {len(tools)} tools available")
        return True
    except Exception as e:
        print(f"Health check failed: {e}")
        return False


async def run_graph(user_query: str = "No task provided", data: str = "No data provided"):
    final_output = await compiled.ainvoke({"task": user_query, "data": data})
    print(final_output["final_outputs"])
    return final_output


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "--cache":
            # Pre-build tool cache
            asyncio.run(prebuild_tool_cache())

        elif command == "--health":
            # Health check
            asyncio.run(health_check())

        elif command == "--help":
            print("""
Usage: python LLMGraph.py [command]

Commands:
  (no args)   Run with default query
  --cache     Pre-build tool embedding cache
  --health    Check MCP server health
  --help      Show this help message

Environment variables:
  MODEL_PROVIDER       LLM provider (default: openai)
  LLM_MODEL           Model name (default: gpt-4o-mini)
  GOOGLE_MCP_COMMAND  Google MCP command (default: google-mcp)
            """)
        else:
            print(f"Unknown command: {command}")
            print("Use --help for usage information")
    else:
        user_query = """
            Make a doc wherein the only words say \"it works without composio\" and email it to kgubba@wisc.edu and rneela@wisc.edu
            where the subject is the same as the comment I provided to you 
        """
        data = ""

        asyncio.run(run_graph(user_query, data))