import os
from agno.tools import tool

# Define a shared directory within the container for reports
# Ensure this path is accessible and writable by the agent's execution environment.
SHARED_REPORTS_DIR = "/app/shared_reports" 

@tool
def save_report_to_repository(report_content: str, report_name: str = "environment_analysis_report.md") -> str:
    """
    Saves the provided report content to a shared repository (file system).
    Raises standard OS/IO exceptions if saving fails (e.g., PermissionError, OSError).

    Args:
        report_content (str): The content of the report to be saved.
        report_name (str): The name of the file to save the report as (e.g., 'environment_analysis_report.md').
                           Defaults to 'environment_analysis_report.md'.

    Returns:
        str: A message indicating success.
    """
    # No explicit try-except for common IO errors; let them propagate.
    # Agno's tool handling mechanism should catch these and inform the LLM.
    if not os.path.exists(SHARED_REPORTS_DIR):
        os.makedirs(SHARED_REPORTS_DIR) # This can raise OSError if it fails
        print(f"Created directory: {SHARED_REPORTS_DIR}")

    file_path = os.path.join(SHARED_REPORTS_DIR, report_name)
    
    with open(file_path, "w", encoding="utf-8") as f: # This can raise various IOErrors
        f.write(report_content)
    
    success_message = f"Report '{report_name}' successfully saved to repository at {file_path}."
    print(success_message)
    return success_message

@tool
def read_report_from_repository(report_name: str = "environment_analysis_report.md") -> str:
    """
    Reads a report from the shared repository (file system).
    Raises FileNotFoundError if the report_name is not found.
    Raises other standard OS/IO exceptions if reading fails.

    Args:
        report_name (str): The name of the report file to read (e.g., 'environment_analysis_report.md').
                           Defaults to 'environment_analysis_report.md'.

    Returns:
        str: The content of the report.
    """
    # No explicit try-except for common IO errors beyond FileNotFoundError; let them propagate.
    file_path = os.path.join(SHARED_REPORTS_DIR, report_name)
    
    if not os.path.exists(file_path):
        # Raise FileNotFoundError, which is standard and more informative than a custom string.
        raise FileNotFoundError(f"Report '{report_name}' not found in repository at {file_path}.")
        
    with open(file_path, "r", encoding="utf-8") as f: # This can raise various IOErrors
        report_content = f.read()
    
    print(f"Successfully read report '{report_name}' from repository.")
    return report_content

if __name__ == '__main__':
    # Example Usage (for testing the tools directly)
    print("Testing repository tools...")
    
    # Test save
    test_content = "# Test Report\\n\\nThis is a test report content.\\nHello World!"
    save_result = ""
    try:
        save_result = save_report_to_repository(report_content=test_content, report_name="test_report.md")
        print(f"Save test result: {save_result}")
    except Exception as e:
        print(f"Save test failed: {e}")

    # Test read (successful)
    if "successfully saved" in save_result:
        try:
            read_result_success = read_report_from_repository(report_name="test_report.md")
            print(f"Read test (success) result content:\\n{read_result_success[:100]}...") # Print first 100 chars
        except Exception as e:
            print(f"Read test (success) failed: {e}")

    # Test read (file not found)
    try:
        read_result_not_found = read_report_from_repository(report_name="non_existent_report.md")
        print(f"Read test (not found) result: {read_result_not_found}")
    except FileNotFoundError as e:
        print(f"Read test (not found) correctly raised FileNotFoundError: {e}")
    except Exception as e:
        print(f"Read test (not found) failed with unexpected error: {e}")

    # Clean up test file
    test_file_path = os.path.join(SHARED_REPORTS_DIR, "test_report.md")
    if os.path.exists(test_file_path):
        try:
            os.remove(test_file_path)
            print(f"Cleaned up {test_file_path}")
        except Exception as e:
            print(f"Error cleaning up {test_file_path}: {e}") 