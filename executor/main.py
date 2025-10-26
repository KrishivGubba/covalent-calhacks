from llm_client_obj import LLM_Client
import json
from learn_helper import LearnObject
from vocab_code import click_at, insert_at


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


def decideIsMessageSending(context_json):
    """
    Determines whether the user is trying to send or compose a message,
    chat, comment, reply, or otherwise communicate with another person online.

    Returns True or False.
    """
    prompt = f"""
You are an intent classifier.

You will be given a JSON object called `context_json` describing what the user is currently doing.

Your task is to decide if the user’s intent involves **sending, writing, or preparing a message or communication** 
to another person or group.

This includes:
- typing in a chat box or DM window (Slack, Discord, LinkedIn, Gmail, Messenger, etc.)
- replying to a message or email
- composing a comment or post on social media
- filling a “message”, “reply”, or “chat” text field
- engaging in conversation or communication of any form

It does **not** include:
- reading messages without replying,
- searching for information,
- performing unrelated tasks (coding, browsing, buying, learning, watching videos, etc.).

Respond **only** with a JSON object in this exact format:
{{ "res": "True" }} or {{ "res": "False" }}

context_json:
{json.dumps(context_json, indent=4)}
    """

    response = LLM_Client.generate(
        prompt=prompt.strip(),
        sys_prompt="You are a precise intent classifier that decides if the user is composing or sending a message to someone.",
        model="claude-3-opus-latest"  # haiku or sonnet are both fine here
    )

    # handle both dict or string return
    if isinstance(response, dict):
        val = response.get("res")
        return str(val).lower() == "true"
    if isinstance(response, str):
        return "true" in response.lower()
    return False


def thingy(contextJson):
    #somehow the context has to be passed to us, maybe we can hit an endpoint
    # contextJson = {
    #     "action" : "the user is searching things up about spiders",
    #     "details" : "the user seems to want to learn more about spiders and how they mate"
    # }
    if decide(context_json = contextJson): #learning intention has been detected
        action = contextJson.get("action", "")
        details = contextJson.get("details", "")
        if not action and  not details:
            raise Exception("Need to provide action and/or details for a search to take place")
        allQueries = LearnObject.generateQueries(action, details)
        lo = LearnObject()
        for query in allQueries:
            lo.googleSearchAndClick(query)
        lo.youtubeSearchUp(allQueries[0])
        lo.switchToTabByIndex(0)
    else:
        if decideIsMessageSending(context_json=contextJson):
            click_at(642, 767)
            action, details = contextJson["action"], contextJson["details"]
            messageToBeSent = LLM_Client.queryForMessage(action, details)
            insert_at(messageToBeSent)
            click_at(1007, 884)
        else:
            print("not sending a message")

if __name__ == "__main__":
    samples = [
        # {"action": "the user seems to have a question", "details": "what is the difference between supervised and unsupervised learning"},
        # {"action": "the user is searching something up", "details": "looking for a place to eat near San Francisco"},
        # {"action": "the user is debugging some code", "details": "trying to fix a syntax error in my Python script"},
        # {"action": "the user is reading an article", "details": "reading about how blockchain consensus algorithms work"},
        {"action": "the user is texting someone on linkedin", "details": "the user is dming ritesh neela"},
    ]

    print("=== Intent Classification Test ===")
    for i, ctx in enumerate(samples, 1):
        result = thingy(ctx)
        print(f"Sample {i}:")
        print(f"  action  = {ctx['action']}")
        print(f"  details = {ctx['details']}")
        print(f"  → messaging someone? {result}\n")