import os
import json
from dotenv import load_dotenv
from executor.vocab_code import capture_screenshot, click_at, annotate_screenshot
from executor.llm_client_obj import LLM_Client

class ShowUIClaudeAdapter:
    """
    Claude-based drop-in replacement for ShowUIActor.
    Mimics ShowUI-2B’s interface but uses Claude 3.7 Sonnet (vision) to reason on screenshots.
    """
    _NAV_SYSTEM = """
    You are a visual navigation assistant that controls a computer screen.

    You will be given:
    • A **screenshot** that includes a coordinate grid overlay.
    • A **task instruction** describing what to accomplish.
    • A **history of previous actions** you have already taken.

    🧭 Coordinate Grid Overlay:
    - The screenshot is overlaid with a red/blue coordinate grid for spatial reference.
    - Red vertical lines are labeled x=0, x=173, x=346, ... up to x=1730.
    - Blue horizontal lines are labeled y=0, y=100, y=200, ... up to y=1000.
    - The coordinate origin (0,0) is at the **top-left corner** of the visible viewport.
    - These coordinates map directly to real pixel positions in the browser window.
    - Use them to choose **precise pixel coordinates** when deciding where to click, hover, or scroll.

    🎯 Clicking and Targeting Rules:
    - When you identify a button, link, or input field that matches the user’s goal,
      choose the **center point** of that element for the click coordinates.
      Do NOT click the edge or corner — always aim for the visual center of the element.
    - If multiple elements match, pick the most relevant and visible one.
    - If no relevant element is visible, use a "scroll" action to reveal more of the screen.
    - If the task appears complete, respond with "done".

    Think spatially — reason about where on the overlay each target is located.
    Your output will be executed directly as a browser action, so coordinates must be accurate.
    """

    _NAV_FORMAT = """
    Return exactly one JSON object describing your next action:

    {
        "type": "click" | "set_value" | "hover" | "scroll" | "wait" | "done",
        "coords": {"x": int, "y": int},      // pixel coordinates using the overlay grid (center of target)
        "value": "string (for set_value only, optional)",
        "direction": "up" | "down" (optional for scroll)
    }

    Rules:
    - Respond with only one JSON object, no prose.
    - Use integer pixel coordinates from the overlay.
    - Always target the **center** of visible elements when clicking or hovering.
    - Use "scroll" or "done" if interaction isn’t necessary.
    - Keep output strictly valid JSON.
    """

    def __init__(self, output_callback=print):
        load_dotenv()
        self.output_callback = output_callback
        self.action_history = []

        # 👇 Add a manual fallback coordinate for debugging
        self.default_click_coords = {"x": 1730, "y": 1000}

    def __call__(self, task: str):
        screenshot_path = capture_screenshot("page.png")
        screenshot_path = annotate_screenshot(screenshot_path)

        system_prompt = self._NAV_SYSTEM + "\n" + self._NAV_FORMAT
        action_history_text = "\n".join(json.dumps(a) for a in self.action_history)
        user_prompt = f"""
        Task: {task}
        Previous actions:
        {action_history_text if action_history_text else "None yet."}
        Return only the next JSON action.
        """

        result = LLM_Client.queryClaudeVision(
            f"{system_prompt}\n{user_prompt}",
            screenshot_path
        )

        self.output_callback(f"🤖 Claude output: {result}")
        self.action_history.append(result)
        return result

    def execute_action(self, action: dict):
        """
        Executes a Claude-generated action using your existing Playwright helpers.
        """
        t = action.get("type")
        if t == "click":
            coords = action.get("coords") or self.default_click_coords
            x, y = coords["x"], coords["y"] #TODO: is this shit right????
            self.output_callback(f"🖱️ Clicking at ({x}, {y})")
            click_at(x, y)

        elif t == "scroll":
            direction = action.get("direction", "down")
            from vocab_code import scroll_page
            self.output_callback(f"🖱️ Scrolling {direction}")
            scroll_page(direction=direction)

        elif t == "set_value":
            self.output_callback(f"⌨️ Would type: {action.get('value')}")

        elif t == "done":
            self.output_callback("✅ Task complete.")

        else:
            self.output_callback(f"⚠️ Unknown action: {t}")



# agent = ShowUIClaudeAdapter()

# # single step test
# action = agent("click on the message input box to ritesh neela.")
# agent.execute_action(action)
