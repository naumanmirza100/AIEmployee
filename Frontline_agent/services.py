import requests

# Base URL of your Node.js PayPerProject API
PAYPERPROJECT_API = "http://localhost:3000"

def get_all_projects():
    """
    Returns a list of all projects from PayPerProject API
    """
    try:
        response = requests.get(f"{PAYPERPROJECT_API}/projects")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print("Error connecting to PayPerProject API:", e)
        return []

def get_project_info(project_id):
    """
    Returns details of a single project by its ID
    """
    try:
        response = requests.get(f"{PAYPERPROJECT_API}/projects/{project_id}")
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching project {project_id}:", e)
        return None

def answer_project_question(question, project_id):
    """
    This function reads a user question and returns an answer about a project.
    question: string (e.g., "What is the status of project 1?")
    project_id: int (the ID of the project in your PayPerProject database)
    """
    project = get_project_info(project_id)  # fetch project info from your database
    if not project:
        return "Project not found."

    question = question.lower()  # make it easier to check words

    if "status" in question:
        return f"The project '{project['title']}' is currently {project['status']}."
    elif "budget" in question:
        return f"The budget for '{project['title']}' is between {project['budget_min']} and {project['budget_max']}."
    elif "deadline" in question:
        return f"The deadline for '{project['title']}' is {project['deadline']}."
    elif "priority" in question:
        return f"The project '{project['title']}' has {project['priority']} priority."
    elif "manager" in question or "project manager" in question:
        return f"The project manager for '{project['title']}' is {project['project_manager_id']}."
    elif "description" in question:
        return f"Description: {project['description']}"
    else:
        return "Sorry, I cannot answer that question yet."
