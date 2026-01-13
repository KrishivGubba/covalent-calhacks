"""
MCP Client - Connect to and use MCP servers.

Example usage:
    python -m mcp.client
"""
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient


async def test_local_server():
    """Test connection to local MCP server."""
    print("🔌 Connecting to local MCP server...")
    
    client = MultiServerMCPClient({
        "covalent_tools": {
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "mcp.server"]
        }
    })
    
    try:
        # Get all available tools
        print("\n📋 Fetching available tools...")
        tools = await client.get_tools()
        print(f"Found {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description[:60]}...")
        
        # Test a tool
        print("\n🧪 Testing get_weather tool...")
        result = await client.call_tool("get_weather", {
            "location": "San Francisco",
            "unit": "fahrenheit"
        })
        print(f"Result: {result}")
        
        # Test another tool
        print("\n🧪 Testing send_email tool...")
        result = await client.call_tool("send_email", {
            "to": "test@example.com",
            "subject": "Test Email",
            "body": "This is a test email from MCP"
        })
        print(f"Result: {result}")
        
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


async def connect_to_remote_server(url: str):
    """Connect to a remote MCP server via HTTP."""
    print(f"🔌 Connecting to remote MCP server at {url}...")
    
    client = MultiServerMCPClient({
        "remote_server": {
            "transport": "streamable_http",
            "url": url
        }
    })
    
    try:
        tools = await client.get_tools()
        print(f"Found {len(tools)} tools on remote server")
        return client
    except Exception as e:
        print(f"❌ Error connecting: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(test_local_server())
