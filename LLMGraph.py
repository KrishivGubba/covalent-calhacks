from typing import TypedDict, Literal, List
from typing_extensions import TypedDict
import asyncio
import os
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from anthropic import Anthropic
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langgraph.types import Send
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

# Always the kind of task used for the mcp server
class MCPTask(BaseModel):
    prompt: str = Field(
        description="The details of the task that the MCP has to perform",
    )
    # node: Literal[
    #     "gsuite",
    #     "screen controller"
    # ] = Field(
    #     description="The MCP server that has to be called",
    # )

class SCTask(TypedDict):
    # The prompt for krishiv's LLM
    action: str

    # The relevant details for krishiv's LLM
    details : str


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
    mcp_tasks: List[MCPTask]

    # The list of tasks that the screen controller has to complete
    sc_tasks: List[SCTask]

    # The list of outputs the nodes will write to (somehow)
    mcp_outputs: List[Output]

    # The final synthesized output
    final_outputs: str


class LLMTasks(BaseModel):
    mcp_tasks: List[MCPTask]
    sc_tasks: List[SCTask]


model = llm.with_structured_output(LLMTasks)
worker_agent = Anthropic()

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
            or sc_task.  
            - A screen controller task must be split into a list of the smallest executable tasks possible 
            - Make sure to extract the email address of the person you want to send the email to and use that to send the email. DO NOT CREATE TEMPLATE EMAILS OR CALENDAR INVITES - JUST WRITE AND SEND THE EMAIL WITH WHATEVER INFORMATION YOU ARE GIVEN
            - when creating an MCP task, make sure to include ALL information needed to complete the task like the email, time, date, etc. 

            Example: 
                User: Write an email to rneela@wisc.edu to follow up with yesterday's meeting, then go to google and search
                up for some videos of kittens playing with puppies
                
                Output: mcp_tasks = [
                Task(task="Send email to rneela@wisc.edu following up about yesterday's meeting", node="gsuite"),
                Task(task="Go to google and search for videos of kittens playing with dogs", node="screen controller"),
                ]
                
            Example 2: 
                User: Send a message to Ritesh Neela on LinkedIn telling him how much of a good time the user had during the meeting
                Provided data: The user had a lot of fun at the meeting yesterday and the current screen is the open dm with Ritesh
                Neela.
                
                Output: sc_tasks = [
                   SCTask(action="Write a message about how much fun you had at the meeting yesterday", "details"="Current screen is the dm with Ritesh on LinkedIn"),
                   SCTask(action="Press send on the send button", details="")
                   ]
                
            Here is some information about the task that may prove useful : 
            {state['data']}
                
            """),
            HumanMessage(state['task']),
        ]
    )
    # print(plan_of_action)
    return {
        "mcp_tasks": plan_of_action.mcp_tasks,
        "sc_tasks": plan_of_action.sc_tasks,
        "mcp_outputs": [],
    }

async def gsuite(state : State):
    try:
        print("Using the gsuite node")
        user_id = os.getenv("USER_ID")
        print(user_id)
        connected_accounts = composio.connected_accounts.list(
            user_ids=[user_id], # this is set to xxx to always bypass the filtering and setup and new auth every time
            auth_config_ids=["ac_gbtRGl26MO9g"],
            toolkit_slugs=["GMAIL","GOOGLECALENDAR","GOOGLESLIDES","GOOGLEDRIVE","GOOGLESHEETS","GOOGLEDOCS"]
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
                auth_config_id="ac_gbtRGl26MO9g",
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

        mcp_tasks = [task.prompt for task in state['mcp_tasks']]
        task_content = " THEN \n ".join(mcp_tasks) if mcp_tasks else ""

        result = await agent.ainvoke(
            input={"messages": [
                {"role": "system",
                 "content": """
                 - You are a helpful GSuite agent.
                 - Your task is to take the user's query, and use the provided tools to do what the user asked.
                 - You do not need to confirm or ask for permission. SEND THE EMAIL. TRY SENDING IT EVEN IF YOU THINK YOU DON'T HAVE PROPER AUTHENTICATION. JUST SEND IT.
                 - Remember not to leave any fields blank.
                 - If you have to modify something, first check if it's empty or not before trying to delete anything 
                - Make sure to extract the email address of the person you want to send the email to and use that to send the email. DO NOT CREATE TEMPLATE EMAILS OR CALENDAR INVITES - JUST WRITE AND SEND A FULL COMPLETE EMAIL WITH WHATEVER INFORMATION YOU ARE GIVEN

                 """},
                {"role": "user",
                 "content": task_content
                 }
            ]},
        )
        messages = result.get('messages', [])
        final_ai_message = None

        for msg in reversed(messages):  # Start from the end
            if getattr(msg, 'type', None) == 'ai':
                final_ai_message = msg.content
                break

        return {
            "mcp_outputs": state['mcp_outputs'] + [
                Output(node="gsuite", result={"response": final_ai_message})
            ]
        }
    except Exception as e:
        print(f"Error in gsuite node: {e}")
        return {
            "mcp_outputs": state['mcp_outputs'] + [
                Output(node="gsuite", result={"response": f"Error: {str(e)}"})  # Wrap in dict
            ]
        }

def screen_controller(state : State):
    print("Using the screen_controller node")
    tasks = state['sc_tasks']
    from executor.main import thingy
    for task in tasks:
        thingy(task)


def synthesizer(state: State):
    final_outputs = []
    for output in state['mcp_outputs']:
        if isinstance(output.result, dict):
            # Extract the response from the dict
            final_outputs.append(output.result.get('response', str(output.result)))
        else:
            final_outputs.append(str(output.result))

    completed_tasks = "\n\n---\n\n".join(final_outputs)
    return {"final_outputs": completed_tasks}

def assign_workers(state: State):
    sends = []
    # Only sending the state object to the appropriate node when that associated list in the state
    # has executable tasks
    if len(state['mcp_tasks']) > 0:
        sends.append(Send("gsuite", state))
    if len(state['sc_tasks']) > 0:
        sends.append(Send("screen controller", state))
    return sends


# Build the workflow graph

graph = StateGraph(State)

graph.add_node("gsuite", gsuite)
graph.add_node("orchestrator", orchestrator)
graph.add_node("screen controller", screen_controller)
graph.add_node("synthesizer", synthesizer)

graph.add_edge(START, "orchestrator")
graph.add_conditional_edges("orchestrator", assign_workers, ["gsuite","screen controller"])

graph.add_edge("screen controller", "synthesizer")
graph.add_edge("gsuite", "synthesizer")
graph.add_edge("synthesizer", END)

# Compile and invoke the graph with hardcoded inputs
compiled = graph.compile()

async def run_graph(user_query : str = "No task provided", data : str = "No data provided"):
    print(f"🎯 [LLMGraph.py] run_graph() CALLED!")
    print(f"🎯 [LLMGraph.py] Received user_query: {user_query[:100]}...")
    print(f"🎯 [LLMGraph.py] Received data length: {len(data)} characters")
    final_output = await compiled.ainvoke({"task": user_query, "data" : data})
    print(final_output["final_outputs"])
    print(f"✅ [LLMGraph.py] run_graph() execution completed")
    return final_output

# user_query = """
#     Can you send an email to rneela@wisc.edu to confirm the interview with Anand on 21st November and create a calendar event. Use GSuite for all of these
#     """
# data = "Ritesh is an interview candidate that is currently in the process of interviewing for a position at this company "
# user_query = "Complete the interview scheduling process for candidate Siddharth Ghantasala (siddharthghantasala@gmail.com) for the Summer 2026 Software Engineering Intern position. First, send the currently drafted email with subject 'INTERNSHIP INTERVIEW' that confirms the interview scheduled for 7:30 this Sunday. Then, create a calendar event for this Sunday at 7:30pm with duration of 1 hour (7:30pm-8:30pm). The calendar event should be titled 'Interview - Siddharth Ghantasala - SWE Intern Summer 2026' and include a Google Meet link for the video interview. Add siddharthghantasala@gmail.com as an attendee to the calendar event so he receives the meeting invite with the video conferencing details."
# data = ""
# asyncio.run(run_graph(user_query))