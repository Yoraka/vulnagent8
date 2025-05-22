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
from agents.attack_surface_identification_agent import ATTACK_SURFACE_IDENTIFICATION_AGENT_CONFIG

# Import the new repository tools
from tools.report_repository_tools import save_report_to_repository, read_report_from_repository

SECURITY_AUDIT_WORKFLOW_ID = "security_audit_workflow_v2_repository"

class SecurityAuditWorkflow(Workflow):
    """
    A workflow that first runs an environment perception agent and then an attack
    surface identification agent. The first agent saves its report to a file-based
    repository, and the second agent can optionally read from it.
    Both agents have enable_user_memories=False to avoid Grok API issues.
    """

    id = SECURITY_AUDIT_WORKFLOW_ID
    name = "Security Audit Workflow (with Repository)"
    description = (
        "Orchestrates an environment perception agent followed by an attack "
        "surface identification agent. Uses a file-based repository for report sharing."
    )

    env_perception_agent: Agent
    attack_surface_agent: Agent
    # shared_memory: Memory # No longer using shared memory in this way

    def __init__(self, session_id: str, **kwargs):
        super().__init__(session_id=session_id, **kwargs)

        # Memory related setup is removed as enable_user_memories will be False for both agents
        # memory_db = SqliteMemoryDb(table_name=f"workflow_memory_{session_id.replace('-', '_')}", db_file=":memory:") 
        # self.shared_memory = Memory(db=memory_db)
        # self.shared_memory.clear()
        # workflow_user_id = f"workflow_user_{session_id}"

        # Environment Perception Agent
        env_model_id_str = ENVIRONMENT_PERCEPTION_AGENT.model_id if ENVIRONMENT_PERCEPTION_AGENT.model_id else "grok-3-beta"
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

        # Attack Surface Identification Agent
        attack_model_id_str = ATTACK_SURFACE_IDENTIFICATION_AGENT_CONFIG.model_id if ATTACK_SURFACE_IDENTIFICATION_AGENT_CONFIG.model_id else "grok-3-beta"
        attack_model_instance = get_model_instance(attack_model_id_str)
        
        # Combine existing tools with the new read_report_from_repository tool
        attack_surface_tools = list(ATTACK_SURFACE_IDENTIFICATION_AGENT_CONFIG.tools) # Create a mutable copy
        attack_surface_tools.append(read_report_from_repository)

        self.attack_surface_agent = Agent(
            agent_id=ATTACK_SURFACE_IDENTIFICATION_AGENT_CONFIG.agent_id,
            name=ATTACK_SURFACE_IDENTIFICATION_AGENT_CONFIG.name,
            description=ATTACK_SURFACE_IDENTIFICATION_AGENT_CONFIG.description,
            instructions=ATTACK_SURFACE_IDENTIFICATION_AGENT_CONFIG.instructions, 
            tools=attack_surface_tools, # MODIFIED: Added repository tool
            model=attack_model_instance, 
            # memory=self.shared_memory, 
            # user_id=workflow_user_id, 
            enable_user_memories=False, # Kept False
            show_tool_calls=kwargs.get("debug_mode", False),
            debug_mode=kwargs.get("debug_mode", False),
            markdown=True 
        )

    async def stream_audit(self, initial_message: str, images: Optional[List[Image]] = None) -> AsyncIterator[RunResponse]:
        """
        Runs the security audit workflow.
        Both agents will now run in streaming mode.
        The Environment Perception agent will stream its findings and then save its report as a final action.
        The Attack Surface agent streams and can optionally read the report from the repository after its own audit.
        """
        print(f"[{self.name} - {self.session_id}] Starting {self.env_perception_agent.name} (STREAMING, will save report as final action) with initial message: {initial_message[:100]}... Images provided: {images is not None}")

        # Run EnvironmentPerceptionAgent STREAMING.
        # Its instructions include calling save_report_to_repository tool as its final action.
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
            # Yield a response to indicate completion if stream was empty, so UI knows.
            yield RunResponse(
                run_id=self.env_perception_agent.run_id if hasattr(self.env_perception_agent, 'run_id') else self.session_id,
                agent_id=self.env_perception_agent.agent_id,
                session_id=self.session_id,
                content=f"**{self.env_perception_agent.name} Analysis (Streaming) Complete (Stream was empty). Agent was instructed to save report as final action.**"
            )
        
        print(f"[{self.name} - {self.session_id}] DEBUG: Proceeding to {self.attack_surface_agent.name}.")

        # MODIFIED: Second agent's initial message is aligned with its new two-phase instructions.
        # Emphasizes full independent audit first, then optional validation with factual deployment report.
        # AND prepends the original user input from the first stage.
        
        original_user_input_header = "Original user-provided context for the first-stage (Deployment Architecture) analysis:\n---\n"
        original_user_input_content = initial_message # This is the user input to the first agent
        images_provided_note = "\n(Note: Visual context, such as architecture diagrams, was also provided in the first stage.)" if images else ""
        separator = "\n---\n\n"

        # Current detailed instructions for the second agent
        attack_agent_specific_instructions = (
            "Your primary mission is to conduct an exhaustive, independent, and proactive attack surface identification and code security audit for the target project. "
            "You must first complete your own comprehensive deep audit, identifying as many potential vulnerabilities as possible based on your direct analysis of all code and configuration files. "
            "After you have completed this thorough independent investigation and compiled your initial findings, you may optionally use the `read_report_from_repository` tool. "
            "If chosen, this tool will provide access to a purely factual Deployment Architecture Report (containing NO security pre-analysis or application dependency details). "
            "The SOLE purpose of accessing this deployment report at that later stage is to help you cross-verify and contextualize YOUR OWN PREVIOUSLY IDENTIFIED findings against the actual deployment topology (e.g., to confirm exposure paths or adjust risk for internal components). "
            "This deployment report MUST NOT guide your initial audit priorities, direct your investigation scope, or be used to find new vulnerabilities. "
            "Your core analysis and findings must stem entirely from your own independent and comprehensive auditing work in the first phase. "
            "Please refer to your detailed instructions for your two-phase autonomous auditing protocol."
        )

        attack_agent_initial_message = (
            f"{original_user_input_header}"
            f"{original_user_input_content}"
            f"{images_provided_note}"
            f"{separator}"
            f"{attack_agent_specific_instructions}"
        )
        
        print(f"[{self.name} - {self.session_id}] Starting {self.attack_surface_agent.name} (streaming). Initial message now includes original user input preamble.")
        
        attack_surface_stream: AsyncIterator[RunResponse] = await self.attack_surface_agent.arun(
            attack_agent_initial_message, 
            stream=True
        )
        
        stream_had_content = False
        async for chunk in attack_surface_stream:
            stream_had_content = True
            yield chunk

        if not stream_had_content:
            print(f"Warning: [{self.name} - {self.session_id}] Attack surface agent stream produced no content.")
            yield RunResponse(
                run_id=self.attack_surface_agent.run_id if hasattr(self.attack_surface_agent, 'run_id') else self.session_id, 
                agent_id=self.attack_surface_agent.agent_id,
                session_id=self.session_id,
                content="Attack surface agent stream was empty."
            )

if __name__ == "__main__":
    # This main block is for basic structural testing of the workflow, not full execution.
    # For full execution, ensure the agents, their instructions, and tools are correctly set up.
    test_session_id = "test_audit_workflow_repo_v1"
    
    # Mock agent configurations for basic testing if needed, or rely on actual imports
    # For this test, we assume the imported agent configs are sufficient for instantiation.
    
    print(f"Attempting to instantiate SecurityAuditWorkflow with ID: {SECURITY_AUDIT_WORKFLOW_ID}")
    try:
        workflow = SecurityAuditWorkflow(session_id=test_session_id, debug_mode=True)
        print(f"Workflow ID: {workflow.id}")
        print(f"Workflow Name: {workflow.name}")
        print(f"Workflow Description: {workflow.description}")
        print(f"Env Agent Model ID: {workflow.env_perception_agent.model.id}")
        print(f"Attack Agent Model ID: {workflow.attack_surface_agent.model.id}")
        # print(f"Shared Memory DB: {workflow.shared_memory.db}") # Memory removed
        print(f"Env Agent Tools: {[t.__name__ if hasattr(t, '__name__') else str(t) for t in workflow.env_perception_agent.tools]}")
        print(f"Attack Agent Tools: {[t.__name__ if hasattr(t, '__name__') else str(t) for t in workflow.attack_surface_agent.tools]}")
        print("\nSecurityAuditWorkflow instantiation appears successful for basic structural check.")
        print("For actual execution, integrate with FastAPI or use appropriate async runner with a full project context.")
    except Exception as e:
        print(f"Error during SecurityAuditWorkflow instantiation or basic check: {e}")
        import traceback
        traceback.print_exc()