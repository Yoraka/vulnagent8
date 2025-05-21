from textwrap import dedent
from typing import Optional

from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from agno.models.xai import xAI
from agno.storage.agent.postgres import PostgresAgentStorage
from agno.tools.shell import ShellTools
from agno.tools.file import FileTools
from agno.utils.pprint import pprint_run_response

from db.session import db_url

# Hardcoded workspace root path
HARDCODED_WORKSPACE_PATH = "/data/mall_code" # 注意：在Windows上路径分隔符通常是 \\ 或 /

def get_local_tool_tester_agent(
    model_id: str = "qwen/qwen3-235b-a22b", # Using a default free model
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    debug_mode: bool = True,
) -> Agent:
    """
    Creates an agent designed as a white-box security auditing expert.
    It uses ShellTools and FileTools to analyze code, configurations, and system states.
    It's instructed to operate within a hardcoded workspace path for file/shell operations
    when relative paths are implied, which can represent a target system or codebase.
    """

    # Initialize ShellTools
    shell_tools = ShellTools()

    # Initialize FileTools
    file_tools = FileTools()

    additional_context = ""
    if user_id:
        additional_context += "<context>"
        additional_context += f"You are interacting with the user: {user_id}"
        additional_context += "</context>"

    agent_description = dedent(f"""\
        You are a sophisticated white-box security auditing expert. 
        Your purpose is to analyze provided code, configurations, and system states for security vulnerabilities and best practice deviations. 
        You are equipped with ShellTools and FileTools to inspect files, directories, and execute commands within a designated environment.

        Operational Environment for Tools:
        - Your primary designated operational directory for relative path commands (shell or file operations) is {HARDCODED_WORKSPACE_PATH}. This path simulates the root of the codebase or system you are auditing.
        - When a user provides a command or requests a file operation, if they specify an absolute path, you MUST respect and use that path.
        - If no absolute path is given for a path-dependent command, assume operations are relative to {HARDCODED_WORKSPACE_PATH}.
        - Examples:
            - 'analyze the configuration file app.conf' -> implies reading {HARDCODED_WORKSPACE_PATH}/app.conf
            - 'check permissions in /var/log' -> implies using shell tools to inspect /var/log.
            - 'list all .js files in the project' -> implies searching within {HARDCODED_WORKSPACE_PATH}
        """)

    agent_instructions = [
        "Assume the role of a white-box security auditor. Your goal is to identify potential security weaknesses.",
        "Carefully interpret user requests to determine which tool (Shell or File) and what specific commands or file paths are needed for your security analysis.",
        f"For ShellTools and FileTools, if a path is relative, assume it is relative to {HARDCODED_WORKSPACE_PATH} (the root of the system/codebase under audit). Always prefer user-provided absolute paths if they are given for a specific target outside this primary workspace.",
        "When listing files or directory contents as part of an audit, aim for detailed and permission-aware listings (e.g., 'ls -lha').",
        "When asked to analyze code or configurations, use FileTools to read the content, then provide your security assessment.",
        "If you identify potential vulnerabilities (e.g., insecure permissions, hardcoded secrets, outdated dependencies, common CVE patterns in code), clearly state the finding, the potential risk, and suggest a remediation.",
        "If a user asks you to perform a potentially destructive operation (e.g., delete files, modify configurations), first state the potential impact and ask for explicit confirmation before proceeding.",
        "Provide clear, precise feedback on the outcome of your operations and your audit findings.",
        "Reference previous interactions and findings in the current session to build a comprehensive audit picture. Maintain conversation continuity."
    ]

    return Agent(
        name="LocalSecurityAuditor",
        agent_id="local_security_auditor_v1",
        user_id=user_id,
        session_id=session_id,
        model=xAI(id=model_id),
        tools=[shell_tools, file_tools],
        storage=PostgresAgentStorage(table_name="local_tool_tester_sessions", db_url=db_url),
        description=agent_description,
        instructions=agent_instructions,
        additional_context=additional_context,
        debug_mode=debug_mode,
        show_tool_calls=True,
        markdown=True,
        add_history_to_messages=True,
        num_history_responses=10,
        read_chat_history=True
    )

# --- Example Usage (optional, for direct script execution testing) ---
async def main():
    print("--- Local Tool Tester Agent Example ---")
    tester_agent = get_local_tool_tester_agent()

    prompts = [
        # ShellTool tests
        "Show me the contents of the /app directory using shell commands.",
        f"Using shell, list what's inside {HARDCODED_WORKSPACE_PATH}",
        "Run 'echo hello' with shell tools.",
        # FileTool tests
        f"Using file tools, list files in {HARDCODED_WORKSPACE_PATH}",
        f"Create a file named 'test_from_agent.txt' in {HARDCODED_WORKSPACE_PATH} with content 'Hello from FileTools!'",
        f"Read the file '{HARDCODED_WORKSPACE_PATH}/test_from_agent.txt'",
    ]

    for i, prompt_text in enumerate(prompts):
        print(f"\n--- Prompt {i+1}: {prompt_text} ---")
        await pprint_run_response(tester_agent, prompt_text)

    print("\n--- End of Example ---")

if __name__ == "__main__":
    print(f"Initializing LocalToolTester Agent to operate in: {HARDCODED_WORKSPACE_PATH}")
    print("This agent will use ShellTools and FileTools to interact with the local filesystem.")
    print("Make sure the path exists and the agent has permissions if you ask it to write files or make changes.")

    import asyncio
    asyncio.run(main()) 