import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic
import base64
from executor.vocab_code import capture_screenshot

class LLM_Client:

    @staticmethod
    def generate(prompt: str, 
                 sys_prompt = "You are an automation agent. Respond ONLY with strict JSON for the action to execute.",
                 model = "claude-3-7-sonnet-20250219") -> dict:
        """
        Sends a prompt to Claude and returns parsed JSON.
        Expects Claude to respond with *only* JSON (no prose).
        """
        # load your .env file once
        load_dotenv()

        # initialize client (make sure the key matches your .env variable)
        client = Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))

        if not client.api_key:
            raise ValueError("❌ CLAUDE_API_KEY not found. Check your .env or environment variables.")

        # use the latest non-deprecated model
        response = client.messages.create(
            model=model,
            max_tokens=512,
            temperature=0,
            system=sys_prompt,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Claude returns content as a list of message blocks
        raw_output = response.content[0].text.strip()
        print("this is the raw output\n", raw_output)
        try:
            return raw_output
        except json.JSONDecodeError:
            raise ValueError(f"Claude returned invalid JSON:\n{raw_output}")

        return parsed
    
    @staticmethod
    def queryClaudeVision(prompt: str, image_path: str) -> dict:
        """
        Sends a prompt + screenshot to Claude (vision model)
        and expects a pure JSON response describing one action,
        e.g. {"type": "click", "coords": {"x": 512, "y": 300}}

        Args:
            prompt (str): Instruction for the model.
            image_path (str): Path to the screenshot (PNG/JPG).

        Returns:
            dict: Parsed JSON from Claude.
        """
        load_dotenv()

        api_key = os.getenv("CLAUDE_API_KEY")
        if not api_key:
            raise ValueError("❌ CLAUDE_API_KEY missing. Check your .env file.")

        client = Anthropic(api_key=api_key)

        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        response = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=256,
            temperature=0,
            system="You are a coordinate-finding vision model. Respond only with valid JSON.",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64
                    }}
                ]}
            ]
        )

        raw = response.content[0].text.strip()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            raise ValueError(f"❌ Claude returned invalid JSON:\n{raw}")

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
        load_dotenv()
        api_key = os.getenv("CLAUDE_API_KEY")
        if not api_key:
            raise ValueError("❌ CLAUDE_API_KEY missing. Check your .env file.")

        client = Anthropic(api_key=api_key)

        # take screenshot of current page
        screenshot_path = capture_screenshot("msg_context.png")
        with open(screenshot_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

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
I’ve been exploring similar topics for a project at UW–Madison and would love to connect!

Example output (incorrect):
{{ "message": "Hi Alex..." }}  ❌
"Hi Alex..." ❌

Respond ONLY with the raw message body.

Action: {action}
Details: {json.dumps(details, indent=4)}
        """

        response = client.messages.create(
            model="claude-3-7-sonnet-20250219",  # Sonnet is better for writing quality here
            max_tokens=500,
            temperature=0.7,
            system="You are a message-writing assistant. Respond only with the message text.",
            messages=[
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image", "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_b64
                    }}
                ]}
            ]
        )

        # extract and clean the message
        message = response.content[0].text.strip()
        print("📨 Generated message:\n", message)
        return message


# # test it
# if __name__ == "__main__":
#     output = LLM_Client.queryClaude("""
#     The current webpage has a login form.
#     Decide the next action as JSON with keys {action, selector, value}.
#     """)

#     print(output)
