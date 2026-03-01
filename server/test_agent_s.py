#!/usr/bin/env python3
"""
Test script for Agent-S integration.

This script tests the Agent-S executor with simple actions to verify
that everything is configured correctly.

Usage:
    python test_agent_s.py
"""

import os
import sys
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from agent_s_executor import create_executor_from_env

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_simple_action():
    """Test a simple action like opening an app."""
    logger.info("=" * 70)
    logger.info("Testing Agent-S Executor")
    logger.info("=" * 70)
    
    # Check environment variables
    logger.info("\n📋 Configuration:")
    logger.info(f"  Provider: {os.getenv('AGENT_S_PROVIDER', 'openai')}")
    logger.info(f"  Model: {os.getenv('AGENT_S_MODEL', 'gpt-5-2025-08-07')}")
    logger.info(f"  Grounding Provider: {os.getenv('AGENT_S_GROUNDING_PROVIDER', 'huggingface')}")
    logger.info(f"  Grounding URL: {os.getenv('AGENT_S_GROUNDING_URL', 'http://localhost:8080')}")
    logger.info(f"  Grounding Model: {os.getenv('AGENT_S_GROUNDING_MODEL', 'ui-tars-1.5-7b')}")
    logger.info(f"  Platform: {os.getenv('AGENT_S_PLATFORM', 'darwin')}")
    
    # Create executor
    try:
        logger.info("\n🤖 Creating Agent-S executor...")
        executor = create_executor_from_env()
        logger.info("✅ Executor created successfully")
    except Exception as e:
        logger.error(f"❌ Failed to create executor: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test action
    test_instructions = [
        # "Take a screenshot",  # Simple test
        "Open Safari",  # Basic app opening
        # "Open Safari and navigate to google.com",  # More complex
        # "Close all Safari windows",  # Cleanup
    ]
    
    for instruction in test_instructions:
        logger.info(f"\n{'=' * 70}")
        logger.info(f"📝 Testing instruction: {instruction}")
        logger.info(f"{'=' * 70}")
        
        try:
            result = executor.execute_action(
                instruction=instruction,
                max_steps=5,  # Shorter for testing
                step_delay=1.0
            )
            
            logger.info("\n📊 Results:")
            logger.info(f"  Success: {result['success']}")
            logger.info(f"  Steps Taken: {result['steps_taken']}")
            logger.info(f"  Completion Status: {result['completion_status']}")
            
            if result['error']:
                logger.error(f"  Error: {result['error']}")
            
            logger.info("\n📝 Execution Logs:")
            for log_line in result['logs']:
                logger.info(f"    {log_line}")
            
            if result['success']:
                logger.info(f"\n✅ Test PASSED for: {instruction}")
            else:
                logger.warning(f"\n⚠️  Test FAILED for: {instruction}")
                
            # Wait between tests
            if len(test_instructions) > 1:
                import time
                logger.info("\n⏳ Waiting 5 seconds before next test...")
                time.sleep(5)
            
        except Exception as e:
            logger.error(f"\n❌ Test failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    logger.info(f"\n{'=' * 70}")
    logger.info("🎉 All tests completed!")
    logger.info(f"{'=' * 70}")
    return True


def test_flask_integration():
    """Test the Flask API integration."""
    import requests
    
    logger.info("\n" + "=" * 70)
    logger.info("Testing Flask API Integration")
    logger.info("=" * 70)
    
    # Check if Flask server is running
    try:
        flask_port = os.environ.get('VITE_FLASK_PORT', '15001')
        response = requests.get(f"http://127.0.0.1:{flask_port}/health", timeout=5)
        if response.status_code == 200:
            logger.info("✅ Flask server is running")
        else:
            logger.error(f"❌ Flask server returned status {response.status_code}")
            return False
    except Exception as e:
        logger.error(f"❌ Flask server is not running: {e}")
        logger.info("   Please start the Flask server: cd server && python app.py")
        return False
    
    # Test trigger_action endpoint
    test_payload = {
        "action_uuid": "test-uuid-12345",
        "action": "Open Safari"
    }
    
    logger.info(f"\n📤 Sending test request to /trigger_action")
    logger.info(f"   Payload: {test_payload}")
    
    try:
        response = requests.post(
            f"http://127.0.0.1:{flask_port}/trigger_action",
            json=test_payload,
            timeout=120  # Long timeout for Agent-S execution
        )
        
        logger.info(f"\n📥 Response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            logger.info("✅ Request successful")
            logger.info(f"   Response: {result}")
            return True
        else:
            logger.error(f"❌ Request failed: {response.text}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Request failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Agent-S integration")
    parser.add_argument(
        "--test",
        choices=["executor", "flask", "all"],
        default="executor",
        help="Which test to run (default: executor)"
    )
    
    args = parser.parse_args()
    
    success = True
    
    if args.test in ["executor", "all"]:
        success = test_simple_action() and success
    
    if args.test in ["flask", "all"]:
        success = test_flask_integration() and success
    
    if success:
        logger.info("\n✅ All tests passed!")
        sys.exit(0)
    else:
        logger.error("\n❌ Some tests failed")
        sys.exit(1)

