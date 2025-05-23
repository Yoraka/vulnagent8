import os
from agno.tools import tool

# Define a shared directory within the container for reports
# Ensure this path is accessible and writable by the agent's execution environment.
SHARED_REPORTS_DIR = "/app/shared_reports" 

@tool
def save_report_to_repository(report_content: str, report_name: str = "environment_analysis_report.md") -> str:
    """
    Saves the provided report content to a shared repository (file system).

    Args:
        report_content (str): The content of the report to be saved.
        report_name (str): The name of the file to save the report as (e.g., 'environment_analysis_report.md').
                           Defaults to 'environment_analysis_report.md'.

    Returns:
        str: A message indicating success or failure.
    """
    try:
        if not os.path.exists(SHARED_REPORTS_DIR):
            os.makedirs(SHARED_REPORTS_DIR)
            print(f"Created directory: {SHARED_REPORTS_DIR}")

        file_path = os.path.join(SHARED_REPORTS_DIR, report_name)
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        
        success_message = f"Report '{report_name}' successfully saved to repository at {file_path}."
        print(success_message)
        return success_message
    except Exception as e:
        error_message = f"Error saving report '{report_name}' to repository: {str(e)}"
        print(error_message)
        return error_message

@tool
def read_report_from_repository(report_name: str = "environment_analysis_report.md") -> str:
    """
    Reads a report from the shared repository (file system).

    Args:
        report_name (str): The name of the report file to read (e.g., 'environment_analysis_report.md').
                           Defaults to 'environment_analysis_report.md'.

    Returns:
        str: The content of the report, or an error message if the report is not found or an error occurs.
    """
    try:
        file_path = os.path.join(SHARED_REPORTS_DIR, report_name)
        
        if not os.path.exists(file_path):
            not_found_message = f"Report '{report_name}' not found in repository at {file_path}."
            print(not_found_message)
            return not_found_message
            
        with open(file_path, "r", encoding="utf-8") as f:
            report_content = f.read()
        
        print(f"Successfully read report '{report_name}' from repository.")
        return report_content
    except Exception as e:
        error_message = f"Error reading report '{report_name}' from repository: {str(e)}"
        print(error_message)
        return error_message

if __name__ == '__main__':
    # Example Usage (for testing the tools directly)
    print("Testing repository tools...")
    
    # Test save
    test_content = "# Test Report\n\nThis is a test report content.\nHello World!"
    save_result = save_report_to_repository(report_content=test_content, report_name="test_report.md")
    print(f"Save test result: {save_result}")

    # Test read (successful)
    if "successfully saved" in save_result:
        read_result_success = read_report_from_repository(report_name="test_report.md")
        print(f"Read test (success) result content:\n{read_result_success[:100]}...") # Print first 100 chars

    # Test read (file not found)
    read_result_not_found = read_report_from_repository(report_name="non_existent_report.md")
    print(f"Read test (not found) result: {read_result_not_found}")

    # Clean up test file
    test_file_path = os.path.join(SHARED_REPORTS_DIR, "test_report.md")
    if os.path.exists(test_file_path):
        os.remove(test_file_path)
        print(f"Cleaned up {test_file_path}") 