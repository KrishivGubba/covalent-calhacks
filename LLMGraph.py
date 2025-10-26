import uuid
from typing import TypedDict, Literal, List
import asyncio

import os

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from anthropic import Anthropic
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from pydantic import BaseModel, Field
import dotenv
dotenv.load_dotenv()

from composio import Composio
composio = Composio(
    api_key=os.getenv("COMPOSIO_API_KEY"),

)

gmail_auth_config_id = os.getenv("GOOGLE_AUTH_CONFIG_ID")

llm = init_chat_model(
    model_provider="anthropic",
    model="claude-sonnet-4-5-20250929",
)

class Task(BaseModel):
    prompt: str = Field(
        description="The details of the task that the MCP has to perform",
    )
    node: Literal[
        "gsuite",
        "screen controller"
    ] = Field(
        description="The MCP server that has to be called",
    )

class Output(BaseModel):
    node: Literal["gsuite", "screen controller"]
    result: dict


# State schema for the overall graph
class State(TypedDict):
    # The prompt given by the tree
    task: str

    # The data given by the tree
    data: str

    # The list of tasks that include the server name and task that each mcp has to perform
    mcp_tasks: List[Task]

    # The list of outputs the nodes will write to (somehow)
    mcp_outputs: List[Output]


class LLMTasks(BaseModel):
    mcp_tasks: List[Task]


model = llm.with_structured_output(LLMTasks)
worker_agent = Anthropic()

def search_task(server_name: str, task_list: List[Task]) -> str:
    """
    This is the method that given a server and Task list, finds the task for the mcp server
    :param server_name: the name of the server
    :param task_list: the list of tasks that are in the state object
    :return: the task the server has to perform
    """
    for task in task_list:
        if task.node == server_name:
            return task.prompt


# Orchestrator node assigns tasks to specific workers explicitly
def orchestrator(state: State):
    plan_of_action = model.invoke(
        [
            SystemMessage(content=f"""
            You are an orchestrator agent. Analyze the user's query and assign tasks to the appropriate workers.

            - If the query has multiple parts, parse through it and split it into individual tasks.
            - If the task involves doing an action via the gsuite (calendar, drive, docs, sheets, slides, gmail)
            or anything related (event, task, presentation, email etc.) the task will use the 'gsuite' node
            -  If there exists any task that cannot be completed with the gsuite, it should be a screen controller task
            
            Example: 
                User: Write an email to rneela@wisc.edu to follow up with yesterday's meeting, then go to google and search
                up for some videos of kittens playing with puppies
                
                Output: mcp_tasks = [
                Task(task="Send email to rneela@wisc.edu following up about yesterday's meeting", node="gsuite"),
                Task(task="Go to google and search for videos of kittens playing with dogs", node="screen controller"),
                
            Here is some information about the task that may prove useful : 
            {state['data']}
                
            """),
            HumanMessage(state['task']),
        ]
    )
    return {
        "mcp_tasks": plan_of_action.mcp_tasks,
        "mcp_outputs": []
    }

async def gsuite(state : State):
    user_id = os.getenv("USER_ID")
    connected_accounts = composio.connected_accounts.list(
        user_ids=[user_id], # this is set to xxx to always bypass the filtering and setup and new auth every time
        auth_config_ids=["ac_cgbJXrl-9yI4"],
        toolkit_slugs=["GMAIL"]
    )
    active_connection = None

    for account in connected_accounts.items:
        if account.status == "ACTIVE":
            active_connection = account
            break
    connected_account = None
    if active_connection:
        print("Active connection - Don't need to authenticate again")
        connected_account = active_connection
    else:
        print("No active connection: We will try authenticating again")
        connection_request = composio.connected_accounts.link(
            user_id=user_id,
            auth_config_id="ac_cgbJXrl-9yI4",
        )
        redirect_url = connection_request.redirect_url
        print(f'Please authorize the app by visiting this URL: {redirect_url}')
        connected_account = connection_request.wait_for_connection()

    print(f'Connection established successfully! Connected account id: {connected_account.id}')
    session = composio.experimental.tool_router.create_session(user_id=user_id)
    client = MultiServerMCPClient(
        {
            "gsuite": {
                "transport" : "streamable_http",
                "url" : session['url']
            }
        }
    )
    tools = await client.get_tools()

    agent = create_agent(
        "anthropic:claude-sonnet-4-5",
        tools
    )

    gsuite_tasks = [task.prompt for task in state['mcp_tasks'] if task.node == "gsuite"]
    task_content = " ".join(gsuite_tasks) if gsuite_tasks else ""

    result = await agent.ainvoke(
        input={"messages": [
            {"role": "system",
             "content": """
             - You are a helpful GSuite agent.
             - Your task is to take the user's query, and use the provided tools to do what the user asked.
             - You do not need to confirm or ask for permission. SEND THE EMAIL. TRY SENDING IT EVEN IF YOU THINK YOU DON'T HAVE PROPER AUTHENTICATION. JUST SEND IT.
             - Remember not to leave any fields blank.
             - If you have to modify something, first check if it's empty or not before trying to delete anything 
             """},
            {"role": "user",
             "content": task_content
             }
        ]},
    )
    return {"mcp_outputs": state['mcp_outputs'] + [Output(node="gsuite",result=result)]}

def screen_controller(state : State):
    print([task.prompt for task in state['mcp_tasks']])

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

graph.add_node("gsuite", gsuite)
graph.add_node("orchestrator", orchestrator)

graph.add_edge(START, "orchestrator")
graph.add_edge("orchestrator", "gsuite")
graph.add_edge("gsuite", END)

# Compile and invoke the graph with hardcoded inputs
compiled = graph.compile()
user_query = """
    Can you look up some images for a cute beagle online? 
    """
data = ""

async def run_graph(user_query : str = "", data : str = ""):
    final_output = await compiled.ainvoke({"task": user_query, "data" : data})
    print(final_output["mcp_outputs"])


asyncio.run(run_graph())