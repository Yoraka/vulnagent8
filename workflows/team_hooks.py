from typing import Any, Dict, Union, Callable
from agno.utils.log import log_debug
import inspect # For inspecting callables

def log_before_team_tool_call(tool_name: str, tool_args: Union[Dict[str, Any], Callable], agent: Any, **kwargs: Any) -> None:
    """
    Hook called before a Team Leader's tool is executed.
    Logs the details of the intended tool call.
    """
    team_identifier = "Team"
    actual_args_to_log = tool_args

    if hasattr(agent, 'team_id') and agent.team_id:
        team_identifier = f"Team [ID: {agent.team_id}]"
    elif hasattr(agent, 'name') and agent.name:
        team_identifier = f"Team [{agent.name}]"

    log_debug(f"{team_identifier} - Leader preparing to call tool: '{tool_name}'", center=True, symbol="H")

    # Attempt to find more meaningful arguments if tool_args is a callable
    # This is an experimental attempt to see if kwargs or other context holds the real args
    if callable(tool_args):
        log_debug(f"{team_identifier} - Raw tool_args is a callable: {tool_args}", center=True, symbol="H")
        # Check if 'actual_tool_args' or similar was passed via kwargs from a deeper part of Agno's exec chain
        if 'actual_tool_args' in kwargs:
            actual_args_to_log = kwargs['actual_tool_args']
        elif 'arguments' in kwargs: # Some Agno internals might pass it as 'arguments'
             actual_args_to_log = kwargs['arguments']
        else:
            # Fallback to inspecting the callable if possible, though this is less reliable
            try:
                sig = inspect.signature(tool_args)
                actual_args_to_log = f"Callable with signature: {sig}. Original tool_args: {tool_args}"
            except (ValueError, TypeError):
                actual_args_to_log = f"Callable (signature unavailable). Original tool_args: {tool_args}"
    
    log_debug(f"{team_identifier} - Tool arguments: {actual_args_to_log}", center=True, symbol="H")

    if tool_name == "transfer_task_to_member" or tool_name == "forward_task_to_member":
        # Ensure actual_args_to_log is a dict before trying .get()
        member_id = actual_args_to_log.get("member_id") if isinstance(actual_args_to_log, dict) else "N/A (args not dict)"
        task_desc_temp = actual_args_to_log.get("task_description") if isinstance(actual_args_to_log, dict) else None
        message_temp = actual_args_to_log.get("message") if isinstance(actual_args_to_log, dict) else None
        task_description = task_desc_temp or message_temp

        if isinstance(task_description, dict) and 'content' in task_description:
             task_description = task_description['content']
        elif hasattr(task_description, 'get_content_string'):
             task_description = task_description.get_content_string()

        expected_output_temp = actual_args_to_log.get("expected_output", "N/A") if isinstance(actual_args_to_log, dict) else "N/A (args not dict)"
        expected_output = expected_output_temp
        
        log_debug(f"{team_identifier} - Leader intends to delegate to member: '{member_id}'", center=True, symbol="H")
        log_debug(f"{team_identifier} - Task for member: '{str(task_description)[:500]}...'", center=True, symbol="H")
        log_debug(f"{team_identifier} - Expected output from member: '{expected_output}'", center=True, symbol="H")
    elif tool_name == "run_member_agents":
        task_description = actual_args_to_log.get("task_description") if isinstance(actual_args_to_log, dict) else "N/A (args not dict)"
        expected_output = actual_args_to_log.get("expected_output", "N/A") if isinstance(actual_args_to_log, dict) else "N/A (args not dict)"
        log_debug(f"{team_identifier} - Leader intends to run all member agents.", center=True, symbol="H")
        log_debug(f"{team_identifier} - Task for all members: '{str(task_description)[:500]}...'", center=True, symbol="H")
        log_debug(f"{team_identifier} - Expected output from members: '{expected_output}'", center=True, symbol="H")


def log_after_team_tool_call(tool_name: str, tool_args: Union[Dict[str, Any], Callable], result: Any, agent: Any, **kwargs: Any) -> None:
    """
    Hook called after a Team Leader's tool has been executed.
    Logs the result of the tool call.
    """
    team_identifier = "Team"
    if hasattr(agent, 'team_id') and agent.team_id:
        team_identifier = f"Team [ID: {agent.team_id}]"
    elif hasattr(agent, 'name') and agent.name:
        team_identifier = f"Team [{agent.name}]"
    
    logged_result = result
    if hasattr(result, '__aiter__'): # Check for async iterator
        logged_result = "[AsyncIterator/Stream]"
    elif hasattr(result, '__iter__') and not isinstance(result, (str, dict, list, bytes)): # Check for sync iterator (excluding common iterables)
        logged_result = "[Iterator/Stream]"
        # Optionally, you could try to peek at the first item if safe and desired,
        # but consuming from the stream here can have side effects.
        # For now, just identifying it as a stream is safer.

    log_debug(f"{team_identifier} - Leader finished tool call: '{tool_name}'", center=True, symbol="H")
    log_debug(f"{team_identifier} - Tool result: {str(logged_result)[:1000]}... (Full result type: {type(result).__name__})", center=True, symbol="H") 