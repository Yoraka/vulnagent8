from enum import Enum
from typing import List, Optional

from agents.sage import get_sage
from agents.scholar import get_scholar
from agents.local_tool_tester import get_local_tool_tester_agent


class AgentType(Enum):
    SAGE = "sage"
    SCHOLAR = "scholar"
    LOCAL_TOOL_TESTER = "local_tool_tester"


def get_available_agents() -> List[str]:
    """Returns a list of all available agent IDs."""
    return [agent.value for agent in AgentType]


def get_agent(
    model_id: str = "gpt-4o",
    agent_id: Optional[AgentType] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    debug_mode: bool = True,
):
    if agent_id == AgentType.SAGE:
        return get_sage(model_id=model_id, user_id=user_id, session_id=session_id, debug_mode=debug_mode)
    elif agent_id == AgentType.LOCAL_TOOL_TESTER:
        return get_local_tool_tester_agent(model_id=model_id, user_id=user_id, session_id=session_id, debug_mode=debug_mode)
    else:  # Default to scholar or handle unknown types
        return get_scholar(model_id=model_id, user_id=user_id, session_id=session_id, debug_mode=debug_mode)
