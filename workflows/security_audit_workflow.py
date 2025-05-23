from agno.workflow import Workflow
from agno.agent import Agent
from agno.run.response import RunResponse
from typing import AsyncIterator, Iterator, Dict, Any, List, Optional
from agno.media import Image
# Removed Memory related imports as enable_user_memories will be False
# from agno.memory.v2.memory import Memory 
# from agno.memory.v2.db.sqlite import SqliteMemoryDb

# Import the utility function from its new location
from core.model_factory import get_model_instance 

from agents.environment_perception_agent import ENVIRONMENT_PERCEPTION_AGENT
# MODIFIED: Import the new AttackSurfacePlanningAgentForWhiteBox config
from agents.attack_surface_identification_agent import ATTACK_SURFACE_PLANNING_AGENT_CONFIG # This should now refer to the _v2_whitebox config

# Import the new repository tools
from tools.report_repository_tools import save_report_to_repository, read_report_from_repository

# MODIFIED: Update workflow ID to reflect white-box focus if desired, e.g., v4
SECURITY_AUDIT_WORKFLOW_ID = "security_audit_workflow_v4_whitebox_planning"

class SecurityAuditWorkflow(Workflow):
    """
    A workflow that first runs an environment perception agent and then an attack
    surface planning agent focused on white-box code review. The first agent saves 
    its deployment report, and the second agent reads it to create a detailed 
    code review plan, which it also saves.
    Both agents have enable_user_memories=False.
    """

    id = SECURITY_AUDIT_WORKFLOW_ID
    name = "Security Audit Workflow (Environment -> White-Box Code Review Planning)"
    description = (
        "Orchestrates an environment perception agent followed by an attack surface planning agent "
        "that generates a white-box code review plan. Uses a file-based repository for report and plan sharing."
    )

    env_perception_agent: Agent
    attack_planning_agent: Agent
    # shared_memory: Memory # No longer using shared memory in this way

    def __init__(self, session_id: str, **kwargs):
        super().__init__(session_id=session_id, **kwargs)

        # Define the new OpenRouter model ID
        # User confirmed model ID: google/gemini-flash-1.5-preview-0514
        # If another ID like google/gemini-2.5-flash-preview-05-20 is preferred, update this string.
        open_router_model_string = "openrouter/google/gemini-2.5-flash-preview-05-20"

        # Memory related setup is removed as enable_user_memories will be False for both agents
        # memory_db = SqliteMemoryDb(table_name=f"workflow_memory_{session_id.replace('-', '_')}", db_file=":memory:") 
        # self.shared_memory = Memory(db=memory_db)
        # self.shared_memory.clear()
        # workflow_user_id = f"workflow_user_{session_id}"

        # Environment Perception Agent
        # Use the new OpenRouter model ID, overriding any default in AgentConfig if necessary
        # env_model_id_str = ENVIRONMENT_PERCEPTION_AGENT.model_id if ENVIRONMENT_PERCEPTION_AGENT.model_id else open_router_model_string
        env_model_id_str = open_router_model_string # Directly set to the desired OpenRouter model
        env_model_instance = get_model_instance(env_model_id_str)
        
        # Combine existing tools with the new save_report_to_repository tool
        env_perception_tools = list(ENVIRONMENT_PERCEPTION_AGENT.tools) # Create a mutable copy
        env_perception_tools.append(save_report_to_repository)

        self.env_perception_agent = Agent(
            agent_id=ENVIRONMENT_PERCEPTION_AGENT.agent_id,
            name=ENVIRONMENT_PERCEPTION_AGENT.name,
            description=ENVIRONMENT_PERCEPTION_AGENT.description,
            instructions=ENVIRONMENT_PERCEPTION_AGENT.instructions,
            tools=env_perception_tools, # MODIFIED: Added repository tool
            model=env_model_instance, 
            # memory=self.shared_memory, 
            # user_id=workflow_user_id, 
            enable_user_memories=False, # Kept False
            show_tool_calls=kwargs.get("debug_mode", False),
            debug_mode=kwargs.get("debug_mode", False),
            markdown=True
        )

        # MODIFIED: Attack Surface Planning Agent setup
        planning_model_instance = get_model_instance(open_router_model_string)
        
        # Combine existing tools with BOTH read_report_from_repository and save_report_to_repository
        # as the planner reads one report and saves another.
        planning_agent_tools = list(ATTACK_SURFACE_PLANNING_AGENT_CONFIG.tools)
        planning_agent_tools.append(read_report_from_repository) 
        planning_agent_tools.append(save_report_to_repository) # Planner also saves its plan

        self.attack_planning_agent = Agent(
            # Ensure these use the _v2_whitebox config details
            agent_id=ATTACK_SURFACE_PLANNING_AGENT_CONFIG.agent_id, 
            name=ATTACK_SURFACE_PLANNING_AGENT_CONFIG.name,
            description=ATTACK_SURFACE_PLANNING_AGENT_CONFIG.description,
            instructions=ATTACK_SURFACE_PLANNING_AGENT_CONFIG.instructions,
            tools=planning_agent_tools,
            model=planning_model_instance,
            enable_user_memories=False,
            show_tool_calls=kwargs.get("debug_mode", False),
            debug_mode=kwargs.get("debug_mode", False),
            markdown=True
        )

    async def stream_audit(self, initial_message: str, images: Optional[List[Image]] = None) -> AsyncIterator[RunResponse]:
        """
        Runs the security audit workflow.
        1. Environment Perception agent streams and saves `environment_analysis_report.md`.
        2. Attack Surface Planning agent (white-box focus) streams, reads the first report, 
           creates `attack_surface_investigation_plan_whitebox.md`, and saves it.
        """
        print(f"[{self.name} - {self.session_id}] Starting {self.env_perception_agent.name} (STREAMING, will save report as final action) with initial message: {initial_message[:100]}... Images provided: {images is not None}")

        env_perception_stream: AsyncIterator[RunResponse] = await self.env_perception_agent.arun(
            initial_message,
            stream=True,
            images=images
        )

        env_stream_had_content = False
        async for chunk in env_perception_stream:
            env_stream_had_content = True
            yield chunk
        
        if env_stream_had_content:
            print(f"[{self.name} - {self.session_id}] {self.env_perception_agent.name} (STREAMING) complete. Agent should have saved its report as its final action.")
        else:
            print(f"Warning: [{self.name} - {self.session_id}] {self.env_perception_agent.name} (STREAMING) produced no content.")
            yield RunResponse(
                run_id=self.env_perception_agent.run_id if hasattr(self.env_perception_agent, 'run_id') else self.session_id,
                agent_id=self.env_perception_agent.agent_id,
                session_id=self.session_id,
                content=f"**{self.env_perception_agent.name} Analysis (Streaming) Complete (Stream was empty). Agent was instructed to save report as final action.**"
            )
        
        print(f"[{self.name} - {self.session_id}] DEBUG: Proceeding to {self.attack_planning_agent.name} ({ATTACK_SURFACE_PLANNING_AGENT_CONFIG.agent_id}).")

        original_user_input_header = "Original user-provided context for the overall security audit (for white-box code review planning):\n---\n"
        original_user_input_content = initial_message
        images_provided_note = "\n(Note: Visual context, such as architecture diagrams, was also provided in the first stage and may be relevant for contextualizing code review priorities.)" if images else ""
        separator = "\n---\n\n"

        # MODIFIED: Instructions for the AttackSurfacePlanningAgent (White-Box Focus)
        planning_agent_specific_instructions = (
            f"You are the {ATTACK_SURFACE_PLANNING_AGENT_CONFIG.name} ({ATTACK_SURFACE_PLANNING_AGENT_CONFIG.agent_id}). "
            "Your primary task is to create a detailed Attack Surface Investigation Plan specifically designed to guide a **white-box code review**. "
            "You will be provided with the original user input for the entire audit. "
            "As per your main instructions, your first step should be to use the `read_report_from_repository` tool to fetch the 'environment_analysis_report.md'. This report provides deployment context. "
            "Then, considering the original user input, the deployment context, and your extensive knowledge of common code vulnerabilities (e.g., OWASP Top 10), "
            "generate a comprehensive white-box code review plan. This plan should focus on identifying specific code areas (files, classes, methods, dependencies in pom.xml) and suggesting code review techniques. "
            f"Save your plan using `save_report_to_repository` as 'attack_surface_investigation_plan_whitebox.md'. "
            "Refer to your detailed agent instructions for the expected structure, content, and emphasis on code-level analysis."
        )

        planning_agent_initial_message = (
            f"{original_user_input_header}"
            f"{original_user_input_content}"
            f"{images_provided_note}"
            f"{separator}"
            f"{planning_agent_specific_instructions}"
        )
        
        print(f"[{self.name} - {self.session_id}] Starting {self.attack_planning_agent.name} (streaming). Initial message tailored for white-box code review planning.")
        
        attack_planning_stream: AsyncIterator[RunResponse] = await self.attack_planning_agent.arun(
            planning_agent_initial_message, 
            stream=True
        )
        
        stream_had_content = False
        async for chunk in attack_planning_stream:
            stream_had_content = True
            yield chunk

        if not stream_had_content:
            print(f"Warning: [{self.name} - {self.session_id}] {self.attack_planning_agent.name} stream produced no content.")
            yield RunResponse(
                run_id=self.attack_planning_agent.run_id if hasattr(self.attack_planning_agent, 'run_id') else self.session_id, 
                agent_id=self.attack_planning_agent.agent_id,
                session_id=self.session_id,
                content=f"{self.attack_planning_agent.name} stream was empty."
            )

if __name__ == "__main__":
    # This main block is for basic structural testing of the workflow, not full execution.
    # For full execution, ensure the agents, their instructions, and tools are correctly set up.
    test_session_id = "test_audit_workflow_whitebox_planning_v1"
    
    # Mock agent configurations for basic testing if needed, or rely on actual imports
    # For this test, we assume the imported agent configs are sufficient for instantiation.
    
    print(f"Attempting to instantiate SecurityAuditWorkflow with ID: {SECURITY_AUDIT_WORKFLOW_ID}")
    try:
        workflow = SecurityAuditWorkflow(session_id=test_session_id, debug_mode=True)
        print(f"Workflow ID: {workflow.id}")
        print(f"Workflow Name: {workflow.name}")
        print(f"Workflow Description: {workflow.description}")
        print(f"Env Agent Model ID: {workflow.env_perception_agent.model.id}")
        print(f"Attack Planning Agent Model ID: {workflow.attack_planning_agent.model.id} (Name: {workflow.attack_planning_agent.name})")
        # print(f"Shared Memory DB: {workflow.shared_memory.db}") # Memory removed
        print(f"Env Agent Tools: {[t.__name__ if hasattr(t, '__name__') else str(t) for t in workflow.env_perception_agent.tools]}")
        print(f"Attack Planning Agent Tools: {[t.__name__ if hasattr(t, '__name__') else str(t) for t in workflow.attack_planning_agent.tools]}")
        print("\nSecurityAuditWorkflow instantiation appears successful for basic structural check.")
        print("For actual execution, integrate with FastAPI or use appropriate async runner with a full project context.")
    except Exception as e:
        print(f"Error during SecurityAuditWorkflow instantiation or basic check: {e}")
        import traceback
        traceback.print_exc()