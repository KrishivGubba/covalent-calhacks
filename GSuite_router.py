from dotenv import load_dotenv
import os
from composio import Composio
from composio_gemini import GeminiProvider
load_dotenv()

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
    connection_request.wait_for_connection(timeout=10000)
    print(connection_request.redirect_url)
    return connection_request.id

# Initialize Composio and create Tool Router session
composio = Composio(
    api_key=os.getenv("COMPOSIO_API_KEY"),  # Uses env var by default
    provider=GeminiProvider()
)

if os.getenv("USER_ID") == "":
    connection_id = authenticate_toolkit(user_id="user", auth_config_id=os.getenv("GOOGLE_AUTH_CONFIG_ID"))
    os.environ["USER_ID"] = "user"

user_id = os.getenv("USER_ID")

session = composio.experimental.tool_router.create_session(
    user_id=user_id,
    # toolkits=["GMAIL"]
)

print(session['url'])