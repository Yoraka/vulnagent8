import asyncio
from textwrap import dedent
from typing import Optional, List, Any
from pathlib import Path # Import Path

from agno.agent import Agent
from agno.team import Team
from agno.tools import Function # Import Function for wrapping callables

from core.model_factory import get_model_instance, DEFAULT_MODEL_ID 
from agents.deep_dive_security_auditor_agent import (
    DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG,
    DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID,
    DeepDiveReportStructuredOutput # Import the Pydantic model
)
from agno.tools.file import FileTools 
from agno.tools.shell import ShellTools 
from tools.report_repository_tools import save_report_to_repository, read_report_from_repository 
# Import the session state tool classes
from tools.session_state_tools import ReadSessionStateTool, UpdateSessionStateTool 
from tools.project_structure_tools import ListDirectoryTreeTool # Import the new tool

from pydantic import BaseModel, Field

# Standard plan filename, consistent with SecurityAuditTeam
PLAN_FILENAME_FOR_TEST = "AttackSurfaceInvestigationPlan_whitebox.md" 

# MINIMAL_TEAM_LEADER_INSTRUCTIONS_CACHE_TEST = dedent(f'''...''') # Commenting out previous cache test instructions

# New Minimal Team Leader Instructions for Deep Dive Agent Cache Test & Tree Tool Test
MINIMAL_TEAM_LEADER_INSTRUCTIONS_DEEP_DIVE_CACHE_TEST = dedent(f'''\
You are a Test Team Leader. Your sole task is to delegate a specific multi-step file operation task to the DeepDiveSecurityAuditorAgent to test its internal input caching behavior, its ability to use the list_directory_tree tool, AND its structured output capability.

**Agent Details:**
- Agent ID for delegation: '{DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID}'
- Agent Name: '{DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG.name}'

**Your Tools:**
- `atransfer_task_to_member`: To delegate tasks.

**Workflow:**

**Single Phase: Delegate Test Task to DeepDiveSecurityAuditorAgent**
1.  The specific task description for the DeepDiveSecurityAuditorAgent is PREDEFINED in its own instructions for general tasks. You will provide a specific sequence for this test.
2.  You **MUST** use the `atransfer_task_to_member` tool to delegate this task.
    - `member_id`: '{DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID}'
    - `task_description`: "Perform a test sequence: First, use the `list_directory_tree` tool with `target_path="."` and `max_depth=1` to list the contents of your base directory. Then, perform your predefined multi-step cache test task which involves reading config_for_cache_test.txt, then status_for_cache_test.txt, then creating and saving CacheTestDeepDiveReport.md. Your final output should be a JSON object conforming to the DeepDiveReportStructuredOutput model, including the filename CacheTestDeepDiveReport.md."
    - `expected_output`: "A JSON object string that conforms to the DeepDiveReportStructuredOutput model. For example: {{ \"report_filename\": \"CacheTestDeepDiveReport.md\", \"status_message\": \"Report saved successfully.\" }}"
3.  The DeepDiveSecurityAuditorAgent is expected to perform several internal tool calls and return a structured JSON output.
4.  Once the DeepDiveSecurityAuditorAgent responds with the JSON object, you must parse this JSON, extract the value of the `report_filename` field.
5.  Your final response for this entire interaction **MUST BE ONLY** the extracted `report_filename` (which should be "CacheTestDeepDiveReport.md"), or any critical error it might report if it fails or if the JSON is malformed.

Do not add any other commentary. Strictly follow this delegation.
''')
class DeepDiveReportStructuredOutput(BaseModel):
    report_filename: str = Field(..., description="The filename of the saved Markdown report. This is the primary output.")
    status_message: str = Field(..., description="A brief status message, e.g., 'Report saved successfully', 'Audit completed with warnings', 'Error during audit'.")
    key_findings_summary: Optional[List[str]] = Field(None, description="Optional: A list of 1-3 very brief strings highlighting the most critical findings, if any. Omit if no critical findings or if an error occurred.")
    tool_calls_made: Optional[int] = Field(None, description="Optional: Number of tool calls made during the audit for this task.")

class MinimalTestTeam(Team):
    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        user_id: Optional[str] = "default_user",
        team_id: str = "minimal_test_team_deep_dive_v1",
        name: str = "MinimalTestDeepDiveTeam_Phase3Sim",
        **kwargs: Any,
    ):
        team_leader_model = get_model_instance(model_id)
        if not team_leader_model:
            raise ValueError(f"Could not get team_leader_model instance for {model_id}")
        
        auditor_agent_model_id = model_id # Use same model for auditor in this test team
        auditor_agent_model = get_model_instance(auditor_agent_model_id)
        if not auditor_agent_model:
            raise ValueError(f"Could not get auditor_agent_model instance for {auditor_agent_model_id}")

        # Define base directory for auditor's file tools
        auditor_base_dir = Path("/data/jstachio") 
        # Ensure it exists for the tools if they are strict at init, though they should handle it gracefully
        # auditor_base_dir.mkdir(parents=True, exist_ok=True) # Usually not tool's job to create its base

        auditor_file_tools = FileTools(base_dir=str(auditor_base_dir))
        auditor_shell_tools = ShellTools()
        
        # Instantiate and wrap ListDirectoryTreeTool
        list_dir_tree_tool_instance = ListDirectoryTreeTool(base_dir=str(auditor_base_dir))
        list_directory_tree_tool_wrapped = Function.from_callable(list_dir_tree_tool_instance.__call__)
        list_directory_tree_tool_wrapped.name = list_dir_tree_tool_instance.name
        list_directory_tree_tool_wrapped.description = list_dir_tree_tool_instance.description
        
        deep_dive_agent_tools = [
            auditor_file_tools,
            auditor_shell_tools,
            read_report_from_repository,
            save_report_to_repository,
            list_directory_tree_tool_wrapped # Add the new tool
        ]
        deep_dive_auditor_agent = Agent(
            agent_id=DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID,
            name=DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG.name,
            description=DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG.description,
            instructions=DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG.instructions_template, 
            tools=deep_dive_agent_tools,
            model=auditor_agent_model,
            user_id=user_id,
            debug_mode=True,
            response_model=DeepDiveReportStructuredOutput, # Added response_model
            # use_json_mode=True # Can be added if model supports strict JSON mode and it's desired
        )
        
        # Team specific tools for the Leader
        # Instantiate the tool classes
        update_tool_instance = UpdateSessionStateTool()
        read_tool_instance = ReadSessionStateTool()

        # Wrap their __call__ methods using Function.from_callable
        update_session_state_tool_func = Function.from_callable(update_tool_instance.__call__)
        update_session_state_tool_func.name = update_tool_instance.name
        update_session_state_tool_func.description = update_tool_instance.description

        read_session_state_tool_func = Function.from_callable(read_tool_instance.__call__)
        read_session_state_tool_func.name = read_tool_instance.name
        read_session_state_tool_func.description = read_tool_instance.description
        
        team_level_tools = [
            update_session_state_tool_func, 
            read_session_state_tool_func, 
            read_report_from_repository
        ]

        super().__init__(
            team_id=team_id,
            name=name,
            instructions=MINIMAL_TEAM_LEADER_INSTRUCTIONS_DEEP_DIVE_CACHE_TEST, 
            members=[deep_dive_auditor_agent],
            model=team_leader_model,
            tools=team_level_tools,
            user_id=user_id,
            session_state={'audit_plan_items': [], 'current_audit_item_index': 0, 'individual_report_files': []}, 
            debug_mode=True, 
            enable_team_history=True, 
            **kwargs, 
        )
        print(f"MinimalTestTeam '{name}' initialized with leader model '{model_id}'. Testing ListDirectoryTreeTool and class-based session tools.")

# The async main() and if __name__ == "__main__": block are removed.
# Instantiation will now be done in playground.py or other runner scripts.
# The dummy project creation is also removed, as it's not the responsibility of this module. 