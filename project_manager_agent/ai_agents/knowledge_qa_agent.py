"""
Knowledge Q&A Agent
Answers questions about projects, provides information, and assists with queries.
This agent only provides descriptive answers - it does not perform actions.
"""

from .base_agent import BaseAgent
from typing import Dict, Optional, List
import json
import re


class KnowledgeQAAgent(BaseAgent):
    """
    Agent responsible for:
    - Answer questions about project status
    - Provide information about tasks, deadlines, and team members
    - Search project history and documentation
    - Explain project workflows and processes
    - Assist with project-related queries
    - Provide contextual help and guidance
    - Retrieve project information quickly
    - Support natural language queries
    - Learn from project patterns and provide insights
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Knowledge Q&A Agent for a project management system.
        Your role is to answer questions about projects, tasks, team members, and provide helpful information.
        You ONLY provide descriptive answers and information - you do NOT perform actions like creating projects or tasks.
        For action requests (creating projects, tasks, etc.), users should use the Project Pilot agent.
        You should be conversational, accurate, and provide context-aware responses."""
    
    def answer_question(self, question: str, context: Optional[Dict] = None, available_users: Optional[List[Dict]] = None) -> Dict:
        """
        Answer a question about the project. This agent ONLY provides descriptive answers.
        For action requests (creating projects/tasks), use the Project Pilot agent.
        
        Args:
            question (str): User's question
            context (Dict): Optional context (project info, tasks, etc.)
            available_users (List[Dict]): List of available users/team members
            
        Returns:
            Dict: Answer with relevant information
        """
        self.log_action("Answering question", {"question": question[:50]})
        
        # Build context string
        context_str = ""
        if context:
            # Always show all projects first
            if 'all_projects' in context:
                projects = context['all_projects']
                context_str += f"\nAll Your Projects ({len(projects)} total):\n"
                for proj in projects:
                    context_str += f"- ID: {proj.get('id', 'N/A')}, Name: {proj.get('name', 'Unknown')}, "
                    context_str += f"Status: {proj.get('status', 'Unknown')}, "
                    context_str += f"Priority: {proj.get('priority', 'Unknown')}, "
                    context_str += f"Tasks: {proj.get('tasks_count', 0)}\n"
                    if proj.get('description'):
                        context_str += f"  Description: {proj.get('description', '')}\n"
            
            # Show specific project details if provided
            if 'project' in context:
                project = context['project']
                context_str += f"\nCurrent Project (Selected):\n"
                context_str += f"- Name: {project.get('name', 'Unknown')}\n"
                context_str += f"- ID: {project.get('id', 'Unknown')}\n"
                context_str += f"- Status: {project.get('status', 'Unknown')}\n"
                context_str += f"- Tasks: {project.get('tasks_count', 0)} tasks\n"
            
            # Show tasks
            if 'tasks' in context:
                context_str += f"\nCurrent Tasks:\n"
                for task in context['tasks'][:20]:  # Show more tasks
                    task_line = f"- ID: {task.get('id', 'N/A')}, Title: {task.get('title', '')} (Status: {task.get('status', '')}, Priority: {task.get('priority', 'N/A')})"
                    if task.get('assignee_username'):
                        task_line += f" [Assigned to: {task.get('assignee_username')}]"
                    if task.get('project_name'):
                        task_line += f" [Project: {task.get('project_name')}]"
                    context_str += task_line + "\n"
        
        # Add available users information
        users_str = ""
        if available_users:
            users_str = f"\nAvailable Users/Team Members ({len(available_users)} total):\n"
            for user in available_users:
                users_str += f"- ID: {user.get('id', 'N/A')}, Username: {user.get('username', 'Unknown')}, Name: {user.get('name', user.get('username', 'Unknown'))}\n"
                if 'role' in user:
                    users_str += f"  Role: {user.get('role')}\n"
        
        # Add user-task assignments if available
        assignments_str = ""
        if 'user_assignments' in context:
            assignments_str = "\n\n📋 USER-TASK ASSIGNMENTS:\n"
            assignments_str += f"Total Users with Assignments: {len([u for u in context['user_assignments'] if u.get('total_tasks', 0) > 0])}\n\n"
            
            for assignment in context['user_assignments']:
                if assignment.get('total_tasks', 0) > 0:
                    assignments_str += f"\n👤 {assignment.get('name', assignment.get('username', 'Unknown'))} (Username: {assignment.get('username', 'Unknown')}) - {assignment.get('total_tasks', 0)} task(s) assigned:\n"
                    for project_info in assignment.get('projects', []):
                        assignments_str += f"  📁 Project: {project_info.get('project_name', 'Unknown')}\n"
                        for task in project_info.get('tasks', []):
                            assignments_str += f"    - Task: \"{task.get('title', 'Unknown')}\" (Status: {task.get('status', 'N/A')}, Priority: {task.get('priority', 'N/A')})\n"
                else:
                    assignments_str += f"\n👤 {assignment.get('name', assignment.get('username', 'Unknown'))} (Username: {assignment.get('username', 'Unknown')}) - No tasks assigned\n"
        
        context_str += assignments_str
        
        # Check if user is asking for an action (create, add, update, etc.)
        question_lower = question.lower()
        action_keywords = ['create', 'add', 'make', 'assign', 'update', 'change', 'modify', 'edit', 'set', 'adjust', 'new task', 'new project']
        is_action_request = any(keyword in question_lower for keyword in action_keywords)
        
        if is_action_request:
            # Redirect to Project Pilot agent
            prompt = f"""The user is asking you to perform an action (like creating a project or task).

{context_str}
{users_str}

User Request: {question}

You are the Knowledge Q&A agent. You ONLY answer questions and provide information.
You do NOT perform actions like creating projects or tasks.

Respond politely that:
1. You only answer questions and provide information
2. For action requests like creating projects or tasks, they should use the Project Pilot agent
3. You can help them understand their projects and tasks, but cannot create them

Example response:
"I'm the Knowledge Q&A agent, and I only provide information and answer questions. For creating projects or tasks, please use the Project Pilot agent. However, I can help you understand your current projects and tasks if you have questions about them!"

Return a helpful text response (NOT JSON)."""
        else:
            # Regular Q&A request
            prompt = f"""Answer the following question about the project management system.
        
{context_str}
{users_str}

Question: {question}

IMPORTANT INSTRUCTIONS:
- If the question asks about users and their task assignments, use the "USER-TASK ASSIGNMENTS" section above to provide detailed information
- List all users and clearly show which tasks each user is assigned to, grouped by project
- Be specific: include task titles, status, priority, and which project each task belongs to
- If a user has no tasks assigned, mention that clearly
- Provide a clear, organized answer that's easy to read

Provide a helpful, accurate answer. If the question is about specific data that isn't in the context, mention that.
Be conversational and clear. If asked about available users and their assignments, provide detailed information from the assignments section above."""
        
        try:
            max_tokens = 800
            response = self._call_llm(prompt, self.system_prompt, temperature=0.7, max_tokens=max_tokens)
            
            return {
                "success": True,
                "answer": response,
                "question": question
            }
        except Exception as e:
            self.log_action("Error answering question", {"error": str(e)})
            return {
                "success": False,
                "error": str(e),
                "answer": "I'm sorry, I encountered an error while processing your question. Please try again."
            }
    
    def search_project_history(self, query: str, project_id: int) -> Dict:
        """
        Search project history and documentation.
        
        Args:
            query (str): Search query
            project_id (int): Project ID to search
            
        Returns:
            Dict: Search results
        """
        # This would typically search a database or knowledge base
        # For now, return a placeholder
        return {
            "success": True,
            "query": query,
            "results": [],
            "message": "Project history search not yet fully implemented"
        }
    
    def explain_workflow(self, workflow_name: str) -> Dict:
        """
        Explain a project workflow or process.
        
        Args:
            workflow_name (str): Name of the workflow
            
        Returns:
            Dict: Workflow explanation
        """
        prompt = f"""Explain the project management workflow or process: {workflow_name}

Provide a clear, step-by-step explanation of how this workflow works."""
        
        try:
            explanation = self._call_llm(prompt, self.system_prompt, temperature=0.5)
            return {
                "success": True,
                "workflow": workflow_name,
                "explanation": explanation
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_project_summary(self, project_id: int) -> Dict:
        """
        Get a comprehensive summary of a project.
        
        Args:
            project_id (int): Project ID
            
        Returns:
            Dict: Project summary
        """
        # This would fetch project data and generate summary
        return {
            "success": True,
            "project_id": project_id,
            "summary": "Project summary generation not yet fully implemented"
        }
    
    def provide_insights(self, project_id: int) -> Dict:
        """
        Provide insights based on project patterns.
        
        Args:
            project_id (int): Project ID
            
        Returns:
            Dict: Project insights
        """
        # This would analyze project data and provide insights
        return {
            "success": True,
            "project_id": project_id,
            "insights": "Insight generation not yet fully implemented"
        }
    
    def process(self, question: str, **kwargs) -> Dict:
        """
        Main processing method for Q&A agent.
        
        Args:
            question (str): User's question or query
            **kwargs: Additional context parameters (context, available_users, etc.)
            
        Returns:
            dict: Answer and relevant information, may include action to perform
        """
        self.log_action("Processing question", {"question": question[:50]})
        
        context = kwargs.get('context', {})
        available_users = kwargs.get('available_users', [])
        return self.answer_question(question, context, available_users)

