from enum import Enum
from typing import List, Optional

from agno.agent import Agent
from agents.sage import get_sage
from agents.scholar import get_scholar
# Temporarily comment out the problematic import
# from agents.local_tool_tester import get_local_security_auditor_agent


class AgentType(Enum):
    SAGE = "sage"
    SCHOLAR = "scholar"
    # Temporarily comment out this agent type
    # LOCAL_TOOL_TESTER = "local_tool_tester"


def get_available_agents() -> List[str]:
    """Returns a list of all available agent IDs."""
    # Adjust to work without the commented-out type
    available_types = [AgentType.SAGE, AgentType.SCHOLAR]
    return [agent.value for agent in available_types]


def get_agent(
    model_id: str = "gpt-4o", # Default model, ensure it's appropriate if used
    agent_id: Optional[AgentType] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    debug_mode: bool = True,
) -> Agent: # Added return type hint based on other get_agent functions
    if agent_id == AgentType.SAGE:
        return get_sage(model_id=model_id, user_id=user_id, session_id=session_id, debug_mode=debug_mode)
    # Temporarily comment out this branch
    # elif agent_id == AgentType.LOCAL_TOOL_TESTER:
    #     return get_local_security_auditor_agent(
    #         user_id=user_id, session_id=session_id, debug_mode=True
    #     )
    # Ensure there's a default or scholar is always the fallback
    elif agent_id == AgentType.SCHOLAR:
        return get_scholar(model_id=model_id, user_id=user_id, session_id=session_id, debug_mode=debug_mode)
    else:  # Default to scholar or handle unknown types if SCHOLAR is not explicitly passed
        # Or raise an error for unknown agent_id if that's preferred behavior
        # For now, assuming scholar is a safe default if no match or if LOCAL_TOOL_TESTER was intended but now commented out
        # This might need adjustment based on how agent_id is typically passed or if it can be None when LOCAL_TOOL_TESTER was the only other option.
        print(f"Warning: agent_id '{agent_id}' not fully handled or LOCAL_TOOL_TESTER was requested. Defaulting to Scholar.")
        return get_scholar(model_id=model_id, user_id=user_id, session_id=session_id, debug_mode=debug_mode)
