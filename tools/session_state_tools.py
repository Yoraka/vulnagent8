from typing import Any, Dict, Optional
from agno.agent import Agent # Assuming Agent is the type passed when tool is bound

class ReadSessionStateTool:
    """Tool to read a value from the team's session_state."""
    name: str = "ReadSessionStateTool"
    description: str = "Reads a value from the team's shared session_state. Args: key (str)."

    def __init__(self, agent: Optional[Agent] = None):
        self.agent = agent

    def __call__(self, key: str) -> Any:
        if self.agent is None or not hasattr(self.agent, 'team_session_state'):
            return "Error: Tool not properly bound to an agent with team_session_state or agent is None."
        
        try:
            value = self.agent.team_session_state.get(key)
            if value is None:
                # To differentiate between a key existing with value None vs key not existing
                if key not in self.agent.team_session_state:
                    return f"Error: Key '{key}' not found in session_state."
            return value
        except Exception as e:
            return f"Error reading session_state key '{key}': {str(e)}"

class UpdateSessionStateTool:
    """Tool to update a value in the team's session_state."""
    name: str = "UpdateSessionStateTool"
    description: str = (
        "Updates a value in the team's shared session_state. "
        "Args: key (str), value (any), action (str, optional: 'set', 'append', 'increment'). Default action is 'set'."
    )

    def __init__(self, agent: Optional[Agent] = None):
        self.agent = agent

    def __call__(self, key: str, value: Any, action: str = "set") -> str:
        if self.agent is None or not hasattr(self.agent, 'team_session_state'):
            return "Error: Tool not properly bound to an agent with team_session_state or agent is None."

        state = self.agent.team_session_state

        try:
            if action == "set":
                state[key] = value
                return f"Session state key '{key}' set successfully."
            elif action == "append":
                if key not in state:
                    state[key] = [] # Initialize as list if key doesn't exist
                if not isinstance(state[key], list):
                    return f"Error: Cannot append. Key '{key}' in session_state is not a list (current type: {type(state[key])})."
                state[key].append(value)
                return f"Value appended to session_state key '{key}' successfully."
            elif action == "increment":
                if key not in state:
                    # Initialize to 0 if key doesn't exist, then increment
                    state[key] = 0
                
                current_val = state.get(key, 0) # Default to 0 if somehow still not there, or if value is None
                if not isinstance(current_val, (int, float)):
                    return f"Error: Cannot increment. Key '{key}' in session_state is not a number (current value: {current_val}, type: {type(current_val)})."
                if not isinstance(value, (int, float)):
                    return f"Error: Cannot increment. Provided value '{value}' is not a number (type: {type(value)})."
                
                state[key] = current_val + value
                return f"Session state key '{key}' incremented by {value} successfully. New value: {state[key]}."
            else:
                return f"Error: Unknown action '{action}'. Valid actions are 'set', 'append', 'increment'."
        except Exception as e:
            return f"Error updating session_state key '{key}' with action '{action}': {str(e)}"

# Example Usage (conceptual, not runnable directly here)
if __name__ == "__main__":
    # This is how Agno might bind the agent when the tool is part of an Agent's tool list
    # and the agent (here, the Team Leader) calls it.
    
    class MockAgent:
        def __init__(self):
            self.team_session_state: Dict[str, Any] = {
                "existing_list": [1, 2],
                "existing_number": 10,
                "name": "Test Session"
            }

    mock_leader_agent = MockAgent()

    # Tool Instantiation (Agno does this internally when Agent is initialized with tools)
    # In our workflow, we do: update_state_tool = UpdateSessionStateTool()
    # Agno then likely does something like: update_state_tool.agent = leader_agent_instance

    read_tool = ReadSessionStateTool(agent=mock_leader_agent)
    update_tool = UpdateSessionStateTool(agent=mock_leader_agent)

    print("--- Read Operations ---")
    print(f"Reading 'name': {read_tool(key='name')}")
    print(f"Reading 'non_existent_key': {read_tool(key='non_existent_key')}")
    print(f"Reading 'existing_list': {read_tool(key='existing_list')}")
    
    print("\n--- Update Operations ---")
    # Set
    print(update_tool(key="new_key", value="new_value", action="set"))
    print(f"State for 'new_key': {read_tool('new_key')}")
    print(update_tool(key="name", value="Updated Test Session", action="set"))
    print(f"State for 'name': {read_tool('name')}")

    # Append
    print(update_tool(key="existing_list", value=3, action="append"))
    print(f"State for 'existing_list': {read_tool('existing_list')}")
    print(update_tool(key="another_list", value="a", action="append")) # Creates new list
    print(f"State for 'another_list': {read_tool('another_list')}")
    print(update_tool(key="name", value="x", action="append")) # Error: name is not a list

    # Increment
    print(update_tool(key="existing_number", value=5, action="increment"))
    print(f"State for 'existing_number': {read_tool('existing_number')}")
    print(update_tool(key="new_counter", value=1, action="increment")) # Creates new counter
    print(f"State for 'new_counter': {read_tool('new_counter')}")
    print(update_tool(key="existing_list", value=1, action="increment")) # Error: existing_list is not a number
    print(update_tool(key="existing_number", value="test", action="increment")) # Error: value "test" is not a number

    print("\nFinal session state:", mock_leader_agent.team_session_state) 