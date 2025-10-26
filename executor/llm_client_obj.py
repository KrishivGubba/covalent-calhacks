import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic

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
            parsed = json.loads(raw_output)
        except json.JSONDecodeError:
            raise ValueError(f"Claude returned invalid JSON:\n{raw_output}")

        return parsed


# test it
if __name__ == "__main__":
    output = LLM_Client.queryClaude("""
    The current webpage has a login form.
    Decide the next action as JSON with keys {action, selector, value}.
    """)

    print(output)
