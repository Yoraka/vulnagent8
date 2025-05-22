import streamlit as st
# import requests # No longer making HTTP requests to self for this
import json
import os
import uuid # For generating session_ids
import asyncio # For running async functions if needed
import nest_asyncio # To allow nested asyncio event loops
from typing import AsyncIterator, List, Optional # Added List, Optional

from agno.run.response import RunResponse # To type hint what workflow.run yields
from agno.media import Image # Added for image input

# Assuming SecurityAuditWorkflow is accessible from this path
# This might require adjusting PYTHONPATH or the import statement if issues arise
from workflows.security_audit_workflow import SecurityAuditWorkflow
# We might need display_tool_calls from ui.utils if we want to reuse it
# from ui.utils import display_tool_calls 

nest_asyncio.apply() # Apply nest_asyncio early

st.set_page_config(layout="wide", page_title="Security Audit Workflow")

# BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://agent-app-api:8000") # Not used for direct call
# WORKFLOW_ENDPOINT = f"{BACKEND_API_URL}/v1/workflows/run_security_audit" # Not used

st.title("🛡️ Security Audit Workflow")

# Moved the output area and its subheader higher up
st.markdown("---")
st.subheader("Workflow Output (Streaming)")
output_area = st.empty() # Placeholder for stream output
st.markdown("---")

st.markdown("""
This page allows you to run a two-step security audit workflow:
1.  **Environment Perception**: Analyzes the project structure, deployment, and technologies. Can optionally accept images (e.g., network diagrams, architecture schematics) for richer context.
2.  **Attack Surface Identification**: Uses the environment analysis to find potential attack surfaces.
""")

# --- Inputs Section ---
col1, col2 = st.columns([0.7, 0.3])

with col1:
    project_path = st.text_input(
        "Enter the full workspace_path of the project to analyze within the container (e.g., /data/my_project):", 
        value=st.session_state.get("audit_project_path", "/data/mall_code")
    )
    st.session_state.audit_project_path = project_path

with col2:
    uploaded_files = st.file_uploader(
        "Optional: Upload Images (Network/Architecture Diagrams)", 
        type=["png", "jpg", "jpeg"], 
        accept_multiple_files=True,
        key="audit_workflow_images"
    )

if "workflow_running" not in st.session_state:
    st.session_state.workflow_running = False
# Use more descriptive names for session state to avoid clashes if we bring back other agents
if "audit_workflow_content" not in st.session_state:
    st.session_state.audit_workflow_content = ""
if "audit_workflow_tool_calls_md" not in st.session_state:
    st.session_state.audit_workflow_tool_calls_md = [] # Store markdown strings for tool calls

# This function will now be an async generator for st.write_stream
async def generate_workflow_output_stream(workflow: SecurityAuditWorkflow, initial_message: str, images: Optional[List[Image]] = None):
    st.session_state.workflow_running = True
    st.session_state.audit_workflow_tool_calls_md = [] # Reset tool calls for new run
    st.session_state.audit_workflow_content = "" # Reset content for new run
    accumulated_text_for_placeholder = ""
    
    try:
        first_agent_completed_message_sent = False
        async for response_chunk in workflow.stream_audit(initial_message=initial_message, images=images):
            chunk_to_display = ""
            if response_chunk:
                if hasattr(response_chunk, 'agent_id') and response_chunk.agent_id == workflow.env_perception_agent.agent_id:
                    # Content from the first agent (even if it's just a single chunk now)
                    if hasattr(response_chunk, 'content') and response_chunk.content:
                        chunk_content = response_chunk.content
                        st.session_state.audit_workflow_content += chunk_content
                        chunk_to_display += chunk_content
                    
                    if hasattr(response_chunk, 'tools') and response_chunk.tools:
                        for tool_call in response_chunk.tools:
                            tool_name = tool_call.get('name', 'Unknown Tool')
                            tool_input_str = json.dumps(tool_call.get('input', 'No Input'), indent=2)
                            tool_output = tool_call.get('output', 'No Output')
                            if isinstance(tool_output, str) and len(tool_output) > 300:
                                tool_output = tool_output[:300] + "... (truncated)"
                            else:
                                tool_output = str(tool_output)
                            tool_call_md = f"<details>\n<summary>🛠️ Tool Call: {tool_name}</summary>\n\n**Input:**\n```json\n{tool_input_str}\n```\n**Output:**\n```\n{tool_output}\n```\n</details>\n"
                            st.session_state.audit_workflow_tool_calls_md.append(tool_call_md)
                            chunk_to_display += "\n" + tool_call_md
                    
                    # After processing the (potentially single) chunk from the first agent
                    if not first_agent_completed_message_sent:
                        completion_message = f"\n\n---\n**🛡️ {workflow.env_perception_agent.name} (Agent 1) has completed.**\nStarting {workflow.attack_surface_agent.name} (Agent 2)...\n---"
                        chunk_to_display += completion_message
                        st.session_state.audit_workflow_content += completion_message # Also add to full content log
                        first_agent_completed_message_sent = True

                elif hasattr(response_chunk, 'agent_id') and response_chunk.agent_id == workflow.attack_surface_agent.agent_id:
                    # Content from the second agent
                    if hasattr(response_chunk, 'content') and response_chunk.content:
                        chunk_content = response_chunk.content
                        st.session_state.audit_workflow_content += chunk_content
                        chunk_to_display += chunk_content
                    
                    if hasattr(response_chunk, 'tools') and response_chunk.tools:
                        # (Identical tool display logic as above, can be refactored)
                        for tool_call in response_chunk.tools:
                            tool_name = tool_call.get('name', 'Unknown Tool')
                            tool_input_str = json.dumps(tool_call.get('input', 'No Input'), indent=2)
                            tool_output = tool_call.get('output', 'No Output')
                            if isinstance(tool_output, str) and len(tool_output) > 300:
                                tool_output = tool_output[:300] + "... (truncated)"
                            else:
                                tool_output = str(tool_output)
                            tool_call_md = f"<details>\n<summary>🛠️ Tool Call: {tool_name}</summary>\n\n**Input:**\n```json\n{tool_input_str}\n```\n**Output:**\n```\n{tool_output}\n```\n</details>\n"
                            st.session_state.audit_workflow_tool_calls_md.append(tool_call_md)
                            chunk_to_display += "\n" + tool_call_md
            
            if chunk_to_display:
                accumulated_text_for_placeholder += chunk_to_display
                output_area.markdown(accumulated_text_for_placeholder, unsafe_allow_html=True)
                yield chunk_to_display

    except Exception as e:
        error_message = f"Error in generate_workflow_output_stream: {e}"
        # import traceback # Already imported by Agno probably
        # error_message += f"\n{traceback.format_exc()}"
        st.session_state.audit_workflow_content += f"\n\n<span style='color: red;'>{error_message}</span>"
        output_area.markdown(st.session_state.audit_workflow_content, unsafe_allow_html=True)
        # yield error_message # yield error to stream if needed
        st.error(error_message) # Also display as a more prominent error
        print(error_message) # also log to server console
        # import traceback
        # print(traceback.format_exc())
    finally:
        st.session_state.workflow_running = False


# Main button logic for Streamlit page
if st.button("Run Security Audit Workflow", key="run_audit_workflow"):
    if not project_path:
        st.warning("Please enter a project path.")
    else:
        st.session_state.audit_workflow_running = True
        output_area.info("Workflow started...") # Initial message in the placeholder
        
        # Prepare images for the workflow
        agno_images: Optional[List[Image]] = None
        if uploaded_files:
            agno_images = []
            for uploaded_file in uploaded_files:
                # For Agno, we need to pass image content as bytes or a filepath if the agent/model supports it.
                # Using content (bytes) is generally more portable if the workflow runs in a different context than UI.
                image_bytes = uploaded_file.getvalue()
                agno_images.append(Image(content=image_bytes, format=uploaded_file.type.split('/')[-1]))
            st.success(f"Processing with {len(agno_images)} image(s).")

        session_id = f"ui-audit-workflow-{uuid.uuid4()}"
        workflow = SecurityAuditWorkflow(session_id=session_id, debug_mode=True) 
        initial_message = f"The project to analyze is at workspace_path: {project_path}. Please also consider any provided images in your analysis."
        
        # Using asyncio.run to bridge to the async world from Streamlit's sync context
        # We are not using st.write_stream directly with the generator anymore,
        # but rather updating the st.empty() placeholder from within the async generator.
        async def run_and_update():
            async for _ in generate_workflow_output_stream(workflow, initial_message, agno_images):
                pass # The generator itself updates the UI
            st.session_state.audit_workflow_running = False
            # No explicit rerun here, final content is already in audit_workflow_content 
            # and displayed by the placeholder updates.
            # output_area.markdown(st.session_state.audit_workflow_content, unsafe_allow_html=True) # Ensure final display

        try:
            asyncio.run(run_and_update())
        except Exception as e:
            st.error(f"Failed to run workflow: {e}")
            # import traceback
            # st.error(traceback.format_exc())
            st.session_state.audit_workflow_running = False
            output_area.markdown(st.session_state.audit_workflow_content, unsafe_allow_html=True) # Show whatever content was accumulated

# This part is removed as the placeholder is updated directly and st.rerun is avoided.
# if not st.session_state.get('audit_workflow_running', False) and st.session_state.audit_workflow_content:
#    st.markdown("### Final Accumulated Workflow Output:")
#    st.markdown(st.session_state.audit_workflow_content, unsafe_allow_html=True)
#    if st.session_state.audit_workflow_tool_calls_md:
#        st.markdown("---debug: tool calls collected---")
#        for tc_md in st.session_state.audit_workflow_tool_calls_md:
#            st.markdown(tc_md, unsafe_allow_html=True)

st.markdown("---")
st.markdown("**Note**: Ensure the project path is accessible by the UI container (e.g., `/app/data/...`).") 