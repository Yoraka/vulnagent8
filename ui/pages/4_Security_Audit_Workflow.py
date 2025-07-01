import streamlit as st
# import requests # No longer making HTTP requests to self for this
import json
import os
import uuid # For generating session_ids
import asyncio # For running async functions if needed
import nest_asyncio # To allow nested asyncio event loops
from typing import AsyncIterator, List, Optional # Added List, Optional

from agno.run.response import RunResponse # Reverted from agno.client.response_models
from agno.media import Image # Added for image input

# Assuming SecurityAuditWorkflow is accessible from this path
# This might require adjusting PYTHONPATH or the import statement if issues arise
from workflows.security_audit_team import (
    SecurityAuditTeam,
    SECURITY_AUDIT_TEAM_ID,
    DEPLOYMENT_ARCHITECTURE_REPORTER_AGENT_ID,
    ATTACK_SURFACE_PLANNING_AGENT_ID,
    DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID,
    SHARED_REPORTS_DIR, # To show where reports are saved
    DEPLOYMENT_REPORT_FILENAME,
    PLAN_FILENAME,
    AGGREGATED_DEEP_DIVE_FILENAME_PREFIX,
    INDIVIDUAL_DEEP_DIVE_REPORT_PREFIX
)
# We might need display_tool_calls from ui.utils if we want to reuse it
# from ui.utils import display_tool_calls 

nest_asyncio.apply() # Apply nest_asyncio early

st.set_page_config(layout="wide", page_title="Security Audit Team Workflow")

# BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://agent-app-api:8000") # Not used for direct call
# WORKFLOW_ENDPOINT = f"{BACKEND_API_URL}/v1/workflows/run_security_audit" # Not used

st.title("🛡️ Security Audit Team Workflow")

# Moved the output area and its subheader higher up
st.markdown("---")
st.subheader("Team Workflow Output (Streaming)")
output_area = st.empty() # Placeholder for stream output
st.markdown("---")

st.markdown("""
This page runs a **three-stage security audit** using a coordinated team of AI agents:
1.  **Environment Perception Agent**: Analyzes the project structure, deployment, and technologies.
2.  **Attack Surface Planning Agent**: Uses the environment analysis and user query to create a detailed, white-box code review plan (with actionable tasks).
3.  **Deep Dive Security Auditor Agent (Iterative)**: Executes each task from the plan, performing in-depth code and configuration reviews, and attempts to formulate PoCs. The Team Leader coordinates this iterative process.

Optionally, you can upload images (e.g., network diagrams, architecture schematics) for richer context for the first agent.
""")

# --- Inputs Section ---
col1, col2 = st.columns([0.7, 0.3])

with col1:
    project_path = st.text_input(
        "Enter the full workspace_path of the project to analyze (e.g., /data/target_code):",
        value=st.session_state.get("audit_project_path", "/data/target_code") # Default to a path accessible within a typical Docker setup
    )
    st.session_state.audit_project_path = project_path

with col2:
    uploaded_files = st.file_uploader(
        "Optional: Upload Images (Network/Architecture Diagrams for Stage 1)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="audit_team_images"
    )

if "team_workflow_running" not in st.session_state:
    st.session_state.team_workflow_running = False
if "team_workflow_content" not in st.session_state:
    st.session_state.team_workflow_content = ""
# No need for separate tool_calls_md list if we embed them directly or handle differently.

def get_agent_name_from_id(agent_id: str) -> str:
    if agent_id == SECURITY_AUDIT_TEAM_ID:
        return "Team Leader"
    elif agent_id == DEPLOYMENT_ARCHITECTURE_REPORTER_AGENT_ID:
        return "Environment Perception Agent"
    elif agent_id == ATTACK_SURFACE_PLANNING_AGENT_ID:
        return "Attack Surface Planning Agent"
    elif agent_id == DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID:
        return "Deep Dive Security Auditor Agent"
    # For member agents that might have suffixes if multiple instances were used by team
    if DEPLOYMENT_ARCHITECTURE_REPORTER_AGENT_ID in agent_id: return "Environment Perception Agent"
    if ATTACK_SURFACE_PLANNING_AGENT_ID in agent_id: return "Attack Surface Planning Agent"
    if DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID in agent_id: return "Deep Dive Security Auditor Agent"
    return agent_id # Fallback to raw ID

async def generate_team_workflow_output_stream(team_instance: SecurityAuditTeam, initial_message: str, images: Optional[List[Image]] = None):
    st.session_state.team_workflow_running = True
    st.session_state.team_workflow_content = "" # Reset content for new run
    accumulated_text_for_placeholder = ""
    
    try:
        async for response_chunk in team_instance.stream_team_audit(initial_user_query=initial_message, images=images): # Pass images if team supports
            chunk_to_display = ""
            agent_name = "Unknown Agent/Team"
            if response_chunk and hasattr(response_chunk, 'run_id') and response_chunk.run_id:
                agent_name = get_agent_name_from_id(response_chunk.run_id)

            if response_chunk:
                # Handle content stream from Team Leader or Agents
                if response_chunk.event == "on_agent_stream_chunk":
                    content = response_chunk.data.get("output_chunk", "")
                    if content:
                        # Only display stream from Team Leader directly, or add prefix for agents
                        # if response_chunk.run_id == SECURITY_AUDIT_TEAM_ID:
                        #     chunk_to_display += content
                        # else:
                        #     chunk_to_display += f"*{agent_name} streaming...*\n{content}\n"
                        # For now, let's display all stream chunks, prefixing non-leader ones.
                        # The Team Leader's main orchestration logic might be verbose, so focus on its explicit outputs via on_agent_action_end
                        if response_chunk.run_id != SECURITY_AUDIT_TEAM_ID:
                             chunk_to_display += content # Display agent's direct stream
                        else: # Team leader stream
                            chunk_to_display += content


                # Handle final output from an agent (or the team leader)
                elif response_chunk.event == "on_agent_action_end":
                    content = response_chunk.data.get("output", "")
                    if content:
                        chunk_to_display += f"\n\n---\n**Output from {agent_name}:**\n```text\n{content}\n```\n---\n"
                
                # Handle tool calls
                elif response_chunk.event == "on_tool_use" or response_chunk.event == "on_tool_end":
                    tool_name = response_chunk.data.get('name', 'Unknown Tool')
                    tool_input_str = json.dumps(response_chunk.data.get('input', {}), indent=2, ensure_ascii=False)
                    
                    summary_line = f"🛠️ Tool Call by {agent_name}: {tool_name}"
                    details_content = f"**Input:**\n```json\n{tool_input_str}\n```\n"

                    if response_chunk.event == "on_tool_end":
                        tool_output = response_chunk.data.get('output', 'No Output')
                        # if isinstance(tool_output, str) and len(tool_output) > 500: # Truncate long outputs
                        #     tool_output = tool_output[:500] + "... (truncated)"
                        # else:
                        #     tool_output = str(tool_output) # Ensure it's a string
                        # For now, don't truncate in the stream, full output is in backend logs.
                        # The UI might become too cluttered. Let's show a summary.
                        # For FileTools.edit_file, output can be long.
                        if tool_name == "edit_file" and isinstance(tool_output, dict) and "results" in tool_output :
                             details_content += f"**Output:**\n```json\n{json.dumps(tool_output, indent=2, ensure_ascii=False)}\n```\n" # Show structured output for edit_file
                        elif isinstance(tool_output, str):
                             details_content += f"**Output (summary):**\n```\n{tool_output[:300] if tool_output else 'No Output/Empty'}{'... (truncated)' if tool_output and len(tool_output) > 300 else ''}\n```\n"
                        else:
                             details_content += f"**Output:**\n```json\n{json.dumps(tool_output, indent=2, ensure_ascii=False)}\n```\n"


                    tool_call_md = f"<details>\n<summary>{summary_line} ({'completed' if response_chunk.event == 'on_tool_end' else 'started'})</summary>\n\n{details_content}\n</details>\n"
                    chunk_to_display += "\n" + tool_call_md

            if chunk_to_display:
                st.session_state.team_workflow_content += chunk_to_display
                output_area.markdown(st.session_state.team_workflow_content, unsafe_allow_html=True)
                yield chunk_to_display # Still yield for st.write_stream if it were used directly

    except Exception as e:
        error_message = f"Error in generate_team_workflow_output_stream: {e}"
        st.session_state.team_workflow_content += f"\n\n<span style='color: red;'>{error_message}</span>"
        output_area.markdown(st.session_state.team_workflow_content, unsafe_allow_html=True)
        st.error(error_message)
        import traceback
        print(traceback.format_exc()) # Log full traceback to console
    finally:
        st.session_state.team_workflow_running = False
        st.info("Team workflow finished. Check below for report paths.")
        # Add display of final report paths here or trigger a rerun to show them
        st.rerun() # Rerun to display the final reports section


if st.button("Run Security Audit Team Workflow", key="run_audit_team_workflow"):
    if not project_path:
        st.warning("Please enter a project path.")
    else:
        st.session_state.team_workflow_running = True
        st.session_state.team_workflow_content = "" # Clear previous content
        output_area.info("Team workflow started... Please wait, this may take several minutes.")
        
        agno_images: Optional[List[Image]] = None
        if uploaded_files:
            agno_images = []
            for uploaded_file in uploaded_files:
                image_bytes = uploaded_file.getvalue()
                agno_images.append(Image(content=image_bytes, format=uploaded_file.type.split('/')[-1]))
            if agno_images: st.success(f"Processing with {len(agno_images)} image(s) for context.")

        session_id = f"ui-audit-team-{uuid.uuid4()}"
        
        # Ensure the SHARED_REPORTS_DIR exists
        # The SecurityAuditTeam class now handles this, but belt and braces
        try:
            os.makedirs(SHARED_REPORTS_DIR, exist_ok=True)
        except Exception as e:
            st.error(f"Could not create shared reports directory {SHARED_REPORTS_DIR}: {e}")
            st.stop()

        # Instantiate the team
        # Assuming OPENROUTER_API_KEY is set elsewhere (e.g. environment variable)
        # and model_factory.py is correctly configured.
        # The SecurityAuditTeam class will use the default model_id from model_factory if not specified
        team = SecurityAuditTeam() 
        
        initial_message_to_team = f"The project to analyze is at workspace_path: {project_path}."
        if agno_images:
            initial_message_to_team += " Please also consider any provided images in your analysis for the initial environment perception stage."
        
        async def run_and_update_team_ui():
            async for _ in generate_team_workflow_output_stream(team, initial_message_to_team, agno_images):
                pass 
            # The st.rerun() in the finally block of the generator will handle updating the page

        try:
            asyncio.run(run_and_update_team_ui())
        except Exception as e:
            st.error(f"Failed to run team workflow: {e}")
            import traceback
            st.error(traceback.format_exc())
            st.session_state.team_workflow_running = False
            output_area.markdown(st.session_state.team_workflow_content, unsafe_allow_html=True)

# Display final report information if workflow is not running and content exists
if not st.session_state.get('team_workflow_running', False) and st.session_state.team_workflow_content:
    st.markdown("---")
    st.subheader("Workflow Complete & Generated Reports")
    st.success(f"The team audit workflow has finished. Reports are located in: `{os.path.abspath(SHARED_REPORTS_DIR)}`")
    
    report_files = []
    if os.path.exists(SHARED_REPORTS_DIR):
        report_files = [f for f in os.listdir(SHARED_REPORTS_DIR) if os.path.isfile(os.path.join(SHARED_REPORTS_DIR, f))]

    if DEPLOYMENT_REPORT_FILENAME in report_files:
        st.markdown(f"- **Environment Report**: `{DEPLOYMENT_REPORT_FILENAME}`")
    if PLAN_FILENAME in report_files:
        st.markdown(f"- **Attack Surface Plan**: `{PLAN_FILENAME}`")
    
    individual_reports = sorted([f for f in report_files if f.startswith(INDIVIDUAL_DEEP_DIVE_REPORT_PREFIX)])
    if individual_reports:
        with st.expander(f"Individual Deep Dive Audit Reports ({len(individual_reports)} files):"):
            for report_name in individual_reports:
                st.markdown(f"  - `{report_name}`")
                
    aggregated_reports = sorted([f for f in report_files if f.startswith(AGGREGATED_DEEP_DIVE_FILENAME_PREFIX)], reverse=True)
    if aggregated_reports:
        st.markdown(f"- **Aggregated Audit Findings**: `{aggregated_reports[0]}` (Latest)")
        if len(aggregated_reports) > 1:
            with st.expander("Older Aggregated Reports"):
                for report_name in aggregated_reports[1:]:
                    st.markdown(f"  - `{report_name}`")
    
    if not report_files:
        st.warning("No report files found in the shared directory. The workflow might not have completed all stages successfully.")


st.markdown("---")
st.markdown(f"**Note**: Ensure the project path is accessible. Reports are saved to `{os.path.abspath(SHARED_REPORTS_DIR)}` on the server.") 