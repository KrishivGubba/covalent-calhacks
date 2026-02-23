"""
MCP Agent Integration - Use MCP tools with LangChain agents.

Example usage:
    python -m mcp.agent_integration
"""
import asyncio
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))
from logger import get_logger
log = get_logger()
from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.chat_models import init_chat_model


async def create_agent_with_mcp_tools():
    """Create a LangChain agent with MCP tools."""
    log.info("🤖 Creating agent with MCP tools...")
    
    # Connect to MCP server
    client = MultiServerMCPClient({
        "covalent_tools": {
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "mcp.server"]
        }
    })
    
    # Get tools
    tools = await client.get_tools()
    log.info(f"📋 Loaded {len(tools)} tools into agent")
    
    # Initialize LLM
    llm = init_chat_model(
        model_provider="anthropic",
        model="claude-sonnet-4-5-20250929",
    )
    
    # Create agent with tools
    agent = create_agent(
        llm,
        tools
    )
    
    # Test the agent
    log.info("\n💬 Testing agent...")
    result = await agent.ainvoke({
        "messages": [{
            "role": "user",
            "content": "What's the weather in New York?"
        }]
    })
    
    log.info("\n🤖 Agent response:")
    log.info(str(result))
    
    return agent


if __name__ == "__main__":
    asyncio.run(create_agent_with_mcp_tools())
