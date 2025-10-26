import json
from action_run import parse_and_run, get_simplified_dom  # reuse your executor
import time
from llm_client_obj import LLM_Client

class Action:
    def __init__(self, contextJson):
        """
        dom_snapshot: simplified JSON representation of the current DOM
        context: info from your friend's module (task intent, user goal, etc.)
        prev_action: optional info about last executed step
        """
        # if "goal" not in contextJson or "details" not in contextJson: TODO: uncomment thisl ater
        #     raise KeyError("Must provide both goal and details in the contextJson")
        self.dom_snapshot = get_simplified_dom()
        self.context = contextJson
        self.prev_action = None
        self.last_change = None
        self.result = None

    def query_llm(self, llm_client : LLM_Client):
        """
        Build the structured prompt and query the LLM for the next step.
        Returns parsed JSON action spec.
        """
        prompt = f"""
You are a deterministic web-automation planner.
You will be given:
- a goal
- details about the user's intent
- the last DOM change
- the current DOM snapshot

You must output exactly ONE JSON object describing the next action to take on the web page.

⚙️ EXECUTION SPECIFICATION
The JSON must follow this schema:

{{
    "type": "click" | "set_value" | "scroll" | "wait" | "hover" | "navigate" | "extract" | "done",
    "selector": "CSS selector or text id to target (omit if not applicable)",
    "value": "string (required only for 'set_value')",
    "url": "string (required only for 'navigate')",
    "direction": "down" | "up" (optional, for scroll),
    "amount": 800 (integer, optional, for scroll),
    "duration": number (optional, for wait)
}}

⚠️ RULES
- Return exactly ONE JSON object — not an array or prose.
- Use only the fields that apply for the chosen action type.
- Prefer 'click' or 'set_value' when a visible element matches the goal.
- Use 'scroll' ONLY if there are no interactive elements in the visible DOM or no action can progress the goal.
- When scrolling, use {{ "direction": "down", "amount": 800 }} by default.
- When the task appears complete, return {{ "type": "done" }}.
- Do not include any explanations, comments, or markdown formatting.
- Output must be valid JSON that can be parsed by json.loads() with no errors.

🚫 AVOID RE-INTERACTION
- Never interact with elements that are already filled, checked, disabled, hidden, or marked as completed.
- Do not click buttons or inputs that appear to have already been pressed, submitted, or contain confirmation text.
- If all actionable elements are already filled or disabled, prefer a 'scroll' or 'done' action instead.
- DO NOT EVER REPEAT PREVIOUS ACTIONS

🧭 CONTEXT
Goal: {self.context['goal']}
Details: {self.context['details']}
Previous action: {self.prev_action}
Last DOM change: {self.last_change}
Current DOM snapshot:
{self.dom_snapshot}

Return only the JSON action now.
"""


        llm_output = llm_client.generate(prompt)
        print(llm_output, "this is the output from claude")
        return self._parse_action(llm_output)

    def _parse_action(self, raw):
        """Validate/parse LLM JSON output."""
        try:
            action = json.loads(raw)
            return action
        except Exception:
            pass
            # raise ValueError(f"❌ Bad LLM output (not JSON): {raw}")
        return raw

    def execute(self, action):
        """
        Execute the parsed action using your run_actions.py executor.
        """
        try:
            print(f"⚙️  Executing action: {action}")
            parse_and_run(action)  
            self.prev_action = action
            self.result = f"Executed {action['type']} on {action.get('selector')}"
            print("✅ Execution done.")
        except Exception as e:
            self.result = f"❌ Failed to execute {action}: {e}"
            print(self.result)
        return self.result

    def update_dom_change(self, new_dom):
        """Compute and store DOM delta for feedback loop."""
        diff = Action.compute_dom_diff(self.dom_snapshot, new_dom)
        self.last_change = diff
        self.dom_snapshot = new_dom
        return diff

    @staticmethod
    def compute_dom_diff(prev_dom, new_dom):
        """Compare simplified DOM snapshots and return a diff summary."""
        diff = {"added": [], "removed": [], "modified": []}
        old_keys, new_keys = set(prev_dom.keys()), set(new_dom.keys())

        for k in new_keys - old_keys:
            diff["added"].append({k: new_dom[k]})
        for k in old_keys - new_keys:
            diff["removed"].append(k)
        for k in old_keys & new_keys:
            if prev_dom[k] != new_dom[k]:
                diff["modified"].append({"id": k, "old": prev_dom[k], "new": new_dom[k]})

        # cleanup
        for k in list(diff.keys()):
            if not diff[k]:
                del diff[k]

        return diff

# with open("/Users/krishivgubba/Dev/covalent-calhacks/executor/testscroll.json", "r") as data:
#     time.sleep(4)
#     thing = Action("", "", "")
#     thing.execute(json.load(data))
for i in range(10):
    contextJson = {
        "goal" : "the user is trying to apply for a job",
        "details" : """
user details:
first name: krishiv
last name: gubba
phone number: 8476682616
email: kgubba@wisc.edu
                    """
    }
    first = Action(contextJson=contextJson)
    client = LLM_Client()
    output = first.query_llm(client)
    first.execute(output)
    newDom = first.update_dom_change(get_simplified_dom())
    with open("/Users/krishivgubba/Dev/covalent-calhacks/executor/something.json", "w") as file:
        file.write(json.dumps(first.dom_snapshot))

#TODO: terminate when the LLM wants you to scroll on a page where you've already reached the bottom

