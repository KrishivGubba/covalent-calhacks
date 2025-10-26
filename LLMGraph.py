import uuid
from typing import TypedDict, Literal, List
import asyncio

import os

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Send
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
import dotenv
dotenv.load_dotenv()

from composio import Composio
composio = Composio(api_key=os.getenv("COMPOSIO_API_KEY"))

gmail_auth_config_id = os.getenv("GOOGLE_AUTH_CONFIG_ID")
user_uuid = "ea208670-a797-4fdb-b527-63942d74dd70"


def authenticate_toolkit(user_id: str, auth_config_id: str):
    """
    Authentication for composio. Authenticates gsuite-master-auth which gives authentication to EVERYTHING you can think of
    :param user_id: user_id of the user
    :param auth_config_id: master config
    :return: returns the connection request id for use
    """
    connection_request = composio.connected_accounts.initiate(
        user_id=user_id,
        auth_config_id=auth_config_id,
    )
    print(
        f"Visit this URL to authenticate Gmail: {connection_request.redirect_url}"
    )
    # This will wait for the auth flow to be completed
    connection_request.wait_for_connection(timeout=15)
    return connection_request.id

connection_id = authenticate_toolkit(user_uuid, gmail_auth_config_id) # highlight : Important user connection id for use in tool servers
# You can also verify the connection status using:
connected_account = composio.connected_accounts.get(connection_id)
print(f"Connected account: {connected_account}")

llm = init_chat_model(
    model_provider="google_genai",
    model="gemini-2.5-flash",
)


class Task(BaseModel):
    task: str = Field(
        description="The details of the task that the MCP has to perform",
    )
    server: Literal[
        "drive",
        "docs",
        "calendar",
        "sheets",
        "slides",
        "mail"
    ] = Field(
        description="The MCP server that has to be called",
    )


class Output(BaseModel):
    server: Literal["drive", "docs", "calendar", "sheets", "slides", "mail"]
    result: str


# State schema for the overall graph
class State(TypedDict):
    task: str

    # The list of tasks that include the server name and task that each mcp has to perform
    mcp_tasks: List[Task]

    # The list of outputs the nodes will write to (somehow)
    mcp_outputs: List[Output]


class LLMTasks(BaseModel):
    mcp_tasks: List[Task]


model = llm.with_structured_output(LLMTasks)


def search_task(server_name: str, task_list: List[Task]) -> str:
    """
    This is the method that given a server and Task list, finds the task for the mcp server
    :param server_name: the name of the server
    :param task_list: the list of tasks that are in the state object
    :return: the task the server has to perform
    """
    for task in task_list:
        if task.server == server_name:
            return task.task


# Orchestrator node assigns tasks to specific workers explicitly
def orchestrator(state: State):
    plan_of_action = model.invoke(
        [
            SystemMessage(content="""
            You are an orchestrator agent. Analyze the user's query and assign tasks to the appropriate workers.

            - If the query involves any of the given keywords, drive, docs, calendar, sheets, slides, mail, based on the 
            user's query, create a task the user wants to be done with that service
            - If the user doesn't mention any task for that keyword, just put in n/a and nothing else
            - Don't touch mcp_outputs parameter of State class

            """),
            HumanMessage(state['task']),
        ]
    )
    return {
        "mcp_tasks": plan_of_action.mcp_tasks,
        "mcp_outputs": []
    }

async def gsuite(state : State):
    client = MultiServerMCPClient(
        {
            "gsuite": {
                "transport": "stdio",
                "command": "python",
                "args": ""
            }
        }
    )

    tools = await client.get_tools()
    gsuite_worker = llm.with_config(tools)


# Worker nodes get assigned explicitly
# async def drive_worker(state: State):
#     input_text = search_task("drive", state['mcp_tasks'])
#     # from client import main
#     # result = await main(prompt=input_text, server="drive")
#     toolset = composio.tools.get(user_id=user_uuid, toolkits=["DRIVE"])
#     docs_model = llm.with_structured_output(Task).with_config(toolset)
#     result = docs_model.ainvoke(input=input_text)
#     return {"mcp_outputs": state['mcp_outputs'] + [Output(server="drive", result=result)]}
#
#
# async def docs_worker(state: State):
#     input_text = search_task("docs", state['mcp_tasks'])
#     # from client import main
#     # result = await main(prompt=input_text, server="docs")
#     toolset = composio.tools.get(user_id=user_uuid, toolkits=["DOCS"])
#     docs_model = llm.with_structured_output(Task).with_config(toolset)
#     result = docs_model.ainvoke(input=input_text)
#     return {"mcp_outputs": state['mcp_outputs'] + [Output(server="docs", result=result)]}
#
#
# async def calendar_worker(state: State):
#     input_text = search_task("calendar", state['mcp_tasks'])
#     # from client import main
#     # result = await main(prompt=input_text, server="calendar")
#     toolset = composio.tools.get(user_id=user_uuid, toolkits=["CALENDAR"])
#     docs_model = llm.with_config(toolset)
#     result = docs_model.ainvoke(input=input_text)
#     return {"mcp_outputs": state['mcp_outputs'] + [Output(server="calendar", result=result)]}
#
#
# async def sheets_worker(state: State):
#     input_text = search_task("sheets", state['mcp_tasks'])
#     # from client import main
#     # result = await main(prompt=input_text, server="sheets")
#     toolset = composio.tools.get(user_id=user_uuid, toolkits=["SHEETS"])
#     docs_model = llm.with_structured_output(Task).with_config(toolset)
#     result = docs_model.ainvoke(input=input_text)
#     return {"mcp_outputs": state['mcp_outputs'] + [Output(server="sheets", result=result)]}
#
#
# async def slides_worker(state: State):
#     input_text = search_task("slides", state['mcp_tasks'])
#     # from client import main
#     # result = await main(prompt=input_text, server="slides")
#     toolset = composio.tools.get(user_id=user_uuid, toolkits=["SLILDES"])
#     docs_model = llm.with_structured_output(Task).with_config(toolset)
#     result = docs_model.ainvoke(input=input_text)
#     return {"mcp_outputs": state['mcp_outputs'] + [Output(server="slides", result=result)]}
#
#
# async def mail_worker(state: State):
#     input_text = search_task("mail", state['mcp_tasks'])
#     # from client import main
#     # result = await main(prompt=input_text, server="mail")
#     toolset = composio.tools.get(user_id=user_uuid, toolkits=["GMAIL"])
#     docs_model = llm.with_structured_output(Task).with_config(toolset)
#     result = docs_model.ainvoke(input=input_text)
#     return {"mcp_outputs": state['mcp_outputs'] + [Output(server="mail", result=result)]}
#
#
# def synthesizer(state: State):
#     results = []
#     outputs = state['mcp_outputs']
#     for output in outputs:
#         results.append(output.result)
#     combined = " | ".join(results) if results else ""
#     return {"combined_result": combined}
#
#
# def assign_workers(state: State):
#     sends = []
#     tasks = state['mcp_tasks']
#     for task in tasks:
#         if task.server == "docs":
#             if task.task != "n/a":
#                 sends.append(Send("docs_worker", state))
#         if task.server == "sheets":
#             if task.task != "n/a":
#                 sends.append(Send("sheets_worker", state))
#         if task.server == "slides":
#             if task.task != "n/a":
#                 sends.append(Send("slides_worker", state))
#         if task.server == "mail":
#             if task.task != "n/a":
#                 sends.append(Send("mail_worker", state))
#         if task.server == "drive":
#             if task.task != "n/a":
#                 sends.append(Send("drive_worker", state))
#         if task.server == "calendar":
#             if task.task != "n/a":
#                 sends.append(Send("calendar_worker", state))
#     return sends


# Build the workflow graph
graph = StateGraph(State)

# graph.add_node("orchestrator", orchestrator)
# graph.add_node("drive_worker", drive_worker)
# graph.add_node("docs_worker", docs_worker)
# graph.add_node("calendar_worker", calendar_worker)
# graph.add_node("sheets_worker", sheets_worker)
# graph.add_node("slides_worker", slides_worker)
# graph.add_node("mail_worker", mail_worker)
# graph.add_node("synthesizer", synthesizer)
graph.add_node("gsuite", gsuite)

graph.add_edge(START, "orchestrator")
graph.add_edge("orchestrator", "gsuite")
graph.add_edge("gsuite", END)

# graph.add_conditional_edges("orchestrator", assign_workers)

# graph.add_edge("drive_worker", "synthesizer")
# graph.add_edge("docs_worker", "synthesizer")
# graph.add_edge("calendar_worker", "synthesizer")
# graph.add_edge("sheets_worker", "synthesizer")
# graph.add_edge("slides_worker", "synthesizer")
# graph.add_edge("mail_worker", "synthesizer")

graph.add_edge("synthesizer", END)

# Compile and invoke the graph with hardcoded inputs
compiled = graph.compile()
user_query = "Make a google doc called \" it worked! \", create a calendar event called haircut and send an email to riteshneela@wisc.edu"


async def run_graph():
    final_output = await compiled.ainvoke({"task": user_query})
    print(final_output["combined_result"])


asyncio.run(run_graph())