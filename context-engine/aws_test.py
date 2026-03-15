"""
Test script for AWS Bedrock via the unified model interface.

This script tests the bedrock provider integration through model_interface.py,
which routes through GatewayClient -> Lambda -> AWS Bedrock.

Usage:
    python aws_test.py
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))
from logger import get_logger
log = get_logger()

# Load environment variables
load_dotenv()

from model_interface import ModelFactory


def main():
    """Test the Bedrock integration via model_interface."""
    log.info("Testing Bedrock integration via model_interface...")
    
    try:
        # Create model factory and get a chat model
        factory = ModelFactory()
        model = factory.get_chat_model("action_creation")
        
        log.info(f"Provider: {model.provider}")
        log.info(f"Model: {model.model_name}")
        
        # Test message
        user_message = "this is a test message - say hello!"
        
        log.info(f"Sending: {user_message}")
        response = model.generate(user_message)
        
        log.info(f"Response: {response}")
        log.info("Test completed successfully!")
        
    except Exception as e:
        log.error(f"ERROR: Test failed. Reason: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
