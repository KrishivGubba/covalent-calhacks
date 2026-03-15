import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))

# Add context-engine to path for model_interface
_context_engine_path = _project_root / "context-engine"
if str(_context_engine_path) not in sys.path:
    sys.path.insert(0, str(_context_engine_path))

from logger import get_logger
log = get_logger()
from model_interface import ModelFactory
from executor.vocab_code import capture_screenshot

# Bedrock model ID mapping
BEDROCK_MODELS = {
    "claude-sonnet-4-5-20250929": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "claude-3-5-sonnet-20241022": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "claude-3-7-sonnet-20250219": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
}

# Cached model factory instance
_model_factory = None


def _get_model_factory() -> ModelFactory:
    """Get or create the cached ModelFactory instance."""
    global _model_factory
    load_dotenv()
    if _model_factory is None:
        _model_factory = ModelFactory()
    return _model_factory


class LLM_Client:

    @staticmethod
    def generate(prompt: str, 
                 sys_prompt = "You are an automation agent. Respond ONLY with strict JSON for the action to execute.",
                 model = "claude-sonnet-4-5-20250929") -> dict:
        """
        Sends a prompt to the LLM via Bedrock Gateway and returns the response.
        Expects the LLM to respond with *only* JSON (no prose).
        """
        factory = _get_model_factory()
        chat_model = factory.get_chat_model("action_creation")
        
        # Map Anthropic model name to Bedrock ID if needed
        bedrock_model = BEDROCK_MODELS.get(model, model)
        
        response = chat_model.generate(
            prompt=prompt,
            system_prompt=sys_prompt,
            model=bedrock_model,
            max_tokens=512,
            temperature=0,
        )

        raw_output = response.strip()
        log.debug("this is the raw output\n" + raw_output)
        try:
            return raw_output
        except json.JSONDecodeError:
            raise ValueError(f"LLM returned invalid JSON:\n{raw_output}")
    
    @staticmethod
    def queryClaudeVision(prompt: str, image_path: str) -> dict:
        """
        Sends a prompt + screenshot to the vision model via Bedrock Gateway
        and expects a pure JSON response describing one action,
        e.g. {"type": "click", "coords": {"x": 512, "y": 300}}

        Args:
            prompt (str): Instruction for the model.
            image_path (str): Path to the screenshot (PNG/JPG).

        Returns:
            dict: Parsed JSON from the model.
        """
        factory = _get_model_factory()
        chat_model = factory.get_chat_model("action_creation")
        
        bedrock_model = BEDROCK_MODELS.get("claude-3-5-sonnet-20241022", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")
        
        response = chat_model.generate_with_vision(
            prompt=prompt,
            image_path=image_path,
            system_prompt="You are a coordinate-finding vision model. Respond only with valid JSON.",
            model=bedrock_model,
            max_tokens=256,
            temperature=0,
        )

        raw = response.strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError(f"LLM returned invalid JSON:\n{raw}")

        return parsed
    
    @staticmethod
    def queryForMessage(action: str, details: dict) -> str:
        """
        Generates a full LinkedIn-style message to send to someone,
        based on the current page screenshot + contextual details.

        Args:
            action (str): The high-level intent (e.g. "send connection message", "reply to recruiter").
            details (dict): Extra metadata like recipient name, topic, tone hints, etc.

        Returns:
            str: A long, natural language message (no JSON, no markup).
        """
        factory = _get_model_factory()
        chat_model = factory.get_chat_model("action_creation")

        # take screenshot of current page
        screenshot_path = capture_screenshot("msg_context.png")

        # build prompt
        prompt = f"""
You are a professional messaging assistant trained to compose warm, personalized LinkedIn or recruiter messages.

You will be given:
1. A **screenshot** of the current chat or LinkedIn page (showing message history or UI layout).
2. A short action description: what kind of message the user wants to send.
3. Some structured details about the recipient and context.

Your job:
- Write the *full text* of the message the user should send.
- The message should sound natural, friendly, and context-aware.
- Do NOT include any metadata, JSON, explanations, or quotes — return only the message text itself.
- Use a tone that fits LinkedIn or recruiter messaging (warm, concise, human).

Example output (correct):
Hi Alex! I saw your post about distributed systems — super interesting work. 
I've been exploring similar topics for a project at UW–Madison and would love to connect!

Example output (incorrect):
{{ "message": "Hi Alex..." }}  ❌
"Hi Alex..." ❌

Respond ONLY with the raw message body.

Action: {action}
Details: {json.dumps(details, indent=4)}
        """
        
        bedrock_model = BEDROCK_MODELS.get("claude-3-7-sonnet-20250219", "us.anthropic.claude-3-7-sonnet-20250219-v1:0")

        response = chat_model.generate_with_vision(
            prompt=prompt,
            image_path=screenshot_path,
            system_prompt="You are a message-writing assistant. Respond only with the message text.",
            model=bedrock_model,
            max_tokens=500,
            temperature=0.7,
        )

        # extract and clean the message
        message = response.strip()
        log.info("Generated message:\n" + message)
        return message
