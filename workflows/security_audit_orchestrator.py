import asyncio
import os
import uuid
import time
from textwrap import dedent
from typing import AsyncIterator, List, Optional, Dict, Any, Iterator, Union
from pathlib import Path
import json

from agno.agent import Agent
from agno.run.response import RunResponse, RunEvent
from agno.workflow import Workflow
from agno.media import Image
from agno.storage.sqlite import SqliteStorage # Keep concrete one for __main__ example

# It's likely we'll need model instances, similar to the original team
from core.model_factory import get_model_instance, DEFAULT_MODEL_ID

# Import agent configurations and IDs (assuming these are accessible)
from agents.environment_perception_agent import (
    DEPLOYMENT_ARCHITECTURE_REPORTER_AGENT_CONFIG,
    DEPLOYMENT_ARCHITECTURE_REPORTER_AGENT_ID
)
from agents.attack_surface_identification_agent import (
    ATTACK_SURFACE_PLANNING_AGENT_CONFIG,
    ATTACK_SURFACE_PLANNING_AGENT_ID
)
from agents.deep_dive_security_auditor_agent import (
    DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG,
    DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID
)

# Import tool functions (assuming these can be called directly or wrapped)
from tools.report_repository_tools import (
    save_report_to_repository,
    read_report_from_repository,
    SHARED_REPORTS_DIR
)

# --- Report Filenames Constants (copied from original team) ---
DEPLOYMENT_REPORT_FILENAME = "DeploymentArchitectureReport.md"
PLAN_FILENAME = "AttackSurfaceInvestigationPlan_whitebox.md"
AGGREGATED_DEEP_DIVE_FILENAME_PREFIX = "DeepDiveAuditFindings_Aggregated"
INDIVIDUAL_DEEP_DIVE_REPORT_PREFIX = "DeepDiveReport_Task"

# --- Session State Keys ---
# These keys will be used to store and retrieve data from self.session_state
PHASE_1_OUTPUT_KEY = "phase_1_output_deployment_report_path"
PHASE_2_OUTPUT_KEY = "phase_2_output_audit_plan_filepath"
PHASE_3_OUTPUT_KEY_INDIVIDUAL_REPORTS = "phase_3_output_individual_report_files"
PHASE_3_OUTPUT_KEY_COMPLETED_TASKS = "phase_3_output_completed_tasks" # List of raw task lines marked as done
WORKFLOW_CURRENT_PHASE_STATUS_KEY = "workflow_current_phase_status" # e.g., "phase_1_completed", "phase_3_in_progress"


class SecurityAuditWorkflow(Workflow):
    description: str = dedent((
        "Orchestrates a three-stage security audit of a software project, with advanced execution control and caching. "
        "Stage 1: Environment Perception. Stage 2: Attack Surface Planning. Stage 3: Deep-Dive Auditing. Stage 4: Aggregation."
    ))

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID, # General model ID if specific ones aren't set
        env_reporter_model_id: Optional[str] = None,
        attack_planning_model_id: Optional[str] = None,
        deep_dive_auditor_model_id: Optional[str] = None,
        user_id: Optional[str] = "workflow_user",
        session_id: Optional[str] = None, # Crucial for persistent state
        storage: Optional[Any] = None, # Changed type hint from WorkflowStorageBase to Any
        # Alternatively, could use: Optional[SqliteWorkflowStorage] if only sqlite is planned
        # Or: from agno.storage.base import StorageBase (if such a generic base exists and is importable)
        **kwargs: Any,
    ):
        # Ensure a session_id is present if storage is used, for state persistence
        _session_id = session_id if session_id else f"audit_session_{uuid.uuid4()}"
        
        super().__init__(session_id=_session_id, storage=storage, **kwargs) # Initialize base Workflow class
        
        self.user_id = user_id
        # self.run_id is typically managed by the Workflow base or per-run.
        # For a persistent workflow, session_id is more central for state.

        # Resolve model IDs
        _env_reporter_model_id = env_reporter_model_id or model_id
        _attack_planning_model_id = attack_planning_model_id or model_id
        _deep_dive_auditor_model_id = deep_dive_auditor_model_id or model_id

        # Instantiate models
        env_reporter_model = get_model_instance(_env_reporter_model_id)
        attack_planning_model = get_model_instance(_attack_planning_model_id)
        deep_dive_auditor_model = get_model_instance(_deep_dive_auditor_model_id)

        self.env_perception_agent = Agent(
            agent_id=DEPLOYMENT_ARCHITECTURE_REPORTER_AGENT_ID,
            name=DEPLOYMENT_ARCHITECTURE_REPORTER_AGENT_CONFIG.name,
            description=DEPLOYMENT_ARCHITECTURE_REPORTER_AGENT_CONFIG.description,
            instructions=DEPLOYMENT_ARCHITECTURE_REPORTER_AGENT_CONFIG.instructions,
            tools=[save_report_to_repository],
            model=env_reporter_model,
        )

        self.attack_planning_agent = Agent(
            agent_id=ATTACK_SURFACE_PLANNING_AGENT_ID,
            name=ATTACK_SURFACE_PLANNING_AGENT_CONFIG.name,
            description=ATTACK_SURFACE_PLANNING_AGENT_CONFIG.description,
            instructions=ATTACK_SURFACE_PLANNING_AGENT_CONFIG.instructions,
            tools=[read_report_from_repository, save_report_to_repository] + (ATTACK_SURFACE_PLANNING_AGENT_CONFIG.tools or []),
            model=attack_planning_model,
        )

        self.deep_dive_auditor_agent = Agent(
            agent_id=DEEP_DIVE_SECURITY_AUDITOR_AGENT_ID,
            name=DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG.name,
            description=DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG.description,
            instructions=DEEP_DIVE_SECURITY_AUDITOR_AGENT_CONFIG.instructions_template,
            tools=[read_report_from_repository, save_report_to_repository], # Add other tools if they are directly usable
            model=deep_dive_auditor_model,
        )
        
        os.makedirs(SHARED_REPORTS_DIR, exist_ok=True)
        print(f"SecurityAuditWorkflow initialized for session_id='{self.session_id}'. Reports in: {os.path.abspath(SHARED_REPORTS_DIR)}")
        # self.session_state is automatically loaded by Workflow base if storage & session_id are provided.

    async def _invoke_agent(self, agent: Agent, task_description: str, **kwargs) -> RunResponse:
        """Helper to run an agent and get its consolidated response."""
        print(f"Invoking agent: {agent.name} for task: {task_description[:100]}...")
        # stream=False should ideally return a single RunResponse with the full content.
        # If it returns an iterator, we need to consume it.
        response_or_iterator = await agent.arun(message=task_description, stream=False, **kwargs)

        final_response: Optional[RunResponse] = None
        if isinstance(response_or_iterator, RunResponse):
            final_response = response_or_iterator
        elif hasattr(response_or_iterator, '__aiter__'): # Check if it's an async iterator
            async for r_chunk in response_or_iterator:
                final_response = r_chunk # Capture the last (or only) response, assuming it aggregates.
                # A more robust way might be to check for a specific event like on_agent_action_end if available
        else:
            print(f"Warning: Agent {agent.name} returned an unexpected type: {type(response_or_iterator)}. Expected RunResponse or AsyncIterator.")
            return RunResponse(run_id=agent.agent_id or agent.name, content=f"[DATA]: {json.dumps({'error': 'Unexpected agent response type'}, ensure_ascii=False)}", event=RunEvent.agent_error)

        if not final_response:
             print(f"Warning: Agent {agent.name} did not produce a final response object.")
             return RunResponse(run_id=agent.agent_id or agent.name, content=f"[DATA]: {json.dumps({'error': 'No final response from agent'}, ensure_ascii=False)}", event=RunEvent.agent_error)

        output_preview = None
        if final_response.data and final_response.data.get("output"):
            output_preview = str(final_response.data.get('output'))
        elif final_response.content:
            output_preview = str(final_response.content)
        
        if output_preview:
            print(f"Agent {agent.name} completed. Output (preview): {output_preview[:200]}...")
        else:
            print(f"Agent {agent.name} completed, but no direct output/content found in RunResponse. Full data: {final_response.data}")
        
        return final_response

    async def _save_state_and_notify(self, event_name: str, event_data: Dict, content: Optional[str] = None):
        """Saves session_state to storage and yields a notification."""
        self.write_to_storage() # Persist changes
        yield RunResponse(run_id=self.run_id, event=event_name, content=f"{content or ''}\n[DATA]: {json.dumps(event_data, ensure_ascii=False)}")
        print(f"[State Notification] Event: {event_name}, Data: {event_data}, Content: {content or ''}")

    async def stream_audit(
        self,
        initial_user_query: Optional[str] = None, # Needed if starting from scratch or for context
        images: Optional[List[Image]] = None,
        
        # --- Control Parameters ---
        start_at_phase: int = 1,
        force_rerun_phases: Optional[List[int]] = None, # List of phase numbers to rerun
        target_tasks_for_phase3: Optional[List[str]] = None, # Exact raw lines of tasks to run in phase 3
        
        # --- Inspection/Manipulation Parameters ---
        inspect_phase_output: Optional[int] = None,
        inspect_all_session_state: bool = False,
        clear_cache_for_phases: Optional[List[int]] = None,
        clear_all_session_cache: bool = False
    ) -> AsyncIterator[RunResponse]:

        # self.session_state is loaded by the Workflow base class if storage and session_id are set.
        # It's an empty dict if not found in storage or no storage.
        
        # 0. Handle Cache Clearing Commands First
        if clear_all_session_cache:
            self.session_state.clear()
            await self._save_state_and_notify("cache_cleared", {"scope": "all"}, "All session cache cleared.")
            # Typically, after clearing all, a re-run from phase 1 is implied or should be commanded next.
            return 
        if clear_cache_for_phases:
            keys_to_clear = []
            for phase_num in clear_cache_for_phases:
                if phase_num == 1: keys_to_clear.append(PHASE_1_OUTPUT_KEY)
                elif phase_num == 2: keys_to_clear.append(PHASE_2_OUTPUT_KEY)
                elif phase_num == 3: 
                    keys_to_clear.append(PHASE_3_OUTPUT_KEY_INDIVIDUAL_REPORTS)
                    keys_to_clear.append(PHASE_3_OUTPUT_KEY_COMPLETED_TASKS)
                # Phase 4 is aggregation, its direct output is the final report, not typically "cleared" in this way
            for key in keys_to_clear:
                if key in self.session_state:
                    del self.session_state[key]
            await self._save_state_and_notify("cache_cleared_for_phases", {"phases": clear_cache_for_phases}, f"Cache cleared for phases: {clear_cache_for_phases}.")
            # After clearing, the user might want to re-run or inspect.
            # Consider if the function should return here or proceed based on other params.
            # For now, it proceeds, potentially re-running if start_at_phase dictates.

        # 0. Handle Inspection Commands
        if inspect_all_session_state:
            yield RunResponse(run_id=self.run_id, event="session_state_inspection", content=f"Full session state.\n[DATA]: {json.dumps({'session_state': self.session_state}, ensure_ascii=False)}")
            return
        if inspect_phase_output is not None:
            output_key = None
            if inspect_phase_output == 1: output_key = PHASE_1_OUTPUT_KEY
            elif inspect_phase_output == 2: output_key = PHASE_2_OUTPUT_KEY
            elif inspect_phase_output == 3: 
                # Yield both parts of phase 3 state
                reports = self.session_state.get(PHASE_3_OUTPUT_KEY_INDIVIDUAL_REPORTS)
                completed = self.session_state.get(PHASE_3_OUTPUT_KEY_COMPLETED_TASKS)
                yield RunResponse(run_id=self.run_id, event="phase_output_inspection", content=f"Cached output for phase 3.\n[DATA]: {json.dumps({'phase': 3, 'individual_reports': reports, 'completed_tasks': completed}, ensure_ascii=False)}")
                return

            cached_data = self.session_state.get(output_key) if output_key else None
            yield RunResponse(run_id=self.run_id, event="phase_output_inspection", content=f"Cached output for phase {inspect_phase_output}.\n[DATA]: {json.dumps({'phase': inspect_phase_output, 'cached_data': cached_data}, ensure_ascii=False)}")
            return

        # --- Workflow Execution ---
        # Ensure force_rerun_phases is a list if provided
        _force_rerun_phases = force_rerun_phases or []

        # Retrieve the initial query if needed and not already in session_state (e.g., for context in later phases)
        # This assumes initial_user_query is only passed on the very first run for a session, or if context is lost.
        # A more robust way would be to store it in session_state if it's always needed.
        _current_initial_query = initial_user_query or self.session_state.get("initial_user_query_context")
        if initial_user_query and not self.session_state.get("initial_user_query_context"):
             self.session_state["initial_user_query_context"] = initial_user_query


        yield RunResponse(run_id=self.run_id, event="workflow_start_or_resume", content=f"Workflow audit process started/resumed for session {self.session_id}.\n[DATA]: {json.dumps({'start_at_phase': start_at_phase, 'force_rerun': _force_rerun_phases, 'session_id': self.session_id}, ensure_ascii=False)}")

        # --- Phase 1: Environment Perception ---
        deployment_report_path_str: Optional[str] = self.session_state.get(PHASE_1_OUTPUT_KEY)
        if start_at_phase <= 1 and (1 in _force_rerun_phases or not deployment_report_path_str):
            if not _current_initial_query:
                yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content="Initial user query is required to start/rerun Phase 1.", error=True)
                return
            yield RunResponse(run_id=self.run_id, event="phase_start", content=f"[DATA]: {json.dumps({'phase': 1, 'name': 'Environment Perception'}, ensure_ascii=False)}")
            env_task_desc = (
                f"Analyze the project based on the user query: '{_current_initial_query}'. "
                f"Produce a deployment architecture report. Your final output artifact should be the "
                f"content of this report. Save this report using the 'save_report_to_repository' tool "
                f"with the report_name '{DEPLOYMENT_REPORT_FILENAME}'."
            )
            await self._invoke_agent(self.env_perception_agent, env_task_desc) # Agent saves the file
            
            temp_path = Path(SHARED_REPORTS_DIR) / DEPLOYMENT_REPORT_FILENAME
            if not temp_path.exists():
                yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content=f"Phase 1 Error: Deployment report '{temp_path}' not found after agent execution.", error=True)
                return
            deployment_report_path_str = str(temp_path)
            self.session_state[PHASE_1_OUTPUT_KEY] = deployment_report_path_str
            self.session_state[WORKFLOW_CURRENT_PHASE_STATUS_KEY] = "phase_1_completed"
            await self._save_state_and_notify("phase_end", {"phase": 1, "status": "completed", "report_path": deployment_report_path_str})
        elif start_at_phase > 1 and not deployment_report_path_str:
            yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content="Cannot start at Phase > 1: Phase 1 output (Deployment Report) not found in cache.", error=True)
            return
        else: # Using cache or skipping
            yield RunResponse(run_id=self.run_id, event="phase_skipped_or_cached", content=f"[DATA]: {json.dumps({'phase': 1, 'report_path': deployment_report_path_str}, ensure_ascii=False)}")

        # --- Phase 2: Attack Surface Planning ---
        audit_plan_filepath_str: Optional[str] = self.session_state.get(PHASE_2_OUTPUT_KEY)
        if start_at_phase <= 2 and (2 in _force_rerun_phases or not audit_plan_filepath_str):
            if not deployment_report_path_str: # Dependency from Phase 1
                 yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content="Phase 2 Error: Deployment report path from Phase 1 is missing.", error=True)
                 return
            if not _current_initial_query: # Also needed for context
                 yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content="Phase 2 Error: Initial user query context is missing.", error=True)
                 return

            yield RunResponse(run_id=self.run_id, event="phase_start", content=f"[DATA]: {json.dumps({'phase': 2, 'name': 'Attack Surface Planning'}, ensure_ascii=False)}")
            plan_task_desc = (
                f"Read the deployment architecture report from '{deployment_report_path_str}'. "
                f"Consider the original user query: '{_current_initial_query}'. "
                f"Create an attack surface investigation plan. Your final output artifact should be the "
                f"content of this plan. You **MUST** save this plan using the 'save_report_to_repository' tool "
                f"with the exact report_name '{PLAN_FILENAME}'."
            )
            await self._invoke_agent(self.attack_planning_agent, plan_task_desc) # Agent saves the file

            temp_path = Path(SHARED_REPORTS_DIR) / PLAN_FILENAME
            if not temp_path.exists():
                yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content=f"Phase 2 Error: Attack plan '{temp_path}' not found after agent execution.", error=True)
                return
            try: # Verify readability
                with open(temp_path, 'r', encoding='utf-8') as f: f.read(10)
            except Exception as e:
                yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content=f"Phase 2 Error: Attack plan '{temp_path}' exists but cannot be read. Error: {e}", error=True)
                return
            audit_plan_filepath_str = str(temp_path)
            self.session_state[PHASE_2_OUTPUT_KEY] = audit_plan_filepath_str
            self.session_state[WORKFLOW_CURRENT_PHASE_STATUS_KEY] = "phase_2_completed"
            await self._save_state_and_notify("phase_end", {"phase": 2, "status": "completed", "plan_path": audit_plan_filepath_str})
        elif start_at_phase > 2 and not audit_plan_filepath_str:
            yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content="Cannot start at Phase > 2: Phase 2 output (Audit Plan) not found in cache.", error=True)
            return
        else: # Using cache or skipping
            yield RunResponse(run_id=self.run_id, event="phase_skipped_or_cached", content=f"[DATA]: {json.dumps({'phase': 2, 'plan_path': audit_plan_filepath_str}, ensure_ascii=False)}")

        # --- Phase 3: Iterative Deep-Dive Auditing ---
        # Load from session state, initialize if not present
        individual_report_files: List[str] = self.session_state.get(PHASE_3_OUTPUT_KEY_INDIVIDUAL_REPORTS, [])
        completed_tasks_in_plan: List[str] = self.session_state.get(PHASE_3_OUTPUT_KEY_COMPLETED_TASKS, [])

        if start_at_phase <= 3: # Only run or potentially continue phase 3 if targeted
            if not audit_plan_filepath_str: # Dependency from Phase 2
                yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content="Phase 3 Error: Audit plan path from Phase 2 is missing.", error=True)
                return
            if not _current_initial_query: # Context
                 yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content="Phase 3 Error: Initial user query context is missing.", error=True)
                 return

            yield RunResponse(run_id=self.run_id, event="phase_start", content=f"[DATA]: {json.dumps({'phase': 3, 'name': 'Deep-Dive Auditing'}, ensure_ascii=False)}")
            self.session_state[WORKFLOW_CURRENT_PHASE_STATUS_KEY] = "phase_3_in_progress"
            await self._save_state_and_notify("phase_status_update", {"phase": 3, "status": "in_progress"})

            # If phase 3 is in force_rerun_phases, clear its previous progress
            if 3 in _force_rerun_phases:
                individual_report_files = []
                completed_tasks_in_plan = []
                self.session_state[PHASE_3_OUTPUT_KEY_INDIVIDUAL_REPORTS] = []
                self.session_state[PHASE_3_OUTPUT_KEY_COMPLETED_TASKS] = []
                yield RunResponse(run_id=self.run_id, event="phase_3_progress_reset", content=f"[DATA]: {json.dumps({'reason': 'force_rerun'}, ensure_ascii=False)}")


            # Main loop for Phase 3 tasks
            max_tasks_to_process_this_run = None # Set to a number if you want to limit tasks per call
            tasks_processed_this_run = 0
            
            while True:
                if max_tasks_to_process_this_run is not None and tasks_processed_this_run >= max_tasks_to_process_this_run:
                    yield RunResponse(run_id=self.run_id, event="phase_3_iteration_limit_reached", content=f"[DATA]: {json.dumps({'limit': max_tasks_to_process_this_run}, ensure_ascii=False)}")
                    break

                try:
                    with open(audit_plan_filepath_str, 'r', encoding='utf-8') as f: plan_content_lines = f.readlines()
                except Exception as e:
                    yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content=f"Phase 3 Error: Could not read audit plan '{audit_plan_filepath_str}'. Error: {e}", error=True)
                    return

                current_raw_task_line_from_file: Optional[str] = None
                full_task_context_lines = []
                task_line_number_in_file = -1
                
                # Find next task
                for i, line_in_plan in enumerate(plan_content_lines):
                    stripped_line = line_in_plan.strip()
                    is_pending = stripped_line.startswith("- [ ] ")
                    # If target_tasks_for_phase3 is specified, only pick tasks from that list.
                    # The check `line_in_plan.rstrip() in completed_tasks_in_plan` is to ensure we don't re-process.
                    # However, if a task is in target_tasks_for_phase3 and also in completed_tasks_in_plan,
                    # and phase 3 is *not* in force_rerun_phases, we should skip it.
                    # If phase 3 *is* in force_rerun_phases, completed_tasks_in_plan was already cleared.
                    
                    task_already_completed = line_in_plan.rstrip() in completed_tasks_in_plan

                    if is_pending and not task_already_completed:
                        if target_tasks_for_phase3: # If specific tasks are targeted
                            if stripped_line in target_tasks_for_phase3 or line_in_plan.rstrip() in target_tasks_for_phase3:
                                current_raw_task_line_from_file = line_in_plan
                                task_line_number_in_file = i
                                # (Context extraction logic as before)
                                full_task_context_lines.append(line_in_plan)
                                for j in range(i + 1, len(plan_content_lines)):
                                    nextLine = plan_content_lines[j]
                                    if nextLine.strip().startswith(("- [ ] ", "- [x] ")): break
                                    full_task_context_lines.append(nextLine)
                                break # Found a targeted, pending task
                        else: # No specific targets, pick first pending task
                            current_raw_task_line_from_file = line_in_plan
                            task_line_number_in_file = i
                            # (Context extraction logic as before)
                            full_task_context_lines.append(line_in_plan)
                            for j in range(i + 1, len(plan_content_lines)):
                                nextLine = plan_content_lines[j]
                                if nextLine.strip().startswith(("- [ ] ", "- [x] ")): break
                                full_task_context_lines.append(nextLine)
                            break # Found first pending task
                
                if not current_raw_task_line_from_file: # No more suitable tasks found
                    yield RunResponse(run_id=self.run_id, event="phase_3_no_more_tasks", content=f"[DATA]: {json.dumps({'target_tasks': target_tasks_for_phase3, 'completed_in_session': len(completed_tasks_in_plan)}, ensure_ascii=False)}")
                    break # Exit Phase 3 loop
                
                tasks_processed_this_run += 1
                _current_audit_task_raw_line_for_agent = current_raw_task_line_from_file.rstrip()
                full_task_description_for_agent = "".join(full_task_context_lines)

                yield RunResponse(run_id=self.run_id, event="task_delegation", content=f"[DATA]: {json.dumps({'task_line': _current_audit_task_raw_line_for_agent}, ensure_ascii=False)}")
                
                auditor_task_desc = f"""Perform a deep-dive security audit for the following task taken from the audit plan:
{full_task_description_for_agent}
Consider the original user query for broader context: '{_current_initial_query}'.
Your final output should be a string: the filename of the report you saved using 'save_report_to_repository'. The report filename should be unique, perhaps like '{INDIVIDUAL_DEEP_DIVE_REPORT_PREFIX}_[task_identifier_or_summary].md'."""
                auditor_response = await self._invoke_agent(self.deep_dive_auditor_agent, auditor_task_desc)

                new_report_filename = None
                if auditor_response and auditor_response.content and isinstance(auditor_response.content, str):
                    new_report_filename = auditor_response.content.strip()
                elif auditor_response and auditor_response.data and isinstance(auditor_response.data.get("output"), str):
                    new_report_filename = auditor_response.data.get("output").strip()

                if not new_report_filename:
                    yield RunResponse(run_id=self.run_id, event="task_error", 
                                      data={"task": _current_audit_task_raw_line_for_agent, "error": "Auditor did not return report filename"}, error=True)
                    # Decide: stop workflow, skip task, or retry? For now, skip this task's processing.
                    # If it's skipped, it might be picked up again in the next interaction unless `target_tasks_for_phase3` changes.
                    # Or we could add it to a "failed_tasks" list in session_state.
                    # To prevent infinite loops on consistently failing tasks without `target_tasks_for_phase3`, this needs care.
                    # For now, just yield error and it will be re-attempted or skipped on next "find task"
                    continue 

                if new_report_filename not in individual_report_files: # Avoid duplicates if re-running
                    individual_report_files.append(new_report_filename)
                
                # Mark task as complete in plan file (by modifying the list of lines)
                # And add to our session_state list of completed tasks
                edited_task_line = current_raw_task_line_from_file.replace("- [ ] ", "- [x] ", 1)
                plan_content_lines[task_line_number_in_file] = edited_task_line
                
                if current_raw_task_line_from_file.rstrip() not in completed_tasks_in_plan:
                    completed_tasks_in_plan.append(current_raw_task_line_from_file.rstrip())

                try: # Write changes back to plan file
                    with open(audit_plan_filepath_str, 'w', encoding='utf-8') as f: f.writelines(plan_content_lines)
                except Exception as e:
                    yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content=f"Phase 3 Error: Failed to update audit plan file '{audit_plan_filepath_str}'. Error: {e}", error=True)
                    # Potentially revert session state changes for this task or halt
                    return 
                
                # Update session state after successful task completion and plan update
                self.session_state[PHASE_3_OUTPUT_KEY_INDIVIDUAL_REPORTS] = individual_report_files
                self.session_state[PHASE_3_OUTPUT_KEY_COMPLETED_TASKS] = completed_tasks_in_plan
                await self._save_state_and_notify("task_completed_in_plan", {"task": edited_task_line.strip(), "report_file": new_report_filename})
            
            # End of Phase 3 while loop
            self.session_state[WORKFLOW_CURRENT_PHASE_STATUS_KEY] = "phase_3_completed" # Or partially if loop broke early
            await self._save_state_and_notify("phase_end", {"phase": 3, "status": "processed_tasks_in_run", "total_individual_reports": len(individual_report_files)})
        elif start_at_phase > 3 and (not individual_report_files or not audit_plan_filepath_str): # Check dependencies for phase 4
            yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content="Cannot start at Phase 4: Phase 3 output (Individual Reports / Plan) not found in cache.", error=True)
            return
        else: # Phase 3 skipped or already done according to start_at_phase
             yield RunResponse(run_id=self.run_id, event="phase_skipped_or_cached", content=f"[DATA]: {json.dumps({'phase': 3, 'individual_reports_count': len(individual_report_files)}, ensure_ascii=False)}")


        # --- Phase 4: Final Aggregation and Output ---
        # Phase 4 always runs if prior phases are complete (or skipped via start_at_phase and cache exists)
        # unless start_at_phase is > 4 (which means workflow is done or an invalid state)
        if start_at_phase <= 4 :
            # Check if all prerequisites for aggregation are met
            if not audit_plan_filepath_str: # Plan file is a soft check, but good to have
                yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content="Phase 4 Warning: Audit plan file path not found, proceeding with aggregation if reports exist.", error=False) # Not a fatal error for aggregation itself
            
            # Key dependency: individual_report_files from Phase 3
            # If individual_report_files is empty, Phase 4 might still run but produce an empty agg report.

            yield RunResponse(run_id=self.run_id, event="phase_start", content=f"[DATA]: {json.dumps({'phase': 4, 'name': 'Final Aggregation'}, ensure_ascii=False)}")
            
            final_report_content_parts = []
            if not individual_report_files: # Loaded from session_state at start of phase 3 section
                final_report_content_parts.append("No individual deep dive audit reports were generated or recorded successfully to aggregate.")
            else:
                for i, report_filename in enumerate(individual_report_files):
                    try:
                        report_content = read_report_from_repository(report_name=report_filename)
                        final_report_content_parts.append(f"--- Report: {report_filename} ---{report_content}")
                        if i < len(individual_report_files) - 1: final_report_content_parts.append("===")
                    except Exception as e:
                        error_msg = f"Phase 4 Error: Could not read individual report '{report_filename}'. Error: {e}"
                        final_report_content_parts.append(f"--- Error reading report: {report_filename} (Error: {e}) ---")
                        yield RunResponse(run_id=self.run_id, event="aggregation_error", content=f"[DATA]: {json.dumps({'filename': report_filename, 'error': str(e)}, ensure_ascii=False)}")
            
            final_report_content = "".join(final_report_content_parts)
            timestamp = time.strftime("%Y%m%d%H%M%S")
            final_aggregated_report_name = f"{AGGREGATED_DEEP_DIVE_FILENAME_PREFIX}_{timestamp}.md"
            
            try:
                save_report_to_repository(report_name=final_aggregated_report_name, report_content=final_report_content)
                final_report_path_str = str(Path(SHARED_REPORTS_DIR) / final_aggregated_report_name)
                # Storing final report info in session_state might be useful
                self.session_state["phase_4_output_final_report_path"] = final_report_path_str
                self.session_state[WORKFLOW_CURRENT_PHASE_STATUS_KEY] = "phase_4_completed"
                await self._save_state_and_notify("phase_end", {"phase": 4, "status": "completed", "final_report_name": final_aggregated_report_name, "final_report_path": final_report_path_str})
                yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_completed, content=f"Security audit workflow completed. Final aggregated report: {final_aggregated_report_name} in {SHARED_REPORTS_DIR}.")
            except Exception as e:
                yield RunResponse(run_id=self.run_id, event=RunEvent.workflow_error, content=f"Phase 4 CRITICAL Error: Failed to save final aggregated report '{final_aggregated_report_name}'. Error: {e}", error=True)
                return
        elif start_at_phase > 4:
             yield RunResponse(run_id=self.run_id, event="workflow_already_completed_or_invalid_start_phase", content=f"[DATA]: {json.dumps({'start_at_phase': start_at_phase}, ensure_ascii=False)}")
        
        print(f"Workflow processing for session {self.session_id} finished for this run.")

    def run(
        self,
        initial_user_query: Optional[str] = None,
        images: Optional[List[Image]] = None,
        start_at_phase: int = 1,
        force_rerun_phases: Optional[List[int]] = None,
        target_tasks_for_phase3: Optional[List[str]] = None,
        inspect_phase_output: Optional[int] = None,
        inspect_all_session_state: bool = False,
        clear_cache_for_phases: Optional[List[int]] = None,
        clear_all_session_cache: bool = False
    ) -> RunResponse: # Playground likely expects a single RunResponse
        """Synchronous entry point for the workflow, compatible with Playground."""
        
        print(f"Synchronous SecurityAuditWorkflow.run() called for session {self.session_id}")
        
        all_events: List[RunResponse] = []
        final_status_content = "Workflow execution initiated."
        error_occurred = False

        async def _collect_events():
            nonlocal final_status_content, error_occurred
            async for event_chunk in self.stream_audit(
                initial_user_query=initial_user_query,
                images=images,
                start_at_phase=start_at_phase,
                force_rerun_phases=force_rerun_phases,
                target_tasks_for_phase3=target_tasks_for_phase3,
                inspect_phase_output=inspect_phase_output,
                inspect_all_session_state=inspect_all_session_state,
                clear_cache_for_phases=clear_cache_for_phases,
                clear_all_session_cache=clear_all_session_cache
            ):
                all_events.append(event_chunk)
                if event_chunk.event == RunEvent.workflow_completed:
                    final_status_content = event_chunk.content or "Workflow completed successfully."
                elif event_chunk.error:
                    final_status_content = event_chunk.content or "Workflow encountered an error."
                    error_occurred = True
                elif event_chunk.event == "phase_output_inspection" or event_chunk.event == "session_state_inspection":
                    # For inspection commands, the content of the inspection is the primary result
                    final_status_content = event_chunk.content or f"Inspection for {event_chunk.event} completed."
                    # We might want to return the inspection data directly here if Playground can handle it.
                    # For now, just setting a status.
                elif event_chunk.event == "cache_cleared" or event_chunk.event == "cache_cleared_for_phases":
                    final_status_content = event_chunk.content or "Cache operation completed."

        # Run the async stream_audit method
        # Using asyncio.run() can sometimes cause issues if an event loop is already running (e.g., in FastAPI/Playground).
        # A more robust way in an async framework is to await it if the calling context is async,
        # or use asyncio.create_task if the framework manages the loop.
        # However, `Playground` seems to call a synchronous `run`.
        # If `asyncio.run()` causes issues, this might need `nest_asyncio` or a different approach
        # for integrating async logic into a sync call within an async environment.
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 事件循环已在运行（如FastAPI），直接创建任务并等待
                task = loop.create_task(_collect_events())
                loop.run_until_complete(task)
            else:
                loop.run_until_complete(_collect_events())
        except RuntimeError as e:
            if "cannot call run() when an event loop is running" in str(e) or "asyncio.run() cannot be called from a running event loop" in str(e):
                print(f"RuntimeError with asyncio.run: {e}. This often happens when calling sync `run` from an async framework like FastAPI.")
                print("Consider making the Playground endpoint call an async method directly or use nest_asyncio.")
                final_status_content = "Error: Workflow async execution issue within sync call."
                error_occurred = True
            else:
                raise # Re-raise other RuntimeErrors
        
        # Playground likely expects a single RunResponse. 
        # We can return a summary or the last significant event.
        # If an inspection happened, that data is in `all_events`.
        # For now, return a general status.
        final_event_type = "workflow_error" if error_occurred else "workflow_completed"
        if not all_events: # If _collect_events didn't run or yield, e.g. due to immediate return from stream_audit
            if inspect_phase_output is not None or inspect_all_session_state or clear_all_session_cache or clear_cache_for_phases:
                 final_status_content = "Control command processed (no async events to collect)."
                 final_event_type = RunEvent.workflow_event # Or a custom event for control commands
            else:
                final_status_content = "Workflow did not produce any events (check parameters and control flow)."
                final_event_type = RunEvent.workflow_warning

        return RunResponse(
            run_id=self.run_id if hasattr(self, 'run_id') else self.session_id, # Ensure run_id is available
            event=final_event_type,
            content=final_status_content,
            data={"all_collected_events_count": len(all_events)} # Optionally pass all_events if needed, but can be large
        )

# Example of how this workflow might be run with control parameters
async def main_workflow_runner():
    # --- Setup for a persistent session ---
    session_id_for_run = "my_persistent_audit_session_001"
    # Configure SQLite storage for session state persistence
    from agno.storage.sqlite import SqliteStorage
    workflow_storage = SqliteStorage(db_file="workflow_sessions.db", table_name="security_audit_sessions")

    print(f"Shared reports will be in: {os.path.abspath(SHARED_REPORTS_DIR)}")
    print(f"Workflow session state DB: workflow_sessions.db (table: security_audit_sessions)")

    # Instantiate workflow with session_id and storage
    audit_workflow = SecurityAuditWorkflow(
        session_id=session_id_for_run,
        storage=workflow_storage,
        user_id="test_interactive_user"
    )
    
    # --- Example Scenarios ---

    # Scenario 1: Fresh run from the beginning
    print("\n--- SCENARIO 1: Fresh run from Phase 1 ---")
    test_query_s1 = "Audit our new Python web service for common vulnerabilities."
    async for chunk in audit_workflow.stream_audit(initial_user_query=test_query_s1, start_at_phase=1):
        # print(f"[Run 1 Log] Event: {chunk.event}, Content: {chunk.content or ''}, Data: {chunk.data}")
        if chunk.event == RunEvent.workflow_completed: print(f"WORKFLOW COMPLETED: {chunk.content}")
        elif chunk.error: print(f"WORKFLOW ERROR: {chunk.content}")


    # Scenario 2: Inspect Phase 2 output (assuming Scenario 1 ran and cached it)
    print("\n--- SCENARIO 2: Inspect Phase 2 (Audit Plan) Output ---")
    async for chunk in audit_workflow.stream_audit(inspect_phase_output=2): # session_id is implicit via instance
        if chunk.event == "phase_output_inspection":
            print(f"Inspect Result for Phase {chunk.data.get('phase')}: {chunk.data.get('cached_data')}")

    # Scenario 3: Run only specific tasks from Phase 3 (assuming plan exists from Scenario 1)
    # First, let's imagine the plan file (e.g., "AttackSurfaceInvestigationPlan_whitebox.md") content is:
    # - [ ] Task Alpha: Check for XSS
    # - [ ] Task Beta: Review dependencies
    # - [ ] Task Gamma: SQL Injection tests
    print("\n--- SCENARIO 3: Run specific tasks ('Task Alpha', 'Task Gamma') from Phase 3 plan ---")
    # Note: The task strings must exactly match the line in the plan file (excluding leading/trailing whitespace for matching, but provide full line).
    # This is a simplified matching. A more robust system might use task IDs.
    # For this example, we assume these are the raw lines.
    specific_tasks = ["- [ ] Task Alpha: Check for XSS", "- [ ] Task Gamma: SQL Injection tests"]
    async for chunk in audit_workflow.stream_audit(start_at_phase=3, target_tasks_for_phase3=specific_tasks):
        # print(f"[Run 3 Log] Event: {chunk.event}, Content: {chunk.content or ''}, Data: {chunk.data}")
        if chunk.event == "task_completed_in_plan": print(f"TASK COMPLETED: {chunk.data.get('task')}")
        if chunk.event == RunEvent.workflow_completed: print(f"WORKFLOW COMPLETED (after targeted tasks): {chunk.content}")


    # Scenario 4: Force rerun Phase 2, then continue to Phase 3 & 4
    # This would regenerate the plan, potentially affecting Phase 3.
    # The initial query might be needed again if phase 2 depends on it and it wasn't in session state.
    print("\n--- SCENARIO 4: Force rerun Phase 2, then proceed ---")
    test_query_s4 = "Re-audit the Python web service, focusing on auth module this time." # Potentially new query for re-plan
    async for chunk in audit_workflow.stream_audit(initial_user_query=test_query_s4, start_at_phase=2, force_rerun_phases=[2]):
        # print(f"[Run 4 Log] Event: {chunk.event}, Content: {chunk.content or ''}, Data: {chunk.data}")
        if chunk.event == RunEvent.workflow_completed: print(f"WORKFLOW COMPLETED (after Phase 2 rerun): {chunk.content}")
    
    # Scenario 5: Clear cache for phase 1 and 2, then inspect all session state
    print("\n--- SCENARIO 5: Clear cache for Phase 1 & 2, then inspect state ---")
    async for chunk in audit_workflow.stream_audit(clear_cache_for_phases=[1, 2]):
        if chunk.event == "cache_cleared_for_phases": print(f"CACHE CLEARED: {chunk.content}")
    
    async for chunk in audit_workflow.stream_audit(inspect_all_session_state=True):
        if chunk.event == "session_state_inspection":
            import json
            print(f"Full Session State Inspection: {json.dumps(chunk.data.get('session_state'), indent=2)}")


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = Path(current_dir).parent.parent 
    sys_path_to_add = str(project_root)
    if sys_path_to_add not in sys.path:
         sys.path.insert(0, sys_path_to_add)
    
    vulnagent8_parent = Path(current_dir).parent
    if str(vulnagent8_parent) not in sys.path:
        sys.path.insert(0, str(vulnagent8_parent))

    if '../..' not in sys.path: 
        sys.path.append(os.path.join(os.path.dirname(__file__), '../..')) 
    
    import sys
    asyncio.run(main_workflow_runner()) 