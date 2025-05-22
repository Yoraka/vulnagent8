from os import getenv

from agno.playground import Playground

from agents.sage import get_sage
from agents.scholar import get_scholar
# from agents.local_tool_tester import get_local_tool_tester_agent
from workspace.dev_resources import dev_fastapi

######################################################
## Router for the Playground Interface
######################################################

sage_agent = get_sage(debug_mode=True)
scholar_agent = get_scholar(debug_mode=True)
# local_tool_tester_agent = get_local_tool_tester_agent(debug_mode=True)

# Create a playground instance
playground = Playground(agents=[sage_agent, scholar_agent])

# Register the endpoint where playground routes are served with agno.com
if getenv("RUNTIME_ENV") == "dev":
    playground.create_endpoint(f"http://localhost:{dev_fastapi.host_port}")

playground_router = playground.get_async_router()
