"""
LLMGraph Client - Send requests to the always-on agent
Usage:
    python client.py "Email test@example.com"
    python client.py --health
    python client.py --interactive
"""

import requests
import sys
import json

BASE_URL = "http://127.0.0.1:8000"


def send_task(query: str, data: str = "") -> dict:
    """Send a task to the agent."""
    response = requests.post(
        f"{BASE_URL}/task",
        json={"query": query, "data": data},
        timeout=120,  # Long timeout for complex tasks
    )
    return response.json()


def check_health() -> dict:
    """Check agent health."""
    response = requests.get(f"{BASE_URL}/health", timeout=10)
    return response.json()


def rebuild_cache() -> dict:
    """Rebuild the tool cache."""
    response = requests.post(f"{BASE_URL}/cache/rebuild", timeout=60)
    return response.json()


def interactive_mode():
    """Interactive REPL for sending tasks."""
    print("LLMGraph Interactive Client")
    print("Type 'quit' to exit, 'health' to check status")
    print("-" * 40)

    while True:
        try:
            query = input("\n> ").strip()

            if not query:
                continue

            if query.lower() in ('quit', 'exit', 'q'):
                break

            if query.lower() == 'health':
                result = check_health()
                print(f"Status: {result['status']}")
                print(f"Tools loaded: {result['tools_loaded']}")
                print(f"MCP connected: {result['mcp_connected']}")
                continue

            if query.lower() == 'rebuild':
                print("Rebuilding cache...")
                result = rebuild_cache()
                print(f"Result: {result}")
                continue

            print("Processing...")
            result = send_task(query)

            if result['status'] == 'success':
                print(f"\n✅ {result['result']}")
            else:
                print(f"\n❌ Error: {result['error']}")

        except KeyboardInterrupt:
            break
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to server. Is it running?")
        except Exception as e:
            print(f"❌ Error: {e}")

    print("\nGoodbye!")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python client.py \"Your task here\"")
        print("  python client.py --health")
        print("  python client.py --interactive")
        print("  python client.py --rebuild-cache")
        sys.exit(1)

    arg = sys.argv[1]

    try:
        if arg == "--health":
            result = check_health()
            print(json.dumps(result, indent=2))

        elif arg == "--interactive" or arg == "-i":
            interactive_mode()

        elif arg == "--rebuild-cache":
            print("Rebuilding cache...")
            result = rebuild_cache()
            print(json.dumps(result, indent=2))

        else:
            # Treat as a task query
            query = " ".join(sys.argv[1:])
            data = ""

            # Check for --data flag
            if "--data" in sys.argv:
                data_idx = sys.argv.index("--data")
                data = sys.argv[data_idx + 1]
                query = " ".join(sys.argv[1:data_idx])

            print(f"Sending task: {query}")
            result = send_task(query, data)

            if result['status'] == 'success':
                print(f"\n✅ {result['result']}")
            else:
                print(f"\n❌ Error: {result['error']}")

    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to server at", BASE_URL)
        print("   Make sure the server is running: python server.py")
        sys.exit(1)


if __name__ == "__main__":
    main()