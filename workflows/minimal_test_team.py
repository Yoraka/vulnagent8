import asyncio
from textwrap import dedent
from typing import Optional, List, Any

from agno.agent import Agent
from agno.team import Team
from agno.tools import Function # Import Function for wrapping callables

from core.model_factory import get_model_instance, DEFAULT_MODEL_ID 
from agents.deep_dive_security_auditor_agent import (
    DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG,
    DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID
)
from agno.tools.file import FileTools 
from agno.tools.shell import ShellTools 
from tools.report_repository_tools import save_report_to_repository, read_report_from_repository 
# Import the session state tool classes
from tools.session_state_tools import ReadSessionStateTool, UpdateSessionStateTool 

# Standard plan filename, consistent with SecurityAuditTeam
PLAN_FILENAME_FOR_TEST = "AttackSurfaceInvestigationPlan_whitebox.md" 

# Restore Minimal Team Leader Instructions to test session state tools
MINIMAL_TEAM_LEADER_INSTRUCTIONS = dedent(f'''\
You are a Test Team Leader. Your goal is to read an audit plan from the shared repository, parse it, **mandatorily store it in session_state using tools**, read it back, report on the count, and then delegate the FIRST task to the DeepDiveSecurityAuditorAgent.

**Agent Details:**
- Agent ID for delegation: '{DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID}'
- Agent Name: '{DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG.name}'

**Your Tools:**
- `atransfer_task_to_member`: To delegate tasks.
- `UpdateSessionStateTool`: To modify `session_state`. Args: `key` (str), `value` (any), `action` (str, optional: 'set', 'append', 'increment'). Default action is 'set'.
- `ReadSessionStateTool`: To read from `session_state`. Args: `key` (str).
- `read_report_from_repository`: To read reports.

**Workflow:**

**Phase 1: Plan Ingestion and State Verification (MANDATORY TOOL USE)**
1.  **Read the Audit Plan:**
    a. You **MUST** use the `read_report_from_repository` tool to read the content of the audit plan.
    b. The `report_name` to read is "{PLAN_FILENAME_FOR_TEST}".
    c. If the tool returns an error or no content, report this critical error and stop.
2.  **Parse the Plan (assuming successful read):**
    a. Create an empty list in your internal reasoning (e.g., `parsed_tasks`).
    b. Iterate through each line of the retrieved audit plan content.
    c. If a line starts with `- [ ]` (a Markdown unchecked checkbox):
        i.  Extract the full text after `- [ ] ` as the `raw_task_line`.
        ii. Create a dictionary: `{{ "raw_task_line": "THE_RAW_LINE_TEXT", "description": "THE_RAW_LINE_TEXT", "status": "pending" }}`.
        iii. Add this dictionary to your `parsed_tasks` list.
3.  **Update Session State (MANDATORY TOOL USE - THREE SEPARATE CALLS):**
    a. You **MUST** call `UpdateSessionStateTool` with `key='audit_plan_items'`, `value=YOUR_ENTIRE_PARSED_TASKS_LIST`, `action='set'`.
    b. You **MUST** call `UpdateSessionStateTool` with `key='current_audit_item_index'`, `value=0`, `action='set'`.
    c. You **MUST** call `UpdateSessionStateTool` with `key='individual_report_files'`, `value=[]`, `action='set'`.
4.  **Verify and Report from Session State (MANDATORY TOOL USE - TWO SEPARATE CALLS):**
    a. You **MUST** call `ReadSessionStateTool` with `key='audit_plan_items'` to get the list of tasks.
    b. You **MUST** call `ReadSessionStateTool` with `key='current_audit_item_index'` to get the current index.
    c. Let `retrieved_tasks` be the list from step 4a and `retrieved_index` be the value from 4b.
    d. If `retrieved_tasks` is None or `retrieved_index` is None, report a critical error: "Failed to read populated values from session_state after UpdateSessionStateTool calls." Then stop.
    e. Count the number of items in `retrieved_tasks`. State: "Successfully read plan from repository and updated session_state. Found [COUNT] tasks in 'audit_plan_items'. Current index is [INDEX]."
    f. If `retrieved_tasks` is empty, report: "Audit plan was empty after parsing. Stopping." Then stop.

**Phase 2: Delegate First Audit Task (Contingent on successful Phase 1)**
1.  Use the `retrieved_tasks` and `retrieved_index` from Phase 1, step 4c.
2.  Get the task dictionary for the `retrieved_index`: `current_task_data = retrieved_tasks[retrieved_index]`.
3.  Extract the `description` field (raw task line) from `current_task_data`.
4.  Construct the full task description: "`description_from_plan`. The project for this audit is located at `{{workspace_path}}`. Please also consult `DeploymentArchitectureReport.md` from the repository if relevant."
5.  Delegate this full task description to agent '{DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID}' using `atransfer_task_to_member`.
6.  The agent is expected to return ONLY THE FILENAME of its report.
7.  Your final response: ONLY this filename, or any critical error encountered.

''')

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
        
        auditor_agent_model_id = model_id
        auditor_agent_model = get_model_instance(auditor_agent_model_id)
        if not auditor_agent_model:
            raise ValueError(f"Could not get auditor_agent_model instance for {auditor_agent_model_id}")

        auditor_file_tools = FileTools()
        auditor_shell_tools = ShellTools()
        deep_dive_agent_tools = [
            auditor_file_tools,
            auditor_shell_tools,
            read_report_from_repository,
            save_report_to_repository
        ]
        deep_dive_auditor_agent = Agent(
            agent_id=DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID,
            name=DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG.name,
            description=DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG.description,
            instructions=DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG.instructions_template, 
            tools=deep_dive_agent_tools,
            model=auditor_agent_model,
            user_id=user_id,
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
            instructions=MINIMAL_TEAM_LEADER_INSTRUCTIONS, 
            members=[deep_dive_auditor_agent], 
            model=team_leader_model,
            tools=team_level_tools,
            user_id=user_id,
            session_state={'audit_plan_items': [], 'current_audit_item_index': 0, 'individual_report_files': []}, 
            debug_mode=True,
            enable_team_history=True, 
            **kwargs, 
        )
        print(f"MinimalTestTeam '{name}' initialized with leader model '{model_id}'. Testing class-based session tools via Function.from_callable.")

# The async main() and if __name__ == "__main__": block are removed.
# Instantiation will now be done in playground.py or other runner scripts.
# The dummy project creation is also removed, as it's not the responsibility of this module. 