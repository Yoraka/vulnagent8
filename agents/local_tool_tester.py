from textwrap import dedent
from typing import Optional

from agno.agent import Agent
from agno.models.openrouter import OpenRouter
from agno.models.xai import xAI
from agno.tools.shell import ShellTools
from agno.tools.file import FileTools
from agno.utils.pprint import pprint_run_response

# Hardcoded workspace root path
HARDCODED_WORKSPACE_PATH = "/data/mall_code" # 注意：在Windows上路径分隔符通常是 \\ 或 /

def get_local_tool_tester_agent(
    model_id: str = "qwen/qwen3-235b-a22b", # Using a default free model
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    debug_mode: bool = True,
) -> Agent:
    """
    Creates an agent designed to test local tools: ShellTools and FileTools.
    It's instructed to operate within a hardcoded workspace path for file/shell operations
    when relative paths are implied.
    """

    # Initialize ShellTools
    shell_tools = ShellTools()

    # Initialize FileTools
    # Not setting base_dir here to allow testing with absolute paths.
    # Agent instructions should guide its use of paths.
    file_tools = FileTools(
        # save_files=True, read_files=True, list_files=True are defaults
    )

    agent_description = dedent(f"""\
        You are a local operations testing agent equipped with ShellTools and FileTools.

        Shell Operations:
        - Your primary designated operational directory for relative path commands is {HARDCODED_WORKSPACE_PATH}.
        - When a user provides a command, if they specify an absolute path, you MUST respect and use that path.
        - If no absolute path is given for a path-dependent shell command, assume operations are relative to {HARDCODED_WORKSPACE_PATH}.
        - Examples:
            - 'list files' -> should interpret as 'ls {HARDCODED_WORKSPACE_PATH}' or similar.
            - 'list files in /tmp' -> should execute 'ls /tmp'.

        File Operations (using FileTools):
        - You can read, write, and list files.
        - If a path is not absolute, assume it's relative to {HARDCODED_WORKSPACE_PATH}.
        - Example: 'read the file named my_document.txt' -> try reading {HARDCODED_WORKSPACE_PATH}/my_document.txt
        - Example: 'save "hello" to /app/test.txt' -> save to /app/test.txt
        """)

    agent_instructions = [
        "Carefully interpret user requests to determine which tool (Shell or File) is most appropriate.",
        f"For ShellTools and FileTools, if a path is relative, assume it is relative to {HARDCODED_WORKSPACE_PATH}. Always prefer user-provided absolute paths.",
        "When using ShellTools to list files (e.g., with 'ls' or 'dir'), always include options for detailed, human-readable output (like 'ls -lah').",
        "Confirm critical operations, especially those that are destructive (e.g., removing files).",
        "Provide clear feedback on the outcome of operations."
    ]

    return Agent(
        name="LocalToolTester",
        agent_id="local_tool_tester_v2",
        user_id=user_id,
        session_id=session_id,
        model=xAI(id=model_id),
        tools=[shell_tools, file_tools],
        description=agent_description,
        instructions=agent_instructions,
        debug_mode=debug_mode,
        show_tool_calls=True,
        markdown=True,
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