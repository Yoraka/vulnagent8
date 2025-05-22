from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from agno.run.response import RunResponse
import uuid
import json # Added for JSON serialization
from typing import AsyncGenerator, Iterator # Iterator added for workflow.run typing

# Assuming PYTHONPATH might be set to the 'vulnagent8' directory itself,
# making 'workflows' a top-level importable package from within 'api.routes'
from workflows.security_audit_workflow import SecurityAuditWorkflow

# Create a new APIRouter instance for workflow-related endpoints
workflows_router = APIRouter()

async def stream_workflow_response(workflow: SecurityAuditWorkflow, initial_message: str) -> AsyncGenerator[str, None]:
    """Helper async generator to stream workflow responses as Server-Sent Events."""
    run_response_iterator: Iterator[RunResponse] = workflow.run(initial_message=initial_message)
    for run_response in run_response_iterator:
        if run_response:
            # Serialize the RunResponse object (or parts of it) to JSON
            # For now, let's assume we just want to stream the 'content' if available
            # and potentially other fields like 'type' or 'tool_calls' later.
            
            response_data = {}
            if hasattr(run_response, 'content') and run_response.content:
                response_data['content'] = run_response.content
            if hasattr(run_response, 'type') and run_response.type: # Example: 'message', 'tool_call', 'tool_result'
                response_data['type'] = run_response.type.value if hasattr(run_response.type, 'value') else run_response.type
            if hasattr(run_response, 'tool_calls') and run_response.tool_calls:
                 response_data['tool_calls'] = run_response.tool_calls # Assuming serializable
            # Add other relevant fields from RunResponse as needed

            if not response_data: # Don't send empty messages
                continue

            json_data = json.dumps(response_data)
            sse_event_line = f"data: {json_data}\\n\\n" # SSE format: data: <json_string>\\n\\n
            print(f"BACKEND SENDING SSE: {sse_event_line!r}") # Print the exact SSE event line
            yield sse_event_line
    
    # Signal end of stream
    end_event_data = {"event": "stream_end"}
    final_event_json = json.dumps(end_event_data)
    final_event_sse_line = f"data: {final_event_json}\\n\\n"
    print(f"BACKEND SENDING FINAL SSE: {final_event_sse_line!r}")
    yield final_event_sse_line

@workflows_router.post("/run_security_audit", name="Run Security Audit Workflow")
async def run_security_audit_endpoint(project_path: str):
    """
    Runs the security audit workflow with the given project path as the initial message.
    Streams the responses back.
    """
    if not project_path:
        raise HTTPException(status_code=400, detail="project_path query parameter is required.")

    session_id = f"audit-workflow-{uuid.uuid4()}"
    initial_message = f"Please analyze the project at the following workspace path: {project_path}"

    try:
        # Assuming SecurityAuditWorkflow can be instantiated with debug_mode
        # and that its .run() method is an iterator/generator
        workflow = SecurityAuditWorkflow(session_id=session_id, debug_mode=True) # Ensure debug_mode is passed if needed
        
        # Use the async generator for SSE
        return StreamingResponse(stream_workflow_response(workflow, initial_message), media_type="text/event-stream")
    except ImportError as e:
        # Log this error server-side for debugging
        print(f"ImportError during workflow execution: {e}")
        raise HTTPException(status_code=500, detail=f"Workflow module import error: {e}")
    except Exception as e:
        # Log this error server-side
        print(f"Exception during workflow execution: {e}")
        # Consider if more specific error handling or information disclosure is appropriate
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred during workflow execution: {e}")

# Removed old non-streaming code block to avoid confusion, 
# the above endpoint is the corrected one for streaming. 