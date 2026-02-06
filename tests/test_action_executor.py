"""
Minimal test - shows raw LLM outputs from Bedrock.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path so we can import action_executor
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from action_executor import gather_context, plan_action, health_check


async def test():
    health = await health_check()
    if health['status'] != 'healthy':
        return
    
    action_text = "Send an email to ritesh about the latest developments in the USA"
    initial_context = """
Known information:
- Ritesh's email is ritesh@example.com
"""
    
    # Phase 0: Research - LLM decides what resources to read
    research_result = await gather_context(action_text, initial_context)
    
    # Phase 1: Planning - LLM proposes tool + parameters  
    await plan_action(action_text, research_result['context'])


if __name__ == "__main__":
    asyncio.run(test())
