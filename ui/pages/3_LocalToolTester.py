import asyncio
import nest_asyncio
import streamlit as st
from agno.agent import Agent
from agno.tools.streamlit.components import check_password
from agno.utils.log import logger

from agents.local_tool_tester import get_local_tool_tester_agent, HARDCODED_WORKSPACE_PATH # MODIFIED: Import HARDCODED_WORKSPACE_PATH
from ui.css import CUSTOM_CSS
from ui.utils import (
    about_agno,
    add_message,
    display_tool_calls,
    initialize_agent_session_state,
    selected_model, # Model selection might be less relevant if the agent is for fixed tool testing
    # session_selector, # Session management might be simplified or removed
    # utilities_widget, # May not need all utilities for a test agent
)

nest_asyncio.apply()

st.set_page_config(
    page_title="Local Tool Tester", # Changed title
    page_icon=":wrench:", # Changed icon
    layout="wide",
)
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
agent_name = "local_tool_tester" # Changed agent name


async def header():
    st.markdown("<h1 class='heading'>Local Tool Tester</h1>", unsafe_allow_html=True) # Changed heading
    st.markdown(
        "<p class='subheading'>An agent to test local command execution using ShellTools.</p>", # Changed subheading
        unsafe_allow_html=True,
    )


async def body() -> None:
    ####################################################################
    # Initialize User and Session State
    ####################################################################
    user_id = st.sidebar.text_input(":technologist: Username", value="Tester")

    ####################################################################
    # Model selector - Potentially simplify or fix for a test agent
    ####################################################################
    model_id = await selected_model() # Or fix to a default model for testing

    ####################################################################
    # Initialize Agent
    ####################################################################
    tester_agent: Agent # Changed variable name
    if (
        agent_name not in st.session_state
        or st.session_state[agent_name]["agent"] is None
        or st.session_state.get("selected_model") != model_id # Retain if model selection is kept
    ):
        logger.info(f"---*--- Creating {agent_name.capitalize()} Agent ---*---") # Dynamic agent name
        tester_agent = get_local_tool_tester_agent(user_id=user_id, model_id=model_id) # Changed function call
        st.session_state[agent_name]["agent"] = tester_agent
        st.session_state["selected_model"] = model_id
    else:
        tester_agent = st.session_state[agent_name]["agent"]

    ####################################################################
    # Load Agent Session from the database - Simplified for a test agent
    # ShellTools typically doesn't require complex session loading like RAG agents
    ####################################################################
    # if tester_agent.storage: # Check if storage is configured (might not be for simple ShellTools agent)
    #     try:
    #         st.session_state[agent_name]["session_id"] = tester_agent.load_session()
    #     except Exception as e:
    #         st.warning(f"Could not load Agent session: {e}")
    # else:
    #     st.session_state[agent_name]["session_id"] = tester_agent.session_id

    # Simplified session ID handling for a test agent
    if not st.session_state[agent_name].get("session_id"):
        st.session_state[agent_name]["session_id"] = tester_agent.session_id


    ####################################################################
    # Load agent runs (i.e. chat history) - if memory is used
    ####################################################################
    if tester_agent.memory and not st.session_state[agent_name]["messages"]:
        agent_runs = tester_agent.memory.runs
        if len(agent_runs) > 0:
            logger.debug("Loading run history")
            for agent_run in agent_runs:
                if agent_run.message is not None:
                    await add_message(agent_name, agent_run.message.role, str(agent_run.message.content))
                if agent_run.response is not None:
                    await add_message(
                        agent_name, "assistant", str(agent_run.response.content), agent_run.response.tools
                    )

    ####################################################################
    # Get user input
    ####################################################################
    prompt_placeholder = (
        f"Ask LocalToolTester to run a command (e.g., 'list files in {HARDCODED_WORKSPACE_PATH}')" # MODIFIED: Use imported constant
    )
    if prompt := st.chat_input(prompt_placeholder):
        await add_message(agent_name, "user", prompt)

    ####################################################################
    # Show example inputs - Customize for LocalToolTester
    ####################################################################
    # await example_inputs(agent_name, ["List files in the current directory", "What is your working directory?"]) # Example
    # For now, let's disable example_inputs or make it very simple
    if not st.session_state[agent_name]["messages"]:
         st.info(f"Welcome to the Local Tool Tester! Try asking it to list files in its designated workspace or run other shell commands. The configured workspace is: {HARDCODED_WORKSPACE_PATH}") # MODIFIED: Use imported constant


    ####################################################################
    # Display agent messages
    ####################################################################
    for message in st.session_state[agent_name]["messages"]:
        if message["role"] in ["user", "assistant"]:
            _content = message["content"]
            if _content is not None:
                with st.chat_message(message["role"]):
                    if "tool_calls" in message and message["tool_calls"]:
                        display_tool_calls(st.empty(), message["tool_calls"])
                    st.markdown(_content)

    ####################################################################
    # Generate response for user message
    ####################################################################
    last_message = st.session_state[agent_name]["messages"][-1] if st.session_state[agent_name]["messages"] else None
    if last_message and last_message.get("role") == "user":
        user_message = str(last_message["content"])
        logger.info(f"Responding to message: {user_message}")
        with st.chat_message("assistant"):
            tool_calls_container = st.empty()
            resp_container = st.empty()
            with st.spinner(":construction_worker: Executing command..."): # Changed spinner
                response = ""
                try:
                    run_response = await tester_agent.arun(user_message, stream=True)
                    async for resp_chunk in run_response:
                        if resp_chunk.tools and len(resp_chunk.tools) > 0:
                            display_tool_calls(tool_calls_container, resp_chunk.tools)
                        if resp_chunk.content is not None:
                            response += resp_chunk.content
                            resp_container.markdown(response)
                    if tester_agent.run_response is not None:
                        await add_message(agent_name, "assistant", response, tester_agent.run_response.tools)
                    else:
                        await add_message(agent_name, "assistant", response)
                except Exception as e:
                    logger.error(f"Error during agent run: {str(e)}", exc_info=True)
                    error_message = f"Sorry, I encountered an error: {str(e)}"
                    await add_message(agent_name, "assistant", error_message)
                    st.error(error_message)

    # Simplified sidebar - removing knowledge widget and potentially session selector for this agent
    # await utilities_widget(agent_name, tester_agent) # Keep if needed for clearing history etc.

async def main():
    await initialize_agent_session_state(agent_name)
    await header()
    await body()
    await about_agno()


if __name__ == "__main__":
    # The sys.path modification should ideally be in a common entry point or managed by how you run Streamlit.
    # If you run streamlit run agent-app/ui/Home.py (and agent-app is in PYTHONPATH or you run from E:\vulnAgent8),
    # imports like `from agents.local_tool_tester` should work.
    # For direct execution of this page for testing (streamlit run agent-app/ui/pages/3_LocalToolTester.py),
    # you might need to ensure agent-app is in sys.path.
    # One way: add the following at the very top of THIS file if running it directly and imports fail:
    # import sys, os
    # sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
    if check_password(): # Assuming check_password handles authentication
        asyncio.run(main()) 