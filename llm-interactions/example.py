"""
Example usage of LLMClient.

Run this to test the unified LLM interface.
"""
import sys
from pathlib import Path

# Add parent directory to path (required because directory has hyphen)
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the client
from llm_interactions import LLMClient


def main():
    """Example usage of LLMClient."""
    print("🤖 Initializing LLM Client...")
    client = LLMClient()
    print(f"✅ Using provider: {client.provider}")
    
    # Simple query
    print("\n📝 Test 1: Simple query")
    response = client.generate("What is 2+2?")
    print(f"Response: {response}")
    
    # With system prompt
    print("\n📝 Test 2: With system prompt")
    response = client.generate(
        prompt="Explain quantum computing in one sentence",
        system_prompt="You are a helpful physics teacher."
    )
    print(f"Response: {response}")
    
    # With custom parameters
    print("\n📝 Test 3: Custom parameters")
    response = client.generate(
        prompt="Write a haiku about coding",
        temperature=0.9,
        max_tokens=100
    )
    print(f"Response: {response}")


if __name__ == "__main__":
    main()
