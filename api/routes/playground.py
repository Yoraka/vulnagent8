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
from agents.icla_test_agent import get_icla_test_agent
from agents.token_test_agent import get_token_test_agent
from workflows.security_audit_team import SecurityAuditTeam
from workflows.minimal_test_team import MinimalTestTeam
from workflows.security_audit_orchestrator import SecurityAuditWorkflow

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
icla_agent = get_icla_test_agent(user_id="playground_default_user", model_id="google/gemini-2.5-flash")
token_test_agent = get_token_test_agent(user_id="playground_default_user", model_id="deepseek-reasoner")

# Instantiate Teams
# Ensure DEFAULT_MODEL_ID is available or pass a specific one
# from core.model_factory import DEFAULT_MODEL_ID # Assuming you might want this #openrouter/anthropic/claude-sonnet-4
audit_team = SecurityAuditTeam(model_id="deepseek/deepseek-reasoner",
                                team_leader_model_id="openrouter/google/gemini-2.5-pro-preview",
                                env_reporter_model_id="deepseek/deepseek-reasoner",
                                attack_planning_model_id="deepseek/deepseek-reasoner", 
                                attack_surface_refiner_model_id="openrouter/google/gemini-2.5-pro-preview",
                                deep_dive_auditor_model_id="openrouter/google/gemini-2.5-pro-preview", 
                                user_id="playground_default_user")
minimal_test_team_instance = MinimalTestTeam(model_id="openrouter/openai/o4-mini", user_id="playground_default_user")
security_audit_workflow_instance = SecurityAuditWorkflow(model_id="openrouter/openai/o4-mini", user_id="playground_default_user")
playground_router = APIRouter(prefix="/playground", tags=["Playground"])

# Instantiate Playground
playground_instance = Playground(
    agents=[web_agent, finance_agent, sage_agent, scholar_agent, icla_agent, token_test_agent], 
    teams=[audit_team, minimal_test_team_instance],
    workflows=[security_audit_workflow_instance]
)

app = playground_instance.get_app()

if __name__ == "__main__":
    serve_playground_app("playground:app", reload=True)