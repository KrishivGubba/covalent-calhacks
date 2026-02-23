import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
import os
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))
from logger import get_logger
log = get_logger()

# Load environment variables from .env file
load_dotenv()

# Get AWS credentials from environment variables
aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID')
aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY')
aws_region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')  # default to us-east-1 if not set

# Create a Bedrock Runtime client in the AWS Region you want to use.
client = boto3.client("bedrock-runtime", region_name="us-east-1")
# Set the model ID, e.g., Claude 3 Haiku.
model_id = "us.anthropic.claude-sonnet-4-20250514-v1:0"
# Start a conversation with the user message.
user_message = "this is a test message - say hello!"
conversation = [
 {
 "role": "user",
 "content": [{"text": user_message}],
 }
]
try:
 # Send the message to the model, using a basic inference configuration.
 response = client.converse(
 modelId=model_id,
 messages=conversation,
 inferenceConfig={"maxTokens": 512, "temperature": 0.5, "topP": 0.9},
 )
 # Extract and print the response text.
 response_text = response["output"]["message"]["content"][0]["text"]
 log.info(response_text)
except (ClientError, Exception) as e:
 log.error(f"ERROR: Can't invoke '{model_id}'. Reason: {e}")
 exit(1)