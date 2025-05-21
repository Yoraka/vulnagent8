import asyncio
import nest_asyncio
import streamlit as st
from agno.agent import Agent
from agno.tools.streamlit.components import check_password
from agno.utils.log import logger

from agents.local_tool_tester import get_local_security_auditor_agent, HARDCODED_WORKSPACE_PATH
from ui.css import CUSTOM_CSS
from ui.utils import (
    about_agno,
    add_message,
    display_tool_calls,
    initialize_agent_session_state,
    selected_model,
    session_selector,
    utilities_widget,
    example_inputs
)

nest_asyncio.apply()

st.set_page_config(
    page_title="Java Security Auditor",
    page_icon="🛡️",
    layout="wide",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
agent_name = "java_security_auditor_v1"

if "editing_message_idx" not in st.session_state:
    st.session_state.editing_message_idx = None
if "edited_message_content" not in st.session_state:
    st.session_state.edited_message_content = ""
# Ensure agent-specific state exists
if agent_name not in st.session_state:
    st.session_state[agent_name] = {
        "agent": None,
        "messages": [],
        "session_id": None # Explicitly track current session_id for clarity
    }

async def header():
    st.markdown("<h1 class='heading'>Java Security Auditor</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p class='subheading'>A white-box security auditing expert to identify attack surfaces in Java backend projects.</p>",
        unsafe_allow_html=True,
    )

async def body() -> None:
    user_id = st.sidebar.text_input(":technologist: Username", value="JavaAuditor_User")
    model_id = await selected_model()

    # Sidebar buttons for New Chat and Delete Chat
    if st.sidebar.button("✨ New Chat", key="new_chat_button"):
        logger.info(f"User {user_id} started a new chat for {agent_name}.")
        st.session_state[agent_name]["agent"] = get_local_security_auditor_agent(user_id=user_id, model_id=model_id, session_id=None)
        st.session_state[agent_name]["messages"] = []
        st.session_state[agent_name]["session_id"] = st.session_state[agent_name]["agent"].session_id # Will be a new ID from agent
        st.session_state.editing_message_idx = None
        st.rerun()

    if st.session_state[agent_name]["agent"] and st.session_state[agent_name]["session_id"]:
        if st.sidebar.button("🗑️ Delete Current Chat", key="delete_chat_button"):
            session_to_delete = st.session_state[agent_name]["session_id"]
            current_agent = st.session_state[agent_name]["agent"]
            if session_to_delete and current_agent and current_agent.storage:
                try:
                    logger.info(f"User {user_id} deleting session {session_to_delete} for {agent_name}.")
                    current_agent.storage.delete_session(session_to_delete)
                    current_agent.storage.delete_runs(session_to_delete)
                    st.toast(f"Session {session_to_delete[:8]}... deleted successfully!", icon="🗑️")
                    # Reset to a new chat state
                    st.session_state[agent_name]["agent"] = get_local_security_auditor_agent(user_id=user_id, model_id=model_id, session_id=None)
                    st.session_state[agent_name]["messages"] = []
                    st.session_state[agent_name]["session_id"] = st.session_state[agent_name]["agent"].session_id
                    st.session_state.editing_message_idx = None
                    st.rerun()
                except Exception as e:
                    logger.error(f"Error deleting session {session_to_delete}: {e}", exc_info=True)
                    st.sidebar.error(f"Failed to delete session: {e}")
            else:
                st.sidebar.warning("No active session to delete or storage not configured.")

    auditor_agent: Agent = st.session_state[agent_name]["agent"]
    current_ui_session_id = st.session_state[agent_name]["session_id"]

    # Agent Initialization / Re-initialization Logic
    # This block runs on every rerun, ensuring agent is consistent with selected user/model/session.
    # It also handles initial agent creation.
    re_initialize_agent = False
    if auditor_agent is None: # First time loading, or after a full reset
        re_initialize_agent = True
        logger.info(f"No agent in session state for {agent_name}. Initializing.")
    elif auditor_agent.user_id != user_id: # User changed
        re_initialize_agent = True
        logger.info(f"User changed from {auditor_agent.user_id} to {user_id}. Re-initializing agent.")
    elif st.session_state.get("selected_model") != model_id: # Model changed
        re_initialize_agent = True
        logger.info(f"Model changed. Re-initializing agent.")
    # If session_selector changed the agent's session_id, this agent object would be different.
    # The session_selector should handle putting the correct agent (for the selected historical session) into st.session_state[agent_name]["agent"]
    # So, if the current_ui_session_id (managed by this page) mismatches agent's internal session_id, it implies external change (e.g. session_selector)
    elif current_ui_session_id != auditor_agent.session_id and current_ui_session_id is not None:
        # This case should ideally be handled by session_selector's callback updating the agent directly.
        # However, if session_selector only updates a st.session_state key for the ID, 
        # then we might need to re-init. For agno's selector, it should replace the agent object.
        logger.info(f"Session ID mismatch. UI had {current_ui_session_id}, agent has {auditor_agent.session_id}. Assuming agent was updated by selector. Clearing UI messages.")
        # If session_selector has updated the agent object, its session_id is king.
        # The current_ui_session_id should then align with auditor_agent.session_id from session_state.
        st.session_state[agent_name]["messages"] = []
        st.session_state[agent_name]["session_id"] = auditor_agent.session_id # Align UI session_id with agent's
        current_ui_session_id = auditor_agent.session_id # Update for current run
        st.session_state.editing_message_idx = None # Reset editing state on session change

    if re_initialize_agent:
        # When re-initializing, use current_ui_session_id if it's set (e.g. by session_selector recovering state),
        # otherwise, it will be None and agent will load latest or create new.
        auditor_agent = get_local_security_auditor_agent(user_id=user_id, model_id=model_id, session_id=current_ui_session_id)
        st.session_state[agent_name]["agent"] = auditor_agent
        st.session_state["selected_model"] = model_id # Persist selected model
        # If re-initializing, messages should be cleared to be reloaded from the new agent's context/session
        st.session_state[agent_name]["messages"] = []
        st.session_state.editing_message_idx = None
    
    # Ensure we are using the agent from session state after any potential re-initialization
    auditor_agent = st.session_state[agent_name]["agent"]
    if not auditor_agent: # Should not happen if logic above is correct
        st.error("Auditor Agent could not be initialized. Please refresh or select a user.")
        return

    # Load session data (like ID and runs) from DB using the agent's current session_id configuration
    # This load_session is crucial for populating agent.memory.runs for an existing session_id
    try:
        # agent.load_session() ensures agent.session_id is valid (loads last for user, uses existing, or makes new if None)
        # and loads runs into agent.memory for that session_id.
        loaded_session_id = auditor_agent.load_session() 
        st.session_state[agent_name]["session_id"] = loaded_session_id
        if auditor_agent.session_id != loaded_session_id: # Keep agent's internal ID and UI's tracking in sync
            auditor_agent.session_id = loaded_session_id

        # Load history into UI state ONLY if UI messages are empty (e.g., after session switch / initial load)
        # AND not currently in editing mode (to prevent reload during text_area interaction)
        if not st.session_state[agent_name]["messages"] and st.session_state.editing_message_idx is None:
            if auditor_agent.memory and auditor_agent.memory.runs:
                logger.debug(f"Loading run history for session {loaded_session_id} into UI from agent.memory")
                # Messages already cleared if agent was re-initialized. If not, this ensures clean load.
                st.session_state[agent_name]["messages"] = [] 
                for agent_run in auditor_agent.memory.runs:
                    if agent_run.message is not None:
                        await add_message(agent_name, agent_run.message.role, str(agent_run.message.content))
                    if agent_run.response is not None:
                        await add_message(
                            agent_name, "assistant", str(agent_run.response.content), agent_run.response.tools
                        )
    except Exception as e:
        st.error(f"Error loading agent session: {e}. Is the database connected and schema correct?")
        logger.error(f"Error in agent.load_session() or subsequent history loading: {e}", exc_info=True)
        return # Stop further execution if session loading fails

    # Chat Input
    prompt_placeholder = f"Ask the Java Security Auditor... (e.g., 'analyze {HARDCODED_WORKSPACE_PATH}/pom.xml')"
    user_prompt = st.chat_input(prompt_placeholder, key=f"{agent_name}_main_chat_input")

    if user_prompt and st.session_state.editing_message_idx is None:
        # Only add message if there's an active agent and session
        if auditor_agent and auditor_agent.session_id:
            await add_message(agent_name, "user", user_prompt)
        else:
            st.warning("Agent not ready. Try refreshing or starting a new chat.")

    # Welcome message if no messages and not editing
    if not st.session_state[agent_name]["messages"] and st.session_state.editing_message_idx is None:
        if st.session_state[agent_name].get("session_id"):
             st.info(f"Java Security Auditor ready. Workspace: {HARDCODED_WORKSPACE_PATH}. Session: {st.session_state[agent_name]['session_id'][:8]}...")
        else:
             st.info(f"Java Security Auditor ready. Start a new chat or select a historical session. Workspace: {HARDCODED_WORKSPACE_PATH}.")

    # Display messages and editing UI (Copying existing robust logic)
    # ... (previous message display and editing logic remains largely the same, ensure keys are unique)
    for i, message in enumerate(st.session_state[agent_name]["messages"]):
        if message["role"] in ["user", "assistant"]:
            _content = message["content"]
            if _content is not None:
                with st.chat_message(message["role"], avatar={"user": "🧑‍💻", "assistant": "🛡️"}.get(message["role"])):
                    message_key_prefix = f"{agent_name}_msg_{st.session_state[agent_name]['session_id']}_{i}"
                    if st.session_state.editing_message_idx == i:
                        edited_text = st.text_area("Edit your message:", value=st.session_state.edited_message_content, key=f"{message_key_prefix}_edit_area")
                        col1, col2 = st.columns(2)
                        if col1.button("💾 Save Changes", key=f"{message_key_prefix}_save_edit"):
                            st.session_state[agent_name]["messages"][i]["content"] = edited_text
                            st.session_state[agent_name]["messages"] = st.session_state[agent_name]["messages"][:i+1]
                            st.session_state.editing_message_idx = None
                            st.session_state.edited_message_content = ""
                            st.rerun()
                        if col2.button("✖️ Cancel", key=f"{message_key_prefix}_cancel_edit"):
                            st.session_state.editing_message_idx = None
                            st.session_state.edited_message_content = ""
                            st.rerun()
                    else:
                        st.markdown(_content)
                        if message["role"] == "user":
                            if st.button("✏️ Edit", key=f"{message_key_prefix}_edit_btn", help="Edit this message"):
                                st.session_state.editing_message_idx = i
                                st.session_state.edited_message_content = _content
                                st.rerun()
                    
                    if "tool_calls" in message and message["tool_calls"] and st.session_state.editing_message_idx != i:
                        display_tool_calls(st.empty(), message["tool_calls"])

    # Generate response logic
    last_message = st.session_state[agent_name]["messages"][-1] if st.session_state[agent_name]["messages"] else None
    if last_message and last_message.get("role") == "user" and st.session_state.editing_message_idx is None:
        if not auditor_agent or not auditor_agent.session_id: # Ensure agent is ready
            st.warning("Agent session not ready. Cannot process message.")
        else:
            user_message_content = str(last_message["content"])
            logger.info(f"Responding to message: '{user_message_content}' for session {auditor_agent.session_id} by user {user_id}")
            with st.chat_message("assistant", avatar="🛡️"):
                tool_calls_container = st.empty()
                resp_container = st.empty()
                with st.spinner("🛡️ Analyzing project..."):
                    response_text = ""
                    try:
                        # Prevent saving empty user messages that didn't lead to a run
                        if not user_message_content.strip():
                            logger.info("Skipping agent run for empty user message.")
                            # Optionally remove the empty user message from UI history if desired
                            # st.session_state[agent_name]["messages"].pop()
                        else:
                            run_response_stream = await auditor_agent.arun(user_message_content, stream=True)
                            async for resp_chunk in run_response_stream:
                                if resp_chunk.tools and len(resp_chunk.tools) > 0:
                                    display_tool_calls(tool_calls_container, resp_chunk.tools)
                                if resp_chunk.content is not None:
                                    response_text += resp_chunk.content
                                    resp_container.markdown(response_text)
                            
                            if auditor_agent.run_response: # run_response has the full data after stream
                                await add_message(agent_name, "assistant", response_text, auditor_agent.run_response.tools)
                            else:
                                await add_message(agent_name, "assistant", response_text)

                    except Exception as e:
                        logger.error(f"Error during agent run: {str(e)}", exc_info=True)
                        error_message = f"Sorry, I encountered an error: {str(e)}"
                        await add_message(agent_name, "assistant", error_message)
                        st.error(error_message)

    # Session Selector and Utilities (at the bottom or in sidebar)
    # The session_selector should ideally handle the agent re-initialization for a selected session.
    if auditor_agent and auditor_agent.storage:
        # The agent instance passed to session_selector is important.
        # It uses this agent's user_id, agent_id for querying sessions.
        # Its on_change will use the factory to create a new agent instance for the selected session.
        # Crucially, the on_change of session_selector should set the new agent into st.session_state[agent_name]["agent"]
        # AND clear st.session_state[agent_name]["messages"]
        # This is standard behavior for agno's session_selector.
        await session_selector(agent_name, auditor_agent, get_local_security_auditor_agent, user_id, model_id)
        await utilities_widget(agent_name, auditor_agent)
    else:
        st.sidebar.text("Session history features unavailable.")

async def main():
    # Initial setup of session_state structure if it doesn't exist.
    # initialize_agent_session_state(agent_name) # This built-in might be too generic, manual preferred for now.
    if agent_name not in st.session_state:
        st.session_state[agent_name] = {"agent": None, "messages": [], "session_id": None}
    elif "messages" not in st.session_state[agent_name]: # Ensure messages list exists
        st.session_state[agent_name]["messages"] = []
    elif "session_id" not in st.session_state[agent_name]:
        st.session_state[agent_name]["session_id"] = None
    
    await header()
    await body()
    await about_agno()

if __name__ == "__main__":
    if check_password():
        asyncio.run(main()) 