from agno.agent import Agent
from agno.models.openai import OpenAIChat
from agno.playground import Playground, serve_playground_app
from agno.storage.sqlite import SqliteStorage
from agno.tools.duckduckgo import DuckDuckGoTools
from agno.tools.yfinance import YFinanceTools
from os import getenv
from fastapi import APIRouter

from agents.sage import get_sage
from agents.scholar import get_scholar
from workflows.security_audit_team import SecurityAuditTeam

agent_storage: str = "tmp/agents.db"

web_agent = Agent(
    name="Web Agent",
    model=OpenAIChat(id="gpt-4o"),
    tools=[DuckDuckGoTools()],
    instructions=["Always include sources"],
    # Store the agent sessions in a sqlite database
    storage=SqliteStorage(table_name="web_agent", db_file=agent_storage),
    # Adds the current date and time to the instructions
    add_datetime_to_instructions=True,
    # Adds the history of the conversation to the messages
    add_history_to_messages=True,
    # Number of history responses to add to the messages
    num_history_responses=5,
    # Adds markdown formatting to the messages
    markdown=True,
)

finance_agent = Agent(
    name="Finance Agent",
    model=OpenAIChat(id="gpt-4o"),
    tools=[YFinanceTools(stock_price=True, analyst_recommendations=True, company_info=True, company_news=True)],
    instructions=["Always use tables to display data"],
    storage=SqliteStorage(table_name="finance_agent", db_file=agent_storage),
    add_datetime_to_instructions=True,
    add_history_to_messages=True,
    num_history_responses=5,
    markdown=True,
)

# Get Sage and Scholar agent instances
sage_agent = get_sage()
scholar_agent = get_scholar()
audit_team = SecurityAuditTeam(model_id="openrouter/google/gemini-2.5-flash-preview-05-20")

playground_router = APIRouter(prefix="/playground", tags=["Playground"])

# Instantiate Playground
playground_instance = Playground(agents=[web_agent, finance_agent, sage_agent, scholar_agent], teams=[audit_team])

app = playground_instance.get_app()

if __name__ == "__main__":
    serve_playground_app("playground:app", reload=True)