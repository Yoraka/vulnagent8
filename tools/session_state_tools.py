from typing import Any, Dict, Optional
from agno.agent import Agent # Required for type hinting in __init__
# No longer using Toolkit or standalone @tool here for these specific tools

class ReadSessionStateTool:
    """Tool to read a value from the team's session_state."""
    name: str = "ReadSessionStateTool"  # Exposed name to the LLM
    description: str = "Reads a value from the team's shared session_state. Args: key (str)."

    def __call__(self, agent: Any, key: str) -> Any:
        """Executes the tool to read from session_state."""
        if agent is None or not hasattr(agent, 'session_state'):
            raise RuntimeError("ReadSessionStateTool: Agent not properly passed to tool or agent has no session_state.")
        
        state: Dict[str, Any] = agent.session_state
        try:
            return state[key]
        except KeyError:
            raise KeyError(f"Key '{key}' not found in session_state.")
        except Exception as e:
            raise RuntimeError(f"Error reading session_state key '{key}': {str(e)}")

class UpdateSessionStateTool:
    """Tool to update a value in the team's session_state."""
    name: str = "UpdateSessionStateTool"  # Exposed name to the LLM
    description: str = (
        "Updates a value in the team's shared session_state. "
        "Args: key (str), value (any), action (str, optional: 'set', 'append', 'increment'). Default action is 'set'."
    )

    def __call__(self, agent: Any, key: str, value: Any, action: str = "set") -> str:
        """Executes the tool to update session_state."""
        if agent is None or not hasattr(agent, 'session_state'):
            raise RuntimeError("UpdateSessionStateTool: Agent not properly passed to tool or agent has no session_state.")

        state: Dict[str, Any] = agent.session_state
        
        try:
            if action == "set":
                state[key] = value
                return f"Session state key '{key}' set successfully."
            
            elif action == "append":
                if key not in state or state[key] is None:
                    state[key] = [] 
                if not isinstance(state[key], list):
                    current_type = type(state[key]).__name__
                    raise TypeError(f"Cannot append. Key '{key}' in session_state is not a list (current type: {current_type}). Please ensure the key holds a list before appending.")
                state[key].append(value)
                return f"Value appended to session_state key '{key}' successfully."
            
            elif action == "increment":
                current_val = state.get(key, 0)
                if not isinstance(current_val, (int, float)):
                    raise TypeError(f"Cannot increment. Current value for key '{key}' in session_state is not a number (current value: {current_val}, type: {type(current_val).__name__}).")
                if not isinstance(value, (int, float)):
                    raise TypeError(f"Cannot increment. Provided value '{value}' for key '{key}' is not a number (type: {type(value).__name__}).")
                state[key] = current_val + value
                return f"Session state key '{key}' incremented by {value} successfully. New value: {state[key]}."
            
            else:
                raise ValueError(f"Unknown action '{action}'. Valid actions are 'set', 'append', 'increment'.")
        
        except (TypeError, ValueError) as e:
            raise e 
        except Exception as e:
            raise RuntimeError(f"Unexpected error updating session_state key '{key}' with action '{action}': {str(e)}")

# The simple_standalone_test function is removed as per plan.
# The SessionStateManagementTools class (Toolkit) remains commented out from previous steps.

# Temporarily comment out the entire SessionStateManagementTools class
# class SessionStateManagementTools(Toolkit):
#     """
#     A toolkit for reading and updating the team's shared session_state.
#     The 'agent' attribute (the TeamLeader instance) will be automatically set 
#     by Agno when this toolkit is added to the agent's tools.
#     """
# 
#     @tool(name="TestToolSimple", description="A very simple test tool.")
#     def simple_test(self, input_text: str) -> str: # Changed input to input_text to avoid keyword clash
#         print(f"TestToolSimple called with: {input_text}")
#         return f"TestToolSimple received: {input_text}"
# 
#     # Temporarily comment out the original read_value and update_value
#     # @tool(name="ReadSessionStateTool", description="Reads a value from the team's shared session_state. Args: key (str).")
#     # def read_value(self, key: str) -> Any:
#     #     """
#     #     Reads a value from the team's shared session_state.
#     #     This method will be exposed as a tool named 'ReadSessionStateTool'.
#     #     """
#     #     if not hasattr(self, 'agent') or self.agent is None or not hasattr(self.agent, 'team_session_state'):
#     #         # This check ensures the toolkit has been properly bound to an agent by the Agno framework.
#     #         raise RuntimeError("SessionStateManagementTools.read_value: Toolkit not properly bound to an agent with team_session_state or agent is None.")
#     #     
#     #     state: Dict[str, Any] = self.agent.team_session_state
#     #     try:
#     #         return state[key]
#     #     except KeyError:
#     #         # It's good practice to let specific exceptions like KeyError propagate,
#     #         # as the LLM or calling code might handle them based on the type of error.
#     #         raise KeyError(f"Key '{key}' not found in session_state.")
#     #     except Exception as e:
#     #         # Catch any other unexpected errors during access.
#     #         raise RuntimeError(f"Error reading session_state key '{key}': {str(e)}")
# 
#     # @tool(name="UpdateSessionStateTool", description="Updates a value in the team's shared session_state. Args: key (str), value (any), action (str, optional: 'set', 'append', 'increment'). Default action is 'set'.")
#     # def update_value(self, key: str, value: Any, action: str = "set") -> str:
#     #     """
#     #     Updates a value in the team's shared session_state.
#     #     This method will be exposed as a tool named 'UpdateSessionStateTool'.
#     #     Valid actions: 'set', 'append', 'increment'.
#     #     """
#     #     if not hasattr(self, 'agent') or self.agent is None or not hasattr(self.agent, 'team_session_state'):
#     #         raise RuntimeError("SessionStateManagementTools.update_value: Toolkit not properly bound to an agent with team_session_state or agent is None.")
# 
#     #     state: Dict[str, Any] = self.agent.team_session_state
#     #     
#     #     try:
#     #         if action == "set":
#     #             state[key] = value
#     #             return f"Session state key '{key}' set successfully."
#     #         
#     #         elif action == "append":
#     #             # Ensure the target is a list. Initialize if not present or if None.
#     #             if key not in state or state[key] is None:
#     #                 state[key] = [] 
#     #             
#     #             if not isinstance(state[key], list):
#     #                 current_type = type(state[key]).__name__
#     #                 raise TypeError(f"Cannot append. Key '{key}' in session_state is not a list (current type: {current_type}). Please ensure the key holds a list before appending.")
#     #             
#     #             state[key].append(value)
#     #             return f"Value appended to session_state key '{key}' successfully."
#     #         
#     #         elif action == "increment":
#     #             current_val = state.get(key, 0) # Default to 0 if key doesn't exist or its value is None
#     #                                             # This allows incrementing a new key or a key explicitly set to None.
# 
#     #             if not isinstance(current_val, (int, float)):
#     #                 raise TypeError(f"Cannot increment. Current value for key '{key}' in session_state is not a number (current value: {current_val}, type: {type(current_val).__name__}).")
#     #             if not isinstance(value, (int, float)):
#     #                 raise TypeError(f"Cannot increment. Provided value '{value}' for key '{key}' is not a number (type: {type(value).__name__}).")
#     #             
#     #             state[key] = current_val + value
#     #             return f"Session state key '{key}' incremented by {value} successfully. New value: {state[key]}."
#     #         
#     #         else:
#     #             # This ValueError will be caught by the specific except block below.
#     #             raise ValueError(f"Unknown action '{action}'. Valid actions are 'set', 'append', 'increment'.")
#     #     
#     #     except (TypeError, ValueError) as e:
#     #         # Re-raise specific errors that indicate misuse of the tool's parameters or state conditions.
#     #         raise e 
#     #     except Exception as e:
#     #         # Catch any other unexpected error during the update process.
#     #         raise RuntimeError(f"Unexpected error updating session_state key '{key}' with action '{action}': {str(e)}")
# 
# # Example Usage (conceptual, for understanding how Agno might bind and use it)
# # This part is not meant to be run directly from here but illustrates the concept.
# # (The example usage for the original tools is now commented out as well)
# # if __name__ == "__main__":
# #     
# #     class MockTeamLeaderAgent(Agent): # Inherit from Agent for type compatibility
# #         def __init__(self):
# #             super().__init__(agent_id="mock_leader", name="MockLeader") # Basic Agent init
# #             self.team_session_state: Dict[str, Any] = {
# #                 "existing_list": [1, 2],
# #                 "existing_number": 10,
# #                 "name": "Test Session"
# #             }
# # 
# #     mock_leader = MockTeamLeaderAgent()
# #     
# #     # In a real Agno setup, the toolkit would be added to the agent's tools list,
# #     # and Agno would handle binding `self.agent = mock_leader` to the toolkit instance.
# #     session_toolkit = SessionStateManagementTools()
# #     # session_toolkit.agent = mock_leader # Manual binding for this standalone example
# # 
# #     # Using the new simple_test method
# #     print(session_toolkit.simple_test(input_text="Hello from test"))
#     
#     # print("--- Read Operations (via Toolkit) ---")
#     # print(f"Reading 'name': {session_toolkit.read_value(key='name')}")
#     # try:
#     #     print(f"Reading 'non_existent_key': {session_toolkit.read_value(key='non_existent_key')}")
#     # except KeyError as e:
#     #     print(e)
#     # 
#     # print("\\n--- Update Operations (via Toolkit) ---")
#     # # Set
#     # print(session_toolkit.update_value(key="new_key", value="new_value", action="set"))
#     # print(f"State for 'new_key': {session_toolkit.read_value('new_key')}")
#     # 
#     # # Append
#     # print(session_toolkit.update_value(key="existing_list", value=3, action="append"))
#     # print(f"State for 'existing_list': {session_toolkit.read_value('existing_list')}")
#     # 
#     # # Increment
#     # print(session_toolkit.update_value(key="existing_number", value=5, action="increment"))
#     # print(f"State for 'existing_number': {session_toolkit.read_value('existing_number')}")

#     # print("\\nFinal session state:", mock_leader.team_session_state) 