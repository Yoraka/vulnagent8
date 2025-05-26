import os
from pathlib import Path
from typing import Optional, List

# Removed: from agno.tools import Tool

class ListDirectoryTreeTool: # Renamed and no inheritance
    """
    Tool to list directory structures in a tree-like format.
    The actual name and description used by the LLM are set when this tool
    is wrapped with Function.from_callable and those attributes are copied.
    """
    # Attributes for potential direct registration if not wrapped by Function.from_callable,
    # or for reference. The wrapper approach is preferred for consistency here.
    name: str = "list_directory_tree"
    description: str = (
        "Lists the file and directory structure in a tree-like format, starting "
        "from the specified target_path (relative to the tool's pre-configured base_dir) "
        "up to a given recursion depth. Args: target_path (str), max_depth (int, default 2)."
    )

    def __init__(self, base_dir: Optional[str] = None):
        # super().__init__(**kwargs) # Removed super() call as there's no base class
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        if not self.base_dir.exists() or not self.base_dir.is_dir():
            # This warning is helpful for debugging tool instantiation.
            print(f"Warning: ListDirectoryTreeTool base_dir '{self.base_dir}' does not exist or is not a directory at instantiation.")
            # The __call__ method will perform a more robust check at runtime.

    def _build_tree(self, dir_path: Path, prefix: str, current_depth: int, max_depth: int, tree_lines: List[str]):
        """Helper recursive function to build the directory tree."""
        if current_depth > max_depth and max_depth != -1:
            return

        try:
            # Sort order: directories first (by is_file() being False), then files, then alphabetically.
            contents = sorted(list(dir_path.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            tree_lines.append(f"{prefix}└── [Error: Permission Denied to read {dir_path}]")
            return
        except FileNotFoundError: # Should ideally not happen if initial checks pass
            tree_lines.append(f"{prefix}└── [Error: Directory Not Found during traversal: {dir_path}]")
            return

        pointers = ['├── '] * (len(contents) - 1) + ['└── ']
        for pointer, path_item in zip(pointers, contents):
            entry_name = path_item.name
            if path_item.is_dir():
                entry_name += "/"
            tree_lines.append(f"{prefix}{pointer}{entry_name}")

            if path_item.is_dir():
                # Corrected prefix for recursive calls
                # extension = '    ' if pointer == '├── ' else '│   ' # This logic for │ is tricky with just prefix
                # Simpler: always extend with 4 spaces for visual indent, relying on the pointers for structure.
                # The choice of '│   ' or '    ' depends on whether it's the *last* item at the *current* level,
                # which is handled by the pointer. The prefix for the next level is consistent.
                next_prefix = prefix + ('    ' if pointer == '└── ' else '│   ')

                if max_depth == -1 or current_depth < max_depth:
                    self._build_tree(path_item, next_prefix, current_depth + 1, max_depth, tree_lines)

    def __call__(self, target_path: str, max_depth: int = 2) -> str:
        """
        Lists the file and directory structure in a tree-like format.
        This method is intended to be wrapped by Function.from_callable.
        """
        if not isinstance(max_depth, int):
            return "Error: max_depth must be an integer."
        if max_depth < -1: # 0 is shallowest, -1 is infinite
            return "Error: max_depth cannot be less than -1."

        try:
            if not self.base_dir.exists() or not self.base_dir.is_dir():
                return f"Error: Tool's base directory '{self.base_dir}' is invalid or not accessible at call time."

            # Resolve the absolute path securely against the base_dir
            # Path.resolve() handles '..' and symlinks to give the canonical path.
            absolute_target_path = (self.base_dir / target_path).resolve()

            # Security check: Ensure the resolved path is still within or same as the base_dir
            # This prevents `target_path` like '../../../../etc/passwd' from escaping `base_dir`
            if not str(absolute_target_path).startswith(str(self.base_dir.resolve())):
                 return f"Error: target_path '{target_path}' resolves to '{absolute_target_path}', which is outside the configured base directory '{self.base_dir.resolve()}'."

            if not absolute_target_path.exists():
                return f"Error: Target path '{target_path}' (resolved to '{absolute_target_path}') does not exist."
            if not absolute_target_path.is_dir():
                return f"Error: Target path '{target_path}' (resolved to '{absolute_target_path}') is not a directory."

            # Start tree with the resolved target directory name
            tree_lines: List[str] = [f"{absolute_target_path.name}/"]
            # Initial call to _build_tree for the contents of absolute_target_path
            self._build_tree(absolute_target_path, "", 0, max_depth, tree_lines)
            return "\n".join(tree_lines)

        except Exception as e:
            # Log the full exception for debugging if a logger is available
            # For now, return a generic error with the exception message.
            return f"An unexpected error occurred in list_directory_tree: {str(e)}"

# Keep the __main__ for direct testing if needed, but it's not part of the tool's runtime for Agno.
if __name__ == '__main__':
    current_script_dir = Path(__file__).parent
    # Test project relative to the script's parent directory (e.g., vulnagent8/)
    test_proj_root_name = "test_project_tree_tool"
    test_proj_base = current_script_dir.parent / test_proj_root_name

    if test_proj_base.exists():
        import shutil
        shutil.rmtree(test_proj_base)
    test_proj_base.mkdir(parents=True, exist_ok=True)

    (test_proj_base / "file1.txt").write_text("content1")
    (test_proj_base / "file2.py").write_text("content2")
    subfolder1 = test_proj_base / "subfolder1"
    subfolder1.mkdir()
    (subfolder1 / "s1_file1.txt").write_text("s1_content1")
    s1_subfolder = subfolder1 / "s1_subfolder"
    s1_subfolder.mkdir()
    (s1_subfolder / "s1_s1_file.txt").write_text("s1_s1_content")
    (s1_subfolder / "s1_s2_file.json").write_text("{}")
    subfolder2 = test_proj_base / "subfolder2"
    subfolder2.mkdir()
    (subfolder2 / "s2_file1.yml").write_text("s2_content1")
    (test_proj_base / ".hiddenfile").write_text("hidden")


    print(f"Test project base directory for tool: {test_proj_base.parent.resolve()}")
    print(f"Target path for tool: {test_proj_root_name}")

    # Instantiate the tool, base_dir is one level up from where test_project_tree_tool is
    tool_instance = ListDirectoryTreeTool(base_dir=str(test_proj_base.parent))

    # Mimic Function.from_callable wrapping for testing name and description
    effective_tool_name = ListDirectoryTreeTool.name_for_llm
    effective_tool_description = ListDirectoryTreeTool.description_for_llm
    print(f"\n--- Tool: {effective_tool_name} ---")
    print(f"Desc: {effective_tool_description}")

    print("\n--- Tree for '.' relative to test_project_root (depth 0) ---")
    # If base_dir is vulnagent8/, and target is test_project_tree_tool,
    # then target_path="." inside test_project_tree_tool means we list test_project_tree_tool itself.
    # To list contents of test_project_tree_tool, target_path should be test_project_tree_tool
    print(tool_instance(target_path=test_proj_root_name, max_depth=0))

    print("\n--- Tree for '.' relative to test_project_root (depth 1) ---")
    print(tool_instance(target_path=test_proj_root_name, max_depth=1))

    print("\n--- Tree for '.' relative to test_project_root (depth 2) ---")
    print(tool_instance(target_path=test_proj_root_name, max_depth=2))

    print("\n--- Tree for subfolder1 inside test_project_root (depth 0) ---")
    print(tool_instance(target_path=f"{test_proj_root_name}/subfolder1", max_depth=0))
    
    print("\n--- Tree for subfolder1 inside test_project_root (depth 1, unlimited for sub-contents) ---")
    # This is effectively max_depth=1 for the subfolder1 contents relative to subfolder1.
    print(tool_instance(target_path=f"{test_proj_root_name}/subfolder1", max_depth=1))

    print("\n--- Tree for test_project_root (depth -1, unlimited) ---")
    print(tool_instance(target_path=test_proj_root_name, max_depth=-1))

    # ... (other test cases from before can be adapted) ...
    # Clean up
    # import shutil
    # shutil.rmtree(test_proj_base) 