from llm_client_obj import LLM_Client
import json

def decide(context_json):
    """
    Determines whether the user is trying to learn more about something
    (any topic, concept, process, person, place, etc.)
    based on their current context JSON.
    Returns True or False.
    """
    prompt = f"""
You are an intent classifier.

You will be given a JSON object called `context_json` describing what the user is currently doing.

Your job is to decide if the user’s intent is to **learn, understand, or gain knowledge** about *anything* — 
this includes:
- asking how something works,
- asking why something happens,
- seeking explanations, definitions, examples, comparisons, or tutorials,
- reading or watching educational content,
- searching for background info, guides, or “how to” material.

It does **not** include:
- performing an action (e.g., booking, coding, emailing, debugging, purchasing),
- executing a task the user already understands,
- social or communication activities.

Respond **only** with a JSON object in this exact format:
{{ "res": "True" }} or {{ "res": "False" }}

context_json:
{json.dumps(context_json, indent=4)}
    """

    response = LLM_Client.generate(
        prompt=prompt.strip(),
        sys_prompt="You are a precise intent classifier that decides if the user is trying to learn or understand something new.",
model="claude-3-opus-latest"

    )

    # handle both dict or string return
    if isinstance(response, dict):
        val = response.get("res")
        return str(val).lower() == "true"
    if isinstance(response, str):
        return "true" in response.lower()
    return False



if __name__ == "__main__":
    samples = [
        {"action": "the user seems to have a question", "details": "what is the difference between supervised and unsupervised learning"},
        {"action": "the user is searching something up", "details": "looking for a place to eat near San Francisco"},
        {"action": "the user is debugging some code", "details": "trying to fix a syntax error in my Python script"},
        {"action": "the user is reading an article", "details": "reading about how blockchain consensus algorithms work"},
        {"action": "the user is composing an email", "details": "writing a follow-up to the recruiter about interview scheduling"},
    ]

    print("=== Intent Classification Test ===")
    for i, ctx in enumerate(samples, 1):
        result = decide(ctx)
        print(f"Sample {i}:")
        print(f"  action  = {ctx['action']}")
        print(f"  details = {ctx['details']}")
        print(f"  → learning intent? {result}\n")
