"""
Subtask Generation Agent
Generates detailed subtasks for tasks to help users understand what they need to do.
"""

from .base_agent import BaseAgent
from .enhancements.subtask_generation_enhancements import SubtaskGenerationEnhancements
from typing import List, Dict, Optional
import json


class SubtaskGenerationAgent(BaseAgent):
    """
    Agent responsible for:
    - Generating detailed subtasks for tasks
    - Breaking down complex tasks into actionable steps
    - Creating subtasks that help users understand what to do
    """
    
    def __init__(self):
        super().__init__()
        self.system_prompt = """You are a Subtask Generation Agent for a project management system.
        Your role is to break down tasks into detailed, actionable subtasks that help users understand exactly what they need to do.
        You should create comprehensive, step-by-step subtasks that cover all aspects of completing a task.
        Always provide clear, specific, and actionable subtasks."""
    
    def generate_subtasks(self, task: Dict) -> List[Dict]:
        """
        Generate subtasks for a given task.
        
        Args:
            task (Dict): Task information with id, title, description, etc.
            
        Returns:
            List[Dict]: List of subtask dictionaries with title, description, and order
        """
        self.log_action("Generating subtasks", {"task_id": task.get('id'), "task_title": task.get('title')})
        
        # Enhanced: Determine optimal granularity
        optimal_count = SubtaskGenerationEnhancements.determine_optimal_granularity(task)
        
        # Enhanced: Get domain template
        project_type = task.get('project_type') or task.get('project', {}).get('project_type')
        domain_template = SubtaskGenerationEnhancements.get_domain_template(
            task.get('description', '') + ' ' + task.get('title', ''),
            project_type
        )
        
        domain_guidance = ""
        if domain_template:
            domain_guidance = f"""
DOMAIN-SPECIFIC GUIDANCE:
This task appears to be in the {domain_template.get('phases', [])} domain.
Consider these common phases: {', '.join(domain_template.get('phases', []))}
Common subtask patterns: {', '.join(domain_template.get('common_subtasks', [])[:5])}
"""
        
        prompt = f"""You are an expert at breaking down tasks into detailed, actionable subtasks with comprehensive descriptions.

Task Information:
- Title: {task.get('title', 'Unknown')}
- Description: {task.get('description', 'No description')}
- Status: {task.get('status', 'todo')}
- Priority: {task.get('priority', 'medium')}
- Estimated Hours: {task.get('estimated_hours', 'Not specified')}
{domain_guidance}

Your goal is to break down this task into {optimal_count} detailed, actionable subtasks that help someone understand exactly what they need to do to complete this task efficiently.

CRITICAL REQUIREMENTS for subtask descriptions:
Each subtask description must be COMPREHENSIVE (6-8 sentences) and include:
1. WHAT the subtask is - Clear explanation of what needs to be accomplished in this step
2. HOW to do it - Detailed step-by-step methodology and approach specific to this subtask (be specific about the process)
3. WHY this subtask is relevant - Explain how this subtask contributes to completing the parent task and why it's necessary
4. WHICH TOOLS/TECHNOLOGIES to use - Specific technologies, frameworks, libraries, commands, software, or tools needed for this subtask (be specific: e.g., "React.js for frontend", "PostgreSQL database", "Docker for containerization", "Git for version control")
5. MOST EFFICIENT WAY - Best practices, shortcuts, optimizations, and efficient approaches for this specific subtask
6. DEPENDENCIES - What needs to be done before this subtask (if any) and what this subtask enables next

IMPORTANT: You must also provide a DETAILED reasoning explaining:
- WHY this task should be broken down in this specific way
- HOW the subtasks relate to each other and the overall task goal
- WHAT approach or methodology should be used to complete this task most efficiently
- WHAT potential challenges or considerations need to be addressed
- HOW to execute these subtasks effectively and in the right order

Guidelines for creating subtasks:
1. Make each subtask specific and actionable (someone should be able to understand what to do)
2. Cover all aspects of the task (planning, setup, implementation, testing, documentation if needed)
3. Order subtasks logically (what should be done first, second, etc.) for maximum efficiency
4. Make subtasks granular enough to be meaningful but not too small
5. Consider the task's domain/context when creating subtasks
6. Include setup, implementation, and verification steps when appropriate
7. Ensure subtasks flow logically and build upon each other for efficient completion

For each subtask, provide:
- title: A clear, specific title (e.g., "Set up OAuth integration with Instagram API" or "Design database schema for trust ledger")
- description: A COMPREHENSIVE description (6-8 sentences) that includes:
  * WHAT the subtask is - what needs to be accomplished in this step
  * HOW to do it - detailed step-by-step approach and methodology (be specific about the process)
  * WHY this subtask is relevant - how this subtask contributes to completing the parent task and why it's necessary
  * WHICH TOOLS/TECHNOLOGIES to use - specific tools, technologies, frameworks, libraries, software, or commands needed (be specific: e.g., "React.js", "PostgreSQL", "Docker", "Git", "Node.js", "Express.js", "JWT", etc.)
  * MOST EFFICIENT WAY - best practices, optimizations, shortcuts, and efficient approaches
  * DEPENDENCIES - what needs to be done before this subtask and what this subtask enables next
- order: The sequence number (1, 2, 3, etc.) indicating when this subtask should be done

Return a JSON object with this structure:
{{
  "subtasks": [
    {{
      "title": "Specific subtask title",
      "description": "COMPREHENSIVE description (6-8 sentences): WHAT this subtask accomplishes, HOW to do it step-by-step (detailed methodology), WHY this subtask is relevant to the parent task, WHICH TOOLS/TECHNOLOGIES to use (be specific: e.g., React.js, PostgreSQL, Docker, Git, Node.js, etc.), the MOST EFFICIENT WAY to complete it, and what DEPENDENCIES exist. Make it detailed enough that a developer can understand exactly what to do, how to do it, why it's needed, and what tools to use.",
      "order": 1
    }},
    {{
      "title": "Next subtask title",
      "description": "COMPREHENSIVE description (6-8 sentences) following the same format: WHAT, HOW, WHY relevant, TOOLS/TECHNOLOGIES, EFFICIENT WAY, DEPENDENCIES...",
      "order": 2
    }}
  ],
  "task_reasoning": "DETAILED explanation (5-7 sentences): WHY this task should be broken down in this specific way, HOW the subtasks relate to each other and flow logically for efficient completion, WHAT approach or methodology should be used to complete this task most efficiently, WHAT potential challenges or considerations need to be addressed, HOW to execute these subtasks effectively, and WHAT the overall strategy is for completing this task efficiently."
}}

Rules:
- Return ONLY the JSON object, no explanations
- Create 4-8 subtasks (adjust based on task complexity - more complex tasks need more subtasks)
- Make subtasks specific to this task (not generic)
- Order subtasks logically (order field: 1, 2, 3, etc.) for efficient execution
- Each subtask description must be COMPREHENSIVE (6-8 sentences) covering WHAT, HOW (detailed steps), WHY relevant, TOOLS/TECHNOLOGIES (be specific), EFFICIENT WAY, and DEPENDENCIES
- Always mention specific tools, technologies, frameworks, or software needed (e.g., "Use React.js for the frontend component", "Set up PostgreSQL database", "Use Docker for containerization")
- Explain why each subtask is relevant to completing the parent task
- Include detailed task_reasoning explaining the breakdown strategy and efficiency considerations"""

        try:
            response = self._call_llm(prompt, self.system_prompt, temperature=0.5, max_tokens=2048)
            
            # Try to extract JSON from response (handle markdown code blocks)
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            elif "```" in response:
                json_start = response.find("```") + 3
                json_end = response.find("```", json_start)
                response = response[json_start:json_end].strip()
            
            # Parse JSON response
            parsed_data = json.loads(response)
            
            # Handle both old format (array) and new format (object with subtasks and task_reasoning)
            if isinstance(parsed_data, dict):
                subtasks_data = parsed_data.get('subtasks', [])
                task_reasoning = parsed_data.get('task_reasoning', '')
                
                # Enhanced: Add quality gates and dependency analysis
                try:
                    # Add quality gates
                    subtasks_data = SubtaskGenerationEnhancements.add_quality_gates(subtasks_data)
                    
                    # Identify dependencies
                    dependency_analysis = SubtaskGenerationEnhancements.identify_subtask_dependencies(subtasks_data)
                    
                    # Store reasoning in the return dict for later use
                    return {
                        'subtasks': subtasks_data,
                        'task_reasoning': task_reasoning,
                        'dependency_analysis': dependency_analysis,
                        'optimal_count': optimal_count,
                    }
                except Exception as e:
                    self.log_action("Error enhancing subtasks", {"error": str(e)})
                    # Return without enhancements if error
                    return {
                        'subtasks': subtasks_data,
                        'task_reasoning': task_reasoning
                    }
            elif isinstance(parsed_data, list):
                # Old format - just return the list
                return parsed_data
            else:
                return []
            
        except json.JSONDecodeError as e:
            self.log_action("Error parsing subtasks JSON", {"error": str(e), "response": response[:200]})
            # Try to extract JSON from markdown code blocks
            try:
                import re
                # Try to match both array and object formats
                json_match = re.search(r'```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```', response, re.DOTALL)
                if json_match:
                    parsed_data = json.loads(json_match.group(1))
                    if isinstance(parsed_data, dict):
                        return {
                            'subtasks': parsed_data.get('subtasks', []),
                            'task_reasoning': parsed_data.get('task_reasoning', '')
                        }
                    elif isinstance(parsed_data, list):
                        return parsed_data
                    else:
                        return []
            except:
                pass
            
            return []
        except Exception as e:
            from core.api_key_service import KeyServiceError
            if isinstance(e, KeyServiceError):
                raise
            self.log_action("Error generating subtasks", {"error": str(e)})
            return []
    
    def generate_subtasks_for_project(self, tasks: List[Dict]) -> Dict[int, Dict]:
        """
        Generate subtasks for all tasks in a project.
        
        Args:
            tasks (List[Dict]): List of tasks
            
        Returns:
            Dict[int, Dict]: Dictionary mapping task_id to dict with 'subtasks' list and 'task_reasoning' string
        """
        self.log_action("Generating subtasks for project", {"task_count": len(tasks)})
        
        result = {}
        for task in tasks:
            subtask_result = self.generate_subtasks(task)
            # Handle both old format (list) and new format (dict)
            if isinstance(subtask_result, dict):
                result[task.get('id')] = subtask_result
            else:
                # Old format - wrap in dict
                result[task.get('id')] = {
                    'subtasks': subtask_result,
                    'task_reasoning': ''
                }
        
        return result
    
    def process(self, action: str, **kwargs) -> Dict:
        """
        Main processing method for subtask generation agent.
        
        Args:
            action (str): Action to perform:
                - 'generate_for_task': Generate subtasks for a single task
                - 'generate_for_project': Generate subtasks for all tasks in a project
            **kwargs: Action-specific parameters
            
        Returns:
            dict: Processing results
        """
        self.log_action(f"Processing action: {action}", kwargs)
        
        try:
            if action == "generate_for_task":
                task = kwargs.get('task', {})
                if not task:
                    return {"success": False, "error": "Task is required"}
                
                subtask_result = self.generate_subtasks(task)
                # Handle both old format (list) and new format (dict)
                if isinstance(subtask_result, dict):
                    return {
                        "success": True,
                        "task_id": task.get('id'),
                        "subtasks": subtask_result.get('subtasks', []),
                        "task_reasoning": subtask_result.get('task_reasoning', '')
                    }
                else:
                    return {
                        "success": True,
                        "task_id": task.get('id'),
                        "subtasks": subtask_result,
                        "task_reasoning": ''
                    }
            
            elif action == "generate_for_project":
                tasks = kwargs.get('tasks', [])
                if not tasks:
                    return {"success": False, "error": "Tasks list is required"}
                
                result = self.generate_subtasks_for_project(tasks)
                return {
                    "success": True,
                    "subtasks_by_task": result
                }
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
                
        except Exception as e:
            self.log_action(f"Error processing {action}", {"error": str(e)})
            return {"success": False, "error": str(e)}

